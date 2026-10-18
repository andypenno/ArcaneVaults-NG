#pragma once
#include "InventoryStacks.h"
#include <functional>
#include <unordered_map>
#include <unordered_set>

namespace PlayerEquipment {
    struct StackIdentity {
        RE::ExtraDataList* extra{};
        int count{};
        std::optional<std::pair<std::uint32_t, std::uint16_t>> unique;
        bool worn{};
        bool operator==(const StackIdentity&) const = default;
    };
    struct ItemEquipment {
        std::unordered_set<RE::ExtraDataList*> equipped;
        std::vector<StackIdentity> stacks;
    };
    using Snapshot = std::unordered_map<RE::TESBoundObject*, ItemEquipment>;
    const Snapshot* Current();
    bool Apply(Snapshot& snapshot, RE::TESBoundObject* item, const std::function<bool()>& work);
    void Run(std::function<void()> work, std::function<void()> complete = {});
    bool IsRunning();
    void Reset();
}
