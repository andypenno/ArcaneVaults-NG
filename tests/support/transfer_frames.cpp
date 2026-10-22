int main(int argc, char** argv) {
    auto* player = RE::PlayerCharacter::GetSingleton();
    auto* utility = Utility::GetSingleton();
    auto* stores = Stores::GetSingleton();
    auto* ui = RE::UI::GetSingleton();
    auto* tasks = SKSE::GetTaskInterface();
    auto* queue = RE::UIMessageQueue::GetSingleton();
    SKSEMenuFramework::installed = true;
    TransferFeedback::Register();
    std::map<Container, std::unique_ptr<RE::TESObjectREFR>> banks;
    for (auto kind : {Container::Armor, Container::Weapon, Container::Book, Container::Notes, Container::Scroll,
        Container::SpellTomes, Container::SkillBooks, Container::Recipes, Container::Maps, Container::Concoction,
        Container::Potion, Container::Poison, Container::Restorative, Container::HealthPotions,
        Container::MagickaPotions, Container::StaminaPotions, Container::Gear, Container::Instruments,
        Container::Soulgem, Container::EmptySoulgems, Container::FilledSoulgems, Container::Smithing,
        Container::Crafting, Container::Smelting, Container::Construction, Container::Tanning, Container::Gemstone, Container::Remains,
        Container::Sort, Container::Keys, Container::Junk, Container::Personal, Container::Treasure,
        Container::Ammunition, Container::Food, Container::Alchemy}) {
        banks[kind] = std::make_unique<RE::TESObjectREFR>(19000 + static_cast<unsigned>(kind));
        utility->containers[kind] = banks[kind].get();
    }
    RE::TESObjectREFR chest{18000}, assignment{18001};
    utility->containerMap[Container::QuickTransfer] = {&assignment, [](auto*) { Stores::GetSingleton()->OffloadItems(); }};
    auto draw = [] {
        ImGuiMCP::renderTime = FrameProbe::Now() / 1000;
        ImGuiMCP::fills.clear(); ImGuiMCP::outlines.clear(); ImGuiMCP::lineColors.clear();
        SKSEMenuFramework::render();
    };
    auto pump = [&] {
        draw();
        ProbeClock::tick += std::chrono::milliseconds(16);
        queue->ProcessCommands();
        auto ready = std::move(timers); timers.clear();
        for (auto& timer : ready) timer();
        tasks->RunUI(); tasks->Run();
    };
    auto idle = [&] {
        return !PlayerEquipment::IsRunning() && timers.empty() && tasks->ui.empty() && tasks->queue.empty() && queue->commands.empty();
    };
    for (bool yielding : {false, true}) {
        ProbeClock::tick = {}; FrameProbe::Reset("control");
        for (int i = 0; i < 1000; ++i) {
            FrameProbe::Unit("control");
            if (yielding && i % 32 == 31) FrameProbe::Draw();
        }
        FrameProbe::Observe();
        assert((FrameProbe::maxGap <= 50) == yielding);
        std::cout << "{\"control\":\"" << (yielding ? "bounded chunks" : "uninterrupted loop")
            << "\",\"passed\":true,\"max_gap_ms\":" << FrameProbe::maxGap << "}\n";
        FrameProbe::enabled = false;
    }
    for (const auto* phase : {"native inventory", "native menu", "native bulk"}) {
        ProbeClock::tick = {}; FrameProbe::Reset(phase);
        FrameProbe::Opaque(phase); FrameProbe::Opaque(phase); FrameProbe::Observe();
        assert(FrameProbe::maxGap == 250 && FrameProbe::units == 1 && FrameProbe::draws == 0 && FrameProbe::worstPhase == phase);
        std::cout << "{\"control\":\"" << phase << "\",\"passed\":true,\"max_gap_ms\":250}\n";
        FrameProbe::enabled = false;
    }
    struct Expected {
        RE::TESBoundObject* item;
        RE::ExtraDataList* identity;
        RE::ExtraDataList metadata;
        RE::TESObjectREFR* destination;
    };
    const std::vector<std::string> phases{"capture", "protected capture", "row indexing", "row matching",
        "delayed rows", "validation", "candidate enumeration", "job expansion", "soul gem recovery", "distinct soul gems",
        "native inventory", "native menu", "native bulk", "cancel during readiness",
        "capture prefix", "validation prefix", "row prefix", "transfer stack scan", "misc stack scan", "soul gem scan",
        "destination count scan", "archive listing scan", "remains recovery", "remains archive"};
    const std::vector<std::string> callPhases{"native capture read", "native validation read", "native transfer read",
        "native row member", "native menu population", "native recovery refresh", "native menu close", "native item removal"};
    auto scenarios = phases;
    scenarios.insert(scenarios.end(), callPhases.begin(), callPhases.end());
    if (argc > 1) scenarios.assign(argv + 1, argv + argc);
    for (int entry = 0; entry < 3; ++entry) for (const auto& phase : scenarios) for (int size : {1, 1000})
    for (int delay : phase.starts_with("native ") ? std::vector<int>{0, 250} : std::vector<int>{250}) {
        assert(idle() && !ui->menu);
        TransferFeedback::Reset(); FrameProbe::enabled = false;
        *Settings::GetSingleton() = Settings{};
        RE::InventoryMenu::grouped = phase == "row prefix" || phase == "transfer stack scan";
        auto* settings = Settings::GetSingleton();
        settings->GSC_SoulgemKeepAmount = 0;
        settings->GSC_OffloadJewelry = settings->GSC_OffloadNotes = settings->GSC_OffloadPotion = true;
        player->rows.clear(); RE::SCRIPT_FUNCTION::equipped.clear();
        for (auto& [kind, bank] : banks) { (void)kind; bank->rows.clear(); }
        ui->messageBox = false; stores->options.clear(); stores->ResetNavigation();
        std::vector<std::unique_ptr<RE::TESBoundObject>> objects;
        RE::TESBoundObject ring{21000, false, true}, favorite{21001}, quest{21002}, ignored{21003};
        ring.categories = ItemCategory::Armor | ItemCategory::Jewelry;
        favorite.categories = ItemCategory::Concoction | ItemCategory::Potion;
        quest.categories = ignored.categories = ToMask(ItemCategory::Note);
        RE::TESForm owner{21004}; owner.playerOwned = true;
        RE::TESSoulGem gem{21005};
        RE::EnchantmentItem enchanted, spareEnchantment;
        std::vector<Expected> expected;
        auto put = [&](auto* from, auto* item, auto* destination, std::string name) {
            from->Put(item, 0, 1, &owner, name);
            return std::pair{from->rows[item].extras.back().get(), destination};
        };
        auto remember = [&](auto value, auto* item) {
            expected.push_back({item, value.first, *value.first, value.second});
        };
        auto worn = put(player, &ring, player, "worn favourite enchanted ring");
        worn.first->hotkey = true; worn.first->uiWorn = true; worn.first->enchantment = RE::ExtraEnchantment{&enchanted};
        remember(worn, &ring); RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        auto f = put(player, &favorite, player, "favourite potion"); f.first->hotkey = true; remember(f, &favorite);
        remember(put(player, &quest, player, "quest object"), &quest); player->rows[&quest].quest = true;
        remember(put(player, &ignored, player, "ignored object"), &ignored); settings->ignored.insert(&ignored);
        const bool equipment = phase == "capture" || phase == "protected capture" || phase == "row indexing" ||
            phase == "row matching" || phase == "delayed rows" || phase == "validation" || phase == "native menu" ||
            phase == "cancel during readiness" || phase == "transfer stack scan" || phase.ends_with(" prefix") || std::ranges::find(callPhases, phase) != callPhases.end();
        const bool cancel = phase == "cancel during readiness";
        const int copies = phase == "destination count scan" ? 1 : size;
        for (int i = 0; i < copies; ++i) {
            RE::TESObjectREFR* source = player;
            auto* destination = banks[Container::Notes].get();
            RE::TESBoundObject* item{};
            if ((phase.ends_with(" prefix") || phase.ends_with(" stack scan") || phase == "archive listing scan" || phase.starts_with("remains ")) && !objects.empty()) item = objects.front().get();
            else if (phase == "row matching") item = &ring;
            else if (phase == "soul gem recovery" || phase == "soul gem scan") item = &gem;
            else {
                if (phase == "distinct soul gems") objects.push_back(std::make_unique<RE::TESSoulGem>(22000 + i));
                else objects.push_back(std::make_unique<RE::TESBoundObject>(22000 + i, false, equipment));
                item = objects.back().get();
                item->categories = equipment ? ItemCategory::Armor | ItemCategory::Jewelry : ToMask(ItemCategory::Note);
            }
            if (equipment) destination = phase == "protected capture" || cancel ? player : banks[Container::Armor].get();
            if (phase == "native bulk" || phase == "archive listing scan") source = banks[Container::Maps].get();
            if (phase.starts_with("remains ")) {
                item->categories = ItemCategory::Remains | ItemCategory::Smithing;
                source = banks[phase == "remains recovery" ? Container::Junk : Container::Remains].get();
                destination = banks[Container::Smithing].get();
            }
            if (phase == "soul gem recovery" || phase == "soul gem scan" || phase == "distinct soul gems") {
                source = banks[Container::Crafting].get(); destination = banks[Container::Soulgem].get();
            }
            auto value = put(source, item, destination, "copy " + std::to_string(i));
            if (equipment) value.first->enchantment = RE::ExtraEnchantment{&spareEnchantment};
            if (phase == "protected capture") value.first->hotkey = true;
            remember(value, item);
        }
        if (phase == "destination count scan") {
            auto* item = objects.front().get();
            auto* destination = banks[Container::Notes].get();
            for (int i = 0; i < size; ++i)
                remember(put(destination, item, destination, "stored copy " + std::to_string(i)), item);
        }
        ProbeClock::tick = {};
        const std::string cost = phase == "protected capture" ? "capture" :
            phase == "delayed rows" || cancel ? "row indexing" : phase == "distinct soul gems" ? "soul gem recovery" : phase;
        FrameProbe::Reset(cost);
        FrameProbe::nativeDelay = delay;
        int shownFrame = -1, frame = 0;
        if (phase == "delayed rows" || cancel || phase == "native recovery refresh") FrameProbe::afterShow = [&] {
            if (phase != "native recovery refresh") shownFrame = frame;
            auto* menu = static_cast<RE::InventoryMenu*>(ui->menu);
            for (auto* row : menu->list.items) row->obj.kind = RE::GFxValue::Undefined;
        };
        const auto input = RE::input;
        const auto blocked = RE::PlayerControls::GetSingleton()->blockPlayerInput;
        bool completed = false, cancelled = false;
        if (entry == 0) {
            stores->ShowVaultMenu(&chest);
            auto option = std::ranges::find_if(stores->options, [](auto& value) { return value.text == "Vault.ArcaneOffload"; });
            assert(option != stores->options.end());
            auto action = option->action; stores->options.clear(); ui->messageBox = false; action();
        } else if (entry == 1) assert(utility->RunContainerAction(&assignment, &chest));
        else stores->OffloadItems([&] { completed = true; });
        for (frame = 0; frame < 1500 && !idle(); ++frame) {
            if (shownFrame >= 0 && frame - shownFrame >= (cancel ? 2 : 4) && (!cancel || FrameProbe::units > 0)) {
                if (cancel && !cancelled) {
                    TransferFeedback::Reset(); PlayerEquipment::Reset(); cancelled = true;
                } else if (!cancel && ui->menu) {
                    auto* menu = static_cast<RE::InventoryMenu*>(ui->menu);
                    for (auto* row : menu->list.items) row->obj.kind = RE::GFxValue::Object;
                }
            }
            pump();
        }
        FrameProbe::Observe();
        if (!idle()) std::cerr << "Quick Transfer did not complete: phase=" << phase << " size=" << size
            << " entry=" << entry << " traversal_units=" << FrameProbe::units << " max_gap_ms=" << FrameProbe::maxGap << '\n';
        if (!idle() && PlayerEquipment::pending) std::cerr << "Inspection cursor: row=" << PlayerEquipment::pending->rowCursor
            << " extra=" << PlayerEquipment::pending->extraCursor << " phase=" << static_cast<int>(PlayerEquipment::pending->phase) << '\n';
        assert(idle() && !ui->menu && RE::input == input && RE::PlayerControls::GetSingleton()->blockPlayerInput == blocked);
        assert(!InventoryPreview::active);
        RE::InputEvent button; assert(!SKSEMenuFramework::block(&button));
        assert(FrameProbe::confirmations == (cancel ? 0 : 1));
        if (entry == 2) assert(completed == !cancel);
        int actualCount = 0;
        auto check = [&](auto* source) {
            for (const auto& [item, row] : source->rows) {
                (void)item; actualCount += row.total;
                assert(row.total == static_cast<int>(row.extras.size()));
            }
        };
        check(player); for (auto& [kind, bank] : banks) { (void)kind; check(bank.get()); }
        assert(actualCount == static_cast<int>(expected.size()));
        for (const auto& value : expected) {
            const auto& extras = value.destination->rows[value.item].extras;
            const auto matches = std::ranges::count_if(extras, [&](const auto& extra) {
                return (value.destination != player || extra.get() == value.identity) &&
                    extra->count == 1 && extra->Same(value.metadata);
            });
            if (matches != 1) std::cerr << "Metadata mismatch " << phase << " size=" << size << " entry=" << entry
                << " item=" << value.item->id << " copy=" << value.metadata.metadata << " matches=" << matches << '\n';
            assert(matches == 1);
        }
        const bool opaque = phase.starts_with("native ");
        if (FrameProbe::opaqueCharged) {
            assert(FrameProbe::units == 1);
            if (delay) assert(FrameProbe::maxGap >= delay && FrameProbe::worstPhase == phase);
            else assert(FrameProbe::maxGap <= 50);
        }
        else if (!opaque) {
            if (!FrameProbe::units) std::cerr << "Unexercised phase " << phase << " size=" << size << " entry=" << entry << '\n';
            assert(FrameProbe::units > 0);
        }
        if (std::ranges::find(callPhases, phase) != callPhases.end()) {
            assert(FrameProbe::opaqueCharged && FrameProbe::drawsBeforeOpaque > 0);
            assert(FrameProbe::draws > FrameProbe::drawsBeforeOpaque);
        }
        const bool passed = (opaque && FrameProbe::opaqueCharged) || FrameProbe::maxGap <= 50;
        std::cout << "{\"entry\":" << entry << ",\"phase\":\"" << phase << "\",\"size\":" << size
            << ",\"injected_delay_ms\":" << (opaque ? delay : 0) << ",\"draws_before_call\":" << FrameProbe::drawsBeforeOpaque
            << ",\"copies\":" << copies << ",\"units\":" << FrameProbe::units << ",\"draws\":" << FrameProbe::draws
            << ",\"destination_copies\":" << (phase == "destination count scan" ? size : 0)
            << ",\"max_gap_ms\":" << FrameProbe::maxGap << ",\"worst_phase\":\"" << FrameProbe::worstPhase
            << "\",\"opaque_control\":" << (opaque ? "true" : "false")
            << ",\"opaque_call_observed\":" << (FrameProbe::opaqueCharged ? "true" : "false")
            << ",\"safety_passed\":true,\"passed\":" << (passed ? "true" : "false") << ",\"draw_gaps_ms\":[";
        for (std::size_t i = 0; i < FrameProbe::gaps.size(); ++i) {
            if (i) std::cout << ',';
            std::cout << FrameProbe::gaps[i];
        }
        std::cout << "]}\n";
        FrameProbe::enabled = false; FrameProbe::afterShow = {};
        RE::InventoryMenu::grouped = false;
    }
}
