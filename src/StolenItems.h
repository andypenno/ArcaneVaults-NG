#pragma once

namespace StolenItems {
    struct Stack {
        RE::TESObjectREFR* source;
        RE::TESBoundObject* item;
        RE::ExtraDataList* extra;
        int count;
    };

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
