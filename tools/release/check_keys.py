"""Exercise actual transfer and Quick Transfer code with inventory stubs."""

from pathlib import Path
import copy
import json
import subprocess
import tempfile

from esp import generate_esp, walk
from validate import validate_esp

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/Stores.cpp").read_text()
start = source.index("void Stores::PlayerToStore(")
method = source[start:source.index("\n}\n", start) + 3]
start = source.index("void Stores::OffloadItems(")
offload = source[start:source.index("\n}\n", start) + 3]
start = source.index("void Stores::StoreToStore(")
store_to_store = source[start:source.index("\n}\n", start) + 3]
start = source.index("void Stores::SortItems(")
sort_items = source[start:source.index("\n}\n", start) + 3]
extra_methods = ""
for name in ["StoreToPlayer", "AllToStore", "ReturnValuables", "ShowValuablesMenu", "ValuablesMenu", "ShowTreasureMenu", "ShowAlchemyMenu", "AlchemyMenu", "AllToPlayer", "ShowArmorJewelryMenu", "EmptySoulgemsMenu", "KeysMenu", "ShowKeysMenu", "BookMenu", "ShowBookMenu", "ScrollMenu", "ShowScrollMenu", "ReturnIgnoredItems", "FinishIgnorePicker", "BeginJunkLoan", "EndJunkLoan", "ConsolidateBooks", "NotesMenu", "ShowNotesMenu", "ShowBookArchives", "OpenBookArchive"]:
    start = source.index("void Stores::" + name + "(")
    extra_methods += source[start:source.index("\n}\n", start) + 3]
settings = (ROOT / "src/Settings.cpp").read_text()
start = settings.index("template <class Func>\nvoid Settings::ForEachINIOption(")
ini_options = settings[start:settings.index("\n}\n", start) + 3]
start = settings.index("template <class T>\nvoid Settings::get_value(")
get_value = settings[start:settings.index("\n}\n", start) + 3]
classification = (ROOT / "src/ItemClass.cpp").read_text()
start = classification.index("CategoryMask ClassifyItem(")
classification = classification[start:classification.index("    // Food, Potions, and Poisons", start)]
armor_source = (ROOT / "src/ItemClass.cpp").read_text()
classification += armor_source[armor_source.index("    // Armor and Clothing"):armor_source.index("    // Weapons", armor_source.index("    // Armor and Clothing"))]
book_source = (ROOT / "src/ItemClass.cpp").read_text()
classification += book_source[book_source.index("    // Books, Scrolls, and Spell Tomes"):book_source.rindex("    return categories;")]
classification += "\n    return categories | ToMask(a_item->category);\n}\n"
settings_fields = "\n".join(line for line in (ROOT / "src/Settings.h").read_text().splitlines()
                            if line.strip().startswith(("bool GSC_", "int GSC_")))
program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <charconv>
#include <climits>
#include <limits>
#include <type_traits>
#include <functional>
#include <sstream>
#include <unordered_set>
#include <vector>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
enum class ITEM_REMOVE_REASON { kStoreInContainer };
struct TESAmmo {};
struct ScrollItem {};
struct TESObjectBOOK {
    bool note=false, spell=false, skill=false, recipe=false;
    bool IsNoteScroll() const { return note; }
    bool TeachesSpell() const { return spell; }
    bool TeachesSkill() const { return skill; }
    bool HasKeywordByEditorID(std::string_view key) const { return recipe && key=="VendorItemRecipe"; }
};
struct TESObjectMISC {};
struct TESSoulGem {};
struct IngredientItem { bool food = false; bool IsFood() const { return food; } };
struct BIPED_MODEL {
    enum class BipedObjectSlot : unsigned { kHead=1, kHair=2, kBody=4, kHands=8, kAmulet=32, kRing=64, kFeet=128, kShield=512, kCirclet=4096 };
    enum class ArmorType { kLightArmor, kHeavyArmor, kClothing };
};
struct TESObjectARMO {
    using BipedObjectSlot = BIPED_MODEL::BipedObjectSlot;
    using ArmorType = BIPED_MODEL::ArmorType;
    struct SlotMask {
        unsigned bits = 0;
        template<class... Flags> bool all(Flags... flags) const { return (((bits & static_cast<unsigned>(flags)) == static_cast<unsigned>(flags)) && ...); }
    };
    struct { SlotMask bipedObjectSlots; ArmorType armorType = ArmorType::kClothing; } bipedModelData;
    bool jewelryKeyword = false;
    bool HasKeywordByEditorID(const char*) const { return jewelryKeyword; }
    bool IsClothing() const;
    bool IsLightArmor() const;
    bool IsHeavyArmor() const;
    bool IsAccessory() const;
    bool IsHelmet() const;
    bool IsCirclet() const;
    bool IsChestpiece() const;
    bool IsBoots() const;
    bool IsGauntlets() const;
    bool IsShield() const;
};
struct TESBoundObject {
    ItemCategory category;
    bool bolt = false;
    unsigned formID = 0;
    IngredientItem ingredient{};
    TESObjectARMO armor{};
    bool nativeArmor = false;
    bool nativeScroll = false;
    bool nativeBook = false;
    TESObjectBOOK book{};
    unsigned GetFormID() const { return formID; }
    bool IsGold() const { return formID == 0xF; }
    bool IsKey() const { return category == ItemCategory::Keys; }
    template<class T> T* As() {
        static T object;
        if constexpr (std::is_same_v<T, TESAmmo>) return category == ItemCategory::Ammunition ? &object : nullptr;
        else if constexpr (std::is_same_v<T, ScrollItem>) return nativeScroll ? &object : nullptr;
        else if constexpr (std::is_same_v<T, TESObjectBOOK>) return nativeBook ? &book : nullptr;
        else if constexpr (std::is_same_v<T, TESObjectMISC>) return category == ItemCategory::PreciousIngot ? &object : nullptr;
        else if constexpr (std::is_same_v<T, IngredientItem>) return category == ItemCategory::Ingredient || category == ItemCategory::Catalyst || category == ItemCategory::Reagent ? &ingredient : nullptr;
        else if constexpr (std::is_same_v<T, TESObjectARMO>) return nativeArmor ? &armor : nullptr;
        else return nullptr;
    }
};
struct InventoryEntryData {
    bool quest = false, favorite = false, worn = false;
    bool IsQuestObject() const { return quest; }
    bool IsFavorited() const { return favorite; }
    bool IsWorn() const { return worn; }
};
struct TESObjectREFR;
struct Handle {
    TESObjectREFR* object;
    struct Pointer {
        TESObjectREFR* object;
        operator bool() const { return object != nullptr; }
        TESObjectREFR* get() const { return object; }
    };
    Pointer get() const;
};
struct TESObjectREFR {
    int removeLimit = INT_MAX, removeCalls = 0;
    bool rejectMove = false;
    bool alive = true;
    Handle GetHandle() { return {this}; }
    struct Changes {
        TESObjectREFR* owner;
        void RemoveAllItems(TESObjectREFR*, TESObjectREFR* destination, bool, bool, bool) {
            const auto snapshot = owner->inventory;
            for (const auto& [item, entry] : snapshot)
                if (item && entry.first > 0)
                    {
                        owner->inventory[item].first -= entry.first;
                        destination->inventory[item].first += entry.first;
                        if (!destination->inventory[item].second) destination->inventory[item].second = std::make_shared<InventoryEntryData>();
                    }
        }
    } changes{this};
    Changes* GetInventoryChanges() { return &changes; }
    std::map<TESBoundObject*, std::pair<int, std::shared_ptr<InventoryEntryData>>> inventory;
    auto GetInventory() const { return inventory; }
    auto GetInventoryCounts(std::function<bool(TESBoundObject&)> filter = [](auto&) { return true; }) const {
        std::map<TESBoundObject*, int> counts;
        for (auto& [item, data] : inventory) if (filter(*item)) counts[item] = data.first;
        return counts;
    }
    void RemoveItem(TESBoundObject* item, int count, ITEM_REMOVE_REASON, void*, TESObjectREFR* destination) {
        assert(count > 0 && count <= inventory.at(item).first);
        ++removeCalls;
        if (rejectMove) return;
        count = std::min(count, removeLimit);
        inventory.at(item).first -= count;
        destination->inventory[item].first += count;
        if (!destination->inventory[item].second) destination->inventory[item].second = std::make_shared<InventoryEntryData>();
    }
};
Handle::Pointer Handle::get() const { return {object && object->alive ? object : nullptr}; }
struct PlayerCharacter : TESObjectREFR {
    static PlayerCharacter* GetSingleton() { static PlayerCharacter player; return &player; }
};
struct SCRIPT_FUNCTION {
    using Condition_t = bool(TESObjectREFR*, void*, void*, double&);
    Condition_t* conditionFunction = nullptr;
    inline static bool available = true, succeeds = true;
    inline static int calls = 0;
    inline static std::unordered_set<TESBoundObject*> equipped;
    static bool GetEquipped(TESObjectREFR* actor, void* item, void* other, double& result) {
        assert(actor == PlayerCharacter::GetSingleton() && !other);
        ++calls; result = equipped.contains(static_cast<TESBoundObject*>(item)) ? 1.0 : 0.0;
        return succeeds;
    }
    static SCRIPT_FUNCTION* LocateScriptCommand(std::string_view name) {
        assert(name == "GetEquipped");
        static SCRIPT_FUNCTION command{GetEquipped}; return available ? &command : nullptr;
    }
};
struct SendHUDMessage { static void ShowHUDMessage(const char*) {} };
}
struct Utility {
    RE::TESObjectREFR chest, inbox, ammunition, treasure, smithing, armor, valuables, junk, notes, spellTomes, skillBooks, recipes, treasureMaps;
    RE::TESObjectREFR* scrollContainer = nullptr;
    std::unordered_set<unsigned> SmithingMap, SmeltingMap, TanningMap, ConstructionMap, RawFoodMap;
    bool isSmithing(unsigned id) const { return SmithingMap.contains(id) || SmeltingMap.contains(id) || TanningMap.contains(id) || ConstructionMap.contains(id); }
    BenchType bench = BenchType::Smithing;
    BenchType GetBenchType(RE::TESObjectREFR*) { return bench; }
    bool missingSmithing = false;
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    RE::TESObjectREFR* GetContainer(Container container) {
        switch (container) {
        case Container::None: return nullptr;
        case Container::Junk: return &junk;
        case Container::Notes: return &notes;
        case Container::SpellTomes: return &spellTomes;
        case Container::SkillBooks: return &skillBooks;
        case Container::Recipes: return &recipes;
        case Container::TreasureMaps: return &treasureMaps;
        case Container::Scroll: return scrollContainer ? scrollContainer : &chest;
        case Container::Sort: return &inbox;
        case Container::Ignore: return &inbox;
        case Container::Ammunition: return &ammunition;
        case Container::Treasure: return &treasure;
        case Container::Smithing: return missingSmithing ? nullptr : &smithing;
        case Container::Armor: return &armor;
        case Container::Valuables: return &valuables;
        default: return &chest;
        }
    }
};
'''
biped_source = (ROOT / "lib/commonlibsse-ng/src/RE/B/BGSBipedObjectForm.cpp").read_text()
for name in ["IsClothing", "IsLightArmor", "IsHeavyArmor", "IsAccessory", "IsHelmet", "IsCirclet", "IsChestpiece", "IsBoots", "IsGauntlets", "IsShield"]:
    start = biped_source.index(f"bool BGSBipedObjectForm::{name}(")
    body = biped_source[start:biped_source.index("\n\t}", start) + 3]
    program += body.replace("BGSBipedObjectForm::", "RE::TESObjectARMO::") + "\n"
item_source = (ROOT / "src/ItemClass.cpp").read_text()
program += item_source[item_source.index("CategoryMask ToMask("):item_source.index("CategoryMask ParseCategories(")]
program += item_source[item_source.index("bool HasCategory("):item_source.index("CategoryMask ClassifyItem(")]
program += r'''
namespace Soulgems {
    void Recover() {} void Deposit(int, bool = false) {} void BeginLoan(bool) {} void EndLoan() {} void ResetLoan() {}
    void Split() {} void Consolidate() {}
    std::optional<int> lastTarget;
    int withdrawals = 0;
    void TakeEmpty(std::optional<int> target = std::nullopt) { lastTarget=target; ++withdrawals; }
}
const char* Translate(const char* key) {
    if (std::string_view{key} == "Vault.KeepAmount") return "Keep";
    if (std::string_view{key} == "Vault.Septims") return "Septims";
    if (std::string_view{key} == "Vault.TakeUpToAmount") return "Take Up To";
    return key;
}
const char* Translate(const std::string& key) { return Translate(key.c_str()); }

struct MenuOption { std::string text; std::function<void()> action; };
struct Stores {
    void PlayerToStore(ItemCategory, Container, int = 0, int = 0, bool = false);
    std::unordered_map<unsigned, std::pair<int,int>> junkLoan_;
    void BeginJunkLoan();
    void EndJunkLoan();
    void ResetJunkLoan() { junkLoan_.clear(); }
    void ReturnIgnoredItems();
    void FinishIgnorePicker();
    void OffloadItems();
    void StoreToStore(ItemCategory, Container, Container);
    void SortItems();
    void StoreToPlayer(ItemCategory, Container, int = 0, std::optional<int> = std::nullopt);
    void AllToStore(Container, Container);
    void AllToPlayer(Container);
    void ShowArmorJewelryMenu(RE::TESObjectREFR*);
    void EmptySoulgemsMenu(RE::TESObjectREFR*);
    void KeysMenu(RE::TESObjectREFR*);
    void ShowKeysMenu(RE::TESObjectREFR*);
    void BookMenu(RE::TESObjectREFR*);
    void ConsolidateBooks();
    void NotesMenu(RE::TESObjectREFR*);
    void ShowNotesMenu(RE::TESObjectREFR*);
    void ShowBookArchives(Container,RE::TESObjectREFR*);
    void OpenBookArchive(Container,Container,ItemCategory,RE::TESObjectREFR*,bool = false);
    void ShowBookMenu(RE::TESObjectREFR*);
    void ScrollMenu(RE::TESObjectREFR*);
    void ShowScrollMenu(RE::TESObjectREFR*);
    inline static Stores* instance = nullptr;
    Stores() { instance = this; }
    static Stores* GetSingleton() { return instance; }
    void ReturnValuables();
    void ShowValuablesMenu(RE::TESObjectREFR*);
    void ValuablesMenu(RE::TESObjectREFR*);
    void ShowTreasureMenu(RE::TESObjectREFR*);
    void ShowAlchemyMenu(RE::TESObjectREFR*);
    void AlchemyMenu(RE::TESObjectREFR*);
    void TreasureMenu(RE::TESObjectREFR* source) { ShowTreasureMenu(source); }
    void OpenStoreObject(RE::TESObjectREFR* source, std::function<void(RE::TESObjectREFR*)> action) { action(source); }
    void CloseStoreObject(RE::TESObjectREFR*) { closed = true; }
    bool closed = false;
    std::vector<MenuOption> options;
    std::string title;
    Container opened = Container::None;
    std::function<void()> onClose;
    void ShowDynamicMessageBox(std::string_view text, std::vector<MenuOption> values, int cancel) {
        assert(cancel >= 0 && cancel < static_cast<int>(values.size()));
        assert(values.at(cancel).text == "Vault.Exit");
        title = text; options = std::move(values);
    }
    void OpenStorageMenu(Container container, RE::TESObjectREFR* source, std::function<void(RE::TESObjectREFR*)> action) {
        assert(container == Container::Valuables || container == Container::Treasure || container == Container::Alchemy || container == Container::Jewelry || container == Container::EmptySoulgems || container == Container::Keys || container == Container::Book || container == Container::Scroll || container == Container::Notes || container == Container::SpellTomes || container == Container::SkillBooks || container == Container::Recipes || container == Container::TreasureMaps);
        opened = container;
        onClose = [source, action] { action(source); };
    }
};
struct CSimpleIniA {
    std::string text;
    bool exists = true;
    bool KeyExists(const char*, const char*) { return exists; }
    bool GetBoolValue(const char*, const char*, bool fallback) { return fallback; }
    const char* GetValue(const char*, const char*, const char*) { return text.c_str(); }
};
namespace std {
    template<class... Args> string format(const char* text, Args... args) {
        string result{text};
        const auto replace = [&](const auto& arg) {
            ostringstream value; value << arg;
            const auto at = result.find("{}");
            if (at != string::npos) result.replace(at, 2, value.str());
        };
        (replace(args), ...);
        return result;
    }
}
'''
program += "struct Settings {\n" + settings_fields + r'''
    std::optional<CategoryMask> override;
    std::optional<CategoryMask> FindOverride(RE::TESBoundObject* item) {
        if (override) return override;
        if (overrides.contains(item)) return overrides.at(item);
        return std::nullopt;
    }
    std::unordered_set<const RE::TESBoundObject*> ignored;
    bool saveFails = false;
    bool IsIgnored(const RE::TESBoundObject* item) const { return ignored.contains(item); }
    bool AddIgnoredItem(RE::TESBoundObject* item) { if (item->formID == 0xFF000001) return false; ignored.insert(item); return true; }
    bool SaveIgnoredItems() const { return !saveFails; }
    std::map<RE::TESBoundObject*, CategoryMask> overrides;
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    template <class Func> void ForEachINIOption(Settings&, Func&&);
    template <class T> void get_value(CSimpleIniA&, T&, const char*, const char*);
    template <class T> void set_value(CSimpleIniA& ini, const T& value, const char*, const char*) {
        ini.text = std::to_string(value);
    }
};
'''
move_start = source.index("    void MoveItems(")
program += source[move_start:source.index("\n    }", move_start) + 6]
program += classification + method + offload + store_to_store + sort_items + extra_methods + ini_options + get_value
events = (ROOT / "src/Events.cpp").read_text()
loan_start = events.index("class CraftingLoanState {")
program += events[loan_start:events.index("\n};", loan_start) + 3]
program += r'''
int main() {
    static_assert(static_cast<unsigned>(Container::Staff) == 32);
    static_assert(static_cast<unsigned>(ItemCategory::None) == 35);
    static_assert(static_cast<unsigned>(ItemCategory::Keys) == 36);
    static_assert(static_cast<unsigned>(Container::Keys) == 33);
    static_assert(static_cast<unsigned>(ItemCategory::Ammunition) < 64);
    auto* player = RE::PlayerCharacter::GetSingleton();
    auto& chest = Utility::GetSingleton()->chest;
    RE::TESBoundObject a{ItemCategory::Keys}, b{ItemCategory::Keys}, nonkey{ItemCategory::Book};
    RE::TESBoundObject quest{ItemCategory::Keys}, favorite{ItemCategory::Keys}, worn{ItemCategory::Keys};
    auto put = [&](RE::TESBoundObject* item, int count, bool q = false, bool f = false, bool w = false) {
        player->inventory[item] = {count, std::make_shared<RE::InventoryEntryData>(q, f, w)};
    };
    put(&a, 5); put(&b, 1); put(&nonkey, 7);
    put(&quest, 3, true); put(&favorite, 4, false, true); put(&worn, 2, false, false, true);
    Stores stores;
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys, 0, true);
    assert(player->inventory[&a].first == 1 && chest.inventory[&a].first == 4);
    assert(player->inventory[&b].first == 1 && !chest.inventory.contains(&b));
    assert(player->inventory[&nonkey].first == 7);
    assert(player->inventory[&quest].first == 3 && player->inventory[&favorite].first == 4 && player->inventory[&worn].first == 2);
    chest.inventory[&b].first = 8;
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys, 0, true);
    assert(player->inventory[&a].first == 1 && chest.inventory[&a].first == 4);
    assert(player->inventory[&b].first == 1 && chest.inventory[&b].first == 8);
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys);
    assert(player->inventory[&a].first == 0 && chest.inventory[&a].first == 5);
    assert(player->inventory[&b].first == 0 && chest.inventory[&b].first == 9);
    put(&a, 20000);
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys, 0, true);
    assert(player->inventory[&a].first == 1 && chest.inventory[&a].first == 20004);
    put(&nonkey, 5);
    stores.PlayerToStore(ItemCategory::Book, Container::Book, 3);
    assert(player->inventory[&nonkey].first == 2 && chest.inventory[&nonkey].first == 3);
    stores.PlayerToStore(ItemCategory::Book, Container::Book, 3);
    assert(player->inventory[&nonkey].first == 0 && chest.inventory[&nonkey].first == 5);
    put(&a, 4);
    stores.PlayerToStore(ItemCategory::Keys, Container::None, 0, true);
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys, -1);
    assert(player->inventory[&a].first == 4);
    player->inventory[nullptr] = {3, std::make_shared<RE::InventoryEntryData>()};
    player->inventory[&a].second.reset();
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys);
    assert(player->inventory[&a].first == 4);
    auto* settings = Settings::GetSingleton();
    std::map<std::pair<std::string, std::string>, int> options;
    settings->ForEachINIOption(*settings, [&](auto& value, const char* section, const char* key) {
        options[{section, key}] = value;
    });
    assert(options.at({"General", "SoulgemKeepAmount"}) == 25);
    assert(options.at({"General", "AlchemyKeepAmount"}) == 1);
    assert(options.at({"General", "ScrollKeepAmount"}) == 3);
    assert(options.at({"General", "ReturnIgnoredItems"}) == 1);
    assert(options.at({"Offload", "Notes"}) == 0);
    assert(options.at({"Offload", "Soulgems"}) == 1);
    assert(!options.contains({"Offload", "GrandSoulgem"}));
    assert(options.at({"General", "GoldKeepAmount"}) == 5000);
    assert(options.at({"Offload", "Gold"}) == 1);
    assert(options.at({"General", "AmmunitionKeepAmount"}) == 100);
    assert(options.at({"Offload", "Ammunition"}) == 1);
    assert(options.at({"Offload", "Keys"}) == 1 && options.at({"Offload", "KeysKeepOne"}) == 1);
    put(&a, 4);
    stores.OffloadItems();
    assert(player->inventory[&a].first == 1);
    settings->GSC_KeysKeepOne = false;
    stores.OffloadItems();
    assert(player->inventory[&a].first == 0);
    settings->GSC_OffloadKeys = false;
    put(&a, 4);
    stores.OffloadItems();
    assert(player->inventory[&a].first == 4);
    auto& ammoChest = Utility::GetSingleton()->ammunition;
    player->inventory.clear(); ammoChest.inventory.clear();
    RE::TESBoundObject arrows{ItemCategory::Ammunition}, bolts{ItemCategory::Ammunition, true};
    assert(ClassifyItem(&arrows) == ToMask(ItemCategory::Ammunition));
    assert(ClassifyItem(&bolts) == ToMask(ItemCategory::Ammunition));
    settings->override = ToMask(ItemCategory::Book);
    assert(ClassifyItem(&arrows) == ToMask(ItemCategory::Book));
    settings->override.reset();
    assert(ClassifyItem(nullptr) == 0);
    RE::TESBoundObject equipped{ItemCategory::Ammunition}, ammoQuest{ItemCategory::Ammunition}, ammoFavorite{ItemCategory::Ammunition};
    put(&arrows, 250); put(&bolts, 40); put(&equipped, 300, false, false, true);
    put(&ammoQuest, 300, true); put(&ammoFavorite, 300, false, true); put(&nonkey, 7);
    stores.OffloadItems();
    assert(player->inventory[&arrows].first == 100 && ammoChest.inventory[&arrows].first == 150);
    assert(player->inventory[&bolts].first == 40 && !ammoChest.inventory.contains(&bolts));
    assert(player->inventory[&equipped].first == 300 && player->inventory[&ammoQuest].first == 300);
    assert(player->inventory[&ammoFavorite].first == 300 && player->inventory[&nonkey].first == 7);
    stores.OffloadItems();
    assert(player->inventory[&arrows].first == 100 && ammoChest.inventory[&arrows].first == 150);
    settings->GSC_AmmunitionKeepAmount = 25;
    stores.OffloadItems();
    assert(player->inventory[&arrows].first == 25 && player->inventory[&bolts].first == 25);
    settings->GSC_OffloadAmmunition = false;
    put(&arrows, 250);
    stores.OffloadItems();
    assert(player->inventory[&arrows].first == 250);
    stores.PlayerToStore(ItemCategory::Ammunition, Container::Ammunition, 0, 10);
    assert(player->inventory[&arrows].first == 10 && player->inventory[&bolts].first == 10);
    stores.PlayerToStore(ItemCategory::Ammunition, Container::Ammunition, 0, -1);
    assert(player->inventory[&arrows].first == 10);
    settings->GSC_OffloadAmmunition = true;
    settings->GSC_AmmunitionKeepAmount = 0;
    stores.OffloadItems();
    assert(player->inventory[&arrows].first == 0 && player->inventory[&bolts].first == 0);
    put(&arrows, INT_MAX);
    stores.PlayerToStore(ItemCategory::Ammunition, Container::Ammunition, 0, INT_MAX);
    assert(player->inventory[&arrows].first == INT_MAX);
    put(&arrows, 25000); ammoChest.inventory.clear();
    stores.PlayerToStore(ItemCategory::Ammunition, Container::Ammunition, 0, 100);
    assert(player->inventory[&arrows].first == 100 && ammoChest.inventory[&arrows].first == 24900);
    auto& inbox = Utility::GetSingleton()->inbox;
    inbox.inventory[&arrows] = {25000, std::make_shared<RE::InventoryEntryData>()};
    stores.SortItems();
    assert(inbox.inventory[&arrows].first == 0 && ammoChest.inventory[&arrows].first == 49900);
    CSimpleIniA ini;
    int amount = 100;
    for (const auto text : {"0", "1", "25", "100", "2147483647"}) {
        ini.text = text;
        settings->get_value(ini, amount, "General", "AmmunitionKeepAmount");
        assert(amount == std::stoi(text));
    }
    for (const auto text : {"", "-1", "1.5", "abc", "100x", "2147483648", "9999999999999999999"}) {
        ini.text = text; amount = 25;
        settings->get_value(ini, amount, "General", "AmmunitionKeepAmount");
        assert(amount == 100);
    }
    ini.exists = false; amount = 100;
    settings->get_value(ini, amount, "General", "AmmunitionKeepAmount");
    assert(amount == 100 && ini.text == "100");
    ini.exists = true; ini.text = "-1";
    settings->get_value(ini, amount, "General", "AssignKeyCode");
    assert(amount == -1);
    player->inventory.clear();
    auto* utility = Utility::GetSingleton();
    auto& treasury = utility->treasure;
    treasury.inventory.clear();
    RE::TESBoundObject gold{ItemCategory::Gold, false, 0xF}, trinket{ItemCategory::Treasure};
    assert(ClassifyItem(&gold) == ToMask(ItemCategory::Gold));
    assert(!HasCategory(ClassifyItem(&gold), ItemCategory::Treasure));
    settings->override = ToMask(ItemCategory::Treasure);
    assert(ClassifyItem(&gold) == ToMask(ItemCategory::Treasure));
    settings->override.reset();
    put(&gold, 12000); settings->GSC_OffloadTreasure = true;
    stores.OffloadItems();
    assert(player->inventory[&gold].first == 5000 && treasury.inventory[&gold].first == 7000);
    stores.OffloadItems();
    assert(player->inventory[&gold].first == 5000 && treasury.inventory[&gold].first == 7000);
    put(&gold, 3000); stores.OffloadItems();
    assert(player->inventory[&gold].first == 3000 && treasury.inventory[&gold].first == 7000);
    settings->GSC_GoldKeepAmount = 2000; stores.OffloadItems();
    assert(player->inventory[&gold].first == 2000 && treasury.inventory[&gold].first == 8000);
    settings->GSC_OffloadGold = false; put(&gold, 12000); stores.OffloadItems();
    assert(player->inventory[&gold].first == 12000);
    settings->GSC_OffloadGold = true; settings->GSC_GoldKeepAmount = 0; stores.OffloadItems();
    assert(player->inventory[&gold].first == 0 && treasury.inventory[&gold].first == 20000);
    put(&gold, 10000, true); stores.OffloadItems();
    assert(player->inventory[&gold].first == 10000);
    put(&gold, 10000, false, true); stores.OffloadItems();
    assert(player->inventory[&gold].first == 10000);
    put(&gold, 10000, false, false, true); stores.OffloadItems();
    assert(player->inventory[&gold].first == 10000);
    inbox.inventory.clear();
    inbox.inventory[&gold] = {30000, std::make_shared<RE::InventoryEntryData>()};
    settings->GSC_GoldKeepAmount = 5000;
    stores.SortItems();
    assert(inbox.inventory[&gold].first == 0 && treasury.inventory[&gold].first == 50000);
    stores.StoreToPlayer(ItemCategory::Gold, Container::Treasure, 60000);
    assert(treasury.inventory[&gold].first == 0 && player->inventory[&gold].first == 60000);
    treasury.inventory[&gold].first = 15;
    stores.StoreToPlayer(ItemCategory::Gold, Container::Treasure, -1);
    assert(treasury.inventory[&gold].first == 15);
    stores.StoreToPlayer(ItemCategory::Gold, Container::Treasure, 5);
    assert(treasury.inventory[&gold].first == 10);
    stores.StoreToPlayer(ItemCategory::Gold, Container::Treasure);
    assert(treasury.inventory[&gold].first == 0);

    RE::TESBoundObject goldIngot{ItemCategory::PreciousIngot, false, 0x5AD9E};
    RE::TESBoundObject silverIngot{ItemCategory::PreciousIngot, false, 0x5ACE3};
    RE::TESBoundObject ironIngot{ItemCategory::PreciousIngot, false, 0x5ACE4};
    utility->SmithingMap = {goldIngot.formID, silverIngot.formID, ironIngot.formID};
    utility->SmeltingMap.insert(goldIngot.formID);
    utility->ConstructionMap.insert(silverIngot.formID);
    assert(HasAllCategories(ClassifyItem(&goldIngot), ItemCategory::PreciousIngot | ItemCategory::Smithing | ItemCategory::Crafting | ItemCategory::Smelting));
    assert(HasAllCategories(ClassifyItem(&silverIngot), ItemCategory::PreciousIngot | ItemCategory::Smithing | ItemCategory::Crafting | ItemCategory::Construction));
    assert(!HasCategory(ClassifyItem(&ironIngot), ItemCategory::PreciousIngot));
    assert(HasCategory(ExpandCategories(ToMask(ItemCategory::PreciousIngot)), ItemCategory::Smithing));
    settings->override = ToMask(ItemCategory::Treasure);
    assert(ClassifyItem(&goldIngot) == ToMask(ItemCategory::Treasure));
    settings->override.reset();
    RE::TESBoundObject gem{ItemCategory::Gemstone}, ring{ItemCategory::Jewelry}, armor{ItemCategory::HeavyArmor};
    settings->overrides[&gem] = ToMask(ItemCategory::Gemstone);
    auto entry = [](int count) { return std::pair{count, std::make_shared<RE::InventoryEntryData>()}; };
    auto& smithing = utility->smithing;
    auto& armorVault = utility->armor;
    auto& valuables = utility->valuables;
    player->inventory.clear(); treasury.inventory.clear();
    smithing.inventory.clear(); armorVault.inventory.clear(); valuables.inventory.clear();
    RE::TESObjectREFR source;
    auto click = [&](int index) { auto action = stores.options.at(index).action; action(); };
    put(&gold, 25000); treasury.inventory[&trinket] = entry(9);
    stores.ValuablesMenu(&source);
    assert(stores.title == "Vault.Valuables Vault.Archive" && stores.options.size() == 5);
    assert(stores.options[0].text == "Vault.ValuablesOpen");
    assert(stores.options[1].text == "Vault.Exit");
    assert(stores.options[2].text == "Keep 5000 Septims");
    assert(stores.options[3].text == "Vault.StoreAllSeptims");
    assert(stores.options[4].text == "Vault.TakeAllSeptims");
    click(2);
    assert(player->inventory[&gold].first == 5000 && treasury.inventory[&gold].first == 20000);
    settings->GSC_GoldKeepAmount = 2500;
    stores.ValuablesMenu(&source);
    assert(stores.options[2].text == "Keep 2500 Septims");
    click(2);
    assert(player->inventory[&gold].first == 2500 && treasury.inventory[&gold].first == 22500);
    click(3);
    assert(player->inventory[&gold].first == 0 && treasury.inventory[&gold].first == 25000);
    click(4);
    assert(player->inventory[&gold].first == 25000 && treasury.inventory[&gold].first == 0);
    assert(treasury.inventory[&trinket].first == 9);
    click(3);
    smithing.inventory[&gem] = entry(12);
    smithing.inventory[&goldIngot] = entry(4); smithing.inventory[&silverIngot] = entry(6);
    smithing.inventory[&ironIngot] = entry(8);
    armorVault.inventory[&ring] = entry(3); armorVault.inventory[&armor] = entry(2);
    click(0);
    assert(valuables.inventory[&gold].first == 25000 && valuables.inventory[&gem].first == 12);
    assert(valuables.inventory[&goldIngot].first == 4 && valuables.inventory[&silverIngot].first == 6);
    assert(valuables.inventory[&ring].first == 3);
    assert(smithing.inventory[&ironIngot].first == 8 && armorVault.inventory[&armor].first == 2);
    assert(treasury.inventory[&trinket].first == 9);
    valuables.inventory[&gold].first -= 1000;
    valuables.inventory[&goldIngot].first += 2; valuables.inventory[&gem].first += 1;
    valuables.inventory[&ring].first += 1; valuables.inventory[&nonkey] = entry(5);
    auto closeArchive = stores.onClose; stores.onClose = {}; closeArchive();
    assert(treasury.inventory[&gold].first == 24000 && treasury.inventory[&nonkey].first == 5);
    assert(smithing.inventory[&goldIngot].first == 6 && smithing.inventory[&silverIngot].first == 6 && smithing.inventory[&gem].first == 13);
    assert(armorVault.inventory[&ring].first == 4);
    for (const auto& [item, value] : valuables.inventory) { (void)item; assert(value.first == 0); }
    click(0);
    assert(valuables.inventory[&gold].first == 24000 && valuables.inventory[&ring].first == 4);
    stores.ReturnValuables();
    stores.ReturnValuables();
    assert(treasury.inventory[&gold].first == 24000 && armorVault.inventory[&ring].first == 4);
    valuables.inventory[&gem] = entry(2);
    utility->missingSmithing = true;
    stores.ReturnValuables();
    assert(valuables.inventory[&gem].first == 2 && !treasury.inventory.contains(&gem));
    utility->missingSmithing = false;
    stores.ValuablesMenu(&source);
    assert(valuables.inventory[&gem].first == 0 && smithing.inventory[&gem].first == 15);
    click(1); assert(stores.closed);
    stores.options.clear(); stores.closed = false;
    stores.ShowTreasureMenu(&source);
    assert(stores.options.empty() && stores.opened == Container::Treasure);
    auto closeTreasure = stores.onClose; closeTreasure(); assert(stores.closed);
    stores.ValuablesMenu(&source);
    source.alive = false;
    const int previousGold = treasury.inventory[&gold].first;
    click(0);
    assert(treasury.inventory[&gold].first == previousGold);
    ini.exists = true;
    for (const auto text : {"0", "5000", "10000", "2147483647"}) {
        ini.text = text;
        settings->get_value(ini, amount, "General", "GoldKeepAmount");
        assert(amount == std::stoi(text));
    }
    for (const auto text : {"", "-1", "1.5", "abc", "5000x", "2147483648"}) {
        ini.text = text; amount = 25;
        settings->get_value(ini, amount, "General", "GoldKeepAmount");
        assert(amount == 5000);
    }
    ini.exists = false; amount = 5000;
    settings->get_value(ini, amount, "General", "GoldKeepAmount");
    assert(amount == 5000 && ini.text == "5000");

    ini.exists = true;
    for (const auto text : {"0", "25", "100", "2147483647"}) {
        ini.text = text;
        settings->get_value(ini, amount, "General", "SoulgemKeepAmount");
        assert(amount == std::stoi(text));
    }
    for (const auto text : {"", "-1", "1.5", "abc", "25x", "2147483648"}) {
        ini.text = text; amount = 100;
        settings->get_value(ini, amount, "General", "SoulgemKeepAmount");
        assert(amount == 25);
    }

    assert(options.at({"General", "SalePercentage"}) == 30);
    for (const char* text : {"0", "101", "-1", "30x", "", "9999999999999999999"}) {
        ini.text = text;
        int amount = 1;
        settings->get_value(ini, amount, "General", "SalePercentage");
        assert(amount == 30);
    }
    for (int expected : {1, 30, 100}) {
        ini.text = std::to_string(expected);
        int amount = 0;
        settings->get_value(ini, amount, "General", "SalePercentage");
        assert(amount == expected);
    }

    inbox.inventory.clear(); chest.inventory.clear();
    RE::TESBoundObject ordinary{ItemCategory::Ingredient, false, 2000};
    RE::TESBoundObject craftingIngredient{ItemCategory::Catalyst, false, 2001};
    RE::TESBoundObject cookingIngredient{ItemCategory::Reagent, false, 2002};
    RE::TESBoundObject foodIngredient{ItemCategory::Reagent, false, 2003};
    RE::TESBoundObject overriddenIngredient{ItemCategory::Ingredient, false, 2004};
    RE::TESBoundObject unmatched{ItemCategory::None, false, 2005};
    utility->ConstructionMap.insert(craftingIngredient.formID);
    utility->RawFoodMap.insert(cookingIngredient.formID);
    foodIngredient.ingredient.food = true;
    settings->overrides[&overriddenIngredient] = ToMask(ItemCategory::Reagent);
    for (auto* item : {&ordinary, &craftingIngredient, &cookingIngredient, &foodIngredient, &overriddenIngredient}) {
        assert(HasCategory(ClassifyItem(item), ItemCategory::Alchemy));
        inbox.inventory[item] = entry(12);
    }
    assert(HasCategory(ClassifyItem(&ordinary), ItemCategory::Ingredient));
    assert(HasCategory(ClassifyItem(&craftingIngredient), ItemCategory::Catalyst));
    assert(HasCategory(ClassifyItem(&cookingIngredient), ItemCategory::Reagent));
    inbox.inventory[&unmatched] = entry(7);
    stores.SortItems();
    for (auto* item : {&ordinary, &craftingIngredient, &cookingIngredient, &foodIngredient, &overriddenIngredient}) {
        assert(inbox.inventory[item].first == 0 && chest.inventory[item].first == 12);
    }
    assert(inbox.inventory[&unmatched].first == 0 && utility->junk.inventory[&unmatched].first == 7);
    stores.SortItems();
    assert(chest.inventory[&ordinary].first == 12);
    player->inventory.clear(); chest.inventory.clear(); source.alive = true;
    for (auto* item : {&ordinary, &craftingIngredient, &cookingIngredient, &foodIngredient, &overriddenIngredient})
        player->inventory[item] = entry(12);
    RE::TESBoundObject questIngredient{ItemCategory::Ingredient}, favoriteIngredient{ItemCategory::Ingredient}, wornIngredient{ItemCategory::Ingredient};
    player->inventory[&questIngredient] = entry(4); player->inventory[&questIngredient].second->quest = true;
    player->inventory[&favoriteIngredient] = entry(5); player->inventory[&favoriteIngredient].second->favorite = true;
    player->inventory[&wornIngredient] = entry(6); player->inventory[&wornIngredient].second->worn = true;
    player->inventory[&unmatched] = entry(7);
    stores.AlchemyMenu(&source);
    assert(stores.options[0].text == "Vault.StoreAll"); click(0);
    for (auto* item : {&ordinary, &craftingIngredient, &cookingIngredient, &foodIngredient, &overriddenIngredient})
        assert(player->inventory[item].first == 0 && chest.inventory[item].first == 12);
    assert(player->inventory[&questIngredient].first == 4);
    assert(player->inventory[&favoriteIngredient].first == 5);
    assert(player->inventory[&wornIngredient].first == 6);
    assert(player->inventory[&unmatched].first == 7);
    click(0); assert(chest.inventory[&ordinary].first == 12);

    assert(utility->junk.inventory[&unmatched].first == 7);
    chest.inventory.clear(); armorVault.inventory.clear(); valuables.inventory.clear();
    RE::TESBoundObject helmet{ItemCategory::None}, hat{ItemCategory::None}, robe{ItemCategory::None}, nativeRing{ItemCategory::None}, circlet{ItemCategory::None};
    for (auto* item : {&helmet, &hat, &robe, &nativeRing, &circlet}) item->nativeArmor = true;
    helmet.armor.bipedModelData.bipedObjectSlots.bits = 1 | 2 | 4096;
    helmet.armor.bipedModelData.armorType = RE::BIPED_MODEL::ArmorType::kHeavyArmor;
    hat.armor.bipedModelData.bipedObjectSlots.bits = 2 | 4096;
    robe.armor.bipedModelData.bipedObjectSlots.bits = 4 | 32;
    nativeRing.armor.bipedModelData.bipedObjectSlots.bits = 64;
    circlet.armor.bipedModelData.bipedObjectSlots.bits = 4096;
    for (auto* item : {&helmet, &hat, &robe}) assert(!HasCategory(ClassifyItem(item), ItemCategory::Jewelry));
    assert(HasCategory(ClassifyItem(&helmet), ItemCategory::HeavyArmor));
    for (auto* item : {&hat, &robe}) assert(HasCategory(ClassifyItem(item), ItemCategory::Clothing));
    for (auto* item : {&nativeRing, &circlet}) assert(HasCategory(ClassifyItem(item), ItemCategory::Jewelry));
    for (auto* item : {&helmet, &hat, &robe, &nativeRing, &circlet}) armorVault.inventory[item] = entry(3);
    stores.ShowArmorJewelryMenu(&source);
    for (auto* item : {&helmet, &hat, &robe}) assert(armorVault.inventory[item].first == 3 && chest.inventory[item].first == 0);
    assert(chest.inventory[&nativeRing].first == 3 && chest.inventory[&circlet].first == 3);
    auto closeJewelry = stores.onClose; closeJewelry();
    stores.ValuablesMenu(&source); click(0);
    for (auto* item : {&helmet, &hat, &robe}) assert(armorVault.inventory[item].first == 3 && valuables.inventory[item].first == 0);
    assert(valuables.inventory[&nativeRing].first == 3 && valuables.inventory[&circlet].first == 3);
    stores.ReturnValuables();
    settings->overrides[&helmet] = ToMask(ItemCategory::Jewelry);
    assert(HasCategory(ClassifyItem(&helmet), ItemCategory::Jewelry));
    settings->overrides.erase(&helmet);
    RE::TESBoundObject welkynd{ItemCategory::None, false, 0xFE001800};
    settings->overrides[&welkynd] = ToMask(ItemCategory::Treasure);
    inbox.inventory.clear(); treasury.inventory.clear();
    inbox.inventory[&welkynd] = entry(13); stores.SortItems();
    assert(inbox.inventory[&welkynd].first == 0 && treasury.inventory[&welkynd].first == 13);


    player->inventory.clear(); chest.inventory.clear(); treasury.inventory.clear(); inbox.inventory.clear();
    player->removeLimit = 9999; treasury.removeLimit = 9999; inbox.removeLimit = 9999;
    put(&gold, 30000); stores.PlayerToStore(ItemCategory::Gold, Container::Treasure, 0, 5000);
    assert(player->inventory[&gold].first == 5000 && treasury.inventory[&gold].first == 25000);
    stores.StoreToPlayer(ItemCategory::Gold, Container::Treasure);
    assert(player->inventory[&gold].first == 30000 && treasury.inventory[&gold].first == 0);
    inbox.inventory[&gold] = entry(30000); stores.SortItems();
    assert(inbox.inventory[&gold].first == 0 && treasury.inventory[&gold].first == 30000);
    player->rejectMove = true; const int beforeCalls = player->removeCalls;
    stores.PlayerToStore(ItemCategory::Gold, Container::Treasure);
    assert(player->removeCalls == beforeCalls + 1 && player->inventory[&gold].first == 30000);
    player->rejectMove = false;

    smithing.inventory.clear(); player->inventory.clear(); chest.inventory.clear();
    smithing.inventory[&ironIngot] = entry(30000);
    settings->GSC_CraftingLoan = true;
    CraftingLoanState::GetSingleton()->EnterCrafting(&source);
    assert(player->inventory[&ironIngot].first == 30000 && smithing.inventory[&ironIngot].first == 0);
    CraftingLoanState::GetSingleton()->ExitCrafting();
    assert(player->inventory[&ironIngot].first == 0 && smithing.inventory[&ironIngot].first == 30000);
    player->removeLimit = INT_MAX; treasury.removeLimit = INT_MAX; inbox.removeLimit = INT_MAX;

    player->inventory.clear(); armorVault.inventory.clear();
    std::array<RE::TESBoundObject,10> virtualRings{};
    RE::TESBoundObject spare{ItemCategory::Jewelry}, equippedSpare{ItemCategory::Jewelry},
        vanillaWorn{ItemCategory::Jewelry}, protectedQuest{ItemCategory::Jewelry}, protectedFavorite{ItemCategory::Jewelry};
    for (auto& ring : virtualRings) {
        ring.category=ItemCategory::Jewelry; put(&ring,2); RE::SCRIPT_FUNCTION::equipped.insert(&ring);
    }
    put(&spare,3); put(&equippedSpare,4); RE::SCRIPT_FUNCTION::equipped.insert(&equippedSpare);
    put(&vanillaWorn,2,false,false,true); put(&protectedQuest,2,true); put(&protectedFavorite,2,false,true);
    settings->GSC_OffloadJewelry=true; stores.OffloadItems();
    for (auto& ring : virtualRings) assert(player->inventory[&ring].first==2 && armorVault.inventory[&ring].first==0);
    assert(player->inventory[&equippedSpare].first==4 && armorVault.inventory[&equippedSpare].first==0);
    assert(player->inventory[&spare].first==0 && armorVault.inventory[&spare].first==3);
    for (auto* item : {&vanillaWorn,&protectedQuest,&protectedFavorite}) assert(player->inventory[item].first==2);
    // Replacing the standard condition between transfers must be observed.
    auto* command=RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
    command->conditionFunction=[](RE::TESObjectREFR*,void*,void*,double& result) { result=0; return true; };
    stores.PlayerToStore(ItemCategory::Jewelry,Container::Armor);
    for (auto& ring : virtualRings) assert(player->inventory[&ring].first==0 && armorVault.inventory[&ring].first==2);
    assert(player->inventory[&equippedSpare].first==0 && armorVault.inventory[&equippedSpare].first==4);
    command->conditionFunction=RE::SCRIPT_FUNCTION::GetEquipped;
    // Missing or failed conditions retain the existing vanilla protections.
    for (int failure=0; failure<3; ++failure) {
        put(&equippedSpare,2);
        RE::SCRIPT_FUNCTION::available=failure!=0;
        command->conditionFunction=failure==1 ? nullptr : RE::SCRIPT_FUNCTION::GetEquipped;
        RE::SCRIPT_FUNCTION::succeeds=false;
        stores.PlayerToStore(ItemCategory::Jewelry,Container::Armor);
        assert(player->inventory[&equippedSpare].first==0);
        for (auto* item : {&vanillaWorn,&protectedQuest,&protectedFavorite}) assert(player->inventory[item].first==2);
    }
    RE::SCRIPT_FUNCTION::succeeds=true;
    // The condition applies to any matching inventory form, not just rings or armor.
    put(&nonkey,5); RE::SCRIPT_FUNCTION::equipped.insert(&nonkey);
    stores.PlayerToStore(ItemCategory::Book,Container::Book);
    assert(player->inventory[&nonkey].first==5);
    RE::SCRIPT_FUNCTION::equipped.clear(); const int beforeEquipmentCalls=RE::SCRIPT_FUNCTION::calls;
    stores.PlayerToStore(ItemCategory::Book,Container::Book);
    assert(player->inventory[&nonkey].first==0 && RE::SCRIPT_FUNCTION::calls==beforeEquipmentCalls+1);
    settings->GSC_SoulgemKeepAmount=25;stores.EmptySoulgemsMenu(&source);
    assert(stores.options.size()==4 && stores.options[0].text=="Take Up To 25");
    const int beforeWithdrawals=Soulgems::withdrawals;
    settings->GSC_SoulgemKeepAmount=10;click(0);
    assert(Soulgems::withdrawals==beforeWithdrawals+1 && Soulgems::lastTarget==25);
    assert(stores.options[0].text=="Take Up To 10");
    click(1);assert(!Soulgems::lastTarget);
    settings->GSC_SoulgemKeepAmount=0;stores.EmptySoulgemsMenu(&source);click(0);
    assert(Soulgems::lastTarget==0 && stores.options[0].text=="Take Up To 0");
    click(2);assert(stores.opened==Container::EmptySoulgems);stores.onClose();
    assert(stores.options.size()==4);stores.closed=false;click(3);
    assert(stores.closed);
    player->inventory.clear();chest.inventory.clear();
    put(&a,0);put(&b,3);chest.inventory[&a]=entry(4);chest.inventory[&b]=entry(6);
    stores.KeysMenu(&source);assert(stores.options.size()==6 && stores.options[2].text=="Take Up To 1");
    click(2);assert(player->inventory[&a].first==1 && chest.inventory[&a].first==3);
    assert(player->inventory[&b].first==3 && chest.inventory[&b].first==6);
    click(2);assert(player->inventory[&a].first==1 && chest.inventory[&a].first==3);
    click(0);assert(player->inventory[&b].first==1 && chest.inventory[&b].first==8);
    click(3);assert(player->inventory[&a].first==4 && player->inventory[&b].first==9);
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,0);
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,-1);
    assert(player->inventory[&a].first==4);
    player->inventory.clear();chest.inventory.clear();chest.removeLimit=9999;
    chest.inventory[&a]=entry(50000);put(&a,10000);
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,40000);
    assert(player->inventory[&a].first==40000 && chest.inventory[&a].first==20000);
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,1000,45000);
    assert(player->inventory[&a].first==41000 && chest.inventory[&a].first==19000);
    chest.removeLimit=INT_MAX;
    player->inventory.clear();chest.inventory.clear();
    RE::TESBoundObject duplicateBook{ItemCategory::Book};
    chest.inventory[&nonkey]=entry(4);chest.inventory[&duplicateBook]=entry(8);put(&duplicateBook,2);
    stores.BookMenu(&source);assert(stores.options.size()==6 && stores.options[1].text=="Take Up To 1");
    click(1);assert(player->inventory[&nonkey].first==1 && chest.inventory[&nonkey].first==3);
    assert(player->inventory[&duplicateBook].first==2 && chest.inventory[&duplicateBook].first==8);
    click(1);assert(player->inventory[&nonkey].first==1 && chest.inventory[&nonkey].first==3);
    player->inventory[&duplicateBook].second->favorite=true;
    click(0);assert(player->inventory[&nonkey].first==0 && chest.inventory[&nonkey].first==4);
    assert(player->inventory[&duplicateBook].first==2 && chest.inventory[&duplicateBook].first==8);
    click(4);assert(stores.opened==Container::Book);stores.onClose();
    stores.closed=false;click(5);assert(stores.closed);
    player->inventory.clear();chest.inventory.clear();settings->GSC_AlchemyKeepAmount=6;
    for (auto* item : {&ordinary,&craftingIngredient,&cookingIngredient,&foodIngredient,&overriddenIngredient}) {
        put(item,8);chest.inventory[item]=entry(10);
    }
    put(&favoriteIngredient,8,false,true);
    stores.AlchemyMenu(&source);assert(stores.options.size()==7 && stores.options[1].text=="Keep 6" && stores.options[2].text=="Take Up To 6");
    click(1);
    for (auto* item : {&ordinary,&craftingIngredient,&cookingIngredient,&foodIngredient,&overriddenIngredient})
        assert(player->inventory[item].first==6 && chest.inventory[item].first==12);
    assert(player->inventory[&favoriteIngredient].first==8);
    put(&ordinary,2);put(&craftingIngredient,9);chest.inventory[&ordinary].first=1;
    click(2);assert(player->inventory[&ordinary].first==3 && chest.inventory[&ordinary].first==0);
    assert(player->inventory[&craftingIngredient].first==9 && chest.inventory[&craftingIngredient].first==12);
    settings->GSC_AlchemyKeepAmount=0;stores.AlchemyMenu(&source);click(2);
    assert(player->inventory[&ordinary].first==3);click(1);
    for (auto* item : {&ordinary,&craftingIngredient,&cookingIngredient,&foodIngredient,&overriddenIngredient})
        assert(player->inventory[item].first==0);
    assert(player->inventory[&favoriteIngredient].first==8);
    for (const auto* text : {"bad","-1","2147483648","3junk",""}) {
        ini.text=text;amount=8;settings->get_value(ini,amount,"General","AlchemyKeepAmount");assert(amount==1);
    }
    ini.text="0";settings->get_value(ini,amount,"General","AlchemyKeepAmount");assert(amount==0);
    ini.text="7";settings->get_value(ini,amount,"General","AlchemyKeepAmount");assert(amount==7);
    player->inventory.clear();chest.inventory.clear();
    RE::TESBoundObject scrollA{ItemCategory::None}, scrollB{ItemCategory::None}, protectedScroll{ItemCategory::None};
    for (auto* item : {&scrollA,&scrollB,&protectedScroll}) item->nativeScroll=true;
    scrollA.formID=0x12345;scrollB.formID=0xFE123800;
    assert(ClassifyItem(&scrollA)==ToMask(ItemCategory::Scroll) && ClassifyItem(&scrollB)==ToMask(ItemCategory::Scroll));
    settings->GSC_ScrollKeepAmount=3;put(&scrollA,8);put(&scrollB,1);put(&protectedScroll,6,true);
    chest.inventory[&scrollA]=entry(4);chest.inventory[&scrollB]=entry(1);
    stores.ScrollMenu(&source);assert(stores.options.size()==5 && stores.options[1].text=="Keep 3" && stores.options[2].text=="Take Up To 3");
    click(1);assert(player->inventory[&scrollA].first==3 && chest.inventory[&scrollA].first==9);
    assert(player->inventory[&scrollB].first==1 && player->inventory[&protectedScroll].first==6);
    click(2);assert(player->inventory[&scrollA].first==3 && chest.inventory[&scrollA].first==9);
    assert(player->inventory[&scrollB].first==2 && chest.inventory[&scrollB].first==0);
    settings->GSC_ScrollKeepAmount=5;stores.ScrollMenu(&source);click(2);
    assert(player->inventory[&scrollA].first==5 && chest.inventory[&scrollA].first==7);
    settings->GSC_ScrollKeepAmount=0;stores.ScrollMenu(&source);click(2);
    assert(player->inventory[&scrollA].first==5);click(1);
    assert(player->inventory[&scrollA].first==0 && player->inventory[&scrollB].first==0);
    assert(player->inventory[&protectedScroll].first==6);
    click(3);assert(stores.opened==Container::Scroll);stores.onClose();
    stores.closed=false;click(4);assert(stores.closed);
    for (const auto* text : {"bad","-1","2147483648","3junk",""}) {
        ini.text=text;amount=8;settings->get_value(ini,amount,"General","ScrollKeepAmount");assert(amount==3);
    }
    ini.text="0";settings->get_value(ini,amount,"General","ScrollKeepAmount");assert(amount==0);
    ini.text="6";settings->get_value(ini,amount,"General","ScrollKeepAmount");assert(amount==6);
    player->inventory.clear();chest.inventory.clear();inbox.inventory.clear();utility->junk.inventory.clear();
    inbox.inventory[&scrollA]=entry(12);inbox.inventory[&scrollB]=entry(7);stores.SortItems();
    assert(inbox.inventory[&scrollA].first==0 && chest.inventory[&scrollA].first==12);
    assert(inbox.inventory[&scrollB].first==0 && chest.inventory[&scrollB].first==7);
    assert(!utility->junk.inventory.contains(&scrollA) && !utility->junk.inventory.contains(&scrollB));
    chest.inventory.clear();settings->GSC_OffloadScrolls=false;put(&scrollA,9);stores.OffloadItems();
    assert(player->inventory[&scrollA].first==9);
    settings->GSC_OffloadScrolls=true;put(&scrollB,4,false,true);put(&protectedScroll,6,true);stores.OffloadItems();
    assert(player->inventory[&scrollA].first==0 && chest.inventory[&scrollA].first==9);
    assert(player->inventory[&scrollB].first==4 && player->inventory[&protectedScroll].first==6);
    player->inventory[&scrollB].second->favorite=false;player->inventory[&scrollB].second->worn=true;stores.OffloadItems();
    assert(player->inventory[&scrollB].first==4);
    settings->overrides[&scrollA]=ToMask(ItemCategory::Book);
    assert(ClassifyItem(&scrollA)==ToMask(ItemCategory::Book));settings->overrides.erase(&scrollA);
    player->inventory.clear();chest.inventory.clear();inbox.inventory.clear();utility->junk.inventory.clear();
    settings->ignored.insert(&scrollA);put(&scrollA,15);put(&scrollB,4);player->inventory[&scrollB].second->worn=false;
    stores.OffloadItems();assert(player->inventory[&scrollA].first==15 && player->inventory[&scrollB].first==0);
    stores.PlayerToStore(ItemCategory::Scroll,Container::Scroll);assert(player->inventory[&scrollA].first==0);
    inbox.inventory[&scrollA]=entry(15000);inbox.inventory[&scrollB]=entry(4);
    inbox.removeLimit=9999;stores.SortItems();assert(player->inventory[&scrollA].first==15000 && inbox.inventory[&scrollA].first==0);
    assert(chest.inventory[&scrollB].first==8);
    inbox.inventory[&scrollA]=entry(5);inbox.rejectMove=true;stores.SortItems();
    assert(inbox.inventory[&scrollA].first==5 && !utility->junk.inventory.contains(&scrollA));inbox.rejectMove=false;
    settings->GSC_ReturnIgnoredItems=false;stores.SortItems();assert(inbox.inventory[&scrollA].first==0 && chest.inventory[&scrollA].first==20);
    RE::TESBoundObject unknown{ItemCategory::None};settings->ignored.insert(&unknown);inbox.inventory[&unknown]=entry(6);
    settings->GSC_ReturnIgnoredItems=true;stores.SortItems();assert(player->inventory[&unknown].first==6 && !utility->junk.inventory.contains(&unknown));
    inbox.inventory[&unknown]=entry(3);settings->GSC_ReturnIgnoredItems=false;stores.SortItems();assert(utility->junk.inventory[&unknown].first==3);
    settings->GSC_ReturnIgnoredItems=true;
    inbox.inventory.clear();settings->ignored.clear();
    inbox.inventory[&scrollA]=entry(25000);inbox.inventory[&scrollB]=entry(2);settings->saveFails=true;
    stores.FinishIgnorePicker();assert(settings->IsIgnored(&scrollA) && settings->IsIgnored(&scrollB));
    assert(inbox.inventory[&scrollA].first==0 && inbox.inventory[&scrollB].first==0);
    unknown.formID=0xFF000001;inbox.inventory[&unknown]=entry(4);stores.FinishIgnorePicker();
    assert(!settings->IsIgnored(&unknown) && inbox.inventory[&unknown].first==0);
    settings->saveFails=false;

    player->inventory.clear();utility->junk.inventory.clear();chest.inventory.clear();
    RE::TESBoundObject junkMaterial{ItemCategory::None,false,0x123123}, protectedJunk{ItemCategory::None,false,0x123124};
    put(&junkMaterial,7);utility->junk.inventory[&junkMaterial]=entry(25000);utility->junk.inventory[&protectedJunk]=entry(3);utility->junk.inventory[&protectedJunk].second->quest=true;
    player->removeLimit=9999;utility->junk.removeLimit=9999;
    stores.BeginJunkLoan();assert(player->inventory[&junkMaterial].first==25007 && utility->junk.inventory[&junkMaterial].first==0);
    assert(utility->junk.inventory[&protectedJunk].first==3);
    player->inventory[&junkMaterial].first-=11;stores.EndJunkLoan();
    assert(player->inventory[&junkMaterial].first==7 && utility->junk.inventory[&junkMaterial].first==24989);
    stores.EndJunkLoan();assert(player->inventory[&junkMaterial].first==7);
    stores.BeginJunkLoan();player->inventory[&junkMaterial].first=3;stores.EndJunkLoan();
    assert(player->inventory[&junkMaterial].first==3 && utility->junk.inventory[&junkMaterial].first==0);
    utility->junk.inventory[&junkMaterial]=entry(5);stores.BeginJunkLoan();stores.ResetJunkLoan();stores.EndJunkLoan();
    assert(player->inventory[&junkMaterial].first==8 && utility->junk.inventory[&junkMaterial].first==0);
    player->inventory.clear();utility->junk.inventory[&junkMaterial]=entry(5);stores.BeginJunkLoan();
    RE::SCRIPT_FUNCTION::equipped.insert(&junkMaterial);stores.EndJunkLoan();
    assert(player->inventory[&junkMaterial].first==5);RE::SCRIPT_FUNCTION::equipped.erase(&junkMaterial);
    player->inventory.clear();utility->junk.inventory[&junkMaterial]=entry(5);utility->junk.rejectMove=true;
    stores.BeginJunkLoan();assert(player->inventory.empty() && stores.junkLoan_.empty());utility->junk.rejectMove=false;
    settings->GSC_CraftingLoan=true;auto* crafting=CraftingLoanState::GetSingleton();
    crafting->EnterCrafting(&source);assert(player->inventory[&junkMaterial].first==5);
    settings->GSC_CraftingLoan=false;crafting->ExitCrafting();assert(utility->junk.inventory[&junkMaterial].first==5);

    for (auto bench : {BenchType::Alchemy, BenchType::Cooking, BenchType::Enchanting, BenchType::StaffEnchanting}) {
        player->inventory.clear();chest.inventory.clear();utility->junk.inventory.clear();utility->junk.inventory[&junkMaterial]=entry(9);
        utility->bench=bench;settings->GSC_CraftingLoan=true;crafting->EnterCrafting(&source);
        assert(player->inventory[&junkMaterial].first==9 && utility->junk.inventory[&junkMaterial].first==0);
        player->inventory[&junkMaterial].first-=4;crafting->ExitCrafting();
        assert(utility->junk.inventory[&junkMaterial].first==5 && player->inventory[&junkMaterial].first==0);
    }
    utility->bench=BenchType::None;utility->junk.inventory[&junkMaterial]=entry(9);crafting->EnterCrafting(&source);crafting->ExitCrafting();
    assert(utility->junk.inventory[&junkMaterial].first==9);
    utility->bench=BenchType::Smithing;player->inventory.clear();utility->smithing.inventory.clear();utility->junk.inventory.clear();
    junkMaterial.category=ItemCategory::Smithing;put(&junkMaterial,3);utility->smithing.inventory[&junkMaterial]=entry(2);utility->junk.inventory[&junkMaterial]=entry(4);
    crafting->EnterCrafting(&source);assert(player->inventory[&junkMaterial].first==9);
    player->inventory[&junkMaterial].first-=1;crafting->ExitCrafting();
    assert(utility->junk.inventory[&junkMaterial].first==3 && utility->smithing.inventory[&junkMaterial].first==5);
    player->inventory.clear();utility->junk.inventory.clear();junkMaterial.category=ItemCategory::None;
    put(&junkMaterial,INT_MAX-2);utility->junk.inventory[&junkMaterial]=entry(5);stores.BeginJunkLoan();
    assert(player->inventory[&junkMaterial].first==INT_MAX && utility->junk.inventory[&junkMaterial].first==3);
    stores.EndJunkLoan();assert(player->inventory[&junkMaterial].first==INT_MAX-2 && utility->junk.inventory[&junkMaterial].first==5);

    player->inventory.clear();chest.inventory.clear();inbox.inventory.clear();utility->notes.inventory.clear();utility->junk.inventory.clear();
    RE::TESObjectREFR scrollBank;utility->scrollContainer=&scrollBank;settings->ignored.clear();
    RE::TESBoundObject plainBook{ItemCategory::None,false,0x120001}, spellBook{ItemCategory::None,false,0x120002}, skillBook{ItemCategory::None,false,0x120003}, noteBook{ItemCategory::None,false,0x120004}, recipeBook{ItemCategory::None,false,0x120005}, mapBook{ItemCategory::None,false,0x120006};
    for (auto* item : {&plainBook,&spellBook,&skillBook,&noteBook,&recipeBook,&mapBook}) item->nativeBook=true;
    spellBook.book.spell=true;skillBook.book.skill=true;noteBook.book.note=true;recipeBook.book.note=true;recipeBook.book.recipe=true;mapBook.book.note=true;
    settings->overrides[&mapBook]=ToMask(ItemCategory::TreasureMap);
    assert(ClassifyItem(&plainBook)==ToMask(ItemCategory::Book));
    assert(ClassifyItem(&spellBook)==(ItemCategory::Book|ItemCategory::SpellTome));
    assert(ClassifyItem(&skillBook)==(ItemCategory::Book|ItemCategory::SkillBook));
    assert(ClassifyItem(&noteBook)==ToMask(ItemCategory::Note));
    assert(ClassifyItem(&recipeBook)==(ItemCategory::Note|ItemCategory::Recipe));
    assert(ClassifyItem(&mapBook)==(ItemCategory::Note|ItemCategory::TreasureMap));
    RE::TESBoundObject miscMap{ItemCategory::None,false,0xFE001800};settings->overrides[&miscMap]=ToMask(ItemCategory::TreasureMap);
    assert(ClassifyItem(&miscMap)==(ItemCategory::Note|ItemCategory::TreasureMap));
    spellBook.book.note=true;spellBook.book.recipe=true;spellBook.book.skill=true;
    assert(ClassifyItem(&spellBook)==(ItemCategory::Book|ItemCategory::SpellTome));
    skillBook.book.note=true;assert(ClassifyItem(&skillBook)==(ItemCategory::Book|ItemCategory::SkillBook));
    assert(ExpandCategories(ToMask(ItemCategory::SpellTome))==(ItemCategory::SpellTome|ItemCategory::Book));
    assert(ExpandCategories(ToMask(ItemCategory::Recipe))==(ItemCategory::Recipe|ItemCategory::Note));
    for(auto* item : {&plainBook,&spellBook,&skillBook,&noteBook,&recipeBook,&mapBook,&scrollA}) inbox.inventory[item]=entry(7);
    stores.SortItems();
    for(auto* item : {&plainBook,&spellBook,&skillBook}) assert(chest.inventory[item].first==7);
    for(auto* item : {&noteBook,&recipeBook,&mapBook}) assert(utility->notes.inventory[item].first==7);
    assert(scrollBank.inventory[&scrollA].first==7 && utility->junk.inventory.empty());
    scrollBank.inventory[&noteBook]=entry(2);scrollBank.inventory[&plainBook]=entry(3);stores.ConsolidateBooks();
    assert(utility->notes.inventory[&noteBook].first==9 && chest.inventory[&plainBook].first==10 && scrollBank.inventory[&scrollA].first==7);
    stores.BookMenu(&source);click(3);assert(stores.options.size()==4 && stores.options[0].text=="Vault.SpellTomes" && stores.options[1].text=="Vault.SkillBooks");
    click(0);assert(stores.opened==Container::SpellTomes && utility->spellTomes.inventory[&spellBook].first==7 && chest.inventory[&spellBook].first==0);
    stores.onClose();assert(utility->spellTomes.inventory[&spellBook].first==0 && chest.inventory[&spellBook].first==7 && stores.options.size()==4);
    click(1);assert(stores.opened==Container::SkillBooks && utility->skillBooks.inventory[&skillBook].first==7);stores.onClose();click(2);assert(stores.options.size()==6);
    stores.NotesMenu(&source);click(2);assert(stores.options.size()==4 && stores.options[0].text=="Vault.Recipes" && stores.options[1].text=="Vault.TreasureMaps");
    click(0);assert(stores.opened==Container::Recipes && utility->recipes.inventory[&recipeBook].first==7);stores.onClose();
    click(1);assert(stores.opened==Container::TreasureMaps && utility->treasureMaps.inventory[&mapBook].first==7);stores.onClose();click(2);assert(stores.options.size()==5);
    player->inventory[&noteBook]=entry(2);click(1);assert(player->inventory[&noteBook].first==2 && player->inventory[&recipeBook].first==1 && player->inventory[&mapBook].first==1);
    click(0);assert(player->inventory[&noteBook].first==0 && utility->notes.inventory[&noteBook].first==11);
    stores.closed=false;stores.OpenBookArchive(Container::Recipes,Container::Notes,ItemCategory::Recipe,&source);stores.onClose();assert(stores.closed);
    utility->recipes.inventory[&recipeBook]=entry(2);utility->skillBooks.inventory[&skillBook]=entry(2);stores.ConsolidateBooks();
    assert(utility->recipes.inventory[&recipeBook].first==0 && utility->notes.inventory[&recipeBook].first==9 && chest.inventory[&skillBook].first==9);
    player->inventory.clear();settings->GSC_OffloadNotes=false;settings->GSC_OffloadBooks=true;
    put(&noteBook,5);put(&plainBook,5);stores.OffloadItems();assert(player->inventory[&noteBook].first==5 && player->inventory[&plainBook].first==0);
    settings->GSC_OffloadNotes=true;settings->ignored.clear();settings->ignored.insert(&mapBook);put(&mapBook,4);stores.OffloadItems();
    assert(player->inventory[&noteBook].first==0 && player->inventory[&mapBook].first==4);
    utility->scrollContainer=nullptr;

}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-key-check-") as temporary:
    path = Path(temporary)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
working = json.loads((ROOT / "release/ArcaneVaults-LinkedStorage.json").read_text())
assert validate_esp(ROOT, generate_esp(working)) == 96
nodes = list(walk(working["records"]))
assert len([n for n in nodes if n["type"] == "CONT"]) == 45
for local_id, flag, field in [("0x01000DC7", 0x400, None), ("0x01000DC6", None, "DATA"), ("0x01000DC9", 0x400, None), ("0x01000DC8", None, "DATA"), ("0x01000DD3", 0x400, None), ("0x01000DD2", None, "DATA"), *[(f"0x01000{local:03X}", 0x400, None) for local in (0xDD5,0xDD7,0xDD9,0xDDB,0xDDD)], *[(f"0x01000{local:03X}", None, "DATA") for local in (0xDD4,0xDD6,0xDD8,0xDDA,0xDDC)]]:
    changed = copy.deepcopy(working)
    node = next(n for n in walk(changed["records"]) if n["form_id"] == local_id)
    if flag:
        node["flags"] &= ~flag
    else:
        next(f for f in node["fields"] if f["type"] == field)["hex"] = "0200000000"
    try:
        validate_esp(ROOT, generate_esp(changed))
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe storage accepted")

map_overrides = {}
for line in (ROOT / "ini/ArcaneVaultOverrides.ini").read_text().splitlines():
    if "=" in line:
        identifier, categories = (part.strip() for part in line.split("=", 1))
        if categories == "TreasureMap":
            plugin, local = identifier.split("|", 1)
            map_overrides[(plugin, int(local, 16))] = categories
assert set(map_overrides) == {("Skyrim.esm", local) for local in
    (0xEF07A, 0xF33CE, 0xF33CF, 0xF33D1, 0xF33D4, 0xF33D0, 0xF33D5, 0xF33D3,
     0xF33CD, 0xF33E0, 0xF33D2, 0xDDEFB)} | {("Dragonborn.esm", 0x2BAAE)}
print("PASS: Books/Notes classification, archives, migration and routing; ignore-aware Sort/Quick Transfer and picker returns, Junk crafting loans, native spell-scroll sorting/Quick Transfer/overrides, vault carried targets, equipped protections, Alchemy/Welkynd sorting, Jewelry/Valuables filtering, reserves, partial transfers, crafting-loan return, INI validation, and ESP storage")
