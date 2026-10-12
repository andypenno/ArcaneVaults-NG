"""Exercise deposit learning with real session, event, queue, and rollback code."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
program = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <ranges>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace std {
    template<class... Args> int make_format_args(Args&...) { return 0; }
    string vformat(const char* text,int) { return text; }
}
namespace logger { template<class... Args> void warn(const char*,Args...) {} }
namespace RE {
using FormID=unsigned;
struct TESSoulGem {};
struct TESBoundObject {
    unsigned id; CategoryMask natural{}; bool gem=false, stable=true;
    unsigned GetFormID() const { return id; }
    const char* GetName() const { return "item"; }
    template<class T> T* As() { return gem?reinterpret_cast<T*>(this):nullptr; }
};
struct TESForm {
    inline static std::map<unsigned,TESBoundObject*> forms;
    template<class T> static T* LookupByID(unsigned id) { return forms.contains(id)?forms[id]:nullptr; }
};
struct TESObjectREFR {
    unsigned id;
    unsigned GetFormID() const { return id; }
    inline static TESObjectREFR* target=nullptr;
    static TESObjectREFR* LookupByHandle(unsigned) { return target; }
};
struct ContainerMenu { static constexpr const char* MENU_NAME="ContainerMenu"; static unsigned GetTargetRefHandle() { return 1; } };
struct UI { bool open=true; static UI* GetSingleton() { static UI ui; return &ui; } bool IsMenuOpen(const char*) { return open; } };
struct SendHUDMessage { inline static int errors=0; static void ShowHUDMessage(const char*) { ++errors; } };
struct TESContainerChangedEvent { unsigned oldContainer,newContainer,baseObj; int itemCount; };
enum class BSEventNotifyControl { kContinue };
template<class T> struct BSTEventSource {};
template<class T> struct BSTEventSink { virtual BSEventNotifyControl ProcessEvent(const T*,BSTEventSource<T>*)=0; };
struct ScriptEventSourceHolder {
    BSTEventSink<TESContainerChangedEvent>* sink=nullptr;
    static ScriptEventSourceHolder* GetSingleton() { static ScriptEventSourceHolder holder; return &holder; }
    void AddEventSink(BSTEventSink<TESContainerChangedEvent>* value) { sink=value; }
    void Send(TESContainerChangedEvent event) { sink->ProcessEvent(&event,nullptr); }
};
}
namespace SKSE {
struct Tasks {
    std::deque<std::function<void()>> queue;
    void AddTask(std::function<void()> task) { queue.push_back(task); }
    void Run() { while(!queue.empty()) { auto f=queue.front();queue.pop_front();f(); } }
};
Tasks* GetTaskInterface() { static Tasks tasks;return &tasks; }
}
struct Settings {
    bool GSC_LearnDepositOverrides=false,fail=false;
    std::unordered_map<unsigned,CategoryMask> overrides,disk;
    static Settings* GetSingleton() { static Settings s;return &s; }
    static std::optional<std::string> MakeFormIdentifier(RE::TESBoundObject* item) { return item->stable?std::optional<std::string>{"plugin|id"}:std::nullopt; }
    const auto& GetUserOverrides() const { return overrides; }
    void SetUserOverride(RE::TESBoundObject* item,CategoryMask mask) { overrides[item->id]=mask; }
    bool RemoveUserOverride(unsigned id) { return overrides.erase(id)!=0; }
    bool SaveUserOverrides() { if(fail)return false;disk=overrides;return true; }
};
struct Utility {
    Container kind=Container::Alchemy;
    static Utility* GetSingleton() { static Utility u;return &u; }
    Container GetContainerKind(unsigned) const { return kind; }
};
namespace AVTranslation { const char* Translate(const char* text) { return text; } }
struct Stores {
    struct MenuOption { std::string text;std::function<void()> action; };
    std::vector<MenuOption> options;int prompts=0;
    static Stores* GetSingleton() { static Stores s;return &s; }
    void ShowDynamicMessageBox(std::string_view,std::vector<MenuOption> value,int cancel) { assert(cancel==0);options=std::move(value);++prompts; }
    void Answer(bool accept) { auto callback=options[accept?1:0].action;options.clear();callback();SKSE::GetTaskInterface()->Run(); }
};
CategoryMask ClassifyItem(RE::TESBoundObject* item) noexcept {
    const auto& overrides=Settings::GetSingleton()->overrides;
    return ExpandCategories(overrides.contains(item->id)?overrides.at(item->id):item->natural);
}
'''
item = (ROOT / "src/ItemClass.cpp").read_text()
program += item[item.index("CategoryMask ToMask("):item.index("CategoryMask ClassifyItem(")]
module = (ROOT / "src/DepositLearning.cpp").read_text()
program += "\n".join(line for line in module.splitlines() if not line.startswith("#include"))
program += r'''
int main() {
    auto* s=Settings::GetSingleton();auto* u=Utility::GetSingleton();auto* menu=Stores::GetSingleton();
    auto* events=RE::ScriptEventSourceHolder::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    RE::TESObjectREFR player{0x14}, bank{0x100};RE::TESObjectREFR::target=&bank;
    RE::TESBoundObject a{1},b{2},gem{3,0,true},dynamic{4,0,false,false},matched{5,ToMask(ItemCategory::Ingredient)};
    for(auto* item:{&a,&b,&gem,&dynamic,&matched}) RE::TESForm::forms[item->id]=item;
    auto send=[&](RE::TESBoundObject& item,int count=1){events->Send({0x14,bank.id,item.id,count});};
    auto open=[&](Container kind){u->kind=kind;DepositLearning::MenuOpened();};
    DepositLearning::Register();open(Container::Alchemy);send(a);tasks->Run();assert(menu->prompts==0);
    s->GSC_LearnDepositOverrides=true;
    for(auto kind:{Container::None,Container::Master,Container::Sort,Container::Ignore,Container::Junk,Container::Trade,Container::Personal,Container::Valuables,Container::Soulgem,Container::FilledSoulgems,Container::EmptySoulgems}) {
        open(kind);send(a);tasks->Run();assert(menu->prompts==0);
    }
    for(auto [name,cat]:categoryNames) assert(ParseCategories(FormatCategories(ToMask(cat)))==ToMask(cat));
    assert(ExpandCategories(ToMask(ItemCategory::Alchemy))==ToMask(ItemCategory::Alchemy));
    assert(HasCategory(ExpandCategories(ToMask(ItemCategory::Restorative)),ItemCategory::Concoction));
    open(Container::Alchemy);send(gem);send(dynamic);send(matched);events->Send({0x22,bank.id,a.id,1});events->Send({0x14,0x99,a.id,1});send(a,0);tasks->Run();assert(menu->prompts==0);
    // The event can arrive before or after the RemoveItem caller records its observed delta.
    send(a,3);DepositLearning::RecordAutomaticTransfer(&player,&bank,&a,3);tasks->Run();assert(menu->prompts==0);
    DepositLearning::RecordAutomaticTransfer(&player,&bank,&a,5);send(a,2);send(a,3);tasks->Run();assert(menu->prompts==0);
    send(a);send(a);send(b);tasks->Run();assert(menu->prompts==1 && menu->options.size()==2);
    menu->Answer(false);assert(menu->prompts==2 && !s->overrides.contains(a.id));menu->Answer(true);
    assert(s->overrides[b.id]==ToMask(ItemCategory::Alchemy) && s->disk==s->overrides);
    send(a);tasks->Run();assert(menu->prompts==2);
    open(Container::Alchemy);send(a);tasks->Run();assert(menu->prompts==3);
    DepositLearning::MenuClosed();menu->Answer(true);assert(!s->overrides.contains(a.id));
    open(Container::Jewelry);s->overrides[a.id]=ToMask(ItemCategory::Book);s->fail=true;send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Book) && RE::SendHUDMessage::errors==1);
    open(Container::Keys);s->overrides.erase(a.id);send(a);tasks->Run();menu->Answer(true);assert(!s->overrides.contains(a.id) && RE::SendHUDMessage::errors==2);
    s->fail=false;open(Container::Jewelry);send(a);tasks->Run();menu->Answer(true);assert(s->overrides[a.id]==ToMask(ItemCategory::Jewelry));
    open(Container::Notes);send(a);DepositLearning::MenuClosed();tasks->Run();assert(menu->options.empty());
    open(Container::Notes);send(a);tasks->Run();auto old=menu->options[1].action;DepositLearning::Reset();
    open(Container::Scroll);send(b);tasks->Run();old();tasks->Run();assert(s->overrides[a.id]==ToMask(ItemCategory::Jewelry));menu->Answer(true);assert(s->overrides[b.id]==ToMask(ItemCategory::Scroll));
    open(Container::Food);send(a);tasks->Run();s->GSC_LearnDepositOverrides=false;menu->Answer(true);assert(s->overrides[a.id]==ToMask(ItemCategory::Jewelry));
}
'''
with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / "learning.cpp"
    binary = Path(tmp) / "learning"
    source.write_text(program)
    subprocess.run(["g++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: deposit mismatches, exclusions, broad categories, automatic event counts, queued prompts, decline suppression, persistence rollback, close/load invalidation")
