#pragma once
#include <functional>
namespace RE { class InputEvent; }

namespace TransferFeedback {
    void Register();
    bool IsBusy();
    bool FilterInput(RE::InputEvent* event);
    using Complete = std::function<bool()>;
    void Begin(std::function<void(Complete)> start);
    void Run(std::function<bool(const std::function<bool()>&)> step, std::function<void()> complete);
    void WaitForFrame(std::function<void()> work, std::function<void()> cancelled = {});
    void Reset();
}
