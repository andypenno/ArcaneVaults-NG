"""Exercise the production sorting overlay lifecycle with deterministic UI/game frames."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
program = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>
#define __stdcall
#include "src/TransferFeedback.h"
struct ProbeClock {
    using time_point=std::chrono::steady_clock::time_point;
    inline static time_point tick{};
    static time_point now(){return tick;}
};
std::deque<std::function<void()>> timers;
struct TestThread {
    template<class F> explicit TestThread(F action){timers.emplace_back(std::move(action));}
    void detach(){}
};
namespace RE {struct InputEvent {bool up=false,button=true;bool IsUp()const{return up;}InputEvent* AsButtonEvent(){return button?this:nullptr;}};}
namespace SKSE {
struct Tasks {
    std::deque<std::function<void()>> queue;
    void AddTask(std::function<void()> action){queue.push_back(std::move(action));}
    void Run(){auto ready=std::move(queue);queue.clear();for(auto& action:ready)action();}
};
Tasks* GetTaskInterface(){static Tasks tasks;return &tasks;}
}
namespace ImGuiMCP {
struct ImVec2 {float x,y;};
struct IO {ImVec2 DisplaySize{1920,1080};} io;
struct DrawList {} canvas;
int backgrounds=0,texts=0;
IO* GetIO(){return &io;}
DrawList* GetForegroundDrawList(){return &canvas;}
ImVec2 CalcTextSize(const char*){return {140,24};}
namespace ImDrawListManager {
void AddRectFilled(DrawList*,ImVec2,ImVec2,unsigned,float,int){++backgrounds;}
void AddText(DrawList*,ImVec2 position,unsigned,const char* label){
    assert(position.x>0 && position.y>0 && std::string(label)=="Sorting items...");++texts;
}
}
}
namespace SKSEMenuFramework {
bool installed=false;
void (*render)()=nullptr;
bool (*block)(RE::InputEvent*)=nullptr;
int registrations=0;
namespace Model {struct HudElement {};struct InputEvent {};}
bool IsInstalled(){return installed;}
Model::HudElement* AddHudElement(void (*callback)()){render=callback;++registrations;return new Model::HudElement;}
Model::InputEvent* AddInputEvent(bool (*callback)(RE::InputEvent*)){block=callback;return new Model::InputEvent;}
}
namespace AVTranslation {const char* Translate(const char*){return "Sorting items...";}}
'''
FRAMEWORK = program[program.index("namespace ImGuiMCP {"):]
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
    Begin([&](Complete done){++starts;ProbeClock::tick+=5ms;Mark(Stage::Recovery);ProbeClock::tick+=3ms;assert(done());});
    auto report=LastReport();assert(starts==1 && report.complete && report.total==8);
    assert(report.milliseconds[static_cast<unsigned>(Stage::Inspection)]==5 && report.milliseconds[static_cast<unsigned>(Stage::Recovery)]==3);
    assert(timers.empty() && !SKSEMenuFramework::render);
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
    ProbeClock::tick+=7ms;Mark(Stage::Transfer);ProbeClock::tick+=11ms;
    assert(complete() && !complete() && !SKSEMenuFramework::block(&event));
    report=LastReport();double sum=0;for(auto value:report.milliseconds)sum+=value;
    assert(report.complete && report.total==50 && sum==report.total && report.milliseconds[0]==32);
    const int priorDraws=ImGuiMCP::texts;SKSEMenuFramework::render();assert(ImGuiMCP::texts==priorDraws);

    for(bool invalidSize:{false,true}){
        Reset();ImGuiMCP::io.DisplaySize=invalidSize?ImGuiMCP::ImVec2{}:ImGuiMCP::ImVec2{1920,1080};
        const int before=starts;Begin([&](Complete done){++starts;complete=std::move(done);});
        for(int frame=0;starts==before && frame<20;++frame){if(invalidSize)SKSEMenuFramework::render();step();}
        assert(starts==before+1 && LastReport().complete==false && complete());
        report=LastReport();assert(report.milliseconds[0]>=250 && report.milliseconds[0]<273);
        assert(!SKSEMenuFramework::block(&event));
    }
    ImGuiMCP::io.DisplaySize={1920,1080};
    Reset();const int beforeCancel=starts;Begin([&](Complete){++starts;});Reset();step();
    assert(starts==beforeCancel && !SKSEMenuFramework::block(&event) && !LastReport().complete);

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
    assert(caught && !SKSEMenuFramework::block(&event) && !LastReport().complete);
    Begin({});SKSEMenuFramework::render();step();SKSEMenuFramework::render();step();
    assert(LastReport().complete && !SKSEMenuFramework::block(&event));
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
    print("PASS: rendered-frame barrier, button blocking with releases preserved, completion, overlap, absent/stalled renderer, reset, stale callbacks, failures and memory-only timings")


if __name__ == "__main__":
    main()
