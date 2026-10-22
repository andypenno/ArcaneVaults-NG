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
    for (int mode = 0; mode < 10; ++mode) {
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
                if (mode == 8) {
                    RE::ScriptEventSourceHolder::GetSingleton()->Send(RE::TESContainerChangedEvent{source.id, 0, item.id, 1});
                    source.rows[&item].extras[20] = std::make_shared<RE::ExtraDataList>();
                }
                if (mode == 9) {
                    RE::ScriptEventSourceHolder::GetSingleton()->Send(RE::TESEquipEvent{{&source}, item.id});
                    source.rows[&item].extras[20]->worn = true;
                }
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
    cursor={};RE::ScriptEventSourceHolder::available=false;
    assert(InventoryStacks::ReadPart(&source,&item,cursor,[](auto&,auto*,int){assert(false);}));
    assert(!cursor.valid);RE::ScriptEventSourceHolder::available=true;
}

void CheckCounts() {
    RE::TESBoundObject item{92000}, other{92001};
    RE::TESObjectREFR source{92002};
    for (int stock : {0, 4}) for (int delta : {-4, 0, 3}) for (bool leveled : {false, true}) {
        source.rows.clear();
        source.Put(&item, delta + (leveled ? 0 : stock));
        source.rows[&item].baseStock = stock;
        source.rows[&item].leveled = leveled;
        source.Put(&other, 7);
        int baseEntries = 0;
        source.GetContainer()->ForEachContainerObject([&](auto& entry) {
            assert(entry.obj == &item && entry.count == stock);++baseEntries;
        });
        assert(baseEntries == (stock != 0));
        assert(InventoryStacks::Counts(&source) == source.GetInventoryCounts());
        const auto counts = InventoryStacks::Counts(&source, [&](auto& candidate) { return &candidate == &item; });
        assert(counts.size() == 1 && counts.at(&item) == delta + (leveled ? 0 : stock));
        assert(InventoryStacks::Count(&source, &item) == (std::max)(0, counts.at(&item)));
        assert(InventoryStacks::Count(&source, &other) == 7);
    }
    source.initialized = false;
    InventoryStacks::Counts(&source, {}, true);
    assert(!source.initialized);
    InventoryStacks::Counts(&source);
    assert(source.initialized);
    assert(InventoryStacks::Counts(nullptr).empty());
}

void CheckPreparedMoves() {
    RE::TESBoundObject item{93000};
    RE::TESObjectREFR source{93001}, target{93002}, diverted{93003};
    source.Put(&item, 0, 1, nullptr, "first");source.Put(&item, 0, 1, nullptr, "second");
    InventoryStacks::Prepared prepared;
    while (!InventoryStacks::Prepare(&source, &item, prepared)) {}
    struct SideEffect final : RE::BSTEventSink<RE::TESContainerChangedEvent> {
        std::function<void()> run;
        RE::BSEventNotifyControl ProcessEvent(const RE::TESContainerChangedEvent*, RE::BSTEventSource<RE::TESContainerChangedEvent>*) override {
            if (run) { auto callback=std::move(run);run={};callback(); }
            return RE::BSEventNotifyControl::kContinue;
        }
    } effect;
    effect.run=[&]{source.RemoveItem(&item,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,prepared.stacks[1].extra,&diverted);};
    auto* events=RE::ScriptEventSourceHolder::GetSingleton();events->AddEventSink(&effect);
    assert(InventoryStacks::MovePrepared(prepared.stacks[0],&target,prepared,0)==0);
    assert(!InventoryStacks::Valid(prepared.cursor));
    assert(InventoryStacks::MovePrepared(prepared.stacks[1],&target,prepared,1)==0);
    assert(InventoryStacks::Count(&target,&item)==1 && InventoryStacks::Count(&diverted,&item)==1);
    std::erase(events->sinks,&effect);
    prepared={};source.rows.clear();target.rows.clear();source.Put(&item,0,3);source.limit=1;
    while (!InventoryStacks::Prepare(&source,&item,prepared)) {}
    assert(InventoryStacks::MovePrepared(prepared.stacks.front(),&target,prepared,0)==1);
    assert(InventoryStacks::Valid(prepared.cursor) && InventoryStacks::Count(&source,&item)==2);
    prepared={};source.rows.clear();source.limit=std::numeric_limits<int>::max();
    for(int i=0;i<33;++i)source.Put(&item,0,1);
    assert(!InventoryStacks::Prepare(&source,&item,prepared));
    source.rows[&item].quest=true;source.rows[&item].favorite=true;
    while(!InventoryStacks::Prepare(&source,&item,prepared)) {}
    assert(prepared.quest && prepared.favorite);
}

int main(int argc, char** argv) {
    CheckReadCursor();
    CheckCounts();
    CheckPreparedMoves();
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
