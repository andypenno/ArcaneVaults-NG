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

    using InventoryStacks::Count;
    using InventoryStacks::HasItems;
    using InventoryStacks::Move;

    std::vector<StolenItems::Stack> ReadStacks(RE::TESObjectREFR* source, bool stolenOnly) {
        if (!stolenOnly) return InventoryStacks::Read(source);
        auto* player = RE::PlayerCharacter::GetSingleton();
        if (!player) return {};
        return InventoryStacks::Read(source, [player](auto*, RE::InventoryEntryData& entry, auto* extra) {
            return extra && !entry.IsOwnedBy(player, extra->GetOwner(), true);
        });
    }

    bool HasMarker(RE::ExtraDataList* extra) {
        return InventoryStacks::HasOrigin(extra, originKeyword);
    }

    void ClearMarkers(RE::TESObjectREFR* source) {
        InventoryStacks::ClearOrigins(source, originKeyword);
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
