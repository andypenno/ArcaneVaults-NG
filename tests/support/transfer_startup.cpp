void StartupResult(const char* name, bool passed,
    std::initializer_list<std::pair<const char*, long long>> metrics = {}) {
    std::cout << "{\"startup\":true,\"name\":\"" << name << "\",\"passed\":" << (passed ? "true" : "false");
    for (const auto& [key, value] : metrics) std::cout << ",\"" << key << "\":" << value;
    std::cout << "}\n";
}

void CheckStartup() {
    auto* player = RE::PlayerCharacter::GetSingleton();
    auto* settings = Settings::GetSingleton();
    auto* utility = Utility::GetSingleton();
    auto* stores = Stores::GetSingleton();
    auto* ui = RE::UI::GetSingleton();
    auto* queue = RE::UIMessageQueue::GetSingleton();
    auto* tasks = SKSE::GetTaskInterface();
    SKSEMenuFramework::installed = true;
    TransferFeedback::Register();
    const auto originalSettings = *settings;
    std::map<Container, std::unique_ptr<RE::TESObjectREFR>> banks;
    for (auto kind : {Container::Armor, Container::Weapon, Container::Book, Container::Notes, Container::Scroll,
        Container::SpellTomes, Container::SkillBooks, Container::Recipes, Container::Maps, Container::Concoction,
        Container::Potion, Container::Poison, Container::Restorative, Container::HealthPotions,
        Container::MagickaPotions, Container::StaminaPotions, Container::Gear, Container::Instruments,
        Container::Soulgem, Container::EmptySoulgems, Container::FilledSoulgems, Container::Smithing,
        Container::Crafting, Container::Smelting, Container::Construction, Container::Tanning, Container::Gemstone,
        Container::Sort, Container::Keys, Container::Junk, Container::Personal, Container::Treasure, Container::Ammunition,
        Container::Food, Container::Alchemy}) {
        banks[kind] = std::make_unique<RE::TESObjectREFR>(19000 + static_cast<unsigned>(kind));
        utility->containers[kind] = banks[kind].get();
    }
    RE::TESObjectREFR chest{18000}, assignment{18001};
    utility->containerMap[Container::QuickTransfer] = {&assignment, [](auto*) { Stores::GetSingleton()->OffloadItems(); }};
    auto reset = [&] {
        assert(!ui->menu && !PlayerEquipment::IsRunning());
        TransferFeedback::Reset();
        timers.clear(); tasks->queue.clear(); tasks->ui.clear();
        assert(queue->commands.empty());
        *settings = Settings{};
        player->rows.clear();
        for (auto& [kind, bank] : banks) { (void)kind; bank->rows.clear(); bank->changes.bulkRefuse = false; bank->changes.bulkLimit = 100000; bank->refuse = false; bank->limit = 100000; }
        RE::SCRIPT_FUNCTION::equipped.clear();
        StartupProbe::equippedQueries = StartupProbe::explicitUpdates = StartupProbe::confirmations = 0;
        StartupProbe::failQueue = false;
        StartupProbe::validatedEquipment.clear();
        RE::SendHUDMessage::message.clear();
        StartupProbe::afterShow = StartupProbe::beforeUpdate = {};
        RE::inventoryReads = RE::bulkCalls = RE::removeCalls = 0;
        RE::InventoryMenu::empty = RE::InventoryMenu::uninitialized = false;
        ui->messageBox = false; queue->refuseHide = false; queue->afterHide = {};
        stores->options.clear(); stores->ResetNavigation();
        ProbeClock::tick = {};
    };
    auto pump = [&] {
        SKSEMenuFramework::render();
        ProbeClock::tick += std::chrono::milliseconds(16);
        queue->ProcessCommands();
        auto ready = std::move(timers); timers.clear();
        for (auto& timer : ready) timer();
        tasks->RunUI(); tasks->Run();
    };
    auto drain = [&] {
        for (int i = 0; i < 200 && (PlayerEquipment::IsRunning() || !timers.empty() ||
            !tasks->queue.empty() || !tasks->ui.empty() || !queue->commands.empty()); ++i) pump();
        assert(!PlayerEquipment::IsRunning() && !ui->menu && timers.empty() && tasks->queue.empty() && tasks->ui.empty());
    };
    auto start = [&](int entry) {
        if (entry == 0) {
            stores->ShowVaultMenu(&chest);
            auto selected = std::ranges::find_if(stores->options, [](auto& option) { return option.text == "Vault.ArcaneOffload"; });
            assert(selected != stores->options.end());
            auto action = selected->action; stores->options.clear(); ui->messageBox = false; action();
        } else if (entry == 1) assert(utility->RunContainerAction(&assignment, &chest));
        else stores->OffloadItems();
    };
    for (int protection = 0; protection < 3; ++protection) for (bool weapon : {false, true}) for (int size : {1, 100}) {
        reset();
        std::vector<std::unique_ptr<RE::TESBoundObject>> items;
        for (int i = 0; i < size; ++i) {
            auto item = std::make_unique<RE::TESBoundObject>(20000 + i, weapon, !weapon);
            player->Put(item.get(), 0, 1, nullptr, "protected");
            auto& row = player->rows[item.get()];
            if (protection == 0) row.quest = true;
            if (protection == 1) row.extras.front()->hotkey = true;
            if (protection == 2) settings->ignored.insert(item.get());
            items.push_back(std::move(item));
        }
        const auto input = RE::input; const auto shows = queue->shows;
        int worked = 0, completed = 0;
        PlayerEquipment::Run([&] { ++worked; }, [&] { ++completed; });
        drain();
        assert(worked == 1 && completed == 1 && RE::input == input && queue->shows == shows);
        for (auto& item : items) assert(player->rows[item.get()].total == 1);
        StartupResult("protected equipment avoids equipped queries", StartupProbe::equippedQueries == 0,
            {{"protection", protection}, {"weapon", weapon}, {"size", size}, {"equipped_queries", StartupProbe::equippedQueries}});
        StartupResult("protected preflight uses bounded fresh reads", RE::inventoryReads <= size + 1,
            {{"protection", protection}, {"weapon", weapon}, {"size", size}, {"inventory_reads", RE::inventoryReads}});
    }
    RE::TESBoundObject ring{21000, false, true};
    ring.categories = ItemCategory::Armor | ItemCategory::Jewelry;
    RE::TESForm owner{21001}; owner.playerOwned = true;
    RE::EnchantmentItem enchantmentA, enchantmentB;
    for (int entry = 0; entry < 3; ++entry) for (int shape = 0; shape < 6; ++shape)
        for (int fields = 0; fields < 4; ++fields) {
        reset();
        settings->GSC_OffloadOneHand = settings->GSC_OffloadTwoHand = settings->GSC_OffloadArchery = true;
        settings->GSC_OffloadLightArmor = settings->GSC_OffloadHeavyArmor = settings->GSC_OffloadClothing = true;
        settings->GSC_OffloadJewelry = settings->GSC_OffloadNotes = true;
        const std::array names{"Ancient Nord sword", "Ancient Nord battle axe", "Ebony bow", "Fur armor", "Iron armor", "Bandit robes"};
        const std::array categories{ItemCategory::OneHand, ItemCategory::TwoHand, ItemCategory::Archery,
            ItemCategory::LightArmor, ItemCategory::HeavyArmor, ItemCategory::Clothing};
        std::vector<std::unique_ptr<RE::TESBoundObject>> loot;
        const int count = shape == 2 || shape == 5 ? 3 : 1;
        const bool explicitStack = shape == 1 || shape == 5;
        for (unsigned i = 0; i < names.size(); ++i) {
            auto item = std::make_unique<RE::TESBoundObject>(50000 + i, i < 3, i >= 3);
            item->categories = (i < 3 ? ItemCategory::Weapon : ItemCategory::Armor) | categories[i];
            player->Put(item.get(), explicitStack ? 0 : count, explicitStack ? count : 0,
                explicitStack ? &owner : nullptr, names[i]);
            if (shape == 3 || shape == 4) {
                player->Put(item.get(), 0, 1, &owner, "protected named enchanted copy");
                auto& extra = player->rows[item.get()].extras.back();
                extra->hotkey = shape == 3; extra->uiWorn = shape == 4;
                extra->enchantment = RE::ExtraEnchantment{&enchantmentA};
                extra->displayName = "My " + std::string(names[i]);
                if (shape == 4) RE::SCRIPT_FUNCTION::equipped.insert(item.get());
            }
            loot.push_back(std::move(item));
        }
        RE::TESBoundObject note{50100}, ingredient{50101};
        note.categories = ToMask(ItemCategory::Note);
        ingredient.categories = ItemCategory::Alchemy | ItemCategory::Ingredient;
        player->Put(&note, 2); player->Put(&ingredient, 5);
        player->Put(&ring, 0, 1, &owner, "worn loadout");
        player->rows[&ring].extras.back()->worn = true;
        player->rows[&ring].extras.back()->hotkey = true;
        RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        // Missing both equipment fields must retain equipment rather than assume it is unworn.
        StartupProbe::afterShow = [&] {
            for (auto* row : static_cast<RE::InventoryMenu*>(ui->menu)->list.items) {
                if (fields == 1 || fields == 3) row->obj.members.erase("isEquipped");
                if (fields == 2 || fields == 3) row->obj.members.erase("equipState");
            }
        };
        StartupProbe::beforeUpdate = [&] { RE::InventoryMenu::missingFields = fields == 3; };
        const auto input = RE::input;
        const bool blocked = RE::PlayerControls::GetSingleton()->blockPlayerInput;
        start(entry); drain();
        RE::InventoryMenu::missingFields = false;
        assert(RE::input == input && RE::PlayerControls::GetSingleton()->blockPlayerInput == blocked);
        assert(player->rows[&ring].total == 1 && player->rows[&ring].extras.front()->worn);
        assert(player->rows[&note].total == 0 && banks[Container::Notes]->rows[&note].total == 2);
        assert(player->rows[&ingredient].total == 0 && banks[Container::Alchemy]->rows[&ingredient].total == 5);
        assert(StartupProbe::confirmations == 1);
        for (unsigned i = 0; i < loot.size(); ++i) {
            auto* item = loot[i].get();
            const auto destination = i < 3 ? Container::Weapon : Container::Armor;
            const int moved = banks[destination]->rows[item].total;
            assert(player->rows[item].total + moved == count + (shape == 3 || shape == 4 ? 1 : 0));
            if (shape == 3 || shape == 4) {
                const auto& extras = player->rows[item].extras;
                const auto found = std::ranges::find_if(extras, [](auto& extra) { return extra->hotkey || extra->uiWorn; });
                assert(found != extras.end() && (*found)->owner == &owner && (*found)->enchantment->enchantment == &enchantmentA);
                assert((*found)->displayName == "My " + std::string(names[i]));
            }
            if (explicitStack && moved) {
                const auto& extras = banks[destination]->rows[item].extras;
                assert(extras.size() == 1 && extras.front()->owner == &owner && extras.front()->metadata == names[i]);
            }
            const bool validated = StartupProbe::validatedEquipment.contains(item->GetFormID());
            StartupResult(names[i], moved == (fields == 3 ? 0 : count),
                {{"entry", entry}, {"physical_shape", shape}, {"ui_fields", fields}, {"validated", validated},
                 {"moved", moved}, {"expected", fields == 3 ? 0 : count}});
        }
    }
    {
        reset();
        std::vector<std::unique_ptr<RE::TESBoundObject>> candidates;
        for (int i = 0; i < 100; ++i) {
            auto item = std::make_unique<RE::TESBoundObject>(40000 + i, true);
            player->Put(item.get(), 1); candidates.push_back(std::move(item));
        }
        int worked = 0;
        PlayerEquipment::Run([&] { ++worked; }); drain();
        assert(worked == 1);
        for (auto& item : candidates) assert(player->rows[item.get()].total == 1);
        StartupResult("required inspection avoids repeated single-copy queries", StartupProbe::equippedQueries <= 1,
            {{"candidate_bases", 100}, {"equipped_queries", StartupProbe::equippedQueries}});
    }
    {
        reset(); player->Put(&ring, 0, 1); player->rows[&ring].extras.back()->hotkey = true;
        std::vector<std::unique_ptr<RE::TESBoundObject>> unrelated;
        for (int i = 0; i < 1000; ++i) {
            auto item = std::make_unique<RE::TESBoundObject>(30000 + i);
            player->Put(item.get(), 1); unrelated.push_back(std::move(item));
        }
        RE::TESObjectREFR::inventoryCopies = 0; int worked = 0;
        PlayerEquipment::Run([&] { ++worked; }); drain();
        assert(worked == 1 && player->rows[&ring].total == 1);
        for (auto& item : unrelated) assert(player->rows[item.get()].total == 1);
        StartupResult("preflight copies equipment only", RE::TESObjectREFR::inventoryCopies <= 2,
            {{"unrelated_bases", 1000}, {"copied_entries", RE::TESObjectREFR::inventoryCopies}});
    }
    for (int entry = 0; entry < 3; ++entry) for (int scenario = 0; scenario < 15; ++scenario) {
        reset();
        settings->GSC_OffloadJewelry = scenario != 0;
        settings->GSC_OffloadSoulgems = false;
        player->Put(&ring, 0, 1, &owner, "worn custom ring");
        player->rows[&ring].extras.back()->uiWorn = true;
        player->rows[&ring].extras.back()->enchantment = RE::ExtraEnchantment{&enchantmentA};
        if (scenario == 10) player->rows[&ring].extras.back()->hotkey = true;
        RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        if (scenario == 1) {
            player->rows[&ring].extras.back()->worn = true;
            player->Put(&ring, 0, 1, &owner, "second native worn ring");
            player->rows[&ring].extras.back()->worn = true;
        } else {
            player->Put(&ring, 0, 1, &owner, "spare custom ring");
            player->rows[&ring].extras.back()->enchantment = RE::ExtraEnchantment{&enchantmentB};
        }
        RE::TESBoundObject sword{21400, true}, note{21401};
        if (scenario == 14) {
            settings->GSC_OffloadOneHand = settings->GSC_OffloadNotes = true;
            sword.categories = ItemCategory::Weapon | ItemCategory::OneHand;
            note.categories = ToMask(ItemCategory::Note);
            player->Put(&sword, 3); player->Put(&note, 2);
        }
        const auto input = RE::input; const bool blocked = RE::PlayerControls::GetSingleton()->blockPlayerInput;
        const int shows = queue->shows;
        const bool deferred = (scenario >= 3 && scenario <= 7) || scenario == 12 || scenario == 13;
        bool loading = deferred; int redundant = 0, shownFrame = -1;
        StartupProbe::afterShow = [&] {
            if (scenario == 14) ProbeClock::tick += std::chrono::milliseconds(400);
            shownFrame = static_cast<int>(std::chrono::duration_cast<std::chrono::milliseconds>(ProbeClock::tick.time_since_epoch()).count() / 16);
            auto* menu = static_cast<RE::InventoryMenu*>(ui->menu);
            if (scenario == 3 || scenario == 4 || scenario == 7 || scenario == 8 || scenario == 11 || scenario == 13 || scenario == 14) {
                RE::InventoryMenu::empty = true; menu->list.items.clear(); menu->list.root.kind = RE::GFxValue::Undefined;
            } else if (scenario == 5) {
                menu->list.root.kind = RE::GFxValue::Undefined;
                for (auto* row : menu->list.items) row->obj.kind = RE::GFxValue::Undefined;
            } else if (scenario == 6) {
                for (auto* row : menu->list.items) { row->obj.members.erase("equipState"); row->obj.members.erase("isEquipped"); }
            } else if (scenario == 12) {
                for (auto* row : menu->list.items) { row->obj.members["equipState"].number = 0; row->obj.members["isEquipped"].boolean = false; }
            }
        };
        StartupProbe::beforeUpdate = [&] {
            if (loading) ++redundant;
            if (scenario == 11 || scenario == 14) RE::InventoryMenu::empty = false;
        };
        if (scenario == 9) queue->afterHide = [&] { player->rows[&ring].favorite = true; };
        start(entry);
        if (scenario == 13) ui->messageBox = true;
        bool cancelled = false;
        auto stale = PlayerEquipment::pending;
        for (int frame = 0; frame < 200; ++frame) {
            if (scenario == 13 && frame == 45) ui->messageBox = false;
            if (shownFrame >= 0 && loading && frame - shownFrame >= (scenario == 4 ? 8 : 5)) {
                loading = false; RE::InventoryMenu::empty = false;
                if (ui->menu) {
                    RE::InventoryUpdateData data{player->GetHandle().native_handle()};
                    RE::UIMessage message{std::string(RE::InventoryMenu::MENU_NAME), RE::UI_MESSAGE_TYPE::kInventoryUpdate, &data};
                    auto* menu = static_cast<RE::InventoryMenu*>(ui->menu);
                    menu->list.root.kind = RE::GFxValue::DisplayObject; menu->ProcessMessage(message);
                }
            }
            if (scenario == 7 && shownFrame >= 0 && !cancelled) {
                cancelled = true; stale = PlayerEquipment::pending; TransferFeedback::Reset(); PlayerEquipment::Reset();
            }
            if (scenario == 7 && cancelled && frame > shownFrame + 2) PlayerEquipment::Poll(stale);
            pump();
            if (!PlayerEquipment::IsRunning() && timers.empty() && tasks->queue.empty() && tasks->ui.empty() && queue->commands.empty() &&
                (scenario != 7 || frame >= shownFrame + 10)) break;
        }
        drain();
        assert(RE::input == input && RE::PlayerControls::GetSingleton()->blockPlayerInput == blocked);
        const int moved = banks[Container::Armor]->rows[&ring].total;
        assert(player->rows[&ring].total + moved == 2 && moved <= 1);
        auto* worn = player->rows[&ring].extras.front().get();
        assert(worn->metadata == "worn custom ring" && worn->owner == &owner && worn->enchantment->enchantment == &enchantmentA);
        if (moved) {
            auto* spare = banks[Container::Armor]->rows[&ring].extras.front().get();
            assert(spare->metadata == "spare custom ring" && spare->owner == &owner && spare->enchantment->enchantment == &enchantmentB);
        }
        const int expected = scenario == 2 || scenario >= 10 || (scenario >= 3 && scenario <= 6) ? 1 : 0;
        assert(StartupProbe::confirmations == (scenario == 7 ? 0 : 1));
        if (scenario == 10) assert(worn->hotkey);
        StartupResult("startup preserves protection and transfers eligible spare", moved == expected,
            {{"entry", entry}, {"scenario", scenario}, {"moved", moved}, {"expected", expected}});
        if (scenario <= 1) StartupResult("ineligible equipment avoids opening inventory", queue->shows == shows,
            {{"entry", entry}, {"scenario", scenario}, {"inspection_shows", queue->shows - shows}});
        if (deferred) StartupResult("initial loading avoids redundant full refresh", redundant == 0,
            {{"entry", entry}, {"scenario", scenario}, {"redundant_full_refreshes", redundant}});
        if (scenario == 8) StartupResult("failed initialization has bounded recovery", StartupProbe::explicitUpdates <= 1 &&
            ProbeClock::tick.time_since_epoch() <= std::chrono::milliseconds(1250),
            {{"entry", entry}, {"refreshes", StartupProbe::explicitUpdates}});
        if (scenario == 11) StartupResult("one recovery refresh makes equipment usable", moved == 1 && StartupProbe::explicitUpdates == 1 &&
            ProbeClock::tick.time_since_epoch() <= std::chrono::milliseconds(1100),
            {{"entry", entry}, {"refreshes", StartupProbe::explicitUpdates}, {"moved", moved}});
        if (scenario == 14) {
            const int weapons = banks[Container::Weapon]->rows[&sword].total;
            assert(player->rows[&sword].total + weapons == 3);
            assert(player->rows[&note].total == 0 && banks[Container::Notes]->rows[&note].total == 2);
            StartupResult("delayed menu opening still permits recovery and equipment sorting",
                moved == 1 && weapons == 3 && StartupProbe::explicitUpdates == 1,
                {{"entry", entry}, {"opening_delay_ms", 400}, {"refreshes", StartupProbe::explicitUpdates},
                 {"armor_moved", moved}, {"weapons_moved", weapons}, {"notes_moved", 2}});
        }
        if (scenario == 7) assert(cancelled && moved == 0 && stores->options.empty());
    }
    for (int entry = 0; entry < 3; ++entry) {
        reset(); settings->GSC_OffloadJewelry = true;
        player->Put(&ring, 1); StartupProbe::failQueue = true;
        const auto input = RE::input;
        start(entry); drain();
        RE::InputEvent button;
        assert(!SKSEMenuFramework::block(&button) && RE::input == input && player->rows[&ring].total == 1);
        assert(StartupProbe::confirmations == 0 && RE::removeCalls == 0);
        StartupResult("queue failure releases feedback without moving items", true, {{"entry", entry}});
    }
    RE::TESBoundObject disabled{21500};
    const std::array disabledCategories{ToMask(ItemCategory::Armor), ToMask(ItemCategory::Weapon),
        ItemCategory::Weapon | ItemCategory::OneHand, ToMask(ItemCategory::Ignore)};
    for (int entry = 0; entry < 3; ++entry) for (unsigned kind = 0; kind < disabledCategories.size(); ++kind) {
        reset(); settings->GSC_OffloadSoulgems = false;
        disabled.categories = disabledCategories[kind]; disabled.armor = kind == 0 || kind == 3; disabled.weapon = !disabled.armor;
        if (kind == 3) settings->GSC_OffloadHeavyArmor = settings->GSC_OffloadJewelry = true;
        player->Put(&disabled, 0, 1, &owner, "ineligible equipment");
        const int shows = queue->shows; const auto input = RE::input;
        start(entry); drain();
        assert(player->rows[&disabled].total == 1 && RE::input == input && RE::removeCalls == 0 && StartupProbe::confirmations == 1);
        StartupResult("disabled or Ignore equipment avoids inspection", queue->shows == shows,
            {{"entry", entry}, {"category_case", kind}, {"inspection_shows", queue->shows - shows}});
    }
    for (int entry = 0; entry < 3; ++entry) for (int mode = 0; mode < 3; ++mode) {
        reset(); settings->GSC_OffloadSoulgems = false;
        player->Put(&ring, 0, 1, &owner, "protected loadout"); player->rows[&ring].extras.back()->hotkey = true;
        std::vector<std::unique_ptr<RE::TESBoundObject>> items;
        const std::array sources{Container::SpellTomes, Container::SkillBooks, Container::Recipes, Container::Maps,
            Container::Potion, Container::Poison, Container::Restorative, Container::HealthPotions,
            Container::MagickaPotions, Container::StaminaPotions, Container::Instruments};
        for (unsigned i = 0; i < sources.size(); ++i) {
            auto item = std::make_unique<RE::TESBoundObject>(22000 + i);
            banks[sources[i]]->Put(item.get(), 0, 3, &owner, "archive metadata");
            banks[sources[i]]->refuse = mode == 1;
            banks[sources[i]]->limit = mode == 2 ? 1 : 100000;
            banks[sources[i]]->changes.bulkRefuse = mode == 1;
            banks[sources[i]]->changes.bulkLimit = mode == 2 ? 1 : 100000;
            items.push_back(std::move(item));
        }
        const auto input = RE::input; const int shows = queue->shows;
        start(entry); drain();
        assert(RE::input == input && player->rows[&ring].total == 1 && queue->shows == shows && StartupProbe::confirmations == 1);
        for (unsigned i = 0; i < sources.size(); ++i) {
            auto destination = i < 2 ? Container::Book : i < 4 ? Container::Notes : i < 10 ? Container::Concoction : Container::Gear;
            const int expected = mode == 1 ? 0 : mode == 2 && RE::bulkCalls > 0 ? 1 : 3;
            auto* item = items[i].get(); const auto& source = banks[sources[i]]->rows[item];
            const auto& target = banks[destination]->rows[item];
            assert(source.total + target.total == 3 && player->rows[item].total == 0);
            for (auto* row : {&source, &target}) for (const auto& extra : row->extras)
                assert(extra->owner == &owner && extra->metadata == "archive metadata");
            StartupResult("populated archive consolidation preserves stock", target.total == expected,
                {{"entry", entry}, {"mode", mode}, {"archive", i}, {"moved", target.total}, {"expected", expected}});
        }
    }

#ifdef AV_SLICED_INSPECTION
    for (int entry = 0; entry < 3; ++entry) {
        reset(); settings->GSC_OffloadJewelry = settings->GSC_OffloadNotes = true;
        RE::TESBoundObject note{22400}; note.categories = ToMask(ItemCategory::Note);
        player->Put(&note, 1);
        for (int i = 0; i < 128; ++i) player->Put(&ring, 0, 1, &owner, "late equipped copy " + std::to_string(i));
        RE::InventoryMenu::grouped = true;
        start(entry);
        bool changed = false;
        for (int frame = 0; frame < 600; ++frame) {
            const auto request = PlayerEquipment::pending;
            if (!changed && request && ui->menu && request->extraCursor > 0) {
                for (auto& extra : player->rows[&ring].extras) extra->uiWorn = true;
                RE::ItemList::Item* row{};
                for (auto* candidate : static_cast<RE::InventoryMenu*>(ui->menu)->list.items)
                    if (candidate->data.objDesc->object == &ring) { row = candidate; break; }
                assert(row);
                row->obj.members["equipState"].number = 3;
                row->obj.members["isEquipped"].boolean = true;
                changed = true;
            }
            pump();
            if (!PlayerEquipment::IsRunning() && timers.empty() && tasks->queue.empty() && tasks->ui.empty() && queue->commands.empty()) break;
        }
        drain(); RE::InventoryMenu::grouped = false;
        assert(changed && player->rows[&ring].total == 128 && banks[Container::Armor]->rows[&ring].total == 0);
        assert(player->rows[&note].total == 0 && banks[Container::Notes]->rows[&note].total == 1);
        StartupResult("grouped row equipment markers are rechecked between chunks", true, {{"entry", entry}});
    }
    for (int entry = 0; entry < 3; ++entry) {
        reset(); settings->GSC_OffloadJewelry = settings->GSC_OffloadNotes = true;
        RE::TESBoundObject note{22500}; note.categories = ToMask(ItemCategory::Note);
        player->Put(&note, 1);
        for (int i = 0; i < 129; ++i) player->Put(&ring, 0, 1, &owner, "generation copy " + std::to_string(i));
        player->rows[&ring].extras.front()->uiWorn = true;
        RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        start(entry);
        bool changed = false;
        for (int frame = 0; frame < 500; ++frame) {
            const auto request = PlayerEquipment::pending;
            if (!changed && request && ui->menu && request->rowCursor >= 8) {
                player->rows[&ring].extras[0]->uiWorn = false;
                player->rows[&ring].extras[1]->uiWorn = true;
                RE::TESEquipEvent event{{player}, ring.GetFormID(), 0, 0, true};
                RE::ScriptEventSourceHolder::GetSingleton()->Send(event);
                RE::InventoryUpdateData data{player->GetHandle().native_handle()};
                RE::UIMessage message{std::string(RE::InventoryMenu::MENU_NAME), RE::UI_MESSAGE_TYPE::kInventoryUpdate, &data};
                static_cast<RE::InventoryMenu*>(ui->menu)->ProcessMessage(message);
                changed = true;
            }
            pump();
            if (!PlayerEquipment::IsRunning() && timers.empty() && tasks->queue.empty() && tasks->ui.empty() && queue->commands.empty()) break;
        }
        drain();
        assert(changed && player->rows[&ring].total == 129 && banks[Container::Armor]->rows[&ring].total == 0);
        assert(player->rows[&note].total == 0 && banks[Container::Notes]->rows[&note].total == 1);
        StartupResult("equip event invalidates a group changed during sliced inspection", true, {{"entry", entry}});
    }
    for (int entry = 0; entry < 3; ++entry) {
        reset(); settings->GSC_OffloadJewelry = true;
        for (int i = 0; i < 1000; ++i) player->Put(&ring, 0, 1, &owner, "cancelled capture " + std::to_string(i));
        const auto input = RE::input; const int shows = queue->shows;
        start(entry);
        bool cancelled = false;
        for (int frame = 0; frame < 100; ++frame) {
            const auto request = PlayerEquipment::pending;
            if (!cancelled && request && request->phase == PlayerEquipment::Phase::Capturing && request->physical.offset > 0) {
                TransferFeedback::Reset(); cancelled = true;
            }
            pump();
            if (cancelled && !PlayerEquipment::IsRunning() && timers.empty() && tasks->queue.empty() && tasks->ui.empty()) break;
        }
        drain();
        assert(cancelled && RE::input == input && queue->shows == shows && player->rows[&ring].total == 1000 && StartupProbe::confirmations == 0);
        StartupResult("feedback cancellation discards pending capture without opening inventory", true, {{"entry", entry}});
    }
#endif
    reset();
    *settings = originalSettings;
    StartupProbe::afterShow = StartupProbe::beforeUpdate = {};
    utility->containers.clear(); utility->containerMap.clear();
}
