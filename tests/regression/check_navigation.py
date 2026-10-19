"""Exercise actual message-box navigation, exit, and container-close handling."""

from pathlib import Path
import re
import argparse
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--probe-return", type=Path, help="Record production and direct-menu Quick Transfer returns with a simulated clock")
args = parser.parse_args()
translations = json.loads((ROOT / "ini/ArcaneVaultTranslation.json").read_text())
for key, label in {"Vault.StoreAll": "Store All", "Vault.WithdrawAll": "Withdraw All"}.items():
    assert [name for name, text in translations.items() if text == label] == [key]
program = r'''
#include <cassert>
#include <algorithm>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>
namespace RE {
struct TESObjectREFR;
struct ObjectRefHandle {
    TESObjectREFR* object = nullptr;
    struct Pointer {
        TESObjectREFR* object;
        explicit operator bool() const { return object != nullptr; }
        TESObjectREFR* get() const { return object; }
        TESObjectREFR* operator->() const { return object; }
    };
    Pointer get() const;
    std::uintptr_t native_handle() const { return reinterpret_cast<std::uintptr_t>(object); }
};
struct TESObjectREFR {
    bool alive = true, open = true;
    unsigned id;
    unsigned GetFormID() const { return id; }
    ObjectRefHandle GetHandle() { return {this}; }
};
ObjectRefHandle::Pointer ObjectRefHandle::get() const { return {object && object->alive ? object : nullptr}; }
struct PlayerCharacter {
    static PlayerCharacter* GetSingleton() { static PlayerCharacter p; return &p; }
    bool IsSneaking() const { return false; }
};
struct BGSOpenCloseForm {
    enum class OPEN_STATE { kClosed, kClosing, kOpen, kOpening };
    static OPEN_STATE GetOpenState(TESObjectREFR* source) { return source->open ? OPEN_STATE::kOpen : OPEN_STATE::kClosed; }
    static void SetOpenState(TESObjectREFR* source, bool open, bool) { source->open = open; }
};
struct IMessageBoxCallback { virtual ~IMessageBoxCallback() = default; virtual void Run(std::uint8_t) = 0; };
template<class T> using BSTSmartPointer = std::shared_ptr<T>;
struct MessageBoxData {
    std::string bodyText;
    std::vector<std::string> buttonText;
    BSTSmartPointer<IMessageBoxCallback> callback;
    int warningType, cancelButtonIndex, menuDepth, buttonPressOffset;
    bool useHtml, verticalButtons, isCancellable;
};
std::unique_ptr<MessageBoxData> box;
struct InterfaceStrings {
    int messageBoxData = 0;
    static InterfaceStrings* GetSingleton() { static InterfaceStrings strings; return &strings; }
};
struct MessageDataFactoryManager {
    struct Creator { MessageBoxData* Create() const { return new MessageBoxData; } } creator;
    static MessageDataFactoryManager* GetSingleton() { static MessageDataFactoryManager manager; return &manager; }
    template<class T> const Creator* GetCreator(int) { return &creator; }
};
struct MessageBoxMenu { static void QueueMessage(MessageBoxData* data) { box.reset(data); } };
}
namespace SKSE {
struct Tasks {
    std::vector<std::function<void()>> pending;
    void AddTask(std::function<void()> action) { pending.push_back(std::move(action)); }
    void Flush() {
        while (!pending.empty()) {
            auto actions = std::move(pending); pending.clear();
            for (auto& action : actions) action();
        }
    }
};
Tasks* GetTaskInterface() { static Tasks tasks; return &tasks; }
}
const char* Translate(const char* key) { return key; }
enum class Container { QuickTransfer, Trade, Master, Sort, Armor, Weapon, HeavyArmor, LightArmor, Clothing, Jewelry, Archery, OneHand, TwoHand, Staff };
'''
header = (ROOT / "src/Stores.h").read_text()
program += header[header.index("using MenuAction"):header.index("class Stores {")]
program += r'''
struct Stores {
    RE::ObjectRefHandle navigationSource_;
    MenuAction returnToVault_;
    using AnimationCallback = std::function<void(RE::TESObjectREFR*)>;
    static Stores* GetSingleton() { static Stores stores; return &stores; }

    bool archiveCleaned = false;
    std::vector<std::pair<Container,Container>> returned;
    Container opened=Container::Sort;MenuAction onClose;int revisited=0;
    void AllToStore(Container child,Container parent){returned.emplace_back(child,parent);}
    void OpenStorageMenu(Container kind,RE::TESObjectREFR* source,AnimationCallback callback){opened=kind;onClose=[source,callback]{callback(source);};}
    void ArmorMenu(RE::TESObjectREFR*){++revisited;}
    void WeaponMenu(RE::TESObjectREFR*){++revisited;}
    void TestOpenArmor(RE::TESObjectREFR*);
    void TestOpenWeapon(RE::TESObjectREFR*);
    void ResetNavigation();
    void ShowDynamicMessageBox(std::string_view, std::vector<MenuOption>, std::int32_t = -1);
    void CloseStoreObject(RE::TESObjectREFR*, AnimationCallback = {});
    void PersonalMenu(RE::TESObjectREFR* source) { CloseStoreObject(source); archiveCleaned = true; }
    void IgnoreMenu(RE::TESObjectREFR*) {}
    void GearMenu(RE::TESObjectREFR* source) { PersonalMenu(source); }
    void JunkMenu(RE::TESObjectREFR* source) { PersonalMenu(source); }
    void TradeMenu(RE::TESObjectREFR* source) {
        ShowDynamicMessageBox("Trade", {{"Vault.OpenContainer", [] {}}, {"Vault.Exit", [this, source] { CloseStoreObject(source); }}}, 1);
    }
};
void WaitForOpenState(RE::TESObjectREFR* source, RE::BGSOpenCloseForm::OPEN_STATE, Stores::AnimationCallback action) {
    if (action) action(source);
}
struct Utility {
    struct Entry { RE::TESObjectREFR* container; std::function<void(RE::TESObjectREFR*)> action; };
    std::map<Container, Entry> containerMap;
    bool RunContainerAction(const RE::TESObjectREFR*, RE::TESObjectREFR*) const;
};
'''
source = (ROOT / "src/Stores.cpp").read_text()
open_keys={"Vault.Open","Vault.OpenContainer","Vault.KeysOpen","Vault.AmmunitionOpen","Vault.SoulgemsOpen","Vault.ValuablesOpen","Stolen.Open"}
storage_menus=[]
for match in re.finditer(r'void Stores::(\w+)\(',source):
    block=source[match.start():source.index('\n}',match.start())+2]
    if match.group(1).startswith("ShowVault") or match.group(1)=="VaultAssignment": continue
    if 'ShowDynamicMessageBox(' in block and 'std::vector<MenuOption> options' in block and ('Translate("Vault.Vault")' in block or 'Translate("Vault.Archive")' in block):
        keys=set(re.findall(r'options\.push_back\(\{Translate\("([^"]+)"\)',block))
        assert keys & open_keys,match.group(1)
        storage_menus.append(match.group(1))
assert {"ShowArmorMenu","ShowWeaponMenu","ShowTradeMenu","ShowGearMenu"}<=set(storage_menus)
for kind in ("Armor","Weapon"):
    start=source.index(f"void Stores::Show{kind}Menu(")
    begin=source.index('    options.push_back({Translate("Vault.Open")',start)
    end=source.index('\n    }});',begin)+len('\n    }});')
    program+=f'void Stores::TestOpen{kind}(RE::TESObjectREFR* a_source) {{const auto sourceHandle=a_source->GetHandle();std::vector<MenuOption> options;\n'
    program+=source[begin:end]+'\noptions.front().action();}\n'
for name in ["ResetNavigation", "ShowDynamicMessageBox", "CloseStoreObject"]:
    start = source.index(f"void Stores::{name}(")
    program += source[start:source.index("\n}\n", start) + 3]
utility = (ROOT / "src/Utility.cpp").read_text()
start = utility.index("bool Utility::RunContainerAction(")
program += utility[start:utility.index("\n}\n", start) + 3]
program += r'''
int main() {
    auto* stores = Stores::GetSingleton();
    RE::TESObjectREFR root{true, true, 1}, direct{true, true, 2}, bank{true, true, 3};
    auto click = [](int index) { auto callback = RE::box->callback; callback->Run(index); SKSE::GetTaskInterface()->Flush(); };
    stores->TradeMenu(&direct);
    assert(RE::box->buttonText.size() == 2 && RE::box->cancelButtonIndex == 1);
    click(1); assert(!direct.open && !stores->returnToVault_);
    int returnedToList=0;
    auto browse=[&]{root.open=true;stores->navigationSource_=root.GetHandle();stores->returnToVault_=[&]{++returnedToList;};};
    browse();stores->TradeMenu(&root);
    assert(RE::box->buttonText.size()==3 && RE::box->buttonText[1]=="Vault.Back" && RE::box->buttonText[2]=="Vault.Exit");
    click(1);assert(returnedToList==1 && stores->returnToVault_);
    stores->PersonalMenu(&root);SKSE::GetTaskInterface()->Flush();
    assert(stores->archiveCleaned && root.open && returnedToList==2);
    stores->ShowDynamicMessageBox("Confirm", {{"Cancel", [] {}}, {"Sell All", [] {}}}, 0);
    assert(RE::box->buttonText.size()==2 && RE::box->cancelButtonIndex==0);
    click(0);assert(stores->returnToVault_);
    stores->TradeMenu(&root);click(2);assert(!root.open && !stores->returnToVault_);
    browse();const int before=returnedToList;
    stores->CloseStoreObject(&root);stores->ResetNavigation();SKSE::GetTaskInterface()->Flush();
    assert(returnedToList==before && !stores->returnToVault_);
    browse();root.alive=false;stores->CloseStoreObject(&root);SKSE::GetTaskInterface()->Flush();
    assert(returnedToList==before);
    root.alive=true;browse();
    Utility utility;
    utility.containerMap[Container::Trade] = {&bank, [stores](RE::TESObjectREFR* source) { stores->TradeMenu(source); }};
    assert(utility.RunContainerAction(&bank, &direct));
    assert(!stores->returnToVault_ && RE::box->buttonText.size() == 2);
    assert(!utility.RunContainerAction(nullptr, &direct));
    click(1); assert(!direct.open);

    for (const char* open : {"Vault.Open", "Vault.OpenContainer", "Vault.KeysOpen", "Vault.AmmunitionOpen",
                             "Vault.SoulgemsOpen", "Vault.ValuablesOpen", "Stolen.Open"}) {
        for (bool contextual : {false,true}) {
            int selected=-1,back=0;
            stores->returnToVault_=contextual?MenuAction{[&]{++back;}}:MenuAction{};
            stores->ShowDynamicMessageBox("Storage", {{"First",[&]{selected=1;}}, {"Vault.Exit",[&]{selected=4;}},
                {"Second",[&]{selected=2;}}, {open,[&]{selected=0;}}},1);
            const std::vector<std::string> expected=contextual?std::vector<std::string>{open,"First","Second","Vault.Back","Vault.Exit"}:
                std::vector<std::string>{open,"First","Second","Vault.Exit"};
            assert(RE::box->buttonText==expected && RE::box->cancelButtonIndex==static_cast<int>(expected.size()-1));
            click(0);assert(selected==0);click(1);assert(selected==1);click(2);assert(selected==2);
            if(contextual){click(3);assert(back==1 && stores->returnToVault_);}
            click(RE::box->cancelButtonIndex);assert(selected==4 && !stores->returnToVault_);
        }
    }

    stores->returnToVault_=[]{};
    for(const auto* keep:{"Vault.KeepAmount 25","Vault.KeepOne","Vault.KeepThree"}){
        stores->ShowDynamicMessageBox("Quantities",{{"Vault.StoreAll",[]{}},{keep,[]{}},{"Vault.Exit",[]{}},
            {"Vault.TakeUpToAmount 25",[]{}},{"Vault.Open",[]{}},{"Vault.WithdrawAll",[]{}}},2);
        assert((RE::box->buttonText==std::vector<std::string>{"Vault.Open","Vault.TakeUpToAmount 25","Vault.WithdrawAll",keep,"Vault.StoreAll","Vault.Back","Vault.Exit"}));
        assert(RE::box->cancelButtonIndex==6);
    }
    stores->ResetNavigation();
    stores->ShowDynamicMessageBox("No escape", {{"Vault.Exit",[]{}},{"Vault.Open",[]{}}},-1);
    assert(!RE::box->isCancellable && RE::box->cancelButtonIndex==-1 && RE::box->buttonText.front()=="Vault.Open");
    stores->returned.clear();stores->TestOpenArmor(&direct);
    assert(stores->opened==Container::Armor && stores->returned.size()==4);
    for(const auto& pair:stores->returned)assert(pair.second==Container::Armor);
    stores->onClose();assert(stores->revisited==1);
    stores->returned.clear();stores->TestOpenWeapon(&direct);
    assert(stores->opened==Container::Weapon && stores->returned.size()==4);
    for(const auto& pair:stores->returned)assert(pair.second==Container::Weapon);
    stores->onClose();assert(stores->revisited==2);
}
'''
if args.probe_return:
    if args.probe_return.exists():
        parser.error("Choose a new report path")
    program = program[:program.index("int main() {")]
    program = program.replace("#include <cassert>", "#include <cassert>\n#include <chrono>\n#include <deque>\n#include <iostream>")
    program = program.replace("namespace RE {", r'''
struct ProbeClock {
    inline static std::chrono::steady_clock::time_point tick{};
    using time_point=std::chrono::steady_clock::time_point;
    static time_point now(){return tick;}
};
std::deque<std::function<void()>> timers;
struct TestThread {
    template<class F> explicit TestThread(F action){timers.emplace_back(std::move(action));}
    void detach(){}
};
namespace logger {template<class... T> void warn(const char*,T...) {}}
namespace PlayerEquipment {
    void Run(std::function<void()> work,std::function<void()> complete){work();if(complete)complete();}
}
namespace std {template<class... T> string format(const char*,T...){return "Vault";}}
namespace RE {''', 1)
    program = program.replace("bool alive = true, open = true;", "bool alive = true, open = true;int state=2,animation=0;")
    program = program.replace("return source->open ? OPEN_STATE::kOpen : OPEN_STATE::kClosed;", "return static_cast<OPEN_STATE>(source->state);")
    program = program.replace("source->open = open;", "source->open=open;source->state=open?(source->animation==0?2:3):0;")
    program = program.replace("    bool archiveCleaned = false;", r'''
    int transfers{};
    void OffloadItems(std::function<void()> complete={});
    void OffloadItemsNow(std::function<void()> complete={}){++transfers;if(complete)complete();}
    void VaultMenu(RE::TESObjectREFR*);
    void ShowVaultMenu(RE::TESObjectREFR*);
    void ShowVaultsMenu(RE::TESObjectREFR*){}
    void ShowVaultArchivesMenu(RE::TESObjectREFR*){}
    void SortItems(){}
    void OpenStoreObject(RE::TESObjectREFR*,AnimationCallback);
    bool archiveCleaned = false;''')
    start = program.index("void WaitForOpenState(")
    end = program.index("struct Utility {", start)
    animation = source[source.index("    using OpenState ="):source.index("\n}\n\nusing AVTranslation")]
    animation = animation.replace("std::chrono::steady_clock", "ProbeClock").replace("std::thread(", "TestThread(")
    animation = animation.replace("std::this_thread::sleep_for(std::chrono::milliseconds(16));", "")
    program = program[:start] + animation + program[end:]
    for name in ("OffloadItems", "VaultMenu", "OpenStoreObject", "ShowVaultMenu"):
        start = source.index(f"void Stores::{name}(")
        end = source.index("\n}",start)+2
        program += source[start:end]
    program += r'''
int main(){
    for(int state:{2,3,0,1,-1})for(int animation:{0,1,2}){
        ProbeClock::tick={};timers.clear();RE::box.reset();
        RE::TESObjectREFR chest;chest.id=99;chest.state=state;chest.animation=animation;
        auto* stores=Stores::GetSingleton();stores->ResetNavigation();stores->transfers=0;
        stores->ShowVaultMenu(&chest);
        auto selected=std::ranges::find(RE::box->buttonText,std::string("Vault.ArcaneOffload"));
        assert(selected!=RE::box->buttonText.end());
        auto callback=RE::box->callback;const auto index=selected-RE::box->buttonText.begin();RE::box.reset();
        callback->Run(static_cast<std::uint8_t>(index));SKSE::GetTaskInterface()->Flush();
        int elapsed=0;
        while(!RE::box && elapsed<6000){
            elapsed+=16;ProbeClock::tick+=std::chrono::milliseconds(16);
            if(animation==1 && elapsed>=32)chest.state=2;
            auto ready=std::move(timers);timers.clear();for(auto& timer:ready)timer();
            SKSE::GetTaskInterface()->Flush();
        }
        assert(RE::box && stores->transfers==1);
        std::cout<<"{\"state\":"<<state<<",\"animation\":"<<animation<<",\"return_ms\":"<<elapsed
            <<",\"prompt\":"<<(elapsed<=100?"true":"false")<<"}\n";
    }
}
'''
    program = program.replace("#include <vector>", "#include <vector>\n#include <ranges>")
    results={}
    assert sum(program.count(f"if (auto source = sourceHandle.get()) {name}(source.get());") for name in ("VaultMenu","ShowVaultMenu"))==1
    with tempfile.TemporaryDirectory(prefix="arcanevault-return-probe-") as directory:
        path=Path(directory)
        for variant in ("production","direct_menu_control"):
            candidate=program if variant=="production" else program.replace("if (auto source = sourceHandle.get()) VaultMenu(source.get());","if (auto source = sourceHandle.get()) ShowVaultMenu(source.get());")
            (path/"check.cpp").write_text(candidate)
            subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",str(path/"check.cpp"),"-o",str(path/"check")],check=True,timeout=90)
            results[variant]=[json.loads(line) for line in subprocess.check_output([str(path/"check")],text=True,timeout=15).splitlines()]
    args.probe_return.parent.mkdir(parents=True,exist_ok=True)
    args.probe_return.write_text(json.dumps({"boundary":"Production callback, menu builder and animation polling. Equipment completion is immediate in both variants. Times are simulated, not Skyrim measurements.","cases":results},indent=2)+"\n")
    assert all(case["prompt"] for case in results["direct_menu_control"])
    failures=sum(not case["prompt"] for case in results["production"])
    print(f"Quick Transfer return probe: {failures} slow production cases; report {args.probe_return}")
    raise SystemExit(1 if failures else 0)

with tempfile.TemporaryDirectory(prefix="arcanevault-navigation-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", str(path / "check.cpp"),
                    "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: all storage Open aliases, stable action order, Back before Exit, cancel mapping, confirmations, direct bindings and navigation lifetime")
