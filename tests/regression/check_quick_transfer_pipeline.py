"""Exercise inspection, full Quick Transfer, consolidation and return as one interaction."""
import argparse
import json
import hashlib
import os
import signal
import statistics
from pathlib import Path
import subprocess
import tempfile

from support import engine as harness
from support import transfer_render_probe as rendering

ROOT=harness.ROOT
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--sanitize",action="store_true")
parser.add_argument("--source-ref")
parser.add_argument("--feedback",action="store_true",help="Run the actual overlay barrier and completion with the full transfer pipeline")
parser.add_argument("--startup-only",action="store_true",help="Run startup readiness, protection work and populated-archive regressions")
parser.add_argument("--frame-startup",action="store_true",help="Require rendered-frame opportunities across preparation, inspection and queued actions")
parser.add_argument("--render-probe",action="store_true",help="Measure rendering gaps with declared native-call costs; fail if distributed work blocks frames")
parser.add_argument("--cost-models",nargs="+",choices=rendering.MODELS,default=rendering.MODELS)
parser.add_argument("--profile",action="store_true",help="Profile fixture phases and two test-only candidates against unchanged production")
parser.add_argument("--samples",type=int,default=5)
parser.add_argument("--sizes",type=int,nargs="+",default=[0,1000])
parser.add_argument("--scenarios",type=Path,help="Run representative JSON sorting inventories through every entry path")
args=parser.parse_args()
if args.frame_startup:
    if args.startup_only or args.scenarios or args.profile or args.render_probe:parser.error("Frame startup checks run separately")
    args.feedback=True
if args.startup_only:
    if args.scenarios or args.profile or args.render_probe:parser.error("Startup checks are separate from scenario and performance probes")
    args.feedback=True
if args.scenarios:
    if args.profile or args.render_probe:parser.error("JSON scenarios are separate from profiling probes")
    args.feedback=True
if args.render_probe:
    if args.profile:parser.error("Render probes and CPU candidate profiles are separate experiments")
    args.feedback=True
if args.output.exists():parser.error("Choose a new output path")
tracked_sources=("Stores","PlayerEquipment","InventoryStacks","Soulgems")+(("TransferFeedback",) if args.feedback else ())
if args.profile and args.sanitize:parser.error("Profile runs exclude sanitizers")
if (args.profile or args.render_probe) and (args.samples<2 or args.samples>10 or any(size<0 or size>1000 for size in args.sizes)):
    parser.error("Use 2 to 10 samples and sizes between zero and 1000")
def source(name):
    if not args.source_ref:return (ROOT/f"src/{name}.cpp").read_text()
    text=subprocess.check_output(["git","show",f"{args.source_ref}:src/{name}.cpp"],cwd=ROOT,text=True)
    header=subprocess.check_output(["git","show",f"{args.source_ref}:src/ItemClass.h"],cwd=ROOT,text=True)
    return harness.rename_enum_references(text,header)
stores=source("Stores")
common=harness.common.replace('#include "src/OffloadBatch.h"', '')
if "TransferFeedback::Mark(" in stores and not args.feedback:
    common+="namespace TransferFeedback {enum class Stage {Recovery,Transfer,Soulgems};inline void Mark(Stage){}}\n"
if args.feedback:
    from support import feedback
    stub="namespace TransferFeedback {\ninline void Begin(std::function<void(Complete)> start){start([]{return true;});}\ninline void Reset(){}\n}"
    assert stub in common
    common=common.replace(stub, "")
    wait_stub=common.index('namespace TransferFeedback {\ninline void WaitForFrame(')
    wait_end=common.index('\n}',wait_stub)+2
    wait_end=common.index('\n}',wait_end)+2
    common=common[:wait_stub]+common[wait_end:]
    common=common.replace("inline const char* Translate(const char* text){return text;}", "inline const char* Translate(const char* text){return std::string_view{text}==\"Vault.Sorting\"?\"Sorting items...\":text;}")
    common+='namespace RE {struct InputEvent {bool up=false;bool IsUp()const{return up;}InputEvent* AsButtonEvent(){return this;}};}\n'
    framework=feedback.FRAMEWORK[:feedback.FRAMEWORK.index("namespace AVTranslation")]

common=common.replace("inline bool inspectionOpen=false;", "inline int inventoryReads=0,bulkCalls=0,emptyBulkCalls=0,removeCalls=0;inline bool inspectionOpen=false;")
common=common.replace("struct TESObjectREFR {", r'''
namespace Profile {
#ifdef AV_PROFILE
inline constexpr bool enabled=true;
#else
inline constexpr bool enabled=false;
#endif
inline int candidate=0;
struct Phase {double inclusiveMs=0,selfMs=0;int calls=0;};
inline std::map<std::string,Phase> phases;
struct Scope {
    inline static thread_local Scope* current=nullptr;
    const char* name;Scope* parent{};double childrenMs=0;
    std::chrono::steady_clock::time_point start{};
    explicit Scope(const char* value):name(value){if(enabled){parent=current;current=this;start=std::chrono::steady_clock::now();}}
    ~Scope(){if(enabled){
        const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        auto& phase=phases[name];phase.inclusiveMs+=ms;phase.selfMs+=ms-childrenMs;++phase.calls;
        if(parent){parent->childrenMs+=ms;}current=parent;
    }}
};
}
struct TESObjectREFR {''')
common=common.replace("std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;", "++inventoryReads;std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;")
common=common.replace("assert(owner==source && !stealing);++bulkTransfers;", "assert(owner==source && !stealing);++bulkCalls;if(!std::ranges::any_of(source->rows,[](auto& row){return row.second.total>0;})){++emptyBulkCalls;}++bulkTransfers;")
common=common.replace("assert(!inspectionOpen);if(refuse)return;", "assert(!inspectionOpen);++removeCalls;if(refuse)return;")
common=common.replace("++inventoryReads;std::map", 'Profile::Scope phase{"inventory API stub"};++inventoryReads;std::map')
common=common.replace("assert(owner==source && !stealing);++bulkCalls;", 'Profile::Scope phase{"bulk API stub"};assert(owner==source && !stealing);++bulkCalls;')
common=common.replace("struct TESSoulGem {};", "enum class SOUL_LEVEL {kNone,kPetty,kLesser,kCommon,kGreater,kGrand};struct TESSoulGem;")
common=common.replace("    unsigned id;\n    bool weapon", "    TESBoundObject(unsigned value,bool w=false,bool a=false):id(value),weapon(w),armor(a){}\n    virtual ~TESBoundObject()=default;\n    unsigned id;\n    bool weapon")
common=common.replace("        else return nullptr;", "        else if constexpr(std::is_same_v<T,TESSoulGem>) return dynamic_cast<T*>(this);else return nullptr;")
common=common.replace("struct ExtraEnchantment {", "struct TESSoulGem:TESBoundObject {using TESBoundObject::TESBoundObject;SOUL_LEVEL soul=SOUL_LEVEL::kNone;TESSoulGem* linkedSoulGem=nullptr;SOUL_LEVEL GetContainedSoul()const{return soul;}};struct ExtraSoul {SOUL_LEVEL soul;SOUL_LEVEL GetContainedSoul()const{return soul;}};\nstruct ExtraEnchantment {")
common=common.replace("bool worn=false,leftWorn", "std::optional<ExtraSoul> soul{};bool worn=false,leftWorn")
common=common.replace("if constexpr(std::is_same_v<T,ExtraEnchantment>)", "if constexpr(std::is_same_v<T,ExtraSoul>)return soul?&*soul:nullptr;else if constexpr(std::is_same_v<T,ExtraEnchantment>)")
common=common.replace("if(worn!=other.worn", "if((soul?soul->soul:SOUL_LEVEL::kNone)!=(other.soul?other.soul->soul:SOUL_LEVEL::kNone))return false;\n        if(worn!=other.worn")
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
common=common.replace("void OffloadItemsNow(std::function<void()> complete={}){PlayerEquipment::Run([this]{PlayerToStore(ItemCategory::Jewelry,Container::Armor);},std::move(complete));}", ("void OffloadItemsNow(std::function<void()> complete = {});" if "OffloadItemsNow(std::function<void()>" in stores else "void OffloadItemsNow();"))
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
inline std::deque<std::function<void()>> timers;
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
namespace TransferFeedback {void Run(std::function<bool(const std::function<bool()>&)>,std::function<void()>);}
namespace Soulgems {void Recover(const std::unordered_set<RE::FormID>& = {});void Deposit(int,bool);}
inline void DumpProfile(double ms){
    if(!RE::Profile::enabled)return;
    std::cout<<",\"fixture_cpu_ms\":"<<ms<<",\"phases\":{";bool first=true;
    for(auto& [name,phase]:RE::Profile::phases){
        if(!first){std::cout<<",";}first=false;
        std::cout<<"\""<<name<<"\":{\"inclusive_ms\":"<<phase.inclusiveMs<<",\"self_ms\":"<<phase.selfMs<<",\"calls\":"<<phase.calls<<"}";
    }
    std::cout<<"}";
}
'''

startup_checks=args.feedback and not (args.scenarios or args.profile or args.render_probe or args.frame_startup)
if startup_checks:
    common=common.replace('namespace RE { struct TESBoundObject; }', '''namespace StartupProbe {
inline int equippedQueries=0,explicitUpdates=0,confirmations=0;
inline bool failQueue=false;
inline std::function<void()> afterShow,beforeUpdate;
}
namespace RE { struct TESBoundObject; }''')
    needle='static bool Query(TESObjectREFR*,void* item,void*,double& value){'
    assert common.count(needle)==1
    common=common.replace(needle,needle+'++StartupProbe::equippedQueries;')
    needle='                inventory->ProcessMessage(message);'
    assert common.count(needle)==1
    common=common.replace(needle,needle+'if(StartupProbe::afterShow)StartupProbe::afterShow();')
    needle='assert(payload && !payload->updateObj);++ItemList::refreshes;'
    assert common.count(needle)==1
    common=common.replace(needle,needle+'++StartupProbe::explicitUpdates;if(StartupProbe::beforeUpdate)StartupProbe::beforeUpdate();')
    needle='message=text;'
    assert common.count(needle)==1
    common=common.replace(needle,needle+'++StartupProbe::confirmations;')

def body(text,signature,ending="\n}\n"):
    start=text.index(signature)
    return text[start:text.index(ending,start)+len(ending)]

def profiled(text,signature,label):
    first=text.index(signature);brace=text.index("{",first)
    return text[:brace+1]+f'RE::Profile::Scope phase{{"{label}"}};'+text[brace+1:]

program='#include "common.hpp"\n#include "OffloadBatch.h"\n'+("#define __stdcall\n"+framework if args.feedback else "")
item_source=(ROOT/"src/ItemClass.cpp").read_text()
program+=item_source[item_source.index("CategoryMask operator|("):item_source.index("bool HasCategory(")]
for name in ("InventoryStacks","PlayerEquipment"):
    text=source(name)
    if name=="PlayerEquipment":
        text=text.replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;")
        start=text.index("        void Later(")
        end=text.index("\n        void Close(",start)
        later = 'TransferFeedback::WaitForFrame([request]{Poll(request);},[request]{if(Active(request))Reset();});' if args.feedback and '        void CaptureStep(' in text else 'timers.emplace_back([request]{Poll(request);});'
        text=text[:start]+"        void Later(const std::shared_ptr<Request>& request){"+later+"}\n"+text[end:]
        text=profiled(text,"        Snapshot Read(","equipment UI read")
        text=profiled(text,"        void Work(","equipment validation and work")
        text=profiled(text,"    void Run(","equipment preflight")
        needle="            for (const auto& stack : InventoryStacks::Read(player)) fresh[stack.item].push_back(stack);"
        if needle in text:text=text.replace(needle,"            if(RE::Profile::candidate!=2 || !snapshot.empty())\n"+needle)
    program+="\n".join(line for line in text.splitlines() if not line.startswith("#include"))+"\n"
if not args.feedback:
    program+='namespace TransferFeedback {void Run(std::function<bool(const std::function<bool()>&)> step,std::function<void()> complete){while(!step([]{return true;})){}if(complete)complete();}}\n'
program+=body(stores,"    int MoveItems(","\n    }")
program+=body(stores,"    std::unordered_set<RE::FormID> SelectedAmmunition(","\n    }")
animation=stores[stores.index("    using OpenState ="):stores.index("\n}\n\nusing AVTranslation")]
animation=animation.replace("std::chrono::steady_clock","ProbeClock").replace("std::thread(","TestThread(").replace("std::this_thread::sleep_for(std::chrono::milliseconds(16));","")
program+=animation
for name in ("PlayerToStore","StoreToStore","AllToStore","ConsolidateBooks","ConsolidatePotions","KeepAmmunition","OffloadItemsNow","OffloadItems","OpenStoreObject","VaultMenu","ShowVaultMenu"):
    fragment=body(stores,"void Stores::"+name+"(")
    if name=="AllToStore":
        needle="    auto* inventory = source->GetInventoryChanges();"
        assert needle in fragment
        fragment=fragment.replace(needle,"    if(RE::Profile::candidate==1 && !InventoryStacks::HasItems(source))return;\n"+needle)
    program+=profiled(fragment,"void Stores::"+name+"(",name)
program+=body((ROOT/"src/Utility.cpp").read_text(),"bool Utility::RunContainerAction(")
if args.feedback:
    feedback_source=source("TransferFeedback").replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;").replace("std::thread(", "TestThread(").replace("std::this_thread::sleep_for(std::chrono::milliseconds(16));", "")
    if startup_checks:
        signature='    void Run(std::function<bool(const std::function<bool()>&)> step, std::function<void()> complete) {'
        assert feedback_source.count(signature)==1
        feedback_source=feedback_source.replace(signature,signature+'if(StartupProbe::failQueue)throw std::runtime_error("queue failure");')
    program+="\n".join(line for line in feedback_source.splitlines() if not line.startswith("#include"))
program+=r'''
int main(){
    auto* player=RE::PlayerCharacter::GetSingleton();auto* utility=Utility::GetSingleton();auto* stores=Stores::GetSingleton();
    auto* tasks=SKSE::GetTaskInterface();auto* ui=RE::UI::GetSingleton();auto* queue=RE::UIMessageQueue::GetSingleton();
    std::map<Container,std::unique_ptr<RE::TESObjectREFR>> banks;
    for(auto kind:{Container::Armor,Container::Weapon,Container::Book,Container::Notes,Container::Scroll,Container::SpellTomes,Container::SkillBooks,
        Container::Recipes,Container::Maps,Container::Concoction,Container::Potion,Container::Poison,Container::Restorative,
        Container::HealthPotions,Container::MagickaPotions,Container::StaminaPotions,Container::Gear,Container::Instruments,Container::Keys,Container::Soulgem,
        Container::EmptySoulgems,Container::FilledSoulgems,Container::Smithing,Container::Crafting,Container::Smelting,Container::Construction,Container::Tanning,Container::Gemstone,Container::Sort}){
        banks[kind]=std::make_unique<RE::TESObjectREFR>(9000+static_cast<unsigned>(kind));utility->containers[kind]=banks[kind].get();
    }
    RE::TESObjectREFR chest{8000},assignment{8001};RE::TESBoundObject ring{200,false,true},note{201},book{202},potion{203},instrument{204},lockpick{205};
    RE::TESSoulGem gem{206};gem.categories=ToMask(ItemCategory::Soulgem);RE::TESBoundObject favorite{207,true},quest{208},ignored{209};
    favorite.categories=ToMask(ItemCategory::Weapon)|ToMask(ItemCategory::OneHand);quest.categories=ToMask(ItemCategory::Note);ignored.categories=ToMask(ItemCategory::Gear);
    ring.categories=ToMask(ItemCategory::Jewelry)|ToMask(ItemCategory::Armor);note.categories=ToMask(ItemCategory::Note);book.categories=ToMask(ItemCategory::Book);
    potion.categories=ToMask(ItemCategory::Potion);instrument.categories=ToMask(ItemCategory::Gear);lockpick.categories=ToMask(ItemCategory::Lockpick)|ToMask(ItemCategory::Gear);
    auto* settings=Settings::GetSingleton();settings->GSC_OffloadSoulgems=false;settings->GSC_OffloadJewelry=settings->GSC_OffloadNotes=settings->GSC_OffloadBooks=settings->GSC_OffloadGear=true;
    settings->GSC_LockpickKeepAmount=25;
    utility->containerMap[Container::QuickTransfer]={&assignment,[](RE::TESObjectREFR*){Stores::GetSingleton()->OffloadItems();}};
    for(int entry=0;entry<3;++entry)for(int shape=0;shape<7;++shape)for(bool stalled:{false,true})for(bool gems:{false,true})for(bool archived:{false,true}){
        settings->ignored.clear();player->rows.clear();for(auto& [kind,bank]:banks){(void)kind;bank->rows.clear();}
        RE::SCRIPT_FUNCTION::equipped.clear();timers.clear();ProbeClock::tick={};ui->messageBox=false;stores->options.clear();stores->ResetNavigation();
        chest.stalled=stalled;chest.state=stalled?3:2;
        settings->GSC_OffloadSoulgems=gems;settings->GSC_SoulgemKeepAmount=25;
        if(shape==1 || shape==2 || shape>=5){player->Put(&ring,0,1,nullptr,"worn");player->rows[&ring].extras.front()->uiWorn=true;RE::SCRIPT_FUNCTION::equipped.insert(&ring);}
        if(shape>=5){player->Put(&favorite,1);player->rows[&favorite].favorite=true;player->Put(&quest,2);player->rows[&quest].quest=true;player->Put(&ignored,4);settings->ignored.insert(&ignored);}
        if(shape==6)player->Put(&ring,1);
        if(shape==2)player->Put(&ring,0,2,nullptr,"spare");
        if(shape==3){player->Put(&note,2);player->Put(&book,2);player->Put(&lockpick,40);}
        if(shape==4){player->Put(&gem,40);player->Put(&gem,0,10,nullptr,"filled gem");player->rows[&gem].extras.back()->soul=RE::ExtraSoul{RE::SOUL_LEVEL::kGrand};}
        if(archived){banks[Container::SkillBooks]->Put(&book,1);banks[Container::Recipes]->Put(&note,1);banks[Container::Scroll]->Put(&note,1);
            banks[Container::HealthPotions]->Put(&potion,1);banks[Container::Instruments]->Put(&instrument,1);}
        const auto input=RE::input;const auto blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        const int showsBefore=queue->shows;
        RE::inventoryReads=RE::bulkCalls=RE::emptyBulkCalls=RE::removeCalls=0;
        RE::Profile::phases.clear();RE::TESObjectREFR::inventoryCopies=0;
        const auto fixtureStart=std::chrono::steady_clock::now();
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
            auto ready=std::move(timers);timers.clear();
            for(auto& timer:ready)timer();
            tasks->RunUI();tasks->Run();
            if(RE::input!=input || RE::PlayerControls::GetSingleton()->blockPlayerInput!=blocked)blockedMs+=16;
        }
        const auto fixtureMs=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-fixtureStart).count();
        assert(!PlayerEquipment::pending && !ui->menu && RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);
        assert(banks[Container::Armor]->rows[&ring].total==(shape==2?2:shape==6?1:0));
        assert(player->rows[&ring].total==(shape==1 || shape==2 || shape>=5?1:0));
        if(shape==1 || shape==2 || shape>=5)assert(player->rows[&ring].extras.front()->metadata=="worn");
        assert(banks[Container::SkillBooks]->rows[&book].total==0 && banks[Container::Book]->rows[&book].total==(shape==3?2:0)+archived);
        assert(banks[Container::Recipes]->rows[&note].total==0 && banks[Container::Scroll]->rows[&note].total==0 && banks[Container::Notes]->rows[&note].total==(shape==3?2:0)+2*archived);
        assert(banks[Container::HealthPotions]->rows[&potion].total==0 && banks[Container::Concoction]->rows[&potion].total==archived);
        assert(banks[Container::Instruments]->rows[&instrument].total==0 && banks[Container::Gear]->rows[&instrument].total==archived);
        assert(player->rows[&lockpick].total==(shape==3?25:0) && banks[Container::Gear]->rows[&lockpick].total==(shape==3?15:0));
        if(player->rows[&gem].total!=(shape==4?(gems?25:50):0))std::cerr<<"Gem mismatch entry="<<entry<<" shape="<<shape<<" enabled="<<gems<<" player="<<player->rows[&gem].total<<" bank="<<banks[Container::Soulgem]->rows[&gem].total<<'\n';
        assert(player->rows[&gem].total==(shape==4?(gems?25:50):0));
        assert(banks[Container::Soulgem]->rows[&gem].total==(shape==4 && gems?25:0));
        if(shape==4 && gems){assert(banks[Container::Soulgem]->rows[&gem].extras.front()->soul->soul==RE::SOUL_LEVEL::kGrand);assert(player->rows[&gem].extras.empty());}
        if(shape>=5)assert(player->rows[&favorite].total==1 && player->rows[&quest].total==2 && player->rows[&ignored].total==4);
        if(shape==5)assert(queue->shows==showsBefore);
        assert((entry==0)==!stores->options.empty());
        std::cout<<"{\"entry\":"<<entry<<",\"shape\":"<<shape<<",\"stalled\":"<<(stalled?"true":"false")<<",\"archives_populated\":"<<(archived?"true":"false")<<",\"soulgems_enabled\":"<<(gems?"true":"false")<<",\"inventory_reads\":"<<RE::inventoryReads<<",\"bulk_calls\":"<<RE::bulkCalls<<",\"empty_bulk_calls\":"<<RE::emptyBulkCalls<<",\"remove_calls\":"<<RE::removeCalls<<",\"simulated_ms\":"<<elapsed<<",\"inspection_blocked_ms\":"<<blockedMs<<",\"prompt\":"<<(elapsed<1100?"true":"false");DumpProfile(fixtureMs);std::cout<<"}\n";
    }
}
'''
if args.feedback:
    program=program.replace("    auto* player=", "    SKSEMenuFramework::installed=true;TransferFeedback::Register();\n    auto* player=",1)
    program=program.replace("        settings->ignored.clear();", "        TransferFeedback::Reset();\n        settings->ignored.clear();")
    program=program.replace("            elapsed+=16;", "            SKSEMenuFramework::render();\n            elapsed+=16;")
    program=program.replace("        assert(!PlayerEquipment::pending", "        RE::InputEvent inputEvent;assert(!SKSEMenuFramework::block(&inputEvent));\n        assert(!PlayerEquipment::pending")
    recovery=r'''
    TransferFeedback::Reset();player->rows.clear();settings->ignored.clear();
    for(auto& [kind,bank]:banks){(void)kind;bank->rows.clear();}
    player->Put(&ring,0,1,nullptr,"worn recovery");player->rows[&ring].extras.front()->uiWorn=true;player->Put(&ring,2);
    RE::SCRIPT_FUNCTION::equipped.insert(&ring);ProbeClock::tick={};ui->messageBox=false;timers.clear();
    const auto recoveryInput=RE::input;const auto recoveryBlocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
    queue->refuseHide=true;bool recoveryCompleted=false;stores->OffloadItems([&]{recoveryCompleted=true;});
    for(int frame=0;frame<100;++frame){
        SKSEMenuFramework::render();ProbeClock::tick+=std::chrono::milliseconds(16);queue->ProcessCommands();
        auto ready=std::move(timers);timers.clear();for(auto& action:ready){action();}tasks->RunUI();tasks->Run();
    }
    RE::InputEvent recoveryButton;
    assert(PlayerEquipment::pending && ui->menu && !recoveryCompleted && !SKSEMenuFramework::block(&recoveryButton));
    assert(player->rows[&ring].total==3 && banks[Container::Armor]->rows[&ring].total==0);
    stores->OffloadItems();assert(!SKSEMenuFramework::block(&recoveryButton));
    queue->refuseHide=false;queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);
    for(int frame=0;PlayerEquipment::pending && frame<80;++frame){
        ProbeClock::tick+=std::chrono::milliseconds(16);queue->ProcessCommands();auto ready=std::move(timers);timers.clear();
        for(auto& action:ready){action();}tasks->RunUI();tasks->Run();
    }
    assert(!PlayerEquipment::pending && !ui->menu && !recoveryCompleted && RE::input==recoveryInput && RE::PlayerControls::GetSingleton()->blockPlayerInput==recoveryBlocked);
'''
    end=program.rindex("\n}\n")
    program=program[:end]+recovery+program[end:]


if args.feedback and not args.render_probe and "bool Apply(" in source("PlayerEquipment"):
    safety=r"""
    TransferFeedback::Reset();player->rows.clear();settings->ignored.clear();
    RE::SCRIPT_FUNCTION::equipped.clear();banks[Container::Armor]->rows.clear();
    player->Put(&ring,0,1,nullptr,"worn");player->rows[&ring].extras.front()->worn=true;
    for(int i=0;i<3;++i)player->Put(&ring,0,1,nullptr,"copy "+std::to_string(i));
    auto snapshot=PlayerEquipment::Capture(player);
    auto* protectedCopy=player->rows[&ring].extras.front().get();snapshot.at(&ring).equipped.insert(protectedCopy);
    for(int i=0;i<2;++i){
        assert(PlayerEquipment::Apply(snapshot,&ring,[&]{
            auto copies=InventoryStacks::Read(player,{},&ring);
            assert(InventoryStacks::Move(copies.back(),banks[Container::Armor].get())==1);return true;
        }));
        assert(PlayerEquipment::Current()==nullptr && player->rows[&ring].extras.front().get()==protectedCopy);
    }
    protectedCopy->worn=false;bool called=false;
    assert(!PlayerEquipment::Apply(snapshot,&ring,[&]{called=true;return true;}) && !called && !snapshot.contains(&ring));
    assert(!PlayerEquipment::Apply(snapshot,&ring,[&]{called=true;return false;}) && !called);
    assert(!PlayerEquipment::Apply(snapshot,nullptr,[&]{called=true;return false;}) && !called);
    try{PlayerEquipment::Apply(snapshot,&note,[]{throw std::runtime_error("interrupted");return false;});assert(false);}
    catch(const std::runtime_error&){}assert(PlayerEquipment::Current()==nullptr);

    // Cancellation after the first removal must discard every remaining batch.
    for(int interruption=0;interruption<4;++interruption){
        TransferFeedback::Reset();player->rows.clear();banks[Container::Armor]->rows.clear();RE::SCRIPT_FUNCTION::equipped.clear();
        player->Put(&ring,0,1,nullptr,"worn");player->rows[&ring].extras.front()->uiWorn=true;
        RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        for(int i=0;i<100;++i)player->Put(&ring,0,1,nullptr,"copy "+std::to_string(i));
        ui->messageBox=false;stores->options.clear();timers.clear();RE::SendHUDMessage::message.clear();
        bool finished=false;stores->OffloadItems([&]{finished=true;});
        auto pump=[&]{
            ProbeClock::tick+=std::chrono::milliseconds(16);SKSEMenuFramework::render();
            auto ready=std::move(timers);timers.clear();for(auto& action:ready)action();
            queue->ProcessCommands();tasks->RunUI();tasks->Run();
        };
        for(int frame=0;banks[Container::Armor]->rows[&ring].total==0 && frame<400;++frame)pump();
        const int moved=banks[Container::Armor]->rows[&ring].total;
        assert(moved>0 && moved<100 && !finished);
        if(interruption==1)player->rows[&ring].extras.front()->worn=true;
        else if(interruption==2)player->refuse=true;
        else if(interruption==3)player->rows[&ring].favorite=true;
        else TransferFeedback::Reset();
        for(int frame=0;frame<100;++frame)pump();
        assert(banks[Container::Armor]->rows[&ring].total==moved && player->rows[&ring].total==101-moved);
        assert(finished==(interruption!=0) && !PlayerEquipment::IsRunning());
        assert(!SKSEMenuFramework::block(nullptr));
        assert(interruption!=0 || RE::SendHUDMessage::message.empty());
        player->refuse=false;
    }
"""
    marker='    TransferFeedback::Reset();player->rows.clear();settings->ignored.clear();'
    index=program.index(marker)
    program=program[:index]+safety+program[index:]

if args.scenarios:
    from support import sorting
    program=program[:program.index('int main(){')]+(ROOT/'tests/support/sorting.cpp').read_text().replace('SORTING_DEFINITIONS',sorting.definitions())

if startup_checks:
    if '        void CaptureStep(' in program:program = '#define AV_SLICED_INSPECTION\n' + program
    startup=(ROOT/'tests/support/transfer_startup.cpp').read_text()
    if args.startup_only:
        program=program[:program.index('int main(){')]+startup+'\nint main(){CheckStartup();}\n'
    else:
        program=program.replace('int main(){',startup+'\nint main(){\nCheckStartup();',1)

if args.render_probe:
    common,program=rendering.instrument(common,program)

if args.profile:
    needle="int main(){"
    assert needle in program
    program=program.replace(needle,r'''
int main(int argc,char** argv){
    assert(argc==3);RE::Profile::candidate=std::stoi(argv[1]);const int padding=std::stoi(argv[2]);
    assert(RE::Profile::candidate>=0 && RE::Profile::candidate<=2 && padding>=0 && padding<=1000);
    std::vector<std::unique_ptr<RE::TESBoundObject>> unrelated;
    for(int i=0;i<padding;++i)unrelated.push_back(std::make_unique<RE::TESBoundObject>(70000+i));
''')
    program=program.replace("        const auto input=RE::input;", "        for(auto& item:unrelated)player->Put(item.get(),1);\n        const auto input=RE::input;")
    program=program.replace("        assert((entry==0)==!stores->options.empty());", "        for(auto& item:unrelated)assert(player->rows[item.get()].total==1);\n        assert((entry==0)==!stores->options.empty());")

profile={"complete":False,"runner_pid":os.getpid(),"active_child_pid":None,"samples":[]}
cases=[]
def profile_command(command,timeout):
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True) as child:
        profile["active_child_pid"]=child.pid
        args.output.write_text(json.dumps(profile,indent=2)+"\n")
        try:
            output,_=child.communicate(timeout=timeout)
        except BaseException:
            child.terminate()
            try:child.communicate(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.communicate()
            raise
        finally:
            profile["active_child_pid"]=None
            args.output.write_text(json.dumps(profile,indent=2)+"\n")
        if child.returncode:
            args.output.with_suffix(".log").write_text(output)
            raise subprocess.CalledProcessError(child.returncode,command,output=output)
        return output

if args.profile or args.render_probe:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    def stop_profile(_signal,_frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop_profile)
with tempfile.TemporaryDirectory(prefix="av-transfer-pipeline-") as directory:
    path=Path(directory);(path/"OffloadBatch.h").write_text((ROOT/"src/OffloadBatch.h").read_text().replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;"))
    soul=source("Soulgems");soul=soul[:soul.index("    void TakeEmpty(")]+"}\n"
    soul=soul.replace("    Counts carriedBefore;", "").replace("    std::unordered_set<RE::FormID> loanForms;", "").replace("    std::int64_t remainingLoan{};", "")
    start=soul.index("    Counts CountGems(");soul=soul[:start]+soul[soul.index("\n}\n",start):]
    soul=profiled(soul,"    void Deposit(","soul gem deposit")
    soul=profiled(soul,"    void Recover(","soul gem recovery")
    soul=soul.replace("            if (archive && archive != bank) {", "            if (archive && archive != bank) {\n                if(RE::Profile::candidate==1 && !InventoryStacks::HasItems(archive))continue;")
    if args.frame_startup:
        from support import transfer_frame_probe
        common,program,soul=transfer_frame_probe.instrument(common,program,soul)
    (path/"common.hpp").write_text("#pragma once\n"+common)
    (path/"check.cpp").write_text(program)
    (path/"Soulgems.cpp").write_text('#include "common.hpp"\n#include "OffloadBatch.h"\n'+"\n".join(line for line in soul.splitlines() if not line.startswith("#include")))
    flags=["-fsanitize=address,undefined","-fno-omit-frame-pointer"] if args.sanitize else []
    if args.profile or args.render_probe:
        flags.append("-DAV_PROFILE")
        if not args.sanitize:flags.append("-O2")
    command=["g++","-std=c++20","-Wall","-Wextra","-Werror",*flags,"-I",str(ROOT),str(path/"check.cpp"),str(path/"Soulgems.cpp"),"-o",str(path/"check")]
    if args.render_probe:
        profile_command(command,90)
        models=[rendering.MODELS.index(name) for name in args.cost_models]
        for size in args.sizes:
            for sample in range(args.samples):
                for model in models if sample%2==0 else reversed(models):
                    rows=[json.loads(line) for line in profile_command([str(path/"check"),str(model),str(size)],90).splitlines()]
                    for row in rows:
                        if "fixture_cpu_ms" in row:row["fixture_elapsed_ms"]=row.pop("fixture_cpu_ms")
                    profile["samples"].append({"model":rendering.MODELS[model],"size":size,"sample":sample,
                        "controls":[row for row in rows if "control" in row],"cases":[row for row in rows if "control" not in row]})
                    args.output.write_text(json.dumps(profile,indent=2)+"\n")
                print(f"Render probe size={size} repeat={sample+1}/{args.samples}",flush=True)
    elif args.profile:
        profile_command(command,90)
        for size in args.sizes:
            for sample in range(args.samples):
                for candidate in ((0,1,2) if sample%2==0 else (2,1,0)):
                    output=profile_command([str(path/"check"),str(candidate),str(size)],30)
                    cases=[json.loads(line) for line in output.splitlines()]
                    profile["samples"].append({"candidate":candidate,"size":size,"sample":sample,"cases":cases})
                    args.output.write_text(json.dumps(profile,indent=2)+"\n")
                print(f"Profile size={size} repeat={sample+1}/{args.samples}",flush=True)
    else:
        subprocess.run(command,check=True,timeout=90)
        if args.scenarios:
            fixtures=sorted(args.scenarios.glob('*.json'))
            fixtures=[p for p in fixtures if p.name!='catalog.json']
            if not fixtures:raise ValueError('No representative sorting fixtures')
            cases=[]
            for fixture in fixtures:
                expanded=path/'scenario.json';expanded.write_text(json.dumps(sorting.scenario(fixture)))
                cases.extend(json.loads(line) for line in subprocess.check_output([str(path/'check'),str(expanded)],text=True,timeout=120).splitlines())
                print(f'Validated representative inventory {fixture.stem}',flush=True)
        else:
            cases=[json.loads(line) for line in subprocess.check_output([str(path/"check")],text=True,timeout=120 if args.frame_startup else 30).splitlines()]
args.output.parent.mkdir(parents=True,exist_ok=True)
if args.frame_startup:
    controls=[case for case in cases if 'control' in case]
    rows=[case for case in cases if 'control' not in case]
    expected={(entry,phase,size) for entry in range(3) for phase in (
        'capture','protected capture','row indexing','row matching','delayed rows','validation',
        'candidate enumeration','job expansion','soul gem recovery','distinct soul gems','native inventory','native menu','native bulk',
        'cancel during readiness') for size in (1,1000)}
    population={(case['entry'],case['phase'],case['size']) for case in rows}
    if population!=expected or len(rows)!=len(expected) or len(controls)!=5 or not all(c['passed'] for c in controls):
        raise ValueError('Incomplete frame-startup scenarios or failed scheduler controls')
    if any(not case['draw_gaps_ms'] or abs(max(case['draw_gaps_ms'])-case['max_gap_ms'])>.01 for case in rows):
        raise ValueError('Frame gap summary differs from raw draws')
    failures=[case for case in rows if not case['passed']]
    args.output.write_text(json.dumps({'complete':True,'passed':not failures,'source_ref':args.source_ref,
        'source_commit':subprocess.check_output(['git','rev-parse',args.source_ref or 'HEAD'],cwd=ROOT,text=True).strip(),
        'sanitizers':args.sanitize,
        'source_sha256':{name:hashlib.sha256(source(name).encode()).hexdigest() for name in tracked_sources},
        'fixture_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            'tests/support/transfer_frame_probe.py','tests/support/transfer_frames.cpp','tests/support/engine.hpp',
            'tests/regression/check_quick_transfer_pipeline.py','tests/regression/check_quick_transfer_frames.py',
            'tests/support/feedback.py','tests/support/engine.py')},
        'boundary':'Actual production loops/controller/transfers with supplied engine and UI boundaries. Each targeted loop iteration costs 0.1 simulated ms. Opaque native controls cost 250 simulated ms once. Draw callbacks run only in the fixture frame pump, never inside production work or opaque calls. These inputs are not Skyrim timings or proof of the reported native cause.',
        'frame_interval_simulated_ms':16,'max_gap_budget_simulated_ms':50,'controls':controls,'cases':rows,
        'responsiveness_failures':failures},indent=2)+'\n')
    print(f"Frame startup: {len(rows)} cases, {len(failures)} responsiveness failures; safety assertions passed; {args.output}")
    raise SystemExit(1 if failures else 0)
startup_cases=[case for case in cases if case.get('startup')]
cases=[case for case in cases if not case.get('startup')]
startup_contract={
    'startup_fixture_sha256':hashlib.sha256((ROOT/'tests/support/transfer_startup.cpp').read_bytes()).hexdigest(),
    'startup_boundary':'Production controller and physical transfer code. Engine/UI messages and readiness are modelled; delayed initial completion is an external fixture input, not a verified Skyrim schedule. Call counts and clock values are not measured game latency.',
    'startup_scenarios':['disabled jewelry','two native-worn copies','ready worn and enchanted spare',
        'initial rows delayed five frames','initial rows delayed eight frames','row objects delayed five frames',
        'equipment markers delayed five frames','cancel during initialization and stale poll',
        'initialization never completes','favorite state changes after inspection','favorite enchanted copy and spare',
        'one explicit refresh required','valid-looking unequipped markers before late stamping',
        'originating message box delays initial menu opening'],
    'startup_protections':['quest','favorite','ignore list'],
} if startup_checks else {}
if args.scenarios:
    args.output.write_text(json.dumps({'complete':True,'passed':True,'cases':cases,'boundary':'Production Quick Transfer controller, inspection, physical transfers and feedback with supplied classification masks and engine/UI stubs. Host fixture durations are observations, not game latency or calibrated performance gates.'},indent=2)+'\n')
    print(f'Representative sorting checks: {len(cases)} inventory/entry cases; {args.output}')
    raise SystemExit(0)
if args.render_probe:
    profile.update({"complete":True,"source_ref":args.source_ref,"source_commit":subprocess.check_output(["git","rev-parse",args.source_ref or "HEAD"],cwd=ROOT,text=True).strip(),
        "source_sha256":{name:hashlib.sha256(source(name).encode()).hexdigest() for name in tracked_sources},"sanitizers":args.sanitize,
        "fixture_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ["tests/regression/check_quick_transfer_pipeline.py", "tests/support/transfer_render_probe.py", "tests/support/engine.hpp", "tests/support/engine.py", "tests/support/feedback.py"]},
        "boundary":"Production pipeline and renderer with engine/classification/UI stubs. Render callbacks occur only at simulated frame boundaries, never inside native calls. Simulated native durations are chosen test inputs, not Skyrim measurements. Measured durations are fixture wall-clock time, including instrumentation and scheduling overhead. Native stub-internal reads/removals inside bulk transfer are not double charged. The scheduler controls exercise the fixture queue, not a measured Skyrim queue policy.",
        "costs":{"zero":"No native cost","distributed":"Removal 1 ms; inventory/bulk 0.25 ms + 0.002 ms per base record","slow-read":"First inventory call during transfer work costs 250 ms","slow-remove":"First removal during transfer work costs 250 ms","slow-bulk":"First bulk call during transfer work costs 250 ms","slow-preflight":"First inventory call before transfer work costs 250 ms"},"frame_interval_simulated_ms":16,"render_gap_budget_simulated_ms":50,
        "entries":["Arcane Vault","assigned Quick Transfer","hotkey handoff"],"shapes":["empty","worn only","worn and same-base enchanted copies","distinct sortable notes","same-base soul-gem quantity","protected loadout with ignored records","protected loadout with one spare and unrelated records"],
        "source_header_sha256":{name:hashlib.sha256((ROOT/"src"/name).read_bytes()).hexdigest() for name in ["ItemClass.h","Settings.h","InventoryStacks.h","PlayerEquipment.h","TransferFeedback.h","Soulgems.h","OffloadBatch.h"]}})
    groups={}
    for sample in profile["samples"]:
        for case in sample["cases"]:
            key=(sample["model"],sample["size"],case["entry"],case["shape"],case["archives_populated"])
            groups.setdefault(key,[]).append(case)
    profile["summary"]=[]
    for key,rows in groups.items():
        summary=dict(zip(["model","size","entry","shape","archives_populated"],key))
        for metric in ["fixture_elapsed_ms","max_task_elapsed_ms","max_render_gap_simulated_ms","max_task_simulated_ms","frames_during_work","work_color_changes"]:
            values=[row[metric] for row in rows];summary[metric]={"min":min(values),"median":statistics.median(values),"max":max(values)}
        profile["summary"].append(summary)
    failures=[row for row in profile["summary"] if row["model"]=="distributed" and row["max_render_gap_simulated_ms"]["max"]>50]
    profile["responsiveness_regressions"]=failures
    args.output.write_text(json.dumps(profile,indent=2)+"\n")
    print(f"Render probe: {len(groups)} scenarios; {len(failures)} distributed-cost responsiveness failures; report {args.output}")
    raise SystemExit(1 if failures else 0)
if args.profile:
    profile["complete"]=True
    profile["candidates"]=["unchanged production","skip empty bulk calls in compiled fixture","skip validation reads for an empty snapshot in compiled fixture"]
    profile["source_sha256"]={name:hashlib.sha256(source(name).encode()).hexdigest() for name in tracked_sources}
    profile["boundary"]="Serial instrumented fixture CPU timings, not Skyrim performance. Native APIs and classification are stubs. Phase times are inclusive and overlap; self times exclude timed children. Candidates modify only the compiled fixture. All production inventory/input assertions run for every sample. Unrelated padding has no sortable categories. Baseline and candidates alternate order between repeats. Active native-call costs and real UI lock waits cannot be inferred."
    summary=[]
    for size in args.sizes:
        for candidate in (0,1,2):
            samples=[s for s in profile["samples"] if s["size"]==size and s["candidate"]==candidate]
            for index,case in enumerate(samples[0]["cases"]):
                values=[s["cases"][index]["fixture_cpu_ms"] for s in samples]
                summary.append({"candidate":candidate,"size":size,"entry":case["entry"],"shape":case["shape"],"archives_populated":case["archives_populated"],"soulgems_enabled":case["soulgems_enabled"],"stalled":case["stalled"],"min_ms":min(values),"median_ms":statistics.median(values),"max_ms":max(values)})
    profile["summary"]=summary
    args.output.write_text(json.dumps(profile,indent=2)+"\n")
    print(f"Profile complete: {sum(len(sample['cases']) for sample in profile['samples'])} inventory/input cases; report {args.output}")
    raise SystemExit(0)
args.output.write_text(json.dumps({"source_ref":args.source_ref,"feedback_enabled":args.feedback,"extra_cases":["refused native Hide, manual exit and restored input"] if args.feedback else [],"source_sha256":{name:hashlib.sha256(source(name).encode()).hexdigest() for name in tracked_sources},"boundary":"Production inspector, OffloadItemsNow, Book/Note/potion/instrument consolidation, physical animation polling, Arcane Vault callback and assignment dispatch. Engine, classification and message-box presentation are stubs. Hotkey starts at its OffloadItems handoff, without keyboard matching. Uses production soul-gem recovery and deposit, including mixed empty/filled stacks and reserves. Empty and populated archives are exercised. No artificial game-poll stall is injected. Native bulk/remove/read call counts are observations in the fixture, not measured Skyrim costs. Times and input state are simulated.","entries":["Arcane Vault","assigned Quick Transfer","hotkey handoff"],"shapes":["empty","worn only","worn and spares","mixed reserves and notes","mixed empty/filled soul gems","standard protected loadout","standard loadout and one spare"],"cases":cases,"startup_cases":startup_cases,**startup_contract},indent=2)+"\n")
failures=sum(not case["prompt"] for case in cases)
startup_failures=sum(not case['passed'] for case in startup_cases)
print(f"Pipeline checks: {len(cases)} inventory/input invariants pass; {failures} slow returns; {startup_failures}/{len(startup_cases)} startup requirements fail; report {args.output}")
raise SystemExit(1 if failures or startup_failures else 0)
