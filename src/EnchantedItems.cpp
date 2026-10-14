#include "EnchantedItems.h"
#include "InventoryStacks.h"
#include "Utility.h"
#include <atomic>
#include <limits>
#include <mutex>
#include <unordered_map>
#include <unordered_set>

namespace {
    RE::BGSKeyword* originKeyword{};
    std::atomic<std::uint64_t> generation{};
    std::atomic<bool> loanActive{};
    std::atomic<bool> cleanupQueued{};
    std::atomic<bool> ending{};
    bool dispatching{};
    struct LoanItem { int expected{}, received{}, notified{}; };
    std::unordered_map<RE::FormID, LoanItem> loanItems;
    std::mutex receiptMutex;
    std::unordered_map<RE::FormID, std::int64_t> receipts;
    RE::FormID archiveID{};

    RE::TESObjectREFR* Archive() {
        return Utility::GetSingleton()->GetContainer(Container::EnchantedItems);
    }

    std::vector<RE::TESObjectREFR*> Parents() {
        auto* utility = Utility::GetSingleton();
        return {utility->GetContainer(Container::Weapon), utility->GetContainer(Container::Armor)};
    }

    class Sink : public RE::BSTEventSink<RE::TESContainerChangedEvent> {
        RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent* event,
            RE::BSTEventSource<RE::TESContainerChangedEvent>*) override {
            if (!event || !archiveID || event->oldContainer != archiveID || event->newContainer != 0x14 || event->itemCount <= 0)
                return RE::BSEventNotifyControl::kContinue;
            const auto session = generation.load();
            {
                std::lock_guard lock(receiptMutex);
                if (session != generation) return RE::BSEventNotifyControl::kContinue;
                receipts[event->baseObj] = (std::min)(static_cast<std::int64_t>((std::numeric_limits<int>::max)()), receipts[event->baseObj] + event->itemCount);
                if (cleanupQueued.exchange(true)) return RE::BSEventNotifyControl::kContinue;
            }
            SKSE::GetTaskInterface()->AddTask([session] {
                if (session != generation) return;
                std::unordered_map<RE::FormID, std::int64_t> arrived;
                {
                    std::lock_guard lock(receiptMutex);
                    arrived.swap(receipts);
                    cleanupQueued = false;
                }
                if (loanActive) {
                    for (const auto& [id, count] : arrived) {
                        const auto found = loanItems.find(id);
                        if (found == loanItems.end()) continue;
                        auto& item = found->second;
                        item.notified = static_cast<int>((std::min)(static_cast<std::int64_t>(item.expected), item.notified + count));
                        item.received = (std::max)(item.received, item.notified);
                    }
                    if (ending) EnchantedItems::EndLoan();
                } else InventoryStacks::ClearOrigins(RE::PlayerCharacter::GetSingleton(), originKeyword);
            });
            return RE::BSEventNotifyControl::kContinue;
        }
    };
}

namespace EnchantedItems {
    void Init() {
        originKeyword = RE::TESDataHandler::GetSingleton()->LookupForm<RE::BGSKeyword>(0xDED, "ArcaneVaults-LinkedStorage.esp");
        archiveID = Archive() ? Archive()->GetFormID() : 0;
        static Sink sink;
        RE::ScriptEventSourceHolder::GetSingleton()->AddEventSink(&sink);
        if (!originKeyword || !archiveID) logger::error("Enchanted Items archive or origin keyword is missing");
    }

    void Reset() {
        ++generation;
        loanActive = false;
        cleanupQueued = false;
        ending = false;
        dispatching = false;
        loanItems.clear();
        std::lock_guard lock(receiptMutex);
        receipts.clear();
    }

    bool Eligible(RE::TESBoundObject* item, const RE::InventoryEntryData& entry, RE::ExtraDataList* extra) {
        if (!item || entry.IsQuestObject()) return false;
        auto* weapon = item->As<RE::TESObjectWEAP>();
        if (!weapon && !item->As<RE::TESObjectARMO>()) return false;
        if (weapon && weapon->GetWeaponType() == RE::WEAPON_TYPE::kStaff) return false;
        auto* defaults = RE::BGSDefaultObjectManager::GetSingleton();
        auto** disallow = defaults ? defaults->GetObject<RE::BGSKeyword>(RE::DefaultObjectID::kKeywordDisallowEnchanting) : nullptr;
        auto* keywords = item->As<RE::BGSKeywordForm>();
        if (!disallow || !*disallow || !keywords || keywords->HasKeyword(*disallow)) return false;
        auto* enchantable = item->As<RE::TESEnchantableForm>();
        auto* enchantment = enchantable ? enchantable->formEnchanting : nullptr;
        if (auto* custom = extra ? extra->GetByType<RE::ExtraEnchantment>() : nullptr) {
            if (!custom->enchantment) return false;
            enchantment = custom->enchantment;
        }
        if (!enchantment) return false;
        std::unordered_set<RE::EnchantmentItem*> visited;
        while (enchantment) {
            if (!visited.insert(enchantment).second || enchantment->HasKeyword(*disallow) ||
                enchantment->GetSpellType() == RE::MagicSystem::SpellType::kStaffEnchantment) return false;
            enchantment = enchantment->data.baseEnchantment;
        }
        return true;
    }

    bool Recover() {
        if (loanActive && !ending) return false;
        auto* archive = Archive();
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!archive || !player || !originKeyword) return false;
        const auto parents = Parents();
        for (const auto& [item, count] : archive->GetInventoryCounts()) {
            if (!item || count <= 0) continue;
            for (;;) {
                // Engine transfers can replace extra lists, so read them again after each move.
                const auto stacks = InventoryStacks::Read(archive, {}, item, true);
                if (stacks.empty()) {
                    if (InventoryStacks::Count(archive, item) > 0) return false;
                    break;
                }
                const auto& stack = stacks.front();
                auto* origin = stack.extra ? stack.extra->GetLinkedRef(originKeyword) : nullptr;
                if (InventoryStacks::HasOrigin(stack.extra, originKeyword) && !origin) return false;
                auto* target = origin ? origin : player;
                if (target != player && std::ranges::find(parents, target) == parents.end()) return false;
                if (!InventoryStacks::Move(stack, target)) return false;
                InventoryStacks::ClearOrigins(target, originKeyword, item);
            }
        }
        InventoryStacks::ClearOrigins(player, originKeyword);
        for (auto* source : parents) InventoryStacks::ClearOrigins(source, originKeyword);
        return true;
    }

    bool Gather() {
        if (loanActive) return false;
        auto* archive = Archive();
        if (!archive || !originKeyword || !Recover()) return false;
        auto* stores = Stores::GetSingleton();
        for (auto child : {Container::Archery, Container::OneHand, Container::TwoHand, Container::Staff})
            stores->AllToStore(child, Container::Weapon);
        for (auto child : {Container::HeavyArmor, Container::LightArmor, Container::Clothing, Container::Jewelry})
            stores->AllToStore(child, Container::Armor);
        for (auto* source : Parents()) {
            if (!source || source == archive) return false;
            for (const auto& [item, count] : source->GetInventoryCounts()) {
                if (!item || count <= 0) continue;
                for (;;) {
                    const auto stacks = InventoryStacks::Read(source, Eligible, item, true);
                    if (stacks.empty()) break;
                    const auto marked = InventoryStacks::MarkOrigin(stacks.front(), originKeyword);
                    if (!marked || !InventoryStacks::Move(*marked, archive)) {
                        Recover();
                        return false;
                    }
                }
            }
        }
        return true;
    }

    void BeginLoan() {
        if (loanActive) EndLoan();
        if (loanActive) return;
        if (!Gather()) return;
        auto* archive = Archive();
        auto* player = RE::PlayerCharacter::GetSingleton();
        const auto inventory = archive->GetInventoryCounts();
        const auto carried = player->GetInventoryCounts([&](RE::TESBoundObject& item) { return inventory.contains(&item); });
        std::unordered_map<RE::TESBoundObject*, std::int64_t> staged;
        for (const auto& stack : InventoryStacks::Read(archive)) staged[stack.item] += stack.count;
        bool hasItems{};
        for (const auto& [item, count] : inventory) {
            if (!item || count <= 0) continue;
            hasItems = true;
            const int held = carried.contains(item) ? (std::max)(0, carried.at(item)) : 0;
            if (staged[item] != count || count > (std::numeric_limits<int>::max)() - held) {
                Recover();
                return;
            }
        }
        if (!hasItems) return;
        auto* changes = archive->GetInventoryChanges();
        if (!changes) { Recover(); return; }
        ++generation;
        cleanupQueued = false;
        ending = false;
        loanItems.clear();
        {
            std::lock_guard lock(receiptMutex);
            receipts.clear();
        }
        for (const auto& [item, count] : inventory)
            if (item && count > 0) loanItems[item->GetFormID()].expected = count;
        loanActive = true;
        dispatching = true;
        const auto session = generation.load();
        for (const auto& [item, count] : inventory) {
            if (!item || count <= 0) continue;
            int remaining = count;
            while (remaining > 0 && session == generation && !ending) {
                const auto stacks = InventoryStacks::Read(archive, {}, item, true);
                if (session != generation) return;
                if (stacks.empty()) { ending = true; break; }
                const int moved = InventoryStacks::Move(stacks.front(), player);
                if (session != generation) return;
                if (!moved) { ending = true; break; }
                remaining -= moved;
            }
            if (session != generation) return;
        }
        dispatching = false;
        const auto remaining = archive->GetInventoryCounts();
        const auto received = player->GetInventoryCounts([&](RE::TESBoundObject& item) { return inventory.contains(&item); });
        for (const auto& [item, count] : inventory) {
            if (!item || count <= 0) continue;
            const int held = carried.contains(item) ? (std::max)(0, carried.at(item)) : 0;
            const int left = remaining.contains(item) ? remaining.at(item) : 0;
            const int after = received.contains(item) ? received.at(item) : 0;
            auto& loan = loanItems.at(item->GetFormID());
            loan.expected = (std::clamp)(count - left, 0, count);
            loan.received = (std::clamp)(after - held, 0, loan.expected);
            if (left != 0) ending = true;
        }
        if (ending) EndLoan();
    }

    bool HasPendingLoan() { return loanActive && ending; }

    void ReturnLoan() {
        auto* player = RE::PlayerCharacter::GetSingleton();
        const auto parents = Parents();
        const auto* command = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
        const auto equipped = command ? command->conditionFunction : nullptr;
        for (const auto& [item, count] : player->GetInventoryCounts()) {
            if (!item || count <= 0 || !loanItems.contains(item->GetFormID())) continue;
            std::unordered_set<RE::TESObjectREFR*> destinations;
            const auto clearDestinations = [&] {
                for (auto* destination : destinations) InventoryStacks::ClearOrigins(destination, originKeyword, item);
            };
            for (;;) {
                const auto stacks = InventoryStacks::Read(player, [&](auto* candidate, auto& entry, auto* extra) {
                    if (!InventoryStacks::HasOrigin(extra, originKeyword) || entry.IsQuestObject() || entry.IsFavorited() || entry.IsWorn()) return false;
                    auto* origin = extra->GetLinkedRef(originKeyword);
                    if (!origin || std::ranges::find(parents, origin) == parents.end()) return false;
                    double worn{};
                    return !equipped || !equipped(player, candidate, nullptr, worn) || worn == 0.0;
                }, item, true);
                if (stacks.empty()) break;
                const auto& stack = stacks.front();
                auto* origin = stack.extra->GetLinkedRef(originKeyword);
                destinations.insert(origin);
                if (!InventoryStacks::Move(stack, origin)) {
                    clearDestinations();
                    return;
                }
            }
            clearDestinations();
        }
    }

    void EndLoan() {
        if (!loanActive) return;
        ending = true;
        if (dispatching) return;
        ReturnLoan();
        Recover();
        for (const auto& [id, item] : loanItems)
            if (item.received < item.expected) return;
        InventoryStacks::ClearOrigins(RE::PlayerCharacter::GetSingleton(), originKeyword);
        Reset();
    }
}
