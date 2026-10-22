"""Exercise the complete stolen archive and physical-stack modules at engine boundaries."""
from pathlib import Path
import subprocess
import tempfile
from support.engine import ROOT

common=(ROOT / "tests/support/engine.hpp").read_text().split('#include "src/PlayerEquipment.h"',1)[0]
common += r'''
#include "src/StolenItems.h"
struct Settings {bool GSC_AllowRemovingStolenTags=false;static Settings* GetSingleton(){static Settings settings;return &settings;}};
struct MenuOption {std::string text;std::function<void()> action;};
struct Stores {
    std::vector<MenuOption> options;
    static Stores* GetSingleton(){static Stores stores;return &stores;}
    void ShowDynamicMessageBox(const char*,std::vector<MenuOption> values,int cancel){assert(cancel==0);options=std::move(values);}
};
namespace AVTranslation {inline const char* Translate(const char* key){return key;}}
'''
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
}
'''
with tempfile.TemporaryDirectory(prefix="av-stolen-") as directory:
    root=Path(directory);(root / "common.hpp").write_text(common);(root / "check.cpp").write_text(program)
    stolen=(ROOT / "src/StolenItems.cpp").read_text()
    stolen="\n".join(line for line in stolen.splitlines() if not line.startswith('#include "'))
    (root / "StolenItems.cpp").write_text(stolen)
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror","-I",str(ROOT),"-I",str(root),"-include",str(root / "common.hpp"),str(ROOT / "src/InventoryStacks.cpp"),str(root / "StolenItems.cpp"),str(root / "check.cpp"),"-o",str(root / "check")],check=True,timeout=90)
    subprocess.run([str(root / "check")],check=True,timeout=15)
print("PASS: stolen physical metadata, parent returns, excluded containers, failures, consent and stale confirmations")
