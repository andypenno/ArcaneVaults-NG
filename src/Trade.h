#pragma once
#include <cstdint>
#include <optional>
#include <vector>

namespace Trade {
    struct Stack {
        RE::TESBoundObject* item;
        RE::ExtraDataList* extra;
        int count;
        int value;
        bool operator==(const Stack&) const = default;
    };

    struct Quote {
        std::vector<Stack> stacks;
        std::int64_t copies{};
        std::int64_t payout{};
        int percentage{};
        bool valid{false};
    };

    Quote GetQuote(RE::TESObjectREFR* source, int percentage);
    bool CanReceive(const Quote& quote);
    std::optional<int> Sell(RE::TESObjectREFR* source, const Quote& confirmed);
}
