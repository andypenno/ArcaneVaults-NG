#pragma once

namespace DepositLearning {
    void Register();
    void MenuOpened();
    void MenuClosed();
    void Reset();
    void RecordAutomaticTransfer(RE::TESObjectREFR* source, RE::TESObjectREFR* destination,
        RE::TESBoundObject* item, int count);
}
