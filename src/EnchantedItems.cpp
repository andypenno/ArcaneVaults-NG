#include "EnchantedItems.h"
#include "InventoryStacks.h"
#include "Utility.h"
#include <atomic>
#include <unordered_set>

namespace {
    RE::BGSKeyword* originKeyword{};
    std::atomic<std::uint64_t> generation{};
    std::atomic<bool> loanActive{};
    std::atomic<bool> cleanupQueued{};
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
            if (event && !loanActive && archiveID && event->oldContainer == archiveID && event->newContainer == 0x14 && event->itemCount > 0) {
                if (cleanupQueued.exchange(true)) return RE::BSEventNotifyControl::kContinue;
                const auto session = generation.load();
                SKSE::GetTaskInterface()->AddTask([session] {
                    if (session == generation) {
                        cleanupQueued = false;
                        InventoryStacks::ClearOrigins(RE::PlayerCharacter::GetSingleton(), originKeyword);
                    }
                });
            }
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
        if (loanActive) return false;
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
        if (!Gather()) return;
        ++generation;
        cleanupQueued = false;
        loanActive = true;
        auto* archive = Archive();
        auto* player = RE::PlayerCharacter::GetSingleton();
        for (const auto& [item, count] : archive->GetInventoryCounts()) {
            if (!item || count <= 0) continue;
            for (;;) {
                const auto stacks = InventoryStacks::Read(archive, {}, item, true);
                if (stacks.empty() && InventoryStacks::Count(archive, item) == 0) break;
                if (stacks.empty() || !InventoryStacks::Move(stacks.front(), player)) {
                    EndLoan();
                    Recover();
                    return;
                }
            }
        }
    }

    void EndLoan() {
        if (!loanActive.exchange(false)) return;
        ++generation;
        cleanupQueued = false;
        auto* player = RE::PlayerCharacter::GetSingleton();
        const auto parents = Parents();
        const auto* command = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
        const auto equipped = command ? command->conditionFunction : nullptr;
        for (const auto& [item, count] : player->GetInventoryCounts()) {
            if (!item || count <= 0) continue;
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
                    InventoryStacks::ClearOrigins(player, originKeyword);
                    return;
                }
            }
            clearDestinations();
        }
        InventoryStacks::ClearOrigins(player, originKeyword);
    }
}
