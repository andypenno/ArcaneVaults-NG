#include "RedirectManager.h"
#include "Settings.h"

namespace
{
    void RefreshCrosshairText()
    {
        SKSE::GetTaskInterface()->AddTask([] {
            auto* player = RE::PlayerCharacter::GetSingleton();
            if (!player) return;

            player->GetPlayerRuntimeData().playerFlags.shouldUpdateCrosshair = true;
            player->UpdateCrosshairs();
        });
    }

    void SetLinkedContainerBlocked(const RE::TESObjectREFR* a_source, bool a_blocked)
    {
        if (!a_source || !a_source->GetBaseObject() ||
            !a_source->GetBaseObject()->As<RE::TESObjectACTI>()) {
            return;
        }

        auto* linked = const_cast<RE::TESObjectREFR*>(a_source)->GetLinkedRef(nullptr);
        if (linked && linked->GetBaseObject() &&
            linked->GetBaseObject()->As<RE::TESObjectCONT>()) {
            linked->SetActivationBlocked(a_blocked);
        }
    }
}

bool RedirectManager::Add(RE::TESObjectREFR* source, RE::TESObjectREFR* destination) {
    if (!source || !destination) return false;
    return Restore(source->GetFormID(), destination, Settings::MakeFormIdentifier(source).value_or(""));
}

bool RedirectManager::Restore(RE::FormID sourceID, RE::TESObjectREFR* destination, std::string sourceIdentifier) {
    if (!sourceID || !destination || sourceID == destination->GetFormID()) return false;
    auto* form = RE::TESForm::LookupByID(sourceID);
    auto* source = form ? form->As<RE::TESObjectREFR>() : nullptr;
    if (form && !source) return false;
    if (sourceIdentifier.empty())
        sourceIdentifier = Settings::MakeFormIdentifier(source).value_or("");
    redirects.insert_or_assign(sourceID, ContainerRedirect{
        destination->GetFormID(), std::move(sourceIdentifier),
        Settings::MakeFormIdentifier(destination).value_or("") });

    SetLinkedContainerBlocked(source, true);
    RefreshCrosshairText();
    return true;
}

bool RedirectManager::Remove(RE::TESObjectREFR* source) {
    if (!source) return false;

    // Get the source redirect
    const auto entry = redirects.find(source->GetFormID());
    if (entry == redirects.end()) return false;

    // Return the activator back to what it was
    SetLinkedContainerBlocked(source, false);
    // Remove the entry
    redirects.erase(entry);

    // Set the display name back to the original
    RefreshCrosshairText();

    return true;
}

void RedirectManager::Clear() {
    for (const auto& [sourceID, redirect] : redirects) {
        if (auto* source = RE::TESForm::LookupByID<RE::TESObjectREFR>(sourceID)) {
            SetLinkedContainerBlocked(source, false);
        }
    }

    redirects.clear();
    RefreshCrosshairText();
}

RE::TESObjectREFR* RedirectManager::FindDestination(const RE::TESObjectREFR* source) const {
    if (!source) return nullptr;

    // Find the source object in our map
    const auto entry = redirects.find(source->GetFormID());
    if (entry == redirects.end()) return nullptr;

    auto* destination = RE::TESForm::LookupByID<RE::TESObjectREFR>(entry->second.destinationID);
    if (destination) SetLinkedContainerBlocked(source, true);
    return destination;
}
