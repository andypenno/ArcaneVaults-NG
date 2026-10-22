"""Exercise actual shared transfers with inventory stubs."""

from pathlib import Path
import subprocess
import tempfile
import re

ROOT = Path(__file__).resolve().parents[2]
header=(ROOT / "src/ItemClass.h").read_text()
container_enum=header[header.index("enum class Container :"):header.index("enum class ItemCategory :")]
container_names=set(re.findall(r"^\s+(\w+)[,\n]",container_enum,re.M))
assert set(re.findall(r"\bContainer::(\w+)",(ROOT / "src/Utility.cpp").read_text())) <= container_names
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
#include <charconv>
#include <functional>
#include <climits>
#include <optional>
#include <unordered_set>
#include <unordered_map>
#include <limits>
#include <vector>
#include <map>
#include <set>
#include <memory>
#include <string>
#include <string_view>
#include <type_traits>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
using FormID = unsigned;
struct TESSoulGem {};
enum class ITEM_REMOVE_REASON { kStoreInContainer };
struct TESBoundObject { ItemCategory category; CategoryMask extraMask=0; inline static unsigned nextID=1; unsigned id=nextID++; unsigned GetFormID() const {return id;} template<class T>T* As(){return nullptr;} };
struct InventoryEntryData {
    bool quest = false, favorite = false, worn = false;
    bool IsQuestObject() const { return quest; }
    bool IsFavorited() const { return favorite; }
    bool IsWorn() const { return worn; }
};
struct TESObjectREFR;
struct Handle {
    TESObjectREFR* object;
    struct Pointer { TESObjectREFR* object; explicit operator bool()const{return object;} TESObjectREFR* get()const{return object;} };
    Pointer get()const{return {object};}
};
struct InventoryChanges {void RemoveAllItems(TESObjectREFR*,TESObjectREFR*,bool,bool,bool);};
struct TESObjectREFR {
    InventoryChanges changes;InventoryChanges* GetInventoryChanges(){return &changes;}
    Handle GetHandle(){return {this};}
    int removeLimit=INT_MAX,removeCalls=0;bool rejectMove=false;
    std::map<TESBoundObject*, std::pair<int, std::shared_ptr<InventoryEntryData>>> inventory;
    auto GetInventory() const { return inventory; }
    auto GetInventoryCounts(std::function<bool(TESBoundObject&)> filter = [](auto&){return true;}) const {std::map<TESBoundObject*,int> counts;for(const auto& [item,data]:inventory)if(item && filter(*item))counts[item]=data.first;return counts;}
    void RemoveItem(TESBoundObject* item, int count, ITEM_REMOVE_REASON, void*, TESObjectREFR* destination) {
        assert(count > 0 && count <= inventory.at(item).first);
        ++removeCalls;if(rejectMove)return;count=std::min(count,removeLimit);
        inventory.at(item).first -= count;
        destination->inventory[item].first += count;
        if (!destination->inventory[item].second) destination->inventory[item].second=std::make_shared<InventoryEntryData>();
    }
};
void InventoryChanges::RemoveAllItems(TESObjectREFR* source,TESObjectREFR* target,bool,bool,bool){for(auto [item,data]:source->GetInventory())if(item && data.first>0)source->RemoveItem(item,data.first,ITEM_REMOVE_REASON::kStoreInContainer,nullptr,target);}
struct PlayerCharacter : TESObjectREFR {
    TESBoundObject* currentAmmo=nullptr;
    TESBoundObject* GetCurrentAmmo() const {return currentAmmo;}
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
    RE::TESObjectREFR chest,inbox,ammunition,archery,junk;
    std::map<Container,RE::TESObjectREFR*> custom;
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    RE::TESObjectREFR* GetContainer(Container container) { if(custom.contains(container))return custom[container]; return container == Container::None ? nullptr : container==Container::Sort ? &inbox : container==Container::Ammunition ? &ammunition : container==Container::Archery ? &archery : container==Container::Junk ? &junk : &chest; }
};
CategoryMask ClassifyItem(RE::TESBoundObject* item) noexcept { return (CategoryMask{1} << static_cast<unsigned>(item->category)) | item->extraMask; }
CategoryMask ToMask(ItemCategory category)noexcept{return category==ItemCategory::None?0:CategoryMask{1}<<static_cast<unsigned>(category);}
bool HasAnyCategory(CategoryMask mask,CategoryMask wanted)noexcept{return (mask & wanted)!=0;}
bool HasCategory(CategoryMask mask, ItemCategory category) noexcept { return (mask & (CategoryMask{1} << static_cast<unsigned>(category))) != 0; }
const char* Translate(const char*) { return ""; }
namespace Soulgems {void Recover(){} void Deposit(int,bool){}}
struct MenuOption {std::string text;std::function<void()> action;};
struct Stores { void PlayerToStore(ItemCategory, Container, int = 0, int = 0, bool = false, CategoryMask = 0); void ReturnIgnoredItems(); void KeepAmmunition(bool = false); void TakeAmmunition();
    std::function<void()> onClose;
    void ShowWeaponArcheryMenu(RE::TESObjectREFR*);
    std::vector<MenuOption> options;Container opened=Container::None;
    void ShowDynamicMessageBox(std::string_view,std::vector<MenuOption> values,int){options=std::move(values);}
    void OpenStoreObject(RE::TESObjectREFR* source,std::function<void(RE::TESObjectREFR*)> action){action(source);}
    std::function<void()> returnToVault_;
    void GearMenu(RE::TESObjectREFR*);void ShowGearMenu(RE::TESObjectREFR*);
    void JunkMenu(RE::TESObjectREFR*);
    void BookMenu(RE::TESObjectREFR*);void ShowBookMenu(RE::TESObjectREFR*);void NotesMenu(RE::TESObjectREFR*);void ShowNotesMenu(RE::TESObjectREFR*);
    std::unordered_map<RE::FormID,std::pair<int,int>> junkLoan_;
    void BeginJunkLoan();void EndJunkLoan();void ResetJunkLoan(){junkLoan_.clear();}
    void ConsolidateBooks();void ConsolidatePotions();void OpenBookArchive(Container,Container,ItemCategory,RE::TESObjectREFR*,bool=false);
    void AlchemyMenu(RE::TESObjectREFR*);void ShowAlchemyMenu(RE::TESObjectREFR*);
    void ScrollMenu(RE::TESObjectREFR*);void ShowScrollMenu(RE::TESObjectREFR*);
    void ReturnValuables();void ValuablesMenu(RE::TESObjectREFR*);void ShowValuablesMenu(RE::TESObjectREFR*);
    void CloseStoreObject(RE::TESObjectREFR*) {}
    void OpenStorageMenu(Container container,RE::TESObjectREFR* source,std::function<void(RE::TESObjectREFR*)> close){opened=container;onClose=[source,close]{close(source);};}
    void AllToStore(Container,Container); void OffloadItems(); void SortItems(); void StoreToStore(ItemCategory,Container,Container); void StoreToPlayer(ItemCategory,Container,int=0,std::optional<int> = std::nullopt); };
'''
program += r'''struct CSimpleIniA {
    std::string text; bool exists=true;
    bool KeyExists(const char*,const char*){return exists;}
    bool GetBoolValue(const char*,const char*,bool fallback){return fallback;}
    const char* GetValue(const char*,const char*,const char*){return text.c_str();}
};
namespace std {template<class... T> string format(const char*,T...){return "";}template<class T> int make_format_args(T value){return value;}inline string vformat(const char*,int){return "";}}
'''
program += "struct Settings {\n" + settings_fields + r'''
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    std::set<RE::TESBoundObject*> ignored;
    bool IsIgnored(RE::TESBoundObject* item) const { return ignored.contains(item); }
    template<class T> void get_value(CSimpleIniA&,T&,const char*,const char*);
    template<class T> void set_value(CSimpleIniA& ini,T value,const char*,const char*){ini.text=std::to_string(value);}
    template <class Func> void ForEachINIOption(Settings&, Func&&);
};
'''
start=settings.index("template <class T>\nvoid Settings::get_value(")
program += settings[start:settings.index("\n}\n",start)+3]
move_start=source.index("    void MoveItems(")
program+=source[move_start:source.index("\n    }",move_start)+6]
start=source.index("void Stores::StoreToPlayer(")
store_to_player=source[start:source.index("\n}\n",start)+3]
start=source.index("void Stores::StoreToStore(")
store_to_store=source[start:source.index("\n}\n",start)+3]
start=source.index("void Stores::SortItems(")
sort_items=source[start:source.index("\n}\n",start)+3]
start=source.index("void Stores::ReturnIgnoredItems(")
program += source[start:source.index("\n}\n",start)+3]
start=source.index("    std::unordered_set<RE::FormID> SelectedAmmunition(")
program += source[start:source.index("\n    }",start)+6]
for name in ["KeepAmmunition", "TakeAmmunition", "ReturnValuables", "ValuablesMenu", "ShowValuablesMenu", "JunkMenu", "AlchemyMenu", "ShowAlchemyMenu", "ScrollMenu", "ShowScrollMenu", "BookMenu", "ShowBookMenu", "NotesMenu", "ShowNotesMenu", "ConsolidateBooks", "OpenBookArchive", "GearMenu", "ShowGearMenu", "ConsolidatePotions", "BeginJunkLoan", "EndJunkLoan"]:
    start=source.index("void Stores::"+name+"(")
    program += source[start:source.index("\n}\n",start)+3]
start=source.index("void Stores::ShowWeaponArcheryMenu(")
program += source[start:source.index("\n}\n",start)+3]
start=source.index("void Stores::AllToStore(")
program += source[start:source.index("\n}\n",start)+3]

program += method + store_to_player + offload + store_to_store + sort_items + ini_options
program += r'''
int main() {
    assert(ContainerTranslationKey(Container::Ammunition)=="Vault.Ammunition");
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
    player->inventory.clear();chest.inventory.clear();put(&a,4);settings->GSC_OffloadKeys=true;settings->ignored.insert(&a);
    stores.OffloadItems();assert(player->inventory[&a].first==4 && chest.inventory[&a].first==0);
    stores.PlayerToStore(ItemCategory::Keys,Container::Keys);assert(player->inventory[&a].first==0 && chest.inventory[&a].first==4);
    auto& sortInbox=Utility::GetSingleton()->inbox;sortInbox.inventory[&a]={3,std::make_shared<RE::InventoryEntryData>()};
    settings->GSC_ReturnIgnoredItems=true;stores.SortItems();assert(player->inventory[&a].first==3 && sortInbox.inventory[&a].first==0);
    sortInbox.inventory[&a]={2,std::make_shared<RE::InventoryEntryData>()};settings->GSC_ReturnIgnoredItems=false;stores.SortItems();
    assert(sortInbox.inventory[&a].first==0 && chest.inventory[&a].first==6);settings->ignored.clear();
    player->inventory.clear();chest.inventory.clear();auto& inbox=Utility::GetSingleton()->inbox;
    std::array<RE::TESBoundObject,3> ingredients{{{ItemCategory::Ingredient,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Alchemy)},
        {ItemCategory::Reagent,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Alchemy)},
        {ItemCategory::Catalyst,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Alchemy)}}};
    for(auto& item:ingredients)put(&item,5);
    stores.PlayerToStore(ItemCategory::Alchemy,Container::Alchemy);
    for(auto& item:ingredients){assert(player->inventory[&item].first==0 && chest.inventory[&item].first==5);inbox.inventory[&item]={7,std::make_shared<RE::InventoryEntryData>()};}
    stores.SortItems();
    for(auto& item:ingredients)assert(inbox.inventory[&item].first==0 && chest.inventory[&item].first==12);


    CSimpleIniA ini;int reserve=100;
    for(const auto* text:{"0","1","100","2147483647"}){ini.text=text;settings->get_value(ini,reserve,"General","AmmunitionKeepAmount");assert(reserve==std::stoi(text));}
    for(const auto* text:{"","-1","1.5","100x","abc","2147483648"}){ini.text=text;settings->get_value(ini,reserve,"General","AmmunitionKeepAmount");assert(reserve==100);}
    ini.exists=false;reserve=100;settings->get_value(ini,reserve,"General","AmmunitionKeepAmount");assert(ini.text=="100");
    player->inventory.clear();chest.inventory.clear();auto& ammoChest=Utility::GetSingleton()->ammunition;
    RE::TESBoundObject selectedArrows{ItemCategory::Ammunition},selectedBolts{ItemCategory::Ammunition},spareArrows{ItemCategory::Ammunition},questAmmo{ItemCategory::Ammunition},ignoredAmmo{ItemCategory::Ammunition},wornAmmo{ItemCategory::Ammunition},virtualAmmo{ItemCategory::Ammunition};
    settings->GSC_AmmunitionKeepAmount=100;settings->GSC_KeepSelectedAmmunition=false;
    player->currentAmmo=&selectedBolts;put(&selectedArrows,250,false,true);put(&selectedBolts,180);put(&spareArrows,160);put(&questAmmo,200,true);put(&ignoredAmmo,225);
    settings->ignored.insert(&ignoredAmmo);stores.KeepAmmunition(true);
    assert(player->inventory[&selectedArrows].first==250 && player->inventory[&selectedBolts].first==180 && player->inventory[&spareArrows].first==100);
    assert(player->inventory[&questAmmo].first==200 && player->inventory[&ignoredAmmo].first==225);
    settings->GSC_KeepSelectedAmmunition=true;put(&wornAmmo,200,false,false,true);put(&virtualAmmo,220);RE::SCRIPT_FUNCTION::equipped.insert(&virtualAmmo);
    stores.KeepAmmunition(true);
    for(auto* item:{&selectedArrows,&selectedBolts,&wornAmmo,&virtualAmmo})assert(player->inventory[item].first==100);
    assert(player->inventory[&spareArrows].first==0 && player->inventory[&questAmmo].first==200 && player->inventory[&ignoredAmmo].first==225);
    stores.KeepAmmunition();assert(player->inventory[&ignoredAmmo].first==0 && player->inventory[&questAmmo].first==200);
    put(&selectedArrows,30,false,true);put(&selectedBolts,140);put(&wornAmmo,20,false,false,true);put(&virtualAmmo,20);
    ammoChest.inventory[&wornAmmo]={5,std::make_shared<RE::InventoryEntryData>()};ammoChest.inventory[&virtualAmmo]={150,std::make_shared<RE::InventoryEntryData>()};ammoChest.inventory[&spareArrows]={200,std::make_shared<RE::InventoryEntryData>()};
    stores.TakeAmmunition();assert(player->inventory[&selectedArrows].first==100 && player->inventory[&selectedBolts].first==140);
    assert(player->inventory[&wornAmmo].first==25 && player->inventory[&virtualAmmo].first==100 && player->inventory[&spareArrows].first==0);
    settings->GSC_KeepSelectedAmmunition=false;stores.TakeAmmunition();assert(player->inventory[&spareArrows].first==100);
    settings->GSC_KeepSelectedAmmunition=true;player->inventory.clear();player->currentAmmo=nullptr;RE::SCRIPT_FUNCTION::equipped.clear();
    stores.TakeAmmunition();assert(player->inventory.empty());put(&spareArrows,60);put(&selectedArrows,60,false,true);stores.KeepAmmunition();
    assert(player->inventory[&spareArrows].first==0 && player->inventory[&selectedArrows].first==60);
    player->currentAmmo=&selectedArrows;settings->GSC_AmmunitionKeepAmount=40000;player->inventory.clear();ammoChest.inventory.clear();ammoChest.inventory[&selectedArrows]={50000,std::make_shared<RE::InventoryEntryData>()};
    ammoChest.removeLimit=9999;stores.TakeAmmunition();assert(player->inventory[&selectedArrows].first==40000 && ammoChest.inventory[&selectedArrows].first==10000);
    settings->GSC_AmmunitionKeepAmount=100;stores.KeepAmmunition();assert(player->inventory[&selectedArrows].first==100 && ammoChest.inventory[&selectedArrows].first==49900);
    put(&selectedArrows,150,false,true);player->rejectMove=true;stores.KeepAmmunition();assert(player->inventory[&selectedArrows].first==150);player->rejectMove=false;
    put(&selectedArrows,20,false,true);ammoChest.rejectMove=true;stores.TakeAmmunition();assert(player->inventory[&selectedArrows].first==20);ammoChest.rejectMove=false;
    settings->GSC_OffloadAmmunition=true;put(&selectedArrows,150,false,true);put(&spareArrows,20);stores.OffloadItems();
    assert(player->inventory[&selectedArrows].first==100 && player->inventory[&spareArrows].first==0);
    player->currentAmmo=nullptr;RE::SCRIPT_FUNCTION::equipped.clear();settings->ignored.clear();
    player->inventory.clear();ammoChest.inventory.clear();chest.inventory.clear();auto& archery=Utility::GetSingleton()->archery;RE::TESObjectREFR activationSource;
    RE::TESBoundObject bow{ItemCategory::Archery},manualAmmo{ItemCategory::Ammunition};
    chest.inventory[&bow]={2,std::make_shared<RE::InventoryEntryData>()};ammoChest.inventory[&selectedArrows]={250,std::make_shared<RE::InventoryEntryData>()};
    stores.ShowWeaponArcheryMenu(&activationSource);
    assert(archery.inventory[&bow].first==2 && archery.inventory[&selectedArrows].first==250 && chest.inventory[&bow].first==0);
    archery.inventory[&manualAmmo]={90,std::make_shared<RE::InventoryEntryData>()};archery.rejectMove=true;stores.onClose();
    assert(archery.inventory[&selectedArrows].first==250 && archery.inventory[&bow].first==2 && chest.inventory[&selectedArrows].first==0);
    archery.rejectMove=false;stores.onClose();
    assert(ammoChest.inventory[&selectedArrows].first==250 && ammoChest.inventory[&manualAmmo].first==90 && chest.inventory[&bow].first==2);
    assert(archery.inventory[&selectedArrows].first==0 && archery.inventory[&bow].first==0);



    player->inventory.clear();chest.inventory.clear();RE::TESBoundObject ordinarySoulgemOverride{ItemCategory::Soulgem};
    put(&ordinarySoulgemOverride,12);settings->GSC_OffloadSoulgems=true;stores.OffloadItems();
    assert(player->inventory[&ordinarySoulgemOverride].first==0 && chest.inventory[&ordinarySoulgemOverride].first==12);
    auto& soulInbox=Utility::GetSingleton()->inbox;soulInbox.inventory[&ordinarySoulgemOverride]={5,std::make_shared<RE::InventoryEntryData>()};stores.SortItems();
    assert(soulInbox.inventory[&ordinarySoulgemOverride].first==0 && chest.inventory[&ordinarySoulgemOverride].first==17);
    player->inventory.clear();RE::TESObjectREFR treasury,smithing,armor,valuables;auto* utility=Utility::GetSingleton();
    utility->custom={{Container::Treasure,&treasury},{Container::Smithing,&smithing},{Container::Armor,&armor},{Container::Valuables,&valuables}};
    RE::TESBoundObject gold{ItemCategory::Gold},gem{ItemCategory::Gemstone},ingot{ItemCategory::PreciousIngot},jewel{ItemCategory::Jewelry},unrelated{ItemCategory::Scroll};
    auto entry=[](int count){return std::pair{count,std::make_shared<RE::InventoryEntryData>()};};
    treasury.inventory[&gold]=entry(6000);treasury.inventory[&unrelated]=entry(4);smithing.inventory[&gem]=entry(10);smithing.inventory[&ingot]=entry(20);armor.inventory[&jewel]=entry(3);
    stores.ValuablesMenu(&activationSource);assert(stores.options.size()==5);
    auto click=[&](int index){auto action=stores.options.at(index).action;action();};click(0);
    assert(stores.opened==Container::Valuables && valuables.inventory[&gold].first==6000 && valuables.inventory[&gem].first==10 && valuables.inventory[&ingot].first==20 && valuables.inventory[&jewel].first==3);
    assert(treasury.inventory[&unrelated].first==4);stores.onClose();
    assert(treasury.inventory[&gold].first==6000 && smithing.inventory[&gem].first==10 && smithing.inventory[&ingot].first==20 && armor.inventory[&jewel].first==3);
    settings->GSC_GoldKeepAmount=5000;put(&gold,6200);click(2);assert(player->inventory[&gold].first==5000 && treasury.inventory[&gold].first==7200);
    click(3);assert(player->inventory[&gold].first==0 && treasury.inventory[&gold].first==12200);
    click(4);assert(player->inventory[&gold].first==12200 && treasury.inventory[&gold].first==0);
    settings->ignored.insert(&gold);stores.OffloadItems();assert(player->inventory[&gold].first==12200);settings->ignored.clear();stores.OffloadItems();assert(player->inventory[&gold].first==5000 && treasury.inventory[&gold].first==7200);
    for(const auto* text:{"","-1","1.5","100x","abc","2147483648"}){ini.exists=true;ini.text=text;settings->get_value(ini,reserve,"General","GoldKeepAmount");assert(reserve==5000);}
    utility->custom.clear();
    player->inventory.clear();auto& junk=utility->junk;auto& junkInbox=utility->inbox;junk.inventory.clear();junkInbox.inventory.clear();
    RE::TESBoundObject explicitJunk{ItemCategory::Junk,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Smithing)},unmatchedJunk{ItemCategory::None};
    put(&explicitJunk,5);put(&unmatchedJunk,7);settings->GSC_OffloadJunk=true;stores.OffloadItems();
    assert(player->inventory[&explicitJunk].first==0 && junk.inventory[&explicitJunk].first==5 && player->inventory[&unmatchedJunk].first==7);
    settings->GSC_OffloadJunk=false;put(&explicitJunk,4);stores.OffloadItems();assert(player->inventory[&explicitJunk].first==4);
    settings->GSC_OffloadJunk=true;settings->ignored.insert(&explicitJunk);stores.OffloadItems();assert(player->inventory[&explicitJunk].first==4);settings->ignored.clear();
    junkInbox.inventory[&explicitJunk]=entry(9);junkInbox.inventory[&unmatchedJunk]=entry(8);stores.SortItems();
    assert(junk.inventory[&explicitJunk].first==14 && junk.inventory[&unmatchedJunk].first==8 && junkInbox.inventory[&unmatchedJunk].first==0);
    settings->GSC_ReturnIgnoredItems=true;settings->ignored.insert(&unmatchedJunk);junkInbox.inventory[&unmatchedJunk]=entry(3);junkInbox.rejectMove=true;stores.SortItems();
    assert(junkInbox.inventory[&unmatchedJunk].first==3 && junk.inventory[&unmatchedJunk].first==8);
    junkInbox.rejectMove=false;stores.SortItems();assert(junkInbox.inventory[&unmatchedJunk].first==0 && player->inventory[&unmatchedJunk].first==10);
    settings->ignored.clear();stores.JunkMenu(&activationSource);assert(stores.opened==Container::Junk);stores.onClose();



    for(bool alchemy:{false,true})for(int target:{0,1,25})for(int held:{0,1,100})for(int stock:{0,3,100}){
        player->inventory.clear();chest.inventory.clear();utility->custom.clear();
        RE::TESBoundObject item{alchemy?ItemCategory::Alchemy:ItemCategory::Scroll};put(&item,held);chest.inventory[&item]=entry(stock);
        settings->GSC_AlchemyKeepAmount=target;settings->GSC_ScrollKeepAmount=target;
        if(alchemy)stores.AlchemyMenu(&activationSource);else stores.ScrollMenu(&activationSource);
        click(1);assert(player->inventory[&item].first==std::min(held,target));
        assert(player->inventory[&item].first+chest.inventory[&item].first==held+stock);
        click(2);assert(player->inventory[&item].first==std::min(held+stock,target));
        assert(player->inventory[&item].first+chest.inventory[&item].first==held+stock);
    }
    for(auto [key,fallback]:{std::pair{"AlchemyKeepAmount",1},std::pair{"ScrollKeepAmount",3}}){
        for(const auto* text:{"","-1","1.5","100x","abc","2147483648"}){ini.exists=true;ini.text=text;settings->get_value(ini,reserve,"General",key);assert(reserve==fallback);}
        ini.text="0";settings->get_value(ini,reserve,"General",key);assert(reserve==0);
    }


    player->inventory.clear();chest.inventory.clear();utility->custom.clear();RE::TESObjectREFR books,notes,spellArchive,skillArchive,recipeArchive,legacyScroll;
    utility->custom={{Container::Book,&books},{Container::Notes,&notes},{Container::SpellTomes,&spellArchive},{Container::SkillBooks,&skillArchive},{Container::Recipes,&recipeArchive},{Container::Scroll,&legacyScroll}};
    RE::TESBoundObject plainBook{ItemCategory::Book},spellBook{ItemCategory::SpellTome,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Book)},skillBook{ItemCategory::SkillBook,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Book)},recipe{ItemCategory::Recipe,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Note)},note{ItemCategory::Note};
    spellArchive.inventory[&spellBook]=entry(2);skillArchive.inventory[&skillBook]=entry(3);recipeArchive.inventory[&recipe]=entry(4);legacyScroll.inventory[&note]=entry(5);books.inventory[&note]=entry(6);
    stores.ConsolidateBooks();assert(books.inventory[&spellBook].first==2 && books.inventory[&skillBook].first==3 && notes.inventory[&recipe].first==4 && notes.inventory[&note].first==11);
    stores.BookMenu(&activationSource);click(2);assert(stores.opened==Container::SpellTomes && spellArchive.inventory[&spellBook].first==2);stores.onClose();assert(books.inventory[&spellBook].first==2);
    stores.BookMenu(&activationSource);click(3);assert(stores.opened==Container::SkillBooks && skillArchive.inventory[&skillBook].first==3);stores.onClose();assert(books.inventory[&skillBook].first==3);
    stores.NotesMenu(&activationSource);click(2);assert(stores.opened==Container::Recipes && recipeArchive.inventory[&recipe].first==4);stores.onClose();assert(notes.inventory[&recipe].first==4);
    put(&plainBook,3);books.inventory[&plainBook]=entry(10);stores.BookMenu(&activationSource);click(1);assert(player->inventory[&plainBook].first==3);
    player->inventory[&plainBook].first=0;click(1);assert(player->inventory[&plainBook].first==1);click(1);assert(player->inventory[&plainBook].first==1);
    settings->GSC_OffloadNotes=true;put(&note,12);stores.OffloadItems();assert(player->inventory[&note].first==0 && notes.inventory[&note].first==23);
    utility->custom.clear();


    player->inventory.clear();chest.inventory.clear();RE::TESObjectREFR mapArchive;utility->custom[Container::Notes]=&notes;utility->custom[Container::Maps]=&mapArchive;
    RE::TESBoundObject fishingMap{ItemCategory::Map,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Note)};
    notes.inventory[&fishingMap]=entry(8);stores.NotesMenu(&activationSource);click(3);
    assert(stores.opened==Container::Maps && mapArchive.inventory[&fishingMap].first==8 && notes.inventory[&fishingMap].first==0);
    stores.onClose();assert(notes.inventory[&fishingMap].first==8 && mapArchive.inventory[&fishingMap].first==0);
    utility->custom.clear();


    player->inventory.clear();chest.inventory.clear();RE::TESObjectREFR gear,instruments;utility->custom={{Container::Gear,&gear},{Container::Instruments,&instruments}};
    RE::TESBoundObject picks{ItemCategory::Lockpick,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Gear)},instrument{ItemCategory::Instrument,CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Gear)},equipment{ItemCategory::Gear};
    put(&picks,100);put(&equipment,7);put(&instrument,3);settings->GSC_OffloadGear=true;settings->GSC_LockpickKeepAmount=25;stores.OffloadItems();
    assert(player->inventory[&picks].first==25 && gear.inventory[&picks].first==75 && player->inventory[&equipment].first==0 && gear.inventory[&equipment].first==7 && gear.inventory[&instrument].first==3);
    stores.OpenBookArchive(Container::Instruments,Container::Gear,ItemCategory::Instrument,&activationSource);
    assert(stores.opened==Container::Instruments && instruments.inventory[&instrument].first==3 && gear.inventory[&equipment].first==7);stores.onClose();assert(gear.inventory[&instrument].first==3);
    stores.GearMenu(&activationSource);assert(stores.options.size()==4);put(&picks,60);click(2);assert(player->inventory[&picks].first==25);player->inventory[&picks].first=0;click(3);assert(player->inventory[&picks].first==25);
    ini.text="-1";ini.exists=true;settings->get_value(ini,reserve,"General","LockpickKeepAmount");assert(reserve==25);
    utility->custom.clear();


    player->inventory.clear();chest.inventory.clear();RE::TESObjectREFR concoctions,healthArchive,magickaArchive,staminaArchive;
    utility->custom={{Container::Concoction,&concoctions},{Container::HealthPotions,&healthArchive},{Container::MagickaPotions,&magickaArchive},{Container::StaminaPotions,&staminaArchive}};
    RE::TESBoundObject healthDrink{ItemCategory::HealthPotion},magickaDrink{ItemCategory::MagickaPotion},staminaDrink{ItemCategory::StaminaPotion};
    healthArchive.inventory[&healthDrink]=entry(4);magickaArchive.inventory[&magickaDrink]=entry(5);staminaArchive.inventory[&staminaDrink]=entry(6);stores.ConsolidatePotions();
    assert(concoctions.inventory[&healthDrink].first==4 && concoctions.inventory[&magickaDrink].first==5 && concoctions.inventory[&staminaDrink].first==6);
    stores.OpenBookArchive(Container::HealthPotions,Container::Concoction,ItemCategory::HealthPotion,&activationSource);assert(stores.opened==Container::HealthPotions && healthArchive.inventory[&healthDrink].first==4);stores.onClose();assert(concoctions.inventory[&healthDrink].first==4);
    utility->custom.clear();


    player->inventory.clear();utility->junk.inventory.clear();utility->custom.clear();RE::TESBoundObject loanItem{ItemCategory::Junk},protectedLoan{ItemCategory::Junk};
    put(&loanItem,3);utility->junk.inventory[&loanItem]=entry(20);utility->junk.inventory[&protectedLoan]={4,std::make_shared<RE::InventoryEntryData>(false,true,false)};
    stores.BeginJunkLoan();assert(player->inventory[&loanItem].first==23 && utility->junk.inventory[&loanItem].first==0 && utility->junk.inventory[&protectedLoan].first==4);
    player->inventory[&loanItem].first-=5;stores.EndJunkLoan();assert(player->inventory[&loanItem].first==3 && utility->junk.inventory[&loanItem].first==15 && stores.junkLoan_.empty());
    stores.BeginJunkLoan();player->rejectMove=true;stores.EndJunkLoan();assert(player->inventory[&loanItem].first==18 && utility->junk.inventory[&loanItem].first==0);player->rejectMove=false;
    stores.BeginJunkLoan();stores.ResetJunkLoan();stores.EndJunkLoan();assert(player->inventory[&loanItem].first==18);

}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-key-check-") as temporary:
    path = Path(temporary)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: transfer reserves, large stacks, partial/refused moves, protections and quantity conservation")

program = r'''
#include <cassert>
#include <array>
#include <cstdint>
#include <set>
#include <string>
#include <vector>
#include <cctype>
#include <ranges>
#include <algorithm>
#include <string_view>
#include <type_traits>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
struct TESObjectBOOK {
    unsigned id=0;bool spell=false,skill=false,recipe=false,note=false;std::string model;
    bool TeachesSpell()const{return spell;}bool TeachesSkill()const{return skill;}bool IsNoteScroll()const{return note;}
    bool HasKeywordByEditorID(const char*)const{return recipe;}unsigned GetFormID()const{return id;}
};
struct TESDataHandler {std::vector<TESObjectBOOK*> books;template<class T>const auto& GetFormArray(){return books;}};
enum class ActorValue {kHealth,kHealRate,kHealRateMult,kMagicka,kMagickaRate,kMagickaRateMult,kStamina,kStaminaRate,kStaminaRateMult,kOther};
namespace EffectArchetypes {enum class ArchetypeID {kValueModifier,kPeakValueModifier,kDualValueModifier,kOther};}
struct EffectSetting {
    unsigned formID=0;bool hostile=false,detrimental=false;
    struct Data {ActorValue primaryAV=ActorValue::kHealth,secondaryAV=ActorValue::kMagicka;float secondAVWeight=0;EffectArchetypes::ArchetypeID archetype=EffectArchetypes::ArchetypeID::kValueModifier;}data;
    bool IsHostile()const{return hostile;}bool IsDetrimental()const{return detrimental;}auto GetArchetype()const{return data.archetype;}unsigned GetFormID()const{return formID;}
};
struct Effect {EffectSetting* baseEffect;float magnitude=10;float GetMagnitude()const{return magnitude;}};
struct AlchemyItem {bool food=false,poison=false;std::vector<Effect*> effects;bool IsFood()const{return food;}bool IsPoison()const{return poison;}};
struct TESObjectLIGH {bool carryable=true;bool CanBeCarried()const{return carryable;}};
struct TESObjectMISC {};
struct TESAmmo {};
struct ScrollItem {};
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
    bool HasPartOf(BipedObjectSlot) const;
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
    unsigned formID=0;unsigned GetFormID()const{return formID;}bool IsGold()const{return formID==0xF;}
    bool nativeAlchemy=false;AlchemyItem alchemy{};
    bool HasKeywordByEditorID(const char*)const{return false;}
    bool nativeLight=false;TESObjectLIGH light{};
    bool nativeBook=false;TESObjectBOOK book{};
    bool nativeMisc=false;TESObjectMISC misc{};
    bool nativeArmor = false;
    TESObjectARMO armor{};
    bool nativeAmmo = false;
    TESAmmo ammo{};
    bool nativeScroll = false;
    ScrollItem scroll{};
    template<class T> T* As() {
        if constexpr (std::is_same_v<T, AlchemyItem>) return nativeAlchemy ? &alchemy : nullptr;
        else if constexpr (std::is_same_v<T, TESObjectLIGH>) return nativeLight ? &light : nullptr;
        else if constexpr (std::is_same_v<T, TESObjectBOOK>) return nativeBook ? &book : nullptr;
        else if constexpr (std::is_same_v<T, TESObjectMISC>) return nativeMisc ? &misc : nullptr;
        else if constexpr (std::is_same_v<T, TESAmmo>) return nativeAmmo ? &ammo : nullptr;
        else if constexpr (std::is_same_v<T, ScrollItem>) return nativeScroll ? &scroll : nullptr;
        else return nativeArmor ? &armor : nullptr;
    }
};
}
'''
program += "struct Utility {std::set<unsigned> SmithingMap,SmeltingMap,TanningMap,ConstructionMap,SkillBookMap,RawFoodMap;RE::EffectSetting* RestoreHealth=nullptr;RE::EffectSetting* RestoreMagicka=nullptr;RE::EffectSetting* RestoreStamina=nullptr;bool FoundRestore(RE::AlchemyItem*);void CacheSkillBooks(RE::TESDataHandler*);static Utility* GetSingleton(){static Utility u;return &u;}};\n"
utility_source=(ROOT / "src/Utility.cpp").read_text()
a=utility_source.index("bool Utility::FoundRestore(")
program += utility_source[a:utility_source.index("\n}\n",a)+3]
a=utility_source.index("void Utility::CacheSkillBooks(")
program += utility_source[a:utility_source.index("\n}\n",a)+3]
biped_source = (ROOT / "lib/commonlibsse-ng/src/RE/B/BGSBipedObjectForm.cpp").read_text()
for name in ["HasPartOf", "IsClothing", "IsLightArmor", "IsHeavyArmor", "IsAccessory", "IsHelmet", "IsCirclet", "IsChestpiece", "IsBoots", "IsGauntlets", "IsShield"]:
    start = biped_source.index(f"bool BGSBipedObjectForm::{name}(")
    body = biped_source[start:biped_source.index("\n\t}", start) + 3]
    program += body.replace("BGSBipedObjectForm::", "RE::TESObjectARMO::") + "\n"
item_source = (ROOT / "src/ItemClass.cpp").read_text()
program += item_source[item_source.index("CategoryMask ToMask("):item_source.index("CategoryMask ParseCategories(")]
program += item_source[item_source.index("bool HasCategory("):item_source.index("[[nodiscard]] CategoryMask ExpandCategories(")]
expand_start=item_source.index("[[nodiscard]] CategoryMask ExpandCategories(")
program += item_source[expand_start:item_source.index("CategoryMask ClassifyItem(",expand_start)]
program += "CategoryMask ClassifyItem(RE::TESBoundObject* a_item) noexcept { CategoryMask categories=0;auto* utility=Utility::GetSingleton();\n"
gold_start=item_source.index("    if (a_item->GetFormID() == 0xA)")
program += item_source[gold_start:item_source.index("    if (a_item->IsKey())",gold_start)]
start=item_source.index("    // Crafting",gold_start)
program += item_source[start:item_source.index("    // Ingredients",start)]
scroll_start = item_source.index("    if (a_item->As<RE::ScrollItem>())")
program += item_source[scroll_start:item_source.index("    // Crafting", scroll_start)]
a=item_source.index("    // Food, Potions, and Poisons")
program += item_source[a:item_source.index("    // Armor and Clothing",a)]
program += item_source[item_source.index("    // Armor and Clothing"):item_source.index("    // Weapons", item_source.index("    // Armor and Clothing"))]
start=item_source.index("    // Books, Scrolls, and Spell Tomes")
program += item_source[start:item_source.index("\n    return categories;",start)]
program += "return categories; }\nint main() {\n"
program += r'''
    assert(HasCategory(ExpandCategories(ToMask(ItemCategory::Map)),ItemCategory::Note));
    RE::TESBoundObject potion{ItemCategory::None};potion.nativeAlchemy=true;RE::EffectSetting health;health.formID=5;RE::Effect effect{&health};RE::Effect missing{nullptr};
    potion.alchemy.effects={nullptr,&missing,&effect};assert(HasCategory(ClassifyItem(&potion),ItemCategory::HealthPotion));
    auto* potionUtility=Utility::GetSingleton();assert(!potionUtility->FoundRestore(nullptr));potionUtility->RestoreHealth=&health;assert(potionUtility->FoundRestore(&potion.alchemy));
    health.data.archetype=RE::EffectArchetypes::ArchetypeID::kDualValueModifier;health.data.secondAVWeight=1;
    assert(HasCategory(ClassifyPotionEffects(&potion.alchemy),ItemCategory::MagickaPotion));health.data.secondAVWeight=0;assert(!HasCategory(ClassifyPotionEffects(&potion.alchemy),ItemCategory::MagickaPotion));
    for(auto [value,category]:{std::pair{RE::ActorValue::kHealth,ItemCategory::HealthPotion},std::pair{RE::ActorValue::kHealRate,ItemCategory::HealthPotion},std::pair{RE::ActorValue::kHealRateMult,ItemCategory::HealthPotion},std::pair{RE::ActorValue::kMagicka,ItemCategory::MagickaPotion},std::pair{RE::ActorValue::kMagickaRate,ItemCategory::MagickaPotion},std::pair{RE::ActorValue::kMagickaRateMult,ItemCategory::MagickaPotion},std::pair{RE::ActorValue::kStamina,ItemCategory::StaminaPotion},std::pair{RE::ActorValue::kStaminaRate,ItemCategory::StaminaPotion},std::pair{RE::ActorValue::kStaminaRateMult,ItemCategory::StaminaPotion}}){health.data.primaryAV=value;assert(HasCategory(ClassifyPotionEffects(&potion.alchemy),category));}
    health.hostile=true;assert(ClassifyPotionEffects(&potion.alchemy)==0);health.hostile=false;health.detrimental=true;assert(ClassifyPotionEffects(&potion.alchemy)==0);health.detrimental=false;
    effect.magnitude=0;assert(ClassifyPotionEffects(&potion.alchemy)==0);effect.magnitude=10;potion.alchemy.poison=true;assert(ClassifyPotionEffects(&potion.alchemy)==0);potion.alchemy.poison=false;potion.alchemy.food=true;assert(ClassifyPotionEffects(&potion.alchemy)==0);potion.alchemy.food=false;
    assert(HasCategory(ExpandCategories(ToMask(ItemCategory::HealthPotion)),ItemCategory::Potion) && HasCategory(ExpandCategories(ToMask(ItemCategory::HealthPotion)),ItemCategory::Concoction));
    RE::TESBoundObject nativeBook{ItemCategory::None};nativeBook.nativeBook=true;nativeBook.book.id=0x12345;
    assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::Book));nativeBook.book.skill=true;
    RE::TESDataHandler data;data.books={&nativeBook.book,nullptr};Utility::GetSingleton()->CacheSkillBooks(&data);nativeBook.book.skill=false;
    assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::SkillBook));
    Utility::GetSingleton()->CacheSkillBooks(nullptr);assert(!HasCategory(ClassifyItem(&nativeBook),ItemCategory::SkillBook));
    nativeBook.book.spell=true;assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::SpellTome));nativeBook.book.spell=false;
    nativeBook.book.recipe=true;assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::Recipe) && HasCategory(ClassifyItem(&nativeBook),ItemCategory::Note));nativeBook.book.recipe=false;
    for(auto model:{"Clutter/Books/Note.nif","mods/NOtePaper.NIF"}){nativeBook.book.model=model;assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::Note));}
    nativeBook.book.model="clutter/books/book.nif";assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::Book));
    nativeBook.book.note=true;assert(HasCategory(ClassifyItem(&nativeBook),ItemCategory::Note));
    RE::TESBoundObject lockpick{ItemCategory::None},torch{ItemCategory::None};lockpick.formID=0xA;torch.nativeLight=true;
    assert(HasCategory(ClassifyItem(&lockpick),ItemCategory::Lockpick) && HasCategory(ClassifyItem(&lockpick),ItemCategory::Gear));
    assert(HasCategory(ClassifyItem(&torch),ItemCategory::Gear));torch.light.carryable=false;assert(!HasCategory(ClassifyItem(&torch),ItemCategory::Gear));
    assert(HasCategory(ExpandCategories(ToMask(ItemCategory::Instrument)),ItemCategory::Gear));
    RE::TESBoundObject nativeGold{ItemCategory::None},nativeIngot{ItemCategory::None};nativeGold.formID=0xF;nativeIngot.formID=0x5AD9E;nativeIngot.nativeMisc=true;
    assert(HasCategory(ClassifyItem(&nativeGold),ItemCategory::Gold));assert(HasCategory(ClassifyItem(&nativeIngot),ItemCategory::PreciousIngot) && HasCategory(ClassifyItem(&nativeIngot),ItemCategory::Smithing));
    RE::TESBoundObject nativeSpellScroll{ItemCategory::None}, ordinary{ItemCategory::None};
    RE::TESBoundObject nativeAmmo{ItemCategory::None};nativeAmmo.nativeAmmo=true;
    assert(HasCategory(ClassifyItem(&nativeAmmo),ItemCategory::Ammunition));
    nativeSpellScroll.nativeScroll = true;
    assert(HasCategory(ClassifyItem(&nativeSpellScroll), ItemCategory::Scroll));
    assert(!HasCategory(ClassifyItem(&ordinary), ItemCategory::Scroll));
    RE::TESBoundObject helmet{ItemCategory::None}, hat{ItemCategory::None}, robe{ItemCategory::None}, nativeRing{ItemCategory::None}, circlet{ItemCategory::None}, amulet{ItemCategory::None}, ironPlate{ItemCategory::None}, keywordHelmet{ItemCategory::None};
    for (auto* item : {&helmet, &hat, &robe, &nativeRing, &circlet, &amulet, &ironPlate, &keywordHelmet}) item->nativeArmor = true;
    helmet.armor.bipedModelData.bipedObjectSlots.bits = 1 | 2 | 4096;
    helmet.armor.bipedModelData.armorType = RE::BIPED_MODEL::ArmorType::kHeavyArmor;
    hat.armor.bipedModelData.bipedObjectSlots.bits = 2 | 4096;
    robe.armor.bipedModelData.bipedObjectSlots.bits = 4 | 32;
    nativeRing.armor.bipedModelData.bipedObjectSlots.bits = 64;
    circlet.armor.bipedModelData.bipedObjectSlots.bits = 4096;
    amulet.armor.bipedModelData.bipedObjectSlots.bits = 32;
    for (auto* item : {&ironPlate, &keywordHelmet}) {
        item->armor.bipedModelData.bipedObjectSlots.bits = 1 | 4096;
        item->armor.bipedModelData.armorType = RE::BIPED_MODEL::ArmorType::kHeavyArmor;
        assert(item->armor.IsCirclet() && !item->armor.IsHelmet());
        assert(HasCategory(ClassifyItem(item), ItemCategory::HeavyArmor));
    }
    keywordHelmet.armor.jewelryKeyword = true;
    assert(HasCategory(ClassifyItem(&keywordHelmet), ItemCategory::HeavyArmor));
    for (auto* item : {&helmet, &hat, &robe, &ironPlate, &keywordHelmet}) assert(!HasCategory(ClassifyItem(item), ItemCategory::Jewelry));
    assert(HasCategory(ClassifyItem(&helmet), ItemCategory::HeavyArmor));
    for (auto* item : {&hat, &robe}) assert(HasCategory(ClassifyItem(item), ItemCategory::Clothing));
    for (auto* item : {&nativeRing, &circlet, &amulet}) assert(HasCategory(ClassifyItem(item), ItemCategory::Jewelry));

}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-jewelry-check-") as temporary:
    path = Path(temporary)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: native armor slot and keyword Jewelry classification")

map_lines=[line for line in (ROOT / "ini/ArcaneVaultOverrides.ini").read_text().splitlines() if line.strip().endswith("= Map")]
assert len(map_lines)==21
assert {int(line.split("|0x")[1].split()[0],16) for line in map_lines if line.startswith("ccBGSSSE001-Fish.esm|")} == set(range(0x70CCC,0x70CD4))
print("PASS: official treasure and Fishing map defaults")
