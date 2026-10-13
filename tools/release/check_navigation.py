"""Exercise actual message-box navigation, exit, and container-close handling."""

from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
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
with tempfile.TemporaryDirectory(prefix="arcanevault-navigation-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", str(path / "check.cpp"),
                    "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: all storage Open aliases, stable action order, Back before Exit, cancel mapping, confirmations, direct bindings and navigation lifetime")
