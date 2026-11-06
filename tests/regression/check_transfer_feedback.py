"""Exercise the production sorting overlay lifecycle with deterministic UI/game frames."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
from support.feedback import program, FRAMEWORK
source = (ROOT / "src/TransferFeedback.cpp").read_text()
source = source.replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;")
source = source.replace("std::thread(", "TestThread(")
source = source.replace("std::this_thread::sleep_for(std::chrono::milliseconds(16));", "")
program += "\n".join(line for line in source.splitlines() if not line.startswith("#include"))
program += r"""
namespace RE {
enum class BSEventNotifyControl { kContinue };
template<class T> struct BSTEventSource {};
struct PlayerControls {
    inline static std::array<std::uintptr_t,1> VTABLE{1};
    struct Vector {float x{},y{};};
    struct Data {Vector moveInputVec,prevMoveVec,lookInputVec,prevLookVec;bool autoMove{};} data;
    bool blockPlayerInput{};
};
}
namespace Native {
inline std::array<std::uintptr_t,2> table{};
inline std::vector<RE::InputEvent*> seen;
inline bool fail{};
RE::BSEventNotifyControl Process(RE::PlayerControls* controls, RE::InputEvent* const* events, RE::BSTEventSource<RE::InputEvent*>*) {
    seen.clear();
    for(auto* event=events?*events:nullptr;event;event=event->next)seen.push_back(event);
    controls->data.moveInputVec={1,1};controls->data.autoMove=true;
    if(fail)throw std::runtime_error("native input failure");
    return RE::BSEventNotifyControl::kContinue;
}
}
namespace REL {
template<class T> struct Relocation {
    explicit Relocation(std::uintptr_t){}
    template<class F> std::uintptr_t write_vfunc(int slot,F replacement) {
        auto original=Native::table[slot];Native::table[slot]=reinterpret_cast<std::uintptr_t>(replacement);return original;
    }
};
}
"""
program += "\n".join(line for line in (ROOT / 'src/SortingInput.cpp').read_text().splitlines() if not line.startswith('#include'))
program += r'''
int main(){
    using namespace TransferFeedback;
    using namespace std::chrono_literals;
    auto step=[] {
        ProbeClock::tick+=16ms;auto ready=std::move(timers);timers.clear();
        for(auto& action:ready){action();}
        SKSE::GetTaskInterface()->Run();
    };
    Native::table[1]=reinterpret_cast<std::uintptr_t>(Native::Process);
    SortingInput::Install();SortingInput::Install();
    auto dispatch=reinterpret_cast<SortingInput::Process>(Native::table[1]);
    RE::PlayerControls controls;
    RE::InputEvent press,releaseNative,stickNative,neutral,mouseNative,other;
    releaseNative.up=true;stickNative.button=false;stickNative.stick=true;stickNative.xValue=1;
    neutral.button=false;neutral.stick=true;mouseNative.button=false;mouseNative.mouse=true;other.button=false;
    press.next=&releaseNative;releaseNative.next=&stickNative;stickNative.next=&neutral;neutral.next=&mouseNative;mouseNative.next=&other;
    RE::InputEvent* head=&press;
    dispatch(&controls,&head,nullptr);
    assert(Native::seen.size()==6 && controls.data.moveInputVec.x==1 && controls.data.autoMove);
    Complete nativeDone;
    Begin([&](Complete done){nativeDone=std::move(done);});
    assert(IsBusy() && nativeDone);
    controls.blockPlayerInput=false;
    dispatch(&controls,&head,nullptr);
    assert((Native::seen==std::vector<RE::InputEvent*>{&releaseNative,&neutral,&other}));
    assert(press.next==&releaseNative && releaseNative.next==&stickNative && stickNative.next==&neutral && neutral.next==&mouseNative && mouseNative.next==&other);
    assert(!controls.blockPlayerInput && controls.data.moveInputVec.x==0 && !controls.data.autoMove);
    Native::fail=true;bool nativeCaught=false;
    try{dispatch(&controls,&head,nullptr);}catch(const std::runtime_error&){nativeCaught=true;}
    Native::fail=false;
    assert(nativeCaught && releaseNative.next==&stickNative && neutral.next==&mouseNative && controls.data.moveInputVec.x==0);
    dispatch(&controls,nullptr,nullptr);assert(Native::seen.empty() && controls.data.moveInputVec.x==0);
    assert(nativeDone() && !IsBusy());
    dispatch(&controls,&head,nullptr);assert(Native::seen.size()==6 && controls.data.moveInputVec.x==1);
    int starts=0;Register();
    Begin([&](Complete done){++starts;assert(done());});
    assert(starts==1);
    assert(timers.empty() && !SKSEMenuFramework::render);
    int headlessBatches=0;bool headlessDone=false;
    Begin([&](Complete done){Run([&](const std::function<bool()>& active){assert(active());return ++headlessBatches==2;},[&,done]{headlessDone=done();});});
    for(int frame=0;!headlessDone && frame<5;++frame){step();}
    assert(headlessDone && headlessBatches==2 && timers.empty());
    Run([](const std::function<bool()>&)->bool{assert(false);return true;},[]{assert(false);});
    SKSEMenuFramework::installed=true;Register();Register();assert(SKSEMenuFramework::registrations==1);
    RE::InputEvent event;Complete complete;
    Begin([&](Complete done){++starts;complete=std::move(done);});
    Begin([&](Complete){assert(false);});
    assert(starts==1 && SKSEMenuFramework::block(&event));
    RE::InputEvent release;release.up=true;RE::InputEvent motion;motion.button=false;
    assert(!SKSEMenuFramework::block(&release) && !SKSEMenuFramework::block(&motion) && !SKSEMenuFramework::block(nullptr));
    RE::InputEvent stick;stick.button=false;stick.stick=true;stick.xValue=.8f;
    assert(SKSEMenuFramework::block(&stick));stick.xValue=0;assert(!SKSEMenuFramework::block(&stick));
    RE::InputEvent mouse;mouse.button=false;mouse.mouse=true;assert(SKSEMenuFramework::block(&mouse));
    SKSEMenuFramework::render();step();assert(starts==1);
    SKSEMenuFramework::render();step();assert(starts==2 && SKSEMenuFramework::block(&event));
    assert(ImGuiMCP::backgrounds==2 && ImGuiMCP::texts==2);
    assert(complete() && !complete() && !SKSEMenuFramework::block(&event));
    stick.xValue=.8f;assert(!SKSEMenuFramework::block(&stick) && !SKSEMenuFramework::block(&mouse));
    const int priorDraws=ImGuiMCP::texts;SKSEMenuFramework::render();assert(ImGuiMCP::texts==priorDraws);

    for(bool invalidSize:{false,true}){
        Reset();ImGuiMCP::io.DisplaySize=invalidSize?ImGuiMCP::ImVec2{}:ImGuiMCP::ImVec2{1920,1080};
        const int before=starts;Begin([&](Complete done){++starts;complete=std::move(done);});
        for(int frame=0;starts==before && frame<20;++frame){if(invalidSize)SKSEMenuFramework::render();step();}
        assert(starts==before+1 && complete());
        assert(ProbeClock::tick.time_since_epoch()>=250ms);
        assert(!SKSEMenuFramework::block(&event));
    }
    for(const ImGuiMCP::ImVec2 viewport: {ImGuiMCP::ImVec2{640,480}, {1280,800}, {1920,1080}, {3440,1440}}){
        using namespace ImGuiMCP;
        io.DisplaySize=viewport;Reset();Begin([&](Complete done){complete=std::move(done);});
        auto frame=[&](double time){
            renderTime=time;fills.clear();outlines.clear();lineColors.clear();texts=0;backgrounds=0;
            SKSEMenuFramework::render();assert(texts==1&&backgrounds==1&&fills.size()==2&&outlines.size()==5);
            const auto& panel=fills.front().points;assert(panel.size()==8);
            float left=viewport.x,right=0,top=viewport.y,bottom=0;
            for(auto point:panel){left=std::min(left,point.x);right=std::max(right,point.x);top=std::min(top,point.y);bottom=std::max(bottom,point.y);}
            assert(std::abs(left+right-viewport.x)<.01f&&std::abs(top+bottom-viewport.y)<.01f);
            assert(right-left<viewport.x*.75f&&bottom-top<viewport.y*.5f);
            assert(textPosition.x>=left&&textPosition.x+140<=right&&textPosition.y>=top&&textPosition.y+24<=bottom);
            assert(std::abs(textPosition.x+70-viewport.x*.5f)<.01f);
            return outlines[2].color;
        };
        const auto dim=frame(0),bright=frame(1.3),cycled=frame(2.6);
        assert((bright>>24)>(dim>>24)+100&&dim==cycled);
        step();assert(complete());
    }
    ImGuiMCP::io.DisplaySize={1920,1080};
    Reset();const int beforeCancel=starts;Begin([&](Complete){++starts;});Reset();step();
    assert(starts==beforeCancel && !SKSEMenuFramework::block(&event));

    Begin([&](Complete done){complete=std::move(done);});
    SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    auto stale=complete;Reset();Complete newer;
    Begin([&](Complete done){newer=std::move(done);});
    assert(!stale() && SKSEMenuFramework::block(&event));
    SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    assert(!stale() && newer() && !SKSEMenuFramework::block(&event));

    Reset();Begin([](Complete){throw std::runtime_error("start refused");});
    SKSEMenuFramework::render();step();SKSEMenuFramework::render();
    bool caught=false;try{step();}catch(const std::runtime_error&){caught=true;}
    assert(caught && !SKSEMenuFramework::block(&event));

    int batches=0,finishes=0;
    auto startJob=[&](Complete done){
        Run([&](const std::function<bool()>& active){assert(active());return ++batches==3;},
            [&,done]{++finishes;assert(done());});
    };
    Begin(startJob);SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    assert(batches==0);
    for(int i=0;i<5;++i){step();}
    assert(batches==0);
    for(int i=1;i<=3;++i){
        SKSEMenuFramework::render();step();assert(batches==i);
        if(i<3){step();step();assert(batches==i && SKSEMenuFramework::block(&event));}
    }
    assert(finishes==1 && !SKSEMenuFramework::block(&event));
    step();assert(finishes==1);

    auto owned=std::make_shared<int>(42);std::weak_ptr<int> released=owned;
    Begin([&,owned](Complete){
        Run([&,owned](const std::function<bool()>& active){
            assert(active() && *owned==42);Reset();assert(!active() && *owned==42);return false;
        },[]{assert(false);});
    });
    owned.reset();SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    SKSEMenuFramework::render();step();assert(released.expired() && !SKSEMenuFramework::block(&event));
    step();

    batches=0;Begin(startJob);SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    Reset();step();assert(batches==0 && finishes==1);
    Begin([](Complete){Run([](const std::function<bool()>&)->bool{throw std::runtime_error("batch refused");},[]{assert(false);});});
    SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();SKSEMenuFramework::render();
    caught=false;try{step();}catch(const std::runtime_error&){caught=true;}
    assert(caught && !SKSEMenuFramework::block(&event));

    batches=0;Begin(startJob);SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    for(int i=0;finishes==1 && i<60;++i)step();
    assert(batches==3 && finishes==2 && !SKSEMenuFramework::block(&event));
    Begin({});SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    assert(!SKSEMenuFramework::block(&event));
}
'''
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="av-transfer-feedback-") as temporary:
        path = Path(temporary)
        (path / "check.cpp").write_text(program)
        flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if args.sanitize else []
        subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", *flags,
                        "-I", str(ROOT), str(path / "check.cpp"), "-o", str(path / "check")], check=True, timeout=60)
        subprocess.run([str(path / "check")], check=True, timeout=10)
    print("PASS: frame-gated batches, headless/stalled progress, mid-batch reset and captured-state release, rendered-frame barrier, button blocking with releases preserved, completion, overlap, absent/stalled renderer, reset, stale callbacks, failures, compact panel bounds, single label and pulsing sigil")


if __name__ == "__main__":
    main()
