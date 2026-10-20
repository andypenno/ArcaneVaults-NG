#pragma once
#include <optional>
#include <map>
#include <memory>
#include <functional>
#include <vector>
#include <unordered_set>

namespace InventoryStacks {
    struct Stack {
        RE::TESObjectREFR* source;
        RE::TESBoundObject* item;
        RE::ExtraDataList* extra;
        int count;
    };
    using Select = std::function<bool(RE::TESBoundObject*, RE::InventoryEntryData&, RE::ExtraDataList*)>;
    struct ReadState;
    struct ReadCursor {
        std::size_t offset{};
        int total{-1};
        std::int64_t explicitCount{};
        bool valid{true};
        std::unordered_set<RE::ExtraDataList*> seen;
        std::shared_ptr<ReadState> state;
    };
    struct Prepared {
        ReadCursor cursor;
        std::vector<Stack> stacks;
        std::vector<std::pair<std::size_t, int>> moved;
        std::vector<bool> filled;
        bool complete{}, quest{}, favorite{}, worn{}, identifiedFavorite{};
    };
    bool Prepare(RE::TESObjectREFR* source, RE::TESBoundObject* item, Prepared& prepared,
        const std::function<bool(RE::ExtraDataList*, int, std::size_t)>& validate = {});
    bool Valid(const ReadCursor& cursor);
    int MovePrepared(const Stack& stack, RE::TESObjectREFR* target, Prepared& prepared, std::size_t index);
    bool ReadPart(RE::TESObjectREFR* source, RE::TESBoundObject* item, ReadCursor& cursor,
        const std::function<void(RE::InventoryEntryData&, RE::ExtraDataList*, int)>& visit);
    bool ReadEntryPart(RE::TESObjectREFR* source, RE::TESBoundObject* item, RE::InventoryEntryData& entry,
        int total, ReadCursor& cursor, const std::function<void(RE::InventoryEntryData&, RE::ExtraDataList*, int)>& visit);
    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select = {}, RE::TESBoundObject* item = nullptr, bool firstOnly = false);
    std::vector<Stack> Read(RE::TESObjectREFR* source, Select select, RE::TESBoundObject* item, bool firstOnly,
        std::function<bool(RE::TESBoundObject&)> filter);
    bool IsFavorited(const RE::InventoryEntryData& entry, RE::ExtraDataList* extra);
    std::map<RE::TESBoundObject*, int> Counts(RE::TESObjectREFR* source,
        std::function<bool(RE::TESBoundObject&)> filter = {}, bool noInit = false);
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
