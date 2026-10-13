"""Exercise enchanted-copy lending and real crafting-session routing with engine stubs."""

from pathlib import Path
import subprocess
import tempfile

import check_stolen

ROOT = check_stolen.ROOT
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
events = (ROOT / "src/Events.cpp").read_text()
loan = events[events.index("class CraftingLoanState {"):events.index("class FurnitureActivation {")]
start = events.index("    static bool ActivateCraftLoan(")
hook = events[start:events.index("\n    }", start) + 6]
stores_source = (ROOT / "src/Stores.cpp").read_text()
start = stores_source.index("    void MoveItems(")
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
        for(auto* ref:std::array<RE::TESObjectREFR*,6>{player,&weapons,&armor,&archive,&consumed,&junkBank}){ref->rows.clear();ref->refuse=false;ref->limit=INT_MAX;}
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
    subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(cpp), *modules, "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: independent/default-disabled enchanting loans, original copies and metadata, consumption, protections, partial/large transfers, failure, reset, delayed events and other bench isolation")
