"""Exercise stolen-stack gathering, returns, clearing, recovery, and menus."""
from pathlib import Path
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
program = r'''
#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <deque>
#include <functional>
#include <limits>
#include <map>
#include <memory>
#include <optional>
#include <ranges>
#include <string>
#include <type_traits>
#include <optional>
#include <string_view>
#include <unordered_map>
#include <unordered_set>
#include <vector>
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace std { template<class... Args> string format(const char*,Args...){return "title";} }
namespace logger { inline void error(const char*) {} }
namespace RE {
using FormID=unsigned;
struct TESObjectREFR;
struct BGSKeyword { unsigned id; };
struct TESForm {
    unsigned id;bool playerOwned=false;
    inline static std::map<unsigned,TESObjectREFR*> refs;
    template<class T> static T* LookupByID(unsigned id) { return refs.contains(id)?refs[id]:nullptr; }
};
struct BGSKeywordForm {
    bool blocked=false;
    bool HasKeyword(const BGSKeyword*) const { return blocked; }
};
namespace MagicSystem { enum class SpellType { kEnchantment, kStaffEnchantment }; }
struct EnchantmentItem : BGSKeywordForm {
    struct Data { EnchantmentItem* baseEnchantment=nullptr; } data;
    bool known=false,staff=false;
    MagicSystem::SpellType GetSpellType() const { return staff?MagicSystem::SpellType::kStaffEnchantment:MagicSystem::SpellType::kEnchantment; }
};
struct TESEnchantableForm { EnchantmentItem* formEnchanting=nullptr; };
enum class WEAPON_TYPE { kOneHandSword,kStaff };
struct TESObjectWEAP { bool staff=false;WEAPON_TYPE GetWeaponType() const {return staff?WEAPON_TYPE::kStaff:WEAPON_TYPE::kOneHandSword;} };
struct TESObjectARMO {};
struct TESBoundObject {
    unsigned id;
    bool weapon=false,armor=false;
    BGSKeywordForm keywords{};TESEnchantableForm enchantable{};TESObjectWEAP weaponData{};TESObjectARMO armorData{};
    template<class T> T* As() {
        if constexpr(std::is_same_v<T,TESObjectWEAP>) return weapon?&weaponData:nullptr;
        else if constexpr(std::is_same_v<T,TESObjectARMO>) return armor?&armorData:nullptr;
        else if constexpr(std::is_same_v<T,BGSKeywordForm>) return &keywords;
        else if constexpr(std::is_same_v<T,TESEnchantableForm>) return &enchantable;
        else return nullptr;
    }
};
struct ExtraEnchantment { EnchantmentItem* enchantment; };
enum class DefaultObjectID { kKeywordDisallowEnchanting };
struct BGSDefaultObjectManager {
    BGSKeyword keyword{0xC27BD};BGSKeyword* value=&keyword;
    static BGSDefaultObjectManager* GetSingleton(){static BGSDefaultObjectManager d;return &d;}
    template<class T> T** GetObject(DefaultObjectID){return reinterpret_cast<T**>(&value);}
};
enum class ExtraDataType { kOwnership,kLinkedRef };
struct ExtraLinkedRef { struct LinkedRef { BGSKeyword* keyword;TESObjectREFR* refr; };std::vector<LinkedRef> linkedRefs; };
struct ExtraDataList {
    int count=1;TESForm* owner=nullptr;std::string metadata;ExtraLinkedRef links;std::optional<ExtraEnchantment> enchantment{};
    int GetCount() const { return count; }
    void SetCount(std::uint16_t value) { count=value; }
    TESForm* GetOwner() { return owner; }
    template<class T> T* GetByType() { if constexpr(std::is_same_v<T,ExtraEnchantment>)return enchantment?&*enchantment:nullptr;else return links.linkedRefs.empty()?nullptr:&links; }
    TESObjectREFR* GetLinkedRef(BGSKeyword* key) { for(auto& link:links.linkedRefs) if(link.keyword==key)return link.refr;return nullptr; }
    void SetLinkedRef(TESObjectREFR* ref,BGSKeyword* key) { for(auto& link:links.linkedRefs)if(link.keyword==key){link.refr=ref;return;}links.linkedRefs.push_back({key,ref}); }
    bool RemoveByType(ExtraDataType type) { if(type==ExtraDataType::kOwnership)owner=nullptr;else links.linkedRefs.clear();return true; }
    bool Same(const ExtraDataList& other) const {
        if((enchantment?enchantment->enchantment:nullptr)!=(other.enchantment?other.enchantment->enchantment:nullptr) || owner!=other.owner || metadata!=other.metadata || links.linkedRefs.size()!=other.links.linkedRefs.size())return false;
        for(std::size_t i=0;i<links.linkedRefs.size();++i)if(links.linkedRefs[i].keyword!=other.links.linkedRefs[i].keyword || links.linkedRefs[i].refr!=other.links.linkedRefs[i].refr)return false;
        return true;
    }
};
struct PlayerCharacter;
struct InventoryEntryData {
    TESBoundObject* object=nullptr;
    std::function<void(ExtraDataList*)> add;
    bool quest=false;
    InventoryEntryData()=default;
    InventoryEntryData(TESBoundObject* value,int):object(value){}
    void AddExtraList(ExtraDataList* extra){if(add)add(extra);else lists.push_back(extra);}
    bool IsQuestObject()const{return quest;}
    std::vector<ExtraDataList*> lists;std::vector<ExtraDataList*>* extraLists=&lists;
    bool IsOwnedBy(PlayerCharacter*,TESForm* owner,bool defaultTo) { return owner?owner->playerOwned:defaultTo; }
};
struct Ref { TESObjectREFR* value;explicit operator bool() const{return value!=nullptr;}TESObjectREFR* get()const{return value;} };
struct Handle { unsigned id=0;Ref get()const {return {TESForm::refs.contains(id)?TESForm::refs[id]:nullptr};} };
enum class ITEM_REMOVE_REASON { kStoreInContainer };
struct TESContainerChangedEvent { unsigned oldContainer,newContainer,baseObj;int itemCount; };
enum class BSEventNotifyControl { kContinue };
template<class T> struct BSTEventSource {};
template<class T> struct BSTEventSink { virtual BSEventNotifyControl ProcessEvent(const T*,BSTEventSource<T>*)=0; };
struct ScriptEventSourceHolder {
    std::vector<BSTEventSink<TESContainerChangedEvent>*> sinks;
    static ScriptEventSourceHolder* GetSingleton(){static ScriptEventSourceHolder h;return &h;}
    void AddEventSink(BSTEventSink<TESContainerChangedEvent>* s){sinks.push_back(s);}
    void Send(TESContainerChangedEvent e){for(auto* sink:sinks)sink->ProcessEvent(&e,nullptr);}
};
struct TESObjectREFR {
    struct ChangeFlags {static constexpr unsigned kInventory=32;};
    struct Row {int total=0;std::vector<std::shared_ptr<ExtraDataList>> extras;bool duplicate=false,quest=false;};
    unsigned id;int limit=std::numeric_limits<int>::max();bool refuse=false;unsigned changed=0;
    std::map<TESBoundObject*,Row> rows;
    struct Changes {
        TESObjectREFR* source;
        std::vector<InventoryEntryData*> entries;
        std::vector<InventoryEntryData*>* entryList=&entries;
        void AddEntryData(InventoryEntryData* entry){
            entry->add=[this,item=entry->object](ExtraDataList* extra){source->rows[item].extras.emplace_back(extra);};
            entries.push_back(entry);
        }
        ~Changes(){for(auto* entry:entries)delete entry;}
    } changes{this,{},nullptr};
    Changes* GetInventoryChanges(){changes.entryList=&changes.entries;return &changes;}

    explicit TESObjectREFR(unsigned value):id(value){TESForm::refs[id]=this;}
    unsigned GetFormID()const{return id;}Handle GetHandle()const{return {id};}
    void AddChange(unsigned flag){assert(flag==ChangeFlags::kInventory);++changed;}
    auto GetInventory()const{
        std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;
        for(const auto& [item,row]:rows){auto e=std::make_shared<InventoryEntryData>();e->quest=row.quest;for(auto& x:row.extras)e->lists.push_back(x.get());if(row.duplicate&&!e->lists.empty())e->lists.push_back(e->lists.front());result[item]={row.total,e};}return result;
    }
    std::map<TESBoundObject*,int> GetInventoryCounts()const{std::map<TESBoundObject*,int> result;for(auto& [item,row]:rows)result[item]=row.total;return result;}
    void Put(TESBoundObject* item,int plain,int count=0,TESForm* owner=nullptr,std::string metadata=""){
        auto& row=rows[item];row.total+=plain+count;if(count)row.extras.push_back(std::make_shared<ExtraDataList>(ExtraDataList{count,owner,metadata,{}}));
    }
    void RemoveItem(TESBoundObject* item,int requested,ITEM_REMOVE_REASON,ExtraDataList* extra,TESObjectREFR* target){
        if(refuse)return;
        auto& row=rows[item];int count=std::min({requested,row.total,limit});if(count<=0)return;
        auto& out=target->rows[item];
        if(extra){
            auto found=std::ranges::find_if(row.extras,[&](auto& p){return p.get()==extra;});assert(found!=row.extras.end());
            count=std::min(count,extra->count);auto copy=std::make_shared<ExtraDataList>(*extra);copy->count=count;
            auto merged=std::ranges::find_if(out.extras,[&](auto& p){return p->Same(*copy) && p->count+copy->count<=32767;});if(merged==out.extras.end())out.extras.push_back(copy);else (*merged)->count+=count;
            extra->count-=count;if(extra->count==0)row.extras.erase(found);
        }else{assert(row.extras.empty());}
        row.total-=count;out.total+=count;
        ScriptEventSourceHolder::GetSingleton()->Send({id,target->id,item->id,count});
    }
};
inline bool allocationFails=false;
inline int nativeConstructions=0;
inline void* malloc(std::size_t size){return allocationFails ? nullptr : ::operator new(size);}
inline void free(void* value){::operator delete(value);}
struct PlayerCharacter:TESObjectREFR { PlayerCharacter():TESObjectREFR(0x14){}static PlayerCharacter* GetSingleton(){static PlayerCharacter p;return &p;} };
struct TESDataHandler { BGSKeyword keyword{0x01000DE0},enchantedKeyword{0x01000DED};static TESDataHandler* GetSingleton(){static TESDataHandler d;return &d;}template<class T>T* LookupForm(unsigned id,std::string_view plugin){assert((id==0xDE0 || id==0xDED) && plugin=="ArcaneVaults-LinkedStorage.esp");return id==0xDE0?&keyword:&enchantedKeyword;} };
struct SendHUDMessage {inline static std::string message;static void ShowHUDMessage(const char* text){message=text;} };
}
namespace REL {
struct VariantID { VariantID(unsigned se,unsigned ae,unsigned vr){assert(se==11437 && ae==11583 && vr==0x117C80);} };
template<class T> struct Relocation {
    explicit Relocation(VariantID){}
    RE::ExtraDataList* operator()(void* storage)const{++RE::nativeConstructions;return new(storage)RE::ExtraDataList;}
};
template<class T>T Relocate(T se,T ae,T vr){assert(se==0x18 && ae==0x20 && vr==0x18);return sizeof(RE::ExtraDataList);}
}
namespace SKSE {
struct Tasks {std::deque<std::function<void()>> queue;void AddTask(std::function<void()> task){queue.push_back(task);}void Run(){while(!queue.empty()){auto f=queue.front();queue.pop_front();f();}}};
inline Tasks* GetTaskInterface(){static Tasks t;return &t;}
}
struct Utility {
    struct Choice {unsigned formID;};std::vector<Choice> vaults;std::map<Container,RE::TESObjectREFR*> containers;
    static Utility* GetSingleton(){static Utility u;return &u;}
    RE::TESObjectREFR* GetContainer(Container c){return containers.contains(c)?containers[c]:nullptr;}
    const auto& GetVaultChoices()const{return vaults;}
};
struct Settings {bool GSC_AllowRemovingStolenTags=false;static Settings* GetSingleton(){static Settings s;return &s;} };
inline const char* Translate(const char* text){return text;}
namespace AVTranslation {inline const char* Translate(const char* text){return text;} }
struct Stores {
    struct MenuOption {std::string text;std::function<void()> action;};
    std::vector<MenuOption> options;int cancel=-1;bool closed=false;Container opened=Container::None;
    RE::Handle navigationSource_;std::function<void()> returnToVault_;std::function<void(RE::TESObjectREFR*)> onClose;
    static Stores* GetSingleton(){static Stores s;return &s;}
    void ShowDynamicMessageBox(std::string_view,std::vector<MenuOption> value,int c){options=std::move(value);cancel=c;}
    void OpenStoreObject(RE::TESObjectREFR* source,std::function<void(RE::TESObjectREFR*)> f){f(source);}
    void CloseStoreObject(RE::TESObjectREFR*){closed=true;returnToVault_={};}
    void OpenStorageMenu(Container c,RE::TESObjectREFR*,std::function<void(RE::TESObjectREFR*)> callback){opened=c;onClose=std::move(callback);}
    void VaultMenu(RE::TESObjectREFR*){closed=false;options.clear();returnToVault_={};}
    void AllToStore(Container from,Container to) {
        auto* u=Utility::GetSingleton();auto* a=u->GetContainer(from);auto* b=u->GetContainer(to);if(!a||!b||a==b)return;
        while(!a->rows.empty()) {auto it=a->rows.begin();if(it->second.total<=0){a->rows.erase(it);continue;}
            auto* extra=it->second.extras.empty()?nullptr:it->second.extras.front().get();
            a->RemoveItem(it->first,extra?extra->count:it->second.total,RE::ITEM_REMOVE_REASON::kStoreInContainer,extra,b);
        }
    }
    void EnchantedItemsMenu(RE::TESObjectREFR*);
void StolenItemsMenu(RE::TESObjectREFR*);void OpenStolenItems(RE::TESObjectREFR*);void ShowStolenItemsMenu(RE::TESObjectREFR*);
    void Click(int i){auto action=options[i].action;options.clear();action();SKSE::GetTaskInterface()->Run();}
};
#include "src/StolenItems.h"
#include "src/EnchantedItems.h"
'''
common = program
program = '#include "common.hpp"\n'
modules = {}
for name in ("InventoryStacks", "StolenItems", "EnchantedItems"):
    text = (ROOT / f"src/{name}.cpp").read_text()
    modules[name] = '#include "common.hpp"\n' + "\n".join(line for line in text.splitlines() if not line.startswith("#include"))
source=(ROOT / "src/Stores.cpp").read_text()
for name in ["StolenItemsMenu","OpenStolenItems","ShowStolenItemsMenu","EnchantedItemsMenu"]:
    start=source.index("void Stores::"+name+"(")
    program += source[start:source.index("\n}",start)+2]
program += r'''
int main(){
    RE::TESObjectREFR alchemy{1},personal{2},junk{3},trade{4},archive{5},sort{6},ignore{7},source{8};
    auto* u=Utility::GetSingleton();auto* player=RE::PlayerCharacter::GetSingleton();auto* s=Settings::GetSingleton();auto* menu=Stores::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    u->vaults={{1},{2},{3},{4},{6},{7},{1},{999}};u->containers={{Container::StolenItems,&archive},{Container::Trade,&trade},{Container::Sort,&sort},{Container::Ignore,&ignore}};
    RE::TESForm foreign{20},own{21,true},allied{22,true};RE::TESBoundObject ingredient{100},weapon{101};
    RE::BGSKeyword foreignKey{200};auto* key=&RE::TESDataHandler::GetSingleton()->keyword;
    auto count=[](RE::TESObjectREFR& ref,RE::TESBoundObject& item){return ref.rows[&item].total;};
    auto clean=[&]{for(auto* ref:{&alchemy,&personal,&junk,&trade,&archive,&sort,&ignore,static_cast<RE::TESObjectREFR*>(player)}){ref->rows.clear();ref->refuse=false;ref->limit=std::numeric_limits<int>::max();}tasks->Run();StolenItems::Reset();};
    StolenItems::Init();
    alchemy.Put(&ingredient,998,2,&foreign,"soul/charge/temper/enchantment");
    alchemy.rows[&ingredient].extras[0]->SetLinkedRef(&sort,&foreignKey);
    auto stacks=StolenItems::GetStacks(&alchemy);assert(stacks.size()==1 && stacks[0].count==2 && count(alchemy,ingredient)==1000);
    alchemy.rows[&ingredient].duplicate=true;assert(StolenItems::GetStacks(&alchemy).empty());alchemy.rows[&ingredient].duplicate=false;
    alchemy.rows[&ingredient].extras[0]->count=1001;assert(StolenItems::GetStacks(&alchemy).empty());alchemy.rows[&ingredient].extras[0]->count=2;
    personal.Put(&weapon,0,5,&own,"own");personal.Put(&weapon,0,3,&allied,"allied");personal.Put(&weapon,0,7,nullptr,"plain");
    for(auto* ref:{&trade,&sort,&ignore})ref->Put(&ingredient,0,9,&foreign,"excluded");
    assert(StolenItems::GetStoredStacks().size()==1);assert(StolenItems::Gather());assert(count(archive,ingredient)==2 && count(alchemy,ingredient)==998);
    auto moved=archive.rows[&ingredient].extras[0];assert(moved->GetLinkedRef(key)==&alchemy && moved->GetLinkedRef(&foreignKey)==&sort && moved->owner==&foreign);
    assert(StolenItems::Return());auto back=alchemy.rows[&ingredient].extras[0];assert(count(alchemy,ingredient)==1000 && back->metadata=="soul/charge/temper/enchantment" && back->GetLinkedRef(key)==nullptr && back->GetLinkedRef(&foreignKey)==&sort && back->owner==&foreign);
    clean();alchemy.Put(&ingredient,0,2,&foreign,"same");personal.Put(&ingredient,0,3,&foreign,"same");junk.Put(&ingredient,0,4,&foreign,"different");
    assert(StolenItems::Gather());assert(archive.rows[&ingredient].extras.size()==3 && count(archive,ingredient)==9);
    assert(StolenItems::Return());assert(count(alchemy,ingredient)==2 && count(personal,ingredient)==3 && count(junk,ingredient)==4);
    clean();alchemy.Put(&ingredient,5,25000,&foreign,"large");alchemy.limit=9999;archive.limit=9999;
    assert(StolenItems::Gather() && count(archive,ingredient)==25000 && count(alchemy,ingredient)==5);assert(StolenItems::Return() && count(alchemy,ingredient)==25005);
    clean();alchemy.Put(&weapon,0,2,&foreign,"enchanted");alchemy.Put(&weapon,0,3,&foreign,"tempered");assert(StolenItems::Gather());
    auto selected=archive.rows[&weapon].extras[0].get();archive.RemoveItem(&weapon,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,selected,player);tasks->Run();
    assert(player->rows[&weapon].extras[0]->GetLinkedRef(key)==nullptr && player->rows[&weapon].extras[0]->owner==&foreign);assert(StolenItems::Return() && count(alchemy,weapon)==4 && count(*player,weapon)==1);
    clean();archive.Put(&ingredient,4,2,&foreign,"manual");assert(StolenItems::Return());assert(count(*player,ingredient)==6 && player->rows[&ingredient].extras[0]->owner==&foreign);
    clean();alchemy.Put(&ingredient,998,2,&foreign,"valuable");assert(!StolenItems::Clear() && count(alchemy,ingredient)==1000);s->GSC_AllowRemovingStolenTags=true;assert(StolenItems::Clear());
    assert(count(alchemy,ingredient)==1000 && StolenItems::GetStacks(&alchemy).empty() && count(archive,ingredient)==0 && alchemy.rows[&ingredient].extras[0]->metadata=="valuable");assert(StolenItems::Gather() && count(archive,ingredient)==0);
    clean();alchemy.Put(&ingredient,0,3,&foreign,"refused");alchemy.refuse=true;assert(!StolenItems::Gather() && count(alchemy,ingredient)==3 && count(archive,ingredient)==0);alchemy.refuse=false;assert(StolenItems::Recover());assert(!alchemy.rows[&ingredient].extras[0]->GetLinkedRef(key));
    assert(StolenItems::Gather());archive.refuse=true;assert(!StolenItems::Return() && count(archive,ingredient)==3 && archive.rows[&ingredient].extras[0]->GetLinkedRef(key)==&alchemy);archive.refuse=false;assert(StolenItems::Recover() && count(alchemy,ingredient)==3);
    clean();alchemy.Put(&ingredient,0,2,&foreign,"capacity");archive.Put(&ingredient,std::numeric_limits<int>::max());player->Put(&ingredient,std::numeric_limits<int>::max());assert(!StolenItems::Gather() && count(alchemy,ingredient)==2);assert(count(*player,ingredient)==std::numeric_limits<int>::max() && count(archive,ingredient)==std::numeric_limits<int>::max());
    clean();alchemy.Put(&ingredient,0,2,&foreign,"full return");assert(StolenItems::Gather());alchemy.Put(&ingredient,std::numeric_limits<int>::max());assert(!StolenItems::Return() && count(archive,ingredient)==2);
    --alchemy.rows[&ingredient].total;assert(!StolenItems::Return() && count(archive,ingredient)==1);--alchemy.rows[&ingredient].total;assert(StolenItems::Return() && count(archive,ingredient)==0);
    clean();archive.Put(&ingredient,0,2,&foreign,"missing origin");archive.rows[&ingredient].extras[0]->SetLinkedRef(nullptr,key);assert(!StolenItems::Return() && count(archive,ingredient)==2);
    archive.rows[&ingredient].extras[0]->SetLinkedRef(&trade,key);assert(!StolenItems::Return() && count(trade,ingredient)==0);
    archive.rows[&ingredient].extras[0]->SetLinkedRef(&alchemy,key);assert(StolenItems::Return() && count(alchemy,ingredient)==2);
    clean();alchemy.Put(&ingredient,0,4,&foreign,"saved");personal.Put(&ingredient,0,3,&foreign,"saved");assert(StolenItems::Gather());
    // Persist links as form IDs, rebuild references, and resolve links after a load-order change.
    std::vector<std::pair<unsigned,RE::ExtraDataList>> saved;for(auto& x:archive.rows[&ingredient].extras)saved.emplace_back(x->GetLinkedRef(key)->id,*x);
    archive.rows.clear();RE::TESObjectREFR loadedAlchemy{1001},loadedPersonal{1002};u->vaults={{1001},{1002}};
    for(auto& [id,x]:saved){auto copy=std::make_shared<RE::ExtraDataList>(x);copy->SetLinkedRef(id==1?&loadedAlchemy:&loadedPersonal,key);archive.rows[&ingredient].extras.push_back(copy);archive.rows[&ingredient].total+=x.count;}
    StolenItems::Reset();assert(StolenItems::Recover() && count(loadedAlchemy,ingredient)==4 && count(loadedPersonal,ingredient)==3);
    u->vaults={{1},{2},{3},{4},{6},{7}};clean();alchemy.Put(&ingredient,0,2,&foreign,"prompt");
    int finished=0;StolenItems::ConfirmClear([&]{++finished;});assert(menu->cancel==0);menu->Click(0);assert(finished==1 && StolenItems::GetStacks(&alchemy).size()==1);
    StolenItems::ConfirmClear([&]{++finished;});StolenItems::Reset();menu->Click(1);assert(finished==1 && StolenItems::GetStacks(&alchemy).size()==1);
    StolenItems::ConfirmClear([&]{++finished;});s->GSC_AllowRemovingStolenTags=false;menu->Click(1);assert(finished==2 && StolenItems::GetStacks(&alchemy).size()==1);s->GSC_AllowRemovingStolenTags=true;
    StolenItems::ConfirmClear([&]{++finished;});menu->Click(1);assert(finished==3 && StolenItems::GetStacks(&alchemy).empty());
    clean();s->GSC_AllowRemovingStolenTags=false;alchemy.Put(&ingredient,0,2,&foreign,"menu");menu->StolenItemsMenu(&source);assert(menu->opened==Container::StolenItems && count(archive,ingredient)==2);auto close=menu->onClose;close(&source);assert(menu->closed && count(alchemy,ingredient)==2);
    s->GSC_AllowRemovingStolenTags=true;menu->StolenItemsMenu(&source);assert(menu->cancel==1 && menu->options.size()==3 && menu->options[0].text=="Stolen.Open" && menu->options[1].text=="Vault.Exit" && menu->options[2].text=="Stolen.RemoveAllTags");
    menu->Click(0);assert(count(archive,ingredient)==2);close=menu->onClose;close(&source);assert(menu->options.size()==3 && count(alchemy,ingredient)==2);
    menu->Click(2);assert(menu->cancel==0);menu->Click(1);assert(menu->options.size()==3 && count(alchemy,ingredient)==2 && StolenItems::GetStacks(&alchemy).empty());
    menu->Click(0);assert(count(archive,ingredient)==0);close=menu->onClose;close(&source);
    int returns=0;menu->returnToVault_=[&]{++returns;};
    menu->StolenItemsMenu(&source);assert(menu->options.size()==4 && menu->options[2].text=="Vault.Back" && menu->options[3].text=="Stolen.RemoveAllTags");
    menu->Click(2);assert(returns==1);
    s->GSC_AllowRemovingStolenTags=false;menu->StolenItemsMenu(&source);close=menu->onClose;close(&source);assert(returns==2);
    menu->returnToVault_={};

    RE::TESObjectREFR weapons{1001},armorBank{1002},enchantedBank{1003};
    u->containers[Container::Weapon]=&weapons;u->containers[Container::Armor]=&armorBank;u->containers[Container::EnchantedItems]=&enchantedBank;
    EnchantedItems::Init();
    auto resetEnchanted=[&]{weapons.rows.clear();armorBank.rows.clear();enchantedBank.rows.clear();player->rows.clear();tasks->Run();};
    RE::EnchantmentItem normal,derived,blocked,cycle,staffEnchant;
    derived.data.baseEnchantment=&normal;blocked.blocked=true;cycle.data.baseEnchantment=&cycle;staffEnchant.staff=true;
    RE::TESBoundObject sword{200,true},helmet{201,false,true},artifact{202,true},staff{203,true},plainSword{204,true},clothes{205,false,true};
    sword.enchantable.formEnchanting=&derived;helmet.enchantable.formEnchanting=&normal;artifact.enchantable.formEnchanting=&normal;artifact.keywords.blocked=true;
    staff.enchantable.formEnchanting=&normal;staff.weaponData.staff=true;
    RE::InventoryEntryData eligibility;
    assert(EnchantedItems::Eligible(&sword,eligibility,nullptr));normal.known=true;
    assert(EnchantedItems::Eligible(&sword,eligibility,nullptr));
    assert(!EnchantedItems::Eligible(&artifact,eligibility,nullptr) && !EnchantedItems::Eligible(&staff,eligibility,nullptr));
    sword.enchantable.formEnchanting=&blocked;assert(!EnchantedItems::Eligible(&sword,eligibility,nullptr));
    sword.enchantable.formEnchanting=&derived;normal.blocked=true;assert(!EnchantedItems::Eligible(&sword,eligibility,nullptr));normal.blocked=false;
    sword.enchantable.formEnchanting=&cycle;assert(!EnchantedItems::Eligible(&sword,eligibility,nullptr));sword.enchantable.formEnchanting=&staffEnchant;assert(!EnchantedItems::Eligible(&sword,eligibility,nullptr));sword.enchantable.formEnchanting=&derived;
    eligibility.quest=true;assert(!EnchantedItems::Eligible(&sword,eligibility,nullptr));eligibility.quest=false;
    auto* defaults=RE::BGSDefaultObjectManager::GetSingleton();defaults->value=nullptr;assert(!EnchantedItems::Eligible(&sword,eligibility,nullptr));defaults->value=&defaults->keyword;
    weapons.Put(&sword,6);RE::allocationFails=true;
    assert(!EnchantedItems::Gather() && count(weapons,sword)==6 && count(enchantedBank,sword)==0);
    RE::allocationFails=false;resetEnchanted();
    weapons.Put(&sword,70000);weapons.Put(&artifact,3);weapons.Put(&staff,4);armorBank.Put(&helmet,2);
    assert(EnchantedItems::Gather());assert(count(enchantedBank,sword)==70000 && count(enchantedBank,helmet)==2);
    assert(count(weapons,artifact)==3 && count(weapons,staff)==4);assert(EnchantedItems::Recover());
    assert(count(weapons,sword)==70000 && count(armorBank,helmet)==2 && count(enchantedBank,sword)==0 && RE::nativeConstructions>0);
    for(auto& extra:weapons.rows[&sword].extras)assert(!extra->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
    resetEnchanted();weapons.Put(&plainSword,10,3,&foreign,"tempered custom sword");
    weapons.rows[&plainSword].extras[0]->enchantment=RE::ExtraEnchantment{&normal};
    weapons.Put(&plainSword,0,2,&own,"plain tempered sword");
    armorBank.Put(&clothes,0,2,&foreign,"custom robe");armorBank.rows[&clothes].extras[0]->enchantment=RE::ExtraEnchantment{&normal};
    assert(EnchantedItems::Gather());assert(count(enchantedBank,plainSword)==3 && count(weapons,plainSword)==12);
    assert(count(enchantedBank,clothes)==2);
    auto* tagged=enchantedBank.rows[&plainSword].extras[0].get();enchantedBank.RemoveItem(&plainSword,1,RE::ITEM_REMOVE_REASON::kStoreInContainer,tagged,player);tasks->Run();
    assert(player->rows[&plainSword].extras[0]->owner==&foreign && player->rows[&plainSword].extras[0]->metadata=="tempered custom sword" && player->rows[&plainSword].extras[0]->enchantment->enchantment==&normal);
    assert(!player->rows[&plainSword].extras[0]->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
    assert(EnchantedItems::Recover());assert(count(weapons,plainSword)==14 && count(armorBank,clothes)==2);
    resetEnchanted();weapons.Put(&sword,0,2,&foreign,"blocked variant");weapons.rows[&sword].extras[0]->enchantment=RE::ExtraEnchantment{&blocked};
    weapons.Put(&sword,5);assert(EnchantedItems::Gather());assert(count(weapons,sword)==2 && count(enchantedBank,sword)==5);
    assert(EnchantedItems::Recover());
    resetEnchanted();weapons.Put(&plainSword,0,4,&foreign,"malformed");weapons.rows[&plainSword].extras[0]->enchantment=RE::ExtraEnchantment{&normal};weapons.rows[&plainSword].duplicate=true;
    assert(EnchantedItems::Gather() && count(weapons,plainSword)==4 && count(enchantedBank,plainSword)==0);
    resetEnchanted();weapons.Put(&sword,8);weapons.limit=2;assert(EnchantedItems::Gather() && count(enchantedBank,sword)==8);weapons.limit=std::numeric_limits<int>::max();
    enchantedBank.refuse=true;assert(!EnchantedItems::Recover() && count(enchantedBank,sword)==8);enchantedBank.refuse=false;assert(EnchantedItems::Recover() && count(weapons,sword)==8);
    weapons.refuse=true;assert(!EnchantedItems::Gather() && count(weapons,sword)==8);weapons.refuse=false;assert(EnchantedItems::Gather());
    EnchantedItems::Reset();assert(EnchantedItems::Recover() && count(weapons,sword)==8);
    resetEnchanted();enchantedBank.Put(&plainSword,3);assert(EnchantedItems::Recover() && count(*player,plainSword)==3);
    resetEnchanted();weapons.Put(&sword,2);menu->EnchantedItemsMenu(&source);assert(menu->opened==Container::EnchantedItems && count(enchantedBank,sword)==2);
    close=menu->onClose;close(&source);assert(menu->closed && count(weapons,sword)==2);

}
'''
with tempfile.TemporaryDirectory() as tmp:
    source=Path(tmp)/"stolen.cpp";binary=Path(tmp)/"stolen"
    (Path(tmp)/"common.hpp").write_text("#pragma once\n"+common)
    source.write_text(program)
    files=[]
    for name,text in modules.items():
        file=Path(tmp)/(name+".cpp");file.write_text(text);files.append(str(file))
    subprocess.run(["g++","-std=c++20","-Wall","-Wextra","-Werror","-I",str(ROOT),str(source),*files,"-o",str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
translations=json.loads((ROOT / "ini/ArcaneVaultTranslation.json").read_text())
assert translations["Stolen.Open"]=="Open"
assert translations["Stolen.RemoveAllTags"]=="Remove All Stolen Tags"
print("PASS: mixed stolen counts/variants, source markers, exclusions, partial transfers, withdrawals, manual deposits, clearing, recovery, load-order remapping model, confirmation cancellation, and actual archive menus")
