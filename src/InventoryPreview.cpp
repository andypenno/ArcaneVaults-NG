#include "InventoryPreview.h"
#include <atomic>
#include <mutex>
#include <string_view>

namespace InventoryPreview {
    namespace {
        using Processor = RE::FxDelegateHandler::CallbackProcessor;
        using Callback = RE::FxDelegateHandler::CallbackFn;
        using Accept = void (*)(RE::InventoryMenu*, Processor*);
        using Display = void (*)(RE::InventoryMenu*);
        using Process = RE::UI_MESSAGE_RESULTS (*)(RE::InventoryMenu*, RE::UIMessage&);
        Accept accept{};
        Display display{};
        Process process{};
        Callback* update{};
        std::atomic<RE::FxDelegateHandler*> owner{};
        std::atomic<bool> awaiting{};
        std::mutex lifecycle;
        std::atomic<std::uint64_t> revision{};

        void Update(const RE::FxDelegateArgs& args) {
            if (args.GetHandler() != owner.load() && update) update(args);
        }

        struct Filter final : Processor {
            Processor* target;
            explicit Filter(Processor* value) : target(value) {}
            void Process(const RE::GString& name, Callback* callback) override {
                if (std::string_view{name.data(), name.size()} == "UpdateItem3D") {
                    update = callback;
                    target->Process(name, Update);
                } else target->Process(name, callback);
            }
        };

        void Register(RE::InventoryMenu* menu, Processor* processor) {
            bool inspection;
            {
                std::lock_guard guard(lifecycle);
                inspection = awaiting.exchange(false) || menu == owner.load();
                if (inspection) owner.store(menu);
            }
            if (inspection) {
                Filter filter{processor};
                accept(menu, &filter);
            } else accept(menu, processor);
        }

        void PostDisplay(RE::InventoryMenu* menu) {
            if (menu != owner.load()) display(menu);
        }

        RE::UI_MESSAGE_RESULTS ProcessMessage(RE::InventoryMenu* menu, RE::UIMessage& message) {
            if (menu == owner.load()) ++revision;
            return process(menu, message);
        }
    }

    void Install() {
        if (accept) return;
        REL::Relocation<std::uintptr_t> vtable{RE::InventoryMenu::VTABLE[0]};
        accept = reinterpret_cast<Accept>(vtable.write_vfunc(1, Register));
        display = reinterpret_cast<Display>(vtable.write_vfunc(6, PostDisplay));
        process = reinterpret_cast<Process>(vtable.write_vfunc(4, ProcessMessage));
    }

    void Begin() { std::lock_guard guard(lifecycle); awaiting.store(true); }
    void End() { std::lock_guard guard(lifecycle); awaiting.store(false); owner.store(nullptr); }
    std::uint64_t Revision() { return revision.load(); }
}
