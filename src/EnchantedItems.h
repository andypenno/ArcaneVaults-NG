#pragma once

namespace EnchantedItems {
    void Init();
    bool Eligible(RE::TESBoundObject* item, const RE::InventoryEntryData& entry, RE::ExtraDataList* extra);
    bool Gather();
    bool Recover();
}
