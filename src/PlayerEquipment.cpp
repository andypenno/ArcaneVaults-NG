#include "PlayerEquipment.h"
#include <cmath>

namespace PlayerEquipment {
    namespace {
        std::optional<std::unordered_set<RE::ExtraDataList*>> ReadRows(
            RE::ItemList* list, RE::RefHandle owner, RE::TESBoundObject* item, const std::vector<InventoryStacks::Stack>& stacks) {
            std::unordered_set<RE::ExtraDataList*> seen, protectedStacks;
            std::int64_t represented{}, expected{};
            int bare{};
            for (const auto& stack : stacks) {
                expected += stack.count;
                if (!stack.extra) bare = stack.count;
            }
            for (auto* row : list->items) {
                auto* entry = row ? row->data.objDesc : nullptr;
                if (!entry || entry->object != item) continue;
                if (row->data.owner != owner || entry->countDelta <= 0) return std::nullopt;
                RE::GFxValue state, equipped;
                const bool hasState = row->obj.GetMember("equipState", &state);
                const bool hasEquipped = row->obj.GetMember("isEquipped", &equipped);
                if ((hasState && !state.IsNumber()) || (hasEquipped && !equipped.IsBool())) return std::nullopt;
                if ((!hasState && !hasEquipped) || (hasState && (!std::isfinite(state.GetNumber()) || state.GetNumber() < 0)))
                    return std::nullopt;
                const bool worn = (hasState && state.GetNumber() > 0) || (hasEquipped && equipped.GetBool());
                std::int64_t explicitCount{};
                if (entry->extraLists) for (auto* extra : *entry->extraLists) {
                    if (!extra) continue;
                    RE::ExtraDataList* match{};
                    for (const auto& stack : stacks) {
                        if (!stack.extra) continue;
                        auto* a = extra->GetByType<RE::ExtraUniqueID>();
                        auto* b = stack.extra->GetByType<RE::ExtraUniqueID>();
                        if (extra != stack.extra && (!a || !b || a->baseID != b->baseID || a->uniqueID != b->uniqueID)) continue;
                        if (match) return std::nullopt;
                        match = stack.extra;
                    }
                    if (!match || !seen.insert(match).second || extra->GetCount() != match->GetCount()) return std::nullopt;
                    explicitCount += match->GetCount();
                    if (worn) protectedStacks.insert(match);
                }
                const auto implicitCount = entry->countDelta - explicitCount;
                if (implicitCount < 0 || implicitCount > bare) return std::nullopt;
                bare -= static_cast<int>(implicitCount);
                if (implicitCount && worn) protectedStacks.insert(nullptr);
                represented += entry->countDelta;
            }
            if (represented != expected || bare != 0) return std::nullopt;
            for (const auto& stack : stacks)
                if (stack.extra && !seen.contains(stack.extra)) return std::nullopt;
            return protectedStacks;
        }
    }

    Snapshot Read(RE::PlayerCharacter* player) {
        auto* ui = RE::UI::GetSingleton();
        if (!ui || !player) return {};
        const auto factory = ui->menuMap.find(RE::BSFixedString(RE::InventoryMenu::MENU_NAME));
        if (factory == ui->menuMap.end() || !factory->second.create) return {};
        RE::GPtr<RE::IMenu> instance{factory->second.create()};
        if (!instance) return {};
        // The GPtr retains its own reference in addition to the factory's initial reference.
        instance->Release();
        auto* menu = static_cast<RE::InventoryMenu*>(instance.get());
        if (!menu->uiMovie || !menu->GetRuntimeData().itemList) return {};
        menu->uiMovie->SetVisible(false);

        // Dispatch directly; ItemList::Update queues work against the visible menu instead.
        RE::InventoryUpdateData data{};
        data.inventoryRef = player->GetHandle().native_handle();
        RE::UIMessage message{};
        message.menu = RE::InventoryMenu::MENU_NAME;
        message.type = RE::UI_MESSAGE_TYPE::kInventoryUpdate;
        message.data = &data;
        menu->ProcessMessage(message);

        std::unordered_map<RE::TESBoundObject*, std::vector<InventoryStacks::Stack>> items;
        for (const auto& stack : InventoryStacks::Read(player)) items[stack.item].push_back(stack);
        Snapshot result;
        for (const auto& [item, stacks] : items) {
            const auto protectedStacks = ReadRows(menu->GetRuntimeData().itemList, data.inventoryRef, item, stacks);
            if (protectedStacks) result.emplace(item, *protectedStacks);
        }
        return result;
    }
}
