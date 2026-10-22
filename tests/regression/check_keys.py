"""Exercise actual shared transfers with inventory stubs."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "src/Stores.cpp").read_text()
start = source.index("void Stores::PlayerToStore(")
method = source[start:source.index("\n}\n", start) + 3]
start = source.index("void Stores::OffloadItems(")
offload = source[start:source.index("\n}\n", start) + 3]
settings = (ROOT / "src/Settings.cpp").read_text()
start = settings.index("template <class Func>\nvoid Settings::ForEachINIOption(")
ini_options = settings[start:settings.index("\n}\n", start) + 3]
settings_fields = "\n".join(line for line in (ROOT / "src/Settings.h").read_text().splitlines()
                            if line.strip().startswith(("bool GSC_", "int GSC_")))
program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <functional>
#include <climits>
#include <optional>
#include <unordered_set>
#include <map>
#include <memory>
#include <string>
#include <string_view>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
enum class ITEM_REMOVE_REASON { kStoreInContainer };
struct TESBoundObject { ItemCategory category; };
struct InventoryEntryData {
    bool quest = false, favorite = false, worn = false;
    bool IsQuestObject() const { return quest; }
    bool IsFavorited() const { return favorite; }
    bool IsWorn() const { return worn; }
};
struct TESObjectREFR {
    int removeLimit=INT_MAX,removeCalls=0;bool rejectMove=false;
    std::map<TESBoundObject*, std::pair<int, std::shared_ptr<InventoryEntryData>>> inventory;
    auto GetInventory() const { return inventory; }
    auto GetInventoryCounts(std::function<bool(TESBoundObject&)> filter) const {std::map<TESBoundObject*,int> counts;for(const auto& [item,data]:inventory)if(item && filter(*item))counts[item]=data.first;return counts;}
    void RemoveItem(TESBoundObject* item, int count, ITEM_REMOVE_REASON, void*, TESObjectREFR* destination) {
        assert(count > 0 && count <= inventory.at(item).first);
        ++removeCalls;if(rejectMove)return;count=std::min(count,removeLimit);
        inventory.at(item).first -= count;
        destination->inventory[item].first += count;
    }
};
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
    RE::TESObjectREFR chest;
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    RE::TESObjectREFR* GetContainer(Container container) { return container == Container::None ? nullptr : &chest; }
};
CategoryMask ClassifyItem(RE::TESBoundObject* item) noexcept { return CategoryMask{1} << static_cast<unsigned>(item->category); }
bool HasCategory(CategoryMask mask, ItemCategory category) noexcept { return (mask & (CategoryMask{1} << static_cast<unsigned>(category))) != 0; }
const char* Translate(const char*) { return ""; }
struct Stores { void PlayerToStore(ItemCategory, Container, int = 0, int = 0); void OffloadItems(); void StoreToPlayer(ItemCategory,Container,int=0,std::optional<int> = std::nullopt); };
'''
program += "struct Settings {\n" + settings_fields + r'''
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    template <class Func> void ForEachINIOption(Settings&, Func&&);
};
'''
move_start=source.index("    void MoveItems(")
program+=source[move_start:source.index("\n    }",move_start)+6]
start=source.index("void Stores::StoreToPlayer(")
store_to_player=source[start:source.index("\n}\n",start)+3]
program += method + store_to_player + offload + ini_options
program += r'''
int main() {
    static_assert(static_cast<unsigned>(Container::Staff) == 32);
    static_assert(static_cast<unsigned>(ItemCategory::None) == 35);
    static_assert(static_cast<unsigned>(ItemCategory::Keys) < 64);
    auto* player = RE::PlayerCharacter::GetSingleton();
    auto& chest = Utility::GetSingleton()->chest;
    RE::TESBoundObject a{ItemCategory::Keys}, b{ItemCategory::Keys}, nonkey{ItemCategory::Scroll};
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
    stores.PlayerToStore(ItemCategory::Scroll, Container::Keys, 3);
    assert(player->inventory[&nonkey].first == 2 && chest.inventory[&nonkey].first == 3);
    stores.PlayerToStore(ItemCategory::Scroll, Container::Keys, 3);
    assert(player->inventory[&nonkey].first == 0 && chest.inventory[&nonkey].first == 5);
    put(&a, 4);
    stores.PlayerToStore(ItemCategory::Keys, Container::None, 0, true);
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys, -1);
    assert(player->inventory[&a].first == 4);
    player->inventory[nullptr] = {3, std::make_shared<RE::InventoryEntryData>()};
    player->inventory[&a].second.reset();
    stores.PlayerToStore(ItemCategory::Keys, Container::Keys);
    assert(player->inventory[&a].first == 4);

    player->inventory.clear();chest.inventory.clear();put(&a,50000);player->removeLimit=3;
    stores.PlayerToStore(ItemCategory::Keys,Container::Keys,0,1);
    assert(player->inventory[&a].first==1 && chest.inventory[&a].first==49999);
    put(&a,20);player->rejectMove=true;const auto before=player->removeCalls;
    stores.PlayerToStore(ItemCategory::Keys,Container::Keys);
    assert(player->inventory[&a].first==20 && player->removeCalls==before+1);
    player->rejectMove=false;player->removeLimit=0;stores.PlayerToStore(ItemCategory::Keys,Container::Keys);
    assert(player->inventory[&a].first==20 && player->removeCalls==before+2);

    player->removeLimit=INT_MAX;
    auto* settings = Settings::GetSingleton();
    std::map<std::pair<std::string, std::string>, int> options;
    settings->ForEachINIOption(*settings, [&](auto& value, const char* section, const char* key) {
        options[{section, key}] = value;
    });
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
    for(int held:{0,1,3})for(int stock:{0,2,10})for(bool refused:{false,true}){
        player->inventory.clear();chest.inventory.clear();put(&a,held);
        chest.inventory[&a]={stock,std::make_shared<RE::InventoryEntryData>()};chest.rejectMove=refused;chest.removeLimit=2;
        stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,1);
        assert(player->inventory[&a].first==held+(refused?0:std::min(stock,std::max(0,1-held))));
        assert(player->inventory[&a].first+chest.inventory[&a].first==held+stock);
    }
    chest.rejectMove=false;chest.removeLimit=9999;player->inventory.clear();chest.inventory.clear();
    put(&a,10000);chest.inventory[&a]={50000,std::make_shared<RE::InventoryEntryData>()};
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,40000);
    assert(player->inventory[&a].first==40000 && chest.inventory[&a].first==20000);
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,1000,45000);
    assert(player->inventory[&a].first==41000 && chest.inventory[&a].first==19000);
    stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,0);stores.StoreToPlayer(ItemCategory::Keys,Container::Keys,0,-1);
    assert(player->inventory[&a].first==41000);

    auto& armorVault=chest;
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
    auto* command=RE::SCRIPT_FUNCTION::LocateScriptCommand("GetEquipped");
    command->conditionFunction=[](RE::TESObjectREFR*,void*,void*,double& result) { result=0; return true; };
    stores.PlayerToStore(ItemCategory::Jewelry,Container::Armor);
    for (auto& ring : virtualRings) assert(player->inventory[&ring].first==0 && armorVault.inventory[&ring].first==2);
    assert(player->inventory[&equippedSpare].first==0 && armorVault.inventory[&equippedSpare].first==4);
    command->conditionFunction=RE::SCRIPT_FUNCTION::GetEquipped;
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
    put(&nonkey,5); RE::SCRIPT_FUNCTION::equipped.insert(&nonkey);
    stores.PlayerToStore(ItemCategory::Scroll,Container::Book);
    assert(player->inventory[&nonkey].first==5);
    RE::SCRIPT_FUNCTION::equipped.clear(); const int beforeEquipmentCalls=RE::SCRIPT_FUNCTION::calls;
    stores.PlayerToStore(ItemCategory::Scroll,Container::Book);
    assert(player->inventory[&nonkey].first==0 && RE::SCRIPT_FUNCTION::calls==beforeEquipmentCalls+1);
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-key-check-") as temporary:
    path = Path(temporary)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: transfer reserves, large stacks, partial/refused moves, protections and quantity conservation")
