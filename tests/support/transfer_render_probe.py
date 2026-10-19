"""Instrument the existing production pipeline fixture without yielding inside native calls."""

MODELS = ["zero", "distributed", "slow-read", "slow-remove", "slow-bulk", "slow-preflight"]

PROBE = r'''
#include <iostream>
struct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};
namespace RenderProbe {
inline int model=0,bulkDepth=0;
struct PhaseStats {int visits=0,calls=0;double nativeMs=0,maxSpan=0;};
struct State {
    bool enabled=false,working=false,finished=false,slowCharged=false;
    int frames=0,workFrames=0,colorChanges=0,confirmations=0,calls=0;
    unsigned lastColor=0;
    double start=0,lastDraw=0,workStart=0,workEnd=0,maxGap=0,maxNative=0,maxTask=0,maxTaskCpu=0;
    std::vector<double> gaps;
    std::map<std::string,double> nativeMs;
    std::string phase="unattributed",slowPhase;
    std::map<std::string,PhaseStats> phases;
} inline state;
inline double Now(){return std::chrono::duration<double,std::milli>(ProbeClock::now().time_since_epoch()).count();}
struct Phase {
    std::string name,previous;double start;bool enabled;
    explicit Phase(const char* value):name(value),previous(state.phase),start(Now()),enabled(state.enabled){
        if(enabled){state.phase=name;++state.phases[name].visits;}
    }
    ~Phase(){if(enabled){auto& phase=state.phases[name];phase.maxSpan=std::max(phase.maxSpan,Now()-start);state.phase=previous;}}
};
inline void Reset(){state={};state.enabled=true;state.start=state.lastDraw=Now();bulkDepth=0;}
inline void Work(){if(state.enabled && !state.working){state.working=true;state.workStart=Now();}}
inline void Finish(){if(!state.enabled)return;assert(state.working && ++state.confirmations==1);state.finished=true;state.workEnd=Now();state.maxGap=std::max(state.maxGap,Now()-state.lastDraw);}
inline void Draw(unsigned color){
    if(!state.enabled || state.finished)return;
    const double gap=Now()-state.lastDraw;state.gaps.push_back(gap);state.maxGap=std::max(state.maxGap,gap);state.lastDraw=Now();++state.frames;
    if(state.working){++state.workFrames;if(state.lastColor && state.lastColor!=color)++state.colorChanges;state.lastColor=color;}
}
struct NativeCall {
    bool bulk=false;
    NativeCall(const char* name,std::size_t units=0){
        if(!state.enabled || bulkDepth)return;
        ++state.calls;double cost=0;
        if(model==1)cost=std::string_view{name}=="remove"?1.0:0.25+0.002*units;
        const bool slow=(model==2 && std::string_view{name}=="inventory") ||
            (model==3 && std::string_view{name}=="remove") || (model==4 && std::string_view{name}=="bulk");
        const bool preflight=model==5 && !state.working && std::string_view{name}=="inventory";
        if(((slow && state.working) || preflight) && !state.slowCharged){cost=250;state.slowCharged=true;state.slowPhase=state.phase;}
        state.nativeMs[name]+=cost;state.maxNative=std::max(state.maxNative,cost);
        auto& phase=state.phases[state.phase];++phase.calls;phase.nativeMs+=cost;
        ProbeClock::tick+=std::chrono::duration_cast<ProbeClock::time_point::duration>(std::chrono::duration<double,std::milli>(cost));
        bulk=std::string_view{name}=="bulk";if(bulk)++bulkDepth;
    }
    ~NativeCall(){if(bulk)--bulkDepth;}
};
inline void Dispatch(const std::function<void()>& task){
    const double start=Now();const auto cpu=std::chrono::steady_clock::now();task();
    if(state.enabled){state.maxTask=std::max(state.maxTask,Now()-start);state.maxTaskCpu=std::max(state.maxTaskCpu,
        std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-cpu).count());}
}
inline void Dump(){
    assert(state.finished && state.confirmations==1);state.enabled=false;
    const double gap=std::max(state.maxGap,state.workEnd-state.lastDraw);
    std::cout<<",\"render_frames\":"<<state.frames<<",\"frames_during_work\":"<<state.workFrames
        <<",\"work_color_changes\":"<<state.colorChanges<<",\"max_render_gap_simulated_ms\":"<<gap
        <<",\"work_simulated_ms\":"<<state.workEnd-state.workStart<<",\"max_native_simulated_ms\":"<<state.maxNative
        <<",\"max_task_simulated_ms\":"<<state.maxTask<<",\"max_task_elapsed_ms\":"<<state.maxTaskCpu
        <<",\"injected_slow_call\":"<<(state.slowCharged?"true":"false")<<",\"charged_native_calls\":"<<state.calls
        <<",\"responsive_simulated\":"<<(gap<=50?"true":"false")<<",\"slow_call_phase\":\""<<state.slowPhase<<"\",\"native_simulated_ms\":{";
    bool first=true;for(const auto& [name,time]:state.nativeMs){if(!first)std::cout<<",";first=false;std::cout<<"\""<<name<<"\":"<<time;}std::cout<<"},\"render_gaps_simulated_ms\":[";
    first=true;for(double time:state.gaps){if(!first)std::cout<<",";first=false;std::cout<<time;}std::cout<<"],\"phase_costs\":{";
    int calls=0;double charged=0;first=true;
    for(const auto& [name,phase]:state.phases){
        if(!first){std::cout<<",";}first=false;calls+=phase.calls;charged+=phase.nativeMs;
        std::cout<<"\""<<name<<"\":{\"visits\":"<<phase.visits<<",\"native_calls\":"<<phase.calls
            <<",\"native_simulated_ms\":"<<phase.nativeMs<<",\"max_span_simulated_ms\":"<<phase.maxSpan<<"}";
    }
    std::cout<<"}";double native=0;for(const auto& [name,time]:state.nativeMs){(void)name;native+=time;}
    assert(calls==state.calls && std::abs(charged-native)<.001);
    if(state.slowCharged)assert(gap>=249.9);
}
}
'''

CONTROLS = r'''
void RenderOne(){
    ImGuiMCP::renderTime=RenderProbe::Now()/1000;
    ImGuiMCP::fills.clear();ImGuiMCP::outlines.clear();ImGuiMCP::lineColors.clear();
    SKSEMenuFramework::render();
}
void CheckRenderScheduler(){
    using namespace std::chrono_literals;
    auto* tasks=SKSE::GetTaskInterface();const int savedModel=RenderProbe::model;RenderProbe::model=1;
    RenderProbe::Reset();const auto before=RenderProbe::Now();
    {RenderProbe::NativeCall bulk{"bulk",100};RenderProbe::NativeCall nestedRead{"inventory",100};RenderProbe::NativeCall nestedMove{"remove"};}
    assert(RenderProbe::bulkDepth==0 && RenderProbe::state.calls==1 && std::abs(RenderProbe::Now()-before-.45)<.001);
    RenderProbe::state.enabled=false;RenderProbe::NativeCall inactive{"remove"};assert(RenderProbe::state.calls==1);
    RenderProbe::Reset();
    {
        RenderProbe::Phase outer{"outer"};{RenderProbe::NativeCall read{"inventory"};}
        {RenderProbe::Phase inner{"inner"};RenderProbe::NativeCall remove{"remove"};}
        {RenderProbe::NativeCall read{"inventory"};}
    }
    assert(RenderProbe::state.phase=="unattributed" && RenderProbe::state.calls==3);
    assert(RenderProbe::state.phases["outer"].calls==2 && RenderProbe::state.phases["inner"].calls==1);
    assert(std::abs(RenderProbe::state.phases["outer"].nativeMs-.5)<.001 &&
        std::abs(RenderProbe::state.phases["outer"].maxSpan-1.5)<.001 &&
        std::abs(RenderProbe::state.phases["inner"].maxSpan-1)<.001);
    for(int model=0;model<6;++model){
        RenderProbe::model=model;RenderProbe::Reset();const auto start=RenderProbe::Now();
        if(model!=5)RenderProbe::Work();
        const char* kind=model==3?"remove":model==4?"bulk":"inventory";
        {RenderProbe::NativeCall first{kind};}{RenderProbe::NativeCall second{kind};}
        const double expected=model==0?0:model==1?.5:250;
        assert(std::abs(RenderProbe::Now()-start-expected)<.001 && RenderProbe::state.calls==2);
    }
    RenderProbe::state.enabled=false;RenderProbe::model=1;
    for(bool gated:{false,true}){
        TransferFeedback::Reset();RenderProbe::state.enabled=false;TransferFeedback::Complete done;
        TransferFeedback::Begin([&](TransferFeedback::Complete finish){done=std::move(finish);});
        for(int i=0;!done && i<5;++i){
            RenderOne();ProbeClock::tick+=16ms;auto ready=std::move(timers);timers.clear();for(auto& action:ready)action();tasks->Run();
        }
        assert(done);RenderProbe::Reset();RenderOne();RenderProbe::Work();int count=0;
        if(gated){
            for(int frame=0;frame<20;++frame){
                tasks->AddTask([&]{for(int i=0;i<10;++i){RenderProbe::NativeCall call{"remove"};++count;}});
                tasks->Run();ProbeClock::tick+=16ms;RenderOne();
            }
        }else{
            std::function<void()> work;work=[&]{RenderProbe::NativeCall call{"remove"};if(++count<200)tasks->AddTask(work);};
            tasks->AddTask(work);tasks->Run();
        }
        RenderProbe::Finish();assert(count==200 && done());
        assert(gated?(RenderProbe::state.maxGap<=50 && RenderProbe::state.workFrames==20 && RenderProbe::state.colorChanges>0):
            (RenderProbe::state.maxGap>=200 && RenderProbe::state.workFrames==0));
        std::cout<<"{\"control\":\""<<(gated?"render-gated":"same-drain requeue")<<"\"";RenderProbe::Dump();std::cout<<"}\n";
    }
    RenderProbe::model=savedModel;
}
'''


def instrument(common, program):
    clock = "struct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};"
    assert common.count(clock) == 1
    common = common.replace(clock, "").replace("namespace RE { struct TESBoundObject; }", PROBE + "\nnamespace RE { struct TESBoundObject; }")
    for old, new in [
        ('Profile::Scope phase{"inventory API stub"};', 'RenderProbe::NativeCall native{"inventory",rows.size()};Profile::Scope phase{"inventory API stub"};'),
        ('Profile::Scope phase{"bulk API stub"};', 'RenderProbe::NativeCall native{"bulk",source->rows.size()};Profile::Scope phase{"bulk API stub"};'),
        ('assert(!inspectionOpen);++removeCalls;', 'RenderProbe::NativeCall native{"remove"};assert(!inspectionOpen);++removeCalls;'),
        ('}task();}}', '}RenderProbe::Dispatch(task);}}'),
        ('ui.pop_front();task();}}', 'ui.pop_front();RenderProbe::Dispatch(task);}}'),
        ('message=text;', 'message=text;RenderProbe::Finish();'),
    ]:
        assert old in common, old
        common = common.replace(old, new)
    program = program.replace('textPosition=position;++texts;', 'textPosition=position;++texts;RenderProbe::Draw(lineColors.back());')
    assert "RenderProbe::Draw" in program
    for signature, phase in [
        ('    void Run(std::function<void()> work, std::function<void()> complete, std::function<bool(RE::TESBoundObject*)> eligible) {' if 'std::function<bool(RE::TESBoundObject*)> eligible) {' in program else '    void Run(std::function<void()> work, std::function<void()> complete) {', 'equipment preflight'),
        ('        Snapshot Capture(RE::PlayerCharacter* player, InventoryStacks::Select select = {}) {' if 'Snapshot Capture(RE::PlayerCharacter* player, InventoryStacks::Select' in program else '        Snapshot Capture(RE::PlayerCharacter* player) {', 'physical capture'),
        ('        Snapshot Read(RE::InventoryMenu* menu, const Snapshot& physical, RE::RefHandle owner) {', 'equipment menu rows'),
        ('        void Work(const std::shared_ptr<Request>& request, const Snapshot& snapshot) {', 'equipment validation'),
        ('void Stores::OffloadItemsNow(std::function<void()> complete) {' if 'void Stores::OffloadItemsNow(std::function<void()> complete) {' in program else 'void Stores::OffloadItemsNow() {', 'transfer queue setup'),
        ('void Stores::AllToStore(Container a_source, Container a_destination) {', 'archive consolidation'),
        ('void Stores::StoreToStore(ItemCategory a_category, Container a_source, Container a_destination) {', 'archive rerouting'),
    ]:
        assert program.count(signature) == 1, signature
        program = program.replace(signature, signature + f'\n    RenderProbe::Phase renderPhase{{"{phase}"}};')
    program = program.replace("int main(){", CONTROLS + "\nint main(int argc,char** argv){\n    assert(argc==3);RenderProbe::model=std::stoi(argv[1]);const int workload=std::stoi(argv[2]);")
    program = program.replace("    SKSEMenuFramework::installed=true;TransferFeedback::Register();", "    SKSEMenuFramework::installed=true;TransferFeedback::Register();CheckRenderScheduler();")
    signature = 'void Stores::OffloadItemsNow(std::function<void()> complete) {' if 'void Stores::OffloadItemsNow(std::function<void()> complete) {' in program else 'void Stores::OffloadItemsNow() {'
    assert program.count(signature) == 1
    work = '    TransferFeedback::Run([actions](const std::function<bool()>& active) {'
    assert program.count(work) == 1
    program = program.replace(work, '    RenderProbe::Work();\n' + work)
    assert 'RenderProbe::Work();' in program
    program = program.replace('for(bool stalled:{false,true})for(bool gems:{false,true})', 'for(bool stalled:{false})for(bool gems:{true})')
    program = program.replace('        TransferFeedback::Reset();\n        settings->ignored.clear();', '        RenderProbe::state.enabled=false;TransferFeedback::Reset();\n        settings->ignored.clear();')
    seed = r'''
        std::vector<std::unique_ptr<RE::TESBoundObject>> extraItems;
        std::vector<std::unique_ptr<RE::EnchantmentItem>> enchantments;
        RE::TESForm owner{12345};
        for(int i=0;i<workload;++i){
            if(shape==2){
                enchantments.push_back(std::make_unique<RE::EnchantmentItem>());
                player->Put(&ring,0,1,&owner,"variant "+std::to_string(i));player->rows[&ring].extras.back()->enchantment=RE::ExtraEnchantment{enchantments.back().get()};
            }else if(shape==3 || shape>=5){
                extraItems.push_back(std::make_unique<RE::TESBoundObject>(70000+i));auto* item=extraItems.back().get();
                item->categories=shape==3?ToMask(ItemCategory::Note):0;player->Put(item,1);
                if(shape==3 && archived)banks[Container::Recipes]->Put(item,1);
                if(shape==5)settings->ignored.insert(item);
            }
        }
        if(shape==4)player->Put(&gem,workload);
        RenderProbe::Reset();
'''
    program = program.replace('        const auto input=RE::input;', seed + '\n        const auto input=RE::input;', 1)
    program = program.replace('            SKSEMenuFramework::render();', '            RenderOne();')
    program = program.replace('(shape==2?2:shape==6?1:0)', '(shape==2?2+workload:shape==6?1:0)')
    program = program.replace('(gems?25:50)', '(gems?25:50+workload)').replace('(shape==4 && gems?25:0)', '(shape==4 && gems?25+workload:0)')
    verify = r'''
        if(shape==2){
            std::map<std::string,RE::ExtraDataList*> copies;
            for(auto& extra:banks[Container::Armor]->rows[&ring].extras)copies[extra->metadata]=extra.get();
            for(int i=0;i<workload;++i){auto* extra=copies.at("variant "+std::to_string(i));assert(extra->count==1 && extra->owner==&owner && extra->enchantment->enchantment==enchantments[i].get());}
        }
        for(auto& item:extraItems){
            assert(player->rows[item.get()].total==(shape==3?0:1));
            if(shape==3)assert(banks[Container::Notes]->rows[item.get()].total==1+archived && banks[Container::Recipes]->rows[item.get()].total==0);
        }
'''
    program = program.replace('        assert((entry==0)==!stores->options.empty());', verify + '\n        assert((entry==0)==!stores->options.empty());')
    program = program.replace('DumpProfile(fixtureMs);std::cout<<"}\\n";', 'DumpProfile(fixtureMs);RenderProbe::Dump();std::cout<<"}\\n";')
    program = program.replace("elapsed<12000", "elapsed<120000")
    recovery = program.index('    TransferFeedback::Reset();player->rows.clear();settings->ignored.clear();')
    program = program[:recovery] + program[program.index('\n}\n', recovery):]
    return common, program
