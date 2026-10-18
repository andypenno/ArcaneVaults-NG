#include "AVUI.h"
#include "Translation.h"
#include "ItemClass.h"
#include "Utility.h"
#include "TransferFeedback.h"

using AVTranslation::Translate;

namespace AVUI {
	void Register() {
		if (!SKSEMenuFramework::IsInstalled()) return;

		TransferFeedback::Register();

		// Render Menu
		SKSEMenuFramework::SetSection(Translate("Settings.ModName"));
		SKSEMenuFramework::AddSectionItem(Translate("Options"), RenderOptions);
		SKSEMenuFramework::AddSectionItem(Translate("Quantities"), RenderQuantities);
		SKSEMenuFramework::AddSectionItem("Quick Transfer", RenderTransfer);
		SKSEMenuFramework::AddSectionItem(Translate("Override"), RenderOverrides);
		SKSEMenuFramework::AddSectionItem(Translate("Ignore"), RenderIgnoredItems);
	}

	void __stdcall RenderOptions() {
		auto* setting = Settings::GetSingleton();
		auto* utility = Utility::GetSingleton();

		bool changeOption = false;

		// Hotkey Options
		Text(Translate("Options.Hotkey"));
		SameLine();
		int &hotkey = setting->GSC_AssignKeyCode;

		// Show the button with current hotkey name
		if (Button(waitKey ? Translate("Options.WaitKey") : GetKeyName((ImGuiKey)HelperFunctions::IDCodeToImGuiKey(hotkey)))) {
			waitKey = true;
			hotkey = -1;
		}

		// If waiting, check for input
		if (waitKey) {
			for (int key = ImGuiKey_NamedKey_BEGIN; key < ImGuiKey_NamedKey_END; key++) {
				if (IsKeyPressed((ImGuiKey)key)) {
					hotkey = HelperFunctions::ImGuiKeyToIDCode((ImGuiKey)key);
					waitKey = false;
					changeOption = true;
					break;
				}
			}
		}

		// Show a Clear Button
		if (hotkey >= 0) {
			SameLine();
			if (Button(Translate("Options.Reset"))) {
				hotkey = -1;
				changeOption = true;
			}
		}
		if (Checkbox(Translate("Options.OnlyOwn"), &setting->GSC_AssignOnlyOwn))
			changeOption = true;
		if (Checkbox(Translate("Options.AssignSpell"), &setting->GSC_AssignSpell)) {
			changeOption = true;
			utility->ConfigurationSpells();
		}
		if (Checkbox(Translate("Options.Redirect"), &setting->GSC_GlobalRedirects))
			changeOption = true;
		if (Checkbox(Translate("Options.CraftLoan"), &setting->GSC_CraftingLoan))
			changeOption = true;
		if (Checkbox(Translate("Options.AllCraftingMaterials"), &setting->GSC_AllCraftingMaterials))
			changeOption = true;
		if (Checkbox(Translate("Options.LearnDepositOverrides"), &setting->GSC_LearnDepositOverrides))
			changeOption = true;
		if (Checkbox(Translate("Options.SortSpell"), &setting->GSC_SortSpell)) {
			changeOption = true;
			utility->ConfigurationSpells();
		}
		if (Checkbox(Translate("Options.ReturnIgnoredItems"), &setting->GSC_ReturnIgnoredItems))
			changeOption = true;
		if (Checkbox(Translate("Options.KeepSelectedAmmunition"), &setting->GSC_KeepSelectedAmmunition))
			changeOption = true;
		if (Checkbox(Translate("Options.AllowRemovingStolenTags"), &setting->GSC_AllowRemovingStolenTags))
			changeOption = true;

		int salePercentage = setting->GSC_SalePercentage;
		if (InputInt(Translate("Options.SalePercentage"), &salePercentage)) {
			setting->GSC_SalePercentage = std::clamp(salePercentage, 1, 100);
			changeOption = true;
		}

		if (changeOption)
			setting->SaveINI();
	}

	void __stdcall RenderQuantities() {
		auto* setting = Settings::GetSingleton();
		bool changeOption = false;

		int keepAmount = setting->GSC_AmmunitionKeepAmount;
		if (InputInt(Translate("Options.AmmunitionKeepAmount"), &keepAmount)) {
			setting->GSC_AmmunitionKeepAmount = (std::max)(0, keepAmount);
			changeOption = true;
		}

		int goldKeepAmount = setting->GSC_GoldKeepAmount;
		if (InputInt(Translate("Options.GoldKeepAmount"), &goldKeepAmount)) {
			setting->GSC_GoldKeepAmount = (std::max)(0, goldKeepAmount);
			changeOption = true;
		}

		int lockpickKeepAmount = setting->GSC_LockpickKeepAmount;
		if (InputInt(Translate("Options.LockpickKeepAmount"), &lockpickKeepAmount)) {
			setting->GSC_LockpickKeepAmount = (std::max)(0, lockpickKeepAmount);
			changeOption = true;
		}

		int soulgemKeepAmount = setting->GSC_SoulgemKeepAmount;
		if (InputInt(Translate("Options.SoulgemKeepAmount"), &soulgemKeepAmount)) {
			setting->GSC_SoulgemKeepAmount = (std::max)(0, soulgemKeepAmount);
			changeOption = true;
		}

		int alchemyKeepAmount = setting->GSC_AlchemyKeepAmount;
		if (InputInt(Translate("Options.AlchemyKeepAmount"), &alchemyKeepAmount)) {
			setting->GSC_AlchemyKeepAmount = (std::max)(0, alchemyKeepAmount);
			changeOption = true;
		}

		int scrollKeepAmount = setting->GSC_ScrollKeepAmount;
		if (InputInt(Translate("Options.ScrollKeepAmount"), &scrollKeepAmount)) {
			setting->GSC_ScrollKeepAmount = (std::max)(0, scrollKeepAmount);
			changeOption = true;
		}

		if (changeOption)
			setting->SaveINI();
	}

	void __stdcall RenderTransfer() {
		auto* setting = Settings::GetSingleton();
		bool changeOption = false;

		if (CollapsingHeader(Translate("Vault.Alchemy"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Catalyst"), &setting->GSC_OffloadCatalyst))
				changeOption = true;
			if (Checkbox(Translate("Vault.Ingredient"), &setting->GSC_OffloadIngredient))
				changeOption = true;
			if (Checkbox(Translate("Vault.Reagent"), &setting->GSC_OffloadReagent))
				changeOption = true;
		}

		if (CollapsingHeader(Translate("Vault.Armor"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Clothing"), &setting->GSC_OffloadClothing))
				changeOption = true;
			if (Checkbox(Translate("Vault.HeavyArmor"), &setting->GSC_OffloadHeavyArmor))
				changeOption = true;
			if (Checkbox(Translate("Vault.Jewelry"), &setting->GSC_OffloadJewelry))
				changeOption = true;
			if (Checkbox(Translate("Vault.LightArmor"), &setting->GSC_OffloadLightArmor))
				changeOption = true;
		}

		if (CollapsingHeader(Translate("Vault.Book"), ImGuiTreeNodeFlags_DefaultOpen)) {
			PushID("BookTransferOptions");
			if (Checkbox(Translate("Vault.Book"), &setting->GSC_OffloadBooks))
				changeOption = true;
			if (Checkbox(Translate("Vault.Scroll"), &setting->GSC_OffloadScrolls))
				changeOption = true;
			if (Checkbox(Translate("Vault.SpellTome"), &setting->GSC_OffloadSpelltomes))
				changeOption = true;
			PopID();
		}

		if (Checkbox(Translate("Vault.Notes"), &setting->GSC_OffloadNotes))
			changeOption = true;

		if (CollapsingHeader(Translate("Vault.Concoction"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Poison"), &setting->GSC_OffloadPoison))
				changeOption = true;
			if (Checkbox(Translate("Vault.Potion"), &setting->GSC_OffloadPotion))
				changeOption = true;
		}

		if (CollapsingHeader(Translate("Vault.Food"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Cooked"), &setting->GSC_OffloadCookedFood))
				changeOption = true;
			if (Checkbox(Translate("Vault.Raw"), &setting->GSC_OffloadRawFood))
				changeOption = true;
		}

		if (CollapsingHeader(Translate("Vault.Smithing"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Construction"), &setting->GSC_OffloadConstruction))
				changeOption = true;
			if (Checkbox(Translate("Vault.Crafting"), &setting->GSC_OffloadCrafting))
				changeOption = true;
			if (Checkbox(Translate("Vault.Gemstones"), &setting->GSC_OffloadGemstone))
				changeOption = true;
			if (Checkbox(Translate("Vault.Tanning"), &setting->GSC_OffloadTanning))
				changeOption = true;
			if (Checkbox(Translate("Vault.Smelting"), &setting->GSC_OffloadSmelting))
				changeOption = true;

		}

		if (Checkbox(Translate("Vault.Soulgem"), &setting->GSC_OffloadSoulgems))
			changeOption = true;

		if (CollapsingHeader(Translate("Vault.Weapon"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Archery"), &setting->GSC_OffloadArchery))
				changeOption = true;
			if (Checkbox(Translate("Vault.OneHand"), &setting->GSC_OffloadOneHand))
				changeOption = true;
			if (Checkbox(Translate("Vault.Staff"), &setting->GSC_OffloadTwoHand))
				changeOption = true;
			if (Checkbox(Translate("Vault.TwoHand"), &setting->GSC_OffloadStaffHand))
				changeOption = true;
		}

		if (CollapsingHeader(Translate("Vault.More"), ImGuiTreeNodeFlags_DefaultOpen)) {
			if (Checkbox(Translate("Vault.Septims"), &setting->GSC_OffloadGold))
				changeOption = true;
			if (Checkbox(Translate("Vault.Ammunition"), &setting->GSC_OffloadAmmunition))
				changeOption = true;
			if (Checkbox(Translate("Vault.Keys"), &setting->GSC_OffloadKeys))
				changeOption = true;
			SameLine();
			if (Checkbox(Translate("Vault.KeepOne"), &setting->GSC_KeysKeepOne))
				changeOption = true;
			if (Checkbox(Translate("Vault.Treasure"), &setting->GSC_OffloadTreasure))
				changeOption = true;
			if (Checkbox(Translate("Vault.Gear"), &setting->GSC_OffloadGear))
				changeOption = true;
			if (Checkbox(Translate("Vault.Junk"), &setting->GSC_OffloadJunk))
				setting->SaveINI();
			if (Checkbox(Translate("Vault.Personal"), &setting->GSC_OffloadPersonal))
				changeOption = true;
		}

		if (changeOption)
			setting->SaveINI();
        const auto timing = TransferFeedback::LastReport();
        if (timing.complete) {
            Text(Translate("Options.LastTransfer"));
            const std::array<const char*, 5> labels{"Options.TransferOverlay", "Options.TransferInspection",
                "Options.TransferRecovery", "Options.TransferSoulgems", "Options.TransferItems"};
            for (std::size_t i = 0; i < labels.size(); ++i)
                Text("%s: %.1f ms", Translate(labels[i]), timing.milliseconds[i]);
            Text("%s: %.1f ms", Translate("Options.TransferTotal"), timing.total);
        }

	}

	void __stdcall RenderIgnoredItems() {
        static std::array<char, 256> search{};
        static bool confirmClear = false;
        auto* settings = Settings::GetSingleton();
        TextWrapped("%s", Translate("Ignore.Help"));
        InputText(Translate("Ignore.Search"), search.data(), search.size());
        std::optional<std::string> removal;
        if (BeginTable("IgnoredItems", 3)) {
            TableSetupColumn(Translate("Override.Record"));
            TableSetupColumn(Translate("Ignore.Identifier"));
            TableSetupColumn("");
            TableHeadersRow();
            for (const auto& identifier : settings->GetIgnoredItems()) {
                const auto* item = Settings::ResolveIgnoredItem(identifier);
                const std::string name = item && item->GetName() ? item->GetName() : Translate("Ignore.Missing");
                if (search[0] && name.find(search.data()) == std::string::npos &&
                    identifier.find(search.data()) == std::string::npos) continue;
                PushID(identifier.c_str());
                TableNextRow();
                TableNextColumn(); Text("%s", name.c_str());
                TableNextColumn(); Text("%s", identifier.c_str());
                TableNextColumn();
                if (Button(Translate("Override.ButtonRemove"))) removal = identifier;
                PopID();
            }
            EndTable();
        }
        bool changed = removal && settings->RemoveIgnoredItem(*removal);
        if (Button(Translate("Ignore.ClearAll"))) confirmClear = true;
        if (confirmClear) {
            if (Button(Translate("Ignore.ConfirmClear"))) {
                const auto entries = settings->GetIgnoredItems();
                for (const auto& identifier : entries) settings->RemoveIgnoredItem(identifier);
                changed = true;
                confirmClear = false;
            }
            SameLine();
            if (Button(Translate("Ignore.Cancel"))) confirmClear = false;
        }
        if (changed && !settings->SaveIgnoredItems())
            RE::SendHUDMessage::ShowHUDMessage(Translate("Ignore.SaveFailed"));
	}

	void __stdcall RenderOverrides() {
		auto& editor = overrideEditor;

		if (CollapsingHeader(Translate("Override.Lookup"), ImGuiTreeNodeFlags_DefaultOpen)) {
			// Lookup the form ID of the item
			Text(Translate("Override.FormID"));
			InputText("##FormID", editor.formIDText.data(), editor.formIDText.size(), ImGuiInputTextFlags_CharsHexadecimal);
			SameLine();
			if (Button(Translate("Override.ButtonLookup"))) LookupOverrideItem();

			// Display the record name
			Text(Translate("Override.FormID"));
			InputText("##Object", editor.itemName.data(), editor.itemName.size(), ImGuiInputTextFlags_ReadOnly);

			// If record isnt found
			if (!editor.error.empty()) Text("%s", editor.error.c_str());

			if (editor.selectedItem) {
				const auto selected = std::ranges::find_if(categoryNames, [&editor](const auto& entry) {
					return HasCategory(editor.selectedCategories, entry.second);
				});
				const auto preview = selected != categoryNames.end() ? selected->first : std::string_view{ "Select category" };

				Text(Translate("Override.Categories"));
				if (BeginCombo("##CategorySelection", preview.data())) {
					for (const auto& [name, category] : categoryNames) {
						const bool isSelected = HasCategory(editor.selectedCategories, category);
						if (Selectable(name.data(), isSelected))
							editor.selectedCategories = ToMask(category);
					}
					EndCombo();
				}
			}

			if (editor.selectedFormID != 0 && Button(Translate("Override.ButtonSave"))) SaveOverrideChanges();
		}

		if (CollapsingHeader(Translate("Override.UserOverrides"), ImGuiTreeNodeFlags_DefaultOpen)) {
			auto* settings = Settings::GetSingleton();
			std::optional<RE::FormID> pendingRemoval;

			if (BeginTable("UserOverrides", 4)) {
				TableSetupColumn(Translate("Override.FormID"));
				TableSetupColumn(Translate("Override.Record"));
				TableSetupColumn(Translate("Override.Categories"));
				TableSetupColumn("");
				TableHeadersRow();

				for (const auto& [formID, categories] : settings->GetUserOverrides()) {
					TableNextRow();
					PushID(static_cast<int>(formID));

					TableNextColumn();
					Text("0x%08X", formID);

					TableNextColumn();
					const auto* item = RE::TESForm::LookupByID<RE::TESBoundObject>(formID);
					Text("%s", item && item->GetName() ? item->GetName() : "<Missing record>");

					TableNextColumn();
					const auto categoryText = FormatCategories(categories);
					Text("%s", categoryText.c_str());

					TableNextColumn();
					if (Button(Translate("Override.ButtonEdit"))) {
						std::snprintf(editor.formIDText.data(), editor.formIDText.size(), "%08X", formID);
						LookupOverrideItem();
					}
					SameLine();
					if (Button(Translate("Override.ButtonRemove")))
						pendingRemoval = formID;

					PopID();
				}
				EndTable();
			}

			if (pendingRemoval && settings->RemoveUserOverride(*pendingRemoval)) {
				settings->SaveUserOverrides();
				if (editor.selectedFormID == *pendingRemoval) {
					editor.selectedFormID = 0;
					editor.selectedItem = nullptr;
					editor.selectedCategories = 0;
					editor.itemName.fill('\0');
				}
			}
		}
	}

	void LookupOverrideItem() {
		auto& editor = overrideEditor;

		editor.selectedItem = nullptr;
		editor.selectedFormID = 0;
		editor.selectedCategories = 0;
		editor.itemName.fill('\0');
		editor.error.clear();

		std::string_view text{ editor.formIDText.data() };

		if (text.starts_with("0x") || text.starts_with("0X"))
			text.remove_prefix(2);

		RE::FormID formID{};
		const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), formID, 16);

		if (error != std::errc{} || end != text.data() + text.size()) {
			editor.error = "Invalid FormID";
			return;
		}

		// Check overrides first so an existing category selection is restored.
		if (const auto existing = Settings::GetSingleton()->FindOverride(formID))
			editor.selectedCategories = *existing;

		auto* item = RE::TESForm::LookupByID<RE::TESBoundObject>(formID);
		if (!item) {
			editor.error = "Form is not an item";
			return;
		}

		editor.selectedItem = item;
		editor.selectedFormID = item->GetFormID();
		const std::string_view name{ item->GetName() ? item->GetName() : "" };
		const auto length = (std::min)(name.size(), editor.itemName.size() - 1);
		std::ranges::copy_n(name.begin(), length, editor.itemName.begin());
	}

	void SaveOverrideChanges() {
		auto& editor = overrideEditor;
		auto* item = RE::TESForm::LookupByID<RE::TESBoundObject>(editor.selectedFormID);
		if (!item) {
			editor.error = "Look up an item before saving";
			return;
		}

		auto* settings = Settings::GetSingleton();
		settings->SetUserOverride(item, editor.selectedCategories);
		if (settings->SaveUserOverrides())
			editor.error.clear();
		else
			editor.error = "Failed to save user overrides";
	}
}
