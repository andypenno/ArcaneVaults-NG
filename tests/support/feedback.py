"""Shared UI boundary types for the production sorting controller."""
program = r'''
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>
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
constexpr int ImDrawFlags_Closed=1;
double renderTime=0;
double GetTime(){return renderTime;}
struct Polygon {std::vector<ImVec2> points;unsigned color;};
std::vector<Polygon> fills,outlines;
std::vector<unsigned> lineColors;
ImVec2 textPosition;
void CheckPoint(ImVec2 p){assert(std::isfinite(p.x)&&std::isfinite(p.y)&&p.x>=0&&p.y>=0&&p.x<=io.DisplaySize.x&&p.y<=io.DisplaySize.y);}
IO* GetIO(){return &io;}
DrawList* GetForegroundDrawList(){return &canvas;}
ImVec2 CalcTextSize(const char*){return {140,24};}
namespace ImDrawListManager {
void AddRectFilled(DrawList*,ImVec2 a,ImVec2 b,unsigned color,float,int){
    CheckPoint(a);CheckPoint(b);assert((color>>24)<100);++backgrounds;
}
void AddConvexPolyFilled(DrawList*,const ImVec2* points,int count,unsigned color){
    for(int i=0;i<count;++i)CheckPoint(points[i]);
    fills.push_back({{points,points+count},color});
}
void AddPolyline(DrawList*,const ImVec2* points,int count,unsigned color,int flags,float thickness){
    for(int i=0;i<count;++i)CheckPoint(points[i]);
    assert(flags==ImDrawFlags_Closed&&thickness>0);outlines.push_back({{points,points+count},color});
}
void AddCircle(DrawList*,ImVec2 center,float radius,unsigned,int segments,float thickness){
    CheckPoint({center.x-radius,center.y-radius});CheckPoint({center.x+radius,center.y+radius});
    assert(radius>0&&segments>=12&&thickness>0);
}
void AddLine(DrawList*,ImVec2 a,ImVec2 b,unsigned color,float thickness){
    CheckPoint(a);CheckPoint(b);assert(thickness>0);lineColors.push_back(color);
}
void AddText(DrawList*,ImVec2 position,unsigned,const char* label){
    CheckPoint(position);CheckPoint({position.x+140,position.y+24});
    assert(std::string(label)=="Sorting items...");textPosition=position;++texts;
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
