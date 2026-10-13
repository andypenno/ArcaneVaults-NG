#pragma once
#include "Stores.h"
#include "Soulgems.h"
#include "Trade.h"
#include "Events.h"
#include "ContainerMenu.h"
#include "RedirectManager.h"
#include "ItemClass.h"
#include "Translation.h"
#include "Settings.h"
#include "DepositLearning.h"
#include "StolenItems.h"
#include "EnchantedItems.h"
#include "PlayerEquipment.h"

#include <chrono>
#include <thread>

namespace {
    void MoveItems(RE::TESObjectREFR* source, RE::TESObjectREFR* destination, RE::TESBoundObject* item, int count) {
        if (!source || !destination || source == destination || !item || count <= 0) return;
        const auto countItems = [source, item] {
            const auto counts = source->GetInventoryCounts([item](RE::TESBoundObject& candidate) { return &candidate == item; });
            const auto found = counts.find(item);
            return found == counts.end() ? 0 : (std::max)(0, found->second);
        };
        int available = countItems();
        while (count > 0 && available > 0) {
            source->RemoveItem(item, (std::min)(count, available), RE::ITEM_REMOVE_REASON::kStoreInContainer, nullptr, destination);
            const int after = countItems();
            if (after >= available) return;
            DepositLearning::RecordAutomaticTransfer(source, destination, item, available - after);
            count -= (std::min)(count, available - after);
            available = after;
        }
    }

    std::unordered_set<RE::FormID> SelectedAmmunition(RE::PlayerCharacter* player) {
        std::unordered_set<RE::FormID> selected;
        if (!player) return selected;
        if (auto* ammo = player->GetCurrentAmmo()) selected.insert(ammo->GetFormID());
        const auto* command = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
        const auto isEquipped = command ? command->conditionFunction : nullptr;
        for (const auto& [item, data] : player->GetInventory()) {
            if (!item || !data.second || !HasCategory(ClassifyItem(item), ItemCategory::Ammunition)) continue;
            double equipped{};
            if (data.second->IsFavorited() || data.second->IsWorn() ||
                (isEquipped && isEquipped(player, item, nullptr, equipped) && equipped != 0.0))
                selected.insert(item->GetFormID());
        }
        return selected;
    }

    using OpenState = RE::BGSOpenCloseForm::OPEN_STATE;

    struct OpenStatePoll
    {
        RE::ObjectRefHandle handle;
        OpenState desiredState;
        Stores::AnimationCallback callback;
        std::chrono::steady_clock::time_point deadline;
    };

    void PollForOpenState(std::shared_ptr<OpenStatePoll> a_poll)
    {
        // AddTask can drain tasks added by another task during the same frame. Delay
        // off-thread before returning to the game thread so animation frames advance.
        std::thread([a_poll = std::move(a_poll)]() mutable {
            std::this_thread::sleep_for(std::chrono::milliseconds(16));

            SKSE::GetTaskInterface()->AddTask([a_poll = std::move(a_poll)]() mutable {
                auto source = a_poll->handle.get();
                if (!source) {
                    logger::warn("Stopped waiting for storage animation because its reference is no longer available");
                    return;
                }

                if (RE::BGSOpenCloseForm::GetOpenState(source.get()) == a_poll->desiredState) {
                    if (a_poll->callback)
                        a_poll->callback(source.get());
                    return;
                }

                if (std::chrono::steady_clock::now() >= a_poll->deadline) {
                    logger::warn("Timed out waiting for storage animation on {:08X}", source->GetFormID());
                    // Do not leave activation permanently swallowed if a model does
                    // not expose a usable open/close state.
                    if (a_poll->callback)
                        a_poll->callback(source.get());
                    return;
                }

                PollForOpenState(std::move(a_poll));
            });
        }).detach();
    }

    void WaitForOpenState(RE::TESObjectREFR* a_source, OpenState a_state, Stores::AnimationCallback a_callback)
    {
        if (!a_callback)
            return;

        if (RE::BGSOpenCloseForm::GetOpenState(a_source) == a_state) {
            a_callback(a_source);
            return;
        }

        PollForOpenState(std::make_shared<OpenStatePoll>(
            a_source->GetHandle(),
            a_state,
            std::move(a_callback),
            std::chrono::steady_clock::now() + std::chrono::seconds(5)));
    }
}

using AVTranslation::Translate;

void Stores::ResetNavigation() {
    navigationSource_ = {};
    returnToVault_ = {};
}

void Stores::ShowDynamicMessageBox(std::string_view a_message, std::vector<MenuOption> a_options, std::int32_t a_cancelOption) {
    if (a_options.empty()) return;
    bool hasExit = false;
    bool hasBack = false;
    for (auto& option : a_options) {
        hasBack |= option.text == Translate("Vault.Back");
        if (option.text == Translate("Vault.Exit")) {
            hasExit = true;
            auto action = std::move(option.action);
            option.action = [this, action = std::move(action)] {
                ResetNavigation();
                if (action) action();
            };
        }
    }
    if (returnToVault_ && hasExit && !hasBack)
        a_options.push_back({Translate("Vault.Back"), returnToVault_});

    if (hasExit) {
        const auto rank = [](const MenuOption& option) {
            if (option.text == Translate("Vault.Exit")) return 3;
            if (option.text == Translate("Vault.Back")) return 2;
            for (const auto* key : {"Vault.Open", "Vault.OpenContainer", "Vault.KeysOpen", "Vault.AmmunitionOpen",
                                   "Vault.SoulgemsOpen", "Vault.ValuablesOpen", "Stolen.Open"})
                if (option.text == Translate(key)) return 0;
            return 1;
        };
        std::stable_sort(a_options.begin(), a_options.end(), [&](const auto& left, const auto& right) {
            return rank(left) < rank(right);
        });
        if (a_cancelOption >= 0) a_cancelOption = static_cast<std::int32_t>(a_options.size() - 1);
    }

    // Start the strings
    const auto* strings = RE::InterfaceStrings::GetSingleton();
    auto* factoryManager = RE::MessageDataFactoryManager::GetSingleton();
    if (!strings || !factoryManager) return;

    // Setup the message box
    const auto* creator = factoryManager->GetCreator<RE::MessageBoxData>(strings->messageBoxData);
    if (!creator) return;

    // Create the data
    auto* data = creator->Create();
    if (!data) return;

    // Prepare actions
    std::vector<MenuAction> actions;
    actions.reserve(a_options.size());

    // Create the body text
    data->bodyText = a_message.data();
    for (auto& option : a_options) {
        data->buttonText.emplace_back(option.text.c_str());
        actions.emplace_back(std::move(option.action));
    }

    // Set menu data
    data->callback = RE::BSTSmartPointer<RE::IMessageBoxCallback>(new MenuCallback(std::move(actions)));
    data->warningType = 0;
    data->cancelButtonIndex = a_cancelOption;
    data->menuDepth = 4;
    data->buttonPressOffset = 0;
    data->useHtml = true;
    data->verticalButtons = false;
    data->isCancellable = a_cancelOption >= 0;

    RE::MessageBoxMenu::QueueMessage(data);
}

//===================================================
// Storage Functions
//===================================================
void Stores::PlayerToStore(ItemCategory a_category, Container a_chest, int i_count, int a_keepCount, bool a_respectIgnores, CategoryMask a_excluded) {
    auto* utility = Utility::GetSingleton();
    auto* chest = utility->GetContainer(a_chest);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!player || !chest || i_count < 0 || a_keepCount < 0) return;

    const auto* equippedCommand = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
    const auto isEquipped = equippedCommand ? equippedCommand->conditionFunction : nullptr;
    const auto* currentAmmo = player->GetCurrentAmmo();
    std::optional<PlayerEquipment::Snapshot> equipment;
    const auto inventory = player->GetInventory();
    for (const auto& [item, data] : inventory) {
        if (!item || !data.second || data.first <= 0 || item->As<RE::TESSoulGem>()) continue;

        if (a_respectIgnores && Settings::GetSingleton()->IsIgnored(item)) continue;

        if (data.second->IsQuestObject() || data.second->IsFavorited()) continue;
        if (currentAmmo && item->GetFormID() == currentAmmo->GetFormID()) continue;

        const auto categories = ClassifyItem(item);
        if (!HasCategory(categories, a_category) || HasAnyCategory(categories, a_excluded)) continue;

        double equipped{};
        const bool formEquipped = isEquipped && isEquipped(player, item, nullptr, equipped) && equipped != 0.0;
        const auto read = [player, item] {
            return InventoryStacks::Read(player, [item](auto* candidate, auto&, auto*) { return candidate == item; });
        };
        auto stacks = read();
        if (stacks.empty()) continue;
        std::unordered_set<RE::ExtraDataList*> protectedStacks;
        if (formEquipped || data.second->IsWorn() || item->As<RE::TESObjectARMO>() || item->As<RE::TESObjectWEAP>()) {
            if (!equipment) equipment = PlayerEquipment::Read(player);
            const auto rows = equipment->find(item);
            if (rows != equipment->end()) protectedStacks = rows->second;
            if ((formEquipped || data.second->IsWorn()) && (rows == equipment->end() || protectedStacks.empty())) continue;
            stacks = read();
        }
        for (const auto& stack : stacks)
            if (stack.extra && (stack.extra->HasType<RE::ExtraWorn>() || stack.extra->HasType<RE::ExtraWornLeft>()))
                protectedStacks.insert(stack.extra);

        int count = InventoryStacks::Count(player, item) - a_keepCount;
        if (i_count > 0) count = std::min(count, i_count);
        while (count > 0) {
            stacks = read();
            const auto next = std::ranges::find_if(stacks, [&](const auto& stack) { return !protectedStacks.contains(stack.extra); });
            if (next == stacks.end()) break;
            auto stack = *next;
            stack.count = (std::min)(stack.count, count);
            // A null-list removal may choose an equipped explicit copy before the bare remainder.
            if (!stack.extra && !protectedStacks.empty()) {
                const auto physical = InventoryStacks::Materialize(stack);
                if (!physical) break;
                stack = *physical;
            }
            const int before = InventoryStacks::Count(player, item);
            if (!InventoryStacks::Move(stack, chest)) break;
            const int moved = before - InventoryStacks::Count(player, item);
            DepositLearning::RecordAutomaticTransfer(player, chest, item, moved);
            count -= moved;
        }
    }
}

void Stores::StoreToPlayer(ItemCategory a_category, Container a_chest, int i_count, std::optional<int> a_target) {
    auto* utility = Utility::GetSingleton();
    auto* chest = utility->GetContainer(a_chest);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!player || !chest || i_count < 0 || (a_target && *a_target <= 0)) return;

    const auto inventory = chest->GetInventory();
    for (const auto& [item, data] : inventory) {
        if (!item || data.first <= 0 || item->As<RE::TESSoulGem>()) continue;

        const auto categories = ClassifyItem(item);
        if (!HasCategory(categories, a_category)) continue;

        int count = i_count == 0 ? data.first : (std::min)(data.first, i_count);
        if (a_target) {
            const auto counts = player->GetInventoryCounts([item](RE::TESBoundObject& candidate) { return &candidate == item; });
            const auto found = counts.find(item);
            const int held = found == counts.end() ? 0 : (std::max)(0, found->second);
            count = (std::min)(count, (std::max)(0, *a_target - held));
        }
        MoveItems(chest, player, item, count);
    }
}

void Stores::StoreToStore(ItemCategory a_category, Container a_source, Container a_destination) {
    auto* utility = Utility::GetSingleton();
    auto* source = utility->GetContainer(a_source);
    auto* destination = utility->GetContainer(a_destination);
    if (!source || !destination) return;

    const auto inventory = source->GetInventory();
    for (const auto& [item, data] : inventory) {
        if (!item || data.first <= 0 || item->As<RE::TESSoulGem>()) continue;

        if (a_source == Container::Sort &&
            (sortFavorites_.contains(item->GetFormID()) || (data.second && data.second->IsFavorited()) ||
             (Settings::GetSingleton()->GSC_ReturnIgnoredItems && Settings::GetSingleton()->IsIgnored(item)))) continue;

        const auto categories = ClassifyItem(item);
        if (!HasCategory(categories, a_category)) continue;
        
        MoveItems(source, destination, item, data.first);
    }
}

void Stores::AllToStore(Container a_source, Container a_destination) {
    auto* utility = Utility::GetSingleton();
    auto* source = utility->GetContainer(a_source);
    auto* destination = utility->GetContainer(a_destination);
    if (!source || !destination || a_source == a_destination) return;

    if (a_source == Container::Sort) {
        for (const auto& [item, data] : source->GetInventory()) {
            if (item && data.first > 0 && !sortFavorites_.contains(item->GetFormID()) &&
                !(data.second && data.second->IsFavorited()) &&
                !(Settings::GetSingleton()->GSC_ReturnIgnoredItems && Settings::GetSingleton()->IsIgnored(item)))
                MoveItems(source, destination, item, data.first);
        }
        return;
    }
    auto* inventory = source->GetInventoryChanges();
    if (!inventory) return;

    inventory->RemoveAllItems(source, destination, false, false, false);
}

void Stores::AllToPlayer(Container a_source) {
    auto* utility = Utility::GetSingleton();
    auto* source = utility->GetContainer(a_source);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!source || !player) return;

    auto* inventory = source->GetInventoryChanges();
    if (!inventory) return;

    inventory->RemoveAllItems(source, player, false, false, false);
}

//===================================================
// Storage Animations
//===================================================
void Stores::OpenStorageMenu(Container a_chest, RE::TESObjectREFR* a_source, std::function<void(RE::TESObjectREFR*)> a_onClose) {
    if (!a_source || !a_onClose) return;

    auto* chest = Utility::GetSingleton()->GetContainer(a_chest);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!chest || !player) return;

    if (a_chest == Container::Sort) CaptureSortFavorites();

    const auto sourceHandle = a_source->GetHandle();
    auto returnToMenu = [sourceHandle, a_onClose = std::move(a_onClose)] {
        if (auto source = sourceHandle.get())
            a_onClose(source.get());
    };

    AVEvents::RunAfterContainerMenuCloses(chest, returnToMenu);

    if (!chest->ActivateRef(player, 0, nullptr, 1, false)) {
        AVEvents::CancelContainerMenuCloseCallback();
        returnToMenu();
    }
}

void Stores::OpenStoreObject(RE::TESObjectREFR* a_source, AnimationCallback a_onComplete) {
    if (!a_source) return;

    const auto openState = RE::BGSOpenCloseForm::GetOpenState(a_source);
    if (openState != RE::BGSOpenCloseForm::OPEN_STATE::kOpen && openState != RE::BGSOpenCloseForm::OPEN_STATE::kOpening) {
        RE::BGSOpenCloseForm::SetOpenState(a_source, true, false);
    }

    WaitForOpenState(a_source, RE::BGSOpenCloseForm::OPEN_STATE::kOpen, std::move(a_onComplete));
}

void Stores::CloseStoreObject(RE::TESObjectREFR* a_source, AnimationCallback a_onComplete) {
    if (!a_source) return;
    if (!a_onComplete && returnToVault_ &&
        navigationSource_.native_handle() == a_source->GetHandle().native_handle()) {
        const auto handle = navigationSource_;
        auto action = returnToVault_;
        SKSE::GetTaskInterface()->AddTask([this, handle, action = std::move(action)] {
            if (handle.get() && returnToVault_ && navigationSource_.native_handle() == handle.native_handle()) action();
        });
        return;
    }

    const auto openState = RE::BGSOpenCloseForm::GetOpenState(a_source);
    if (openState != RE::BGSOpenCloseForm::OPEN_STATE::kClosed &&
        openState != RE::BGSOpenCloseForm::OPEN_STATE::kClosing) {
        RE::BGSOpenCloseForm::SetOpenState(a_source, false, false);
    }

    WaitForOpenState(a_source, RE::BGSOpenCloseForm::OPEN_STATE::kClosed, std::move(a_onComplete));
}

//===================================================
// Sorting
//===================================================
void Stores::SortItems() {
    ConsolidateBooks();
    ConsolidatePotions();
    AllToStore(Container::Instruments, Container::Gear);
    const bool returnedFavorites = ReturnSortFavorites();
    ReturnIgnoredItems();
    Soulgems::Recover(sortFavorites_);
    // Sort all items in the sorting container
    StoreToStore(ItemCategory::Personal, Container::Sort, Container::Personal);
    StoreToStore(ItemCategory::Gear, Container::Sort, Container::Gear);
    StoreToStore(ItemCategory::Gold, Container::Sort, Container::Treasure);
    StoreToStore(ItemCategory::Ammunition, Container::Sort, Container::Ammunition);
    StoreToStore(ItemCategory::Keys, Container::Sort, Container::Keys);
    StoreToStore(ItemCategory::Smithing, Container::Sort, Container::Smithing);
    StoreToStore(ItemCategory::Food, Container::Sort, Container::Food);
    StoreToStore(ItemCategory::Alchemy, Container::Sort, Container::Alchemy);
    StoreToStore(ItemCategory::Scroll, Container::Sort, Container::Scroll);
    StoreToStore(ItemCategory::Note, Container::Sort, Container::Notes);
    StoreToStore(ItemCategory::Book, Container::Sort, Container::Book);
    StoreToStore(ItemCategory::Treasure, Container::Sort, Container::Treasure);
    StoreToStore(ItemCategory::Armor, Container::Sort, Container::Armor);
    StoreToStore(ItemCategory::Weapon, Container::Sort, Container::Weapon);
    StoreToStore(ItemCategory::Concoction, Container::Sort, Container::Concoction);
    AllToStore(Container::Sort, Container::Junk);
    RE::SendHUDMessage::ShowHUDMessage(Translate(returnedFavorites ? "Vault.FavoritesReturned" : "Vault.StoreAllMessage"));
}

void Stores::OffloadItems() {
    ConsolidateBooks();
    ConsolidatePotions();
    AllToStore(Container::Instruments, Container::Gear);
    auto* settings = Settings::GetSingleton();

    if (settings->GSC_OffloadGear) {
        PlayerToStore(ItemCategory::Lockpick, Container::Gear, 0, settings->GSC_LockpickKeepAmount, true);
        PlayerToStore(ItemCategory::Gear, Container::Gear, 0, 0, true, ToMask(ItemCategory::Lockpick));
    }

    if (settings->GSC_OffloadPersonal)
        PlayerToStore(ItemCategory::Personal, Container::Personal, 0, 0, true);

    if (settings->GSC_OffloadSoulgems) Soulgems::Deposit(settings->GSC_SoulgemKeepAmount, true);

    if (settings->GSC_OffloadGold)
        PlayerToStore(ItemCategory::Gold, Container::Treasure, 0, settings->GSC_GoldKeepAmount, true);

    if (settings->GSC_OffloadAmmunition)
        KeepAmmunition(true);

    if (settings->GSC_OffloadKeys)
        PlayerToStore(ItemCategory::Keys, Container::Keys, 0, settings->GSC_KeysKeepOne ? 1 : 0, true);

    // Alchemy
    if (settings->GSC_OffloadReagent) PlayerToStore(ItemCategory::Reagent, Container::Alchemy, 0, 0, true);
    if (settings->GSC_OffloadCatalyst) PlayerToStore(ItemCategory::Catalyst, Container::Alchemy, 0, 0, true);
    if (settings->GSC_OffloadIngredient) PlayerToStore(ItemCategory::Ingredient, Container::Alchemy, 0, 0, true);

    // Armor
    if (settings->GSC_OffloadClothing) PlayerToStore(ItemCategory::Clothing, Container::Armor, 0, 0, true);
    if (settings->GSC_OffloadHeavyArmor) PlayerToStore(ItemCategory::HeavyArmor, Container::Armor, 0, 0, true);
    if (settings->GSC_OffloadLightArmor) PlayerToStore(ItemCategory::LightArmor, Container::Armor, 0, 0, true);
    if (settings->GSC_OffloadJewelry) PlayerToStore(ItemCategory::Jewelry, Container::Armor, 0, 0, true);

    if (settings->GSC_OffloadNotes) PlayerToStore(ItemCategory::Note, Container::Notes, 0, 0, true);

    // Books
    if (settings->GSC_OffloadBooks) PlayerToStore(ItemCategory::Book, Container::Book, 0, 0, true);
    if (settings->GSC_OffloadSpelltomes) PlayerToStore(ItemCategory::SpellTome, Container::Book, 0, 0, true);
    if (settings->GSC_OffloadScrolls) PlayerToStore(ItemCategory::Scroll, Container::Scroll, 0, 0, true);

    // Smithing
    if (settings->GSC_OffloadCrafting) PlayerToStore(ItemCategory::Crafting, Container::Smithing, 0, 0, true);
    if (settings->GSC_OffloadConstruction) PlayerToStore(ItemCategory::Construction, Container::Smithing, 0, 0, true);
    if (settings->GSC_OffloadGemstone) PlayerToStore(ItemCategory::Gemstone, Container::Smithing, 0, 0, true);
    if (settings->GSC_OffloadSmelting) PlayerToStore(ItemCategory::Smelting, Container::Smithing, 0, 0, true);
    if (settings->GSC_OffloadTanning) PlayerToStore(ItemCategory::Tanning, Container::Smithing, 0, 0, true);

    // Concoction
    if (settings->GSC_OffloadPotion) PlayerToStore(ItemCategory::Potion, Container::Concoction, 0, 0, true);
    if (settings->GSC_OffloadPoison) PlayerToStore(ItemCategory::Poison, Container::Concoction, 0, 0, true);

    // Food
    if (settings->GSC_OffloadCookedFood) PlayerToStore(ItemCategory::CookedFood, Container::Food, 0, 0, true);
    if (settings->GSC_OffloadRawFood) PlayerToStore(ItemCategory::RawFood, Container::Food, 0, 0, true);

    // Treasure
    if (settings->GSC_OffloadTreasure) PlayerToStore(ItemCategory::Treasure, Container::Treasure, 0, 0, true);

    // Weapons
    if (settings->GSC_OffloadArchery) PlayerToStore(ItemCategory::Archery, Container::Weapon, 0, 0, true);
    if (settings->GSC_OffloadOneHand) PlayerToStore(ItemCategory::OneHand, Container::Weapon, 0, 0, true);
    if (settings->GSC_OffloadTwoHand) PlayerToStore(ItemCategory::TwoHand, Container::Weapon, 0, 0, true);
    if (settings->GSC_OffloadStaffHand) PlayerToStore(ItemCategory::Staff, Container::Weapon, 0, 0, true);

    // Broad overrides have no subtype checkbox of their own.
    if (settings->GSC_OffloadReagent || settings->GSC_OffloadCatalyst || settings->GSC_OffloadIngredient)
        PlayerToStore(ItemCategory::Alchemy, Container::Alchemy, 0, 0, true, ItemCategory::Reagent | ItemCategory::Catalyst | ItemCategory::Ingredient);
    if (settings->GSC_OffloadClothing || settings->GSC_OffloadHeavyArmor || settings->GSC_OffloadLightArmor || settings->GSC_OffloadJewelry)
        PlayerToStore(ItemCategory::Armor, Container::Armor, 0, 0, true, ItemCategory::Clothing | ItemCategory::HeavyArmor | ItemCategory::LightArmor | ItemCategory::Jewelry);
    if (settings->GSC_OffloadArchery || settings->GSC_OffloadOneHand || settings->GSC_OffloadTwoHand || settings->GSC_OffloadStaffHand)
        PlayerToStore(ItemCategory::Weapon, Container::Weapon, 0, 0, true, ItemCategory::Archery | ItemCategory::OneHand | ItemCategory::TwoHand | ItemCategory::Staff);
    if (settings->GSC_OffloadCrafting || settings->GSC_OffloadConstruction || settings->GSC_OffloadGemstone || settings->GSC_OffloadSmelting || settings->GSC_OffloadTanning)
        PlayerToStore(ItemCategory::Smithing, Container::Smithing, 0, 0, true, ItemCategory::Crafting | ItemCategory::Construction | ItemCategory::Gemstone | ItemCategory::Smelting | ItemCategory::Tanning | ItemCategory::PreciousIngot);
    if (settings->GSC_OffloadCookedFood || settings->GSC_OffloadRawFood)
        PlayerToStore(ItemCategory::Food, Container::Food, 0, 0, true, ItemCategory::CookedFood | ItemCategory::RawFood);
    if (settings->GSC_OffloadPotion || settings->GSC_OffloadPoison)
        PlayerToStore(ItemCategory::Concoction, Container::Concoction, 0, 0, true, ItemCategory::Potion | ItemCategory::Poison | ItemCategory::Restorative);

    // Final Message
    RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
}

//===================================================
// Vault Menu
//===================================================
void Stores::VaultMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ResetNavigation();
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowVaultMenu(a_openSource); });
}

void Stores::ShowVaultMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.ArcaneOffload"), [this, sourceHandle] {
        OffloadItems();
        if (auto source = sourceHandle.get()) VaultMenu(source.get());
    }});

    options.push_back({Translate("Vault.ArcaneSort"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Sort, source.get(), [this](RE::TESObjectREFR* a_source) {
                SortItems();
                VaultMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.ArcaneVaults"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) VaultDetail1Menu(source.get());
    }});

    options.push_back({Translate("Vault.ArcaneArchives"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) ShowVaultArchivesMenu(source.get());
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Arcane"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::VaultDetail1Menu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowVaultDetail1Menu(a_openSource); });
}

void Stores::ShowVaultDetail1Menu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    navigationSource_ = sourceHandle;
    returnToVault_ = [this, sourceHandle] {
        if (auto source = sourceHandle.get()) VaultDetail1Menu(source.get());
    };
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.Smithing"), [this, sourceHandle] {
        AllToStore(Container::Crafting, Container::Smithing);
        AllToStore(Container::Smelting, Container::Smithing);
        AllToStore(Container::Tanning, Container::Smithing);
        AllToStore(Container::Construction, Container::Smithing);
        
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Smithing, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail1Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Alchemy"), [this, sourceHandle] {
        AllToStore(Container::Reagent, Container::Alchemy);
        
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Alchemy, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail1Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Armor"), [this, sourceHandle] {
        AllToStore(Container::HeavyArmor, Container::Armor);
        AllToStore(Container::LightArmor, Container::Armor);
        AllToStore(Container::Jewelry, Container::Armor);
        AllToStore(Container::Clothing, Container::Armor);
        
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Armor, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail1Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Weapon"), [this, sourceHandle] {
        AllToStore(Container::Archery, Container::Weapon);
        AllToStore(Container::OneHand, Container::Weapon);
        AllToStore(Container::TwoHand, Container::Weapon);
        AllToStore(Container::Staff, Container::Weapon);
        
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Weapon, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail1Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Concoction"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Concoction, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail1Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Food"), [this, sourceHandle] {
        AllToStore(Container::RawFood, Container::Food);
        AllToStore(Container::CookedFood, Container::Food);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Food, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail1Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.More"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) VaultDetail2Menu(source.get());
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Arcane"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::VaultDetail2Menu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowVaultDetail2Menu(a_openSource); });
}

void Stores::ShowVaultDetail2Menu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    navigationSource_ = sourceHandle;
    returnToVault_ = [this, sourceHandle] {
        if (auto source = sourceHandle.get()) VaultDetail2Menu(source.get());
    };
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.Ammunition"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) AmmunitionMenu(source.get());
    }});

    options.push_back({Translate("Vault.Keys"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) KeysMenu(source.get());
    }});

    options.push_back({Translate("Vault.Book"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) BookMenu(source.get());
    }});

    options.push_back({Translate("Vault.Notes"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) NotesMenu(source.get());
    }});

    options.push_back({Translate("Vault.Scroll"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Scroll, source.get(), [this](RE::TESObjectREFR* a_source) {
                ShowVaultDetail2Menu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Soulgem"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) SoulgemMenu(source.get());
    }});

    options.push_back({Translate("Vault.Treasure"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) TreasureMenu(source.get());
    }});

    options.push_back({Translate("Vault.More"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) VaultDetail3Menu(source.get());
    }});

    options.push_back({Translate("Vault.Back"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) VaultDetail1Menu(source.get());
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Arcane"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

//===================================================
// Vault Assignment
//===================================================
void Stores::VaultAssignment(RE::TESObjectREFRPtr a_source) {
    if (!a_source) return;
    ResetNavigation();
    auto* utility = Utility::GetSingleton();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.AssignArcane"), [utility, a_source] {
        auto* source = a_source.get();
        auto* destination = utility->GetContainer(Container::Master);
        if (destination && destination != source) RedirectManager::GetSingleton()->Add(source, destination);
    }});

    options.push_back({Translate("Vault.AssignSort"), [utility, a_source] {
        auto* source = a_source.get();
        auto* destination = utility->GetContainer(Container::Sort);
        if (destination && destination != source) RedirectManager::GetSingleton()->Add(source, destination);
    }});

    options.push_back({Translate("Vault.AssignVault"), [this, a_source] {
        auto choices = Utility::GetSingleton()->GetVaultChoices();
        choices.insert(choices.begin(), Utility::ContainerChoice{
            .name = std::format("[{}]", Translate("Vault.Back")),
            .action = [this, a_source] {
                SKSE::GetTaskInterface()->AddTask([this, a_source] { VaultAssignment(a_source); });
            }
        });
        choices.insert(choices.begin() + 1, Utility::ContainerChoice{
            .name = std::format("[{}]", Translate("Vault.Exit")),
            .action = [] {}
        });
        ContainerSelectionState::GetSingleton()->Begin(std::move(a_source), std::move(choices));
        RE::UIMessageQueue::GetSingleton()->AddMessage(ContainerListMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kShow, nullptr);
    }});

    options.push_back({Translate("Vault.AssignArchive"), [this, a_source] {
        auto choices = Utility::GetSingleton()->GetArchiveChoices();
        choices.insert(choices.begin(), Utility::ContainerChoice{
            .name = std::format("[{}]", Translate("Vault.Back")),
            .action = [this, a_source] {
                SKSE::GetTaskInterface()->AddTask([this, a_source] { VaultAssignment(a_source); });
            }
        });
        choices.insert(choices.begin() + 1, Utility::ContainerChoice{
            .name = std::format("[{}]", Translate("Vault.Exit")),
            .action = [] {}
        });
        ContainerSelectionState::GetSingleton()->Begin(std::move(a_source), std::move(choices));
        RE::UIMessageQueue::GetSingleton()->AddMessage(ContainerListMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kShow, nullptr);
    }});

    options.push_back({Translate("Vault.AssignRemove"), [this, a_source] {
        auto* source = a_source.get();
        if (source) RedirectManager::GetSingleton()->Remove(source);
    }});

    options.push_back({Translate("Vault.Exit"), [] { }});

    const auto title = std::format("{} {}",Translate("Vault.Arcane"),Translate("Vault.Assign"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

//===================================================
// Auto Sort Menu
//===================================================
void Stores::SortingMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSortingMenu(a_openSource); });
}

void Stores::ShowSortingMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Sort, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            SortItems();
    });
}

// Keys menu
void Stores::KeysMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowKeysMenu(source); });
}

void Stores::ShowKeysMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.KeepOne"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Keys, Container::Keys, 0, 1);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreMostMessage"));
        if (auto source = sourceHandle.get()) KeysMenu(source.get());
    }});

    options.push_back({Translate("Vault.KeysStoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Keys, Container::Keys);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) KeysMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), 1), [this, sourceHandle] {
        StoreToPlayer(ItemCategory::Keys, Container::Keys, 0, 1);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) KeysMenu(source.get());
    }});

    options.push_back({Translate("Vault.KeysTakeAll"), [this, sourceHandle] {
        AllToPlayer(Container::Keys);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) KeysMenu(source.get());
    }});

    options.push_back({Translate("Vault.KeysOpen"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Keys, source.get(), [this](RE::TESObjectREFR* source) {
                KeysMenu(source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}", Translate("Vault.Keys"), Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::AmmunitionMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowAmmunitionMenu(source); });
}

void Stores::ShowAmmunitionMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({std::format("{} {}", Translate("Vault.KeepAmount"), Settings::GetSingleton()->GSC_AmmunitionKeepAmount), [this, sourceHandle] {
        KeepAmmunition();
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreMostMessage"));
        if (auto source = sourceHandle.get()) AmmunitionMenu(source.get());
    }});

    options.push_back({Translate("Vault.AmmunitionStoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Ammunition, Container::Ammunition);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) AmmunitionMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), Settings::GetSingleton()->GSC_AmmunitionKeepAmount), [this, sourceHandle] {
        TakeAmmunition();
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) AmmunitionMenu(source.get());
    }});

    options.push_back({Translate("Vault.AmmunitionTakeAll"), [this, sourceHandle] {
        AllToPlayer(Container::Ammunition);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) AmmunitionMenu(source.get());
    }});

    options.push_back({Translate("Vault.AmmunitionOpen"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Ammunition, source.get(), [this](RE::TESObjectREFR* source) {
                AmmunitionMenu(source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}", Translate("Vault.Ammunition"), Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

// Alchemy menu
void Stores::AlchemyMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowAlchemyMenu(a_openSource); });
}

void Stores::ShowAlchemyMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;
    const int keepAmount = Settings::GetSingleton()->GSC_AlchemyKeepAmount;

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Alchemy, Container::Alchemy);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) AlchemyMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.KeepAmount"), keepAmount), [this, sourceHandle, keepAmount] {
        PlayerToStore(ItemCategory::Alchemy, Container::Alchemy, 0, keepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreMostMessage"));
        if (auto source = sourceHandle.get()) AlchemyMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), keepAmount), [this, sourceHandle, keepAmount] {
        StoreToPlayer(ItemCategory::Alchemy, Container::Alchemy, 0, keepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) AlchemyMenu(source.get());
    }});

    options.push_back({Translate("Vault.GatherFood"), [this, sourceHandle] {
        StoreToPlayer(ItemCategory::Reagent, Container::Alchemy);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) AlchemyMenu(source.get());
    }});

    options.push_back({Translate("Vault.GatherSmithing"), [this, sourceHandle] {
        StoreToPlayer(ItemCategory::Catalyst, Container::Alchemy);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) AlchemyMenu(source.get());
    }});

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        AllToStore(Container::Reagent, Container::Alchemy);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Alchemy, source.get(), [this](RE::TESObjectREFR* a_source) {
                AlchemyMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Alchemy"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

//===================================================
// *Alchemy Menus
//===================================================
void Stores::SoulgemMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSoulgemMenu(a_openSource); });
}

void Stores::ShowSoulgemMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    Soulgems::Recover();
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;
    options.push_back({std::format("{} {} {}", Translate("Vault.KeepAmount"), Settings::GetSingleton()->GSC_SoulgemKeepAmount, Translate("Vault.Empty")), [this, sourceHandle] {
        Soulgems::Deposit(Settings::GetSingleton()->GSC_SoulgemKeepAmount);
        if (auto source = sourceHandle.get()) SoulgemMenu(source.get());
    }});
    options.push_back({Translate("Vault.SoulgemsStoreAll"), [this, sourceHandle] {
        Soulgems::Deposit(0);
        if (auto source = sourceHandle.get()) SoulgemMenu(source.get());
    }});
    options.push_back({Translate("Vault.FilledSoulgems"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) FilledSoulgemsMenu(source.get());
    }});
    options.push_back({Translate("Vault.EmptySoulgems"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) EmptySoulgemsMenu(source.get());
    }});
    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Soulgem, source.get(), [this](RE::TESObjectREFR* source) { SoulgemMenu(source); });
    }});
    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});
    const auto title = std::format("{} {}", Translate("Vault.Soulgem"), Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::FilledSoulgemsMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    Soulgems::Recover();
    Soulgems::Split();
    OpenStorageMenu(Container::FilledSoulgems, a_source, [this](RE::TESObjectREFR* source) {
        Soulgems::Consolidate();
        CloseStoreObject(source);
    });
}

void Stores::EmptySoulgemsMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    Soulgems::Recover();
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;
    const int takeAmount = Settings::GetSingleton()->GSC_SoulgemKeepAmount;
    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), takeAmount), [this, sourceHandle, takeAmount] {
        Soulgems::TakeEmpty(takeAmount);
        if (auto source = sourceHandle.get()) EmptySoulgemsMenu(source.get());
    }});
    options.push_back({Translate("Vault.TakeAllEmptySoulgems"), [this, sourceHandle] {
        Soulgems::TakeEmpty();
        if (auto source = sourceHandle.get()) EmptySoulgemsMenu(source.get());
    }});
    options.push_back({Translate("Vault.SoulgemsOpen"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) {
            Soulgems::Split();
            OpenStorageMenu(Container::EmptySoulgems, source.get(), [this](RE::TESObjectREFR* source) {
                Soulgems::Consolidate();
                EmptySoulgemsMenu(source);
            });
        }
    }});
    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});
    const auto title = std::format("{} {}", Translate("Vault.EmptySoulgems"), Translate("Vault.Archive"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

//===================================================
// *Potion Menus
//===================================================
void Stores::PotionMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowPotionMenu(a_openSource); });
}

void Stores::ShowPotionMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ConsolidatePotions();
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Concoction, Container::Concoction);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) PotionMenu(source.get());
    }});

    options.push_back({Translate("Vault.Potion"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Potion, Container::Concoction, Container::Potion);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Potion, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Potion, Container::Concoction);
                PotionMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Poison"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Poison, Container::Concoction, Container::Poison);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Poison, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Poison, Container::Concoction);
                PotionMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Restoritive"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Restorative, Container::Concoction, Container::Restorative);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Restorative, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Restorative, Container::Concoction);
                PotionMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        AllToStore(Container::Potion, Container::Concoction);
        AllToStore(Container::Poison, Container::Concoction);
        AllToStore(Container::Restorative, Container::Concoction);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Concoction, source.get(), [this](RE::TESObjectREFR* a_source) {
                PotionMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Concoction"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::PotionPositiveMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowPotionPositiveMenu(a_openSource); });
}

void Stores::ShowPotionPositiveMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ConsolidatePotions();
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Potion, Container::Concoction, Container::Potion);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Potion, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Potion, Container::Concoction);
    });
}

void Stores::PotionNegativeMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowPotionNegativeMenu(a_openSource); });
}

void Stores::ShowPotionNegativeMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ConsolidatePotions();
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Poison, Container::Concoction, Container::Poison);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Poison, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Poison, Container::Concoction);
    });
}

void Stores::PotionRestoreMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowPotionRestoreMenu(a_openSource); });
}

void Stores::ShowPotionRestoreMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ConsolidatePotions();
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Restorative, Container::Concoction, Container::Restorative);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Restorative, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Restorative, Container::Concoction);
    });
}

//===================================================
// *Book Menus
//===================================================
void Stores::BookMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ConsolidateBooks();
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowBookMenu(a_openSource); });
}

void Stores::ShowBookMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Book, Container::Book);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) BookMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), 1), [this, sourceHandle] {
        StoreToPlayer(ItemCategory::Book, Container::Book, 0, 1);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) BookMenu(source.get());
    }});

    options.push_back({Translate("Vault.SpellTomes"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenBookArchive(Container::SpellTomes, Container::Book, ItemCategory::SpellTome, source.get(), true);
    }});

    options.push_back({Translate("Vault.SkillBooks"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenBookArchive(Container::SkillBooks, Container::Book, ItemCategory::SkillBook, source.get(), true);
    }});

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Book, source.get(), [this](RE::TESObjectREFR* a_source) {
                BookMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Book"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::ScrollMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowScrollMenu(a_openSource); });
}

void Stores::ShowScrollMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;
    const int keepAmount = Settings::GetSingleton()->GSC_ScrollKeepAmount;

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Scroll, Container::Scroll);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) ScrollMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.KeepAmount"), keepAmount), [this, sourceHandle, keepAmount] {
        PlayerToStore(ItemCategory::Scroll, Container::Scroll, 0, keepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreMostMessage"));
        if (auto source = sourceHandle.get()) ScrollMenu(source.get());
    }});

    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), keepAmount), [this, sourceHandle, keepAmount] {
        StoreToPlayer(ItemCategory::Scroll, Container::Scroll, 0, keepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) ScrollMenu(source.get());
    }});

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Scroll, source.get(), [this](RE::TESObjectREFR* a_source) {
                ScrollMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Scroll"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

//===================================================
// *Smith Menus
//===================================================
void Stores::SmithMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSmithMenu(a_openSource); });
}

void Stores::ShowSmithMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Smithing, Container::Smithing);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) SmithMenu(source.get());
    }});

    options.push_back({Translate("Vault.Crafting"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Crafting, Container::Smithing, Container::Crafting);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Crafting, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Crafting, Container::Smithing);
                SmithMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Smelting"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Smelting, Container::Smithing, Container::Smelting);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Smelting, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Smelting, Container::Smithing);
                SmithMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Tanning"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Tanning, Container::Smithing, Container::Tanning);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Tanning, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Tanning, Container::Smithing);
                SmithMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Construction"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Construction, Container::Smithing, Container::Construction);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Construction, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Construction, Container::Smithing);
                SmithMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Gemstones"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Gemstone, Container::Smithing, Container::Gemstone);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Gemstone, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Gemstone, Container::Smithing);
                SmithMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        AllToStore(Container::Construction, Container::Smithing);
        AllToStore(Container::Crafting, Container::Smithing);
        AllToStore(Container::Smelting, Container::Smithing);
        AllToStore(Container::Tanning, Container::Smithing);
        AllToStore(Container::Gemstone, Container::Smithing);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Smithing, source.get(), [this](RE::TESObjectREFR* a_source) {
                SmithMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Smithing"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::SmithCraftMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSmithCraftMenu(a_openSource); });
}

void Stores::ShowSmithCraftMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Crafting, Container::Smithing, Container::Crafting);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Crafting, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Crafting, Container::Smithing);
    });
}

void Stores::SmithSmeltMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSmithSmeltMenu(a_openSource); });
}

void Stores::ShowSmithSmeltMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Smelting, Container::Smithing, Container::Smelting);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Smelting, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Smelting, Container::Smithing);
    });
}

void Stores::SmithTanMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSmithTanMenu(a_openSource); });
}

void Stores::ShowSmithTanMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Tanning, Container::Smithing, Container::Tanning);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Tanning, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Tanning, Container::Smithing);
    });
}

void Stores::SmithConstructMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowSmithConstructMenu(a_openSource); });
}

void Stores::ShowSmithConstructMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Construction, Container::Smithing, Container::Construction);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Construction, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Construction, Container::Smithing);
    });
}

void Stores::GemstoneMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowGemstoneMenu(a_openSource); });
}

void Stores::ShowGemstoneMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Gemstone, Container::Smithing, Container::Gemstone);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Gemstone, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Gemstone, Container::Smithing);
    });
}

//===================================================
// *Food Menus
//===================================================
void Stores::FoodMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowFoodMenu(a_openSource); });
}

void Stores::ShowFoodMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Food, Container::Food);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) FoodMenu(source.get());
    }});

    options.push_back({Translate("Vault.StoreRaw"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::RawFood, Container::Food);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) FoodMenu(source.get());
    }});

    options.push_back({Translate("Vault.Cooked"), [this, sourceHandle] {
        StoreToStore(ItemCategory::CookedFood, Container::Food, Container::CookedFood);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::CookedFood, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::CookedFood, Container::Food);
                FoodMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Raw"), [this, sourceHandle] {
        StoreToStore(ItemCategory::RawFood, Container::Food, Container::RawFood);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::RawFood, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::RawFood, Container::Food);
                FoodMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Spice"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Reagent, Container::Alchemy, Container::Reagent);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::RawFood, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Reagent, Container::Alchemy);
                FoodMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        AllToStore(Container::RawFood, Container::Food);
        AllToStore(Container::CookedFood, Container::Food);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Food, source.get(), [this](RE::TESObjectREFR* a_source) {
                FoodMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Food"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::FoodCookedMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowFoodCookedMenu(a_openSource); });
}

void Stores::ShowFoodCookedMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::CookedFood, Container::Food, Container::CookedFood);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::CookedFood, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::CookedFood, Container::Food);
    });
}

void Stores::FoodRawMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowFoodRawMenu(a_openSource); });
}

void Stores::ShowFoodRawMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::RawFood, Container::Food, Container::RawFood);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::RawFood, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::RawFood, Container::Food);
    });
}

void Stores::FoodSaltMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowFoodSaltMenu(a_openSource); });
}

void Stores::ShowFoodSaltMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Reagent, Container::Alchemy, Container::Reagent);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Reagent, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Reagent, Container::Alchemy);
    });
}

//===================================================
// *Armor Menus
//===================================================
void Stores::ArmorMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowArmorMenu(a_openSource); });
}

void Stores::ShowArmorMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        for (auto child : {Container::HeavyArmor, Container::LightArmor, Container::Clothing, Container::Jewelry})
            AllToStore(child, Container::Armor);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Armor, source.get(), [this](RE::TESObjectREFR* closed) { ArmorMenu(closed); });
    }});

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::HeavyArmor, Container::Armor);
        PlayerToStore(ItemCategory::LightArmor, Container::Armor);
        PlayerToStore(ItemCategory::Clothing, Container::Armor);
        PlayerToStore(ItemCategory::Jewelry, Container::Armor);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) ArmorMenu(source.get());
    }});

    options.push_back({Translate("Vault.HeavyArmor"), [this, sourceHandle] {
        StoreToStore(ItemCategory::HeavyArmor, Container::Armor, Container::HeavyArmor);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::HeavyArmor, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::HeavyArmor, Container::Armor);
                ArmorMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.LightArmor"), [this, sourceHandle] {
        StoreToStore(ItemCategory::LightArmor, Container::Armor, Container::LightArmor);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::LightArmor, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::LightArmor, Container::Armor);
                ArmorMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Clothing"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Clothing, Container::Armor, Container::Clothing);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Clothing, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Clothing, Container::Armor);
                ArmorMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Jewelry"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Jewelry, Container::Armor, Container::Jewelry);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Jewelry, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Jewelry, Container::Armor);
                ArmorMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Unclassified"), [this, sourceHandle] {
        AllToStore(Container::HeavyArmor, Container::Armor);
        AllToStore(Container::LightArmor, Container::Armor);
        AllToStore(Container::Jewelry, Container::Armor);
        AllToStore(Container::Clothing, Container::Armor);

        StoreToStore(ItemCategory::HeavyArmor, Container::Armor, Container::HeavyArmor);
        StoreToStore(ItemCategory::LightArmor, Container::Armor, Container::LightArmor);
        StoreToStore(ItemCategory::Clothing, Container::Armor, Container::Clothing);
        StoreToStore(ItemCategory::Jewelry, Container::Armor, Container::Jewelry);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Armor, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::HeavyArmor, Container::Armor);
                AllToStore(Container::LightArmor, Container::Armor);
                AllToStore(Container::Jewelry, Container::Armor);
                AllToStore(Container::Clothing, Container::Armor);
                ArmorMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Armor"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::ArmorLightMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowArmorLightMenu(a_openSource); });
}

void Stores::ShowArmorLightMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::LightArmor, Container::Armor, Container::LightArmor);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::LightArmor, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::LightArmor, Container::Armor);
    });
}

void Stores::ArmorHeavyMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowArmorHeavyMenu(a_openSource); });
}

void Stores::ShowArmorHeavyMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::HeavyArmor, Container::Armor, Container::HeavyArmor);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::HeavyArmor, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::HeavyArmor, Container::Armor);
    });
}

void Stores::ArmorJewelryMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowArmorJewelryMenu(a_openSource); });
}

void Stores::ShowArmorJewelryMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Jewelry, Container::Armor, Container::Jewelry);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Jewelry, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Jewelry, Container::Armor);
    });
}

void Stores::ArmorClothingMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowArmorClothingMenu(a_openSource); });
}

void Stores::ShowArmorClothingMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Clothing, Container::Armor, Container::Clothing);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Clothing, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Clothing, Container::Armor);
    });
}

//===================================================
// *Weapons Menus
//===================================================
void Stores::WeaponMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowWeaponMenu(a_openSource); });
}

void Stores::ShowWeaponMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        for (auto child : {Container::Archery, Container::OneHand, Container::TwoHand, Container::Staff})
            AllToStore(child, Container::Weapon);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Weapon, source.get(), [this](RE::TESObjectREFR* closed) { WeaponMenu(closed); });
    }});

    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Archery, Container::Weapon);
        PlayerToStore(ItemCategory::OneHand, Container::Weapon);
        PlayerToStore(ItemCategory::TwoHand, Container::Weapon);
        PlayerToStore(ItemCategory::Staff, Container::Weapon);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) WeaponMenu(source.get());
    }});

    options.push_back({Translate("Vault.OneHand"), [this, sourceHandle] {
        StoreToStore(ItemCategory::OneHand, Container::Weapon, Container::OneHand);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::OneHand, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::OneHand, Container::Weapon);
                WeaponMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.TwoHand"), [this, sourceHandle] {
        StoreToStore(ItemCategory::TwoHand, Container::Weapon, Container::TwoHand);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::TwoHand, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::TwoHand, Container::Weapon);
                WeaponMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Archery"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Archery, Container::Weapon, Container::Archery);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Archery, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Archery, Container::Weapon);
                WeaponMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Staff"), [this, sourceHandle] {
        StoreToStore(ItemCategory::Staff, Container::Weapon, Container::Staff);
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Staff, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Staff, Container::Weapon);
                WeaponMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Unclassified"), [this, sourceHandle] {
        AllToStore(Container::Archery, Container::Weapon);
        AllToStore(Container::OneHand, Container::Weapon);
        AllToStore(Container::TwoHand, Container::Weapon);
        AllToStore(Container::Staff, Container::Weapon);

        StoreToStore(ItemCategory::Archery, Container::Weapon, Container::Archery);
        StoreToStore(ItemCategory::OneHand, Container::Weapon, Container::OneHand);
        StoreToStore(ItemCategory::Staff, Container::Weapon, Container::Staff);
        StoreToStore(ItemCategory::TwoHand, Container::Weapon, Container::TwoHand);

        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Weapon, source.get(), [this](RE::TESObjectREFR* a_source) {
                AllToStore(Container::Archery, Container::Weapon);
                AllToStore(Container::OneHand, Container::Weapon);
                AllToStore(Container::TwoHand, Container::Weapon);
                AllToStore(Container::Staff, Container::Weapon);
                WeaponMenu(a_source);
            });
    }});

    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});

    const auto title = std::format("{} {}",Translate("Vault.Weapon"),Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::WeaponArcheryMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowWeaponArcheryMenu(a_openSource); });
}

void Stores::ShowWeaponArcheryMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Archery, Container::Weapon, Container::Archery);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Archery, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Archery, Container::Weapon);
    });
}

void Stores::WeaponOneHandMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowWeaponOneHandMenu(a_openSource); });
}

void Stores::ShowWeaponOneHandMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::OneHand, Container::Weapon, Container::OneHand);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::OneHand, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::OneHand, Container::Weapon);
    });
}

void Stores::WeaponTwoHandMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowWeaponTwoHandMenu(a_openSource); });
}

void Stores::ShowWeaponTwoHandMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::TwoHand, Container::Weapon, Container::TwoHand);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::TwoHand, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::TwoHand, Container::Weapon);
    });
}

void Stores::WeaponStaffMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowWeaponStaffMenu(a_openSource); });
}

void Stores::ShowWeaponStaffMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Transfer Items
    StoreToStore(ItemCategory::Staff, Container::Weapon, Container::Staff);

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Staff, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
            AllToStore(Container::Staff, Container::Weapon);
    });
}

//===================================================
// *Misc Menus
//===================================================
void Stores::TreasureMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowTreasureMenu(a_openSource); });
}

void Stores::ShowTreasureMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Treasure, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
    });
}

void Stores::ReturnValuables() {
    auto* utility = Utility::GetSingleton();
    if (!utility->GetContainer(Container::Treasure) || !utility->GetContainer(Container::Smithing) ||
        !utility->GetContainer(Container::Armor)) return;

    StoreToStore(ItemCategory::Gemstone, Container::Valuables, Container::Smithing);
    StoreToStore(ItemCategory::PreciousIngot, Container::Valuables, Container::Smithing);
    StoreToStore(ItemCategory::Jewelry, Container::Valuables, Container::Armor);
    AllToStore(Container::Valuables, Container::Treasure);
}

void Stores::ValuablesMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowValuablesMenu(source); });
}

void Stores::ShowValuablesMenu(RE::TESObjectREFR* a_source) {
    auto* utility = Utility::GetSingleton();
    if (!a_source || !utility->GetContainer(Container::Valuables) ||
        !utility->GetContainer(Container::Treasure) || !utility->GetContainer(Container::Smithing) ||
        !utility->GetContainer(Container::Armor)) return;
    ReturnValuables();
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;

    options.push_back({Translate("Vault.ValuablesOpen"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) {
            if (!RE::PlayerCharacter::GetSingleton()) return;
            StoreToStore(ItemCategory::Gold, Container::Treasure, Container::Valuables);
            StoreToStore(ItemCategory::Gemstone, Container::Smithing, Container::Valuables);
            StoreToStore(ItemCategory::PreciousIngot, Container::Smithing, Container::Valuables);
            StoreToStore(ItemCategory::Jewelry, Container::Armor, Container::Valuables);
            OpenStorageMenu(Container::Valuables, source.get(), [this](RE::TESObjectREFR* source) {
                ReturnValuables();
                ValuablesMenu(source);
            });
        }
    }});
    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});
    options.push_back({std::format("{} {} {}", Translate("Vault.KeepAmount"),
        Settings::GetSingleton()->GSC_GoldKeepAmount, Translate("Vault.Septims")), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Gold, Container::Treasure, 0, Settings::GetSingleton()->GSC_GoldKeepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreMostMessage"));
        if (auto source = sourceHandle.get()) ValuablesMenu(source.get());
    }});
    options.push_back({Translate("Vault.StoreAllSeptims"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Gold, Container::Treasure);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) ValuablesMenu(source.get());
    }});
    options.push_back({Translate("Vault.TakeAllSeptims"), [this, sourceHandle] {
        StoreToPlayer(ItemCategory::Gold, Container::Treasure);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) ValuablesMenu(source.get());
    }});

    const auto title = std::format("{} {}", Translate("Vault.Valuables"), Translate("Vault.Archive"));
    const auto cancelIndex = 1;
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::ShowVaultArchivesMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    auto* queue = RE::UIMessageQueue::GetSingleton();
    if (!queue) return;
    const auto handle = a_source->GetHandle();
    navigationSource_ = handle;
    returnToVault_ = [this, handle] {
        if (auto source = handle.get()) ShowVaultArchivesMenu(source.get());
    };
    auto choices = Utility::GetSingleton()->GetArchiveChoices(a_source);
    auto back = [this, handle] {
        if (auto source = handle.get()) VaultMenu(source.get());
    };
    choices.insert(choices.begin(), Utility::ContainerChoice{
        .name = std::format("[{}]", Translate("Vault.Back")), .action = back
    });
    choices.insert(choices.begin() + 1, Utility::ContainerChoice{
        .name = std::format("[{}]", Translate("Vault.Exit")), .action = [this, handle] {
            ResetNavigation();
            if (auto source = handle.get()) CloseStoreObject(source.get());
        }
    });
    // Defer selection until SkyUILib has queued the current list's closure.
    for (auto& choice : choices) {
        choice.action = [action = std::move(choice.action)] {
            SKSE::GetTaskInterface()->AddTask(action);
        };
    }
    ContainerSelectionState::GetSingleton()->Begin(RE::TESObjectREFRPtr{a_source}, std::move(choices),
        Translate("Vault.Archives"), [back = std::move(back)] {
            SKSE::GetTaskInterface()->AddTask(back);
        });
    queue->AddMessage(ContainerListMenu::MENU_NAME, RE::UI_MESSAGE_TYPE::kShow, nullptr);
}

void Stores::StolenItemsMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) {
        if (Settings::GetSingleton()->GSC_AllowRemovingStolenTags) ShowStolenItemsMenu(source);
        else OpenStolenItems(source);
    });
}

void Stores::OpenStolenItems(RE::TESObjectREFR* a_source) {
    if (!a_source || !Utility::GetSingleton()->GetContainer(Container::StolenItems)) return;
    if (!StolenItems::Gather()) RE::SendHUDMessage::ShowHUDMessage(Translate("Stolen.TransferFailed"));
    OpenStorageMenu(Container::StolenItems, a_source, [this](RE::TESObjectREFR* source) {
        if (!StolenItems::Return()) RE::SendHUDMessage::ShowHUDMessage(Translate("Stolen.TransferFailed"));
        if (Settings::GetSingleton()->GSC_AllowRemovingStolenTags) ShowStolenItemsMenu(source);
        else if (returnToVault_) returnToVault_();
        else CloseStoreObject(source);
    });
}

void Stores::ShowStolenItemsMenu(RE::TESObjectREFR* a_source) {
    if (!a_source || !Utility::GetSingleton()->GetContainer(Container::StolenItems)) return;
    if (!StolenItems::Recover()) RE::SendHUDMessage::ShowHUDMessage(Translate("Stolen.TransferFailed"));
    const auto handle = a_source->GetHandle();
    std::vector<MenuOption> options;
    options.push_back({Translate("Stolen.Open"), [this, handle] {
        if (auto source = handle.get()) OpenStolenItems(source.get());
    }});
    options.push_back({Translate("Vault.Exit"), [this, handle] {
        if (auto source = handle.get()) CloseStoreObject(source.get());
    }});
    if (returnToVault_) options.push_back({Translate("Vault.Back"), returnToVault_});
    options.push_back({Translate("Stolen.RemoveAllTags"), [this, handle] {
        StolenItems::ConfirmClear([this, handle] {
            if (auto source = handle.get()) StolenItemsMenu(source.get());
        });
    }});
    const auto title = std::format("{} {}", Translate("Vault.StolenItems"), Translate("Vault.Archive"));
    ShowDynamicMessageBox(title, std::move(options), 1);
}

void Stores::PersonalMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* a_openSource) { ShowPersonalMenu(a_openSource); });
}

void Stores::ShowPersonalMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();

    // Open the container
    if (auto source = sourceHandle.get())
        OpenStorageMenu(Container::Personal, source.get(), [this](RE::TESObjectREFR* a_source) {
            if (a_source) CloseStoreObject(a_source);
    });
}

void Stores::GearMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    AllToStore(Container::Instruments, Container::Gear);
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowGearMenu(source); });
}

void Stores::ShowGearMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto handle = a_source->GetHandle();
    const int amount = Settings::GetSingleton()->GSC_LockpickKeepAmount;
    std::vector<MenuOption> options;
    options.push_back({Translate("Vault.Open"), [this, handle] {
        if (auto source = handle.get())
            OpenStorageMenu(Container::Gear, source.get(), [this](RE::TESObjectREFR* closed) { GearMenu(closed); });
    }});
    options.push_back({Translate("Vault.Exit"), [this, handle] {
        if (auto source = handle.get()) CloseStoreObject(source.get());
    }});
    if (returnToVault_) options.push_back({Translate("Vault.Back"), returnToVault_});
    options.push_back({std::vformat(Translate("Vault.KeepLockpicks"), std::make_format_args(amount)), [this, handle] {
        PlayerToStore(ItemCategory::Lockpick, Container::Gear, 0, Settings::GetSingleton()->GSC_LockpickKeepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreMostMessage"));
        if (auto source = handle.get()) GearMenu(source.get());
    }});
    options.push_back({std::vformat(Translate("Vault.TakeLockpicks"), std::make_format_args(amount)), [this, handle] {
        StoreToPlayer(ItemCategory::Lockpick, Container::Gear, 0, Settings::GetSingleton()->GSC_LockpickKeepAmount);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = handle.get()) GearMenu(source.get());
    }});
    const auto title = std::format("{} {}", Translate("Vault.Gear"), Translate("Vault.Vault"));
    ShowDynamicMessageBox(title, std::move(options), 1);
}

void Stores::JunkMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) {
        OpenStorageMenu(Container::Junk, source, [this](RE::TESObjectREFR* closed) {
            if (closed) CloseStoreObject(closed);
        });
    });
}

void Stores::VaultDetail3Menu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowVaultDetail3Menu(source); });
}

void Stores::ShowVaultDetail3Menu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto handle = a_source->GetHandle();
    navigationSource_ = handle;
    returnToVault_ = [this, handle] {
        if (auto source = handle.get()) VaultDetail3Menu(source.get());
    };
    std::vector<MenuOption> options;
    options.push_back({Translate("Vault.Personal"), [this, handle] {
        if (auto source = handle.get()) PersonalMenu(source.get());
    }});
    options.push_back({Translate("Vault.Junk"), [this, handle] {
        if (auto source = handle.get()) JunkMenu(source.get());
    }});
    options.push_back({Translate("Vault.Trade"), [this, handle] {
        if (auto source = handle.get()) TradeMenu(source.get());
    }});
    options.push_back({Translate("Vault.Gear"), [this, handle] {
        if (auto source = handle.get()) GearMenu(source.get());
    }});
    options.push_back({Translate("Vault.Back"), [this, handle] {
        if (auto source = handle.get()) VaultDetail2Menu(source.get());
    }});
    options.push_back({Translate("Vault.Exit"), [this, handle] {
        if (auto source = handle.get()) CloseStoreObject(source.get());
    }});
    ShowDynamicMessageBox(Translate("Vault.Arcane"), std::move(options), 5);
}

void Stores::TradeMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowTradeMenu(source); });
}

void Stores::ShowTradeMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto handle = a_source->GetHandle();
    std::vector<MenuOption> options;
    options.push_back({Translate("Vault.OpenContainer"), [this, handle] {
        if (auto source = handle.get())
            OpenStorageMenu(Container::Trade, source.get(), [this](RE::TESObjectREFR* closed) {
                ShowTradeMenu(closed);
            });
    }});
    options.push_back({Translate("Vault.Exit"), [this, handle] {
        if (auto source = handle.get()) CloseStoreObject(source.get());
    }});
    options.push_back({Translate("Vault.TakeAll"), [this, handle] {
        if (auto source = handle.get()) {
            AllToPlayer(Container::Trade);
            ShowTradeMenu(source.get());
        }
    }});
    options.push_back({Translate("Vault.SellAll"), [this, handle] {
        auto source = handle.get();
        if (!source) return;
        const auto quote = Trade::GetQuote(Utility::GetSingleton()->GetContainer(Container::Trade),
            Settings::GetSingleton()->GSC_SalePercentage);
        if (!quote.valid || quote.copies == 0) {
            RE::SendHUDMessage::ShowHUDMessage(Translate(quote.valid ? "Vault.NoSale" : "Vault.SaleUnavailable"));
            ShowTradeMenu(source.get());
            return;
        }
        const auto message = std::format("{} {} {} {} {}?\n{}", Translate("Vault.Sell"), quote.copies,
            Translate("Vault.ItemsFor"), quote.payout, Translate("Vault.Septims"), Translate("Vault.SaleExclusions"));
        std::vector<MenuOption> confirmation;
        confirmation.push_back({Translate("Vault.Cancel"), [this, handle] {
            if (auto source = handle.get()) ShowTradeMenu(source.get());
        }});
        confirmation.push_back({Translate("Vault.SellAll"), [this, handle, quote] {
            auto source = handle.get();
            if (!source) return;
            const auto paid = quote.percentage == Settings::GetSingleton()->GSC_SalePercentage
                ? Trade::Sell(Utility::GetSingleton()->GetContainer(Container::Trade), quote) : std::nullopt;
            if (!paid) RE::SendHUDMessage::ShowHUDMessage(Translate(
                Trade::CanReceive(quote) ? "Vault.SaleChanged" : "Vault.SaleOverflow"));
            ShowTradeMenu(source.get());
        }});
        ShowDynamicMessageBox(message, std::move(confirmation), 0);
    }});
    const auto title = std::format("{} {}", Translate("Vault.Trade"), Translate("Vault.Vault"));
    ShowDynamicMessageBox(title, std::move(options), 1);
}

void Stores::CaptureSortFavorites() {
    auto* source = Utility::GetSingleton()->GetContainer(Container::Sort);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!source || !player) return;
    const auto counts = source->GetInventoryCounts();
    std::erase_if(sortFavorites_, [&counts](auto id) {
        return std::ranges::none_of(counts, [id](const auto& entry) {
            return entry.first && entry.first->GetFormID() == id && entry.second > 0;
        });
    });
    for (const auto& [item, data] : player->GetInventory()) {
        if (item && data.first > 0 && data.second && data.second->IsFavorited())
            sortFavorites_.insert(item->GetFormID());
    }
}

bool Stores::ReturnSortFavorites() {
    auto* source = Utility::GetSingleton()->GetContainer(Container::Sort);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!source || !player) return false;
    bool returned = false;
    for (const auto& [item, data] : source->GetInventory()) {
        if (!item || data.first <= 0) continue;
        if (data.second && data.second->IsFavorited()) sortFavorites_.insert(item->GetFormID());
        if (!sortFavorites_.contains(item->GetFormID())) continue;
        MoveItems(source, player, item, data.first);
        const auto counts = source->GetInventoryCounts([item](RE::TESBoundObject& candidate) { return &candidate == item; });
        const auto found = counts.find(item);
        if (found == counts.end() || found->second < data.first) returned = true;
    }
    return returned;
}

void Stores::ReturnIgnoredItems() {
    if (!Settings::GetSingleton()->GSC_ReturnIgnoredItems) return;
    auto* source = Utility::GetSingleton()->GetContainer(Container::Sort);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!source || !player) return;
    for (const auto& [item, data] : source->GetInventory()) {
        if (item && data.first > 0 && Settings::GetSingleton()->IsIgnored(item))
            MoveItems(source, player, item, data.first);
    }
}

void Stores::FinishIgnorePicker() {
    auto* source = Utility::GetSingleton()->GetContainer(Container::Ignore);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!source || !player) return;
    auto* settings = Settings::GetSingleton();
    bool rejected = false;
    bool found = false;
    for (const auto& [item, data] : source->GetInventory()) {
        if (!item || data.first <= 0) continue;
        found = true;
        if (!settings->AddIgnoredItem(item)) rejected = true;
        MoveItems(source, player, item, data.first);
    }
    if (found && !settings->SaveIgnoredItems())
        RE::SendHUDMessage::ShowHUDMessage(Translate("Ignore.SaveFailed"));
    if (rejected) RE::SendHUDMessage::ShowHUDMessage(Translate("Ignore.Unstable"));
}

void Stores::IgnoreMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    FinishIgnorePicker();
    auto* picker = Utility::GetSingleton()->GetContainer(Container::Ignore);
    if (!picker) return;
    for (const auto& [item, count] : picker->GetInventoryCounts())
        if (count > 0) return;
    const auto session = ++ignoreSession_;
    const auto sourceHandle = a_source->GetHandle();
    AVEvents::RunAfterContainerMenuCloses(picker, [this, session, sourceHandle] {
        if (session != ignoreSession_) return;
        FinishIgnorePicker();
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    });
    if (!picker->ActivateRef(RE::PlayerCharacter::GetSingleton(), 0, nullptr, 1, false))
        AVEvents::CancelContainerMenuCloseCallback();
}

void Stores::BeginJunkLoan() {
    ResetJunkLoan();
    auto* source = Utility::GetSingleton()->GetContainer(Container::Junk);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!source || !player) return;
    const auto carried = player->GetInventoryCounts();
    for (const auto& [item, data] : source->GetInventory()) {
        if (!item || data.first <= 0 || !data.second || data.second->IsQuestObject() ||
            data.second->IsFavorited() || data.second->IsWorn()) continue;
        const auto existing = carried.find(item);
        const int before = existing == carried.end() ? 0 : (std::max)(0, existing->second);
        const int count = (std::min)(data.first, (std::numeric_limits<int>::max)() - before);
        MoveItems(source, player, item, count);
        const auto counts = source->GetInventoryCounts([item](RE::TESBoundObject& candidate) { return &candidate == item; });
        const auto remaining = counts.find(item);
        const int after = remaining == counts.end() ? 0 : (std::max)(0, remaining->second);
        const int borrowed = (std::max)(0, data.first - after);
        if (borrowed > 0) junkLoan_[item->GetFormID()] = {before, borrowed};
    }
}

void Stores::EndJunkLoan() {
    auto* destination = Utility::GetSingleton()->GetContainer(Container::Junk);
    auto* player = RE::PlayerCharacter::GetSingleton();
    if (!destination || !player) { ResetJunkLoan(); return; }
    const auto* equippedCommand = RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
    const auto isEquipped = equippedCommand ? equippedCommand->conditionFunction : nullptr;
    for (const auto& [item, data] : player->GetInventory()) {
        if (!item || !data.second || data.first <= 0) continue;
        const auto loan = junkLoan_.find(item->GetFormID());
        if (loan == junkLoan_.end()) continue;
        if (data.second->IsQuestObject() || data.second->IsFavorited() || data.second->IsWorn()) continue;
        double equipped{};
        if (isEquipped && isEquipped(player, item, nullptr, equipped) && equipped != 0.0) continue;
        const auto [before, borrowed] = loan->second;
        const int count = (std::min)(borrowed, (std::max)(0, data.first - before));
        MoveItems(player, destination, item, count);
    }
    ResetJunkLoan();
}

void Stores::ConsolidateBooks() {
    AllToStore(Container::SpellTomes, Container::Book);
    AllToStore(Container::SkillBooks, Container::Book);
    AllToStore(Container::Recipes, Container::Notes);
    AllToStore(Container::TreasureMaps, Container::Notes);
    StoreToStore(ItemCategory::Note, Container::Scroll, Container::Notes);
    StoreToStore(ItemCategory::Book, Container::Scroll, Container::Book);
    StoreToStore(ItemCategory::Note, Container::Book, Container::Notes);
}

void Stores::OpenBookArchive(Container a_archive, Container a_parent, ItemCategory a_category,
    RE::TESObjectREFR* a_source, bool a_returnToParent) {
    if (!a_source) return;
    ConsolidateBooks();
    if (a_parent == Container::Concoction) ConsolidatePotions();
    AllToStore(a_archive, a_parent);
    StoreToStore(a_category, a_parent, a_archive);
    OpenStoreObject(a_source, [this, a_archive, a_parent, a_returnToParent](RE::TESObjectREFR* source) {
        OpenStorageMenu(a_archive, source, [this, a_archive, a_parent, a_returnToParent](RE::TESObjectREFR* source) {
            AllToStore(a_archive, a_parent);
            if (a_returnToParent) {
                if (a_parent == Container::Book) BookMenu(source);
                else NotesMenu(source);
            } else CloseStoreObject(source);
        });
    });
}

void Stores::NotesMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    ConsolidateBooks();
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) { ShowNotesMenu(source); });
}

void Stores::ShowNotesMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    const auto sourceHandle = a_source->GetHandle();
    std::vector<MenuOption> options;
    options.push_back({Translate("Vault.StoreAll"), [this, sourceHandle] {
        PlayerToStore(ItemCategory::Note, Container::Notes);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreAllMessage"));
        if (auto source = sourceHandle.get()) NotesMenu(source.get());
    }});
    options.push_back({std::format("{} {}", Translate("Vault.TakeUpToAmount"), 1), [this, sourceHandle] {
        StoreToPlayer(ItemCategory::Note, Container::Notes, 0, 1);
        RE::SendHUDMessage::ShowHUDMessage(Translate("Vault.StoreGetMessage"));
        if (auto source = sourceHandle.get()) NotesMenu(source.get());
    }});
    options.push_back({Translate("Vault.Recipes"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenBookArchive(Container::Recipes, Container::Notes, ItemCategory::Recipe, source.get(), true);
    }});
    options.push_back({Translate("Vault.TreasureMaps"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenBookArchive(Container::TreasureMaps, Container::Notes, ItemCategory::TreasureMap, source.get(), true);
    }});
    options.push_back({Translate("Vault.Open"), [this, sourceHandle] {
        if (auto source = sourceHandle.get())
            OpenStorageMenu(Container::Notes, source.get(), [this](RE::TESObjectREFR* source) { NotesMenu(source); });
    }});
    options.push_back({Translate("Vault.Exit"), [this, sourceHandle] {
        if (auto source = sourceHandle.get()) CloseStoreObject(source.get());
    }});
    const auto title = std::format("{} {}", Translate("Vault.Notes"), Translate("Vault.Vault"));
    const auto cancelIndex = static_cast<std::int32_t>(options.size() - 1);
    ShowDynamicMessageBox(title, std::move(options), cancelIndex);
}

void Stores::KeepAmmunition(bool a_respectIgnores) {
    auto* settings = Settings::GetSingleton();
    const int target = settings->GSC_AmmunitionKeepAmount;
    if (!settings->GSC_KeepSelectedAmmunition) {
        PlayerToStore(ItemCategory::Ammunition, Container::Ammunition, 0, target, a_respectIgnores);
        return;
    }
    auto* player = RE::PlayerCharacter::GetSingleton();
    auto* chest = Utility::GetSingleton()->GetContainer(Container::Ammunition);
    if (!player || !chest || target < 0) return;
    const auto selected = SelectedAmmunition(player);
    for (const auto& [item, data] : player->GetInventory()) {
        if (!item || !data.second || data.first <= 0 || data.second->IsQuestObject()) continue;
        if (a_respectIgnores && settings->IsIgnored(item)) continue;
        if (!HasCategory(ClassifyItem(item), ItemCategory::Ammunition)) continue;
        const int keep = selected.contains(item->GetFormID()) ? target : 0;
        MoveItems(player, chest, item, (std::max)(0, data.first - keep));
    }
}

void Stores::TakeAmmunition() {
    auto* settings = Settings::GetSingleton();
    const int target = settings->GSC_AmmunitionKeepAmount;
    if (target <= 0) return;
    if (!settings->GSC_KeepSelectedAmmunition) {
        StoreToPlayer(ItemCategory::Ammunition, Container::Ammunition, 0, target);
        return;
    }
    auto* player = RE::PlayerCharacter::GetSingleton();
    auto* chest = Utility::GetSingleton()->GetContainer(Container::Ammunition);
    if (!player || !chest) return;
    const auto selected = SelectedAmmunition(player);
    const auto carried = player->GetInventoryCounts();
    for (const auto& [item, data] : chest->GetInventory()) {
        if (!item || data.first <= 0 || !selected.contains(item->GetFormID())) continue;
        if (!HasCategory(ClassifyItem(item), ItemCategory::Ammunition)) continue;
        const auto existing = carried.find(item);
        const int held = existing == carried.end() ? 0 : (std::max)(0, existing->second);
        MoveItems(chest, player, item, (std::min)(data.first, (std::max)(0, target - held)));
    }
}

void Stores::ConsolidatePotions() {
    for (auto archive : {Container::Potion, Container::Poison, Container::Restorative,
        Container::HealthPotions, Container::MagickaPotions, Container::StaminaPotions})
        AllToStore(archive, Container::Concoction);
}

void Stores::EnchantedItemsMenu(RE::TESObjectREFR* a_source) {
    if (!a_source) return;
    OpenStoreObject(a_source, [this](RE::TESObjectREFR* source) {
        if (!EnchantedItems::Gather()) {
            RE::SendHUDMessage::ShowHUDMessage(Translate("Enchanted.TransferFailed"));
            CloseStoreObject(source);
            return;
        }
        OpenStorageMenu(Container::EnchantedItems, source, [this](RE::TESObjectREFR* closed) {
            if (!EnchantedItems::Recover())
                RE::SendHUDMessage::ShowHUDMessage(Translate("Enchanted.TransferFailed"));
            CloseStoreObject(closed);
        });
    });
}
