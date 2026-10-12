#include "Soulgems.h"
#include "Utility.h"
#include "Settings.h"
#include <array>
#include <unordered_set>

namespace {
    struct Stack {
        RE::ExtraDataList* extra;
        int count;
        bool filled;
    };

    using Counts = std::unordered_map<RE::FormID, std::array<int, 2>>;
    Counts carriedBefore;
    std::unordered_set<RE::FormID> loanForms;
    std::int64_t remainingLoan{};

    bool Protected(RE::TESSoulGem* gem, const RE::InventoryEntryData& entry) {
        if (entry.IsQuestObject() || entry.IsFavorited() || entry.IsWorn()) return true;
        std::unordered_set<RE::TESSoulGem*> visited;
        while (gem && visited.insert(gem).second) {
            if (gem->GetFormID() == 0x63B27 || gem->GetFormID() == 0x63B29) return true;
            gem = gem->linkedSoulGem;
        }
        return false;
    }

    bool ReadStacks(RE::TESSoulGem* gem, int total, const RE::InventoryEntryData& entry,
        std::vector<Stack>& stacks) {
        stacks.clear();
        if (total <= 0) return false;
        std::int64_t explicitCount{};
        std::unordered_set<RE::ExtraDataList*> visited;
        if (entry.extraLists) {
            for (auto* extra : *entry.extraLists) {
                if (!extra) continue;
                if (!visited.insert(extra).second) return false;
                const int count = extra->GetCount();
                const auto* soul = extra->GetByType<RE::ExtraSoul>();
                const auto level = soul ? soul->GetContainedSoul() : gem->GetContainedSoul();
                if (count <= 0 || static_cast<unsigned>(level) > static_cast<unsigned>(RE::SOUL_LEVEL::kGrand))
                    return false;
                explicitCount += count;
                if (explicitCount > total) return false;
                stacks.push_back({extra, count, level != RE::SOUL_LEVEL::kNone});
            }
        }
        const auto level = gem->GetContainedSoul();
        if (static_cast<unsigned>(level) > static_cast<unsigned>(RE::SOUL_LEVEL::kGrand)) return false;
        if (explicitCount < total)
            stacks.push_back({nullptr, static_cast<int>(total - explicitCount), level != RE::SOUL_LEVEL::kNone});
        return true;
    }

    void Move(RE::TESObjectREFR* source, RE::TESObjectREFR* target, RE::TESSoulGem* gem, const Stack& stack, int count) {
        if (count > 0)
            source->RemoveItem(gem, count, RE::ITEM_REMOVE_REASON::kStoreInContainer, stack.extra, target);
    }

    template<class Select>
    void MoveAll(RE::TESObjectREFR* source, RE::TESObjectREFR* target, Select select) {
        if (!source || !target || source == target) return;
        const auto inventory = source->GetInventory();
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->template As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || Protected(gem, *data.second) || !select(gem)) continue;
            if (!ReadStacks(gem, data.first, *data.second, stacks)) continue;
            // Move explicit stacks before a null extra-list can select them.
            for (const auto& stack : stacks) Move(source, target, gem, stack, stack.count);
        }
    }

    Counts CountGems(RE::TESObjectREFR* source) {
        Counts counts;
        if (!source) return counts;
        std::vector<Stack> stacks;
        const auto inventory = source->GetInventory();
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || !ReadStacks(gem, data.first, *data.second, stacks)) continue;
            for (const auto& stack : stacks) counts[gem->GetFormID()][stack.filled] += stack.count;
        }
        return counts;
    }
}

namespace Soulgems {
    void Consolidate() {
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        if (!bank) return;
        for (auto kind : {Container::FilledSoulgems, Container::EmptySoulgems}) {
            auto* archive = utility->GetContainer(kind);
            if (archive && archive != bank) {
                if (auto* changes = archive->GetInventoryChanges())
                    changes->RemoveAllItems(archive, bank, false, false, false);
            }
        }
    }

    void Recover() {
        Consolidate();
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        for (auto kind : {Container::Smithing, Container::Crafting, Container::Smelting,
            Container::Construction, Container::Tanning, Container::Gemstone, Container::Sort})
            MoveAll(utility->GetContainer(kind), bank, [kind](auto* gem) {
                auto* settings = Settings::GetSingleton();
                return kind != Container::Sort || !settings->GSC_ReturnIgnoredItems || !settings->IsIgnored(gem);
            });
    }

    void Split() {
        Consolidate();
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        auto* filled = utility->GetContainer(Container::FilledSoulgems);
        auto* empty = utility->GetContainer(Container::EmptySoulgems);
        if (!bank || !filled || !empty) return;
        const auto inventory = bank->GetInventory();
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || Protected(gem, *data.second)) continue;
            if (!ReadStacks(gem, data.first, *data.second, stacks)) continue;
            for (const auto& stack : stacks)
                Move(bank, stack.filled ? filled : empty, gem, stack, stack.count);
        }
    }

    void Deposit(int a_keepEmpty, bool a_respectIgnores) {
        if (a_keepEmpty < 0) return;
        Recover();
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        auto* buffer = utility->GetContainer(Container::EmptySoulgems);
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!bank || !buffer || !player) return;
        const auto inventory = player->GetInventory();
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || Protected(gem, *data.second)) continue;
            if (a_respectIgnores && Settings::GetSingleton()->IsIgnored(gem)) continue;
            if (!ReadStacks(gem, data.first, *data.second, stacks)) continue;
            int keep = a_keepEmpty;
            for (const auto& stack : stacks) {
                const int retained = stack.filled ? 0 : (std::min)(keep, stack.count);
                keep -= retained;
                Move(player, bank, gem, stack, stack.count - retained);
                // Park retained extras so bare filled items cannot remove them.
                if (retained && stack.extra && gem->GetContainedSoul() != RE::SOUL_LEVEL::kNone)
                    Move(player, buffer, gem, stack, retained);
            }
            MoveAll(buffer, player, [](auto*) { return true; });
        }
    }

    void TakeEmpty(std::optional<int> a_target) {
        if (a_target && *a_target <= 0) return;
        Recover();
        Split();
        auto* source = Utility::GetSingleton()->GetContainer(Container::EmptySoulgems);
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (source && player) {
            if (!a_target) {
                MoveAll(source, player, [](auto*) { return true; });
            } else {
                const auto carried = CountGems(player);
                const auto playerInventory = player->GetInventory();
                const auto inventory = source->GetInventory();
                std::vector<Stack> stacks;
                for (const auto& [item, data] : inventory) {
                    auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
                    if (!gem || !data.second || Protected(gem, *data.second)) continue;
                    const auto id = gem->GetFormID();
                    const auto existing = playerInventory.find(item);
                    // Unparseable carried stacks must not count as zero toward the reserve.
                    if (existing != playerInventory.end() && existing->second.first > 0 && !carried.contains(id)) continue;
                    int take = *a_target - (carried.contains(id) ? carried.at(id)[0] : 0);
                    if (take <= 0 || !ReadStacks(gem, data.first, *data.second, stacks)) continue;
                    for (const auto& stack : stacks) {
                        if (stack.filled) continue;
                        const int count = (std::min)(take, stack.count);
                        Move(source, player, gem, stack, count);
                        take -= count;
                    }
                }
            }
        }
        Consolidate();
    }

    void ResetLoan() {
        carriedBefore.clear();
        loanForms.clear();
        remainingLoan = 0;
    }

    void BeginLoan(bool a_smithing) {
        ResetLoan();
        Recover();
        auto* utility = Utility::GetSingleton();
        auto* player = RE::PlayerCharacter::GetSingleton();
        carriedBefore = CountGems(player);
        auto* source = utility->GetContainer(Container::Soulgem);
        if (!a_smithing) {
            Split();
            source = utility->GetContainer(Container::FilledSoulgems);
        }
        MoveAll(source, player, [utility, a_smithing](auto* gem) {
            return !a_smithing || utility->isSmithing(gem->GetFormID());
        });
        const auto after = CountGems(player);
        for (const auto& [id, counts] : after) {
            const auto before = carriedBefore.contains(id) ? carriedBefore.at(id) : std::array<int, 2>{};
            const auto borrowed = (std::max)(0, counts[0] - before[0]) + (std::max)(0, counts[1] - before[1]);
            if (!borrowed) continue;
            remainingLoan += borrowed;
            loanForms.insert(id);
            if (auto* gem = RE::TESForm::LookupByID<RE::TESSoulGem>(id); gem && gem->linkedSoulGem)
                loanForms.insert(gem->linkedSoulGem->GetFormID());
        }
        Consolidate();
    }

    void EndLoan() {
        auto* player = RE::PlayerCharacter::GetSingleton();
        auto* bank = Utility::GetSingleton()->GetContainer(Container::Soulgem);
        if (!player || !bank) { ResetLoan(); return; }
        const auto inventory = player->GetInventory();
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !loanForms.contains(gem->GetFormID()) || !data.second || Protected(gem, *data.second)) continue;
            if (!ReadStacks(gem, data.first, *data.second, stacks)) continue;
            auto keep = carriedBefore[gem->GetFormID()];
            std::array<bool, 2> retainedExtras{};
            // Ambiguous bare stacks stay with the player until explicit Quick Transfer.
            for (const auto& stack : stacks) {
                const int retained = (std::min)(keep[stack.filled], stack.count);
                keep[stack.filled] -= retained;
                if (stack.extra && retained) retainedExtras[stack.filled] = true;
                if (!stack.extra && retainedExtras[!stack.filled]) continue;
                const int count = static_cast<int>((std::min)(remainingLoan,
                    static_cast<std::int64_t>(stack.count - retained)));
                Move(player, bank, gem, stack, count);
                remainingLoan -= count;
            }
        }
        ResetLoan();
    }
}
