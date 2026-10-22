"""Exercise ignore persistence, picker lifecycle, activation, and management UI."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def body(file, signature, end="\n}"):
    text = (ROOT / file).read_text()
    start = text.index(signature)
    return text[start:text.index(end, start) + len(end)]


program = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <charconv>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
using FormID = unsigned;
struct TESBoundObject {
    unsigned id; std::string plugin, name; bool dynamic = false;
    unsigned GetFormID() const { return id; }
    const char* GetName() const { return name.c_str(); }
};
struct TESForm { TESBoundObject* item; template<class T> T* As() { return item; } };
struct TESDataHandler {
    std::map<std::pair<std::string,unsigned>,TESForm> forms;
    static TESDataHandler* GetSingleton() { static TESDataHandler d; return &d; }
    TESForm* LookupForm(unsigned id, std::string_view plugin) {
        auto it=forms.find({std::string(plugin),id}); return it==forms.end()?nullptr:&it->second;
    }
};
struct TESObjectREFR;
struct Handle { TESObjectREFR* object; struct Ptr { TESObjectREFR* object; operator bool() const { return object!=nullptr; } TESObjectREFR* get() const { return object; } }; Ptr get() const; };
struct TESObjectREFR {
    unsigned id{}; bool alive=true, activate=true, closed=false;
    explicit TESObjectREFR(unsigned value=0):id(value) {}
    std::map<TESBoundObject*,std::pair<int,int>> inventory;
    unsigned GetFormID() const { return id; }
    Handle GetHandle() { return {this}; }
    auto GetInventory() const { return inventory; }
    std::map<TESBoundObject*,int> GetInventoryCounts() const { std::map<TESBoundObject*,int> out; for(auto [item,data]:inventory) out[item]=data.first; return out; }
    bool ActivateRef(TESObjectREFR*,int,void*,int,bool) { return activate; }
};
Handle::Ptr Handle::get() const { return {object && object->alive?object:nullptr}; }
struct PlayerCharacter : TESObjectREFR {
    bool sneak=false;
    bool IsSneaking() const { return sneak; }
    static PlayerCharacter* GetSingleton() { static PlayerCharacter p; return &p; }
};
struct SendHUDMessage { inline static std::string message; static void ShowHUDMessage(const char* text) { message=text; } };
}
struct CSimpleIniA {
    struct Key { const char* pItem; }; using TKeyVal=std::vector<std::pair<Key,const char*>>;
    inline static std::map<std::string,std::map<std::string,std::string>> disk;
    inline static bool fail=false;
    decltype(disk) data; TKeyVal entries;
    void SetUnicode() {} void LoadFile(const wchar_t*) { data=disk; }
    const TKeyVal* GetSection(const char* section) { entries.clear(); for(const auto& [key,value]:data[section]) entries.push_back({{key.c_str()},value.c_str()}); return &entries; }
    void Delete(const char* section,void*) { data.erase(section); }
    void SetValue(const char* section,const char* key,const char* value) { data[section][key]=value; }
    int SaveFile(const wchar_t*) { if(fail)return -1; disk=data; return 0; }
};
namespace logger { void error(const char*) {} }
struct Settings {
    std::unordered_set<std::string> ignoredItems_;
    static constexpr const wchar_t* ignore_path=L"ignore.ini";
    static Settings* GetSingleton() { static Settings s; return &s; }
    static std::optional<std::string> MakeFormIdentifier(const RE::TESBoundObject* item) {
        if(!item || item->dynamic || item->plugin.empty()) return std::nullopt;
        return item->plugin+"|"+std::to_string(item->id);
    }
    static RE::TESBoundObject* ResolveIgnoredItem(std::string_view);
    void LoadIgnoredItems(); bool SaveIgnoredItems() const; bool AddIgnoredItem(RE::TESBoundObject*);
    bool RemoveIgnoredItem(const std::string&); bool IsIgnored(const RE::TESBoundObject*) const;
    const auto& GetIgnoredItems() const { return ignoredItems_; }
};
const char* Translate(const char* key) { return key; }
struct Stores {
    std::uint64_t ignoreSession_{}; int resets=0;
    static Stores* GetSingleton() { static Stores s; return &s; }
    void FinishIgnorePicker(); void IgnoreMenu(RE::TESObjectREFR*);
    void ResetNavigation() { ++resets; }
    void CloseStoreObject(RE::TESObjectREFR* source) { source->closed=true; }
};
struct Utility {
    struct Entry { RE::TESObjectREFR* container; std::function<void(RE::TESObjectREFR*)> action; };
    std::map<Container,Entry> containerMap;
    static Utility* GetSingleton() { static Utility u; return &u; }
    RE::TESObjectREFR* GetContainer(Container c) { auto it=containerMap.find(c); return it==containerMap.end()?nullptr:it->second.container; }
    bool RunContainerAction(const RE::TESObjectREFR*,RE::TESObjectREFR*) const;
};
bool rejectMove=false;
void MoveItems(RE::TESObjectREFR* source,RE::TESObjectREFR* target,RE::TESBoundObject* item,int count) {
    if(rejectMove)return;
    auto& data=source->inventory[item]; target->inventory[item].first+=count; target->inventory[item].second=data.second; data.first-=count;
}
namespace AVEvents {
    std::function<void()> close; RE::TESObjectREFR* target=nullptr;
    void RunAfterContainerMenuCloses(RE::TESObjectREFR* item,std::function<void()> callback) { target=item; close=std::move(callback); }
    void CancelContainerMenuCloseCallback() { close={}; }
}
std::set<std::string> clicks;
std::vector<std::string> shown;
std::vector<std::string> wrapped;
std::string query;
bool Button(const char* key) { return clicks.erase(key)!=0; }
void Text(const char*,const char* text) { shown.emplace_back(text); }
void TextWrapped(const char* format,const char* text) { assert(std::string_view(format)=="%s"); wrapped.emplace_back(text); Text(format,text); }
void InputText(const char*,char* text,std::size_t size) { query.copy(text,size-1); text[query.size()]=0; }
bool BeginTable(const char*,int) { return true; }
void TableSetupColumn(const char*) {} void TableHeadersRow() {} void TableNextRow() {} void TableNextColumn() {}
void PushID(const char*) {} void PopID() {} void EndTable() {} void SameLine() {}
'''
program += body("src/Settings.cpp", "\tstd::optional<std::pair<std::string_view, RE::FormID>> ParseFormIdentifier(", "\n\t}")
for name in ["ResolveIgnoredItem", "LoadIgnoredItems", "SaveIgnoredItems", "AddIgnoredItem", "RemoveIgnoredItem", "IsIgnored"]:
    text = (ROOT / "src/Settings.cpp").read_text()
    start = text.index("Settings::" + name + "(")
    start = text.rfind("\n", 0, start) + 1
    program += text[start:text.index("\n}", start) + 2]
for name in ["FinishIgnorePicker", "IgnoreMenu"]:
    program += body("src/Stores.cpp", "void Stores::" + name + "(")
program += body("src/Utility.cpp", "bool Utility::RunContainerAction(")
program += body("src/AVUI.cpp", "\tvoid __stdcall RenderIgnoredItems()", "\n\t}").replace("__stdcall ", "")
program += r'''
int main() {
    auto* settings=Settings::GetSingleton(); auto* player=RE::PlayerCharacter::GetSingleton();
    RE::TESBoundObject key{1,"Skyrim.esm","Skeleton Key"}, missing{2,"Optional.esl","Optional Item"}, unstable{3,"","Dynamic",true};
    RE::TESDataHandler::GetSingleton()->forms[{"Skyrim.esm",1}]={&key};
    CSimpleIniA::disk={{"IgnoredItems",{{"Skyrim.esm|1","true"},{"Optional.esl|2","true"},{"bad","true"},{"Skyrim.esm|1junk","true"}}},{"Other",{{"keep","yes"}}}};
    settings->LoadIgnoredItems(); assert(settings->GetIgnoredItems().size()==2 && settings->IsIgnored(&key));
    assert(!settings->AddIgnoredItem(&unstable)); assert(settings->AddIgnoredItem(&key));
    assert(settings->SaveIgnoredItems() && CSimpleIniA::disk["IgnoredItems"].contains("Optional.esl|2") && CSimpleIniA::disk["Other"]["keep"]=="yes");
    assert(!Settings::ResolveIgnoredItem("Optional.esl|2")); RE::TESDataHandler::GetSingleton()->forms[{"Optional.esl",2}]={&missing};
    assert(Settings::ResolveIgnoredItem("Optional.esl|2")==&missing && settings->IsIgnored(&missing));
    RE::TESObjectREFR picker{10}, source{11}, master{12}, sorter{13}, trade{14};
    auto* u=Utility::GetSingleton(); auto* stores=Stores::GetSingleton(); int actions=0;
    u->containerMap={{Container::Ignore,{&picker,{}}},{Container::Master,{&master,[&](auto*){++actions;}}},{Container::Sort,{&sorter,[&](auto*){++actions;}}},{Container::Trade,{&trade,[&](auto*){++actions;}}}};
    RE::TESObjectREFR quickTransfer{123};
    u->containerMap[Container::QuickTransfer]={&quickTransfer,[&](auto*){++actions;}};
    player->sneak=false;assert(u->RunContainerAction(&quickTransfer,&source) && actions==1);
    player->sneak=true;assert(u->RunContainerAction(&quickTransfer,&source) && actions==1 && AVEvents::target==&picker);
    auto quickClose=AVEvents::close;quickClose();actions=0;
    player->sneak=false; assert(u->RunContainerAction(&master,&source) && actions==1);
    player->sneak=true; assert(u->RunContainerAction(&master,&source) && actions==1 && AVEvents::target==&picker);
    picker.inventory[&key]={25000,42}; auto close=AVEvents::close; close();
    assert(picker.inventory[&key].first==0 && player->inventory[&key].first==25000 && player->inventory[&key].second==42 && source.closed);
    assert(u->RunContainerAction(&sorter,&source) && actions==1);
    auto stale=AVEvents::close; ++stores->ignoreSession_; picker.inventory[&missing]={1,84}; stale(); assert(picker.inventory[&missing].first==1);
    stores->FinishIgnorePicker(); assert(picker.inventory[&missing].first==0 && player->inventory[&missing].second==84);
    assert(u->RunContainerAction(&trade,&source) && actions==2);
    picker.activate=false; stores->IgnoreMenu(&source); assert(!AVEvents::close); picker.activate=true;
    picker.inventory[&key]={2,42}; rejectMove=true; stores->IgnoreMenu(&source); assert(!AVEvents::close && picker.inventory[&key].first==2); rejectMove=false; stores->FinishIgnorePicker();
    CSimpleIniA::fail=true; picker.inventory[&unstable]={1,7}; stores->FinishIgnorePicker();
    assert(picker.inventory[&unstable].first==0 && !settings->IsIgnored(&unstable)); CSimpleIniA::fail=false;
    query="Skeleton"; RenderIgnoredItems(); assert(std::ranges::find(shown,"Skeleton Key")!=shown.end() && std::ranges::find(shown,"Optional Item")==shown.end());
    assert((wrapped==std::vector<std::string>{"Ignore.Help"}));
    clicks={"Override.ButtonRemove"}; RenderIgnoredItems(); assert(!settings->IsIgnored(&key) && settings->IsIgnored(&missing));
    query=""; clicks={"Ignore.ClearAll"}; RenderIgnoredItems(); assert(settings->IsIgnored(&missing));
    clicks={"Ignore.Cancel"}; RenderIgnoredItems(); assert(settings->IsIgnored(&missing));
    clicks={"Ignore.ClearAll","Ignore.ConfirmClear"}; RenderIgnoredItems(); assert(settings->GetIgnoredItems().empty() && CSimpleIniA::disk["IgnoredItems"].empty());
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-ignore-check-") as directory:
    source = Path(directory) / "check.cpp"
    binary = Path(directory) / "check"
    source.write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: ignore identifier persistence, unresolved plugins, picker return/recovery/failure, sneak activation, search, remove, and confirmed clear")
