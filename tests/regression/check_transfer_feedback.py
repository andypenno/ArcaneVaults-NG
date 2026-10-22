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
program += r'''
int main(){
    using namespace TransferFeedback;
    using namespace std::chrono_literals;
    auto step=[] {
        ProbeClock::tick+=16ms;auto ready=std::move(timers);timers.clear();
        for(auto& action:ready){action();}
        SKSE::GetTaskInterface()->Run();
    };
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
    SKSEMenuFramework::render();step();assert(starts==1);
    SKSEMenuFramework::render();step();assert(starts==2 && SKSEMenuFramework::block(&event));
    assert(ImGuiMCP::backgrounds==2 && ImGuiMCP::texts==2);
    assert(complete() && !complete() && !SKSEMenuFramework::block(&event));
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
