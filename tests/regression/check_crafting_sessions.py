"""Exercise production crafting-session generations and furniture identity guards."""
from pathlib import Path
import subprocess
import tempfile
from support.engine import ROOT
common=(ROOT / "tests/support/engine.hpp").read_text().split('#include "src/PlayerEquipment.h"',1)[0]
common=common.replace("struct Utility {","struct Utility {BenchType bench=BenchType::Alchemy;BenchType GetBenchType(RE::TESObjectREFR*)const{return bench;}")
common += r'''
#include <utility>
struct Settings {bool GSC_CraftingLoan=true;static Settings* GetSingleton(){static Settings settings;return &settings;}};
struct Stores {
    int begins=0,ends=0,returns=0;
    static Stores* GetSingleton(){static Stores stores;return &stores;}
    void BeginJunkLoan(){++begins;}void EndJunkLoan(){++ends;}void ResetJunkLoan(){}
    void AllToPlayer(Container){}void StoreToPlayer(ItemCategory,Container){}void PlayerToStore(ItemCategory,Container){++returns;}
};
namespace Soulgems {inline int begins=0,ends=0;void BeginLoan(bool){++begins;}void EndLoan(){++ends;}void ResetLoan(){}}
'''
events=(ROOT / "src/Events.cpp").read_text()
a=events.index("class CraftingLoanState {");b=events.index("class FurnitureActivation {",a)
program='#include "common.hpp"\n'+events[a:b]+r'''
int main(){
    auto* session=CraftingLoanState::GetSingleton();auto* stores=Stores::GetSingleton();auto* settings=Settings::GetSingleton();auto* utility=Utility::GetSingleton();auto* tasks=SKSE::GetTaskInterface();auto* player=RE::PlayerCharacter::GetSingleton();
    RE::TESObjectREFR first{5101},second{5102},otherActor{5103};
    for(auto bench:{BenchType::Alchemy,BenchType::Smithing,BenchType::Cooking,BenchType::Enchanting,BenchType::StaffEnchanting}){
        session->Reset();utility->bench=bench;settings->GSC_CraftingLoan=true;const int begins=stores->begins,ends=stores->ends,soulBegins=Soulgems::begins,soulEnds=Soulgems::ends;
        session->EnterCrafting(&first);assert(stores->begins==begins+1);settings->GSC_CraftingLoan=false;session->ExitCrafting();session->ExitCrafting();
        assert(stores->ends==ends+1);const int gems=bench==BenchType::Smithing || bench==BenchType::Enchanting;assert(Soulgems::begins==soulBegins+gems && Soulgems::ends==soulEnds+gems);
    }
    settings->GSC_CraftingLoan=true;utility->bench=BenchType::None;const int begins=stores->begins;session->EnterCrafting(&first);assert(stores->begins==begins);
    utility->bench=BenchType::Alchemy;settings->GSC_CraftingLoan=false;session->EnterCrafting(&first);assert(stores->begins==begins);settings->GSC_CraftingLoan=true;
    session->EnterCrafting(&first);session->QueueExitCrafting();session->EnterCrafting(&second);const int switched=stores->ends;tasks->Run();assert(stores->ends==switched);
    RE::TESFurnitureEvent unrelated{{&otherActor},{&second},RE::TESFurnitureEvent::FurnitureEventType::kExit};RE::TESFurnitureEvent stale{{player},{&first},RE::TESFurnitureEvent::FurnitureEventType::kExit};RE::TESFurnitureEvent exit{{player},{&second},RE::TESFurnitureEvent::FurnitureEventType::kExit};
    session->FurnitureEvent(unrelated);session->FurnitureEvent(stale);tasks->Run();assert(stores->ends==switched);
    session->FurnitureEvent(exit);session->FurnitureEvent(exit);tasks->Run();assert(stores->ends==switched+1);
    session->EnterCrafting(&first);session->QueueExitCrafting();session->Reset();const int reset=stores->ends;tasks->Run();assert(stores->ends==reset);
    session->EnterCrafting(&first);RE::TESForm::refs.erase(first.id);RE::TESFurnitureEvent expired{{player},{&first},RE::TESFurnitureEvent::FurnitureEventType::kExit};session->FurnitureEvent(expired);tasks->Run();assert(stores->ends==reset);
    session->QueueExitCrafting();tasks->Run();assert(stores->ends==reset+1);RE::TESForm::refs[first.id]=&first;
}
'''
assert 'AddEventSink<RE::TESFurnitureEvent>' in events
with tempfile.TemporaryDirectory(prefix="av-crafting-session-") as directory:
    root=Path(directory);(root / "common.hpp").write_text(common);(root / "check.cpp").write_text(program)
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror","-I",str(ROOT),"-I",str(root),str(root / "check.cpp"),"-o",str(root / "check")],check=True,timeout=90)
    subprocess.run([str(root / "check")],check=True,timeout=15)
print("PASS: captured loan options, every station, stale and duplicate exits, furniture identity, expired references and load reset")
