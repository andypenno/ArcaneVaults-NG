#include "PlayerEquipment.h"
#include <cmath>
#include <atomic>
#include <chrono>
#include <thread>

namespace PlayerEquipment {
    namespace {
        std::optional<std::unordered_set<RE::ExtraDataList*>> ReadRows(
            const std::vector<RE::ItemList::Item*>& rows, RE::RefHandle owner, const std::vector<InventoryStacks::Stack>& stacks) {
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
                    RE::ExtraDataList* match{};
                    for (const auto& stack : stacks) {
                        if (!stack.extra) continue;
                        auto* a = extra->GetByType<RE::ExtraUniqueID>();
                        auto* b = stack.extra->GetByType<RE::ExtraUniqueID>();
                        if (extra != stack.extra && (!a || !b || a->baseID != b->baseID || a->uniqueID != b->uniqueID)) continue;
                        if (match) return std::nullopt;
                        match = stack.extra;
                    }
                    if (!match || !seen.insert(match).second || extra->GetCount() != match->GetCount()) return std::nullopt;
                    explicitCount += match->GetCount();
                    if (worn) protectedStacks.insert(match);
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
            RE::IMenu* owned{};
            Snapshot snapshot;
            Clock::time_point retry{};
            bool worked{};
            bool refreshRequested{};
            unsigned rowRetries{};
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

        Snapshot Read(RE::InventoryMenu* menu, RE::PlayerCharacter* player) {
            if (!menu || !player || !menu->uiMovie || !menu->GetRuntimeData().itemList) return {};
            std::unordered_map<RE::TESBoundObject*, std::vector<InventoryStacks::Stack>> items;
            for (const auto& stack : InventoryStacks::Read(player)) items[stack.item].push_back(stack);
            std::unordered_map<RE::TESBoundObject*, std::vector<RE::ItemList::Item*>> rowsByItem;
            for (auto* row : menu->GetRuntimeData().itemList->items)
                if (row && row->data.objDesc && row->data.objDesc->object)
                    rowsByItem[row->data.objDesc->object].push_back(row);
            Snapshot result;
            for (const auto& [item, stacks] : items) {
                const auto found = rowsByItem.find(item);
                if (found == rowsByItem.end()) continue;
                auto rows = ReadRows(found->second, player->GetHandle().native_handle(), stacks);
                if (rows) result.emplace(item, ItemEquipment{std::move(*rows), Identities(stacks)});
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
                        bool postpone = !ready;
                        if (ready && Clock::now() < request->deadline) {
                            bool rowsReady = list->root.IsObject();
                            if (!rowsReady) for (auto* row : list->items) {
                                if (row && row->data.objDesc && row->data.objDesc->object && row->obj.IsObject()) {
                                    rowsReady = true;
                                    break;
                                }
                            }
                            auto* player = RE::PlayerCharacter::GetSingleton();
                            if ((list->items.empty() || !rowsReady) && !request->refreshRequested && player) {
                                request->refreshRequested = true;
                                auto* data = new RE::InventoryUpdateData{};
                                data->inventoryRef = player->GetHandle().native_handle();
                                data->updateObj = nullptr;
                                RE::UIMessageQueue::GetSingleton()->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kInventoryUpdate, data);
                                postpone = true;
                            } else if (!rowsReady && !list->items.empty() && request->rowRetries < 2) {
                                ++request->rowRetries;
                                postpone = true;
                            }
                        }
                        if (postpone && Clock::now() < request->deadline) {
                            SKSE::GetTaskInterface()->AddTask([request] {
                                if (Active(request) && request->phase == Phase::Reading) {
                                    request->phase = Phase::Opening;
                                    Later(request);
                                }
                            });
                            return;
                        }
                        if (ready) try {
                            auto* player = RE::PlayerCharacter::GetSingleton();
                            snapshot = Read(inventory, player);
                        } catch (const std::exception&) { logger::error("Could not read equipment rows for Quick Transfer"); }
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

    void Run(std::function<void()> work, std::function<void()> complete) {
        if (pending) return;
        auto* player = RE::PlayerCharacter::GetSingleton();
        bool equipment = false;
        if (player) for (const auto& [item, data] : player->GetInventory([](RE::TESBoundObject& item) {
            return item.As<RE::TESObjectARMO>() || item.As<RE::TESObjectWEAP>();
        })) {
            if (item && data.first > 0) { equipment = true; break; }
        }
        auto request = std::make_shared<Request>();
        request->work = std::move(work); request->complete = std::move(complete);
        pending = request;
        if (!equipment) { Work(request, {}); Finish(request); }
        else Poll(request);
    }

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
