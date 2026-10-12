#include "DepositLearning.h"
#include "Settings.h"
#include "Stores.h"
#include "Utility.h"
#include "Translation.h"
#include <atomic>
#include <deque>

namespace {
    std::atomic<std::uint64_t> generation{};
    RE::FormID destination{};
    ItemCategory category{ ItemCategory::None };
    std::unordered_map<RE::FormID, std::int64_t> automatic;
    std::unordered_set<RE::FormID> considered;
    std::deque<RE::FormID> pending;
    bool showing{};
    std::uint64_t dialog{};

    ItemCategory DestinationCategory(Container kind) {
        switch (kind) {
        case Container::Alchemy: return ItemCategory::Alchemy;
        case Container::Armor: return ItemCategory::Armor;
        case Container::Clothing: return ItemCategory::Clothing;
        case Container::HeavyArmor: return ItemCategory::HeavyArmor;
        case Container::LightArmor: return ItemCategory::LightArmor;
        case Container::Jewelry: return ItemCategory::Jewelry;
        case Container::Book: return ItemCategory::Book;
        case Container::Food: return ItemCategory::Food;
        case Container::CookedFood: return ItemCategory::CookedFood;
        case Container::RawFood: return ItemCategory::RawFood;
        case Container::Reagent: return ItemCategory::Reagent;
        case Container::Gemstone: return ItemCategory::Gemstone;
        case Container::Concoction: return ItemCategory::Concoction;
        case Container::Potion: return ItemCategory::Potion;
        case Container::Poison: return ItemCategory::Poison;
        case Container::Restorative: return ItemCategory::Restorative;
        case Container::Scroll: return ItemCategory::Scroll;
        case Container::Smithing: return ItemCategory::Smithing;
        case Container::Construction: return ItemCategory::Construction;
        case Container::Crafting: return ItemCategory::Crafting;
        case Container::Smelting: return ItemCategory::Smelting;
        case Container::Tanning: return ItemCategory::Tanning;
        case Container::Treasure: return ItemCategory::Treasure;
        case Container::Weapon: return ItemCategory::Weapon;
        case Container::Archery: return ItemCategory::Archery;
        case Container::OneHand: return ItemCategory::OneHand;
        case Container::TwoHand: return ItemCategory::TwoHand;
        case Container::Staff: return ItemCategory::Staff;
        case Container::Keys: return ItemCategory::Keys;
        case Container::Ammunition: return ItemCategory::Ammunition;
        case Container::Notes: return ItemCategory::Note;
        case Container::SpellTomes: return ItemCategory::SpellTome;
        case Container::SkillBooks: return ItemCategory::SkillBook;
        case Container::Recipes: return ItemCategory::Recipe;
        case Container::TreasureMaps: return ItemCategory::TreasureMap;
        default: return ItemCategory::None;
        }
    }

    bool Active(std::uint64_t session) {
        auto target = RE::TESObjectREFR::LookupByHandle(RE::ContainerMenu::GetTargetRefHandle());
        return session == generation && destination && category != ItemCategory::None &&
            Settings::GetSingleton()->GSC_LearnDepositOverrides &&
            RE::UI::GetSingleton()->IsMenuOpen(RE::ContainerMenu::MENU_NAME) &&
            target && target->GetFormID() == destination;
    }

    bool Mismatch(RE::TESBoundObject* item) {
        return item && !item->As<RE::TESSoulGem>() && Settings::MakeFormIdentifier(item) &&
            !HasCategory(ClassifyItem(item), category);
    }

    void ShowNext();

    void Answer(std::uint64_t session, std::uint64_t ticket, RE::FormID formID, ItemCategory proposed, bool accept) {
        if (ticket != dialog) return;
        showing = false;
        if (accept && Active(session)) {
            auto* item = RE::TESForm::LookupByID<RE::TESBoundObject>(formID);
            auto* settings = Settings::GetSingleton();
            if (Mismatch(item)) {
                const auto& overrides = settings->GetUserOverrides();
                const auto found = overrides.find(formID);
                const std::optional<CategoryMask> previous = found == overrides.end() ?
                    std::nullopt : std::optional<CategoryMask>{found->second};
                settings->SetUserOverride(item, ToMask(proposed));
                if (!settings->SaveUserOverrides()) {
                    if (previous) settings->SetUserOverride(item, *previous);
                    else settings->RemoveUserOverride(formID);
                    RE::SendHUDMessage::ShowHUDMessage(AVTranslation::Translate("Learning.SaveFailed"));
                }
            }
        }
        ShowNext();
    }

    void ShowNext() {
        const auto session = generation.load();
        if (showing || !Active(session)) return;
        while (!pending.empty()) {
            const auto id = pending.front();
            pending.pop_front();
            auto* item = RE::TESForm::LookupByID<RE::TESBoundObject>(id);
            if (!Mismatch(item)) continue;
            const auto proposed = category;
            const auto ticket = ++dialog;
            const auto* name = item->GetName();
            auto proposedName = FormatCategories(ToMask(proposed));
            auto currentName = FormatCategories(ClassifyItem(item));
            if (currentName.empty()) currentName = AVTranslation::Translate("Learning.Unclassified");
            const auto message = std::vformat(AVTranslation::Translate("Learning.Confirm"),
                std::make_format_args(name, proposedName, currentName));
            showing = true;
            Stores::GetSingleton()->ShowDynamicMessageBox(message, {
                { AVTranslation::Translate("Learning.No"), [session, ticket, id, proposed] {
                    SKSE::GetTaskInterface()->AddTask([=] { Answer(session, ticket, id, proposed, false); });
                } },
                { AVTranslation::Translate("Learning.Yes"), [session, ticket, id, proposed] {
                    SKSE::GetTaskInterface()->AddTask([=] { Answer(session, ticket, id, proposed, true); });
                } }
            }, 0);
            return;
        }
    }

    void Process(RE::TESContainerChangedEvent event, std::uint64_t session) {
        if (!Active(session) || event.oldContainer != 0x14 || event.newContainer != destination ||
            event.itemCount <= 0) return;
        auto& count = automatic[event.baseObj];
        const auto suppressed = (std::min)(count, static_cast<std::int64_t>(event.itemCount));
        count -= suppressed;
        if (suppressed == event.itemCount) return;
        auto* item = RE::TESForm::LookupByID<RE::TESBoundObject>(event.baseObj);
        if (!Mismatch(item) || !considered.insert(event.baseObj).second) return;
        pending.push_back(event.baseObj);
        ShowNext();
    }

    class Sink : public RE::BSTEventSink<RE::TESContainerChangedEvent> {
        RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent* event,
            RE::BSTEventSource<RE::TESContainerChangedEvent>*) override {
            if (event && event->oldContainer == 0x14 && event->itemCount > 0) {
                const auto session = generation.load();
                const auto copy = *event;
                SKSE::GetTaskInterface()->AddTask([copy, session] { Process(copy, session); });
            }
            return RE::BSEventNotifyControl::kContinue;
        }
    };
}

namespace DepositLearning {
    void Register() {
        static Sink sink;
        RE::ScriptEventSourceHolder::GetSingleton()->AddEventSink(&sink);
    }

    void MenuClosed() {
        ++generation;
        destination = 0;
        category = ItemCategory::None;
        automatic.clear();
        considered.clear();
        pending.clear();
    }

    void MenuOpened() {
        MenuClosed();
        auto target = RE::TESObjectREFR::LookupByHandle(RE::ContainerMenu::GetTargetRefHandle());
        if (!target) return;
        destination = target->GetFormID();
        category = DestinationCategory(Utility::GetSingleton()->GetContainerKind(destination));
    }

    void Reset() {
        MenuClosed();
        ++dialog;
        showing = false;
    }

    void RecordAutomaticTransfer(RE::TESObjectREFR* source, RE::TESObjectREFR* target,
        RE::TESBoundObject* item, int count) {
        // Consume queued engine events by the observed moved count, including partial transfers.
        if (source && source->GetFormID() == 0x14 && target && target->GetFormID() == destination &&
            item && count > 0 && category != ItemCategory::None)
            automatic[item->GetFormID()] += count;
    }
}
