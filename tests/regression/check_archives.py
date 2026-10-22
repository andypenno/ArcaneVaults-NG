"""Exercise registered archive browsing and selection without redirect assignment."""

from pathlib import Path
import re
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def body(file, signature):
    source = (ROOT / file).read_text()
    start = source.index(signature)
    return source[start:source.index("\n}", start) + 2]


registry = body("src/Utility.cpp", "void Utility::LoadContainers(")
program = r'''
#include <algorithm>
#include <cassert>
#include <deque>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace std {
string format(const char*, const char* label) { return "[" + string(label) + "]"; }
string format(const char*, const char* a, const char* b) { return string(a)+" "+b; }
}
namespace RE {
using FormID = unsigned;
struct TESObjectREFR;
struct ObjectRefHandle {
    TESObjectREFR* ref;
    std::shared_ptr<TESObjectREFR> get() const;
};
struct TESObjectREFR {
    unsigned id; bool alive = true; std::string name;
    ObjectRefHandle GetHandle() { return {this}; }
    unsigned GetFormID() const { return id; }
    const char* GetDisplayFullName() const { return name.c_str(); }
};
std::shared_ptr<TESObjectREFR> ObjectRefHandle::get() const {
    return ref && ref->alive ? std::shared_ptr<TESObjectREFR>(ref, [](auto*){}) : nullptr;
}
struct TESObjectREFRPtr {
    std::shared_ptr<TESObjectREFR> pointer;
    TESObjectREFRPtr() = default;
    TESObjectREFRPtr(TESObjectREFR* ref) : pointer(ref, [](auto*){}) {}
    TESObjectREFRPtr(std::shared_ptr<TESObjectREFR> ref) : pointer(std::move(ref)) {}
    explicit operator bool() const { return bool(pointer); }
    TESObjectREFR* get() const { return pointer.get(); }
    void reset() { pointer.reset(); }
};
struct TESDataHandler {};
struct TESForm {
    inline static std::map<unsigned, TESObjectREFR*> forms;
    template<class T> static T* LookupByID(unsigned id) { return forms.contains(id) ? forms[id] : nullptr; }
};
enum class UI_MESSAGE_TYPE { kShow };
struct UIMessageQueue {
    int shown = 0;
    static UIMessageQueue* GetSingleton() { static UIMessageQueue q; return &q; }
    void AddMessage(std::string_view, UI_MESSAGE_TYPE, void*) { ++shown; }
};
}
namespace SKSE {
struct Tasks {
    std::deque<std::function<void()>> tasks;
    void AddTask(std::function<void()> task) { tasks.push_back(std::move(task)); }
    void Run() { while (!tasks.empty()) { auto task = tasks.front(); tasks.pop_front(); task(); } }
};
Tasks* GetTaskInterface() { static Tasks tasks; return &tasks; }
}
struct RedirectManager {
    int assignments = 0; RE::TESObjectREFR* destination=nullptr;
    static RedirectManager* GetSingleton() { static RedirectManager r; return &r; }
    bool Add(RE::TESObjectREFR*, RE::TESObjectREFR* target) { ++assignments; destination=target; return true; }
    void Remove(RE::TESObjectREFR*) {}
};
const char* Translate(const char* key) { return key; }
struct MenuOption { std::string text; std::function<void()> action; };
struct Stores {
    RE::ObjectRefHandle navigationSource_{};
    std::function<void()> returnToVault_;
    std::string called;
    bool closed = false;
    std::vector<MenuOption> options;
    void OffloadItems() { called="OffloadItems"; }
    void VaultAssignment(RE::TESObjectREFRPtr);
    void ShowDynamicMessageBox(std::string_view, std::vector<MenuOption> values, std::int32_t) { options=std::move(values); }
    static Stores* GetSingleton() { static Stores s; return &s; }
    void ResetNavigation() { navigationSource_ = {}; returnToVault_ = {}; }
    void CloseStoreObject(RE::TESObjectREFR*) { closed = true; }
    void VaultMenu(RE::TESObjectREFR*) { ResetNavigation(); called = "VaultMenu"; }
    void ShowVaultsMenu(RE::TESObjectREFR*);
    void ShowVaultArchivesMenu(RE::TESObjectREFR*);
    void ShowStorageListMenu(RE::TESObjectREFR*,ContainerGroup);
    void OpenBookArchive(Container archive, Container, ItemCategory, RE::TESObjectREFR*) {
        called = std::string(ContainerTranslationKey(archive));
    }
'''
for method in sorted(set(re.findall(r"Stores::GetSingleton\(\)->(\w+)\(", registry))):
    if method not in {"VaultMenu", "OpenBookArchive", "OffloadItems"}:
        program += f'    void {method}(RE::TESObjectREFR*) {{ called = "{method}"; }}\n'
program += r'''
};
struct Utility {
    struct ContainerChoice { std::string name; unsigned formID = 0; std::function<void()> action{}; };
    struct Entry { RE::TESObjectREFR* container; ContainerGroup a_group; std::function<void(RE::TESObjectREFR*)> action; };
    std::map<Container, Entry> containerMap;
    std::map<Container, RE::TESObjectREFR> references;
    static Utility* GetSingleton() { static Utility u; return &u; }
    void AddContainer(RE::TESDataHandler*, Container kind, unsigned id, ContainerGroup group,
        std::function<void(RE::TESObjectREFR*)> action = {}) {
        auto& ref = references[kind]; ref = {id, true, std::string(ContainerTranslationKey(kind))};
        containerMap[kind] = {&ref, group, std::move(action)};
    }
    RE::TESObjectREFR* GetContainer(Container kind) { auto it=containerMap.find(kind);return it==containerMap.end()?nullptr:it->second.container; }
    void LoadContainers(RE::TESDataHandler*);
    std::vector<ContainerChoice> GetVaultChoices(RE::TESObjectREFR* source = nullptr) const;
    std::vector<ContainerChoice> GetArchiveChoices(RE::TESObjectREFR* source = nullptr) const;
    std::vector<ContainerChoice> GetGroupedChoices(ContainerGroup,RE::TESObjectREFR*) const;
};
'''
header = (ROOT / "src/ContainerMenu.h").read_text()
program += header[header.index("class ContainerSelectionState"):header.index("class ContainerListMenu")]
program += 'struct ContainerListMenu { static constexpr std::string_view MENU_NAME = "List"; };\n'
program += registry
program += body("src/Stores.cpp", "void Stores::VaultAssignment(")
for name in ("GetVaultChoices", "GetArchiveChoices", "GetGroupedChoices"):
    program += body("src/Utility.cpp", "std::vector<Utility::ContainerChoice> Utility::"+name+"(")
for signature in ["ContainerSelectionState* ContainerSelectionState::GetSingleton(",
                  "void ContainerSelectionState::Begin(", "bool ContainerSelectionState::Complete(",
                  "void ContainerSelectionState::Reset("]:
    program += body("src/ContainerMenu.cpp", signature)
for name in ("ShowVaultsMenu", "ShowVaultArchivesMenu", "ShowStorageListMenu"):
    program += body("src/Stores.cpp", "void Stores::"+name+"(")
program += r'''
int main() {
    auto* utility = Utility::GetSingleton(); utility->LoadContainers(nullptr);
    auto* stores = Stores::GetSingleton(); auto* state = ContainerSelectionState::GetSingleton();
    auto* tasks = SKSE::GetTaskInterface();
    auto source = std::make_shared<RE::TESObjectREFR>(RE::TESObjectREFR{100, true, "Root"});
    for(auto group : {ContainerGroup::Vault,ContainerGroup::Archive}) {
        auto assignments = group==ContainerGroup::Vault ? utility->GetVaultChoices() : utility->GetArchiveChoices();
        const auto expected=std::count_if(utility->containerMap.begin(),utility->containerMap.end(),[&](const auto& entry){return entry.second.container && entry.second.a_group==group;});
        assert(assignments.size()==static_cast<std::size_t>(expected));
        if(group==ContainerGroup::Archive)assert(assignments.size()==33);
        auto browse=[&]{if(group==ContainerGroup::Vault)stores->ShowVaultsMenu(source.get());else stores->ShowVaultArchivesMenu(source.get());};
        for (const auto& choice : assignments) assert(!choice.action);
        source->alive=true;stores->closed=false;browse();
        assert(state->GetTitle() == (group==ContainerGroup::Vault ? "Vault.ArcaneVaults" : "Vault.Archives"));
        assert(state->GetChoices().size() == assignments.size() + 2);
        assert(state->GetChoices()[0].name == "[Vault.Back]" && state->GetChoices()[1].name == "[Vault.Exit]");
        for (std::size_t i = 0; i < assignments.size(); ++i) {
            assert(state->GetChoices()[i+2].formID == assignments[i].formID);
            assert(state->GetChoices()[i+2].name == assignments[i].name);
            assert(state->GetChoices()[i+2].action);
            if(i)assert(assignments[i-1].name<=assignments[i].name);
            stores->called.clear();
            assert(state->Complete(static_cast<int>(i+2)));
            assert(stores->called.empty());
            tasks->Run(); assert(!stores->called.empty() && stores->returnToVault_);
            stores->returnToVault_(); assert(state->GetChoices().size() == assignments.size() + 2);
        }
        assert(state->Complete(0)); tasks->Run();
        assert(stores->called == "VaultMenu" && !stores->returnToVault_);
        browse(); assert(state->Complete(1)); tasks->Run();
        assert(stores->closed && !stores->returnToVault_);
        browse(); assert(!state->Complete(-1)); tasks->Run();
        assert(stores->called == "VaultMenu" && !stores->returnToVault_);
        browse(); source->alive = false; stores->called.clear();
        assert(state->Complete(2)); tasks->Run(); assert(stores->called.empty());
    }
    assert(RedirectManager::GetSingleton()->assignments == 0);
    state->Begin(source, {}); assert(state->GetTitle() == "Select destination");
    assert(!state->Complete(-1)); assert(state->GetTitle().empty());
    source->alive = true;
    stores->VaultAssignment(source);
    auto quick=std::ranges::find_if(stores->options,[](const auto& option){return option.text=="Vault.AssignQuickTransfer";});
    assert(quick!=stores->options.end());quick->action();
    auto* redirect=RedirectManager::GetSingleton();auto& quickEntry=utility->containerMap.at(Container::QuickTransfer);
    assert(redirect->destination==quickEntry.container && quickEntry.a_group==ContainerGroup::Special);
    const auto shown=RE::UIMessageQueue::GetSingleton()->shown;stores->closed=false;stores->called.clear();
    quickEntry.action(source.get());assert(stores->called=="OffloadItems" && !stores->closed);
    assert(RE::UIMessageQueue::GetSingleton()->shown==shown);
    const auto assignmentsBefore=redirect->assignments;quickEntry.container=nullptr;
    quick->action();assert(redirect->assignments==assignmentsBefore);
    quickEntry.container=redirect->destination;redirect->assignments=0;
    for (auto& [kind, entry] : utility->containerMap)
        if (entry.container) RE::TESForm::forms[entry.container->id] = entry.container;
    state->Begin(source, utility->GetArchiveChoices());
    assert(state->Complete(0) && RedirectManager::GetSingleton()->assignments == 1);
    assert(state->GetChoices().empty());
    int cancellations = 0;
    state->Begin(source, {}, "Empty", [&]{ ++cancellations; });
    assert(!state->Complete(99) && cancellations == 1);
    utility->containerMap[Container::Crafting].container = nullptr;
    assert(utility->GetArchiveChoices().size() == 32);
}
'''
root_menu = body("src/Stores.cpp", "void Stores::ShowVaultMenu(")
assert 'Translate("Vault.ArcaneArchives")' in root_menu
assert 'ShowVaultsMenu(source.get())' in root_menu
assert 'VaultDetail' not in (ROOT / 'src/Stores.cpp').read_text()
assert json.loads((ROOT / "ini/ArcaneVaultTranslation.json").read_text())["Vault.ArcaneArchives"] == "Open Archives"
with tempfile.TemporaryDirectory(prefix="arcanevault-archive-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: every registered vault and archive, alphabetical lists, deferred handlers, contextual return, Back/Exit/cancel, expired source, and no browse assignments")

name_builder=(ROOT/"src/Utility.cpp").read_text().split("void Utility::AddContainer(",1)[1].split("RE::TESObjectREFR* Utility::GetContainer",1)[0]
assert 'Translate("Vault.Vault")' in name_builder and '"Vault.Archive"' not in name_builder
assert 'Translate("Vault.Archive")' not in (ROOT/"src/Stores.cpp").read_text()
