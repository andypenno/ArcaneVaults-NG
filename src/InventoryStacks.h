#pragma once
#include <optional>

namespace InventoryStacks {
    struct Stack {
        RE::TESObjectREFR* source;
        RE::TESBoundObject* item;
        RE::ExtraDataList* extra;
        int count;
    };
    using Select = std::function<bool(RE::TESBoundObject*, RE::InventoryEntryData&, RE::ExtraDataList*)>;
    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select = {});
    int Count(RE::TESObjectREFR* source, RE::TESBoundObject* item);
    bool HasItems(RE::TESObjectREFR* source);
    bool Move(const Stack& stack, RE::TESObjectREFR* target);
    std::optional<Stack> Materialize(const Stack& stack);
    bool HasOrigin(RE::ExtraDataList* extra, RE::BGSKeyword* keyword);
    void ClearOrigins(RE::TESObjectREFR* source, RE::BGSKeyword* keyword);
    std::optional<Stack> MarkOrigin(const Stack& stack, RE::BGSKeyword* keyword);
}
