#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <map>
#include <string>
#include <string_view>
namespace RE {
struct GString : std::string { using std::string::string; };
struct FxDelegateArgs;
struct UIMessage {};
enum class UI_MESSAGE_RESULTS {kHandled};
struct FxDelegateHandler {
    using CallbackFn = void(const FxDelegateArgs&);
    struct CallbackProcessor { virtual ~CallbackProcessor() = default; virtual void Process(const GString&, CallbackFn*) = 0; };
};
struct InventoryMenu : FxDelegateHandler { inline static std::array<std::uintptr_t, 1> VTABLE{1}; };
struct FxDelegateArgs { FxDelegateHandler* handler; FxDelegateHandler* GetHandler() const { return handler; } };
}
namespace Native {
inline int loads{}, draws{}, actions{}, accepts{};
inline int messages{};
inline std::array<std::uintptr_t, 7> table;
void Load(const RE::FxDelegateArgs&) { ++loads; }
void Action(const RE::FxDelegateArgs&) { ++actions; }
void Accept(RE::InventoryMenu*, RE::FxDelegateHandler::CallbackProcessor* processor) {
    ++accepts; processor->Process(RE::GString{"UpdateItem3D"}, Load); processor->Process(RE::GString{"ItemSelect"}, Action);
}
void Display(RE::InventoryMenu*) { ++draws; }
RE::UI_MESSAGE_RESULTS Process(RE::InventoryMenu*, RE::UIMessage&) { ++messages;return RE::UI_MESSAGE_RESULTS::kHandled; }
}
namespace REL {
template<class T> struct Relocation {
    explicit Relocation(std::uintptr_t) {}
    template<class F> std::uintptr_t write_vfunc(int slot, F replacement) {
        const auto previous = Native::table[slot]; Native::table[slot] = reinterpret_cast<std::uintptr_t>(replacement); return previous;
    }
};
}
#include "src/InventoryPreview.cpp"
struct Processor : RE::FxDelegateHandler::CallbackProcessor {
    std::map<std::string, RE::FxDelegateHandler::CallbackFn*> callbacks;
    void Process(const RE::GString& name, RE::FxDelegateHandler::CallbackFn* fn) override { callbacks[name] = fn; }
};
void Open(RE::InventoryMenu& menu, Processor& processor) {
    reinterpret_cast<void(*)(RE::InventoryMenu*, RE::FxDelegateHandler::CallbackProcessor*)>(Native::table[1])(&menu, &processor);
}
void Exercise(RE::InventoryMenu& menu, Processor& processor) {
    processor.callbacks.at("UpdateItem3D")({&menu}); processor.callbacks.at("ItemSelect")({&menu});
    reinterpret_cast<void(*)(RE::InventoryMenu*)>(Native::table[6])(&menu);
}
int main() {
    Native::table[1] = reinterpret_cast<std::uintptr_t>(Native::Accept);
    Native::table[6] = reinterpret_cast<std::uintptr_t>(Native::Display);
    Native::table[4] = reinterpret_cast<std::uintptr_t>(Native::Process);
    InventoryPreview::Install(); InventoryPreview::Install();
    RE::InventoryMenu ordinary; Processor normal; Open(ordinary, normal); Exercise(ordinary, normal);
    assert(Native::loads == 1 && Native::draws == 1 && Native::actions == 1);
    for (int exit = 0; exit < 3; ++exit) {
        InventoryPreview::Begin();
        RE::InventoryMenu inspection; Processor owned; Open(inspection, owned);
        Open(inspection, owned);
        const int loads = Native::loads, draws = Native::draws, actions = Native::actions;
        RE::UIMessage message;
        const auto revision = InventoryPreview::Revision();
        auto process = reinterpret_cast<RE::UI_MESSAGE_RESULTS(*)(RE::InventoryMenu*, RE::UIMessage&)>(Native::table[4]);
        assert(process(&ordinary, message) == RE::UI_MESSAGE_RESULTS::kHandled);
        assert(InventoryPreview::Revision() == revision);
        assert(process(&inspection, message) == RE::UI_MESSAGE_RESULTS::kHandled);
        assert(InventoryPreview::Revision() == revision + 1 && Native::messages == (exit + 1) * 2);
        for (int frame = 0; frame < 20; ++frame) Exercise(inspection, owned);
        assert(Native::loads == loads && Native::draws == draws && Native::actions == actions + 20);
        Exercise(ordinary, normal);
        assert(Native::loads == loads + 1 && Native::draws == draws + 1);
        InventoryPreview::End(); InventoryPreview::End();
        Exercise(inspection, owned);
        assert(Native::loads == loads + 2 && Native::draws == draws + 2);
    }
    InventoryPreview::Begin(); InventoryPreview::End();
    RE::InventoryMenu cancelled; Processor afterCancel; Open(cancelled, afterCancel);
    const int loads = Native::loads, draws = Native::draws;
    Exercise(cancelled, afterCancel);
    assert(Native::loads == loads + 1 && Native::draws == draws + 1 && Native::accepts == 8);
}
