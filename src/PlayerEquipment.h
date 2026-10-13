#pragma once
#include "InventoryStacks.h"
#include <functional>
#include <unordered_map>
#include <unordered_set>

namespace PlayerEquipment {
    using Snapshot = std::unordered_map<RE::TESBoundObject*, std::unordered_set<RE::ExtraDataList*>>;
    const Snapshot* Current();
    void Run(std::function<void()> work, std::function<void()> complete = {});
    void Reset();
}
