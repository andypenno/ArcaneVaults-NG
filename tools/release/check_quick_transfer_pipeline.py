"""Exercise inspection, full Quick Transfer, consolidation and return as one interaction."""
import argparse
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile

import check_stolen as harness

ROOT=harness.ROOT
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--sanitize",action="store_true")
parser.add_argument("--source-ref")
args=parser.parse_args()
if args.output.exists():parser.error("Choose a new output path")
def source(name):
    return subprocess.check_output(["git","show",f"{args.source_ref}:src/{name}.cpp"],cwd=ROOT,text=True) if args.source_ref else (ROOT/f"src/{name}.cpp").read_text()
stores=source("Stores")
common=harness.common
common=common.replace("unsigned id;int limit=", "int state=2;bool stalled=false;unsigned id;int limit=")
common=common.replace("TESObjectREFR* get()const{return value;}", "TESObjectREFR* get()const{return value;}TESObjectREFR* operator->()const{return value;}")
common=common.replace("enum class ITEM_REMOVE_REASON", "using ObjectRefHandle=Handle;\nenum class ITEM_REMOVE_REASON")
common=common.replace("bool weapon=false,armor=false;", "bool weapon=false,armor=false;CategoryMask categories=0;")
common=common.replace("return ToMask(item->armor?ItemCategory::Jewelry:ItemCategory::Weapon);", "return item->categories;")
fields="\n".join(line for line in (ROOT/"src/Settings.h").read_text().splitlines() if line.strip().startswith(("bool GSC_","int GSC_")))
common=common.replace("struct Settings {bool GSC_AllowRemovingStolenTags=false;", "struct Settings {"+fields)
common=common.replace("struct Utility {", "struct Utility {struct Entry{RE::TESObjectREFR* container;std::function<void(RE::TESObjectREFR*)> action;};std::map<Container,Entry> containerMap;bool RunContainerAction(const RE::TESObjectREFR*,RE::TESObjectREFR*)const;")
common=common.replace("TESBoundObject* currentAmmo=nullptr;", "bool IsSneaking()const{return false;}TESBoundObject* currentAmmo=nullptr;")
start=common.index("    void AllToStore(Container from,")
end=common.index("\n    }",start)+6
common=common[:start]+"    void AllToStore(Container,Container);\n"+common[end:]
common=common.replace("void OffloadItemsNow(){PlayerToStore(ItemCategory::Jewelry,Container::Armor);}", "void OffloadItemsNow();")
common=common.replace("void OpenStoreObject(RE::TESObjectREFR* source,std::function<void(RE::TESObjectREFR*)> f){f(source);}", "using AnimationCallback=std::function<void(RE::TESObjectREFR*)>;void OpenStoreObject(RE::TESObjectREFR*,AnimationCallback);")
common=common.replace("void VaultMenu(RE::TESObjectREFR*){closed=false;options.clear();returnToVault_={};}", "void VaultMenu(RE::TESObjectREFR*);void ShowVaultMenu(RE::TESObjectREFR*);")
common=common.replace("options=std::move(value);cancel=c;", "options=std::move(value);cancel=c;RE::UI::GetSingleton()->messageBox=true;")
common=common.replace("struct Stores {", """struct Stores {
    std::unordered_set<RE::FormID> sortFavorites_;
    void ResetNavigation(){navigationSource_={};returnToVault_={};}
    void IgnoreMenu(RE::TESObjectREFR*){}
    void ShowVaultsMenu(RE::TESObjectREFR*){}
    void ShowVaultArchivesMenu(RE::TESObjectREFR*){}
    void SortItems(){}
    void StoreToStore(ItemCategory,Container,Container);
    void ConsolidateBooks();void ConsolidatePotions();void KeepAmmunition(bool);
""")
common += r'''
#include <iostream>
struct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};
std::deque<std::function<void()>> timers;
struct TestThread {template<class F> explicit TestThread(F action){timers.emplace_back(std::move(action));}void detach(){}};
namespace logger {template<class... T> void warn(const char*,T...) {}}
namespace RE {
struct BGSOpenCloseForm {
    enum class OPEN_STATE {kClosed,kClosing,kOpen,kOpening};
    static OPEN_STATE GetOpenState(TESObjectREFR* ref){return static_cast<OPEN_STATE>(ref->state);}
    static void SetOpenState(TESObjectREFR* ref,bool open,bool){ref->state=open?(ref->stalled?3:2):0;}
};
struct MessageBoxMenu;
}
namespace Soulgems {void Deposit(int,bool){}}
'''

def body(text,signature,ending="\n}\n"):
    start=text.index(signature)
    return text[start:text.index(ending,start)+len(ending)]

program='#include "common.hpp"\n'
item_source=(ROOT/"src/ItemClass.cpp").read_text()
program+=item_source[item_source.index("CategoryMask operator|("):item_source.index("bool HasCategory(")]
for name in ("InventoryStacks","PlayerEquipment"):
    text=source(name)
    if name=="PlayerEquipment":
        text=text.replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;")
        start=text.index("        void Later(")
        end=text.index("\n        void Close(",start)
        text=text[:start]+"        void Later(const std::shared_ptr<Request>& request){timers.emplace_back([request]{Poll(request);});}\n"+text[end:]
    program+="\n".join(line for line in text.splitlines() if not line.startswith("#include"))+"\n"
program+=body(stores,"    int MoveItems(","\n    }")
program+=body(stores,"    std::unordered_set<RE::FormID> SelectedAmmunition(","\n    }")
animation=stores[stores.index("    using OpenState ="):stores.index("\n}\n\nusing AVTranslation")]
animation=animation.replace("std::chrono::steady_clock","ProbeClock").replace("std::thread(","TestThread(").replace("std::this_thread::sleep_for(std::chrono::milliseconds(16));","")
program+=animation
for name in ("PlayerToStore","StoreToStore","AllToStore","ConsolidateBooks","ConsolidatePotions","KeepAmmunition","OffloadItemsNow","OffloadItems","OpenStoreObject","VaultMenu","ShowVaultMenu"):
    program+=body(stores,"void Stores::"+name+"(")
program+=body((ROOT/"src/Utility.cpp").read_text(),"bool Utility::RunContainerAction(")
program+=r'''
int main(){
    auto* player=RE::PlayerCharacter::GetSingleton();auto* utility=Utility::GetSingleton();auto* stores=Stores::GetSingleton();
    auto* tasks=SKSE::GetTaskInterface();auto* ui=RE::UI::GetSingleton();auto* queue=RE::UIMessageQueue::GetSingleton();
    std::map<Container,std::unique_ptr<RE::TESObjectREFR>> banks;
    for(auto kind:{Container::Armor,Container::Weapon,Container::Book,Container::Notes,Container::Scroll,Container::SpellTomes,Container::SkillBooks,
        Container::Recipes,Container::TreasureMaps,Container::Concoction,Container::Potion,Container::Poison,Container::Restorative,
        Container::HealthPotions,Container::MagickaPotions,Container::StaminaPotions,Container::Gear,Container::Instruments,Container::Keys,Container::Soulgem}){
        banks[kind]=std::make_unique<RE::TESObjectREFR>(9000+static_cast<unsigned>(kind));utility->containers[kind]=banks[kind].get();
    }
    RE::TESObjectREFR chest{8000},assignment{8001};RE::TESBoundObject ring{200,false,true},note{201},book{202},potion{203},instrument{204},lockpick{205};
    ring.categories=ToMask(ItemCategory::Jewelry)|ToMask(ItemCategory::Armor);note.categories=ToMask(ItemCategory::Note);book.categories=ToMask(ItemCategory::Book);
    potion.categories=ToMask(ItemCategory::Potion);instrument.categories=ToMask(ItemCategory::Gear);lockpick.categories=ToMask(ItemCategory::Lockpick)|ToMask(ItemCategory::Gear);
    auto* settings=Settings::GetSingleton();settings->GSC_OffloadSoulgems=false;settings->GSC_OffloadJewelry=settings->GSC_OffloadNotes=settings->GSC_OffloadBooks=settings->GSC_OffloadGear=true;
    settings->GSC_LockpickKeepAmount=25;
    utility->containerMap[Container::QuickTransfer]={&assignment,[](RE::TESObjectREFR*){Stores::GetSingleton()->OffloadItems();}};
    for(int entry=0;entry<3;++entry)for(int shape=0;shape<4;++shape)for(bool stalled:{false,true}){
        player->rows.clear();for(auto& [kind,bank]:banks){(void)kind;bank->rows.clear();}
        RE::SCRIPT_FUNCTION::equipped.clear();timers.clear();ProbeClock::tick={};ui->messageBox=false;stores->options.clear();stores->ResetNavigation();
        chest.stalled=stalled;chest.state=stalled?3:2;
        if(shape==1 || shape==2){player->Put(&ring,0,1,nullptr,"worn");player->rows[&ring].extras.front()->uiWorn=true;RE::SCRIPT_FUNCTION::equipped.insert(&ring);}
        if(shape==2)player->Put(&ring,0,2,nullptr,"spare");
        if(shape==3){player->Put(&note,2);player->Put(&book,2);player->Put(&lockpick,40);}
        banks[Container::SkillBooks]->Put(&book,1);banks[Container::Recipes]->Put(&note,1);banks[Container::Scroll]->Put(&note,1);
        banks[Container::HealthPotions]->Put(&potion,1);banks[Container::Instruments]->Put(&instrument,1);
        const auto input=RE::input;const auto blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        if(entry==0){
            stores->ShowVaultMenu(&chest);
            auto selected=std::ranges::find_if(stores->options,[](auto& option){return option.text=="Vault.ArcaneOffload";});assert(selected!=stores->options.end());
            auto action=selected->action;stores->options.clear();ui->messageBox=false;action();
        }else if(entry==1)assert(utility->RunContainerAction(&assignment,&chest));
        else stores->OffloadItems();
        int elapsed=0,blockedMs=0;
        while((PlayerEquipment::pending || !timers.empty() || !tasks->ui.empty() || !tasks->queue.empty() || !queue->commands.empty()) && elapsed<12000){
            elapsed+=16;ProbeClock::tick+=std::chrono::milliseconds(16);
            queue->ProcessCommands();
            const bool delayedGamePoll=shape==1 && stalled && elapsed<5000;
            auto ready=std::move(timers);timers.clear();
            if(delayedGamePoll)timers=std::move(ready);else for(auto& timer:ready)timer();
            tasks->RunUI();if(!delayedGamePoll)tasks->Run();
            if(RE::input!=input || RE::PlayerControls::GetSingleton()->blockPlayerInput!=blocked)blockedMs+=16;
        }
        assert(!PlayerEquipment::pending && !ui->menu && RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);
        assert(banks[Container::Armor]->rows[&ring].total==(shape==2?2:0));
        assert(player->rows[&ring].total==(shape==1 || shape==2?1:0));
        if(shape==1 || shape==2)assert(player->rows[&ring].extras.front()->metadata=="worn");
        assert(banks[Container::SkillBooks]->rows[&book].total==0 && banks[Container::Book]->rows[&book].total==(shape==3?3:1));
        assert(banks[Container::Recipes]->rows[&note].total==0 && banks[Container::Scroll]->rows[&note].total==0 && banks[Container::Notes]->rows[&note].total==(shape==3?4:2));
        assert(banks[Container::HealthPotions]->rows[&potion].total==0 && banks[Container::Concoction]->rows[&potion].total==1);
        assert(banks[Container::Instruments]->rows[&instrument].total==0 && banks[Container::Gear]->rows[&instrument].total==1);
        assert(player->rows[&lockpick].total==(shape==3?25:0) && banks[Container::Gear]->rows[&lockpick].total==(shape==3?15:0));
        assert((entry==0)==!stores->options.empty());
        std::cout<<"{\"entry\":"<<entry<<",\"shape\":"<<shape<<",\"stalled\":"<<(stalled?"true":"false")<<",\"simulated_ms\":"<<elapsed<<",\"inspection_blocked_ms\":"<<blockedMs<<",\"prompt\":"<<(elapsed<1100?"true":"false")<<"}\n";
    }
}
'''
with tempfile.TemporaryDirectory(prefix="av-transfer-pipeline-") as directory:
    path=Path(directory);(path/"common.hpp").write_text("#pragma once\n"+common);(path/"check.cpp").write_text(program)
    flags=["-fsanitize=address,undefined","-fno-omit-frame-pointer"] if args.sanitize else []
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror",*flags,"-I",str(ROOT),str(path/"check.cpp"),"-o",str(path/"check")],check=True,timeout=90)
    cases=[json.loads(line) for line in subprocess.check_output([str(path/"check")],text=True,timeout=30).splitlines()]
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps({"source_ref":args.source_ref,"source_sha256":{name:hashlib.sha256(source(name).encode()).hexdigest() for name in ("Stores","PlayerEquipment","InventoryStacks")},"boundary":"Production inspector, OffloadItemsNow, Book/Note/potion/instrument consolidation, physical animation polling, Arcane Vault callback and assignment dispatch. Engine, classification and message-box presentation are stubs. Hotkey starts at its OffloadItems handoff, without keyboard matching. Soul gem logic has separate regression coverage. Worn-only/stalled cases withhold game polling while native UI messages continue; blocked milliseconds measure simulated input masks and block state, rather than global queue-drain time. Times are simulated.","entries":["Arcane Vault","assigned Quick Transfer","hotkey handoff"],"shapes":["empty","worn only","worn and spares","mixed reserves and notes"],"cases":cases},indent=2)+"\n")
failures=sum(not case["prompt"] for case in cases)
print(f"Pipeline checks: {len(cases)} inventory/input invariants pass; {failures} slow returns; report {args.output}")
raise SystemExit(1 if failures else 0)
