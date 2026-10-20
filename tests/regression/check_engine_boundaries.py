"""Check native inventory, dispatch, and furniture boundaries with production code."""
import argparse
import json
import hashlib
from pathlib import Path
import subprocess
import tempfile
from support import engine as harness

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source-ref")
parser.add_argument("--sanitize",action="store_true")
parser.add_argument("--probe-output",type=Path,help="Report physical inventory access inside Quick Transfer UI callbacks")
args=parser.parse_args()
if args.probe_output and args.probe_output.exists():parser.error("Choose a new report path")
ROOT=harness.ROOT

def source(name):
    if args.source_ref:
        return subprocess.check_output(["git","show",f"{args.source_ref}:src/{name}.cpp"],cwd=ROOT,text=True)
    return (ROOT/f"src/{name}.cpp").read_text()

common="#include <utility>\n#include <iostream>\n"+harness.common
common=common.replace("inline bool inspectionOpen=false;", "inline bool inUITask=false;inline int uiInventoryReads=0;inline bool inspectionOpen=false;")
common=common.replace("std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;", "if(inUITask){++uiInventoryReads;}std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;")
common=common.replace("ui.pop_front();task();", "ui.pop_front();RE::inUITask=true;task();RE::inUITask=false;")
common=common.replace("enum class BSEventNotifyControl { kContinue };", "enum class BSEventNotifyControl { kContinue,kStop };")
common=common.replace("unsigned oldContainer,newContainer,baseObj;int itemCount;", "unsigned oldContainer,newContainer,baseObj;int itemCount;unsigned reference=0;unsigned short uniqueID=0;")
common=common.replace("void Send(TESContainerChangedEvent e){for(auto* sink:sinks)sink->ProcessEvent(&e,nullptr);}", "void Send(TESContainerChangedEvent e){auto copy=sinks;for(auto* sink:copy)if(sink->ProcessEvent(&e,nullptr)==BSEventNotifyControl::kStop)break;}")
common=common.replace("e->countDelta=row.total;", "e->countDelta=row.total-(row.leveled?0:row.baseStock);")
common=common.replace("bool bulkRefuse=false,lastKeepOwnership=false;", "bool bulkRefuse=false,lastKeepOwnership=false;bool queueBulk=false;inline static std::deque<std::function<void()>> nativeTasks;")
common=common.replace("if(bulkRefuse)return;", "if(bulkRefuse)return;if(queueBulk){queueBulk=false;nativeTasks.emplace_back([=,this]{RemoveAllItems(owner,target,stealing,keepOwnership,false);});return;}")
common=common.replace("struct Settings {", "struct Settings {bool GSC_AllCraftingMaterials=false;bool GSC_CraftingLoan=true;")
common=common.replace("struct Utility {", "struct Utility {BenchType bench=BenchType::Enchanting;BenchType GetBenchType(RE::TESObjectREFR*)const{return bench;}")
common=common.replace("struct Stores {", "struct Stores {int materialReturns=0;void BeginJunkLoan(){}void EndJunkLoan(){++materialReturns;}void ResetJunkLoan(){}void AllToPlayer(Container){}void StoreToPlayer(ItemCategory,Container){}")
common=common.replace("bool savedBlocked=false;", "int capacity=100;bool rejectQueueHide=false;bool savedBlocked=false;")
common=common.replace("assert(name==InventoryMenu::MENU_NAME);commands.push_back(type);", "assert(name==InventoryMenu::MENU_NAME);if((type==UI_MESSAGE_TYPE::kHide && rejectQueueHide) || commands.size()>=static_cast<std::size_t>(capacity)){delete static_cast<InventoryUpdateData*>(data);return;}commands.push_back(type);")
common += r'''
namespace Soulgems {inline void BeginLoan(bool, bool = false){}inline void EndLoan(){}inline void ResetLoan(){}}
'''
common=common.replace("namespace logger { inline void error(const char*) {} }", "namespace logger { inline void error(const char*) {} inline void info(const char*) {} }")
common=common.replace("struct ScriptEventSourceHolder {", "struct MenuOpenCloseEvent {std::string menuName;bool opening;};struct CraftingMenu {inline static constexpr std::string_view MENU_NAME=\"CraftingMenu\";};struct ScriptEventSourceHolder {std::vector<BSTEventSink<TESFurnitureEvent>*> furniture;template<class Event>void AddEventSink(BSTEventSink<Event>* sink){if constexpr(std::is_same_v<Event,TESFurnitureEvent>)furniture.push_back(sink);else sinks.push_back(sink);}")
common=common.replace("struct UI {", "struct UI {template<class Event>void AddEventSink(BSTEventSink<Event>*){}")
events=source("Events")
loan=events[events.index("class CraftingLoanState {"):events.index("class FurnitureActivation {")]
handler=events[events.index("class CraftingMenuEventHandler"):events.index("class InputHandler")]
# Furniture exit handling lives in the session to keep target/generation checks shared.
if "void FurnitureEvent(" not in loan:
    loan=loan.replace("public:", "public:\n    void FurnitureEvent(const RE::TESFurnitureEvent&) {}",1)
equipment=source("PlayerEquipment").replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;")
start=equipment.index("        void Later(");end=equipment.index("\n        void Close(",start)
equipment=equipment[:start]+"        void Later(const std::shared_ptr<Request>&) {}\n"+equipment[end:]
equipment="\n".join(line for line in equipment.splitlines() if not line.startswith("#include"))
clock="struct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};\n"
stores=source("Stores");start=stores.index("void Stores::PlayerToStore(")
transfer=stores[start:stores.index("\n}\n",start)+3]
program='#include "common.hpp"\n'+clock+equipment+transfer+loan+handler+r'''
struct OtherSink:RE::BSTEventSink<RE::TESContainerChangedEvent>{
    std::function<RE::BSEventNotifyControl(const RE::TESContainerChangedEvent&)> callback;
    RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent* e,RE::BSTEventSource<RE::TESContainerChangedEvent>*)override{return callback(*e);}
};
int main(){
    auto* player=RE::PlayerCharacter::GetSingleton();auto* u=Utility::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    auto* events=RE::ScriptEventSourceHolder::GetSingleton();auto* session=CraftingLoanState::GetSingleton();
    RE::TESObjectREFR weapons{1001},armor{1002},archive{1003},bench{1004},otherBench{1005},otherActor{1006};
    u->containers[Container::Weapon]=&weapons;u->containers[Container::Armor]=&armor;u->containers[Container::EnchantedItems]=&archive;
    
    EnchantedItems::Init();CraftingMenuEventHandler::Register();auto registered=events->sinks;
    auto furniture=[&](const RE::TESFurnitureEvent& event){for(auto* sink:events->furniture)sink->ProcessEvent(&event,nullptr);};
    RE::TESBoundObject ring{200,false,true};RE::EnchantmentItem fire,frost;
    auto count=[&](auto& ref){return InventoryStacks::Count(&ref,&ring);};
    auto reset=[&]{session->Reset();tasks->Run();events->sinks=registered;
        for(auto* ref:{static_cast<RE::TESObjectREFR*>(player),&weapons,&armor,&archive}){
            ref->rows.clear();ref->refuse=false;ref->initialized=false;ref->initializations=0;ref->onInit={};
            ref->changes.queueBulk=false;ref->changes.nativeTasks.clear();
        }};
    auto seed=[&]{for(auto* enchantment:{&fire,&frost}){
        weapons.Put(&ring,0,1,nullptr,"borrowed");weapons.rows[&ring].extras.back()->enchantment=RE::ExtraEnchantment{enchantment};
    }player->Put(&ring,0,1,nullptr,"carried");};
    for(int stock:{0,1,3,4})for(bool leveled:{false,true}){
        reset();weapons.Put(&ring,3);auto& row=weapons.rows[&ring];row.baseStock=stock;row.leveled=leveled;
        const auto inventory=weapons.GetInventory();assert(inventory.at(&ring).first==3);
        assert(inventory.at(&ring).second->countDelta==3-(leveled?0:stock));
        assert(InventoryStacks::Read(&weapons).front().count==3 && weapons.initializations==1);
        assert(InventoryStacks::Move(InventoryStacks::Read(&weapons).front(),&armor)==3 && count(armor)==3);
    }
    for(int stock:{0,4})for(int total:{0,3})for(bool leveled:{false,true}){
        reset();weapons.Put(&ring,total);weapons.rows[&ring].baseStock=stock;weapons.rows[&ring].leveled=leveled;
        assert(InventoryStacks::HasItems(&weapons)==(total>0));
        assert(weapons.initializations==0);
    }
    reset();seed();
    RE::TESBoundObject paper{202};player->Put(&paper,1000);
    const auto physicalEquipment=PlayerEquipment::Capture(player);
    assert(!physicalEquipment.contains(&paper) && physicalEquipment.contains(&ring));
    const auto copiesBeforeEmptyWork=RE::TESObjectREFR::inventoryCopies;
    auto emptyRequest=std::make_shared<PlayerEquipment::Request>();bool emptyWorked=false;
    emptyRequest->work=[&]{emptyWorked=true;};PlayerEquipment::Work(emptyRequest,{});
    assert(emptyWorked && RE::TESObjectREFR::inventoryCopies==copiesBeforeEmptyWork);
    reset();weapons.onInit=[&]{weapons.Put(&ring,2);};assert(count(weapons)==2 && count(weapons)==2 && weapons.initializations==1);

    auto* stores=Stores::GetSingleton();
    reset();seed();session->EnterCrafting(&bench);const int returns=stores->materialReturns;
    RE::TESFurnitureEvent unrelated{{&otherActor},{&bench},RE::TESFurnitureEvent::FurnitureEventType::kExit};
    RE::TESFurnitureEvent stale{{player},{&otherBench},RE::TESFurnitureEvent::FurnitureEventType::kExit};
    RE::TESFurnitureEvent exit{{player},{&bench},RE::TESFurnitureEvent::FurnitureEventType::kExit};
    furniture(unrelated);furniture(stale);tasks->Run();assert(stores->materialReturns==returns);
    furniture(exit);furniture(exit);tasks->Run();assert(stores->materialReturns==returns+1);
    reset();session->EnterCrafting(&bench);furniture(exit);session->EnterCrafting(&otherBench);
    const int nextReturns=stores->materialReturns;tasks->Run();assert(stores->materialReturns==nextReturns);
    RE::TESFurnitureEvent newExit{{player},{&otherBench},RE::TESFurnitureEvent::FurnitureEventType::kExit};
    furniture(newExit);tasks->Run();assert(stores->materialReturns==nextReturns+1);
    auto* ui=RE::UI::GetSingleton();auto* queue=RE::UIMessageQueue::GetSingleton();
    for(int congested=0;congested<3;++congested)for(int capacity:{1,64,100}){
        reset();player->Put(&ring,0,3);ProbeClock::tick={};queue->capacity=capacity;queue->rejectQueueHide=congested==2;
        RE::InventoryMenu::empty=RE::InventoryMenu::uninitialized=congested==1;
        const auto input=RE::input;bool done=false;int worked=0;
        if(congested==0)queue->capacity=0;
        PlayerEquipment::Run([&]{assert(!ui->menu);++worked;},[&]{done=true;});
        for(int step=0;!done && step<160;++step){
            if(PlayerEquipment::pending && PlayerEquipment::pending->phase==PlayerEquipment::Phase::Closing && !PlayerEquipment::pending->worked && congested==2)queue->capacity=0;
            queue->ProcessCommands();
            if(congested==1 && ui->menu)queue->capacity=PlayerEquipment::pending->phase==PlayerEquipment::Phase::Closing?capacity:0;
            if(auto request=PlayerEquipment::pending)PlayerEquipment::Poll(request);
            tasks->RunUI();tasks->Run();
            if(congested==2 && ui->menu && PlayerEquipment::pending && PlayerEquipment::pending->worked && ui->menu->uiMovie->visible){
                assert(worked==0);queue->capacity=capacity;queue->rejectQueueHide=false;queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);
            }
            ProbeClock::tick+=std::chrono::milliseconds(16);
        }
        queue->capacity=capacity;queue->ProcessCommands();
        if(auto request=PlayerEquipment::pending)PlayerEquipment::Poll(request);
        if(!(done && !ui->menu && RE::input==input && worked==(congested==2?0:1)))std::cerr<<"queue case="<<congested<<" capacity="<<capacity<<" done="<<done<<" worked="<<worked<<" menu="<<(ui->menu!=nullptr)<<"\n";
        assert(done && !ui->menu && RE::input==input && worked==(congested==2?0:1));
        assert(ProbeClock::tick.time_since_epoch()<std::chrono::milliseconds(2100));
        assert(count(*player)==3);
    }
    RE::InventoryMenu::empty=RE::InventoryMenu::uninitialized=false;queue->capacity=100;
    for(int protection=0;protection<5;++protection){
        reset();player->Put(&ring,0,1);RE::SCRIPT_FUNCTION::equipped.clear();Settings::GetSingleton()->ignored.clear();
        if(protection==0)player->rows[&ring].extras.front()->worn=true;
        if(protection==1)RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        if(protection==2)player->rows[&ring].quest=true;
        if(protection==3)player->rows[&ring].favorite=true;
        if(protection==4)Settings::GetSingleton()->ignored.insert(&ring);
        bool done=false;const auto shows=queue->shows;
        PlayerEquipment::Run([&]{Stores::GetSingleton()->PlayerToStore(ItemCategory::Jewelry,Container::Armor,0,0,true);},[&]{done=true;});
        assert(done && !ui->menu && queue->shows==shows && count(*player)==1 && count(armor)==0);
    }
    Settings::GetSingleton()->ignored.clear();RE::SCRIPT_FUNCTION::equipped.clear();
    for(bool unavailable:{false,true}){
        reset();player->Put(&ring,0,1);player->rows[&ring].extras.front()->uiWorn=true;ProbeClock::tick={};
        RE::SCRIPT_FUNCTION::available=!unavailable;RE::SCRIPT_FUNCTION::succeeds=unavailable;
        bool done=false;const auto shows=queue->shows;const auto input=RE::input;
        PlayerEquipment::Run([&]{Stores::GetSingleton()->PlayerToStore(ItemCategory::Jewelry,Container::Armor);},[&]{done=true;});
        assert(!done);
        for(int step=0;!done && step<80;++step){queue->ProcessCommands();if(auto request=PlayerEquipment::pending)PlayerEquipment::Poll(request);tasks->RunUI();tasks->Run();ProbeClock::tick+=std::chrono::milliseconds(16);}
        assert(done && !ui->menu && queue->shows==shows+1 && count(*player)==1 && count(armor)==0 && RE::input==input);
        RE::SCRIPT_FUNCTION::available=RE::SCRIPT_FUNCTION::succeeds=true;
    }
    for(bool bare:{false,true}) {
        reset();player->Put(&ring,0,1,nullptr,"worn before UI");player->rows[&ring].extras.front()->uiWorn=true;
        RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        if(bare)player->Put(&ring,2);else player->Put(&ring,0,2,nullptr,"retired spare");
        bool done=false;PlayerEquipment::Run([&]{Stores::GetSingleton()->PlayerToStore(ItemCategory::Jewelry,Container::Armor);},[&]{done=true;});
        auto replacement=std::make_shared<RE::ExtraDataList>();replacement->count=2;replacement->metadata="replacement spare";
        auto& extras=player->rows[&ring].extras;if(!bare)extras.pop_back();extras.push_back(replacement);
        for(int step=0;!done && step<80;++step){queue->ProcessCommands();if(auto request=PlayerEquipment::pending)PlayerEquipment::Poll(request);tasks->RunUI();tasks->Run();ProbeClock::tick+=std::chrono::milliseconds(16);}
        assert(done && count(*player)==3 && count(armor)==0 && player->rows[&ring].extras.back()->metadata=="replacement spare");
    }
    reset();player->Put(&ring,3);queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kShow,nullptr);queue->ProcessCommands();
    auto* borrowed=ui->menu;const auto borrowedInput=RE::input;bool done=false;
    PlayerEquipment::Run([]{},[&]{done=true;});assert(done && ui->menu==borrowed && RE::input==borrowedInput);
    player->rows.clear();player->Put(&ring,1);done=false;
    PlayerEquipment::Run([&]{Stores::GetSingleton()->PlayerToStore(ItemCategory::Jewelry,Container::Armor);},[&]{done=true;});
    assert(done && count(*player)==1 && ui->menu==borrowed && RE::input==borrowedInput);
    queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);queue->ProcessCommands();
}
'''
if args.probe_output:
    insertion = r'''
    reset();seed();RE::uiInventoryReads=0;ProbeClock::tick={};bool inspected=false;
    PlayerEquipment::Run([]{},[&]{inspected=true;});
    for(int step=0;!inspected && step<160;++step){
        RE::UIMessageQueue::GetSingleton()->ProcessCommands();
        if(auto request=PlayerEquipment::pending)PlayerEquipment::Poll(request);
        tasks->RunUI();tasks->Run();ProbeClock::tick+=std::chrono::milliseconds(16);
    }
    assert(inspected && !RE::UI::GetSingleton()->menu && count(*player)==1);
    std::cout<<"{\"case\":\"inspection_context\",\"ui_inventory_reads\":"<<RE::uiInventoryReads<<"}\n";
'''
    needle="    for(int stock:{0,1,3,4})"
    assert needle in program
    program=program.replace(needle,insertion+needle)
with tempfile.TemporaryDirectory(prefix="av-engine-boundaries-") as directory:
    root=Path(directory);(root/"common.hpp").write_text("#pragma once\n"+common);(root/"check.cpp").write_text(program)
    modules=[]
    for name in ("InventoryStacks","EnchantedItems"):
        path=root/f"{name}.cpp";path.write_text('#include "common.hpp"\n'+"\n".join(line for line in source(name).splitlines() if not line.startswith("#include")));modules.append(str(path))
    flags=["-fsanitize=address,undefined","-fno-omit-frame-pointer"] if args.sanitize else []
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror",*flags,"-I",str(ROOT),str(root/"check.cpp"),*modules,"-o",str(root/"check")],check=True,timeout=90)
    output=subprocess.check_output([str(root/"check")],text=True,timeout=20)
if args.probe_output:
    cases=[json.loads(line) for line in output.splitlines()]
    assert len(cases)==1
    failures=sum(case["ui_inventory_reads"]>0 for case in cases)
    args.probe_output.parent.mkdir(parents=True,exist_ok=True)
    args.probe_output.write_text(json.dumps({"boundary":"Production Quick Transfer equipment inspector with modeled UI task context. Inventory access inside a UI callback is reported; native lock behaviour and the in-game freeze are not reproduced.","source_sha256":{name:hashlib.sha256(source(name).encode()).hexdigest() for name in ("InventoryStacks","PlayerEquipment")},"cases":cases,"hazards":failures},indent=2)+"\n")
    print(f"Boundary probe: {failures} hazards; existing inventory/input invariants passed; report {args.probe_output}")
    raise SystemExit(1 if failures else 0)
print("PASS: base stock/deltas, cold initialization, event identities, stopped/reentrant sinks, material-loan furniture exits")
