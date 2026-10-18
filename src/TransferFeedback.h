#pragma once
#include <functional>

namespace TransferFeedback {
    void Register();
    using Complete = std::function<bool()>;
    void Begin(std::function<void(Complete)> start);
    void Reset();
}
