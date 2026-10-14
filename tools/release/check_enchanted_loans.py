"""Exercise enchanted-copy lending and real crafting-session routing with engine stubs."""

from pathlib import Path
import argparse
import subprocess
import tempfile

import check_stolen

ROOT = check_stolen.ROOT
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sanitize", action="store_true", help="Check native memory access and undefined behaviour")
args = parser.parse_args()
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
events = (ROOT / "src/Events.cpp").read_text()
loan = events[events.index("class CraftingLoanState {"):events.index("class FurnitureActivation {")]
start = events.index("    static bool ActivateCraftLoan(")
hook = events[start:events.index("\n    }", start) + 6]
stores_source = (ROOT / "src/Stores.cpp").read_text()
start = stores_source.index("    int MoveItems(")
junk = stores_source[start:stores_source.index("\n    }", start) + 6]
for name, counter in (("BeginJunkLoan", "junkLoans"), ("EndJunkLoan", "junkReturns")):
    start = stores_source.index(f"void Stores::{name}(")
    body = stores_source[start:stores_source.index("\n}\n", start) + 3]
    junk += body.replace(f"void Stores::{name}() {{", f"void Stores::{name}() {{++{counter};")
program = '#include "common.hpp"\n' + junk + loan + r'''
namespace RE {
struct TESFurniture {
    struct WorkBenchData {enum class BenchType {kNone,kEnchanting};};
    struct Field {WorkBenchData::BenchType value=WorkBenchData::BenchType::kEnchanting;auto get()const{return value;}};
    struct {Field benchType;} workBenchData;
    bool activation=true;
};
}
bool NativeActivate(RE::TESFurniture* base,RE::TESObjectREFR*,RE::TESObjectREFR*,std::uint8_t,RE::TESBoundObject*,std::int32_t){return base->activation;}
auto activate_=NativeActivate;
''' + hook + r'''
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
    assert(archive.changes.bulkTransfers==1 && archive.changes.lastKeepOwnership);
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
        assert(archive.changes.bulkTransfers==(overflow?0:1));
        assert(count(*player,sword)==held+(overflow?0:3));
        EnchantedItems::EndLoan();
        assert(count(*player,sword)==held && count(weapons,sword)==3 && count(armor,helmet)==2);
    }
    for(int failure=0;failure<3;++failure) {
        reset();seed();player->Put(&sword,0,2,&owner,"carried");
        archive.changes.bulkRefuse=failure==0;archive.changes.bulkLimit=failure==1?2:INT_MAX;
        archive.missingChanges=failure==2;
        EnchantedItems::BeginLoan();tasks->Run();EnchantedItems::EndLoan();
        assert(archive.changes.bulkTransfers==(failure==2?0:1));
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
    subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", *sanitizers, "-I", str(ROOT), str(cpp), *modules, "-o", str(binary)], check=True, timeout=90)
    subprocess.run([str(binary)], check=True, timeout=60)
print("PASS: enchanting loans, replaced same-base stacks, metadata/origins, partial/refused/capacity transfers, Junk ledger, coalesced/reset/new-loan cleanup, protections and bench isolation")
