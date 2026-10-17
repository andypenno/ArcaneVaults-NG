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
    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select = {}, RE::TESBoundObject* item = nullptr, bool firstOnly = false);
    bool IsFavorited(const RE::InventoryEntryData& entry, RE::ExtraDataList* extra);
    RE::BGSKeyword* FavoriteKeyword();
    void RestoreFavorites(RE::TESObjectREFR* source);
    int Count(RE::TESObjectREFR* source, RE::TESBoundObject* item);
    bool HasItems(RE::TESObjectREFR* source);
    int Move(const Stack& stack, RE::TESObjectREFR* target);
    std::optional<Stack> Materialize(const Stack& stack);
    bool HasOrigin(RE::ExtraDataList* extra, RE::BGSKeyword* keyword);
    void ClearOrigins(RE::TESObjectREFR* source, RE::BGSKeyword* keyword, RE::TESBoundObject* item = nullptr);
    std::optional<Stack> MarkOrigin(const Stack& stack, RE::BGSKeyword* keyword);
}
