"""Exercise deposit learning with real session, event, queue, and rollback code."""
from pathlib import Path
import json
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
    bool GSC_LearnDepositOverrides=false,GSC_AllowAutomaticLearning=false,fail=false;
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
program += item[item.index("CategoryMask ToMask("):item.index("namespace {\n    CategoryMask PotionAttribute(")]
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
    for(auto kind:{Container::None,Container::Master,Container::Sort,Container::Ignore,Container::Trade,Container::Valuables,Container::FilledSoulgems,Container::EmptySoulgems,Container::StolenItems,Container::EnchantedItems}) {
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
    s->GSC_LearnDepositOverrides=true;
    open(Container::Personal);send(a);tasks->Run();menu->Answer(false);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Jewelry));
    open(Container::Personal);send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Personal) && s->disk==s->overrides);
    assert(ClassifyItem(&a)==ToMask(ItemCategory::Personal));
    s->overrides.clear();s->overrides=s->disk;
    assert(ClassifyItem(&a)==ToMask(ItemCategory::Personal));
    const auto prompts=menu->prompts;
    open(Container::Personal);send(a);send(gem);send(dynamic);tasks->Run();assert(menu->prompts==prompts);
    s->RemoveUserOverride(a.id);assert(ClassifyItem(&a)==a.natural);
    open(Container::Gear);send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Gear) && s->disk==s->overrides);
    open(Container::Instruments);send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Instrument) && s->disk==s->overrides);
    assert(ClassifyItem(&a)==(ItemCategory::Gear|ItemCategory::Instrument));
    open(Container::Remains);send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Remains) && s->disk==s->overrides);
    assert(ClassifyItem(&a)==(ItemCategory::Remains|ItemCategory::Smithing));
    s->RemoveUserOverride(a.id);assert(ClassifyItem(&a)==a.natural);
    s->overrides[a.id]=ToMask(ItemCategory::Instrument);
    const auto gearPrompts=menu->prompts;
    open(Container::Gear);send(a);send(gem);send(dynamic);tasks->Run();assert(menu->prompts==gearPrompts);
    for(auto [kind,cat]:std::array{std::pair{Container::HealthPotions,ItemCategory::HealthPotion},
        std::pair{Container::MagickaPotions,ItemCategory::MagickaPotion},std::pair{Container::StaminaPotions,ItemCategory::StaminaPotion}}) {
        open(kind);send(a);tasks->Run();menu->Answer(true);
        assert(s->overrides[a.id]==ToMask(cat) && s->disk==s->overrides);
        assert(ClassifyItem(&a)==(cat|ItemCategory::Potion|ItemCategory::Concoction));
        const auto previous=menu->prompts;open(kind);send(a);tasks->Run();assert(menu->prompts==previous);
    }



    open(Container::Soulgem);send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Soulgem) && s->disk==s->overrides);
    const auto soulPrompts=menu->prompts;send(gem);tasks->Run();assert(menu->prompts==soulPrompts);

    open(Container::Junk);send(a);tasks->Run();menu->Answer(true);
    assert(s->overrides[a.id]==ToMask(ItemCategory::Junk) && s->disk==s->overrides);

    s->GSC_AllowAutomaticLearning=true;
    const auto automaticPrompts=menu->prompts;
    for(bool enabled:{false,true}) {
        s->GSC_LearnDepositOverrides=enabled;s->overrides.clear();s->disk.clear();
        open(Container::Alchemy);
        send(gem);send(dynamic);send(matched);send(a,0);
        events->Send({0x14,bank.id,999,1});
        events->Send({0x22,bank.id,a.id,1});events->Send({0x14,0x99,a.id,1});
        send(a,3);DepositLearning::RecordAutomaticTransfer(&player,&bank,&a,3);
        tasks->Run();assert(s->overrides.empty() && menu->prompts==automaticPrompts);
        send(a);send(a);send(b);tasks->Run();
        assert(menu->prompts==automaticPrompts && menu->options.empty());
        if(enabled) assert(s->overrides[a.id]==ToMask(ItemCategory::Alchemy) && s->overrides[b.id]==ToMask(ItemCategory::Alchemy) && s->disk==s->overrides);
        else assert(s->overrides.empty() && s->disk.empty());
    }
    for(auto kind:{Container::None,Container::Master,Container::Sort,Container::Ignore,Container::Trade,Container::Valuables,Container::FilledSoulgems,Container::EmptySoulgems,Container::StolenItems,Container::EnchantedItems}) {
        s->overrides.clear();s->disk.clear();open(kind);send(a);tasks->Run();
        assert(s->overrides.empty() && menu->prompts==automaticPrompts);
    }
    s->overrides[a.id]=ToMask(ItemCategory::Book);s->disk=s->overrides;s->fail=true;
    const auto errors=RE::SendHUDMessage::errors;
    open(Container::Remains);send(a);send(a);send(b);send(b);tasks->Run();
    assert(s->overrides.at(a.id)==ToMask(ItemCategory::Book) && !s->overrides.contains(b.id));
    assert(s->disk==s->overrides && RE::SendHUDMessage::errors==errors+2 && menu->prompts==automaticPrompts);
    s->fail=false;open(Container::Keys);send(a);DepositLearning::MenuClosed();tasks->Run();
    assert(s->overrides.at(a.id)==ToMask(ItemCategory::Book));
    open(Container::Keys);send(a);DepositLearning::Reset();tasks->Run();
    assert(s->overrides.at(a.id)==ToMask(ItemCategory::Book));
    open(Container::Keys);send(a);RE::TESObjectREFR::target=&player;tasks->Run();
    assert(s->overrides.at(a.id)==ToMask(ItemCategory::Book));RE::TESObjectREFR::target=&bank;
    open(Container::Keys);send(a);s->GSC_LearnDepositOverrides=false;tasks->Run();
    assert(s->overrides.at(a.id)==ToMask(ItemCategory::Book));
    s->GSC_LearnDepositOverrides=true;s->GSC_AllowAutomaticLearning=false;
    open(Container::Keys);send(a);send(b);tasks->Run();assert(menu->prompts==automaticPrompts+1);
    s->GSC_AllowAutomaticLearning=true;menu->Answer(false);
    assert(s->overrides.at(a.id)==ToMask(ItemCategory::Book) && s->overrides.at(b.id)==ToMask(ItemCategory::Keys));
    assert(menu->prompts==automaticPrompts+1 && menu->options.empty() && s->disk==s->overrides);

}
'''
with tempfile.TemporaryDirectory() as tmp:
    source = Path(tmp) / "learning.cpp"
    binary = Path(tmp) / "learning"
    source.write_text(program)
    subprocess.run(["g++", "-std=c++23", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: deposit mismatches, exclusions, broad categories, automatic event counts, queued prompts, decline suppression, persistence rollback, close/load invalidation")

prompt = json.loads((ROOT / "ini/ArcaneVaultTranslation.json").read_text())["Learning.Confirm"]
rendered = prompt.format("Test item", "Personal")
assert "Test item" in rendered and "Personal" in rendered and "SKSE Overrides" in rendered
