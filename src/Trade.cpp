#include "Trade.h"
#include <algorithm>
#include <limits>
#include <unordered_set>

namespace {
    std::int64_t Payout(std::int64_t value, int percentage) {
        return (value / 100) * percentage + (value % 100) * percentage / 100;
    }

    int Count(RE::TESObjectREFR* source, RE::TESBoundObject* item) {
        const auto counts = source->GetInventoryCounts();
        const auto found = counts.find(item);
        return found == counts.end() ? 0 : (std::max)(0, found->second);
    }
}

namespace Trade {
    Quote GetQuote(RE::TESObjectREFR* source, int percentage) {
        Quote quote;
        if (!source || percentage < 1 || percentage > 100) return quote;
        quote.percentage = percentage;
        std::int64_t totalValue{};
        for (const auto& [item, data] : source->GetInventory()) {
            const auto* entry = data.second.get();
            if (!item || item->IsGold() || data.first <= 0 || !entry ||
                entry->IsQuestObject() || entry->IsFavorited() || entry->IsWorn()) continue;

            std::vector<Stack> stacks;
            std::unordered_set<RE::ExtraDataList*> visited;
            std::int64_t explicitCount{};
            bool valid = true;
            if (entry->extraLists) {
                for (auto* extra : *entry->extraLists) {
                    if (!extra) continue;
                    const int count = extra->GetCount();
                    if (!visited.insert(extra).second || count <= 0 || explicitCount + count > data.first) {
                        valid = false;
                        break;
                    }
                    explicitCount += count;
                    RE::InventoryEntryData variant(item, count);
                    variant.AddExtraList(extra);
                    stacks.push_back({item, extra, count, (std::max)(0, variant.GetValue())});
                }
            }
            if (!valid) continue;
            if (explicitCount < data.first) {
                RE::InventoryEntryData plain(item, static_cast<int>(data.first - explicitCount));
                stacks.push_back({item, nullptr, static_cast<int>(data.first - explicitCount),
                    (std::max)(0, plain.GetValue())});
            }
            for (const auto& stack : stacks) {
                const auto value = static_cast<std::int64_t>(stack.value) * stack.count;
                if (value > (std::numeric_limits<std::int64_t>::max)() - totalValue) return {};
                totalValue += value;
                quote.copies += stack.count;
                quote.stacks.push_back(stack);
            }
        }
        quote.payout = Payout(totalValue, percentage);
        quote.valid = true;
        return quote;
    }

    bool CanReceive(const Quote& quote) {
        auto* player = RE::PlayerCharacter::GetSingleton();
        auto* gold = RE::TESForm::LookupByID<RE::TESBoundObject>(0xF);
        return player && gold && quote.valid && quote.payout >= 0 &&
            quote.payout <= (std::numeric_limits<int>::max)() - Count(player, gold);
    }

    std::optional<int> Sell(RE::TESObjectREFR* source, const Quote& confirmed) {
        auto* player = RE::PlayerCharacter::GetSingleton();
        auto* gold = RE::TESForm::LookupByID<RE::TESBoundObject>(0xF);
        if (!source || source == player || !player || !gold || !confirmed.valid) return std::nullopt;
        const auto current = GetQuote(source, confirmed.percentage);
        if (!current.valid || current.stacks != confirmed.stacks || current.payout != confirmed.payout ||
            current.copies != confirmed.copies) return std::nullopt;
        if (!CanReceive(current)) return std::nullopt;

        std::int64_t soldValue{};
        RE::TESBoundObject* failedItem{};
        for (const auto& stack : current.stacks) {
            // A failed explicit move must not let a null list select that variant.
            if (stack.item == failedItem) continue;
            const int before = Count(source, stack.item);
            source->RemoveItem(stack.item, stack.count, RE::ITEM_REMOVE_REASON::kRemove, stack.extra, nullptr);
            const int removed = std::clamp(before - Count(source, stack.item), 0, stack.count);
            soldValue += static_cast<std::int64_t>(stack.value) * removed;
            if (removed != stack.count) failedItem = stack.item;
        }
        const int payout = static_cast<int>(Payout(soldValue, current.percentage));
        if (payout > 0) player->AddObjectToContainer(gold, nullptr, payout, nullptr);
        return payout;
    }
}
