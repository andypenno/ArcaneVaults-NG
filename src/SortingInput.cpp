#include "SortingInput.h"
#include "TransferFeedback.h"
#include <vector>

namespace SortingInput {
    namespace {
        using Process = RE::BSEventNotifyControl (*)(RE::PlayerControls*, RE::InputEvent* const*, RE::BSTEventSource<RE::InputEvent*>*);
        Process process{};

        void ClearMovement(RE::PlayerControls* controls) {
            controls->data.moveInputVec = {};
            controls->data.prevMoveVec = {};
            controls->data.lookInputVec = {};
            controls->data.prevLookVec = {};
            controls->data.autoMove = false;
        }

        RE::BSEventNotifyControl Dispatch(RE::PlayerControls* controls, RE::InputEvent* const* events,
            RE::BSTEventSource<RE::InputEvent*>* source) {
            if (!TransferFeedback::IsBusy()) return process(controls, events, source);
            struct Restore {
                RE::PlayerControls* controls;
                std::vector<std::pair<RE::InputEvent*, RE::InputEvent*>> links;
                ~Restore() {
                    for (const auto& [event, next] : links) event->next = next;
                    ClearMovement(controls);
                }
            } restore{controls, {}};
            RE::InputEvent* head{};
            RE::InputEvent* tail{};
            for (auto* event = events ? *events : nullptr; event; event = event->next) {
                if (TransferFeedback::FilterInput(event)) continue;
                restore.links.emplace_back(event, event->next);
                if (tail) tail->next = event; else head = event;
                tail = event;
            }
            if (tail) tail->next = nullptr;
            ClearMovement(controls);
            return process(controls, &head, source);
        }
    }

    void Install() {
        if (process) return;
        REL::Relocation<std::uintptr_t> table{RE::PlayerControls::VTABLE[0]};
        process = reinterpret_cast<Process>(table.write_vfunc(1, Dispatch));
    }
}
