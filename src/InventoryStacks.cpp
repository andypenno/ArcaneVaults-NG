#include "InventoryStacks.h"
#include <limits>
#include <unordered_set>

namespace InventoryStacks {
    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select) {
        std::vector<Stack> result;
        if (!source) return result;
        for (const auto& [item, data] : source->GetInventory()) {
            auto* entry = data.second.get();
            if (!item || data.first <= 0 || !entry) continue;
            std::vector<Stack> selected;
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
                    // The aggregate owner can belong to a different copy of this base record.
                    if (!select || select(item, *entry, extra))
                        selected.push_back({source, item, extra, count});
                }
            }
            if (!valid) continue;
            if (explicitCount < data.first && (!select || select(item, *entry, nullptr)))
                selected.push_back({source, item, nullptr, static_cast<int>(data.first - explicitCount)});
            result.insert(result.end(), selected.begin(), selected.end());
        }
        return result;
    }

    int Count(RE::TESObjectREFR* source, RE::TESBoundObject* item) {
        const auto counts = source->GetInventoryCounts();
        const auto found = counts.find(item);
        return found == counts.end() ? 0 : (std::max)(0, found->second);
    }

    bool HasItems(RE::TESObjectREFR* source) {
        if (!source) return false;
        for (const auto& [item, count] : source->GetInventoryCounts())
            if (item && count > 0) return true;
        return false;
    }

    bool Move(const Stack& stack, RE::TESObjectREFR* target) {
        if (!target || target == stack.source) return false;
        const int before = Count(stack.source, stack.item);
        const int targetBefore = Count(target, stack.item);
        const int count = (std::min)(stack.count, (std::numeric_limits<int>::max)() - targetBefore);
        if (count <= 0) return false;
        stack.source->RemoveItem(stack.item, count, RE::ITEM_REMOVE_REASON::kStoreInContainer, stack.extra, target);
        const int removed = before - Count(stack.source, stack.item);
        return removed > 0 && removed <= count && Count(target, stack.item) - targetBefore == removed;
    }

    bool HasOrigin(RE::ExtraDataList* extra, RE::BGSKeyword* keyword) {
        const auto* links = extra ? extra->GetByType<RE::ExtraLinkedRef>() : nullptr;
        if (!links || !keyword) return false;
        for (const auto& link : links->linkedRefs)
            if (link.keyword == keyword) return true;
        return false;
    }

    void ClearOrigins(RE::TESObjectREFR* source, RE::BGSKeyword* keyword) {
        if (!source || !keyword) return;
        for (const auto& stack : Read(source)) {
            if (!HasOrigin(stack.extra, keyword)) continue;
            auto* links = stack.extra->GetByType<RE::ExtraLinkedRef>();
            for (auto i = links->linkedRefs.size(); i > 0; --i)
                if (links->linkedRefs[i - 1].keyword == keyword)
                    links->linkedRefs.erase(links->linkedRefs.begin() + i - 1);
            if (links->linkedRefs.empty()) stack.extra->RemoveByType(RE::ExtraDataType::kLinkedRef);
            source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
        }
    }

    std::optional<Stack> MarkOrigin(const Stack& stack, RE::BGSKeyword* keyword) {
        if (!stack.source || !stack.item || !keyword || stack.count <= 0) return std::nullopt;
        auto marked = stack;
        if (!marked.extra) {
            auto* changes = stack.source->GetInventoryChanges();
            if (!changes) return std::nullopt;
            RE::InventoryEntryData* entry{};
            if (changes->entryList) {
                for (auto* candidate : *changes->entryList)
                    if (candidate && candidate->object == stack.item) { entry = candidate; break; }
            }
            if (!entry) {
                entry = new RE::InventoryEntryData(stack.item, 0);
                changes->AddEntryData(entry);
            }
            using Construct = RE::ExtraDataList* (*)(void*);
            static REL::Relocation<Construct> construct{REL::VariantID(11437, 11583, 0x117C80)};
            auto* storage = RE::malloc(REL::Relocate<std::size_t>(0x18, 0x20, 0x18));
            if (!storage) return std::nullopt;
            marked.extra = construct(storage);
            if (!marked.extra) { RE::free(storage); return std::nullopt; }
            // ExtraCount stores a signed 16-bit quantity.
            marked.count = (std::min)(stack.count, static_cast<int>((std::numeric_limits<std::int16_t>::max)()));
            marked.extra->SetCount(static_cast<std::uint16_t>(marked.count));
            entry->AddExtraList(marked.extra);
        }
        marked.extra->SetLinkedRef(stack.source, keyword);
        stack.source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
        return marked.extra->GetLinkedRef(keyword) == stack.source ? std::optional{marked} : std::nullopt;
    }
}
