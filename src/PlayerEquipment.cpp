#include "PlayerEquipment.h"
#include <cmath>
#include <atomic>
#include <chrono>
#include <thread>

namespace PlayerEquipment {
    namespace {
        std::optional<std::unordered_set<RE::ExtraDataList*>> ReadRows(
            RE::ItemList* list, RE::RefHandle owner, RE::TESBoundObject* item, const std::vector<InventoryStacks::Stack>& stacks) {
            std::unordered_set<RE::ExtraDataList*> seen, protectedStacks;
            std::int64_t represented{}, expected{};
            int bare{};
            for (const auto& stack : stacks) {
                expected += stack.count;
                if (!stack.extra) bare = stack.count;
            }
            for (auto* row : list->items) {
                auto* entry = row ? row->data.objDesc : nullptr;
                if (!entry || entry->object != item) continue;
                if (row->data.owner != owner || entry->countDelta <= 0) return std::nullopt;
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
        struct Request {
            std::function<void()> work, complete;
            std::atomic<bool> cancelled{};
            Phase phase{Phase::Waiting};
            Clock::time_point deadline{Clock::now() + std::chrono::seconds(5)};
            RE::IMenu* owned{};
            bool worked{};
        };
        std::shared_ptr<Request> pending;
        thread_local const Snapshot* current{};

        Snapshot Read(RE::InventoryMenu* menu, RE::PlayerCharacter* player) {
            if (!menu || !player || !menu->uiMovie || !menu->GetRuntimeData().itemList) return {};
            std::unordered_map<RE::TESBoundObject*, std::vector<InventoryStacks::Stack>> items;
            for (const auto& stack : InventoryStacks::Read(player)) items[stack.item].push_back(stack);
            Snapshot result;
            for (const auto& [item, stacks] : items) {
                const auto rows = ReadRows(menu->GetRuntimeData().itemList, player->GetHandle().native_handle(), item, stacks);
                if (rows) result.emplace(item, *rows);
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
            current = &snapshot;
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
            request->deadline = Clock::now() + std::chrono::seconds(5);
            if (auto* queue = RE::UIMessageQueue::GetSingleton())
                queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kHide, nullptr);
            Later(request);
        }

        void Poll(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            auto* ui = RE::UI::GetSingleton();
            auto* queue = RE::UIMessageQueue::GetSingleton();
            if (!ui || !queue) { Work(request, {}); Finish(request); return; }
            const auto expired = Clock::now() >= request->deadline;
            if (request->phase == Phase::Waiting) {
                if (ui->IsMenuOpen(RE::MessageBoxMenu::MENU_NAME) && !expired) { Later(request); return; }
                if (expired || ui->IsItemMenuOpen()) {
                    Work(request, {}); Finish(request); return;
                }
                request->phase = Phase::Opening;
                request->deadline = Clock::now() + std::chrono::seconds(5);
                queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kShow, nullptr);
                Later(request);
                return;
            }
            auto menu = ui->GetMenu(RE::InventoryMenu::MENU_NAME);
            const bool open = menu && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME);
            if (request->phase == Phase::Opening && open) {
                request->owned = menu.get();
                request->phase = Phase::Reading;
                SKSE::GetTaskInterface()->AddUITask([request] {
                    if (request->cancelled) return;
                    auto* ui = RE::UI::GetSingleton();
                    auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                    Snapshot snapshot;
                    if (menu && menu.get() == request->owned && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME)) {
                        if (menu->uiMovie) menu->uiMovie->SetVisible(false);
                        try { snapshot = Read(skyrim_cast<RE::InventoryMenu*>(menu.get()), RE::PlayerCharacter::GetSingleton()); }
                        catch (const std::exception&) { logger::error("Could not read equipment rows for Quick Transfer"); }
                    }
                    SKSE::GetTaskInterface()->AddTask([request, snapshot = std::move(snapshot)] {
                        if (!Active(request) || request->phase != Phase::Reading) return;
                        auto* ui = RE::UI::GetSingleton();
                        auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                        const bool owned = menu && menu.get() == request->owned && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME);
                        Work(request, owned ? snapshot : Snapshot{});
                        if (!Active(request)) return;
                        if (owned) Close(request); else Finish(request);
                    });
                });
            } else if (request->phase == Phase::Closing) {
                if (!open || (request->owned && menu.get() != request->owned)) { menu = nullptr; Finish(request); return; }
                if (expired) {
                    SKSE::GetTaskInterface()->AddUITask([request] {
                        auto* ui = RE::UI::GetSingleton();
                        auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                        if (!request->cancelled && menu && menu.get() == request->owned && menu->uiMovie)
                            menu->uiMovie->SetVisible(true);
                    });
                    request->deadline = Clock::now() + std::chrono::seconds(5);
                }
            } else if (expired) {
                Work(request, {});
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
        if (player) for (const auto& [item, data] : player->GetInventory())
            if (item && data.first > 0 && (item->As<RE::TESObjectARMO>() || item->As<RE::TESObjectWEAP>())) equipment = true;
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
