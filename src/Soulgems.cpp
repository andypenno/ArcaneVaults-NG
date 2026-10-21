#include "Soulgems.h"
#include "InventoryStacks.h"
#include "Utility.h"
#include "Settings.h"
#include "OffloadBatch.h"
#include <array>
#include <unordered_set>

namespace {
    struct Stack {
        RE::ExtraDataList* extra;
        int count;
        bool filled;
        bool favorite{};
        bool guardedBare{};
    };

    using Counts = std::unordered_map<RE::FormID, std::array<int, 2>>;
    Counts carriedBefore;
    std::unordered_set<RE::FormID> loanForms;
    std::int64_t remainingLoan{};

    bool Protected(RE::TESSoulGem* gem, const RE::InventoryEntryData& entry) {
        if (entry.IsQuestObject() || entry.IsWorn()) return true;
        if (entry.IsFavorited()) {
            bool identified = false;
            if (entry.extraLists) for (auto* extra : *entry.extraLists)
                identified |= extra && extra->HasType<RE::ExtraHotkey>();
            if (!identified) return true;
        }
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
                stacks.push_back({extra, count, level != RE::SOUL_LEVEL::kNone, extra->HasType<RE::ExtraHotkey>() || InventoryStacks::HasOrigin(extra, InventoryStacks::FavoriteKeyword())});
            }
        }
        const auto level = gem->GetContainedSoul();
        if (static_cast<unsigned>(level) > static_cast<unsigned>(RE::SOUL_LEVEL::kGrand)) return false;
        if (explicitCount < total)
            stacks.push_back({nullptr, static_cast<int>(total - explicitCount), level != RE::SOUL_LEVEL::kNone, false, std::ranges::any_of(stacks, [](const auto& stack) { return stack.favorite; })});
        return true;
    }

    void Move(RE::TESObjectREFR* source, RE::TESObjectREFR* target, RE::TESSoulGem* gem, const Stack& stack, int count) {
        if (stack.favorite) return;
        if (OffloadBatch::current) {
            if (!OffloadBatch::current->active() || count <= 0) return;
            auto physical = std::optional{InventoryStacks::Stack{source, gem, stack.extra, count}};
            if (!stack.extra && stack.guardedBare) physical = InventoryStacks::Materialize(*physical);
            if (physical && InventoryStacks::Move(*physical, target)) {
                OffloadBatch::current->Moved(true);
                OffloadBatch::current->repeat = true;
            }
            return;
        }
        if (stack.guardedBare) {
            while (count > 0) {
                const auto physical = InventoryStacks::Materialize({source, gem, nullptr, count});
                if (!physical) return;
                const int moved = InventoryStacks::Move(*physical, target);
                if (!moved) return;
                count -= moved;
            }
        } else if (count > 0)
            source->RemoveItem(gem, count, RE::ITEM_REMOVE_REASON::kStoreInContainer, stack.extra, target);
    }

    template<class Select>
    void MoveAll(RE::TESObjectREFR* source, RE::TESObjectREFR* target, Select select) {
        if (!source || !target || source == target) return;
        if (auto* prepared = OffloadBatch::current ? OffloadBatch::current->prepared : nullptr) {
            auto* item = OffloadBatch::current->item;
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !InventoryStacks::Valid(prepared->cursor) || prepared->stacks.empty() ||
                prepared->stacks.front().source != source || prepared->quest || prepared->worn ||
                (prepared->favorite && !prepared->identifiedFavorite) || !select(gem)) return;
            std::unordered_set<RE::TESSoulGem*> visited;
            for (auto* linked = gem; linked && visited.insert(linked).second; linked = linked->linkedSoulGem)
                if (linked->GetFormID() == 0x63B27 || linked->GetFormID() == 0x63B29) return;
            for (std::size_t index = 0; index < prepared->stacks.size(); ++index) {
                const auto& stack = prepared->stacks[index];
                if (!OffloadBatch::current->active() || !InventoryStacks::Valid(prepared->cursor)) return;
                if (stack.extra && (stack.extra->HasType<RE::ExtraHotkey>() || InventoryStacks::HasOrigin(stack.extra, InventoryStacks::FavoriteKeyword()))) continue;
                auto moving = stack;
                if (!moving.extra && prepared->identifiedFavorite) {
                    const auto physical = InventoryStacks::Materialize(moving);
                    if (!physical) return;
                    moving = *physical;
                }
                const int moved = InventoryStacks::MovePrepared(moving, target, *prepared, index);
                if (!moved) return;
                if (OffloadBatch::current->Moved(moved < stack.count || index + 1 < prepared->stacks.size())) return;
                if (moved < stack.count) { OffloadBatch::current->repeat = true; return; }
            }
            return;
        }
        const auto inventory = source->GetInventory([](RE::TESBoundObject& item) { return item.As<RE::TESSoulGem>() && (!OffloadBatch::current || !OffloadBatch::current->item || OffloadBatch::current->item == &item); });
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->template As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || Protected(gem, *data.second) || !select(gem)) continue;
            if (!ReadStacks(gem, data.first, *data.second, stacks)) continue;
            // Move explicit stacks before a null extra-list can select them.
            for (const auto& stack : stacks) {
                Move(source, target, gem, stack, stack.count);
                if (OffloadBatch::current && OffloadBatch::current->repeat) return;
            }
        }
    }

    Counts CountGems(RE::TESObjectREFR* source) {
        Counts counts;
        if (!source) return counts;
        std::vector<Stack> stacks;
        const auto inventory = source->GetInventory([](RE::TESBoundObject& item) { return item.As<RE::TESSoulGem>() != nullptr; });
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || !ReadStacks(gem, data.first, *data.second, stacks)) continue;
            for (const auto& stack : stacks) counts[gem->GetFormID()][stack.filled] += stack.count;
        }
        return counts;
    }
}

namespace Soulgems {
    bool PrepareTransfer(RE::TESObjectREFR* source, RE::TESBoundObject* item, InventoryStacks::Prepared& prepared) {
        auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
        if (!gem) { prepared.cursor.valid = false; return true; }
        if (static_cast<unsigned>(gem->GetContainedSoul()) > static_cast<unsigned>(RE::SOUL_LEVEL::kGrand)) {
            prepared.cursor.valid = false; return true;
        }
        return InventoryStacks::Prepare(source, item, prepared, [&](auto* extra, int, std::size_t) {
            prepared.identifiedFavorite |= extra && InventoryStacks::HasOrigin(extra, InventoryStacks::FavoriteKeyword());
            const auto* soul = extra ? extra->template GetByType<RE::ExtraSoul>() : nullptr;
            const auto level = soul ? soul->GetContainedSoul() : gem->GetContainedSoul();
            prepared.filled.push_back(level != RE::SOUL_LEVEL::kNone);
            return static_cast<unsigned>(level) <= static_cast<unsigned>(RE::SOUL_LEVEL::kGrand);
        });
    }
    bool PrepareDeposit(RE::TESBoundObject* item, InventoryStacks::Prepared& prepared) {
        return PrepareTransfer(RE::PlayerCharacter::GetSingleton(), item, prepared);
    }
    void Consolidate() {
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        if (!bank) return;
        for (auto kind : {Container::FilledSoulgems, Container::EmptySoulgems}) {
            auto* archive = utility->GetContainer(kind);
            if (archive && archive != bank && InventoryStacks::HasItems(archive)) {
                if (auto* changes = archive->GetInventoryChanges())
                    changes->RemoveAllItems(archive, bank, false, false, false);
            }
        }
    }

    void Recover(const std::unordered_set<RE::FormID>& a_sortExcluded) {
        if (!OffloadBatch::current) Consolidate();
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        for (auto kind : {Container::Smithing, Container::Crafting, Container::Smelting,
            Container::Construction, Container::Tanning, Container::Gemstone, Container::Remains, Container::Sort}) {
            MoveAll(utility->GetContainer(kind), bank, [kind, &a_sortExcluded](auto* gem) {
                auto* settings = Settings::GetSingleton();
                return kind != Container::Sort || (!HasCategory(ClassifyItem(gem), ItemCategory::Ignore) && !a_sortExcluded.contains(gem->GetFormID()) &&
                    (!settings->GSC_ReturnIgnoredItems || !settings->IsIgnored(gem)));
            });
            if (OffloadBatch::current && OffloadBatch::current->repeat) return;
        }
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
        if (auto* prepared = OffloadBatch::current ? OffloadBatch::current->prepared : nullptr) {
            auto* item = OffloadBatch::current->item;
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !prepared->complete || !InventoryStacks::Valid(prepared->cursor) || prepared->quest || prepared->worn ||
                (prepared->favorite && !prepared->identifiedFavorite) || HasCategory(ClassifyItem(gem), ItemCategory::Ignore) ||
                (a_respectIgnores && Settings::GetSingleton()->IsIgnored(gem))) return;
            std::unordered_set<RE::TESSoulGem*> visited;
            for (auto* linked = gem; linked && visited.insert(linked).second; linked = linked->linkedSoulGem)
                if (linked->GetFormID() == 0x63B27 || linked->GetFormID() == 0x63B29) return;
            auto* bank = Utility::GetSingleton()->GetContainer(Container::Soulgem);
            int keep = a_keepEmpty;
            bool retainedExtras = false;
            for (std::size_t index = 0; index < prepared->stacks.size(); ++index) {
                if (!OffloadBatch::current->active() || !InventoryStacks::Valid(prepared->cursor)) return;
                auto stack = prepared->stacks[index];
                const int retained = prepared->filled[index] ? 0 : (std::min)(keep, stack.count);
                keep -= retained;
                const bool favorite = stack.extra && (stack.extra->HasType<RE::ExtraHotkey>() ||
                    InventoryStacks::HasOrigin(stack.extra, InventoryStacks::FavoriteKeyword()));
                if (!favorite && stack.count > retained) {
                    stack.count -= retained;
                    if (!stack.extra && (retainedExtras || prepared->identifiedFavorite)) {
                        const auto physical = InventoryStacks::Materialize(stack);
                        if (!physical) return;
                        stack = *physical;
                    }
                    const int moved = InventoryStacks::MovePrepared(stack, bank, *prepared, index);
                    if (!moved) return;
                    if (OffloadBatch::current->Moved(true)) return;
                    if (moved < stack.count) { OffloadBatch::current->repeat = true; return; }
                }
                retainedExtras |= retained && stack.extra;
            }
            return;
        }
        if (!OffloadBatch::current) Recover();
        auto* utility = Utility::GetSingleton();
        auto* bank = utility->GetContainer(Container::Soulgem);
        auto* buffer = utility->GetContainer(Container::EmptySoulgems);
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!bank || !buffer || !player) return;
        const auto inventory = player->GetInventory([](auto& item) {
            return !OffloadBatch::current || OffloadBatch::current->item == &item;
        });
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !data.second || Protected(gem, *data.second)) continue;
            if (HasCategory(ClassifyItem(gem), ItemCategory::Ignore)) continue;
            if (a_respectIgnores && Settings::GetSingleton()->IsIgnored(gem)) continue;
            if (!ReadStacks(gem, data.first, *data.second, stacks)) continue;
            int keep = a_keepEmpty;
            bool retainedExtras = false;
            for (const auto& stack : stacks) {
                const int retained = stack.filled ? 0 : (std::min)(keep, stack.count);
                keep -= retained;
                auto moving = stack;
                if (OffloadBatch::current && !moving.extra && retainedExtras) moving.guardedBare = true;
                Move(player, bank, gem, moving, stack.count - retained);
                if (OffloadBatch::current && OffloadBatch::current->repeat) return;
                retainedExtras |= retained && stack.extra;
                // Park retained extras so bare filled items cannot remove them.
                if (!OffloadBatch::current && retained && stack.extra && gem->GetContainedSoul() != RE::SOUL_LEVEL::kNone)
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
                const auto inventory = source->GetInventory([](RE::TESBoundObject& item) { return item.As<RE::TESSoulGem>() != nullptr; });
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

    void BeginLoan(bool a_smithing, bool a_allMaterials) {
        ResetLoan();
        Recover();
        auto* utility = Utility::GetSingleton();
        auto* player = RE::PlayerCharacter::GetSingleton();
        carriedBefore = CountGems(player);
        auto* source = utility->GetContainer(Container::Soulgem);
        if (!a_smithing && !a_allMaterials) {
            Split();
            source = utility->GetContainer(Container::FilledSoulgems);
        }
        MoveAll(source, player, [utility, a_smithing, a_allMaterials](auto* gem) {
            return a_allMaterials || !a_smithing || utility->isSmithing(gem->GetFormID());
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
        const auto inventory = player->GetInventory([](RE::TESBoundObject& item) { return loanForms.contains(item.GetFormID()); });
        std::vector<Stack> stacks;
        for (const auto& [item, data] : inventory) {
            auto* gem = item ? item->As<RE::TESSoulGem>() : nullptr;
            if (!gem || !loanForms.contains(gem->GetFormID()) || !data.second || Protected(gem, *data.second)) continue;
            if (HasCategory(ClassifyItem(gem), ItemCategory::Ignore)) continue;
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
