#include "PlayerEquipment.h"
#include "Settings.h"
#include "TransferFeedback.h"
#include <cmath>
#include <atomic>
#include <chrono>
#include <map>
#include <mutex>

namespace PlayerEquipment {
    namespace {
        std::mutex equipmentLock;
        std::unordered_map<RE::FormID, std::uint64_t> equipmentGenerations;
        std::uint64_t Generation(RE::TESBoundObject* item) {
            std::lock_guard guard(equipmentLock);
            const auto found = equipmentGenerations.find(item->GetFormID());
            return found == equipmentGenerations.end() ? 0 : found->second;
        }
        struct EquipEvents final : RE::BSTEventSink<RE::TESEquipEvent> {
            RE::BSEventNotifyControl ProcessEvent(const RE::TESEquipEvent* event, RE::BSTEventSource<RE::TESEquipEvent>*) override {
                if (event && event->actor.get() == RE::PlayerCharacter::GetSingleton()) {
                    std::lock_guard guard(equipmentLock);
                    ++equipmentGenerations[event->baseObject];
                }
                return RE::BSEventNotifyControl::kContinue;
            }
        } equipEvents;
        bool equipEventsRegistered{};
        std::optional<std::unordered_set<RE::ExtraDataList*>> ReadRows(
            const std::vector<RE::ItemList::Item*>& rows, RE::RefHandle owner, const std::vector<StackIdentity>& stacks) {
            std::unordered_set<RE::ExtraDataList*> seen, protectedStacks;
            std::int64_t represented{}, expected{};
            int bare{};
            for (const auto& stack : stacks) {
                expected += stack.count;
                if (!stack.extra) bare = stack.count;
            }
            std::unordered_map<RE::ExtraDataList*, const StackIdentity*> pointers;
            std::map<std::pair<std::uint32_t, std::uint16_t>, std::vector<const StackIdentity*>> unique;
            for (const auto& stack : stacks) {
                if (stack.extra) pointers.emplace(stack.extra, &stack);
                if (stack.unique) unique[*stack.unique].push_back(&stack);
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
                    if (const auto found = pointers.find(extra); found != pointers.end()) match = found->second;
                    if (auto* id = extra->GetByType<RE::ExtraUniqueID>()) {
                        if (const auto found = unique.find({id->baseID, id->uniqueID}); found != unique.end()) {
                            if (found->second.size() != 1 || (match && match != found->second.front())) return std::nullopt;
                            match = found->second.front();
                        }
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
        enum class Phase { Capturing, Waiting, Opening, Reading, Reconciling, Closing, Validating };
        constexpr auto inspectionBudget = std::chrono::seconds(1);
        using Counts = decltype(std::declval<RE::PlayerCharacter*>()->GetInventoryCounts());
        struct Rows {
            std::unordered_map<RE::ExtraDataList*, std::size_t> pointers;
            std::map<std::pair<std::uint32_t, std::uint16_t>, std::vector<std::size_t>> unique;
            std::unordered_set<RE::ExtraDataList*> seen, equipped;
            std::int64_t total{}, represented{};
            int bare{}, usedBare{};
            bool valid{true};
        };
        struct Request {
            std::function<void()> work, complete;
            std::atomic<bool> cancelled{};
            Phase phase{Phase::Capturing};
            Clock::time_point deadline{Clock::now() + inspectionBudget};
            Clock::time_point refreshAt{};
            RE::IMenu* owned{};
            Snapshot snapshot;
            std::unordered_set<RE::TESBoundObject*> expectedEquipped;
            RE::RefHandle owner{};
            Clock::time_point retry{};
            bool worked{};
            bool refreshRequested{};
            std::function<bool(RE::TESBoundObject*)> eligible;
            std::optional<Counts> inventory;
            Counts::const_iterator next;
            InventoryStacks::ReadCursor physical;
            std::vector<StackIdentity> captured;
            bool movable{};
            std::uint64_t generation{};
            Rows building;
            std::unordered_map<RE::TESBoundObject*, Rows> rows;
            Snapshot read, validated;
            Snapshot::const_iterator reconcile;
            std::size_t rowCursor{}, extraCursor{}, stackCount{};
            RE::TESBoundObject* rowItem{};
            std::int64_t rowExplicit{};
            int rowCount{};
            bool rowWorn{}, rowValid{}, firstPass{true};
            Clock::time_point readBegan{};
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

        Snapshot Capture(RE::PlayerCharacter* player, InventoryStacks::Select select = {}, RE::TESBoundObject* only = nullptr) {
            std::unordered_map<RE::TESBoundObject*, std::vector<InventoryStacks::Stack>> items;
            for (const auto& stack : InventoryStacks::Read(player, std::move(select), only, false, [](auto& item) {
                return item.template As<RE::TESObjectARMO>() || item.template As<RE::TESObjectWEAP>();
            })) items[stack.item].push_back(stack);
            Snapshot result;
            for (const auto& [item, stacks] : items)
                result.emplace(item, ItemEquipment{{}, Identities(stacks), Generation(item)});
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
                if (rows) result.emplace(item, ItemEquipment{std::move(*rows), equipment.stacks, equipment.generation});
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
        void CaptureStep(const std::shared_ptr<Request>& request);
        void ValidateStep(const std::shared_ptr<Request>& request);
        void ReconcileStep(const std::shared_ptr<Request>& request);
        void ReadStep(const std::shared_ptr<Request>& request, RE::InventoryMenu* menu);
        void Later(const std::shared_ptr<Request>& request) {
            TransferFeedback::WaitForFrame([request] { Poll(request); }, [request] { if (Active(request)) Reset(); });
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

        void CaptureStep(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            auto* player = RE::PlayerCharacter::GetSingleton();
            if (!player) { Work(request, {}); Finish(request); return; }
            if (!request->inventory) {
                request->inventory = player->GetInventoryCounts([](auto& item) {
                    return item.template As<RE::TESObjectARMO>() || item.template As<RE::TESObjectWEAP>();
                });
                request->next = request->inventory->cbegin();
            }
            const auto deadline = Clock::now() + std::chrono::milliseconds(4);
            for (int n = 0; request->next != request->inventory->cend() && n < 16; ++n) {
                auto* item = request->next->first;
                if (!item || request->next->second <= 0) { ++request->next; continue; }
                if (request->physical.total < 0) request->generation = Generation(item);
                const bool done = InventoryStacks::ReadPart(player, item, request->physical, [&](auto& entry, auto* extra, int count) {
                    if (entry.IsQuestObject() || Settings::GetSingleton()->IsIgnored(item) ||
                        HasCategory(ClassifyItem(item), ItemCategory::Ignore) || (request->eligible && !request->eligible(item))) return;
                    auto identity = Identities({{player, item, extra, count}}).front();
                    if (!identity.worn && !InventoryStacks::IsFavorited(entry, extra)) request->movable = true;
                    const auto index = request->captured.size();
                    if (extra) request->building.pointers.emplace(extra, index);
                    else request->building.bare = count;
                    if (identity.unique) request->building.unique[*identity.unique].push_back(index);
                    request->building.total += count;
                    request->captured.push_back(identity);
                });
                if (done) {
                    if (request->physical.valid && request->movable && request->generation == Generation(item)) {
                        const auto* command = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
                        const auto equipped = command ? command->conditionFunction : nullptr;
                        const bool single = request->captured.size() == 1 && request->captured.front().count == 1;
                        double worn{};
                        const bool formEquipped = (!single || request->snapshot.empty()) && equipped &&
                            equipped(player, item, nullptr, worn) && worn != 0.0;
                        if (!single || !formEquipped) {
                            if (formEquipped) request->expectedEquipped.insert(item);
                            request->stackCount += request->captured.size();
                            request->snapshot.emplace(item, ItemEquipment{{}, std::move(request->captured), request->generation});
                            request->rows.emplace(item, std::move(request->building));
                        }
                    }
                    request->physical = {}; request->captured.clear(); request->building = {}; request->movable = false;
                    ++request->next;
                }
                if (Clock::now() >= deadline) break;
            }
            if (request->next != request->inventory->cend()) { Later(request); return; }
            request->inventory.reset();
            if (request->snapshot.empty()) { Work(request, {}); Finish(request); return; }
            request->owner = player->GetHandle().native_handle();
            request->phase = Phase::Waiting;
            request->deadline = Clock::now() + inspectionBudget;
            Poll(request);
        }

        void ValidateStep(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            auto* player = RE::PlayerCharacter::GetSingleton();
            const auto deadline = Clock::now() + std::chrono::milliseconds(4);
            for (int n = 0; request->reconcile != request->snapshot.cend() && n < 16; ++n) {
                const auto& [item, equipment] = *request->reconcile;
                const bool done = InventoryStacks::ReadPart(player, item, request->physical, [&](auto&, auto* extra, int count) {
                    request->captured.push_back(Identities({{player, item, extra, count}}).front());
                });
                if (done) {
                    if (request->physical.valid && request->captured == equipment.stacks && equipment.generation == Generation(item))
                        request->validated.emplace(item, equipment);
                    request->physical = {}; request->captured.clear(); ++request->reconcile;
                }
                if (Clock::now() >= deadline) break;
            }
            if (request->reconcile != request->snapshot.cend()) { Later(request); return; }
            Work(request, request->validated); Finish(request);
        }

        void ReadStep(const std::shared_ptr<Request>& request, RE::InventoryMenu* menu) {
            auto* list = menu->GetRuntimeData().itemList;
            const auto deadline = Clock::now() + std::chrono::milliseconds(4);
            int processed{};
            while (request->rowCursor < list->items.size() && processed < 16 && Clock::now() < deadline) {
                auto* row = list->items[request->rowCursor];
                auto* entry = row ? row->data.objDesc : nullptr;
                if (!entry || !request->rows.contains(entry->object)) { ++request->rowCursor; ++processed; continue; }
                auto& result = request->rows.at(entry->object);
                const auto& physical = request->snapshot.at(entry->object);
                RE::GFxValue state, equipped;
                const bool hasState = row->obj.IsObject() && row->obj.GetMember("equipState", &state);
                const bool hasEquipped = row->obj.IsObject() && row->obj.GetMember("isEquipped", &equipped);
                const bool valid = row->data.owner == request->owner && entry->countDelta > 0 &&
                    (hasState || hasEquipped) && (!hasState || (state.IsNumber() && std::isfinite(state.GetNumber()) && state.GetNumber() >= 0)) &&
                    (!hasEquipped || equipped.IsBool());
                const bool worn = valid && ((hasState && state.GetNumber() > 0) || (hasEquipped && equipped.GetBool()));
                if (!request->rowItem) {
                    request->rowItem = entry->object; request->rowCount = entry->countDelta;
                    request->rowExplicit = 0; request->extraCursor = 0;
                    request->rowValid = valid;
                    request->rowWorn = worn;
                    ++processed;
                }
                if (request->rowItem != entry->object || request->rowCount != entry->countDelta || !valid || request->rowWorn != worn)
                    request->rowValid = false;
                bool remaining = false;
                std::size_t index{};
                if (request->rowValid && entry->extraLists) for (auto* extra : *entry->extraLists) {
                    if (index++ < request->extraCursor) continue;
                    if (processed >= 16 || Clock::now() >= deadline) { remaining = true; break; }
                    request->extraCursor = index; ++processed;
                    if (!extra) continue;
                    std::optional<std::size_t> match;
                    if (const auto found = result.pointers.find(extra); found != result.pointers.end()) match = found->second;
                    if (const auto* id = extra->GetByType<RE::ExtraUniqueID>()) {
                        if (const auto found = result.unique.find({id->baseID, id->uniqueID}); found != result.unique.end()) {
                            if (found->second.size() != 1 || (match && *match != found->second.front())) request->rowValid = false;
                            else match = found->second.front();
                        }
                    }
                    if (!request->rowValid || !match) { request->rowValid = false; break; }
                    const auto& identity = physical.stacks[*match];
                    if (!result.seen.insert(identity.extra).second || extra->GetCount() != identity.count) { request->rowValid = false; break; }
                    request->rowExplicit += identity.count;
                    if (request->rowWorn) result.equipped.insert(identity.extra);
                }
                if (remaining) break;
                const auto bare = request->rowCount - request->rowExplicit;
                if (!request->rowValid || bare < 0 || bare > result.bare - result.usedBare) result.valid = false;
                else {
                    result.usedBare += static_cast<int>(bare);
                    result.represented += request->rowCount;
                    if (bare && request->rowWorn) result.equipped.insert(nullptr);
                }
                request->rowItem = nullptr; ++request->rowCursor;
            }
            const bool done = request->rowCursor >= list->items.size();
            SKSE::GetTaskInterface()->AddTask([request, done] {
                if (!Active(request) || request->phase != Phase::Reading) return;
                if (done) { request->phase = Phase::Reconciling; request->reconcile = request->snapshot.cbegin(); }
                else request->phase = Phase::Opening;
                Later(request);
            });
        }

        void ReconcileStep(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            auto* ui = RE::UI::GetSingleton();
            auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
            if (!menu || menu.get() != request->owned || !ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME)) { Finish(request); return; }
            const auto deadline = Clock::now() + std::chrono::milliseconds(4);
            for (int n = 0; request->reconcile != request->snapshot.cend() && n < 16; ++n) {
                const auto& [item, equipment] = *request->reconcile++;
                auto& rows = request->rows.at(item);
                if (rows.valid && rows.represented == rows.total && rows.usedBare == rows.bare && rows.seen.size() == rows.pointers.size())
                    request->read.insert_or_assign(item, ItemEquipment{rows.equipped, equipment.stacks, equipment.generation});
                if (request->expectedEquipped.contains(item)) {
                    const auto found = request->read.find(item);
                    if (found != request->read.end() && found->second.equipped.empty()) request->read.erase(found);
                }
                rows.seen.clear(); rows.equipped.clear(); rows.represented = 0; rows.usedBare = 0; rows.valid = true;
                if (Clock::now() >= deadline) break;
            }
            if (request->reconcile != request->snapshot.cend()) { Later(request); return; }
            if (request->firstPass) {
                if (Clock::now() - request->readBegan > std::chrono::milliseconds(100)) request->deadline = Clock::now() + inspectionBudget;
                request->firstPass = false;
            }
            if (request->read.size() != request->snapshot.size() && Clock::now() < request->deadline) {
                const bool ready = menu->uiMovie && skyrim_cast<RE::InventoryMenu*>(menu.get())->GetRuntimeData().itemList;
                if (ready && !request->refreshRequested && Clock::now() >= request->refreshAt) {
                    request->refreshRequested = true;
                    if (auto* player = RE::PlayerCharacter::GetSingleton()) {
                        auto* data = new RE::InventoryUpdateData{};
                        data->inventoryRef = player->GetHandle().native_handle();
                        RE::UIMessageQueue::GetSingleton()->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kInventoryUpdate, data);
                    }
                }
                request->read.clear(); request->rowCursor = 0; request->rowItem = nullptr;
                request->phase = Phase::Opening; Later(request); return;
            }
            request->snapshot = std::move(request->read);
            Close(request);
        }

        void Poll(const std::shared_ptr<Request>& request) {
            if (!Active(request)) return;
            if (request->phase == Phase::Capturing) { CaptureStep(request); return; }
            if (request->phase == Phase::Validating) { ValidateStep(request); return; }
            if (request->phase == Phase::Reconciling) { ReconcileStep(request); return; }
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
                if (!request->owned) request->readBegan = Clock::now();
                request->owned = menu.get();
                request->phase = Phase::Reading;
                SKSE::GetTaskInterface()->AddUITask([request] {
                    if (request->cancelled) return;
                    auto* ui = RE::UI::GetSingleton();
                    auto menu = ui ? ui->GetMenu(RE::InventoryMenu::MENU_NAME) : RE::GPtr<RE::IMenu>{};
                    Snapshot snapshot;
                    if (menu && menu.get() == request->owned && ui->IsMenuOpen(RE::InventoryMenu::MENU_NAME)) {
                        if (menu->uiMovie) menu->uiMovie->SetVisible(false);
                        auto* inventory = skyrim_cast<RE::InventoryMenu*>(menu.get());
                        auto* list = inventory->GetRuntimeData().itemList;
                        const bool ready = menu->uiMovie && list;
                        if (ready && request->stackCount <= 16 && list->items.size() <= 16) try {
                            snapshot = Read(inventory, request->snapshot, request->owner);
                        } catch (const std::exception&) { logger::error("Could not read equipment rows for Quick Transfer"); }
                        else if (ready) {
                            ReadStep(request, inventory);
                            return;
                        }
                        request->read = std::move(snapshot);
                        request->reconcile = request->snapshot.cbegin();
                        SKSE::GetTaskInterface()->AddTask([request] {
                            if (Active(request) && request->phase == Phase::Reading) { request->phase = Phase::Reconciling; ReconcileStep(request); }
                        });
                        return;
                    }
                    SKSE::GetTaskInterface()->AddTask([request] { Finish(request); });
                });
                return;
            } else if (request->phase == Phase::Closing) {
                if (!open) {
                    menu = nullptr;
                    if (!ui->IsItemMenuOpen()) {
                        request->phase = Phase::Validating;
                        request->reconcile = request->snapshot.cbegin();
                        ValidateStep(request); return;
                    }
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
            if (found->second.generation != Generation(item)) { snapshot.erase(found); return false; }
            const auto physical = Capture(player, {}, item);
            const auto fresh = physical.find(item);
            if (fresh == physical.end() || found->second.stacks != fresh->second.stacks) {
                snapshot.erase(found);
                return false;
            }
        }
        struct Restore { const Snapshot* previous{current}; ~Restore() { current = previous; } } restore;
        current = &snapshot;
        const bool changed = work();
        if (equipment && changed) {
            const auto physical = Capture(player, {}, item);
            const auto currentItem = physical.find(item);
            const auto fresh = currentItem == physical.end() ? std::vector<StackIdentity>{} : currentItem->second.stacks;
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
        if (!equipEventsRegistered) if (auto* source = RE::ScriptEventSourceHolder::GetSingleton()) {
            source->AddEventSink<RE::TESEquipEvent>(&equipEvents);
            equipEventsRegistered = true;
        }
        auto* player = RE::PlayerCharacter::GetSingleton();
        auto request = std::make_shared<Request>();
        request->work = std::move(work); request->complete = std::move(complete);
        request->eligible = std::move(eligible);
        pending = request;
        if (!player) { Work(request, {}); Finish(request); return; }
        CaptureStep(request);
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
        if ((!request->owned && request->phase == Phase::Opening) ||
            (request->owned && menu && menu.get() == request->owned))
            if (auto* queue = RE::UIMessageQueue::GetSingleton())
                queue->AddMessage(RE::InventoryMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kHide, nullptr);
    }
}
