#include "InventoryStacks.h"
#include <limits>
#include <atomic>
#include <mutex>
#include <unordered_set>

namespace InventoryStacks {
    struct ReadState {
        using Iterator = decltype(std::declval<RE::InventoryEntryData>().extraLists->begin());
        RE::FormID source{}, item{};
        RE::InventoryEntryData* entry{};
        decltype(RE::InventoryEntryData::extraLists) lists{};
        RE::ExtraDataList** head{};
        Iterator next;
        std::atomic<bool> invalid{};
        RE::FormID destination{};
        int expected{};
    };

    namespace {
        std::mutex readersLock;
        std::vector<std::weak_ptr<ReadState>> readers;
        struct ReadEvents final : RE::BSTEventSink<RE::TESContainerChangedEvent>, RE::BSTEventSink<RE::TESEquipEvent> {
            void Invalidate(RE::FormID from, RE::FormID to, RE::FormID item, int count = 0) {
                std::lock_guard guard(readersLock);
                for (auto it = readers.begin(); it != readers.end();) {
                    if (const auto reader = it->lock()) {
                        if ((reader->source == from || reader->source == to) && reader->item == item) {
                            if (from == reader->source && to == reader->destination && count > 0 && count <= reader->expected)
                                reader->expected -= count;
                            else reader->invalid = true;
                        }
                        ++it;
                    } else it = readers.erase(it);
                }
            }
            RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent* event,
                RE::BSTEventSource<RE::TESContainerChangedEvent>*) override {
                if (event) Invalidate(event->oldContainer, event->newContainer, event->baseObj, event->itemCount);
                return RE::BSEventNotifyControl::kContinue;
            }
            RE::BSEventNotifyControl ProcessEvent(const RE::TESEquipEvent* event,
                RE::BSTEventSource<RE::TESEquipEvent>*) override {
                if (event && event->actor) Invalidate(event->actor.get()->GetFormID(), 0, event->baseObject);
                return RE::BSEventNotifyControl::kContinue;
            }
        } readEvents;
    }

    bool ReadEntryPart(RE::TESObjectREFR* source, RE::TESBoundObject* item, RE::InventoryEntryData& entry,
        int total, ReadCursor& cursor, const std::function<void(RE::InventoryEntryData&, RE::ExtraDataList*, int)>& visit) {
        if (!source || !item || !cursor.valid || total <= 0) { cursor.valid = false; return true; }
        auto* head = entry.extraLists && !entry.extraLists->empty() ? std::addressof(*entry.extraLists->begin()) : nullptr;
        if (!cursor.state) {
            cursor.state = std::make_shared<ReadState>();
            auto& state = *cursor.state;
            state.source = source->GetFormID(); state.item = item->GetFormID(); state.entry = &entry;
            state.lists = entry.extraLists; state.head = head;
            if (entry.extraLists) state.next = entry.extraLists->begin();
            if (auto* events = RE::ScriptEventSourceHolder::GetSingleton()) {
                events->AddEventSink(static_cast<RE::BSTEventSink<RE::TESContainerChangedEvent>*>(&readEvents));
                events->AddEventSink<RE::TESEquipEvent>(&readEvents);
            } else { cursor.valid = false; return true; }
            {
                std::lock_guard guard(readersLock);
                std::erase_if(readers, [](const auto& reader) { return reader.expired(); });
                readers.emplace_back(cursor.state);
            }
            cursor.total = total;
        }
        auto& state = *cursor.state;
        if (state.invalid || state.source != source->GetFormID() || state.item != item->GetFormID() ||
            state.entry != &entry || state.lists != entry.extraLists || state.head != head || cursor.total != total) {
            cursor.valid = false; return true;
        }
        int processed{};
        while (entry.extraLists && state.next != entry.extraLists->end()) {
            if (processed++ == 16) return false;
            auto* extra = *state.next++;
            ++cursor.offset;
            if (!extra) continue;
            const int count = extra->GetCount();
            if (!cursor.seen.insert(extra).second || count <= 0 || cursor.explicitCount + count > total) {
                cursor.valid = false; return true;
            }
            cursor.explicitCount += count;
            visit(entry, extra, count);
            if (!cursor.valid || state.invalid) { cursor.valid = false; return true; }
        }
        if (cursor.explicitCount < total) visit(entry, nullptr, static_cast<int>(total - cursor.explicitCount));
        return true;
    }

    bool ReadPart(RE::TESObjectREFR* source, RE::TESBoundObject* item, ReadCursor& cursor,
        const std::function<void(RE::InventoryEntryData&, RE::ExtraDataList*, int)>& visit) {
        if (!source || !item || !cursor.valid) { cursor.valid = false; return true; }
        auto* changes = source->GetInventoryChanges();
        RE::InventoryEntryData* entry{};
        if (changes && changes->entryList) for (auto* candidate : *changes->entryList)
            if (candidate && candidate->object == item) { entry = candidate; break; }
        const int total = Count(source, item);
        if (!entry) {
            if (cursor.state) { cursor.valid = false; return true; }
            RE::InventoryEntryData bare{item, 0};
            return ReadEntryPart(source, item, bare, total, cursor, visit);
        }
        return ReadEntryPart(source, item, *entry, total, cursor, visit);
    }

    bool Valid(const ReadCursor& cursor) { return cursor.valid && cursor.state && !cursor.state->invalid; }

    bool Prepare(RE::TESObjectREFR* source, RE::TESBoundObject* item, Prepared& prepared,
        const std::function<bool(RE::ExtraDataList*, int, std::size_t)>& validate) {
        if (prepared.complete) return true;
        bool first = true;
        prepared.complete = ReadPart(source, item, prepared.cursor, [&](auto& entry, auto* extra, int count) {
            if (first) {
                first = false;
                prepared.quest |= entry.IsQuestObject();
                prepared.favorite |= entry.IsFavorited();
            }
            prepared.identifiedFavorite |= extra && extra->template HasType<RE::ExtraHotkey>();
            prepared.worn |= extra && (extra->template HasType<RE::ExtraWorn>() || extra->template HasType<RE::ExtraWornLeft>());
            if (validate && !validate(extra, count, prepared.stacks.size())) prepared.cursor.valid = false;
            prepared.stacks.push_back({source, item, extra, count});
        });
        return prepared.complete;
    }

    int MovePrepared(const Stack& stack, RE::TESObjectREFR* target, Prepared& prepared, std::size_t index) {
        if (!Valid(prepared.cursor) || !target || index >= prepared.stacks.size()) return 0;
        auto& state = *prepared.cursor.state;
        { std::lock_guard guard(readersLock); state.destination = target->GetFormID(); state.expected = stack.count; }
        const int moved = Move(stack, target);
        { std::lock_guard guard(readersLock); state.destination = 0; state.expected = 0; }
        if (moved) prepared.moved.emplace_back(index, moved);
        return moved;
    }

    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select, RE::TESBoundObject* onlyItem, bool firstOnly) {
        return Read(source, std::move(select), onlyItem, firstOnly, {});
    }

    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select, RE::TESBoundObject* onlyItem, bool firstOnly,
        std::function<bool(RE::TESBoundObject&)> filter) {
        std::vector<Stack> result;
        if (!source) return result;
        for (const auto& [item, data] : source->GetInventory([onlyItem, &filter](RE::TESBoundObject& item) {
            return (!onlyItem || &item == onlyItem) && (!filter || filter(item));
        })) {
            auto* entry = data.second.get();
            if (!item || data.first <= 0 || !entry) continue;
            std::vector<Stack> selected;
            std::unordered_set<RE::ExtraDataList*> visited;
            std::int64_t explicitCount{};
            bool valid = true;
            // A first-stack request still validates every physical count in the entry.
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
                    if ((!firstOnly || selected.empty()) && (!select || select(item, *entry, extra)))
                        selected.push_back({source, item, extra, count});
                }
            }
            if (!valid) continue;
            if (explicitCount < data.first && (!firstOnly || selected.empty()) && (!select || select(item, *entry, nullptr)))
                selected.push_back({source, item, nullptr, static_cast<int>(data.first - explicitCount)});
            result.insert(result.end(), selected.begin(), selected.end());
            if (firstOnly && !result.empty()) break;
        }
        return result;
    }

    bool IsFavorited(const RE::InventoryEntryData& entry, RE::ExtraDataList* extra) {
        if (!entry.IsFavorited()) return false;
        if (extra && extra->HasType<RE::ExtraHotkey>()) return true;
        if (entry.extraLists) for (auto* copy : *entry.extraLists)
            if (copy && copy->HasType<RE::ExtraHotkey>()) return false;
        return true;
    }

    RE::BGSKeyword* FavoriteKeyword() {
        auto* data = RE::TESDataHandler::GetSingleton();
        return data ? data->LookupForm<RE::BGSKeyword>(0xDF0, "ArcaneVaults-LinkedStorage.esp") : nullptr;
    }

    void RestoreFavorites(RE::TESObjectREFR* source) {
        auto* keyword = FavoriteKeyword();
        auto* changes = source ? source->GetInventoryChanges() : nullptr;
        if (!keyword || !changes) return;
        for (const auto& [item, data] : source->GetInventory()) {
            if (!item || !data.second || !data.second->extraLists) continue;
            for (auto* extra : *data.second->extraLists)
                if (HasOrigin(extra, keyword) && !extra->HasType<RE::ExtraHotkey>())
                    changes->SetFavorite(data.second.get(), extra);
        }
        ClearOrigins(source, keyword);
    }

    std::map<RE::TESBoundObject*, int> Counts(RE::TESObjectREFR* source,
        std::function<bool(RE::TESBoundObject&)> filter, bool noInit) {
        std::map<RE::TESBoundObject*, int> counts;
        if (!source) return counts;
        std::unordered_map<RE::TESBoundObject*, const RE::InventoryEntryData*> entries;
        const auto* changes = source->GetInventoryChanges(noInit);
        if (changes && changes->entryList) for (const auto* entry : *changes->entryList) {
            if (!entry || !entry->object || (filter && !filter(*entry->object))) continue;
            counts.emplace(entry->object, entry->countDelta);
            entries.emplace(entry->object, entry);
        }
        if (auto* container = source->GetContainer()) container->ForEachContainerObject([&](auto& entry) {
            if (entry.obj && (!filter || filter(*entry.obj))) {
                const auto found = entries.find(entry.obj);
                if (!entry.count || found == entries.end() || !found->second->IsLeveled())
                    counts[entry.obj] += entry.count;
            }
            return RE::BSContainer::ForEachResult::kContinue;
        });
        return counts;
    }

    int Count(RE::TESObjectREFR* source, RE::TESBoundObject* item) {
        if (!source || !item) return 0;
        int count = 0;
        bool leveled = false;
        const auto* changes = source->GetInventoryChanges();
        if (changes && changes->entryList) for (auto* entry : *changes->entryList) {
            if (!entry || entry->object != item) continue;
            count = entry->countDelta;
            leveled = entry->IsLeveled();
            break;
        }
        if (!leveled) if (auto* container = source->GetContainer()) container->ForEachContainerObject([&](auto& entry) {
            if (entry.obj == item) count += entry.count;
            return RE::BSContainer::ForEachResult::kContinue;
        });
        return (std::max)(0, count);
    }

    bool HasItems(RE::TESObjectREFR* source) {
        if (!source) return false;
        for (const auto& [item, count] : Counts(source, {}, true))
            if (item && count > 0) return true;
        return false;
    }

    int Move(const Stack& stack, RE::TESObjectREFR* target) {
        if (!target || target == stack.source) return 0;
        const int before = Count(stack.source, stack.item);
        const int targetBefore = Count(target, stack.item);
        const int count = (std::min)(stack.count, (std::numeric_limits<int>::max)() - targetBefore);
        if (count <= 0) return 0;
        stack.source->RemoveItem(stack.item, count, RE::ITEM_REMOVE_REASON::kStoreInContainer, stack.extra, target);
        const int removed = before - Count(stack.source, stack.item);
        return removed > 0 && removed <= count && Count(target, stack.item) - targetBefore == removed ? removed : 0;
    }

    bool HasOrigin(RE::ExtraDataList* extra, RE::BGSKeyword* keyword) {
        const auto* links = extra ? extra->GetByType<RE::ExtraLinkedRef>() : nullptr;
        if (!links || !keyword) return false;
        for (const auto& link : links->linkedRefs)
            if (link.keyword == keyword) return true;
        return false;
    }

    void ClearOrigins(RE::TESObjectREFR* source, RE::BGSKeyword* keyword, RE::TESBoundObject* item) {
        if (!source || !keyword) return;
        for (const auto& stack : Read(source, {}, item)) {
            if (!HasOrigin(stack.extra, keyword)) continue;
            auto* links = stack.extra->GetByType<RE::ExtraLinkedRef>();
            for (auto i = links->linkedRefs.size(); i > 0; --i)
                if (links->linkedRefs[i - 1].keyword == keyword)
                    links->linkedRefs.erase(links->linkedRefs.begin() + i - 1);
            if (links->linkedRefs.empty()) stack.extra->RemoveByType(RE::ExtraDataType::kLinkedRef);
            source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
        }
    }

    std::optional<Stack> Materialize(const Stack& stack) {
        if (!stack.source || !stack.item || stack.count <= 0) return std::nullopt;
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
            stack.source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
        }
        return marked;
    }

    std::optional<Stack> MarkOrigin(const Stack& stack, RE::BGSKeyword* keyword) {
        if (!keyword) return std::nullopt;
        const auto physical = Materialize(stack);
        if (!physical) return std::nullopt;
        auto marked = *physical;
        marked.extra->SetLinkedRef(stack.source, keyword);
        stack.source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
        return marked.extra->GetLinkedRef(keyword) == stack.source ? std::optional{marked} : std::nullopt;
    }
}
