#pragma once
#include "ItemClass.h"
#include "Utility.h"
#include <optional>

using MenuAction = std::function<void()>;

struct MenuOption
{
    std::string text;
    MenuAction action;
};

class MenuCallback final : public RE::IMessageBoxCallback {
public:
    explicit MenuCallback(std::vector<MenuAction> a_actions) : actions(std::move(a_actions)){}

    void Run(std::uint8_t a_message) override {
        const auto index = static_cast<std::size_t>(a_message);
        if (index >= actions.size() || !actions[index]) return;

        // Copy it because this callback may be destroyed after Run returns.
        auto action = actions[index];

        SKSE::GetTaskInterface()->AddTask([action = std::move(action)]() mutable {
            action();
        });
    }

private:
    std::vector<MenuAction> actions;
};

class Stores {
public:
    static Stores* GetSingleton() {
        static Stores singleton;
        return &singleton;
    }

    // Storage Menus
    void ShowDynamicMessageBox(std::string_view a_message, std::vector<MenuOption> a_options, std::int32_t a_cancelOption = -1);

    // Storage Functions
    void PlayerToStore(ItemCategory a_category, Container a_chest, int i_count = 0, int a_keepCount = 0, bool a_respectIgnores = false, CategoryMask a_excluded = 0);
    void StoreToPlayer(ItemCategory a_category, Container a_chest, int i_count = 0, std::optional<int> a_target = std::nullopt);
    void StoreToStore(ItemCategory a_category, Container a_source, Container a_destination);
    void AllToStore(Container a_source, Container a_destination);
    void AllToPlayer(Container a_source);
    void OpenStorageMenu(Container a_chest, RE::TESObjectREFR* a_source, std::function<void(RE::TESObjectREFR*)> a_onClose);

    // Store Animations
    using AnimationCallback = std::function<void(RE::TESObjectREFR*)>;

    void OpenStoreObject(RE::TESObjectREFR* a_source, AnimationCallback a_onComplete = {});
    void CloseStoreObject(RE::TESObjectREFR* a_source, AnimationCallback a_onComplete = {});

    // Utility Functions
    void SortItems();
    void OffloadItems(std::function<void()> complete = {});
    void KeepAmmunition(bool a_respectIgnores = false);
    void TakeAmmunition();
    void IgnoreMenu(RE::TESObjectREFR* a_source);
    void FinishIgnorePicker();
    void ResetIgnorePicker() { ++ignoreSession_; }
    void ReturnIgnoredItems();
    void ResetSortFavorites() { sortFavorites_.clear(); }
    void BeginJunkLoan();
    void EndJunkLoan();
    void ResetJunkLoan() { junkLoan_.clear(); }
    void ResetNavigation();
    void VaultAssignment(RE::TESObjectREFRPtr a_source);
    
    // Container Functions
    void VaultMenu(RE::TESObjectREFR* a_source);
    void ShowVaultsMenu(RE::TESObjectREFR* a_source);
    void ShowVaultArchivesMenu(RE::TESObjectREFR* a_source);
    void SortingMenu(RE::TESObjectREFR* a_source);
    void AlchemyMenu(RE::TESObjectREFR* a_source);
    void SoulgemMenu(RE::TESObjectREFR* a_source);
    void FilledSoulgemsMenu(RE::TESObjectREFR* a_source);
    void EmptySoulgemsMenu(RE::TESObjectREFR* a_source);
    void FoodMenu(RE::TESObjectREFR* a_source);
    void FoodCookedMenu(RE::TESObjectREFR* a_source);
    void FoodRawMenu(RE::TESObjectREFR* a_source);
    void FoodSaltMenu(RE::TESObjectREFR* a_source);
    void BookMenu(RE::TESObjectREFR* a_source);
    void NotesMenu(RE::TESObjectREFR* a_source);
    void ConsolidateBooks();
    void ConsolidatePotions();
    void EnchantedItemsMenu(RE::TESObjectREFR* a_source);
    void OpenBookArchive(Container a_archive, Container a_parent, ItemCategory a_category,
        RE::TESObjectREFR* a_source, bool a_returnToParent = false);
    void ScrollMenu(RE::TESObjectREFR* a_source);
    void ArmorMenu(RE::TESObjectREFR* a_source);
    void ArmorLightMenu(RE::TESObjectREFR* a_source);
    void ArmorHeavyMenu(RE::TESObjectREFR* a_source);
    void ArmorJewelryMenu(RE::TESObjectREFR* a_source);
    void ArmorClothingMenu(RE::TESObjectREFR* a_source);
    void WeaponMenu(RE::TESObjectREFR* a_source);
    void WeaponArcheryMenu(RE::TESObjectREFR* a_source);
    void WeaponOneHandMenu(RE::TESObjectREFR* a_source);
    void WeaponTwoHandMenu(RE::TESObjectREFR* a_source);
    void WeaponStaffMenu(RE::TESObjectREFR* a_source);
    void GemstoneMenu(RE::TESObjectREFR* a_source);
    void TreasureMenu(RE::TESObjectREFR* a_source);
    void TradeMenu(RE::TESObjectREFR* a_source);
    void JunkMenu(RE::TESObjectREFR* a_source);
    void PersonalMenu(RE::TESObjectREFR* a_source);
    void GearMenu(RE::TESObjectREFR* a_source);
    void KeysMenu(RE::TESObjectREFR* a_source);
    void AmmunitionMenu(RE::TESObjectREFR* a_source);
    void ValuablesMenu(RE::TESObjectREFR* a_source);
    void StolenItemsMenu(RE::TESObjectREFR* a_source);
    void ShowStolenItemsMenu(RE::TESObjectREFR* a_source);
    void OpenStolenItems(RE::TESObjectREFR* a_source);
    void ReturnValuables();
    void PotionMenu(RE::TESObjectREFR* a_source);
    void PotionPositiveMenu(RE::TESObjectREFR* a_source);
    void PotionNegativeMenu(RE::TESObjectREFR* a_source);
    void PotionRestoreMenu(RE::TESObjectREFR* a_source);
    void SmithMenu(RE::TESObjectREFR* a_source);
    void SmithCraftMenu(RE::TESObjectREFR* a_source);
    void SmithSmeltMenu(RE::TESObjectREFR* a_source);
    void SmithTanMenu(RE::TESObjectREFR* a_source);
    void SmithConstructMenu(RE::TESObjectREFR* a_source);

private:
    void OffloadItemsNow();
    void ShowStorageListMenu(RE::TESObjectREFR* a_source, ContainerGroup group);
    std::unordered_set<RE::FormID> sortFavorites_;
    void CaptureSortFavorites();
    bool ReturnSortFavorites();
    std::uint64_t ignoreSession_{};
    std::unordered_map<RE::FormID, std::pair<int, int>> junkLoan_;
    RE::ObjectRefHandle navigationSource_;
    MenuAction returnToVault_;
    void ShowVaultMenu(RE::TESObjectREFR* a_source);
    void ShowSortingMenu(RE::TESObjectREFR* a_source);
    void ShowGearMenu(RE::TESObjectREFR* a_source);
    void ShowAlchemyMenu(RE::TESObjectREFR* a_source);
    void ShowSoulgemMenu(RE::TESObjectREFR* a_source);
    void ShowFoodMenu(RE::TESObjectREFR* a_source);
    void ShowFoodCookedMenu(RE::TESObjectREFR* a_source);
    void ShowFoodRawMenu(RE::TESObjectREFR* a_source);
    void ShowFoodSaltMenu(RE::TESObjectREFR* a_source);
    void ShowBookMenu(RE::TESObjectREFR* a_source);
    void ShowNotesMenu(RE::TESObjectREFR* a_source);
    void ShowScrollMenu(RE::TESObjectREFR* a_source);
    void ShowArmorMenu(RE::TESObjectREFR* a_source);
    void ShowArmorLightMenu(RE::TESObjectREFR* a_source);
    void ShowArmorHeavyMenu(RE::TESObjectREFR* a_source);
    void ShowArmorJewelryMenu(RE::TESObjectREFR* a_source);
    void ShowArmorClothingMenu(RE::TESObjectREFR* a_source);
    void ShowWeaponMenu(RE::TESObjectREFR* a_source);
    void ShowWeaponArcheryMenu(RE::TESObjectREFR* a_source);
    void ShowWeaponOneHandMenu(RE::TESObjectREFR* a_source);
    void ShowWeaponTwoHandMenu(RE::TESObjectREFR* a_source);
    void ShowWeaponStaffMenu(RE::TESObjectREFR* a_source);
    void ShowGemstoneMenu(RE::TESObjectREFR* a_source);
    void ShowTreasureMenu(RE::TESObjectREFR* a_source);
    void ShowTradeMenu(RE::TESObjectREFR* a_source);
    void ShowPersonalMenu(RE::TESObjectREFR* a_source);
    void ShowKeysMenu(RE::TESObjectREFR* a_source);
    void ShowAmmunitionMenu(RE::TESObjectREFR* a_source);
    void ShowValuablesMenu(RE::TESObjectREFR* a_source);
    void ShowPotionMenu(RE::TESObjectREFR* a_source);
    void ShowPotionPositiveMenu(RE::TESObjectREFR* a_source);
    void ShowPotionNegativeMenu(RE::TESObjectREFR* a_source);
    void ShowPotionRestoreMenu(RE::TESObjectREFR* a_source);
    void ShowSmithMenu(RE::TESObjectREFR* a_source);
    void ShowSmithCraftMenu(RE::TESObjectREFR* a_source);
    void ShowSmithSmeltMenu(RE::TESObjectREFR* a_source);
    void ShowSmithTanMenu(RE::TESObjectREFR* a_source);
    void ShowSmithConstructMenu(RE::TESObjectREFR* a_source);
};
