#pragma once

#include <cstdint>

enum class Container : std::uint8_t {
    None,
    Master,
    Sort,
    Alchemy,
    Armor,
    Clothing,
    HeavyArmor,
    LightArmor,
    Jewelry,
    Book,
    Food,
    CookedFood,
    RawFood,
    Reagent,
    Personal,
    Gemstone,
    Concoction,
    Potion,
    Poison,
    Restorative,
    Scroll,
    Smithing,
    Construction,
    Crafting,
    Smelting,
    Tanning,
    Soulgem,
    Treasure,
    Weapon,
    Archery,
    OneHand,
    TwoHand,
    Staff,
    Keys,
    Ammunition,
    Valuables,
    FilledSoulgems,
    EmptySoulgems,
    Junk,
    Trade,
    Ignore,
    Notes,
    SpellTomes,
    SkillBooks,
    Recipes,
    Maps,
    StolenItems,
    Gear,
    Instruments,
    HealthPotions,
    MagickaPotions,
    StaminaPotions,
    EnchantedItems,
    QuickTransfer
};

enum class ItemCategory : std::uint8_t {
    Reagent,
    Catalyst,
    Alchemy,
    Armor,
    Clothing,
    HeavyArmor,
    LightArmor,
    Jewelry,
    Book,
    Construction,
    Crafting,
    Food,
    CookedFood,
    RawFood,
    Gemstone,
    Ingredient,
    Concoction,
    Potion,
    Poison,
    Restorative,
    Scroll,
    Smelting,
    Smithing,
    Soulgem,
    EmptySoulgem,
    FilledSoulgem,
    GrandSoulgem,
    SpellTome,
    Tanning,
    Treasure,
    Weapon,
    Archery,
    OneHand,
    TwoHand,
    Staff,
    None,
    Keys,
    Ammunition,
    Gold,
    PreciousIngot,
    Note,
    SkillBook,
    Recipe,
    Map,
    Personal,
    Gear,
    Lockpick,
    Instrument,
    HealthPotion,
    MagickaPotion,
    StaminaPotion,
    Junk
};

enum class ContainerGroup {
    Special,
    Vault,
    Archive
};

[[nodiscard]] constexpr std::string_view ContainerTranslationKey(Container a_container) noexcept {
    switch (a_container) {
    case Container::Master:       return "Vault.Arcane";
    case Container::Sort:         return "Vault.Conduit";
    case Container::QuickTransfer: return "Vault.QuickTransfer";
    case Container::Alchemy:      return "Vault.Alchemy";
    case Container::Armor:        return "Vault.Armor";
    case Container::Clothing:     return "Vault.Clothing";
    case Container::HeavyArmor:   return "Vault.HeavyArmor";
    case Container::LightArmor:   return "Vault.LightArmor";
    case Container::Jewelry:      return "Vault.Jewelry";
    case Container::Book:         return "Vault.Book";
    case Container::Food:         return "Vault.Food";
    case Container::CookedFood:   return "Vault.Cooked";
    case Container::RawFood:      return "Vault.Raw";
    case Container::Reagent:      return "Vault.Spice";
    case Container::Personal:     return "Vault.Personal";
    case Container::Gemstone:     return "Vault.Gemstones";
    case Container::Concoction:   return "Vault.Concoction";
    case Container::Potion:       return "Vault.Potion";
    case Container::Poison:       return "Vault.Poison";
    case Container::Restorative:  return "Vault.Restoritive";
    case Container::Scroll:       return "Vault.Scroll";
    case Container::Smithing:     return "Vault.Smithing";
    case Container::Construction: return "Vault.Construction";
    case Container::Crafting:     return "Vault.Crafting";
    case Container::Smelting:     return "Vault.Smelting";
    case Container::Tanning:      return "Vault.Tanning";
    case Container::Soulgem:      return "Vault.Soulgem";
    case Container::Treasure:     return "Vault.Treasure";
    case Container::Weapon:       return "Vault.Weapon";
    case Container::Archery:      return "Vault.Archery";
    case Container::OneHand:      return "Vault.OneHand";
    case Container::TwoHand:      return "Vault.TwoHand";
    case Container::Staff:        return "Vault.Staff";
    case Container::Keys:         return "Vault.Keys";
    case Container::Ammunition:   return "Vault.Ammunition";
    case Container::Valuables:    return "Vault.Valuables";
    case Container::FilledSoulgems: return "Vault.FilledSoulgems";
    case Container::EmptySoulgems: return "Vault.EmptySoulgems";
    case Container::Trade:        return "Vault.Trade";
    case Container::Junk:         return "Vault.Junk";
    case Container::Ignore:       return "Ignore";
    case Container::Notes:        return "Vault.Notes";
    case Container::SpellTomes:   return "Vault.SpellTomes";
    case Container::SkillBooks:   return "Vault.SkillBooks";
    case Container::Recipes:      return "Vault.Recipes";
    case Container::Maps: return "Vault.Maps";
    case Container::StolenItems:  return "Vault.StolenItems";
    case Container::Gear:         return "Vault.Gear";
    case Container::Instruments:  return "Vault.Instruments";
    case Container::HealthPotions: return "Vault.HealthPotions";
    case Container::MagickaPotions: return "Vault.MagickaPotions";
    case Container::StaminaPotions: return "Vault.StaminaPotions";
    case Container::EnchantedItems: return "Vault.EnchantedItems";
    case Container::None:         return {};
    }
    return {};
};

inline constexpr std::array<std::pair<std::string_view, ItemCategory>, 48> categoryNames{{
    { "Junk", ItemCategory::Junk },
    { "Alchemy", ItemCategory::Alchemy },
    { "Armor", ItemCategory::Armor },
    { "Weapon", ItemCategory::Weapon },
    { "Smithing", ItemCategory::Smithing },
    { "Food", ItemCategory::Food },
    { "Concoction", ItemCategory::Concoction },
    { "Restorative", ItemCategory::Restorative },
    { "Ammunition", ItemCategory::Ammunition },
    { "Archery", ItemCategory::Archery },
    { "Book", ItemCategory::Book },
    { "Note", ItemCategory::Note },
    { "SkillBook", ItemCategory::SkillBook },
    { "Recipe", ItemCategory::Recipe },
    { "Map", ItemCategory::Map },
    { "Catalyst", ItemCategory::Catalyst },
    { "Clothing", ItemCategory::Clothing },
    { "CookedFood", ItemCategory::CookedFood },
    { "Construction", ItemCategory::Construction },
    { "Crafting", ItemCategory::Crafting },
    { "Gemstone", ItemCategory::Gemstone },
    { "Gold", ItemCategory::Gold },
    { "HeavyArmor", ItemCategory::HeavyArmor },
    { "Ingredient", ItemCategory::Ingredient },
    { "Jewelry", ItemCategory::Jewelry },
    { "Keys", ItemCategory::Keys },
    { "LightArmor", ItemCategory::LightArmor },
    { "OneHand", ItemCategory::OneHand },
    { "Potion", ItemCategory::Potion },
    { "Poison", ItemCategory::Poison },
    { "PreciousIngot", ItemCategory::PreciousIngot },
    { "RawFood", ItemCategory::RawFood },
    { "Reagent", ItemCategory::Reagent },
    { "Scroll", ItemCategory::Scroll },
    { "Smelting", ItemCategory::Smelting },
    { "Soulgem", ItemCategory::Soulgem },
    { "SpellTome", ItemCategory::SpellTome },
    { "Staff", ItemCategory::Staff },
    { "Tanning", ItemCategory::Tanning },
    { "Treasure", ItemCategory::Treasure },
    { "TwoHand", ItemCategory::TwoHand },
    { "Personal", ItemCategory::Personal },
    { "Gear", ItemCategory::Gear },
    { "Lockpick", ItemCategory::Lockpick },
    { "Instrument", ItemCategory::Instrument },
    { "HealthPotion", ItemCategory::HealthPotion },
    { "MagickaPotion", ItemCategory::MagickaPotion },
    { "StaminaPotion", ItemCategory::StaminaPotion }
}};

enum class BenchType : std::uint8_t {
    None,
    Alchemy,
    Smithing,
    Cooking,
    Enchanting,
    StaffEnchanting
};

using CategoryMask = std::uint64_t;

[[nodiscard]] CategoryMask ToMask(ItemCategory a_category) noexcept;

[[nodiscard]] CategoryMask operator|(ItemCategory a_lhs, ItemCategory a_rhs) noexcept;
[[nodiscard]] CategoryMask operator|(CategoryMask a_lhs, ItemCategory a_rhs) noexcept;
[[nodiscard]] CategoryMask operator|(ItemCategory a_lhs, CategoryMask a_rhs) noexcept;
CategoryMask& operator|=(CategoryMask& a_lhs, ItemCategory a_rhs) noexcept;

[[nodiscard]] bool HasCategory(CategoryMask a_categories, ItemCategory a_category) noexcept;
[[nodiscard]] bool HasAnyCategory(CategoryMask a_categories, CategoryMask a_wanted) noexcept;
[[nodiscard]] bool HasAllCategories(CategoryMask a_categories, CategoryMask a_wanted) noexcept;

[[nodiscard]] CategoryMask ExpandCategories(CategoryMask categories) noexcept;
[[nodiscard]] CategoryMask ParseCategories(std::string_view a_value);
[[nodiscard]] std::string FormatCategories(CategoryMask a_categories);
[[nodiscard]] CategoryMask ClassifyItem(RE::TESBoundObject* a_item) noexcept;
