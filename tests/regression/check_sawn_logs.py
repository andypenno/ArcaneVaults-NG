"""Exercise sawn-log recovery through physical inventory boundaries."""
from pathlib import Path
import subprocess
import tempfile
from support.engine import ROOT

common=(ROOT / "tests/support/engine.hpp").read_text().split('#include "src/PlayerEquipment.h"',1)[0]
common=common.replace('struct TESDataHandler {', 'struct TESDataHandler {inline static TESBoundObject* logs=nullptr;')
common=common.replace('assert((id==0xDE0', 'if constexpr(std::is_same_v<T,TESBoundObject>){assert(id==0x300E && plugin=="HearthFires.esm");return logs;}else{assert((id==0xDE0')
common=common.replace('&enchantedKeyword:&favoriteKeyword;} };', '&enchantedKeyword:&favoriteKeyword;}} };')
common += r'''
#include "src/InventoryStacks.h"
inline bool ignoreLogs=true;
inline CategoryMask ClassifyItem(RE::TESBoundObject*)noexcept{return CategoryMask{1}<<static_cast<unsigned>(ignoreLogs?ItemCategory::Ignore:ItemCategory::Construction);}
inline bool HasCategory(CategoryMask mask,ItemCategory c)noexcept{return (mask&(CategoryMask{1}<<static_cast<unsigned>(c)))!=0;}
struct Stores {void RecoverSawnLogs();};
'''
source=(ROOT / "src/Stores.cpp").read_text();a=source.index('void Stores::RecoverSawnLogs(')
program=source[a:source.index('\n}',a)+2]+r'''
int main(){
    Stores stores;RE::TESBoundObject logs{0x0800300E};RE::TESDataHandler::logs=&logs;
    auto* player=RE::PlayerCharacter::GetSingleton();auto* utility=Utility::GetSingleton();RE::TESForm owner{7000};
    std::vector<std::unique_ptr<RE::TESObjectREFR>> banks;
    for(auto kind:{Container::Smithing,Container::Construction,Container::Crafting,Container::Smelting,Container::Tanning,Container::Gemstone,Container::Remains,Container::Sort,Container::Junk}){
        auto bank=std::make_unique<RE::TESObjectREFR>(8000+banks.size());bank->limit=7;bank->Put(&logs,0,100,&owner,"stored timber");utility->containers[kind]=bank.get();banks.push_back(std::move(bank));
    }
    stores.RecoverSawnLogs();assert(InventoryStacks::Count(player,&logs)==900);
    for(auto& bank:banks)assert(InventoryStacks::Count(bank.get(),&logs)==0);
    for(auto stack:InventoryStacks::Read(player,{},&logs))assert(stack.extra && stack.extra->owner==&owner && stack.extra->metadata=="stored timber");
    stores.RecoverSawnLogs();assert(InventoryStacks::Count(player,&logs)==900);
    auto* bank=banks.front().get();bank->Put(&logs,20);bank->refuse=true;stores.RecoverSawnLogs();assert(InventoryStacks::Count(bank,&logs)==20);
    bank->refuse=false;bank->rows[&logs].quest=true;stores.RecoverSawnLogs();assert(InventoryStacks::Count(bank,&logs)==20);
    bank->rows[&logs].quest=false;ignoreLogs=false;stores.RecoverSawnLogs();assert(InventoryStacks::Count(bank,&logs)==20);
    ignoreLogs=true;stores.RecoverSawnLogs();assert(InventoryStacks::Count(bank,&logs)==0 && InventoryStacks::Count(player,&logs)==920);
    RE::TESDataHandler::logs=nullptr;stores.RecoverSawnLogs();
}
'''
with tempfile.TemporaryDirectory(prefix="av-sawn-logs-") as directory:
    root=Path(directory);(root / "common.hpp").write_text(common);(root / "check.cpp").write_text(program)
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror","-I",str(ROOT),"-include",str(root / "common.hpp"),str(ROOT / "src/InventoryStacks.cpp"),str(root / "check.cpp"),"-o",str(root / "check")],check=True,timeout=90)
    subprocess.run([str(root / "check")],check=True,timeout=15)
print("PASS: all recovery stores, partial/refused moves, ownership metadata, quest protection, override opt-out and repeated recovery")
