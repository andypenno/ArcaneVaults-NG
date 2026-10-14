"""Exercise enchanted-copy lending and real crafting-session routing with engine stubs."""

from pathlib import Path
import argparse
import json
import hashlib
import os
import statistics
import signal
import atexit
import subprocess
import tempfile

import check_stolen

ROOT = check_stolen.ROOT
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sanitize", action="store_true", help="Check native memory access and undefined behaviour")
parser.add_argument("--probe-deliveries", type=Path, help="Record alternative native dispatch and receipt orders")
parser.add_argument("--time-deliveries", type=Path, help="Measure synchronous and deferred loan phases at 100/1000 copies or stacks")
parser.add_argument("--samples", type=int, default=3)
parser.add_argument("--sizes", type=int, nargs="+", default=[100,1000])
args = parser.parse_args()
if args.time_deliveries and (args.probe_deliveries or args.sanitize):
    parser.error("Timing runs exclude the delivery probe and sanitizers")
common = check_stolen.common.replace(
    "struct Settings {", "struct Settings {bool GSC_CraftingLoan=false,GSC_EnchantedItemsLoan=false;"
).replace(
    "struct Utility {", "struct Utility {BenchType bench=BenchType::None;BenchType GetBenchType(RE::TESObjectREFR*)const{return bench;}"
).replace(
    "struct Stores {", """struct Stores {
    int materialLoans=0,materialReturns=0,junkLoans=0,junkReturns=0;
    std::unordered_map<RE::FormID,std::pair<int,int>> junkLoan_;
    void BeginJunkLoan();void EndJunkLoan();void ResetJunkLoan(){junkLoan_.clear();}
    void AllToPlayer(Container){++materialLoans;}void StoreToPlayer(ItemCategory,Container){++materialLoans;}
"""
)
common += r'''
namespace Soulgems {
    inline int loans=0,returns=0;
    inline void BeginLoan(bool){++loans;}inline void EndLoan(){++returns;}inline void ResetLoan(){}
}
'''
common = common.replace(
    "bool refuse=false;unsigned changed=0;",
    "bool refuse=false,replaceExtras=false;int successfulMoves=0,refuseAfter=INT_MAX;unsigned changed=0;"
).replace(
    "row.total-=count;out.total+=count;",
    """row.total-=count;out.total+=count;
        if(replaceExtras)for(auto& remaining:row.extras)remaining=std::make_shared<ExtraDataList>(*remaining);
        if(++successfulMoves>=refuseAfter)refuse=true;"""
)
common = common.replace(
    "int bulkTransfers=0,bulkLimit=", "std::function<void()> duringDispatch{};int bulkTransfers=0,bulkLimit="
).replace(
    "auto snapshot=source->GetInventoryCounts();int remaining=bulkLimit;",
    "if(duringDispatch){duringDispatch();}auto snapshot=source->GetInventoryCounts();int remaining=bulkLimit;"
)
common=common.replace("if(deferTransfers && target->id==0x14){", "if(changes.duringDispatch && target->id==0x14){auto callback=std::exchange(changes.duringDispatch,{});callback();}if(deferTransfers && target->id==0x14){")
events = (ROOT / "src/Events.cpp").read_text()
loan = events[events.index("class CraftingLoanState {"):events.index("class FurnitureActivation {")]
start = events.index("    static bool ActivateCraftLoan(")
hook = events[start:events.index("\n    }", start) + 6]
start = events.index("    RE::BSEventNotifyControl ProcessEvent(", events.index("class CraftingMenuEventHandler"))
close_handler = events[start:events.index("\n    }", start) + 6].replace(" ProcessEvent(", " CraftingCloseEvent(").replace(" override", "")
stores_source = (ROOT / "src/Stores.cpp").read_text()
start = stores_source.index("    int MoveItems(")
junk = stores_source[start:stores_source.index("\n    }", start) + 6]
for name, counter in (("BeginJunkLoan", "junkLoans"), ("EndJunkLoan", "junkReturns")):
    start = stores_source.index(f"void Stores::{name}(")
    body = stores_source[start:stores_source.index("\n}\n", start) + 3]
    junk += body.replace(f"void Stores::{name}() {{", f"void Stores::{name}() {{++{counter};")
program = '#include "common.hpp"\n' + junk + loan + r'''
namespace RE {
struct CraftingMenu {inline static constexpr std::string_view MENU_NAME="CraftingMenu";};
struct MenuOpenCloseEvent {std::string menuName;bool opening;};
struct TESFurniture {
    struct WorkBenchData {enum class BenchType {kNone,kEnchanting};};
    struct Field {WorkBenchData::BenchType value=WorkBenchData::BenchType::kEnchanting;auto get()const{return value;}};
    struct {Field benchType;} workBenchData;
    bool activation=true;
};
}
bool NativeActivate(RE::TESFurniture* base,RE::TESObjectREFR*,RE::TESObjectREFR*,std::uint8_t,RE::TESBoundObject*,std::int32_t){return base->activation;}
auto activate_=NativeActivate;
''' + hook + close_handler + r'''
void Stores::PlayerToStore(ItemCategory,Container,int,int,bool,CategoryMask){++materialReturns;}
int main() {
    auto* player=RE::PlayerCharacter::GetSingleton();auto* u=Utility::GetSingleton();
    auto* settings=Settings::GetSingleton();auto* stores=Stores::GetSingleton();
    auto* session=CraftingLoanState::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    RE::TESObjectREFR weapons{1001},armor{1002},archive{1003},bench{1004},consumed{1005},junkBank{1006};
    u->containers[Container::Weapon]=&weapons;u->containers[Container::Armor]=&armor;u->containers[Container::EnchantedItems]=&archive;u->containers[Container::Junk]=&junkBank;
    EnchantedItems::Init();
    RE::EnchantmentItem normal;RE::TESForm owner{300,false};
    RE::TESBoundObject sword{200,true},helmet{201,false,true},artifact{202,true},staff{203,true},plain{204,true};
    sword.enchantable.formEnchanting=helmet.enchantable.formEnchanting=&normal;
    artifact.enchantable.formEnchanting=&normal;artifact.keywords.blocked=true;
    staff.enchantable.formEnchanting=&normal;staff.weaponData.staff=true;
    auto count=[](auto& ref,auto& item){return InventoryStacks::Count(&ref,&item);};
    auto reset=[&] {
        session->Reset();EnchantedItems::Reset();tasks->Run();
        for(auto* ref:std::array<RE::TESObjectREFR*,6>{player,&weapons,&armor,&archive,&consumed,&junkBank}){
            ref->rows.clear();ref->refuse=ref->replaceExtras=false;ref->limit=ref->refuseAfter=INT_MAX;ref->successfulMoves=0;
            ref->missingChanges=false;ref->changes.bulkTransfers=0;ref->changes.bulkLimit=INT_MAX;
            ref->changes.bulkRefuse=ref->changes.lastKeepOwnership=false;
            ref->deferTransfers=false;ref->deliveries.clear();
            ref->changes.duringDispatch={};
        }
        RE::SCRIPT_FUNCTION::equipped.clear();settings->GSC_CraftingLoan=settings->GSC_EnchantedItemsLoan=false;
        u->bench=BenchType::Enchanting;stores->materialLoans=stores->materialReturns=stores->junkLoans=stores->junkReturns=0;
        Soulgems::loans=Soulgems::returns=0;
    };
    auto seed=[&]{weapons.Put(&sword,0,3,&owner,"borrowed sword");armor.Put(&helmet,0,2,&owner,"borrowed helmet");};
    reset();seed();session->EnterCrafting(&bench);session->ExitCrafting();
    assert(count(weapons,sword)==3 && count(*player,sword)==0 && Soulgems::loans==0 && stores->junkLoans==0);

    reset();seed();settings->GSC_EnchantedItemsLoan=true;
    player->Put(&sword,0,1,&owner,"carried sword");auto* carried=player->rows[&sword].extras.front().get();
    weapons.Put(&artifact,2);weapons.Put(&staff,2);weapons.Put(&plain,2);
    session->EnterCrafting(&bench);tasks->Run();
    assert(count(*player,sword)==4 && count(*player,helmet)==2 && count(weapons,sword)==0 && count(archive,sword)==0);
    assert(archive.changes.bulkTransfers==0);
    assert(count(weapons,artifact)==2 && count(weapons,staff)==2 && count(weapons,plain)==2);
    assert(Soulgems::loans==0 && stores->junkLoans==0 && stores->materialLoans==0);
    auto* borrowed=player->rows[&sword].extras.back().get();
    assert(borrowed->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword)==&weapons);
    player->RemoveItem(&sword,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,borrowed,&consumed);
    settings->GSC_EnchantedItemsLoan=false;session->ExitCrafting();
    assert(count(*player,sword)==1 && player->rows[&sword].extras.front().get()==carried);
    assert(count(weapons,sword)==2 && count(armor,helmet)==2 && count(*player,helmet)==0);
    assert(weapons.rows[&sword].extras.front()->owner==&owner && weapons.rows[&sword].extras.front()->metadata=="borrowed sword");
    assert(!weapons.rows[&sword].extras.front()->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
    session->ExitCrafting();assert(count(weapons,sword)==2 && stores->materialReturns==0 && Soulgems::returns==0);

    for(auto type:{BenchType::None,BenchType::Alchemy,BenchType::Smithing,BenchType::Cooking,BenchType::StaffEnchanting}) {
        reset();seed();settings->GSC_EnchantedItemsLoan=true;u->bench=type;
        session->EnterCrafting(&bench);session->ExitCrafting();
        assert(count(weapons,sword)==3 && count(*player,sword)==0 && Soulgems::loans==0 && stores->junkLoans==0);
    }
    for(auto type:{BenchType::Alchemy,BenchType::Smithing,BenchType::Cooking,BenchType::Enchanting,BenchType::StaffEnchanting}){
        reset();seed();settings->GSC_CraftingLoan=settings->GSC_EnchantedItemsLoan=true;u->bench=type;
        session->EnterCrafting(&bench);
        RE::TESFurnitureEvent exit{{player},{&bench},RE::TESFurnitureEvent::FurnitureEventType::kExit};
        session->FurnitureEvent(exit);tasks->Run();
        assert(stores->junkLoans==1 && stores->junkReturns==1 && !EnchantedItems::HasPendingLoan());
        assert(count(*player,sword)==0 && count(weapons,sword)==3 && count(armor,helmet)==2);
        if(type==BenchType::Smithing || type==BenchType::Enchanting)assert(Soulgems::loans==1 && Soulgems::returns==1);
    }
    reset();seed();settings->GSC_CraftingLoan=true;session->EnterCrafting(&bench);
    assert(count(weapons,sword)==3 && Soulgems::loans==1 && stores->junkLoans==1);
    settings->GSC_CraftingLoan=false;session->ExitCrafting();assert(Soulgems::returns==1 && stores->junkReturns==1);
    reset();seed();settings->GSC_CraftingLoan=settings->GSC_EnchantedItemsLoan=true;session->EnterCrafting(&bench);
    assert(count(*player,sword)==3 && Soulgems::loans==1 && stores->junkLoans==1);
    session->ExitCrafting();assert(count(weapons,sword)==3 && Soulgems::returns==1 && stores->junkReturns==1);

    reset();seed();junkBank.Put(&sword,0,1,&owner,"junk sword");
    settings->GSC_CraftingLoan=settings->GSC_EnchantedItemsLoan=true;session->EnterCrafting(&bench);tasks->Run();
    assert(count(*player,sword)==4);session->ExitCrafting();
    assert(count(*player,sword)==0 && count(weapons,sword)==3 && count(junkBank,sword)==1);
    assert(junkBank.rows[&sword].extras.front()->metadata=="junk sword");

    reset();EnchantedItems::BeginLoan();EnchantedItems::EndLoan();assert(archive.changes.bulkTransfers==0);
    for(bool overflow:{false,true}) {
        reset();seed();const int held=INT_MAX-(overflow?2:3);player->Put(&sword,held);
        EnchantedItems::BeginLoan();
        assert(archive.changes.bulkTransfers==0);
        assert(count(*player,sword)==held+(overflow?0:3));
        EnchantedItems::EndLoan();
        assert(count(*player,sword)==held && count(weapons,sword)==3 && count(armor,helmet)==2);
    }
    for(int failure=0;failure<3;++failure) {
        reset();seed();player->Put(&sword,0,2,&owner,"carried");
        archive.changes.bulkRefuse=failure==0;archive.changes.bulkLimit=failure==1?2:INT_MAX;
        archive.missingChanges=failure==2;
        EnchantedItems::BeginLoan();tasks->Run();EnchantedItems::EndLoan();
        assert(archive.changes.bulkTransfers==0);
        assert(count(*player,sword)==2 && count(*player,helmet)==0 && count(weapons,sword)==3 && count(armor,helmet)==2);
        assert(count(archive,sword)==0 && count(archive,helmet)==0 && player->rows[&sword].extras.front()->metadata=="carried");
    }
    reset();seed();archive.rows[&sword].duplicate=true;EnchantedItems::BeginLoan();
    assert(archive.changes.bulkTransfers==0 && count(*player,sword)==0 && count(weapons,sword)+count(archive,sword)==3);
    archive.rows[&sword].duplicate=false;assert(EnchantedItems::Recover() && count(weapons,sword)==3);
    reset();seed();archive.limit=1;EnchantedItems::BeginLoan();tasks->Run();player->limit=1;
    EnchantedItems::EndLoan();assert(count(weapons,sword)==3 && count(armor,helmet)==2 && count(*player,sword)==0);
    reset();weapons.Put(&sword,70000);EnchantedItems::BeginLoan();tasks->Run();EnchantedItems::EndLoan();
    assert(count(weapons,sword)==70000 && count(*player,sword)==0);

    reset();seed();player->Put(&sword,0,1,&owner,"carried");archive.deferTransfers=true;
    settings->GSC_EnchantedItemsLoan=true;session->EnterCrafting(&bench);session->ExitCrafting();
    assert(count(*player,sword)==1 && archive.deliveries.size()==1);
    while(!archive.deliveries.empty()){
        auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();tasks->Run();
        assert(count(*player,sword)==1 && count(*player,helmet)==0);
    }
    assert(count(weapons,sword)==3 && count(armor,helmet)==2 && player->rows[&sword].extras.front()->metadata=="carried");

    reset();seed();archive.deferTransfers=true;archive.changes.bulkLimit=2;
    EnchantedItems::BeginLoan();assert(EnchantedItems::HasPendingLoan());
    while(!archive.deliveries.empty()){
        auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();tasks->Run();
    }
    assert(!EnchantedItems::HasPendingLoan() && count(*player,sword)==0 && count(*player,helmet)==0);
    assert(count(weapons,sword)==3 && count(armor,helmet)==2);

    reset();seed();archive.changes.duringDispatch=[] { EnchantedItems::EndLoan(); };
    EnchantedItems::BeginLoan();tasks->Run();
    assert(!EnchantedItems::HasPendingLoan() && count(*player,sword)==0 && count(*player,helmet)==0);
    assert(count(weapons,sword)==3 && count(armor,helmet)==2);

    reset();seed();archive.deferTransfers=true;EnchantedItems::BeginLoan();
    while(!archive.deliveries.empty()){
        auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();
    }
    player->RemoveItem(&sword,3,RE::ITEM_REMOVE_REASON::kStoreInContainer,player->rows[&sword].extras.front().get(),&consumed);
    EnchantedItems::EndLoan();tasks->Run();
    assert(!EnchantedItems::HasPendingLoan() && count(consumed,sword)==3 && count(weapons,sword)==0);
    assert(count(*player,helmet)==0 && count(armor,helmet)==2);

    reset();player->Put(&plain,0,2,&owner,"same");player->rows[&plain].extras.back()->enchantment=RE::ExtraEnchantment{&normal};
    RE::EnchantmentItem lateFire,lateFrost;
    for(auto* enchantment:{&lateFire,&lateFrost}){weapons.Put(&plain,0,3,&owner,"same");weapons.rows[&plain].extras.back()->enchantment=RE::ExtraEnchantment{enchantment};}
    archive.deferTransfers=true;archive.limit=1;settings->GSC_EnchantedItemsLoan=true;
    session->EnterCrafting(&bench);session->ExitCrafting();assert(EnchantedItems::HasPendingLoan() && !EnchantedItems::Gather());
    settings->GSC_CraftingLoan=true;u->bench=BenchType::Alchemy;session->EnterCrafting(&bench);
    assert(stores->materialLoans==0 && archive.deliveries.size()==1);
    while(!archive.deliveries.empty()){
        auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();tasks->Run();
        assert(count(*player,plain)==2 && player->rows[&plain].extras.front()->enchantment->enchantment==&normal);
    }
    assert(!EnchantedItems::HasPendingLoan() && count(weapons,plain)==6);
    std::map<RE::EnchantmentItem*,int> lateCounts;
    for(auto& extra:weapons.rows[&plain].extras){assert(extra->owner==&owner && extra->metadata=="same");lateCounts[extra->enchantment->enchantment]+=extra->count;}
    assert((lateCounts==std::map<RE::EnchantmentItem*,int>{{&lateFire,3},{&lateFrost,3}}));
    archive.deferTransfers=false;u->bench=BenchType::Enchanting;session->EnterCrafting(&bench);tasks->Run();session->ExitCrafting();
    assert(count(*player,plain)==2 && count(weapons,plain)==6);

    for(int protection=0;protection<4;++protection){
        reset();seed();archive.deferTransfers=true;EnchantedItems::BeginLoan();EnchantedItems::EndLoan();
        while(!archive.deliveries.empty()){
            auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();
            if(player->rows[&sword].total){
                if(protection==0)player->rows[&sword].favorite=true;
                if(protection==1)player->rows[&sword].quest=true;
                if(protection==2)player->rows[&sword].extras.front()->worn=true;
                if(protection==3)RE::SCRIPT_FUNCTION::equipped.insert(&sword);
            }
            tasks->Run();
        }
        assert(!EnchantedItems::HasPendingLoan() && count(*player,sword)==3 && count(weapons,sword)==0 && count(armor,helmet)==2);
        assert(!InventoryStacks::HasOrigin(player->rows[&sword].extras.front().get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
    }
    reset();seed();settings->GSC_EnchantedItemsLoan=true;session->EnterCrafting(&bench);
    RE::MenuOpenCloseEvent opening{"CraftingMenu",true},closing{"CraftingMenu",false},other{"InventoryMenu",false};
    const auto queued=tasks->queue.size();CraftingCloseEvent(nullptr,nullptr);CraftingCloseEvent(&opening,nullptr);CraftingCloseEvent(&other,nullptr);
    assert(tasks->queue.size()==queued);CraftingCloseEvent(&closing,nullptr);assert(count(*player,sword)==3);
    tasks->Run();assert(count(*player,sword)==0 && count(weapons,sword)==3);
    session->EnterCrafting(&bench);CraftingCloseEvent(&closing,nullptr);session->EnterCrafting(&bench);tasks->Run();
    assert(count(*player,sword)==3 && count(weapons,sword)==0);session->ExitCrafting();
    session->EnterCrafting(&bench);CraftingCloseEvent(&closing,nullptr);session->Reset();tasks->Run();
    assert(count(*player,sword)==3 && count(weapons,sword)==0);

    for(int protection=0;protection<4;++protection) {
        reset();seed();EnchantedItems::BeginLoan();tasks->Run();
        if(protection==0)player->rows[&sword].favorite=true;
        if(protection==1)player->rows[&sword].quest=true;
        if(protection==2)player->rows[&sword].extras.front()->worn=true;
        if(protection==3)RE::SCRIPT_FUNCTION::equipped.insert(&sword);
        EnchantedItems::EndLoan();assert(count(*player,sword)==3 && count(weapons,sword)==0 && count(armor,helmet)==2);
        assert(!player->rows[&sword].extras.front()->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
    }
    reset();seed();archive.refuse=true;EnchantedItems::BeginLoan();tasks->Run();
    assert(count(*player,sword)==0 && count(weapons,sword)+count(archive,sword)==3);
    archive.refuse=false;assert(EnchantedItems::Recover() && count(weapons,sword)==3);
    reset();seed();EnchantedItems::BeginLoan();tasks->Run();player->refuse=true;
    EnchantedItems::EndLoan();assert(count(*player,sword)==3 && count(weapons,sword)==0);
    reset();seed();EnchantedItems::BeginLoan();tasks->Run();EnchantedItems::Reset();EnchantedItems::EndLoan();
    assert(count(*player,sword)==3 && count(weapons,sword)==0);assert(EnchantedItems::Recover());
    assert(!player->rows[&sword].extras.front()->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword));

    reset();seed();assert(EnchantedItems::Gather());
    archive.RemoveItem(&sword,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,archive.rows[&sword].extras.front().get(),player);
    EnchantedItems::BeginLoan();tasks->Run();EnchantedItems::EndLoan();
    assert(count(*player,sword)==1 && count(weapons,sword)==2);
    reset();seed();EnchantedItems::BeginLoan();EnchantedItems::BeginLoan();tasks->Run();EnchantedItems::EndLoan();
    assert(count(*player,sword)==0 && count(weapons,sword)==3);
    RE::TESFurniture furniture;
    reset();seed();settings->GSC_EnchantedItemsLoan=true;
    assert(ActivateCraftLoan(&furniture,&bench,player,0,nullptr,1));tasks->Run();
    assert(count(*player,sword)==3);session->ExitCrafting();assert(count(weapons,sword)==3);
    reset();seed();settings->GSC_EnchantedItemsLoan=true;furniture.activation=false;
    assert(!ActivateCraftLoan(&furniture,&bench,player,0,nullptr,1));tasks->Run();
    assert(count(*player,sword)==0 && count(weapons,sword)==3);
    reset();seed();settings->GSC_EnchantedItemsLoan=true;furniture.activation=true;
    assert(ActivateCraftLoan(&furniture,&bench,&consumed,0,nullptr,1));
    assert(count(*player,sword)==0 && count(weapons,sword)==3);
    reset();seed();settings->GSC_CraftingLoan=settings->GSC_EnchantedItemsLoan=true;
    furniture.workBenchData.benchType.value=RE::TESFurniture::WorkBenchData::BenchType::kNone;
    assert(ActivateCraftLoan(&furniture,&bench,player,0,nullptr,1));
    assert(count(*player,sword)==0 && count(weapons,sword)==3 && Soulgems::loans==0);

    reset();player->Put(&sword,0,2,&owner,"original");
    for(int i=0;i<16;++i){weapons.Put(&sword,0,1,&owner,"weapon"+std::to_string(i));armor.Put(&sword,0,1,&owner,"armor"+std::to_string(i));}
    for(auto* ref:std::array<RE::TESObjectREFR*,4>{player,&weapons,&armor,&archive})ref->replaceExtras=true;
    EnchantedItems::BeginLoan();assert(count(*player,sword)==34);EnchantedItems::EndLoan();
    assert(count(*player,sword)==2 && count(weapons,sword)==16 && count(armor,sword)==16);
    for(auto* ref:{&weapons,&armor})for(auto& extra:ref->rows[&sword].extras){
        assert(extra->count==1 && extra->owner==&owner && extra->metadata.starts_with(ref==&weapons?"weapon":"armor"));
        assert(!InventoryStacks::HasOrigin(extra.get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
    }

    reset();junkBank.Put(&plain,0,5,&owner,"junk");
    player->Put(&plain,0,2,&owner,"carried junk");junkBank.limit=1;junkBank.refuseAfter=2;
    stores->BeginJunkLoan();assert(count(*player,plain)==4 && count(junkBank,plain)==3);
    assert(stores->junkLoan_.at(plain.GetFormID())==std::pair(2,2));
    player->limit=1;stores->EndJunkLoan();assert(count(*player,plain)==2 && count(junkBank,plain)==5);

    reset();seed();EnchantedItems::BeginLoan();player->limit=1;player->refuseAfter=1;
    EnchantedItems::EndLoan();assert(count(*player,sword)+count(weapons,sword)==3 && count(*player,helmet)+count(armor,helmet)==2);
    for(auto& [item,row]:player->rows){(void)item;for(auto& extra:row.extras)assert(!InventoryStacks::HasOrigin(extra.get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword));}

    reset();seed();assert(EnchantedItems::Gather());
    archive.RemoveItem(&sword,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,archive.rows[&sword].extras.front().get(),player);
    archive.RemoveItem(&helmet,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,archive.rows[&helmet].extras.front().get(),player);
    assert(tasks->queue.size()==1);tasks->Run();
    for(auto& [item,row]:player->rows){(void)item;for(auto& extra:row.extras)assert(!InventoryStacks::HasOrigin(extra.get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword));}

    reset();seed();assert(EnchantedItems::Gather());
    archive.RemoveItem(&sword,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,archive.rows[&sword].extras.front().get(),player);
    EnchantedItems::Reset();
    archive.RemoveItem(&helmet,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,archive.rows[&helmet].extras.front().get(),player);
    assert(tasks->queue.size()==2);tasks->Run();
    for(auto& [item,row]:player->rows){(void)item;for(auto& extra:row.extras)assert(!InventoryStacks::HasOrigin(extra.get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword));}

    reset();seed();assert(EnchantedItems::Gather());
    archive.RemoveItem(&sword,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,archive.rows[&sword].extras.front().get(),player);
    EnchantedItems::BeginLoan();assert(count(*player,sword)==3);tasks->Run();EnchantedItems::EndLoan();
    assert(count(*player,sword)==1 && count(weapons,sword)==2 && count(armor,helmet)==2);

    reset();archive.Put(&sword,0,2,&owner,"malformed archive");archive.rows[&sword].duplicate=true;
    assert(!EnchantedItems::Recover() && count(archive,sword)==2);
    reset();seed();EnchantedItems::BeginLoan();weapons.Put(&sword,INT_MAX);
    EnchantedItems::EndLoan();assert(count(*player,sword)==3 && count(weapons,sword)==INT_MAX);

    reset();RE::EnchantmentItem fire,frost,carriedEnchantment;
    for(auto* enchantment:{&fire,&frost}) {
        weapons.Put(&plain,0,3,&owner,"same metadata");
        weapons.rows[&plain].extras.back()->enchantment=RE::ExtraEnchantment{enchantment};
    }
    weapons.Put(&plain,0,4,&owner,"unenchanted");player->Put(&plain,0,2,&owner,"same metadata");
    player->rows[&plain].extras.back()->enchantment=RE::ExtraEnchantment{&carriedEnchantment};
    for(auto* ref:std::array<RE::TESObjectREFR*,3>{&weapons,&archive,player}){ref->replaceExtras=true;ref->limit=1;}
    const auto enchantmentCounts=[&](RE::TESObjectREFR& ref){
        std::map<RE::EnchantmentItem*,int> counts;
        for(auto& extra:ref.rows[&plain].extras){assert(extra->owner==&owner);counts[extra->enchantment?extra->enchantment->enchantment:nullptr]+=extra->count;}
        return counts;
    };
    EnchantedItems::BeginLoan();tasks->Run();
    assert(enchantmentCounts(*player)==(std::map<RE::EnchantmentItem*,int>{{&fire,3},{&frost,3},{&carriedEnchantment,2}}));
    assert(enchantmentCounts(weapons)==(std::map<RE::EnchantmentItem*,int>{{nullptr,4}}));
    EnchantedItems::EndLoan();
    assert(enchantmentCounts(*player)==(std::map<RE::EnchantmentItem*,int>{{&carriedEnchantment,2}}));
    assert(enchantmentCounts(weapons)==(std::map<RE::EnchantmentItem*,int>{{nullptr,4},{&fire,3},{&frost,3}}));

    reset();weapons.Put(&sword,0,1,&owner,"first");weapons.Put(&sword,0,1,&owner,"second");
    int selections=0;
    auto first=InventoryStacks::Read(&weapons,[&](auto*,auto&,auto*){++selections;return true;},&sword,true);
    assert(first.size()==1 && first.front().extra->metadata=="first" && selections==1);
    weapons.rows[&sword].extras.back()->count=2;
    assert(InventoryStacks::Read(&weapons,{},&sword,true).empty());
    weapons.rows[&sword].extras.back()->count=1;weapons.rows[&sword].duplicate=true;
    assert(InventoryStacks::Read(&weapons,{},&sword,true).empty());

    reset();weapons.Put(&sword,0,3,&owner,"counted move");weapons.limit=1;
    assert(InventoryStacks::Move(InventoryStacks::Read(&weapons,{},&sword,true).front(),&armor)==1);
    assert(count(weapons,sword)==2 && count(armor,sword)==1);
    weapons.refuse=true;
    assert(InventoryStacks::Move(InventoryStacks::Read(&weapons,{},&sword,true).front(),&armor)==0);
    assert(count(weapons,sword)==2 && count(armor,sword)==1);
    armor.Put(&helmet,0,1,&owner,"other base");
    auto* key=&RE::TESDataHandler::GetSingleton()->enchantedKeyword;
    auto* otherKey=&RE::TESDataHandler::GetSingleton()->keyword;
    armor.rows[&sword].extras.front()->SetLinkedRef(&weapons,key);
    armor.rows[&sword].extras.front()->SetLinkedRef(&archive,otherKey);
    armor.rows[&helmet].extras.front()->SetLinkedRef(&weapons,key);
    InventoryStacks::ClearOrigins(&armor,key,&sword);
    assert(!InventoryStacks::HasOrigin(armor.rows[&sword].extras.front().get(),key));
    assert(armor.rows[&sword].extras.front()->GetLinkedRef(otherKey)==&archive);
    assert(armor.rows[&helmet].extras.front()->GetLinkedRef(key)==&weapons);

}
'''

if args.probe_deliveries or args.time_deliveries:
    if (args.probe_deliveries or args.time_deliveries).exists():
        parser.error("Choose a new report path")
    common = common.replace("inline bool inspectionOpen=false;", "inline bool bulkDispatch=false;inline bool inspectionOpen=false;")
    common = common.replace("if(deferTransfers && target->id==0x14){", "if(bulkDispatch && deferTransfers && target->id==0x14){")
    common = common.replace("auto snapshot=source->GetInventoryCounts();int remaining=bulkLimit;", "struct BulkScope{BulkScope(){bulkDispatch=true;}~BulkScope(){bulkDispatch=false;}} scope;auto snapshot=source->GetInventoryCounts();int remaining=bulkLimit;")
    common = common.replace("bool deferTransfers=false;", "int deliveryOrder=0;bool earlyReceipt=false;bool deferTransfers=false;")
    common = common.replace("struct ScriptEventSourceHolder {", "inline int receiptMode=0;\nstruct ScriptEventSourceHolder {")
    common = common.replace("void Send(TESContainerChangedEvent e){for(auto* sink:sinks)sink->ProcessEvent(&e,nullptr);}", r'''
    void Send(TESContainerChangedEvent e){
        const bool loan=e.oldContainer==1003 && e.newContainer==0x14;
        if(loan && receiptMode==1)return;
        if(loan && receiptMode==3)e.oldContainer=1001;
        for(int i=0;i<(loan && receiptMode==2?3:1);++i)for(auto* sink:sinks)sink->ProcessEvent(&e,nullptr);
    }''')
    common = common.replace("for(auto& copy:row.extras)out.extras.push_back(copy);", r'''
        for(auto& copy:row.extras){
            if(receiptMode==4)std::erase_if(copy->links.linkedRefs,[](auto& link){return link.keyword->id==0x01000DED;});
            out.extras.push_back(copy);
        }''')
    common = common.replace("if(row.total>0)deliveries.push_back([item,target,row,from=id]{", "if(earlyReceipt && row.total>0)ScriptEventSourceHolder::GetSingleton()->Send({id,target->id,item->id,row.total});\n            if(row.total>0)deliveries.push_back([item,target,row,from=id,early=earlyReceipt]{")
    common = common.replace("ScriptEventSourceHolder::GetSingleton()->Send({from,target->id,item->id,row.total});", "if(!early)ScriptEventSourceHolder::GetSingleton()->Send({from,target->id,item->id,row.total});")
    needle = "assert(owner==source && !stealing);++bulkTransfers;lastKeepOwnership=keepOwnership;if(bulkRefuse)return;"
    assert needle in common
    common = common.replace(needle, needle + r'''
    if(source->deliveryOrder==2 || source->deliveryOrder==4){
        source->refuse=source->deliveryOrder==2;source->deliveryOrder=0;
        source->deliveries.push_back([this,owner,target,stealing,keepOwnership]{
            source->refuse=false;RemoveAllItems(owner,target,stealing,keepOwnership,false);
        });
        return;
    }
''')
    setup = program[:program.index("    reset();seed();session->EnterCrafting(&bench);")]
    setup = setup.replace("ref->deferTransfers=false;", "ref->deliveryOrder=0;ref->earlyReceipt=false;ref->deferTransfers=false;")
    setup = setup.replace("RE::EnchantmentItem normal;", "RE::EnchantmentItem normal,fire,frost;")
    setup = setup.replace('weapons.Put(&sword,0,3,&owner,"borrowed sword");', '''
        for(auto* enchantment:{&fire,&frost}){
            weapons.Put(&sword,0,enchantment==&fire?1:2,&owner,"borrowed sword");
            weapons.rows[&sword].extras.back()->enchantment=RE::ExtraEnchantment{enchantment};
        }''')
    program = setup + r'''
    (void)artifact;(void)staff;(void)plain;
    RE::TESFurniture furniture;
    for(int order=0;order<5;++order)for(int scenario=0;scenario<17;++scenario){
        reset();seed();player->Put(&sword,0,1,&owner,"carried");
        RE::receiptMode=scenario<=4?scenario:0;
        archive.deliveryOrder=order;archive.deferTransfers=order!=0;archive.earlyReceipt=order==3;
        settings->GSC_EnchantedItemsLoan=true;furniture.activation=scenario!=14;
        assert(ActivateCraftLoan(&furniture,&bench,player,0,nullptr,1)==furniture.activation);furniture.activation=true;
        const int heldAtBegin=count(*player,sword);
        const bool drainingBeforeClose=EnchantedItems::HasPendingLoan();
        if(scenario==9 && !archive.deliveries.empty()){
            auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();tasks->Run();
        }
        if(scenario==5)player->refuse=true;
        if(scenario==6)weapons.Put(&sword,INT_MAX-3);
        if(scenario==7)RE::SCRIPT_FUNCTION::equipped.insert(&sword);
        RE::MenuOpenCloseEvent closing{"CraftingMenu",false};
        if(scenario!=15)CraftingCloseEvent(&closing,nullptr);
        tasks->Run();
        if(scenario==8){CraftingCloseEvent(&closing,nullptr);CraftingCloseEvent(&closing,nullptr);tasks->Run();}
        if(scenario==11 || scenario==12){
            u->bench=scenario==11?BenchType::Enchanting:BenchType::Alchemy;
            settings->GSC_CraftingLoan=scenario==12;session->EnterCrafting(&bench);
            CraftingCloseEvent(&closing,nullptr);tasks->Run();
        }
        if(scenario==13){session->Reset();tasks->Run();}
        const bool oldDeliveries=!archive.deliveries.empty();
        if(scenario==16){
            session->Reset();tasks->Run();armor.Put(&helmet,0,1,&owner,"borrowed helmet");
            session->EnterCrafting(&bench);CraftingCloseEvent(&closing,nullptr);tasks->Run();
        }
        const bool drainingAfterClose=EnchantedItems::HasPendingLoan();
        const int beforeArrival=count(*player,sword);
        int deliveries=0;
        std::vector<std::pair<int,int>> arrivals;
        if(scenario==2)std::reverse(archive.deliveries.begin(),archive.deliveries.end());
        while(!archive.deliveries.empty()){
            assert(++deliveries<20);
            auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();
            const int beforeCleanup=count(*player,sword)+count(*player,helmet);
            if(scenario!=10)tasks->Run();
            arrivals.emplace_back(beforeCleanup,count(*player,sword)+count(*player,helmet));
        }
        tasks->Run();
        const int held=count(*player,sword),returned=count(weapons,sword);
        const std::int64_t capacitySeed=scenario==6?INT_MAX-3:0;
        assert(static_cast<std::int64_t>(held)+returned+count(archive,sword)==4+capacitySeed);
        assert(count(*player,helmet)+count(armor,helmet)+count(archive,helmet)==2+(scenario==16?1:0));
        std::map<RE::EnchantmentItem*,int> enchantments;
        for(auto* ref:{static_cast<RE::TESObjectREFR*>(player),&weapons,&archive})
            for(auto& extra:ref->rows[&sword].extras){
                assert(extra->owner==&owner);assert(extra->metadata=="carried" || extra->metadata=="borrowed sword");
                enchantments[extra->enchantment?extra->enchantment->enchantment:nullptr]+=extra->count;
            }
        assert((enchantments==std::map<RE::EnchantmentItem*,int>{{nullptr,1},{&fire,1},{&frost,2}}));
        int carried=0,marked=0;
        for(auto& extra:player->rows[&sword].extras){
            if(extra->metadata=="carried")carried+=extra->count;
            if(InventoryStacks::HasOrigin(extra.get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword))marked+=extra->count;
        }
        assert(carried==1);
        const bool restored=held==1 && returned==3 && count(*player,helmet)==0 && count(armor,helmet)==2;
        const bool protectedCase=scenario==5 || scenario==6 || scenario==7 || scenario==13 || scenario==15 || scenario==16;
        if(protectedCase)assert(held>=beforeArrival);

        const bool sessionIsolated=scenario!=16 || (count(*player,helmet)==(oldDeliveries?2:0) && count(armor,helmet)==(oldDeliveries?1:3));
        std::cout<<"{\"order\":"<<order<<",\"scenario\":"<<scenario<<",\"protected_case\":"<<(protectedCase?"true":"false")<<",\"held_at_begin\":"<<heldAtBegin
            <<",\"draining_before_close\":"<<(drainingBeforeClose?"true":"false")
            <<",\"draining_after_close\":"<<(drainingAfterClose?"true":"false")
            <<",\"held_after_close\":"<<beforeArrival<<",\"held_final\":"<<held
            <<",\"returned_final\":"<<returned<<",\"marked_final\":"<<marked
            <<",\"pending_final\":"<<(EnchantedItems::HasPendingLoan()?"true":"false")
            <<",\"restored\":"<<(restored?"true":"false")<<",\"session_isolated\":"<<(sessionIsolated?"true":"false")<<",\"held_helmet_final\":"<<count(*player,helmet)<<",\"returned_helmet_final\":"<<count(armor,helmet)<<",\"arrivals\":[";
        for(std::size_t i=0;i<arrivals.size();++i){
            if(i)std::cout<<",";
            std::cout<<"{\"visible_before_cleanup\":"<<arrivals[i].first<<",\"visible_after_cleanup\":"<<arrivals[i].second<<"}";
        }
        std::cout<<"]}\n";
    }
}
'''
    program = program.replace('#include "common.hpp"', '#include "common.hpp"\n#include <iostream>')

if args.time_deliveries:
    def stop_timings(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop_timings)
    if args.samples<2:parser.error("Use at least two repeats")
    if not all(0<=size<=1000 for size in args.sizes):parser.error("Sizes must be between zero and 1000")
    common=common.replace("inline bool inspectionOpen=false;", "struct ScanCounters{inline static std::uint64_t calls=0,extras=0;static void Reset(){calls=extras=0;}};inline bool inspectionOpen=false;")
    common=common.replace("std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;", "++ScanCounters::calls;std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;")
    common=common.replace("for(auto& x:row.extras)e->lists.push_back(x.get());", "for(auto& x:row.extras){++ScanCounters::extras;e->lists.push_back(x.get());}")
    program=setup.replace("int main() {", "int main(int argc,char** argv) {") + r'''
    (void)artifact;(void)staff;(void)plain;(void)seed;(void)fire;(void)frost;
    assert(argc==4);const int size=std::stoi(argv[1]),shape=std::stoi(argv[2]),batch=std::stoi(argv[3]);
    assert(size>=0 && size<=1000 && shape>=0 && shape<=1 && batch>=0);
    reset();player->Put(&sword,0,1,&owner,"carried");
    std::vector<RE::EnchantmentItem> variants(size);
    if(shape==0){
        weapons.Put(&sword,0,size,&owner,"loan");
        if(size)weapons.rows[&sword].extras.back()->enchantment=RE::ExtraEnchantment{&normal};
    }else for(int i=0;i<size;++i){
        weapons.Put(&sword,0,1,&owner,"loan");weapons.rows[&sword].extras.back()->enchantment=RE::ExtraEnchantment{&variants[i]};
    }
    archive.deferTransfers=batch>0;settings->GSC_EnchantedItemsLoan=true;RE::TESFurniture furniture;
    auto phase=[&](const char* name,int frame,const auto& action){
        RE::ScanCounters::Reset();const auto start=std::chrono::steady_clock::now();action();
        const auto ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
        std::cout<<"{\"phase\":\""<<name<<"\",\"frame\":"<<frame<<",\"cpu_ms\":"<<ms
            <<",\"inventory_calls\":"<<RE::ScanCounters::calls<<",\"extra_visits\":"<<RE::ScanCounters::extras
            <<",\"held\":"<<count(*player,sword)<<",\"returned\":"<<count(weapons,sword)<<",\"pending\":"<<(EnchantedItems::HasPendingLoan()?"true":"false")<<"}\n";
    };
    phase("dispatch",0,[&]{assert(ActivateCraftLoan(&furniture,&bench,player,0,nullptr,1));tasks->Run();});
    phase(batch==0?"close_and_settlement":"close",0,[&]{RE::MenuOpenCloseEvent event{"CraftingMenu",false};CraftingCloseEvent(&event,nullptr);tasks->Run();});
    int frame=0;
    while(!archive.deliveries.empty()){
        assert(batch>0 && ++frame<=1000);
        phase(archive.deliveries.size()<=static_cast<std::size_t>(batch)?"final_delivery_settlement":"delivery_cleanup",frame,[&]{
            for(int i=0;i<batch && !archive.deliveries.empty();++i){auto deliver=std::move(archive.deliveries.front());archive.deliveries.pop_front();deliver();}
            tasks->Run();
        });
    }
    assert(count(*player,sword)==1 && count(weapons,sword)==size && count(archive,sword)==0 && !EnchantedItems::HasPendingLoan());
    assert(player->rows[&sword].extras.front()->metadata=="carried");
    std::map<RE::EnchantmentItem*,int> actual,expected;
    if(shape==0 && size)expected[&normal]=size;
    else for(auto& variant:variants)expected[&variant]=1;
    for(auto& extra:weapons.rows[&sword].extras){
        assert(extra->owner==&owner && extra->metadata=="loan" && extra->enchantment);
        assert(!InventoryStacks::HasOrigin(extra.get(),&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
        actual[extra->enchantment->enchantment]+=extra->count;
    }
    assert(actual==expected);
}
'''
    program=program.replace('#include "common.hpp"','#include "common.hpp"\n#include <iostream>')
    args.time_deliveries.parent.mkdir(parents=True,exist_ok=True)
    timing={"pid":os.getpid(),"running":True,"complete":False,"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
        "boundary":"Production dispatch, close and deferred arrival/return CPU costs with instrumented engine stubs. Native engine/UI costs are excluded. Frames are controlled batches, not measured Skyrim frames. Every completed sample validates counts, ownership, custom enchantments, carried copies and marker cleanup.",
        "compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0],
        "source_sha256":{name:hashlib.sha256((ROOT/f"src/{name}.cpp").read_bytes()).hexdigest() for name in ("EnchantedItems","InventoryStacks","Events")},
        "harness_sha256":hashlib.sha256((common+program).encode()).hexdigest(),"samples":[]}
    args.time_deliveries.write_text(json.dumps(timing,indent=2)+"\n")
    def finish_timings():
        timing["running"]=False;timing["pid"]=None
        args.time_deliveries.write_text(json.dumps(timing,indent=2)+"\n")
    atexit.register(finish_timings)

with tempfile.TemporaryDirectory(prefix="arcanevault-enchanted-loan-") as tmp:
    tmp = Path(tmp)
    (tmp / "common.hpp").write_text("#pragma once\n#include <climits>\n#include <utility>\n" + common)
    cpp = tmp / "check.cpp"
    cpp.write_text(program)
    modules = []
    for name in ("InventoryStacks", "EnchantedItems"):
        module = tmp / f"{name}.cpp"
        module.write_text('#include "common.hpp"\n' + "\n".join(line for line in (ROOT / f"src/{name}.cpp").read_text().splitlines() if not line.startswith("#include")))
        modules.append(str(module))
    binary = tmp / "check"
    sanitizers = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if args.sanitize else []
    optimization=["-O2"] if args.time_deliveries else []
    subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", *optimization, *sanitizers, "-I", str(ROOT), str(cpp), *modules, "-o", str(binary)], check=True, timeout=90)
    if args.time_deliveries:
        for size in args.sizes:
            for shape in (0,1):
                for sample in range(args.samples):
                    for batch in ((0,1,32) if sample%2==0 else (32,1,0)):
                        output=subprocess.check_output([str(binary),str(size),str(shape),str(batch)],text=True,timeout=60)
                        phases=[json.loads(line) for line in output.splitlines()]
                        timing["samples"].append({"size":size,"shape":shape,"batch":batch,"sample":sample,"validated":True,"phases":phases})
                        args.time_deliveries.write_text(json.dumps(timing,indent=2)+"\n")
                    print(f"Validated deferred-loan timing size={size} shape={shape} repeat={sample+1}/{args.samples}",flush=True)
        timing["summary"]=[]
        for size in args.sizes:
            for shape in (0,1):
                for batch in (0,1,32):
                    rows=[s for s in timing["samples"] if (s["size"],s["shape"],s["batch"])==(size,shape,batch)]
                    for phase in ("dispatch","close","delivery_cleanup","final_delivery_settlement","close_and_settlement"):
                        totals=[sum(p["cpu_ms"] for p in s["phases"] if p["phase"]==phase) for s in rows]
                        timing["summary"].append({"size":size,"shape":shape,"batch":batch,"phase":phase,"min_ms":min(totals),"median_ms":statistics.median(totals),"max_ms":max(totals)})
        timing["complete"]=True
        args.time_deliveries.write_text(json.dumps(timing,indent=2)+"\n")
        print(f"PASS: {len(timing['samples'])} deferred-loan timing round trips; report {args.time_deliveries}")
        raise SystemExit(0)
    if args.probe_deliveries:
        cases=[json.loads(line) for line in subprocess.check_output([str(binary)],text=True,timeout=60).splitlines()]
        args.probe_deliveries.parent.mkdir(parents=True,exist_ok=True)
        args.probe_deliveries.write_text(json.dumps({"boundary":"Production enchanted loan and crafting session with alternative engine scheduling models. Actual Skyrim scheduling is unknown. Every case asserts conservation, ownership and distinct custom enchantments sharing one base. Refused/full/equipped/reset policies are classified separately. Scenario 15 supplies no terminal menu event after successful activation, so the plugin receives no cancellation signal. Scenario 16 requires old native receipts to remain separate from a new loan of the same base after reset.","orders":["immediate","source removed before delayed arrival","source removal queued, recovery temporarily refused","receipt before visible arrival","source removal queued, recovery allowed"],"scenarios":["normal","missing receipts","duplicated receipts, reverse delivery","wrong receipt source","origin marker lost","player refuses returns","parent at capacity","matching base equipped","repeated close","one delivery before close","coalesced delivery cleanup","reopen and close enchanting","switch and close alchemy","reset with native deliveries pending","activation fails before menu opens","activation succeeds but menu never opens","reset then new loan sharing old delivery base"],"cases":cases},indent=2)+"\n")
        controls=[case for case in cases if case["scenario"]==0 and case["order"] in (0,1,4)]
        assert len(controls)==3 and all(case["restored"] for case in controls)
        failures=sum((not case["restored"] and not case["protected_case"]) or not case["session_isolated"] for case in cases)
        print(f"Enchanted delivery probe: {failures} failed return cases; report {args.probe_deliveries}")
        raise SystemExit(1 if failures else 0)
    subprocess.run([str(binary)], check=True, timeout=60)
print("PASS: enchanting loans, replaced same-base stacks, metadata/origins, partial/refused/capacity transfers, Junk ledger, coalesced/reset/new-loan cleanup, protections and bench isolation")
