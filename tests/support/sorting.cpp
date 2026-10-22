#include "extern/json/single_include/nlohmann/json.hpp"
#include <fstream>

SORTING_DEFINITIONS

int main(int argc,char** argv) {
    assert(argc==2);
    nlohmann::json data;
    std::ifstream(argv[1]) >> data;
    SKSEMenuFramework::installed=true;TransferFeedback::Register();
    for(int entry=0;entry<3;++entry) {
        auto* player=RE::PlayerCharacter::GetSingleton();
        auto* utility=Utility::GetSingleton();auto* settings=Settings::GetSingleton();auto* stores=Stores::GetSingleton();
        auto* tasks=SKSE::GetTaskInterface();auto* queue=RE::UIMessageQueue::GetSingleton();
        PlayerEquipment::Reset();TransferFeedback::Reset();queue->ProcessCommands();
        player->rows.clear();settings->ignored.clear();RE::SCRIPT_FUNCTION::equipped.clear();
        utility->containers.clear();utility->containerMap.clear();timers.clear();ProbeClock::tick={};
        RE::UI::GetSingleton()->messageBox=false;stores->options.clear();stores->ResetNavigation();
        *settings=Settings{};Configure(settings,data.at("settings"));
        std::map<std::string,std::unique_ptr<RE::TESObjectREFR>> banks;
        std::map<std::string,RE::TESObjectREFR*> inventories{{"player",player}};
        for(const auto& [name,kind]:containerNames) {
            if(kind==Container::None || kind==Container::Master || kind==Container::QuickTransfer)continue;
            banks[name]=std::make_unique<RE::TESObjectREFR>(9000+static_cast<unsigned>(kind));
            utility->containers[kind]=banks[name].get();inventories[name]=banks[name].get();
        }
        std::map<std::string,std::unique_ptr<RE::TESBoundObject>> bases;
        for(const auto& [id,item]:data.at("bases").items()) {
            const auto form=1000+static_cast<unsigned>(bases.size());
            if(item.at("kind")=="soulgem")bases[id]=std::make_unique<RE::TESSoulGem>(form);
            else bases[id]=std::make_unique<RE::TESBoundObject>(form,item.at("kind")=="weapon",item.at("kind")=="armor");
            for(const std::string category:item.at("categories"))bases[id]->categories|=ToMask(itemcategoryNames.at(category));
        }
        std::map<std::string,std::unique_ptr<RE::EnchantmentItem>> enchantments;
        std::map<std::string,std::unique_ptr<RE::TESForm>> owners;
        std::map<std::string,nlohmann::json> originals;
        std::map<std::string,std::map<std::string,int>> expected;
        for(const auto& row:data.at("rows")) {
            const std::string id=row.at("id"),base=row.at("base"),inventory=row.at("inventory");
            const auto owner=row.value("owner",std::string{}),enchantment=row.value("enchantment",std::string{});
            if(!owner.empty() && !owners.contains(owner))owners[owner]=std::make_unique<RE::TESForm>(RE::TESForm{7000+static_cast<unsigned>(owners.size())});
            if(!enchantment.empty() && !enchantments.contains(enchantment))enchantments[enchantment]=std::make_unique<RE::EnchantmentItem>();
            auto* item=bases.at(base).get();auto* ref=inventories.at(inventory);
            ref->Put(item,0,row.at("count"),owner.empty()?nullptr:owners.at(owner).get(),id);
            auto& extra=ref->rows[item].extras.back();
            extra->displayName=row.value("name",data.at("bases").at(base).at("name").get<std::string>());
            extra->hotkey=row.value("favorite",false);extra->worn=row.value("worn",false);extra->uiWorn=extra->worn;
            extra->charge=row.value("charge",0.0);extra->temper=row.value("temper",0.0);
            if(row.value("soul",0))extra->soul=RE::ExtraSoul{static_cast<RE::SOUL_LEVEL>(row.at("soul").get<int>())};
            if(!enchantment.empty())extra->enchantment=RE::ExtraEnchantment{enchantments.at(enchantment).get()};
            ref->rows[item].quest|=row.value("quest",false);
            if(inventory=="player" && extra->worn)RE::SCRIPT_FUNCTION::equipped.insert(item);
            if(row.value("ignored",false))settings->ignored.insert(item);
            for(const auto& [destination,count]:row.at("after").items())expected[destination][id]=count;
            originals[id]=row;
        }
        RE::TESObjectREFR chest{8000},assignment{8001};
        utility->containerMap[Container::QuickTransfer]={&assignment,[](auto*){Stores::GetSingleton()->OffloadItems();}};
        const auto input=RE::input;const bool blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        const int shows=queue->shows;RE::removeCalls=RE::inventoryReads=RE::bulkCalls=0;
        RE::SendHUDMessage::message.clear();
        const auto start=std::chrono::steady_clock::now();
        if(entry==0) {
            stores->ShowVaultMenu(&chest);
            const auto selected=std::ranges::find_if(stores->options,[](auto& option){return option.text=="Vault.ArcaneOffload";});
            assert(selected!=stores->options.end());auto action=selected->action;stores->options.clear();
            RE::UI::GetSingleton()->messageBox=false;action();
        } else if(entry==1)assert(utility->RunContainerAction(&assignment,&chest));
        else stores->OffloadItems();
        int frames=0;
        do {
            SKSEMenuFramework::render();ProbeClock::tick+=std::chrono::milliseconds(16);queue->ProcessCommands();
            auto ready=std::move(timers);timers.clear();for(auto& action:ready)action();tasks->RunUI();tasks->Run();++frames;
        } while((PlayerEquipment::IsRunning() || !timers.empty() || !tasks->ui.empty() || !tasks->queue.empty() || !queue->commands.empty()) && frames<10000);
        const auto elapsed=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        assert(frames<10000 && !PlayerEquipment::IsRunning() && !RE::UI::GetSingleton()->menu);
        assert(RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked && !SKSEMenuFramework::block(nullptr));
        for(const auto& [name,ref]:inventories) {
            std::map<std::string,int> actual;
            for(const auto& stack:InventoryStacks::Read(ref)) {
                assert(stack.extra);const auto& id=stack.extra->metadata;const auto& row=originals.at(id);
                assert(stack.item==bases.at(row.at("base")).get());actual[id]+=stack.count;
                assert(stack.extra->displayName==row.value("name",data.at("bases").at(row.at("base").get<std::string>()).at("name").get<std::string>()));
                assert(stack.extra->hotkey==row.value("favorite",false) && stack.extra->worn==row.value("worn",false));
                assert(stack.extra->charge==row.value("charge",0.0) && stack.extra->temper==row.value("temper",0.0));
                assert(static_cast<int>(stack.extra->soul?stack.extra->soul->soul:RE::SOUL_LEVEL::kNone)==row.value("soul",0));
                const auto owner=row.value("owner",std::string{}),enchantment=row.value("enchantment",std::string{});
                assert(stack.extra->owner==(owner.empty()?nullptr:owners.at(owner).get()));
                assert((stack.extra->enchantment?stack.extra->enchantment->enchantment:nullptr)==(enchantment.empty()?nullptr:enchantments.at(enchantment).get()));
            }
            if(actual!=expected[name]) {std::cerr<<data.at("name")<<" entry "<<entry<<" inventory "<<name<<" actual "<<nlohmann::json(actual)<<" expected "<<nlohmann::json(expected[name])<<'\n';return 1;}
        }
        if(data.at("no_transfers").get<bool>())assert(RE::removeCalls==0 && queue->shows==shows);
        std::cout<<"{\"name\":"<<data.at("name")<<",\"entry\":"<<entry<<",\"stacks\":"<<data.at("rows").size()<<",\"fixture_elapsed_ms\":"<<elapsed<<",\"simulated_frames\":"<<frames<<",\"remove_calls\":"<<RE::removeCalls<<",\"inventory_reads\":"<<RE::inventoryReads<<"}\n";
        player->rows.clear();
    }
}
