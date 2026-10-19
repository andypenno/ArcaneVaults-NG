#include "PlayerEquipment.h"
#include "Settings.h"
#include "TransferFeedback.h"
#include <cmath>
#include <atomic>
#include <chrono>
#include <thread>

namespace PlayerEquipment {
    namespace {
        std::optional<std::unordered_set<RE::ExtraDataList*>> ReadRows(
            const std::vector<RE::ItemList::Item*>& rows, RE::RefHandle owner, const std::vector<StackIdentity>& stacks) {
            std::unordered_set<RE::ExtraDataList*> seen, protectedStacks;
            std::int64_t represented{}, expected{};
            int bare{};
            for (const auto& stack : stacks) {
                expected += stack.count;
                if (!stack.extra) bare = stack.count;
            }
            for (auto* row : rows) {
                auto* entry = row->data.objDesc;
                if (row->data.owner != owner || entry->countDelta <= 0 || !row->obj.IsObject()) return std::nullopt;
                RE::GFxValue state, equipped;
                const bool hasState = row->obj.GetMember("equipState", &state);
                const bool hasEquipped = row->obj.GetMember("isEquipped", &equipped);
                if ((hasState && !state.IsNumber()) || (hasEquipped && !equipped.IsBool())) return std::nullopt;
                if ((!hasState && !hasEquipped) || (hasState && (!std::isfinite(state.GetNumber()) || state.GetNumber() < 0)))
                    return std::nullopt;
                const bool worn = (hasState && state.GetNumber() > 0) || (hasEquipped && equipped.GetBool());
                std::int64_t explicitCount{};
                if (entry->extraLists) for (auto* extra : *entry->extraLists) {
                    if (!extra) continue;
                    const StackIdentity* match{};
                    for (const auto& stack : stacks) {
                        if (!stack.extra) continue;
                        auto* a = extra->GetByType<RE::ExtraUniqueID>();
                        if (extra != stack.extra && (!a || !stack.unique || a->baseID != stack.unique->first || a->uniqueID != stack.unique->second)) continue;
                        if (match) return std::nullopt;
                        match = &stack;
                    }
                    if (!match || !seen.insert(match->extra).second || extra->GetCount() != match->count) return std::nullopt;
                    explicitCount += match->count;
                    if (worn) protectedStacks.insert(match->extra);
                }
                const auto implicitCount = entry->countDelta - explicitCount;
                if (implicitCount < 0 || implicitCount > bare) return std::nullopt;
                bare -= static_cast<int>(implicitCount);
                if (implicitCount && worn) protectedStacks.insert(nullptr);
                represented += entry->countDelta;
            }
            if (represented != expected || bare != 0) return std::nullopt;
            for (const auto& stack : stacks)
                if (stack.extra && !seen.contains(stack.extra)) return std::nullopt;
            return protectedStacks;
        }
    }

    namespace {
        using Clock = std::chrono::steady_clock;
        enum class Phase { Waiting, Opening, Reading, Closing };
        constexpr auto inspectionBudget = std::chrono::seconds(1);
        struct Request {
            std::function<void()> work, complete;
            std::atomic<bool> cancelled{};
            Phase phase{Phase::Waiting};
            Clock::time_point deadline{Clock::now() + inspectionBudget};
            Clock::time_point refreshAt{};
            RE::IMenu* owned{};
            Snapshot snapshot;
            std::unordered_set<RE::TESBoundObject*> expectedEquipped;
            RE::RefHandle owner{};
            Clock::time_point retry{};
            bool worked{};
            bool refreshRequested{};
        };
        std::shared_ptr<Request> pending;
        thread_local const Snapshot* current{};

        std::vector<StackIdentity> Identities(const std::vector<InventoryStacks::Stack>& stacks) {
            std::vector<StackIdentity> result;
            for (const auto& stack : stacks) {
                StackIdentity identity{stack.extra, stack.count, {}, false};
                if (stack.extra) {
                    if (auto* id = stack.extra->GetByType<RE::ExtraUniqueID>()) identity.unique = {id->baseID, id->uniqueID};
                    identity.worn = stack.extra->HasType<RE::ExtraWorn>() || stack.extra->HasType<RE::ExtraWornLeft>();
                }
                result.push_back(identity);
            }
            return result;
        }

        Snapshot Capture(RE::PlayerCharacter* player, InventoryStacks::Select select = {}) {
            std::unordered_map<RE::TESBoundObject*, std::vector<InventoryStacks::Stack>> items;
            for (const auto& stack : InventoryStacks::Read(player, std::move(select), nullptr, false, [](auto& item) {
                return item.template As<RE::TESObjectARMO>() || item.template As<RE::TESObjectWEAP>();
            })) items[stack.item].push_back(stack);
            Snapshot result;
            for (const auto& [item, stacks] : items)
                result.emplace(item, ItemEquipment{{}, Identities(stacks)});
            return result;
        }

        Snapshot Read(RE::InventoryMenu* menu, const Snapshot& physical, RE::RefHandle owner) {
            if (!menu || !menu->uiMovie || !menu->GetRuntimeData().itemList) return {};
            std::unordered_map<RE::TESBoundObject*, std::vector<RE::ItemList::Item*>> rowsByItem;
            for (auto* row : menu->GetRuntimeData().itemList->items)
                if (row && row->data.objDesc && physical.contains(row->data.objDesc->object))
                    rowsByItem[row->data.objDesc->object].push_back(row);
            Snapshot result;
            for (const auto& [item, equipment] : physical) {
                const auto found = rowsByItem.find(item);
                if (found == rowsByItem.end()) continue;
                auto rows = ReadRows(found->second, owner, equipment.stacks);
                if (rows) result.emplace(item, ItemEquipment{std::move(*rows), equipment.stacks});
            }
            return result;
        }

        bool Active(const std::shared_ptr<Request>& request) {
            return !request->cancelled && pending == request;
        }

        void Finish(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            pending.reset();
            request->cancelled = true;
            if (request->complete) request->complete();
        }

        void Work(const std::shared_ptr<Request>& request, const Snapshot& snapshot) {
            if (request->worked) return;
            request->worked = true;
            struct ClearSnapshot { ~ClearSnapshot() { current = nullptr; } } clear;
            Snapshot validated;
            auto* player = RE::PlayerCharacter::GetSingleton();
            std::unordered_map<RE::TESBoundObject*, std::vector<InventoryStacks::Stack>> fresh;
            if (!snapshot.empty())
                for (const auto& stack : InventoryStacks::Read(player)) fresh[stack.item].push_back(stack);
            for (const auto& [item, equipment] : snapshot) {
                const auto found = fresh.find(item);
                if (found != fresh.end() && equipment.stacks == Identities(found->second))
                    validated.emplace(item, equipment);
            }
            current = &validated;
            try { request->work(); }
            catch (const std::exception&) { logger::error("Quick Transfer failed during equipment inspection"); }
        }

        void Poll(const std::shared_ptr<Request>& request);
        void Later(const std::shared_ptr<Request>& request) {
            std::thread([request] {
                std::this_thread::sleep_for(std::chrono::milliseconds(16));
                if (!request->cancelled)
                    SKSE::GetTaskInterface()->AddTask([request] { Poll(request); });
            }).detach();
        }

        void Close(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            request->phase = Phase::Closing;
            request->retry = Clock::now() + std::chrono::milliseconds(100);
            request->deadline = Clock::now() + inspectionBudget;
            if (auto* queue = RE::UIMessageQueue::GetSingleton())
                queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kHide, nullptr);
            Later(request);
        }

        void Poll(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            auto* ui = RE::UI::GetSingleton();
            auto* queue = RE::UIMessageQueue::GetSingleton();
            if (!ui || !queue) { if (!request->owned) Work(request, {}); Finish(request); return; }
            const auto expired = Clock::now() >= request->deadline;
            if (request->phase == Phase::Waiting) {
                if (ui->IsMenuOpen(RE::MessageBoxMenu::MENU_NAME) && !expired) { Later(request); return; }
                if (expired || ui->IsItemMenuOpen()) {
                    Work(request, {}); Finish(request); return;
                }
                request->phase = Phase::Opening;
                queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kShow, nullptr);
                Later(request);
                return;
            }
            auto menu = ui->GetMenu(RE::InventoryMenu::MENU_NAME);
            const bool open = menu && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME);
            if (request->phase == Phase::Opening && open) {
                if (request->owned && menu.get() != request->owned) { Finish(request); return; }
                if (!request->owned)
                    request->refreshAt = Clock::now() + std::chrono::duration_cast<std::chrono::milliseconds>(inspectionBudget) * 3 / 4;
                request->owned = menu.get();
                request->phase = Phase::Reading;
                SKSE::GetTaskInterface()->AddUITask([request] {
                    if (request->cancelled) return;
                    auto* ui = RE::UI::GetSingleton();
                    auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                    Snapshot snapshot;
                    if (menu && menu.get() == request->owned && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME)) {
                        auto* inventory = skyrim_cast<RE::InventoryMenu*>(menu.get());
                        auto* list = inventory->GetRuntimeData().itemList;
                        const bool ready = menu->uiMovie && list;
                        if (ready) try {
                            snapshot = Read(inventory, request->snapshot, request->owner);
                        } catch (const std::exception&) { logger::error("Could not read equipment rows for Quick Transfer"); }
                        for (auto* item : request->expectedEquipped) {
                            const auto found = snapshot.find(item);
                            if (found != snapshot.end() && found->second.equipped.empty()) snapshot.erase(found);
                        }
                        if (snapshot.size() != request->snapshot.size() && Clock::now() < request->deadline) {
                            // Leave initial loading alone; reserve the final quarter of the budget for one recovery refresh.
                            if (ready && !request->refreshRequested &&
                                Clock::now() >= request->refreshAt) {
                                request->refreshRequested = true;
                                if (auto* player = RE::PlayerCharacter::GetSingleton()) {
                                    auto* data = new RE::InventoryUpdateData{};
                                    data->inventoryRef = player->GetHandle().native_handle();
                                    data->updateObj = nullptr;
                                    RE::UIMessageQueue::GetSingleton()->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kInventoryUpdate, data);
                                }
                            }
                            SKSE::GetTaskInterface()->AddTask([request] {
                                if (Active(request) && request->phase == Phase::Reading) {
                                    request->phase = Phase::Opening;
                                    Later(request);
                                }
                            });
                            return;
                        }
                        if (menu->uiMovie) menu->uiMovie->SetVisible(false);
                    }
                    SKSE::GetTaskInterface()->AddTask([request, snapshot = std::move(snapshot)] {
                        if (!Active(request) || request->phase != Phase::Reading) return;
                        auto* ui = RE::UI::GetSingleton();
                        auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                        const bool owned = menu && menu.get() == request->owned && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME);
                        if (owned) { request->snapshot = std::move(snapshot); Close(request); }
                        else Finish(request);
                    });
                });
            } else if (request->phase == Phase::Closing) {
                if (!open) {
                    menu = nullptr;
                    if (!ui->IsItemMenuOpen()) Work(request, request->snapshot);
                    Finish(request); return;
                }
                if (request->owned && menu.get() != request->owned) { Finish(request); return; }
                if (expired) {
                    if (!request->worked) TransferFeedback::Reset();
                    request->worked = true;
                    request->snapshot.clear();
                    SKSE::GetTaskInterface()->AddUITask([request] {
                        auto* ui = RE::UI::GetSingleton();
                        auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                        if (!request->cancelled && menu && menu.get() == request->owned && menu->uiMovie)
                            menu->uiMovie->SetVisible(true);
                    });
                    request->deadline = Clock::now() + inspectionBudget;
                } else if (!request->worked && Clock::now() >= request->retry) {
                    queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kHide, nullptr);
                    request->retry = Clock::now() + std::chrono::milliseconds(100);
                }
            } else if (expired) {
                request->snapshot.clear();
                if (!request->owned || (open && menu.get() == request->owned)) Close(request);
                else { menu = nullptr; Finish(request); }
                return;
            }
            Later(request);
        }
    }

    const Snapshot* Current() { return current; }

    bool Apply(Snapshot& snapshot, RE::TESBoundObject* item, const std::function<bool()>& work) {
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!player || !item) return false;
        const bool equipment = item->As<RE::TESObjectARMO>() || item->As<RE::TESObjectWEAP>();
        auto found = snapshot.find(item);
        if (equipment) {
            if (found == snapshot.end()) return false;
            if (found->second.stacks != Identities(InventoryStacks::Read(player, {}, item))) {
                snapshot.erase(found);
                return false;
            }
        }
        struct Restore { const Snapshot* previous{current}; ~Restore() { current = previous; } } restore;
        current = &snapshot;
        const bool changed = work();
        if (equipment && changed) {
            const auto fresh = Identities(InventoryStacks::Read(player, {}, item));
            const auto& before = found->second;
            for (const auto* protectedStack : before.equipped) {
                const auto old = std::ranges::find_if(before.stacks, [protectedStack](const auto& stack) { return stack.extra == protectedStack; });
                if (old == before.stacks.end() || std::ranges::find(fresh, *old) == fresh.end()) {
                    snapshot.erase(found);
                    return changed;
                }
            }
            found->second.stacks = fresh;
        }
        return changed;
    }

    void Run(std::function<void()> work, std::function<void()> complete, std::function<bool(RE::TESBoundObject*)> eligible) {
        if (pending) return;
        auto* player = RE::PlayerCharacter::GetSingleton();
        std::unordered_set<RE::TESBoundObject*> movable;
        auto physical = Capture(player, [&eligible, &movable](auto* item, auto& entry, auto* extra) {
            if (entry.IsQuestObject() || Settings::GetSingleton()->IsIgnored(item) ||
                HasCategory(ClassifyItem(item), ItemCategory::Ignore) || (eligible && !eligible(item))) return false;
            const bool worn = extra && (extra->template HasType<RE::ExtraWorn>() || extra->template HasType<RE::ExtraWornLeft>());
            if (!worn && !InventoryStacks::IsFavorited(entry, extra)) movable.insert(item);
            return true;
        });
        auto request = std::make_shared<Request>();
        const auto* command = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
        const auto equipped = command ? command->conditionFunction : nullptr;
        for (auto& [item, equipment] : physical) {
            if (!movable.contains(item)) continue;
            const bool single = equipment.stacks.size() == 1 && equipment.stacks.front().count == 1;
            double worn{};
            const bool formEquipped = (!single || request->snapshot.empty()) &&
                equipped && equipped(player, item, nullptr, worn) && worn != 0.0;
            if (formEquipped && single) continue;
            if (formEquipped) request->expectedEquipped.insert(item);
            request->snapshot.emplace(item, std::move(equipment));
        }
        request->work = std::move(work); request->complete = std::move(complete);
        pending = request;
        if (request->snapshot.empty()) { Work(request, {}); Finish(request); }
        else {
            request->owner = player->GetHandle().native_handle();
            Poll(request);
        }
    }

    void Run(std::function<void()> work, std::function<void()> complete) {
        Run(std::move(work), std::move(complete), {});
    }

    bool IsRunning() { return pending != nullptr; }

    void Reset() {
        if (!pending) return;
        auto request = std::move(pending);
        request->cancelled = true;
        auto* ui = RE::UI::GetSingleton();
        auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
        if ((!request->owned && request->phase != Phase::Waiting) ||
            (request->owned && menu && menu.get() == request->owned))
            if (auto* queue = RE::UIMessageQueue::GetSingleton())
                queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kHide, nullptr);
    }
}
