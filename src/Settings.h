#pragma once
#include <unordered_map>
#include <unordered_set>
#include <optional>
#include "SimpleIni.h"
#include "ItemClass.h"

// ===========================
// Settings
// ===========================
class Settings {
public:
	// Hotkeys
	int GSC_AssignKeyCode{ -1 };
	int GSC_QuickKeyCode{ -1 };
	bool GSC_GlobalRedirects{ true };
	bool GSC_CraftingLoan{ false };
	bool GSC_EnchantedItemsLoan{ false };
	bool GSC_ReturnIgnoredItems{ true };
	bool GSC_LearnDepositOverrides{ false };
	bool GSC_AllowRemovingStolenTags{ false };
	bool GSC_AssignOnlyOwn{ true };
	bool GSC_AssignSpell{ true };
	bool GSC_SortSpell{ true };

	bool GSC_OffloadReagent{ true };
	bool GSC_OffloadCatalyst{ true };
	bool GSC_OffloadIngredient{ true };
	bool GSC_OffloadClothing{ false };
	bool GSC_OffloadHeavyArmor{ false };
	bool GSC_OffloadLightArmor{ false };
	bool GSC_OffloadJewelry{ false };
	bool GSC_OffloadBooks{ false };
	bool GSC_OffloadNotes{ false };
	bool GSC_OffloadPersonal{ false };
	bool GSC_OffloadGear{ false };
	bool GSC_OffloadJunk{ true };
	int GSC_LockpickKeepAmount{ 25 };
	bool GSC_OffloadScrolls{ false };
	bool GSC_OffloadSpelltomes{ false };
	bool GSC_OffloadCrafting{ true };
	bool GSC_OffloadConstruction{ true };
	bool GSC_OffloadGemstone{ true };
	bool GSC_OffloadSmelting{ true };
	bool GSC_OffloadTanning{ true };
	bool GSC_OffloadPotion{ false };
	bool GSC_OffloadPoison{ false };
	bool GSC_OffloadCookedFood{ false };
	bool GSC_OffloadRawFood{ true };
	bool GSC_OffloadSoulgems{ true };
	int GSC_SoulgemKeepAmount{ 25 };
	int GSC_AlchemyKeepAmount{ 1 };
	int GSC_ScrollKeepAmount{ 3 };
	bool GSC_OffloadTreasure{ false };
	int GSC_GoldKeepAmount{ 5000 };
	bool GSC_OffloadGold{ true };
	int GSC_AmmunitionKeepAmount{ 100 };
	bool GSC_KeepSelectedAmmunition{ false };
	int GSC_SalePercentage{ 30 };
	bool GSC_OffloadAmmunition{ true };
	bool GSC_OffloadKeys{ true };
	bool GSC_KeysKeepOne{ true };
	bool GSC_OffloadArchery{ false };
	bool GSC_OffloadOneHand{ false };
	bool GSC_OffloadTwoHand{ false };
	bool GSC_OffloadStaffHand{ false };

	void Init();

	// Processing
	void LoadINI();
	void SaveINI();
	void LoadRedirects();
	void SaveRedirects() const;
	[[nodiscard]] static std::optional<std::string> MakeFormIdentifier(const RE::TESForm* a_form);
	void LoadIgnoredItems();
	bool SaveIgnoredItems() const;
	bool AddIgnoredItem(RE::TESBoundObject* a_item);
	bool RemoveIgnoredItem(const std::string& a_identifier);
	[[nodiscard]] bool IsIgnored(const RE::TESBoundObject* a_item) const;
	[[nodiscard]] const std::unordered_set<std::string>& GetIgnoredItems() const { return ignoredItems_; }
	[[nodiscard]] static RE::TESBoundObject* ResolveIgnoredItem(std::string_view a_identifier);

	// Overrides
	void ProcessOverrides();
	void ProcessUserOverrides();
	void SetUserOverride(RE::TESBoundObject* a_item, CategoryMask a_categories);
	bool RemoveUserOverride(RE::FormID a_formID);
	bool SaveUserOverrides() const;
	[[nodiscard]] std::optional<CategoryMask> FindOverride(const RE::TESBoundObject* a_item) const;
	[[nodiscard]] std::optional<CategoryMask> FindOverride(RE::FormID a_formID) const;
	[[nodiscard]] const std::unordered_map<RE::FormID, CategoryMask>& GetUserOverrides() const noexcept;

	static Settings* GetSingleton();
private:
	std::unordered_map<RE::FormID, CategoryMask> overrides_;
	std::unordered_map<RE::FormID, CategoryMask> userOverrides_;
	std::unordered_set<std::string> ignoredItems_;

    // cannot use auto for class member declaration
	static constexpr const wchar_t* setting_path = L"Data/SKSE/Plugins/ArcaneVault/ArcaneVaultSettings.ini";
	static constexpr const wchar_t* override_path = L"Data/SKSE/Plugins/ArcaneVault/ArcaneVaultOverrides.ini";
	static constexpr const wchar_t* useroverride_path = L"Data/SKSE/Plugins/ArcaneVault/ArcaneVaultUserOverrides.ini";
	static constexpr const wchar_t* redirect_path = L"Data/SKSE/Plugins/ArcaneVault/ArcaneVaultRedirects.ini";
	static constexpr const wchar_t* ignore_path = L"Data/SKSE/Plugins/ArcaneVault/ArcaneVaultIgnoredItems.ini";

	void ProcessOverrideFile(const wchar_t* a_path , std::unordered_map<RE::FormID, CategoryMask> &a_overrides);

	template <class Func>
	void ForEachINIOption(Settings& settings, Func&& option);

	// Value Setter/Getter
	template <class T>
	void set_value(CSimpleIniA& a_ini, const T& a_value, const char* a_section, const char* a_key);

	template <class T>
	void get_value(CSimpleIniA& a_ini, T& a_value, const char* a_section, const char* a_key);
};
