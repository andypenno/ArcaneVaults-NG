#pragma once
#include "InventoryStacks.h"
#include <unordered_set>
#include <unordered_map>

namespace PlayerEquipment {
    using Snapshot = std::unordered_map<RE::TESBoundObject*, std::unordered_set<RE::ExtraDataList*>>;
    Snapshot Read(RE::PlayerCharacter* player);
}
