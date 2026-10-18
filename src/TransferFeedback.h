#pragma once
#include <functional>

namespace TransferFeedback {
    void Register();
    using Complete = std::function<bool()>;
    void Begin(std::function<void(Complete)> start);
    void Run(std::function<bool(const std::function<bool()>&)> step, std::function<void()> complete);
    void Reset();
}
