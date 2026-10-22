"""Exercise the complete stolen archive and physical-stack modules at engine boundaries."""
from pathlib import Path
import subprocess
import tempfile
from support.engine import ROOT

common=(ROOT / "tests/support/engine.hpp").read_text().split('#include "src/PlayerEquipment.h"',1)[0]
common += r'''
#include "src/StolenItems.h"
#include "src/EnchantedItems.h"
struct Settings {bool GSC_ReturnIgnoredItems=false;bool IsIgnored(RE::TESBoundObject*)const{return false;}bool GSC_AllowRemovingStolenTags=false;static Settings* GetSingleton(){static Settings settings;return &settings;}};
inline CategoryMask ClassifyItem(RE::TESBoundObject*)noexcept{return CategoryMask{1}<<static_cast<unsigned>(ItemCategory::Junk);}
inline bool HasCategory(CategoryMask mask,ItemCategory c)noexcept{return (mask&(CategoryMask{1}<<static_cast<unsigned>(c)))!=0;}
namespace DepositLearning {inline void RecordAutomaticTransfer(RE::TESObjectREFR*,RE::TESObjectREFR*,RE::TESBoundObject*,int){}}
struct MenuOption {std::string text;std::function<void()> action;};
struct Stores {
    std::vector<MenuOption> options;void AllToStore(Container,Container);
    static Stores* GetSingleton(){static Stores stores;return &stores;}
    void ShowDynamicMessageBox(const char*,std::vector<MenuOption> values,int cancel){assert(cancel==0);options=std::move(values);}
};
namespace AVTranslation {inline const char* Translate(const char* key){return key;}}
'''
stores_source=(ROOT / "src/Stores.cpp").read_text()
a=stores_source.index("    int MoveItems(")
common += stores_source[a:stores_source.index("\n    }",a)+6].replace("int MoveItems(","inline int MoveItems(",1)
a=stores_source.index("void Stores::AllToStore(")
common += stores_source[a:stores_source.index("\n}\n",a)+3].replace("void Stores::AllToStore(","inline void Stores::AllToStore(",1)
program=r'''#include "common.hpp"
int main(){
    RE::TESObjectREFR vault{1001},archive{1002},trade{1003},sort{1004},ignore{1005},unknown{1006};
    auto* u=Utility::GetSingleton();auto* player=RE::PlayerCharacter::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    u->containers={{Container::StolenItems,&archive},{Container::Trade,&trade},{Container::Sort,&sort},{Container::Ignore,&ignore}};
    u->vaults={{vault.id},{trade.id},{sort.id},{ignore.id},{vault.id},{9999}};
    RE::TESBoundObject item{2001};RE::TESForm foreign{2002},owned{2003,true};RE::EnchantmentItem enchantment;
    vault.Put(&item,5);vault.Put(&item,0,3,&foreign,"named enchanted copy");vault.Put(&item,0,2,&owned,"owned copy");
    auto* extra=vault.rows[&item].extras.front().get();extra->enchantment=RE::ExtraEnchantment{&enchantment};extra->displayName="Named";extra->charge=42;extra->temper=3;
    trade.Put(&item,0,2,&foreign,"trade");sort.Put(&item,0,2,&foreign,"sort");ignore.Put(&item,0,2,&foreign,"ignore");
    StolenItems::Init();assert(StolenItems::GetStoredStacks().size()==1);assert(StolenItems::Gather());
    assert(InventoryStacks::Count(&archive,&item)==3 && InventoryStacks::Count(&vault,&item)==7);
    auto moved=InventoryStacks::Read(&archive);assert(moved.size()==1 && moved.front().extra->owner==&foreign && moved.front().extra->enchantment->enchantment==&enchantment && moved.front().extra->displayName=="Named" && moved.front().extra->charge==42 && moved.front().extra->temper==3);
    assert(StolenItems::Return() && InventoryStacks::Count(&vault,&item)==10 && !InventoryStacks::HasItems(&archive));
    assert(InventoryStacks::Count(&trade,&item)==2 && InventoryStacks::Count(&sort,&item)==2 && InventoryStacks::Count(&ignore,&item)==2);
    vault.refuse=true;assert(!StolenItems::Gather() && InventoryStacks::Count(&vault,&item)==10);vault.refuse=false;
    assert(!StolenItems::Clear() && !StolenItems::GetStacks(&vault).empty());
    auto* settings=Settings::GetSingleton();settings->GSC_AllowRemovingStolenTags=true;
    int finished=0;StolenItems::ConfirmClear([&]{++finished;});auto yes=Stores::GetSingleton()->options.at(1).action;StolenItems::Reset();yes();tasks->Run();assert(finished==0 && !StolenItems::GetStacks(&vault).empty());
    StolenItems::ConfirmClear([&]{++finished;});auto no=Stores::GetSingleton()->options.at(0).action;no();tasks->Run();assert(finished==1 && !StolenItems::GetStacks(&vault).empty());
    StolenItems::ConfirmClear([&]{++finished;});yes=Stores::GetSingleton()->options.at(1).action;settings->GSC_AllowRemovingStolenTags=false;yes();tasks->Run();assert(finished==2 && !StolenItems::GetStacks(&vault).empty());
    settings->GSC_AllowRemovingStolenTags=true;assert(StolenItems::Clear());assert(StolenItems::GetStacks(&vault).empty() && InventoryStacks::Count(&vault,&item)==10);
    vault.Put(&item,0,1,&foreign,"withdrawn");assert(StolenItems::Gather());moved=InventoryStacks::Read(&archive);assert(InventoryStacks::Move(moved.front(),player)==1);tasks->Run();
    auto* key=&RE::TESDataHandler::GetSingleton()->keyword;assert(!InventoryStacks::HasOrigin(InventoryStacks::Read(player).front().extra,key));
    archive.Put(&item,0,1,&foreign,"unknown origin");archive.rows[&item].extras.back()->SetLinkedRef(&unknown,key);assert(!StolenItems::Return() && InventoryStacks::Count(&archive,&item)==1);

    RE::TESObjectREFR weapons{3001},armor{3002},equipmentArchive{3003};
    u->containers[Container::Weapon]=&weapons;u->containers[Container::Armor]=&armor;u->containers[Container::EnchantedItems]=&equipmentArchive;
    RE::TESBoundObject sword{4001,true},robe{4002,false,true},plain{4003,true},staff{4004,true},mixedSword{4005,true};staff.weaponData.staff=true;
    RE::EnchantmentItem fire,frost;sword.enchantable.formEnchanting=&fire;
    weapons.Put(&sword,40000);weapons.Put(&plain,9);weapons.Put(&staff,0,2);weapons.rows[&staff].extras.back()->enchantment=RE::ExtraEnchantment{&fire};
    armor.Put(&robe,0,2,&foreign,"frost robe");armor.rows[&robe].extras.back()->enchantment=RE::ExtraEnchantment{&frost};armor.rows[&robe].extras.back()->displayName="Frost Robe";
    for(auto* enchantment:{&fire,&frost}){weapons.Put(&mixedSword,0,2,&foreign,"custom variant");weapons.rows[&mixedSword].extras.back()->enchantment=RE::ExtraEnchantment{enchantment};}
    EnchantedItems::Init();assert(EnchantedItems::Gather());
    assert(InventoryStacks::Count(&equipmentArchive,&sword)==40000 && InventoryStacks::Count(&equipmentArchive,&robe)==2 && InventoryStacks::Count(&weapons,&plain)==9 && InventoryStacks::Count(&weapons,&staff)==2);
    assert(InventoryStacks::Count(&equipmentArchive,&mixedSword)==4);
    equipmentArchive.refuse=true;assert(!EnchantedItems::Recover() && InventoryStacks::Count(&equipmentArchive,&sword)==40000);equipmentArchive.refuse=false;
    assert(EnchantedItems::Recover() && InventoryStacks::Count(&weapons,&sword)==40000 && InventoryStacks::Count(&armor,&robe)==2 && !InventoryStacks::HasItems(&equipmentArchive));
    std::unordered_set<RE::EnchantmentItem*> variants;for(auto& stack:InventoryStacks::Read(&weapons,{},&mixedSword))variants.insert(stack.extra->enchantment->enchantment);assert((variants==std::unordered_set<RE::EnchantmentItem*>{&fire,&frost}));
    auto robeStacks=InventoryStacks::Read(&armor);assert(robeStacks.front().extra->enchantment->enchantment==&frost && robeStacks.front().extra->displayName=="Frost Robe" && robeStacks.front().extra->owner==&foreign);
    RE::InventoryEntryData entry(&sword,0);assert(EnchantedItems::Eligible(&sword,entry,nullptr));entry.quest=true;assert(!EnchantedItems::Eligible(&sword,entry,nullptr));entry.quest=false;
    sword.keywords.blocked=true;assert(!EnchantedItems::Eligible(&sword,entry,nullptr));sword.keywords.blocked=false;
    fire.data.baseEnchantment=&fire;assert(!EnchantedItems::Eligible(&sword,entry,nullptr));fire.data.baseEnchantment=nullptr;
    weapons.refuse=true;assert(!EnchantedItems::Gather() && InventoryStacks::Count(&weapons,&sword)==40000);weapons.refuse=false;

}
'''
with tempfile.TemporaryDirectory(prefix="av-stolen-") as directory:
    root=Path(directory);(root / "common.hpp").write_text(common);(root / "check.cpp").write_text(program)
    stolen=(ROOT / "src/StolenItems.cpp").read_text()
    stolen="\n".join(line for line in stolen.splitlines() if not line.startswith('#include "'))
    (root / "StolenItems.cpp").write_text(stolen)
    enchanted=(ROOT / "src/EnchantedItems.cpp").read_text()
    enchanted="\n".join(line for line in enchanted.splitlines() if not line.startswith('#include "'))
    (root / "EnchantedItems.cpp").write_text(enchanted)
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror","-I",str(ROOT),"-I",str(root),"-include",str(root / "common.hpp"),str(ROOT / "src/InventoryStacks.cpp"),str(root / "StolenItems.cpp"),str(root / "EnchantedItems.cpp"),str(root / "check.cpp"),"-o",str(root / "check")],check=True,timeout=90)
    subprocess.run([str(root / "check")],check=True,timeout=15)
print("PASS: stolen and enchanted metadata, distinct enchantments on one base, 40000-copy materialization, eligibility, parent returns, failures and stale confirmations")
