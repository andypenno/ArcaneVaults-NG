"""Charge real loop iterations without inserting render opportunities into production work."""
from pathlib import Path

PROBE = r'''
struct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};
namespace FrameProbe {
inline std::string target,scope,worstPhase;
inline bool enabled=false,opaqueCharged=false;
inline double lastDraw=0,maxGap=0;
inline int draws=0,units=0,confirmations=0;
inline std::map<std::string,double> sinceDraw;
inline std::vector<double> gaps;
inline std::function<void()> afterShow;
inline double Now(){return std::chrono::duration<double,std::milli>(ProbeClock::now().time_since_epoch()).count();}
struct Scope {
    std::string previous;
    explicit Scope(const char* name):previous(scope){scope=name;}
    ~Scope(){scope=previous;}
};
inline void Spend(const std::string& name,double ms){
    ++units;sinceDraw[name]+=ms;
    ProbeClock::tick+=std::chrono::duration_cast<ProbeClock::time_point::duration>(std::chrono::duration<double,std::milli>(ms));
}
inline void Unit(const char* name){
    if(!enabled)return;
    const std::string phase=std::string_view{name}=="physical"?scope:name;
    if(phase==target)Spend(phase,.1);
}
inline void Opaque(const char* name){
    if(enabled && !opaqueCharged && target==name){opaqueCharged=true;Spend(name,250);}
}
inline void Observe(){
    const double gap=Now()-lastDraw;
    gaps.push_back(gap);
    if(gap>maxGap){
        maxGap=gap;worstPhase="frame scheduling";
        if(!sinceDraw.empty())worstPhase=std::max_element(sinceDraw.begin(),sinceDraw.end(),[](const auto& a,const auto& b){return a.second<b.second;})->first;
    }
}
inline void Draw(){if(enabled){Observe();lastDraw=Now();sinceDraw.clear();++draws;}}
inline void Reset(std::string name){
    target=std::move(name);scope.clear();worstPhase.clear();enabled=true;opaqueCharged=false;
    lastDraw=Now();maxGap=0;draws=units=confirmations=0;sinceDraw.clear();gaps.clear();afterShow={};
}
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Frame probe requires one boundary: {old}')
    return text.replace(old, new)


def instrument(common, program, soul):
    clock = 'struct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};'
    common = replace_once(common, clock, '')
    common = replace_once(common, 'namespace RE { struct TESBoundObject; }', PROBE + '\nnamespace RE { struct TESBoundObject; }')
    for old, new in [
        ('Profile::Scope phase{"inventory API stub"};', 'FrameProbe::Opaque("native inventory");Profile::Scope phase{"inventory API stub"};'),
        ('Profile::Scope phase{"bulk API stub"};', 'FrameProbe::Opaque("native bulk");Profile::Scope phase{"bulk API stub"};'),
        ('ui->menu=new InventoryMenu;', 'FrameProbe::Opaque("native menu");ui->menu=new InventoryMenu;'),
        ('                inventory->ProcessMessage(message);', '                inventory->ProcessMessage(message);if(FrameProbe::afterShow)FrameProbe::afterShow();'),
        ('message=text;', 'message=text;if(FrameProbe::enabled)++FrameProbe::confirmations;'),
    ]:
        common = replace_once(common, old, new)
    paced = '        void CaptureStep(const std::shared_ptr<Request>& request) {' in program
    scopes = [
        ('        void CaptureStep(const std::shared_ptr<Request>& request) {', 'capture'),
        ('        void ValidateStep(const std::shared_ptr<Request>& request) {', 'validation'),
    ] if paced else [
        ('        Snapshot Capture(RE::PlayerCharacter* player, InventoryStacks::Select select = {}) {', 'capture'),
        ('        void Work(const std::shared_ptr<Request>& request, const Snapshot& snapshot) {', 'validation'),
    ]
    for signature, phase in scopes:
        program = replace_once(program, signature, signature + f'FrameProbe::Scope frameScope{{"{phase}"}};')
    if paced:
        start = program.index('    bool ReadPart(')
        end = program.index('    std::vector<Stack> Read(', start)
        fragment = program[start:end]
        fragment = replace_once(fragment, '        const auto total =', '        FrameProbe::Unit("physical");const auto total =')
        fragment = replace_once(fragment, '            const int count =', '            FrameProbe::Unit("physical");const int count =')
        program = program[:start] + fragment + program[end:]
        for old, new in [
            ('                auto* row = list->items[request->rowCursor];', '                FrameProbe::Unit("row indexing");auto* row = list->items[request->rowCursor];'),
            ('                    std::optional<std::size_t> match;', '                    FrameProbe::Unit("row matching");std::optional<std::size_t> match;'),
            ('                    const StackIdentity* match{};', '                    FrameProbe::Unit("row matching");const StackIdentity* match{};'),
            ('                const auto [item, count] = *listing->next++;', '                FrameProbe::Unit("candidate enumeration");const auto [item, count] = *listing->next++;'),
        ]:
            program = replace_once(program, old, new)
        marker = '                auto* item = (*candidates)[--**remaining];'
    else:
        for old, new in [
            ('            auto* entry = data.second.get();', '            FrameProbe::Unit("physical");auto* entry = data.second.get();'),
            ('                    const int count = extra->GetCount();', '                    FrameProbe::Unit("physical");const int count = extra->GetCount();'),
            ('                        if (!stack.extra) continue;', '                        FrameProbe::Unit("row matching");if (!stack.extra) continue;'),
            ('                if (item && count > 0) candidates->push_back(item);', '                if ((FrameProbe::Unit("candidate enumeration"), item) && count > 0) candidates->push_back(item);'),
        ]:
            program = replace_once(program, old, new)
        marker = '                auto* item = *it;'
    program = replace_once(program,
        '                if (row && row->data.objDesc && physical.contains(row->data.objDesc->object))',
        '                if ((FrameProbe::Unit("row indexing"), row) && row->data.objDesc && physical.contains(row->data.objDesc->object))')
    if program.count(marker) != 2:
        raise ValueError('Missing deposit/ammunition job expansion loops')
    program = program.replace(marker, '                FrameProbe::Unit("job expansion");' + marker.strip())
    program = replace_once(program, 'textPosition=position;++texts;', 'textPosition=position;++texts;FrameProbe::Draw();')
    signature = '    void Move(RE::TESObjectREFR* source, RE::TESObjectREFR* target, RE::TESSoulGem* gem, const Stack& stack, int count) {'
    soul = replace_once(soul, signature, signature + 'FrameProbe::Unit("soul gem recovery");')
    main = (Path(__file__).with_name('transfer_frames.cpp')).read_text()
    program = program[:program.index('int main(){')] + main
    return common, program, soul
