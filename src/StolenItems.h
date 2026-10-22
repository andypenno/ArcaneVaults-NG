#pragma once
#include "InventoryStacks.h"

namespace StolenItems {
    using Stack = InventoryStacks::Stack;
    [[nodiscard]] std::vector<Stack> GetStacks(RE::TESObjectREFR* source);
    [[nodiscard]] std::vector<Stack> GetStoredStacks();
    void Init();
    void Reset();
    [[nodiscard]] bool Gather();
    bool Return();
    bool Recover();
    bool Clear();
    void ConfirmClear(std::function<void()> onComplete);
}
