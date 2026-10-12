"""Exercise actual message-box navigation, exit, and container-close handling."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
program = r'''
#include <cassert>
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
'''
header = (ROOT / "src/Stores.h").read_text()
program += header[header.index("using MenuAction"):header.index("class Stores {")]
program += r'''
struct Stores {
    RE::ObjectRefHandle navigationSource_;
    MenuAction returnToVault_;
    using AnimationCallback = std::function<void(RE::TESObjectREFR*)>;
    static Stores* GetSingleton() { static Stores stores; return &stores; }
    int page3 = 0, page2 = 0;
    bool archiveCleaned = false;
    void ResetNavigation();
    void ShowDynamicMessageBox(std::string_view, std::vector<MenuOption>, std::int32_t = -1);
    void CloseStoreObject(RE::TESObjectREFR*, AnimationCallback = {});
    void ShowVaultDetail3Menu(RE::TESObjectREFR*);
    void VaultDetail3Menu(RE::TESObjectREFR*);
    void VaultDetail2Menu(RE::TESObjectREFR*) { ++page2; }
    void OpenStoreObject(RE::TESObjectREFR* source, AnimationCallback action) { source->open = true; ++page3; action(source); }
    void PersonalMenu(RE::TESObjectREFR* source) { CloseStoreObject(source); archiveCleaned = true; }
    void IgnoreMenu(RE::TESObjectREFR*) {}
    void JunkMenu(RE::TESObjectREFR* source) { PersonalMenu(source); }
    void TradeMenu(RE::TESObjectREFR* source) {
        ShowDynamicMessageBox("Trade", {{"Open", [] {}}, {"Vault.Exit", [this, source] { CloseStoreObject(source); }}}, 1);
    }
};
void WaitForOpenState(RE::TESObjectREFR* source, RE::BGSOpenCloseForm::OPEN_STATE, Stores::AnimationCallback action) {
    if (action) action(source);
}
enum class Container { Trade, Master, Sort };
struct Utility {
    struct Entry { RE::TESObjectREFR* container; std::function<void(RE::TESObjectREFR*)> action; };
    std::map<Container, Entry> containerMap;
    bool RunContainerAction(const RE::TESObjectREFR*, RE::TESObjectREFR*) const;
};
'''
source = (ROOT / "src/Stores.cpp").read_text()
for name in ["ResetNavigation", "ShowDynamicMessageBox", "CloseStoreObject", "ShowVaultDetail3Menu", "VaultDetail3Menu"]:
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
    stores->VaultDetail3Menu(&root);
    assert(RE::box->buttonText.size() == 5 && RE::box->cancelButtonIndex == 4);
    click(2);
    assert(RE::box->buttonText.size() == 3 && RE::box->buttonText[2] == "Vault.Back");
    assert(RE::box->cancelButtonIndex == 1);
    click(2); assert(stores->page3 == 2 && RE::box->buttonText.size() == 5);
    click(1); assert(stores->archiveCleaned && root.open && stores->page3 == 3);
    stores->ShowDynamicMessageBox("Confirm", {{"Cancel", [] {}}, {"Sell All", [] {}}}, 0);
    assert(RE::box->buttonText.size() == 2 && RE::box->cancelButtonIndex == 0);
    click(0); assert(stores->returnToVault_);
    stores->VaultDetail3Menu(&root);
    click(4); assert(!root.open && !stores->returnToVault_);

    stores->VaultDetail3Menu(&root); const int before = stores->page3;
    stores->CloseStoreObject(&root); stores->ResetNavigation(); SKSE::GetTaskInterface()->Flush();
    assert(stores->page3 == before && !stores->returnToVault_);
    stores->VaultDetail3Menu(&root); root.alive = false;
    stores->CloseStoreObject(&root); SKSE::GetTaskInterface()->Flush();
    assert(stores->page3 == before + 1);
    root.alive = true; stores->VaultDetail3Menu(&root);
    Utility utility;
    utility.containerMap[Container::Trade] = {&bank, [stores](RE::TESObjectREFR* source) { stores->TradeMenu(source); }};
    assert(utility.RunContainerAction(&bank, &direct));
    assert(!stores->returnToVault_ && RE::box->buttonText.size() == 2);
    assert(!utility.RunContainerAction(nullptr, &direct));
    click(1); assert(!direct.open);
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-navigation-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", str(path / "check.cpp"),
                    "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: contextual Back, originating page, plain-container return, Exit/cancel indices, confirmations, direct bindings, reset, and expired handles")
