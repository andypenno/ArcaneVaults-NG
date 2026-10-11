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
settings = (ROOT / "src/Settings.cpp").read_text()
start = settings.index("template <class Func>\nvoid Settings::ForEachINIOption(")
ini_options = settings[start:settings.index("\n}\n", start) + 3]
start = settings.index("template <class T>\nvoid Settings::get_value(")
get_value = settings[start:settings.index("\n}\n", start) + 3]
classification = (ROOT / "src/ItemClass.cpp").read_text()
start = classification.index("CategoryMask ClassifyItem(")
classification = classification[start:classification.index("    // Crafting", start)]
classification += "    (void)utility;\n    return categories | ToMask(a_item->category);\n}\n"
settings_fields = "\n".join(line for line in (ROOT / "src/Settings.h").read_text().splitlines()
                            if line.strip().startswith(("bool GSC_", "int GSC_")))
program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <charconv>
#include <climits>
#include <type_traits>
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
struct TESBoundObject {
    ItemCategory category;
    bool bolt = false;
    bool IsKey() const { return category == ItemCategory::Keys; }
    template<class T> T* As() { static T ammo; return category == ItemCategory::Ammunition ? &ammo : nullptr; }
};
struct InventoryEntryData {
    bool quest = false, favorite = false, worn = false;
    bool IsQuestObject() const { return quest; }
    bool IsFavorited() const { return favorite; }
    bool IsWorn() const { return worn; }
};
struct TESObjectREFR {
    std::map<TESBoundObject*, std::pair<int, std::shared_ptr<InventoryEntryData>>> inventory;
    auto GetInventory() const { return inventory; }
    void RemoveItem(TESBoundObject* item, int count, ITEM_REMOVE_REASON, void*, TESObjectREFR* destination) {
        assert(count > 0 && count <= inventory.at(item).first);
        inventory.at(item).first -= count;
        destination->inventory[item].first += count;
    }
};
struct PlayerCharacter : TESObjectREFR {
    static PlayerCharacter* GetSingleton() { static PlayerCharacter player; return &player; }
};
struct SendHUDMessage { static void ShowHUDMessage(const char*) {} };
}
struct Utility {
    RE::TESObjectREFR chest, inbox, ammunition;
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    RE::TESObjectREFR* GetContainer(Container container) { return container == Container::None ? nullptr : container == Container::Sort ? &inbox : container == Container::Ammunition ? &ammunition : &chest; }
};
CategoryMask ToMask(ItemCategory category) noexcept {
    return category == ItemCategory::None ? 0 : CategoryMask{1} << static_cast<unsigned>(category);
}
CategoryMask ExpandCategories(CategoryMask mask) noexcept { return mask; }
bool HasCategory(CategoryMask mask, ItemCategory category) noexcept { return (mask & (CategoryMask{1} << static_cast<unsigned>(category))) != 0; }
const char* Translate(const char*) { return ""; }
struct Stores {
    void PlayerToStore(ItemCategory, Container, int = 0, int = 0);
    void OffloadItems();
    void StoreToStore(ItemCategory, Container, Container);
    void SortItems();
};
struct CSimpleIniA {
    std::string text;
    bool exists = true;
    bool KeyExists(const char*, const char*) { return exists; }
    bool GetBoolValue(const char*, const char*, bool fallback) { return fallback; }
    const char* GetValue(const char*, const char*, const char*) { return text.c_str(); }
};
namespace std {
    template<class T> string format(const char*, T) { return ""; }
}
'''
program += "struct Settings {\n" + settings_fields + r'''
    std::optional<CategoryMask> override;
    std::optional<CategoryMask> FindOverride(RE::TESBoundObject*) { return override; }
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    template <class Func> void ForEachINIOption(Settings&, Func&&);
    template <class T> void get_value(CSimpleIniA&, T&, const char*, const char*);
    template <class T> void set_value(CSimpleIniA& ini, const T& value, const char*, const char*) {
        ini.text = std::to_string(value);
    }
};
'''
program += classification + method + offload + store_to_store + sort_items + ini_options + get_value
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
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-key-check-") as temporary:
    path = Path(temporary)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
working = json.loads((ROOT / "release/ArcaneVaults-LinkedStorage.json").read_text())
assert validate_esp(ROOT, generate_esp(working)) == 74
nodes = list(walk(working["records"]))
assert len([n for n in nodes if n["type"] == "CONT"]) == 34
for local_id, flag, field in [("0x01000DC7", 0x400, None), ("0x01000DC6", None, "DATA")]:
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
        raise AssertionError("Unsafe ammunition storage accepted")
print("PASS: actual transfers preserve counts/protections; Keys regressions, ammunition reserves/sorting/protections, INI validation/defaults, and ESP storage pass")
