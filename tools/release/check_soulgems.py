"""Run the real soul gem transfer and loan code against mixed-stack inventory stubs."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
implementation = (ROOT / "src/Soulgems.cpp").read_text().replace('#include "Utility.h"', '').replace('#include "Settings.h"', '')
program = r'''
#include <algorithm>
#include <utility>
#include <array>
#include <cassert>
#include <cstdint>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
using FormID = unsigned;
enum class SOUL_LEVEL { kNone, kPetty, kLesser, kCommon, kGreater, kGrand };
struct TESForm {
    inline static std::map<FormID, TESForm*> forms;
    FormID id;
    explicit TESForm(FormID value):id(value) { forms[id]=this; }
    virtual ~TESForm() = default;
    FormID GetFormID() const { return id; }
    template<class T> static T* LookupByID(FormID id) {
        return forms.contains(id) ? dynamic_cast<T*>(forms.at(id)) : nullptr;
    }
};
struct TESBoundObject : TESForm {
    using TESForm::TESForm;
    template<class T> T* As() { return dynamic_cast<T*>(this); }
};
struct TESSoulGem : TESBoundObject {
    SOUL_LEVEL soul;
    TESSoulGem* linkedSoulGem = nullptr;
    TESSoulGem(FormID id, SOUL_LEVEL value):TESBoundObject(id),soul(value) {}
    SOUL_LEVEL GetContainedSoul() const { return soul; }
};
struct ExtraSoul {
    SOUL_LEVEL soul;
    SOUL_LEVEL GetContainedSoul() const { return soul; }
};
struct ExtraDataList {
    int count;
    std::optional<ExtraSoul> soul;
    std::string owner;
    bool alive = true;
    int GetCount() const { assert(alive); return count; }
    template<class T> T* GetByType() { assert(alive); return soul ? &*soul : nullptr; }
};
struct InventoryEntryData {
    std::vector<ExtraDataList*> lists;
    std::vector<ExtraDataList*>* extraLists = nullptr;
    bool quest = false, favorite = false, worn = false;
    bool IsQuestObject() const { return quest; }
    bool IsFavorited() const { return favorite; }
    bool IsWorn() const { return worn; }
};
enum class ITEM_REMOVE_REASON { kStoreInContainer };
struct TESObjectREFR {
    using Inventory = std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>>;
    Inventory inventory;
    inline static std::vector<std::unique_ptr<ExtraDataList>> extras;
    Inventory GetInventory() const { return inventory; }
    void Put(TESBoundObject* item,int count,std::optional<SOUL_LEVEL> soul={},std::string owner={},bool explicitStack=false) {
        auto& data=inventory[item];data.first+=count;
        if (!data.second) data.second=std::make_shared<InventoryEntryData>();
        if (explicitStack) {
            auto extra=std::make_unique<ExtraDataList>();extra->count=count;extra->owner=owner;
            if (soul) extra->soul=ExtraSoul{*soul};
            data.second->lists.push_back(extra.get());extras.push_back(std::move(extra));
            data.second->extraLists=&data.second->lists;
        }
    }
    void RemoveItem(TESBoundObject* item,int count,ITEM_REMOVE_REASON,ExtraDataList* extra,TESObjectREFR* target) {
        auto& data=inventory.at(item);assert(count>0 && count<=data.first);
        while (count>0) {
            auto* chosen=extra;
            if (!chosen && !data.second->lists.empty()) chosen=data.second->lists.front();
            int moving=count;
            if (chosen) {
                assert(chosen->alive);
                moving=std::min(moving,chosen->count);
                if (target) target->Put(item,moving,chosen->soul?std::optional{chosen->soul->soul}:std::nullopt,chosen->owner,true);
                chosen->count-=moving;
                if (chosen->count==0) {
                    std::erase(data.second->lists,chosen);chosen->alive=false;
                    if (data.second->lists.empty()) data.second->extraLists=nullptr;
                }
            } else if (target) target->Put(item,moving);
            data.first-=moving;count-=moving;
            if (extra) { assert(count==0); }
        }
    }
    struct Changes {
        TESObjectREFR* owner;
        void RemoveAllItems(TESObjectREFR*,TESObjectREFR* target,bool,bool,bool) {
            const auto inventory=owner->GetInventory();
            for (const auto& [item,data]:inventory)
                if (data.first>0) owner->RemoveItem(item,data.first,ITEM_REMOVE_REASON::kStoreInContainer,nullptr,target);
        }
    } changes{this};
    Changes* GetInventoryChanges() { return &changes; }
};
struct PlayerCharacter : TESObjectREFR {
    static PlayerCharacter* GetSingleton() { static PlayerCharacter player;return &player; }
};
}
struct Utility {
    std::map<Container,RE::TESObjectREFR> containers;
    std::unordered_set<RE::FormID> recipes;
    static Utility* GetSingleton() { static Utility u;return &u; }
    RE::TESObjectREFR* GetContainer(Container c) { return &containers[c]; }
    bool isSmithing(RE::FormID id) const { return recipes.contains(id); }
    BenchType bench = BenchType::Enchanting;
    BenchType GetBenchType(RE::TESObjectREFR*) const { return bench; }
};
'''
program += r'''
struct Settings {
    bool GSC_CraftingLoan = true;
    bool GSC_EnchantedItemsLoan = false;
    bool GSC_ReturnIgnoredItems = true;
    std::unordered_set<const RE::TESBoundObject*> ignored;
    bool IsIgnored(const RE::TESBoundObject* item) const { return ignored.contains(item); }
    static Settings* GetSingleton() { static Settings s;return &s; }
};
'''
program += implementation
loan = (ROOT / "src/Events.cpp").read_text()
loan = loan[loan.index("class CraftingLoanState {"):loan.index("class FurnitureActivation {")]
program += r'''

struct Stores {
    static Stores* GetSingleton() { static Stores s;return &s; }
    void BeginJunkLoan() {}
    void EndJunkLoan() {}
    void ResetJunkLoan() {}
    void AllToPlayer(Container) {}
    void StoreToPlayer(ItemCategory,Container) {}
    void PlayerToStore(ItemCategory,Container) {}
};
'''
program += "namespace EnchantedItems { void BeginLoan() {} void EndLoan() {} void Reset() {} }\n"
program += loan
program += r'''
int main() {
    auto* u=Utility::GetSingleton();auto* player=RE::PlayerCharacter::GetSingleton();
    auto* bank=u->GetContainer(Container::Soulgem);
    auto* empty=u->GetContainer(Container::EmptySoulgems);
    auto* filled=u->GetContainer(Container::FilledSoulgems);
    auto reset=[&] {
        Soulgems::ResetLoan();player->inventory.clear();u->recipes.clear();
        for (auto& [kind,ref]:u->containers) { (void)kind;ref.inventory.clear(); }
    };
    auto counts=[&](RE::TESObjectREFR* ref,RE::TESSoulGem* gem) {
        return CountGems(ref)[gem->GetFormID()];
    };
    RE::TESSoulGem gem(100,RE::SOUL_LEVEL::kNone);
    player->Put(&gem,40);
    player->Put(&gem,10,RE::SOUL_LEVEL::kGrand,"Filled owner",true);
    player->Put(&gem,10,RE::SOUL_LEVEL::kNone,"Empty owner",true);
    Soulgems::Deposit(25);
    assert((counts(player,&gem)==std::array{25,0}));
    assert((counts(bank,&gem)==std::array{25,10}));
    assert(bank->inventory[&gem].second->lists.front()->owner=="Filled owner");
    Soulgems::Deposit(25);
    assert((counts(player,&gem)==std::array{25,0}));
    Soulgems::Split();
    assert((counts(empty,&gem)==std::array{25,0}));
    assert((counts(filled,&gem)==std::array{0,10}));
    Soulgems::Consolidate();Soulgems::TakeEmpty();
    assert((counts(player,&gem)==std::array{50,0}));
    assert((counts(bank,&gem)==std::array{0,10}));
    Soulgems::Deposit(25);
    assert((counts(player,&gem)==std::array{25,0}));
    Soulgems::Deposit(0);
    assert((counts(player,&gem)==std::array{0,0}));
    reset();
    RE::TESSoulGem prefilled(101,RE::SOUL_LEVEL::kGrand);
    player->Put(&prefilled,12);player->Put(&prefilled,30,RE::SOUL_LEVEL::kNone,"Varla owner",true);
    Soulgems::Deposit(25);
    assert((counts(player,&prefilled)==std::array{25,0}));
    assert((counts(bank,&prefilled)==std::array{5,12}));
    assert(empty->inventory[&prefilled].first==0);
    Soulgems::Split();
    assert((counts(empty,&prefilled)==std::array{5,0}));
    assert((counts(filled,&prefilled)==std::array{0,12}));
    Soulgems::Consolidate();
    reset();
    player->Put(&gem,3,RE::SOUL_LEVEL::kGrand,{},true);
    player->inventory[&gem].first=2;
    Soulgems::Deposit(0);assert(player->inventory[&gem].first==2 && bank->inventory.empty());
    reset();
    for (int protection=0;protection<3;++protection) {
        player->Put(&gem,3);auto& entry=*player->inventory[&gem].second;
        entry.quest=protection==0;entry.favorite=protection==1;entry.worn=protection==2;
        Soulgems::Deposit(0);assert(player->inventory[&gem].first==3);player->inventory.clear();
    }
    RE::TESSoulGem star(0x63B27,RE::SOUL_LEVEL::kNone),modStar(102,RE::SOUL_LEVEL::kGrand);
    modStar.linkedSoulGem=&star;player->Put(&modStar,1);
    Soulgems::Deposit(0);assert(player->inventory[&modStar].first==1);
    reset();
    RE::TESSoulGem varla(0xFE000801,RE::SOUL_LEVEL::kNone);
    player->Put(&varla,2);player->Put(&varla,1,RE::SOUL_LEVEL::kCommon,"Stone owner",true);
    Soulgems::Deposit(25);
    assert((counts(player,&varla)==std::array{2,0}));assert((counts(bank,&varla)==std::array{0,1}));
    Soulgems::BeginLoan(false);
    assert((counts(player,&varla)==std::array{2,1}));
    player->inventory[&varla].second->lists.front()->soul->soul=RE::SOUL_LEVEL::kNone;
    Soulgems::EndLoan();
    assert((counts(player,&varla)==std::array{2,0}));assert((counts(bank,&varla)==std::array{1,0}));
    reset();
    u->GetContainer(Container::Smithing)->Put(&gem,5,RE::SOUL_LEVEL::kGrand,{},true);
    u->GetContainer(Container::Crafting)->Put(&gem,2);
    Soulgems::Recover();assert((counts(bank,&gem)==std::array{2,5}));
    player->Put(&gem,25);u->recipes.insert(gem.GetFormID());
    Soulgems::BeginLoan(true);assert((counts(player,&gem)==std::array{27,5}));
    Soulgems::EndLoan();assert((counts(player,&gem)==std::array{25,0}));
    assert((counts(bank,&gem)==std::array{2,5}));
    reset();
    prefilled.linkedSoulGem=&gem;bank->Put(&prefilled,3);player->Put(&gem,25);
    Soulgems::BeginLoan(false);
    player->RemoveItem(&prefilled,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,nullptr,nullptr);
    player->Put(&gem,1);Soulgems::EndLoan();
    assert((counts(player,&gem)==std::array{25,0}));
    assert((counts(bank,&gem)==std::array{1,0}));assert((counts(bank,&prefilled)==std::array{0,2}));
    reset();
    bank->Put(&prefilled,1);Soulgems::BeginLoan(false);
    RE::TESSoulGem unknown(103,RE::SOUL_LEVEL::kNone);
    player->RemoveItem(&prefilled,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,nullptr,nullptr);
    player->Put(&unknown,1);Soulgems::EndLoan();
    assert(player->inventory[&unknown].first==1);
    reset();
    bank->Put(&prefilled,2);Soulgems::BeginLoan(false);
    player->inventory[&prefilled].first=0;Soulgems::EndLoan();
    assert(bank->inventory[&prefilled].first==0);
    reset();
    bank->Put(&prefilled,3);player->Put(&gem,25);
    auto* session=CraftingLoanState::GetSingleton();
    RE::TESObjectREFR furniture;
    session->EnterCrafting(&furniture);
    assert((counts(player,&prefilled)==std::array{0,3}));
    Settings::GetSingleton()->GSC_CraftingLoan=false;
    session->ExitCrafting();
    assert((counts(player,&prefilled)==std::array{0,0}));
    assert((counts(player,&gem)==std::array{25,0}));
    session->ExitCrafting();
    assert((counts(bank,&prefilled)==std::array{0,3}));
    Settings::GetSingleton()->GSC_CraftingLoan=true;
    u->bench=BenchType::None;session->EnterCrafting(&furniture);session->ExitCrafting();
    assert((counts(bank,&prefilled)==std::array{0,3}));
    u->bench=BenchType::Smithing;u->recipes.insert(prefilled.GetFormID());
    session->EnterCrafting(&furniture);session->ExitCrafting();
    assert((counts(bank,&prefilled)==std::array{0,3}));
    reset();
    player->Put(&gem,25000);Soulgems::Deposit(25);
    assert(player->inventory[&gem].first==25 && bank->inventory[&gem].first==24975);
    reset();
    RE::TESSoulGem lesser(104,RE::SOUL_LEVEL::kNone);
    player->Put(&gem,5);player->Put(&gem,7,RE::SOUL_LEVEL::kGrand,"Carried filled",true);
    bank->Put(&gem,40);bank->Put(&gem,10,RE::SOUL_LEVEL::kLesser,"Stored filled",true);
    player->Put(&lesser,2);bank->Put(&lesser,3);
    player->Put(&varla,30);bank->Put(&varla,8);
    player->Put(&prefilled,3,RE::SOUL_LEVEL::kNone,"Carried empty",true);player->Put(&prefilled,2);
    bank->Put(&prefilled,50,RE::SOUL_LEVEL::kNone,"Stored empty",true);bank->Put(&prefilled,12);
    Soulgems::TakeEmpty(25);
    assert((counts(player,&gem)==std::array{25,7}));assert((counts(bank,&gem)==std::array{20,10}));
    assert((counts(player,&lesser)==std::array{5,0}));assert((counts(bank,&lesser)==std::array{0,0}));
    assert((counts(player,&varla)==std::array{30,0}));assert((counts(bank,&varla)==std::array{8,0}));
    assert((counts(player,&prefilled)==std::array{25,2}));assert((counts(bank,&prefilled)==std::array{28,12}));
    assert(player->inventory[&prefilled].second->lists.back()->owner=="Stored empty");
    assert(empty->inventory[&gem].first==0 && filled->inventory[&gem].first==0);
    Soulgems::TakeEmpty(25);assert((counts(player,&gem)==std::array{25,7}));
    Soulgems::TakeEmpty(0);Soulgems::TakeEmpty(-1);Soulgems::TakeEmpty(5);
    assert((counts(player,&gem)==std::array{25,7}));assert((counts(bank,&gem)==std::array{20,10}));
    Soulgems::TakeEmpty();assert((counts(player,&gem)==std::array{45,7}));
    assert((counts(bank,&gem)==std::array{0,10}));
    reset();
    player->Put(&gem,3,RE::SOUL_LEVEL::kGrand,{},true);player->inventory[&gem].first=2;
    bank->Put(&gem,40);Soulgems::TakeEmpty(25);
    assert(player->inventory[&gem].first==2 && bank->inventory[&gem].first==40);
    player->inventory[&gem].second.reset();Soulgems::TakeEmpty(25);
    assert(player->inventory[&gem].first==2 && bank->inventory[&gem].first==40);
    for (int protection=0;protection<3;++protection) {
        reset();bank->Put(&gem,3);auto& entry=*bank->inventory[&gem].second;
        entry.quest=protection==0;entry.favorite=protection==1;entry.worn=protection==2;
        Soulgems::TakeEmpty(25);assert(bank->inventory[&gem].first==3 && player->inventory.empty());
    }
    reset();bank->Put(&modStar,3);Soulgems::TakeEmpty(25);
    assert(bank->inventory[&modStar].first==3 && player->inventory.empty());
    reset();player->Put(&gem,25000);bank->Put(&gem,35000);Soulgems::TakeEmpty(30000);
    assert(player->inventory[&gem].first==30000 && bank->inventory[&gem].first==30000);
    player->inventory.clear();bank->inventory.clear();
    Settings::GetSingleton()->ignored.insert(&gem);player->Put(&gem,30);
    Soulgems::Deposit(0,true);assert(player->inventory[&gem].first==30 && bank->inventory.empty());
    Soulgems::Deposit(0);assert(player->inventory[&gem].first==0 && bank->inventory[&gem].first==30);
    bank->inventory.clear();auto* sort=u->GetContainer(Container::Sort);sort->inventory.clear();sort->Put(&gem,3);
    Soulgems::Recover();assert(sort->inventory[&gem].first==3 && bank->inventory.empty());
    Settings::GetSingleton()->GSC_ReturnIgnoredItems=false;
    Soulgems::Recover({gem.GetFormID()});
    assert(sort->inventory[&gem].first==3 && bank->inventory.empty());
    Soulgems::Recover();
    assert(sort->inventory[&gem].first==0 && bank->inventory[&gem].first==3);

}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-soulgem-check-") as temporary:
    path = Path(temporary)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                    "-I", str(ROOT), str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: actual soul gem code handles mixed stacks, explicit zero souls, metadata, deposit/top-up reserves, archives, protections, recipe loans, reusable transformations, and uncertain leftovers")
