#include "StolenItems.h"
#include "Utility.h"
#include "Settings.h"
#include "Translation.h"
#include <atomic>
#include <limits>
#include <unordered_set>

namespace {
    RE::BGSKeyword* originKeyword{};
    std::atomic<std::uint64_t> generation{};
    std::atomic<RE::FormID> archiveID{};

    RE::TESObjectREFR* Archive() {
        return Utility::GetSingleton()->GetContainer(Container::StolenItems);
    }

    std::vector<RE::TESObjectREFR*> MainVaults() {
        std::vector<RE::TESObjectREFR*> result;
        auto* utility = Utility::GetSingleton();
        std::unordered_set<RE::FormID> visited;
        for (const auto& choice : utility->GetVaultChoices()) {
            auto* source = RE::TESForm::LookupByID<RE::TESObjectREFR>(choice.formID);
            if (!source || source == utility->GetContainer(Container::Trade) ||
                source == utility->GetContainer(Container::Sort) || source == utility->GetContainer(Container::Ignore) ||
                !visited.insert(choice.formID).second) continue;
            result.push_back(source);
        }
        return result;
    }

    std::vector<StolenItems::Stack> ReadStacks(RE::TESObjectREFR* source, bool stolenOnly) {
        std::vector<StolenItems::Stack> result;
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!source || !player) return result;
        for (const auto& [item, data] : source->GetInventory()) {
            auto* entry = data.second.get();
            if (!item || data.first <= 0 || !entry) continue;
            std::vector<StolenItems::Stack> selected;
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
                    if (!stolenOnly || !entry->IsOwnedBy(player, extra->GetOwner(), true))
                        selected.push_back({source, item, extra, count});
                }
            }
            if (!valid) continue;
            if (!stolenOnly && explicitCount < data.first)
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

    bool HasMarker(RE::ExtraDataList* extra) {
        const auto* links = extra ? extra->GetByType<RE::ExtraLinkedRef>() : nullptr;
        if (!links) return false;
        for (const auto& link : links->linkedRefs)
            if (link.keyword == originKeyword) return true;
        return false;
    }

    void RemoveMarker(RE::ExtraDataList* extra) {
        auto* links = extra ? extra->GetByType<RE::ExtraLinkedRef>() : nullptr;
        if (!links) return;
        for (std::size_t i = links->linkedRefs.size(); i > 0; --i)
            if (links->linkedRefs[i - 1].keyword == originKeyword)
                links->linkedRefs.erase(links->linkedRefs.begin() + i - 1);
        if (links->linkedRefs.empty()) extra->RemoveByType(RE::ExtraDataType::kLinkedRef);
    }

    void ClearMarkers(RE::TESObjectREFR* source) {
        if (!originKeyword || !source) return;
        for (const auto& stack : ReadStacks(source, false)) {
            if (HasMarker(stack.extra)) {
                RemoveMarker(stack.extra);
                source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
            }
        }
    }

    bool Move(const StolenItems::Stack& stack, RE::TESObjectREFR* target) {
        if (!target || target == stack.source) return false;
        const int before = Count(stack.source, stack.item);
        const int targetBefore = Count(target, stack.item);
        const int count = (std::min)(stack.count, (std::numeric_limits<int>::max)() - targetBefore);
        if (count <= 0) return false;
        stack.source->RemoveItem(stack.item, count, RE::ITEM_REMOVE_REASON::kStoreInContainer, stack.extra, target);
        const int removed = before - Count(stack.source, stack.item);
        return removed > 0 && removed <= count && Count(target, stack.item) - targetBefore == removed;
    }

    class Sink : public RE::BSTEventSink<RE::TESContainerChangedEvent> {
        RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent* event,
            RE::BSTEventSource<RE::TESContainerChangedEvent>*) override {
            if (event && archiveID && event->oldContainer == archiveID && event->newContainer == 0x14 && event->itemCount > 0) {
                const auto session = generation.load();
                SKSE::GetTaskInterface()->AddTask([session] {
                    if (session == generation) ClearMarkers(RE::PlayerCharacter::GetSingleton());
                });
            }
            return RE::BSEventNotifyControl::kContinue;
        }
    };
}

namespace StolenItems {
    std::vector<Stack> GetStacks(RE::TESObjectREFR* source) {
        return ReadStacks(source, true);
    }

    std::vector<Stack> GetStoredStacks() {
        std::vector<Stack> result;
        for (auto* source : MainVaults()) {
            const auto stacks = GetStacks(source);
            result.insert(result.end(), stacks.begin(), stacks.end());
        }
        return result;
    }

    void Init() {
        originKeyword = RE::TESDataHandler::GetSingleton()->LookupForm<RE::BGSKeyword>(0xDE0, "ArcaneVaults-LinkedStorage.esp");
        archiveID = Archive() ? Archive()->GetFormID() : 0;
        static Sink sink;
        RE::ScriptEventSourceHolder::GetSingleton()->AddEventSink(&sink);
        if (!originKeyword || !archiveID) logger::error("Stolen Items archive or origin keyword is missing");
    }

    void Reset() {
        ++generation;
    }

    bool Return() {
        auto* archive = Archive();
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!archive || !player || !originKeyword) return false;
        const auto vaults = MainVaults();
        while (HasItems(archive)) {
            // RemoveItem may split, merge, or destroy lists. Reacquire after every move.
            const auto stacks = ReadStacks(archive, false);
            if (stacks.empty()) return false;
            const auto& stack = stacks.front();
            auto* origin = stack.extra ? stack.extra->GetLinkedRef(originKeyword) : nullptr;
            if (HasMarker(stack.extra) && !origin) return false;
            auto* target = origin ? origin : player;
            if (target != player && std::ranges::find(vaults, target) == vaults.end()) return false;
            if (!Move(stack, target)) return false;
            ClearMarkers(target);
        }
        return true;
    }

    bool Recover() {
        if (!Return()) return false;
        ClearMarkers(RE::PlayerCharacter::GetSingleton());
        for (auto* source : MainVaults()) ClearMarkers(source);
        return true;
    }

    bool Gather() {
        auto* archive = Archive();
        if (!archive || !originKeyword || !Recover()) return false;
        for (auto* source : MainVaults()) {
            for (;;) {
                const auto stacks = GetStacks(source);
                if (stacks.empty()) break;
                const auto& stack = stacks.front();
                stack.extra->SetLinkedRef(source, originKeyword);
                source->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
                if (stack.extra->GetLinkedRef(originKeyword) != source || !Move(stack, archive)) {
                    Recover();
                    return false;
                }
            }
        }
        return true;
    }

    bool Clear() {
        if (!Settings::GetSingleton()->GSC_AllowRemovingStolenTags || !Gather()) return false;
        auto* archive = Archive();
        for (const auto& stack : GetStacks(archive)) {
            stack.extra->RemoveByType(RE::ExtraDataType::kOwnership);
            archive->AddChange(RE::TESObjectREFR::ChangeFlags::kInventory);
        }
        return Return();
    }

    void ConfirmClear(std::function<void()> onComplete) {
        if (!Settings::GetSingleton()->GSC_AllowRemovingStolenTags) return;
        const auto session = generation.load();
        const auto finish = [session, onComplete] {
            if (session == generation && onComplete) onComplete();
        };
        Stores::GetSingleton()->ShowDynamicMessageBox(AVTranslation::Translate("Stolen.Confirm"), {
            { AVTranslation::Translate("Learning.No"), [finish] { SKSE::GetTaskInterface()->AddTask(finish); } },
            { AVTranslation::Translate("Learning.Yes"), [session, finish] {
                SKSE::GetTaskInterface()->AddTask([session, finish] {
                    if (session != generation) return;
                    if (!Settings::GetSingleton()->GSC_AllowRemovingStolenTags) { finish(); return; }
                    const bool success = Clear();
                    RE::SendHUDMessage::ShowHUDMessage(AVTranslation::Translate(success ? "Stolen.Cleared" : "Stolen.TransferFailed"));
                    finish();
                });
            } }
        }, 0);
    }
}
