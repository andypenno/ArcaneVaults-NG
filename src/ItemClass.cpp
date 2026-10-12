#include "ItemClass.h"
#include "Settings.h"
#include "Utility.h"

CategoryMask ToMask(ItemCategory a_category) noexcept {
    const auto bit = static_cast<std::uint8_t>(a_category);

    if (a_category == ItemCategory::None)
        return 0;

    return CategoryMask{ 1 } << bit;
}

CategoryMask operator|(ItemCategory a_lhs, ItemCategory a_rhs) noexcept {
    return ToMask(a_lhs) | ToMask(a_rhs);
}

CategoryMask operator|(CategoryMask a_lhs, ItemCategory a_rhs) noexcept {
    return a_lhs | ToMask(a_rhs);
}

CategoryMask operator|(ItemCategory a_lhs, CategoryMask a_rhs) noexcept {
    return ToMask(a_lhs) | a_rhs;
}

CategoryMask& operator|=(CategoryMask& a_lhs, ItemCategory a_rhs) noexcept {
    a_lhs |= ToMask(a_rhs);
    return a_lhs;
}

CategoryMask ParseCategories(std::string_view a_value) {
    CategoryMask result = ToMask(ItemCategory::None);

    for (const auto part : std::views::split(a_value, ',')) {
        std::string name(part.begin(), part.end());

        const auto first = name.find_first_not_of(" \t");
        const auto last = name.find_last_not_of(" \t");

        if (first == std::string::npos)
            continue;

        name = name.substr(first, last - first + 1);

        if (const auto it = std::ranges::find_if(categoryNames, [&name](const auto& entry) {
                return entry.first == name;
            }); it != categoryNames.end()) {
            result |= it->second;
        } else {
            logger::warn("Unknown item category '{}'", name);
        }
    }

    return result;
}

std::string FormatCategories(CategoryMask a_categories) {
    std::string result;
    for (const auto& [name, category] : categoryNames) {
        if (!HasCategory(a_categories, category)) continue;
        if (!result.empty()) result += ", ";
        result += name;
    }
    return result;
}

bool HasCategory(CategoryMask a_categories, ItemCategory a_category) noexcept {
    return (a_categories & ToMask(a_category)) != 0;
}

bool HasAnyCategory(CategoryMask a_categories, CategoryMask a_wanted) noexcept {
    return (a_categories & a_wanted) != 0;
}

bool HasAllCategories(CategoryMask a_categories, CategoryMask a_wanted) noexcept {
    return (a_categories & a_wanted) == a_wanted;
}

[[nodiscard]] CategoryMask ExpandCategories(CategoryMask categories) noexcept {
    // Weapons
    const auto weaponTypes =
        ItemCategory::OneHand |
        ItemCategory::TwoHand |
        ItemCategory::Archery |
        ItemCategory::Staff;

    if (HasAnyCategory(categories, weaponTypes))
        categories |= ItemCategory::Weapon;

    // Armor
    const auto armorTypes =
        ItemCategory::HeavyArmor |
        ItemCategory::LightArmor |
        ItemCategory::Clothing |
        ItemCategory::Jewelry;

    if (HasAnyCategory(categories, armorTypes))
        categories |= ItemCategory::Armor;

    // Concoctions
    const auto concoctionTypes =
        ItemCategory::Potion |
        ItemCategory::Poison |
        ItemCategory::Restorative;

    if (HasAnyCategory(categories, concoctionTypes))
        categories |= ItemCategory::Concoction;

    // Smithing
    const auto smithingTypes =
        ItemCategory::Crafting |
        ItemCategory::Smelting |
        ItemCategory::Tanning |
        ItemCategory::Construction |
        ItemCategory::Gemstone |
        ItemCategory::PreciousIngot;

    if (HasAnyCategory(categories, smithingTypes))
        categories |= ItemCategory::Smithing;

    // Food
    const auto foodTypes =
        ItemCategory::RawFood |
        ItemCategory::CookedFood;

    if (HasAnyCategory(categories, foodTypes))
        categories |= ItemCategory::Food;

    // Alchemy
    const auto alchemyTypes =
        ItemCategory::Ingredient |
        ItemCategory::Reagent |
        ItemCategory::Catalyst;

    if (HasAnyCategory(categories, alchemyTypes))
        categories |= ItemCategory::Alchemy;

    if (HasAnyCategory(categories, ItemCategory::SpellTome | ItemCategory::SkillBook))
        categories |= ItemCategory::Book;
    if (HasAnyCategory(categories, ItemCategory::Recipe | ItemCategory::TreasureMap))
        categories |= ItemCategory::Note;

    return categories;
}

CategoryMask ClassifyItem(RE::TESBoundObject* a_item) noexcept {
    auto* utility = Utility::GetSingleton();
    if (!a_item) return ToMask(ItemCategory::None);
    CategoryMask categories = ToMask(ItemCategory::None);

    if (a_item->As<RE::TESSoulGem>())
        return ToMask(ItemCategory::Soulgem);

    // Overrides
    if (const auto override = Settings::GetSingleton()->FindOverride(a_item))
        return ExpandCategories(*override);

    if (a_item->IsGold())
        return ToMask(ItemCategory::Gold);

    if (a_item->IsKey())
        return ToMask(ItemCategory::Keys);

    if (a_item->As<RE::TESAmmo>())
        return ToMask(ItemCategory::Ammunition);

    if (a_item->As<RE::ScrollItem>())
        return ToMask(ItemCategory::Scroll);

    // Crafting
    if (a_item->As<RE::TESObjectMISC>()) {
        if (a_item->GetFormID() == 0x0005AD9E || a_item->GetFormID() == 0x0005ACE3)
            categories |= ItemCategory::PreciousIngot | ItemCategory::Smithing;
        if (utility->SmithingMap.contains(a_item->formID)) {
            categories |= ItemCategory::Smithing;
            categories |= ItemCategory::Crafting;
        }
        if (utility->SmeltingMap.contains(a_item->formID)) {
            categories |= ItemCategory::Smithing;
            categories |= ItemCategory::Smelting;
        }
        if (utility->TanningMap.contains(a_item->formID)) {
            categories |= ItemCategory::Smithing;
            categories |= ItemCategory::Tanning;
        }
        if (utility->ConstructionMap.contains(a_item->formID)) {
            categories |= ItemCategory::Smithing;
            categories |= ItemCategory::Construction;
        }

        return categories;
    }
            
    // Ingredients
    if (auto* ingredient = a_item->As<RE::IngredientItem>()) {
        categories |= ItemCategory::Alchemy;

        if (ingredient->IsFood() || utility->RawFoodMap.contains(a_item->formID))
            categories |= ItemCategory::Reagent;
        else if (utility->isSmithing(a_item->formID))
            categories |= ItemCategory::Catalyst;
        else
            categories |= ItemCategory::Ingredient;

        return categories;
    }

    // Food, Potions, and Poisons
    if (auto* potion = a_item->As<RE::AlchemyItem>()) {
        if (potion->IsFood()) {
            categories |= ItemCategory::Food;

            if (a_item->HasKeywordByEditorID("VendorItemFoodRaw") || utility->RawFoodMap.contains(a_item->formID))
                categories |= ItemCategory::RawFood;
            else 
                categories |= ItemCategory::CookedFood;

        } else {
            categories |= ItemCategory::Concoction;

            if (utility->FoundRestore(potion))
                categories |= ItemCategory::Restorative;

            if (potion->IsPoison())
                categories |= ItemCategory::Poison;
            else
                categories |= ItemCategory::Potion;
        }

        return categories;
    }

    // Armor and Clothing
    if (auto* armor = a_item->As<RE::TESObjectARMO>()) {
        categories |= ItemCategory::Armor;

        const bool isJewelry =
            armor->HasKeywordByEditorID("VendorItemJewelry") ||
            (armor->IsAccessory() && !armor->IsHelmet() && !armor->IsChestpiece() &&
                !armor->IsBoots() && !armor->IsGauntlets() && !armor->IsShield());

        if (isJewelry)
            categories |= ItemCategory::Jewelry;
        else if (armor->IsClothing())
            categories |= ItemCategory::Clothing;
        else if (armor->IsHeavyArmor())
            categories |= ItemCategory::HeavyArmor;
        else if (armor->IsLightArmor())
            categories |= ItemCategory::LightArmor;

        return categories;
    }

    // Weapons
    if (auto* weapon = a_item->As<RE::TESObjectWEAP>()) {
        categories |= ItemCategory::Weapon;

        switch (weapon->GetWeaponType()) {
        case RE::WEAPON_TYPE::kOneHandSword:
        case RE::WEAPON_TYPE::kOneHandDagger:
        case RE::WEAPON_TYPE::kOneHandAxe:
        case RE::WEAPON_TYPE::kOneHandMace:
            categories |= ItemCategory::OneHand;
            break;

        case RE::WEAPON_TYPE::kTwoHandSword:
        case RE::WEAPON_TYPE::kTwoHandAxe:
            categories |= ItemCategory::TwoHand;
            break;

        case RE::WEAPON_TYPE::kBow:
        case RE::WEAPON_TYPE::kCrossbow:
            categories |= ItemCategory::Archery;
            break;

        case RE::WEAPON_TYPE::kStaff:
            categories |= ItemCategory::Staff;
            break;

        default:
            break;
        }

        return categories;
    }

    // Books, Scrolls, and Spell Tomes
    if (auto* book = a_item->As<RE::TESObjectBOOK>()) {
        if (book->TeachesSpell())
            categories |= ItemCategory::Book | ItemCategory::SpellTome;
        else if (book->TeachesSkill())
            categories |= ItemCategory::Book | ItemCategory::SkillBook;
        else if (book->HasKeywordByEditorID("VendorItemRecipe"))
            categories |= ItemCategory::Note | ItemCategory::Recipe;
        else if (book->IsNoteScroll())
            categories |= ItemCategory::Note;
        else
            categories |= ItemCategory::Book;

        return categories;
    }

    return categories;
}
