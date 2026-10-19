#include "common.hpp"
#include "extern/json/single_include/nlohmann/json.hpp"
#include <fstream>
#include <iostream>
#ifdef NDEBUG
#error Inventory checks require assertions
#endif

void CheckReadCursor() {
    RE::TESBoundObject item{91000};
    RE::TESObjectREFR source{91001};
    RE::TESForm owner{91002};
    RE::EnchantmentItem enchantment;
    for (int mode = 0; mode < 8; ++mode) {
        source.rows.clear();
        for (int i = 0; i < 33; ++i) {
            source.Put(&item, 0, 1, &owner, std::to_string(i));
            source.rows[&item].extras.back()->enchantment = RE::ExtraEnchantment{&enchantment};
        }
        source.rows[&item].total += 5;
        if (mode == 1) source.rows[&item].duplicate = true;
        if (mode == 2) source.rows[&item].extras[17]->count = 0;
        if (mode == 3) source.rows[&item].total = 16;
        InventoryStacks::ReadCursor cursor;
        std::unordered_set<RE::ExtraDataList*> seen;
        int total{}, bare{}, calls{};
        bool done{};
        do {
            int visited{};
            done = InventoryStacks::ReadPart(&source, &item, cursor, [&](auto&, auto* extra, int count) {
                ++visited; total += count;
                if (!extra) { bare += count; return; }
                assert(seen.insert(extra).second && extra->owner == &owner && extra->enchantment->enchantment == &enchantment);
            });
            assert(visited <= 17 && ++calls < 10);
            if (calls == 1 && !done) {
                if (mode == 4) ++source.rows[&item].total;
                if (mode == 5) source.rows[&item].extras.clear();
                if (mode == 6) source.rows[&item].total = 0;
                if (mode == 7) source.rows.erase(&item);
            }
        } while (!done);
        assert(cursor.valid == (mode == 0));
        if (mode == 0) assert(calls == 3 && total == 38 && bare == 5 && seen.size() == 33);
    }
    source.rows.clear(); source.Put(&item, 7);
    InventoryStacks::ReadCursor cursor;
    assert(InventoryStacks::ReadPart(&source, &item, cursor, [](auto&, auto* extra, int count) { assert(!extra && count == 7); }));
    assert(cursor.valid);
    for (int mode = 0; mode < 3; ++mode) {
        cursor = {}; if (mode == 2) cursor.valid = false;
        assert(InventoryStacks::ReadPart(mode == 0 ? nullptr : &source, mode == 1 ? nullptr : &item, cursor,
            [](auto&, auto*, int) { assert(false); }));
        assert(!cursor.valid);
    }
}

int main(int argc, char** argv) {
    CheckReadCursor();
    assert(argc == 2);
    nlohmann::json data;
    std::ifstream(argv[1]) >> data;
    std::map<std::string, std::unique_ptr<RE::TESBoundObject>> bases;
    std::map<std::string, std::unique_ptr<RE::TESObjectREFR>> inventories;
    std::map<std::string, std::unique_ptr<RE::EnchantmentItem>> enchantments;
    std::map<std::string, std::unique_ptr<RE::TESForm>> owners;
    std::map<std::string, nlohmann::json> originals;
    for (const std::string name : data.at("bases"))
        bases[name] = std::make_unique<RE::TESBoundObject>(RE::TESBoundObject{100 + static_cast<unsigned>(bases.size())});
    for (const auto& [name, rows] : data.at("inventories").items()) {
        auto& inventory = inventories[name];
        inventory = std::make_unique<RE::TESObjectREFR>(1000 + static_cast<unsigned>(inventories.size()));
        for (const auto& row : rows) {
            const std::string id = row.at("id"), base = row.at("base");
            const std::string owner = row.value("owner", std::string{}), enchantment = row.value("enchantment", std::string{});
            if (!owner.empty() && !owners.contains(owner)) owners[owner] = std::make_unique<RE::TESForm>(RE::TESForm{300 + static_cast<unsigned>(owners.size())});
            if (!enchantment.empty() && !enchantments.contains(enchantment)) enchantments[enchantment] = std::make_unique<RE::EnchantmentItem>();
            auto* item = bases.at(base).get();
            inventory->Put(item, 0, row.at("count"), owner.empty() ? nullptr : owners.at(owner).get(), id);
            auto& extra = inventory->rows[item].extras.back();
            extra->displayName = row.value("name", std::string{});
            extra->charge = row.value("charge", 0.0);
            extra->temper = row.value("temper", 0.0);
            extra->fixtureSoul = row.value("soul", 0);
            extra->hotkey = row.value("favorite", false);
            extra->worn = row.value("worn", false);
            if (!enchantment.empty()) extra->enchantment = RE::ExtraEnchantment{enchantments.at(enchantment).get()};
            inventory->rows[item].favorite |= extra->hotkey;
            originals[id] = row;
        }
    }
    for (const auto& action : data.at("actions")) {
        auto* source = inventories.at(action.at("from")).get();
        auto* destination = inventories.at(action.at("to")).get();
        auto* item = bases.at(action.at("base")).get();
        source->limit = action.value("limit", std::numeric_limits<int>::max());
        source->refuse = action.value("refuse", false);
        for (;;) {
            const auto stacks = InventoryStacks::Read(source, [](auto*, auto& entry, auto* extra) {
                return !entry.IsQuestObject() && !InventoryStacks::IsFavorited(entry, extra) &&
                    (!extra || (!extra->template HasType<RE::ExtraWorn>() && !extra->template HasType<RE::ExtraWornLeft>()));
            }, item);
            if (stacks.empty() || !InventoryStacks::Move(stacks.front(), destination)) break;
        }
    }
    for (const auto& [name, inventory] : inventories) {
        std::map<std::string, int> actual;
        for (const auto& stack : InventoryStacks::Read(inventory.get())) {
            assert(stack.extra);
            const auto& id = stack.extra->metadata;
            const auto& row = originals.at(id);
            actual[id] += stack.count;
            const auto owner = row.value("owner", std::string{}), enchantment = row.value("enchantment", std::string{});
            assert(stack.extra->displayName == row.value("name", std::string{}));
            assert(stack.extra->charge == row.value("charge", 0.0) && stack.extra->temper == row.value("temper", 0.0));
            assert(stack.extra->fixtureSoul == row.value("soul", 0));
            assert(stack.extra->owner == (owner.empty() ? nullptr : owners.at(owner).get()));
            assert(stack.extra->hotkey == row.value("favorite", false));
            assert(stack.extra->worn == row.value("worn", false));
            assert((stack.extra->enchantment ? stack.extra->enchantment->enchantment : nullptr) ==
                (enchantment.empty() ? nullptr : enchantments.at(enchantment).get()));
        }
        assert(nlohmann::json(actual) == data.at("expected").at(name));
    }
    std::cout << "PASS " << data.at("name") << '\n';
}
