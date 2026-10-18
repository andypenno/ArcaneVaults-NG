#pragma once
#include <chrono>
#include <functional>

namespace RE { class TESBoundObject; }

namespace OffloadBatch {
    using Clock = std::chrono::steady_clock;
    struct Slice {
        RE::TESBoundObject* item{};
        Clock::time_point deadline;
        std::function<bool()> active;
        int moves{};
        bool changed{}, repeat{};
        bool Moved(bool more) {
            changed = true;
            const bool exhausted = ++moves >= 16 || Clock::now() >= deadline;
            repeat = more && exhausted;
            return exhausted;
        }
    };
    inline thread_local Slice* current{};
}
