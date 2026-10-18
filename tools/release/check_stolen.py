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
#include <cmath>
#include <chrono>
#include <thread>
#include <mutex>
#include <exception>
#include <stdexcept>
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
using RefHandle=unsigned;
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
struct TESSoulGem {};
struct TESBoundObject {
    unsigned id;
    bool weapon=false,armor=false;
    unsigned GetFormID()const{return id;}
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
struct ExtraHotkey {};
struct ExtraWorn {};
struct ExtraWornLeft {};
struct ExtraUniqueID {unsigned baseID;std::uint16_t uniqueID;};
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
    bool hotkey=false;bool worn=false,leftWorn=false,uiWorn=false;std::optional<ExtraUniqueID> unique{};
    int GetCount() const { return count; }
    void SetCount(std::uint16_t value) { count=value; }
    TESForm* GetOwner() { return owner; }
    template<class T> T* GetByType() { if constexpr(std::is_same_v<T,ExtraEnchantment>)return enchantment?&*enchantment:nullptr;else if constexpr(std::is_same_v<T,ExtraUniqueID>)return unique?&*unique:nullptr;else return links.linkedRefs.empty()?nullptr:&links; }
    template<class T> bool HasType()const{if constexpr(std::is_same_v<T,ExtraHotkey>)return hotkey;else if constexpr(std::is_same_v<T,ExtraWorn>)return worn;else return leftWorn;}
    TESObjectREFR* GetLinkedRef(BGSKeyword* key) { for(auto& link:links.linkedRefs) if(link.keyword==key)return link.refr;return nullptr; }
    void SetLinkedRef(TESObjectREFR* ref,BGSKeyword* key) { for(auto& link:links.linkedRefs)if(link.keyword==key){link.refr=ref;return;}links.linkedRefs.push_back({key,ref}); }
    bool RemoveByType(ExtraDataType type) { if(type==ExtraDataType::kOwnership)owner=nullptr;else links.linkedRefs.clear();return true; }
    bool Same(const ExtraDataList& other) const {
        if(hotkey!=other.hotkey)return false;
        if(worn!=other.worn || leftWorn!=other.leftWorn || uiWorn!=other.uiWorn || (enchantment?enchantment->enchantment:nullptr)!=(other.enchantment?other.enchantment->enchantment:nullptr) || owner!=other.owner || metadata!=other.metadata || links.linkedRefs.size()!=other.links.linkedRefs.size())return false;
        for(std::size_t i=0;i<links.linkedRefs.size();++i)if(links.linkedRefs[i].keyword!=other.links.linkedRefs[i].keyword || links.linkedRefs[i].refr!=other.links.linkedRefs[i].refr)return false;
        return true;
    }
};
struct PlayerCharacter;
struct InventoryEntryData {
    TESBoundObject* object=nullptr;
    std::function<void(ExtraDataList*)> add;
    bool quest=false;
    bool favorite=false;
    int countDelta=0;
    InventoryEntryData()=default;
    InventoryEntryData(TESBoundObject* value,int):object(value){}
    void AddExtraList(ExtraDataList* extra){if(add)add(extra);else lists.push_back(extra);}
    bool IsQuestObject()const{return quest;}
    bool IsFavorited()const{return favorite || std::ranges::any_of(lists,[](auto* x){return x && x->hotkey;});}
    bool IsWorn()const{return std::ranges::any_of(lists,[](auto* x){return x && (x->worn || x->leftWorn);});}
    std::vector<ExtraDataList*> lists;std::vector<ExtraDataList*>* extraLists=&lists;
    bool IsOwnedBy(PlayerCharacter*,TESForm* owner,bool defaultTo) { return owner?owner->playerOwned:defaultTo; }
};
struct Ref { TESObjectREFR* value;explicit operator bool() const{return value!=nullptr;}TESObjectREFR* get()const{return value;} };
struct Handle { unsigned id=0;unsigned native_handle()const{return id;}Ref get()const {return {TESForm::refs.contains(id)?TESForm::refs[id]:nullptr};} };
using ObjectRefHandle=Handle;
struct TESFurnitureEvent {enum class FurnitureEventType {kEnter,kExit};Ref actor,targetFurniture;FurnitureEventType type;};
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
inline bool inspectionOpen=false;
struct TESObjectREFR {
    struct ChangeFlags {static constexpr unsigned kInventory=32;};
    struct Row {int total=0;std::vector<std::shared_ptr<ExtraDataList>> extras;bool duplicate=false,quest=false,favorite=false;};
    unsigned id;int limit=std::numeric_limits<int>::max();bool refuse=false;unsigned changed=0;
    bool missingChanges=false;
    bool deferTransfers=false;std::deque<std::function<void()>> deliveries;
    std::map<TESBoundObject*,Row> rows;
    struct Changes {
        TESObjectREFR* source;
        std::vector<InventoryEntryData*> entries;
        std::vector<InventoryEntryData*>* entryList=&entries;
        int bulkTransfers=0,bulkLimit=std::numeric_limits<int>::max();bool bulkRefuse=false,lastKeepOwnership=false;
        void SetFavorite(InventoryEntryData*,ExtraDataList* extra){extra->hotkey=true;}
        void RemoveAllItems(TESObjectREFR* owner,TESObjectREFR* target,bool stealing,bool keepOwnership,bool);
        void AddEntryData(InventoryEntryData* entry){
            entry->add=[this,item=entry->object](ExtraDataList* extra){source->rows[item].extras.emplace_back(extra);};
            entries.push_back(entry);
        }
        ~Changes(){for(auto* entry:entries)delete entry;}
    } changes{this,{},nullptr};
    Changes* GetInventoryChanges(){changes.entryList=&changes.entries;return missingChanges?nullptr:&changes;}

    explicit TESObjectREFR(unsigned value):id(value){TESForm::refs[id]=this;}
    unsigned GetFormID()const{return id;}Handle GetHandle()const{return {id};}
    void AddChange(unsigned flag){assert(flag==ChangeFlags::kInventory);++changed;}
    inline static std::size_t inventoryCopies=0;
    auto GetInventory(std::function<bool(TESBoundObject&)> filter=[](auto&){return true;},bool noInit=false)const{
        (void)noInit;
        std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;
        for(const auto& [item,row]:rows){if(!item || !filter(*item))continue;++inventoryCopies;auto e=std::make_shared<InventoryEntryData>();e->object=item;e->countDelta=row.total;e->quest=row.quest;e->favorite=row.favorite;for(auto& x:row.extras)e->lists.push_back(x.get());if(row.duplicate&&!e->lists.empty())e->lists.push_back(e->lists.front());result[item]={row.total,e};}return result;
    }
    std::map<TESBoundObject*,int> GetInventoryCounts(std::function<bool(TESBoundObject&)> filter=[](auto&){return true;},bool noInit=false)const{std::map<TESBoundObject*,int> result;for(auto& [item,data]:GetInventory(filter,noInit))result[item]=data.first;return result;}
    void Put(TESBoundObject* item,int plain,int count=0,TESForm* owner=nullptr,std::string metadata=""){
        auto& row=rows[item];row.total+=plain+count;if(count)row.extras.push_back(std::make_shared<ExtraDataList>(ExtraDataList{count,owner,metadata,{}}));
    }
    void RemoveItem(TESBoundObject* item,int requested,ITEM_REMOVE_REASON,ExtraDataList* extra,TESObjectREFR* target){
        if(deferTransfers && target->id==0x14){
            deferTransfers=false;TESObjectREFR detached{0xFFFFFF};
            RemoveItem(item,requested,ITEM_REMOVE_REASON::kStoreInContainer,extra,&detached);deferTransfers=true;
            auto row=detached.rows[item];TESForm::refs.erase(detached.id);
            if(row.total>0)deliveries.push_back([item,target,row,from=id]{
                auto& out=target->rows[item];out.total+=row.total;
                for(auto& copy:row.extras)out.extras.push_back(copy);
                ScriptEventSourceHolder::GetSingleton()->Send({from,target->id,item->id,row.total});
            });
            return;
        }
        assert(!inspectionOpen);if(refuse)return;
        auto& row=rows[item];int count=std::min({requested,row.total,limit});if(count<=0)return;
        auto& out=target->rows[item];
        if(!extra && !row.extras.empty())extra=row.extras.front().get();
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
inline void TESObjectREFR::Changes::RemoveAllItems(TESObjectREFR* owner,TESObjectREFR* target,bool stealing,bool keepOwnership,bool){
    assert(owner==source && !stealing);++bulkTransfers;lastKeepOwnership=keepOwnership;if(bulkRefuse)return;
    auto snapshot=source->GetInventoryCounts();int remaining=bulkLimit;
    for(auto& [item,total]:snapshot){(void)total;while(source->rows[item].total>0 && remaining>0){
        const int before=source->rows[item].total;
        source->RemoveItem(item,std::min(before,remaining),ITEM_REMOVE_REASON::kStoreInContainer,nullptr,target);
        const int moved=before-source->rows[item].total;if(moved<=0)break;remaining-=moved;
    }}
}
inline bool allocationFails=false;
inline int nativeConstructions=0;
inline void* malloc(std::size_t size){return allocationFails ? nullptr : ::operator new(size);}
inline void free(void* value){::operator delete(value);}
struct PlayerCharacter:TESObjectREFR { TESBoundObject* currentAmmo=nullptr;TESBoundObject* GetCurrentAmmo()const{return currentAmmo;}PlayerCharacter():TESObjectREFR(0x14){}static PlayerCharacter* GetSingleton(){static PlayerCharacter p;return &p;} };
struct SCRIPT_FUNCTION {
    using Condition_t=bool(TESObjectREFR*,void*,void*,double&);
    Condition_t* conditionFunction=nullptr;
    inline static std::unordered_set<TESBoundObject*> equipped;
    inline static bool available=true,succeeds=true;
    static bool Query(TESObjectREFR*,void* item,void*,double& value){value=equipped.contains(static_cast<TESBoundObject*>(item));return succeeds;}
    static SCRIPT_FUNCTION* LocateScriptCommand(std::string_view){static SCRIPT_FUNCTION c{Query};return available?&c:nullptr;}
};
struct TESDataHandler { BGSKeyword keyword{0x01000DE0},enchantedKeyword{0x01000DED},favoriteKeyword{0x01000DF0};static TESDataHandler* GetSingleton(){static TESDataHandler d;return &d;}template<class T>T* LookupForm(unsigned id,std::string_view plugin){assert((id==0xDE0 || id==0xDED || id==0xDF0) && plugin=="ArcaneVaults-LinkedStorage.esp");return id==0xDE0?&keyword:id==0xDED?&enchantedKeyword:&favoriteKeyword;} };
struct SendHUDMessage {inline static std::string message;static void ShowHUDMessage(const char* text){message=text;} };
using BSFixedString=std::string;
struct GFxValue {
    enum Kind {Undefined,Number,Bool,DisplayObject,Object,Array} kind=Undefined;double number=0;bool boolean=false;
    std::map<std::string,GFxValue> members;
    bool GetMember(const char* name,GFxValue* value)const{assert(IsObject());auto i=members.find(name);if(i==members.end())return false;*value=i->second;return true;}
    bool IsObject()const{return kind==Object || kind==Array || kind==DisplayObject;}
    bool IsDisplayObject()const{return kind==DisplayObject;}
    bool IsNumber()const{return kind==Number;}bool IsBool()const{return kind==Bool;}
    double GetNumber()const{return number;}bool GetBool()const{return boolean;}
};
struct PlayerControls {
    bool blockPlayerInput=false;inline static bool available=true;
    static PlayerControls* GetSingleton(){static PlayerControls p;return available?&p:nullptr;}
};
struct Movie {bool visible=true;void SetVisible(bool value){visible=value;}};
enum class UI_MESSAGE_TYPE {kInventoryUpdate,kShow,kHide};
struct InventoryUpdateData {unsigned inventoryRef=0;TESBoundObject* updateObj=nullptr;};
struct UIMessage {std::string menu;UI_MESSAGE_TYPE type{};InventoryUpdateData* data=nullptr;};
struct IMenu {
    unsigned refs=1;std::shared_ptr<Movie> uiMovie=std::make_shared<Movie>();
    virtual ~IMenu()=default;void AddRef(){++refs;}void Release(){if(--refs==0)delete this;}
};
template<class T>struct GPtr {
    T* value=nullptr;GPtr()=default;explicit GPtr(T* p):value(p){if(value)value->AddRef();}~GPtr(){if(value)value->Release();}
    GPtr& operator=(std::nullptr_t){if(value)value->Release();value=nullptr;return *this;}
    explicit operator bool()const{return value!=nullptr;}T* get()const{return value;}T* operator->()const{return value;}
};
struct ItemList {
    struct Item {struct Data {InventoryEntryData* objDesc=nullptr;unsigned owner=0;} data;GFxValue obj;};
    GFxValue root{GFxValue::DisplayObject,0,false,{}};
    std::function<void()> refresh;
    inline static int refreshes=0;
    void Update(TESObjectREFR* source){assert(source==PlayerCharacter::GetSingleton());++refreshes;if(refresh)refresh();}
    inline static std::size_t rowVisits=0;
    struct Rows:std::vector<Item*> {
        struct Iterator {
            std::vector<Item*>::iterator value;
            Item* operator*()const{++rowVisits;return *value;}
            Iterator& operator++(){++value;return *this;}
            bool operator!=(const Iterator& other)const{return value!=other.value;}
        };
        Iterator begin(){return {std::vector<Item*>::begin()};}
        Iterator end(){return {std::vector<Item*>::end()};}
    } items;
};
struct InventoryMenu:IMenu {
    inline static constexpr std::string_view MENU_NAME="InventoryMenu";
    inline static bool empty=false,grouped=false,missingFields=false,wrongOwner=false,wrongCount=false,cloneIDs=false,nan=false;
    inline static bool wrongStateType=false,wrongEquippedType=false,missingMovie=false,missingList=false,uninitialized=false;
    inline static unsigned created=0,destroyed=0,updates=0;
    ItemList list;struct Data {ItemList* itemList;} runtime{&list};
    std::vector<std::unique_ptr<ItemList::Item>> items;std::vector<std::shared_ptr<InventoryEntryData>> entries;
    std::vector<std::shared_ptr<ExtraDataList>> clones;
    InventoryMenu(){++created;PlayerControls::GetSingleton()->blockPlayerInput=true;
        if(uninitialized)list.root.kind=GFxValue::Undefined;
        list.refresh=[this]{InventoryUpdateData data{PlayerCharacter::GetSingleton()->id};
            UIMessage message{std::string(MENU_NAME),UI_MESSAGE_TYPE::kInventoryUpdate,&data};ProcessMessage(message);};
        if(missingMovie)uiMovie.reset();
        if(missingList)runtime.itemList=nullptr;}
    ~InventoryMenu()override{++destroyed;PlayerControls::GetSingleton()->blockPlayerInput=true;}
    auto& GetRuntimeData(){return runtime;}
    void ProcessMessage(UIMessage& message) {
        assert(message.menu==MENU_NAME && message.type==UI_MESSAGE_TYPE::kInventoryUpdate);
        assert(message.data->inventoryRef==PlayerCharacter::GetSingleton()->id);++updates;
        list.items.clear();items.clear();entries.clear();clones.clear();
        if(empty)return;
        auto add=[&](TESBoundObject* item,int count,const std::vector<ExtraDataList*>& extras,bool worn) {
            auto entry=std::make_shared<InventoryEntryData>();entry->object=item;entry->countDelta=count+(wrongCount?1:0);
            for(auto* extra:extras){if(cloneIDs){auto copy=std::make_shared<ExtraDataList>(*extra);entry->lists.push_back(copy.get());clones.push_back(copy);}else entry->lists.push_back(extra);}
            auto row=std::make_unique<ItemList::Item>();row->obj.kind=GFxValue::Object;row->data.objDesc=entry.get();row->data.owner=wrongOwner?999:message.data->inventoryRef;
            if(!missingFields){GFxValue state;state.kind=GFxValue::Number;state.number=nan?std::numeric_limits<double>::quiet_NaN():worn?3:0;row->obj.members["equipState"]=state;
                GFxValue eq;eq.kind=GFxValue::Bool;eq.boolean=worn;row->obj.members["isEquipped"]=eq;}
            if(wrongStateType)row->obj.members["equipState"].kind=GFxValue::Bool;
            if(wrongEquippedType)row->obj.members["isEquipped"].kind=GFxValue::Number;
            entries.push_back(entry);list.items.push_back(row.get());items.push_back(std::move(row));
        };
        for(const auto& [item,data]:PlayerCharacter::GetSingleton()->GetInventory()) {
            if(data.first<=0)continue;
            const auto& extras=data.second->lists;
            if(grouped){add(item,data.first,extras,std::ranges::any_of(extras,[](auto* x){return x->worn || x->leftWorn || x->uiWorn;}));continue;}
            int represented=0;
            for(auto* extra:extras){represented+=extra->count;add(item,extra->count,{extra},extra->worn || extra->leftWorn || extra->uiWorn);}
            if(represented<data.first)add(item,data.first-represented,{},false);
        }
    }
};
struct MessageBoxMenu {inline static constexpr std::string_view MENU_NAME="MessageBoxMenu";};
struct UI {
    IMenu* menu=nullptr;bool messageBox=false;
    inline static bool available=true,factoryFails=false;
    static UI* GetSingleton(){static UI ui;return available?&ui:nullptr;}
    bool IsItemMenuOpen(){return menu!=nullptr;}
    bool IsMenuOpen(std::string_view name){return name==MessageBoxMenu::MENU_NAME?messageBox:menu!=nullptr;}
    GPtr<IMenu> GetMenu(std::string_view name){assert(name==InventoryMenu::MENU_NAME);return GPtr<IMenu>{menu};}
};
struct InputState {
    unsigned enabled=0xABCDE,stored=0x12345;std::vector<int> contexts{9,4};
    bool operator==(const InputState&)const=default;
};
inline InputState input,savedInput;
struct UIMessageQueue {
    std::deque<UI_MESSAGE_TYPE> commands;std::deque<InventoryUpdateData*> payloads;int shows=0,hides=0;
    inline static bool available=true,refuseHide=false;
    inline static int rejectHides=0;
    inline static std::function<void()> afterHide;
    bool savedBlocked=false;
    static UIMessageQueue* GetSingleton(){static UIMessageQueue q;return available?&q:nullptr;}
    void AddMessage(std::string_view name,UI_MESSAGE_TYPE type,void* data) {
        assert(name==InventoryMenu::MENU_NAME);commands.push_back(type);payloads.push_back(static_cast<InventoryUpdateData*>(data));
    }
    void ProcessCommands(){auto* ui=UI::GetSingleton();
        while(!commands.empty()){auto type=commands.front();commands.pop_front();
            auto* payload=payloads.front();payloads.pop_front();
            if(type==UI_MESSAGE_TYPE::kShow){++shows;if(ui->menu || UI::factoryFails)continue;
                savedInput=input;savedBlocked=PlayerControls::GetSingleton()->blockPlayerInput;
                ui->menu=new InventoryMenu;inspectionOpen=true;input.stored=input.enabled;input.enabled=0;input.contexts.insert(input.contexts.end(),{1,2,3});
                auto* inventory=static_cast<InventoryMenu*>(ui->menu);
                InventoryUpdateData data{PlayerCharacter::GetSingleton()->id};
                UIMessage message{std::string(InventoryMenu::MENU_NAME),UI_MESSAGE_TYPE::kInventoryUpdate,&data};
                inventory->ProcessMessage(message);
            }else if(type==UI_MESSAGE_TYPE::kInventoryUpdate){
                assert(payload && !payload->updateObj);++ItemList::refreshes;
                if(ui->menu){UIMessage message{std::string(InventoryMenu::MENU_NAME),type,payload};static_cast<InventoryMenu*>(ui->menu)->ProcessMessage(message);}
                delete payload;
            }else if(type==UI_MESSAGE_TYPE::kHide){++hides;if(rejectHides>0){--rejectHides;continue;}if(refuseHide || !ui->menu)continue;
                ui->menu->Release();ui->menu=nullptr;inspectionOpen=false;input=savedInput;
                PlayerControls::GetSingleton()->blockPlayerInput=savedBlocked;
                if(afterHide)afterHide();
            }
        }
    }
};

}
template<class To,class From>To skyrim_cast(From* source){return dynamic_cast<To>(source);}

namespace REL {
struct VariantID { VariantID(unsigned se,unsigned ae,unsigned vr){assert(se==11437 && ae==11583 && vr==0x117C80);} };
template<class T> struct Relocation {
    explicit Relocation(VariantID){}
    RE::ExtraDataList* operator()(void* storage)const{++RE::nativeConstructions;return new(storage)RE::ExtraDataList;}
};
template<class T>T Relocate(T se,T ae,T vr){assert(se==0x18 && ae==0x20 && vr==0x18);return sizeof(RE::ExtraDataList);}
}
namespace SKSE {
struct Tasks {
    std::deque<std::function<void()>> queue,ui;std::mutex lock;
    void AddTask(std::function<void()> task){std::lock_guard guard(lock);queue.push_back(std::move(task));}
    void AddUITask(std::function<void()> task){ui.push_back(std::move(task));}
    void Run(){while(true){std::function<void()> task;{std::lock_guard guard(lock);if(queue.empty())break;task=std::move(queue.front());queue.pop_front();}task();}}
    void RunUI(){while(!ui.empty()){auto task=std::move(ui.front());ui.pop_front();task();}}
};
inline Tasks* GetTaskInterface(){static Tasks t;return &t;}
}
struct Utility {
    struct Choice {unsigned formID;};std::vector<Choice> vaults;std::map<Container,RE::TESObjectREFR*> containers;
    static Utility* GetSingleton(){static Utility u;return &u;}
    RE::TESObjectREFR* GetContainer(Container c){return containers.contains(c)?containers[c]:nullptr;}
    const auto& GetVaultChoices()const{return vaults;}
};
struct Settings {bool GSC_AllowRemovingStolenTags=false;std::unordered_set<RE::TESBoundObject*> ignored;bool IsIgnored(RE::TESBoundObject* item)const{return ignored.contains(item);}static Settings* GetSingleton(){static Settings s;return &s;} };
inline CategoryMask ClassifyItem(RE::TESBoundObject* item)noexcept{return ToMask(item->armor?ItemCategory::Jewelry:ItemCategory::Weapon);}
inline CategoryMask ToMask(ItemCategory c)noexcept{return CategoryMask{1}<<static_cast<unsigned>(c);}
inline bool HasCategory(CategoryMask mask,ItemCategory c)noexcept{return (mask&ToMask(c))!=0;}
inline bool HasAnyCategory(CategoryMask mask,CategoryMask excluded)noexcept{return (mask&excluded)!=0;}
namespace DepositLearning {inline int moved=0;inline void RecordAutomaticTransfer(RE::TESObjectREFR*,RE::TESObjectREFR*,RE::TESBoundObject*,int count){moved+=count;} }
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
    void PlayerToStore(ItemCategory,Container,int=0,int=0,bool=false,CategoryMask=0);
    void OffloadItems(std::function<void()> complete={});
    void OffloadItemsNow(std::function<void()> complete={}){PlayerToStore(ItemCategory::Jewelry,Container::Armor);if(complete)complete();}

void StolenItemsMenu(RE::TESObjectREFR*);void OpenStolenItems(RE::TESObjectREFR*);void ShowStolenItemsMenu(RE::TESObjectREFR*);
    void Click(int i){auto action=options[i].action;options.clear();action();SKSE::GetTaskInterface()->Run();}
};
#include "src/StolenItems.h"
#include "src/EnchantedItems.h"
#include "src/PlayerEquipment.h"
#include "src/OffloadBatch.h"
#include "src/TransferFeedback.h"
namespace TransferFeedback {
inline void Begin(std::function<void(Complete)> start){start([]{return true;});}
inline void Reset(){}
}

'''
program += "namespace PlayerEquipment { void PollForCheck(); }\n"
common = program
program = '#include "common.hpp"\n'
stores_source=(ROOT / "src/Stores.cpp").read_text()
start=stores_source.index("void Stores::PlayerToStore(")
program+=stores_source[start:stores_source.index("\n}\n",start)+3]
start=stores_source.index("void Stores::OffloadItems(")
program+=stores_source[start:stores_source.index("\n}\n",start)+3]
modules = {}
for name in ("InventoryStacks", "StolenItems", "EnchantedItems", "PlayerEquipment"):
    text = (ROOT / f"src/{name}.cpp").read_text()
    if name=="PlayerEquipment":
        assert all(token not in text for token in ("menuMap", "factory", "ProcessMessage", "blockPlayerInput", "SetControlsState", "ToggleControls"))
        text=text.replace("std::chrono::seconds(5)","std::chrono::milliseconds(60)")
        text=text.replace("std::chrono::milliseconds(16)","std::chrono::milliseconds(1)")
        text=text.replace("std::chrono::milliseconds(100)","std::chrono::milliseconds(5)")
    modules[name] = '#include "common.hpp"\n' + "\n".join(line for line in text.splitlines() if not line.startswith("#include"))
    if name=="PlayerEquipment":
        modules[name] += "\nnamespace PlayerEquipment { void PollForCheck() { if (auto request = pending) Poll(request); } }\n"
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
    assert(EnchantedItems::Recover() && count(weapons,sword)==8);
    resetEnchanted();enchantedBank.Put(&plainSword,3);assert(EnchantedItems::Recover() && count(*player,plainSword)==3);
    resetEnchanted();weapons.Put(&sword,2);menu->EnchantedItemsMenu(&source);assert(menu->opened==Container::EnchantedItems && count(enchantedBank,sword)==2);
    close=menu->onClose;close(&source);assert(menu->closed && count(weapons,sword)==2);

    auto resetTransfer=[&] {
        player->rows.clear();armorBank.rows.clear();player->limit=std::numeric_limits<int>::max();player->refuse=false;
        RE::SCRIPT_FUNCTION::equipped.clear();RE::SCRIPT_FUNCTION::available=true;RE::SCRIPT_FUNCTION::succeeds=true;
        RE::InventoryMenu::empty=RE::InventoryMenu::grouped=RE::InventoryMenu::missingFields=RE::InventoryMenu::wrongOwner=false;
        RE::InventoryMenu::wrongCount=RE::InventoryMenu::cloneIDs=RE::InventoryMenu::nan=false;
        RE::InventoryMenu::wrongStateType=RE::InventoryMenu::wrongEquippedType=false;
        RE::InventoryMenu::missingMovie=RE::InventoryMenu::missingList=RE::InventoryMenu::uninitialized=false;
        RE::UI::available=true;RE::UI::factoryFails=false;RE::allocationFails=false;s->ignored.clear();DepositLearning::moved=0;
    };
    auto pump=[&](const auto& done){
        const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
        while(!done()){
            assert(std::chrono::steady_clock::now()<deadline);
            RE::UIMessageQueue::GetSingleton()->ProcessCommands();tasks->RunUI();tasks->Run();
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        }
    };
    auto deposit=[&](int request=0,int reserve=0,bool ignores=false){
        const auto input=RE::input;const bool blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        bool done=false;
        PlayerEquipment::Run([&]{assert(!RE::UI::GetSingleton()->menu);menu->PlayerToStore(ItemCategory::Jewelry,Container::Armor,request,reserve,ignores);},[&]{
            assert(!RE::UI::GetSingleton()->IsMenuOpen(RE::InventoryMenu::MENU_NAME));
            assert(RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);done=true;
        });
        pump([&]{return done;});assert(PlayerEquipment::Current()==nullptr);
    };
    resetTransfer();std::array<RE::TESBoundObject,10> rings{};
    std::array<RE::ExtraDataList*,10> wornCopies{};
    for(unsigned i=0;i<rings.size();++i){auto& ring=rings[i];ring.id=0x100+i;ring.armor=true;
        player->Put(&ring,2,1,nullptr,"worn ring");auto* extra=player->rows[&ring].extras.front().get();wornCopies[i]=extra;
        if(i==0)extra->worn=true;else if(i==1)extra->leftWorn=true;else extra->uiWorn=true;
        RE::SCRIPT_FUNCTION::equipped.insert(&ring);}
    auto* ui=RE::UI::GetSingleton();
    const auto capturesBefore=RE::InventoryMenu::created;RE::ItemList::rowVisits=0;deposit();
    assert(RE::ItemList::rowVisits==rings.size()*2);assert(RE::InventoryMenu::created==capturesBefore+1);
    for(unsigned i=0;i<rings.size();++i){assert(count(*player,rings[i])==1 && count(armorBank,rings[i])==2);
        assert(player->rows[&rings[i]].extras.front().get()==wornCopies[i] && wornCopies[i]->count==1);}
    assert(DepositLearning::moved==20 && !ui->menu);
    assert(RE::InventoryMenu::created==RE::InventoryMenu::destroyed && RE::InventoryMenu::updates>0);
    for(bool blocked : {false,true}){
        resetTransfer();player->Put(&rings[0],2,1,nullptr,"equipped");player->rows[&rings[0]].extras.front()->uiWorn=true;
        RE::PlayerControls::GetSingleton()->blockPlayerInput=blocked;deposit();
        assert(count(*player,rings[0])==1 && count(armorBank,rings[0])==2);
    }
    RE::PlayerControls::GetSingleton()->blockPlayerInput=false;
    auto& ring=rings[0];
    resetTransfer();player->Put(&ring,3);player->Put(&rings[1],7);
    RE::TESObjectREFR::inventoryCopies=0;
    assert(InventoryStacks::Count(player,&ring)==3 && RE::TESObjectREFR::inventoryCopies==1);
    RE::TESObjectREFR::inventoryCopies=0;
    const auto selectedStacks=InventoryStacks::Read(player,{},&ring);
    assert(selectedStacks.size()==1 && selectedStacks.front().item==&ring && selectedStacks.front().count==3);
    assert(RE::TESObjectREFR::inventoryCopies==1);
    assert(InventoryStacks::Read(player).size()==2);
    assert(InventoryStacks::Read(player,[](auto*,auto&,auto*){return false;},&ring).empty());
    player->rows[&ring].total=0;
    assert(InventoryStacks::Count(player,&ring)==0 && InventoryStacks::Read(player,{},&ring).empty());
    resetTransfer();player->Put(&ring,0,1,nullptr,"enchanted worn");player->Put(&ring,0,3,&foreign,"enchanted spare");
    auto* wornExtra=player->rows[&ring].extras.front().get();wornExtra->uiWorn=true;wornExtra->unique=RE::ExtraUniqueID{player->id,1};
    auto* spareExtra=player->rows[&ring].extras.back().get();spareExtra->unique=RE::ExtraUniqueID{player->id,2};
    spareExtra->enchantment=RE::ExtraEnchantment{&normal};RE::SCRIPT_FUNCTION::equipped.insert(&ring);
    RE::InventoryMenu::cloneIDs=true;player->limit=1;deposit();
    assert(count(*player,ring)==1 && count(armorBank,ring)==3 && player->rows[&ring].extras.front().get()==wornExtra);
    assert(armorBank.rows[&ring].extras.front()->enchantment->enchantment==&normal && armorBank.rows[&ring].extras.front()->owner==&foreign);
    assert(armorBank.rows[&ring].extras.front()->metadata=="enchanted spare");
    for(int mutation=0;mutation<4;++mutation) {
        resetTransfer();player->Put(&ring,2,1,nullptr,"equipped");auto& row=player->rows[&ring];
        row.extras.front()->uiWorn=true;row.extras.front()->unique=RE::ExtraUniqueID{player->id,1};
        RE::UIMessageQueue::afterHide=[&]{
            if(mutation==0)++row.total;
            else if(mutation==1)++row.extras.front()->unique->uniqueID;
            else if(mutation==2)row.extras.front()->worn=true;
            else row.extras.front()=std::make_shared<RE::ExtraDataList>(*row.extras.front());
        };
        deposit();assert(count(armorBank,ring)==0 && count(*player,ring)==(mutation==0?4:3));
        RE::UIMessageQueue::afterHide={};
    }
    resetTransfer();std::array<RE::TESBoundObject,200> enchantedGear{};
    for(unsigned i=0;i<enchantedGear.size();++i){auto& gear=enchantedGear[i];gear.id=0x2000+i;gear.armor=true;
        player->Put(&gear,0,1,nullptr,"worn");player->rows[&gear].extras.front()->uiWorn=true;
        player->Put(&gear,0,3,&foreign,"enchanted");player->rows[&gear].extras.back()->enchantment=RE::ExtraEnchantment{&normal};
        player->Put(&gear,0,2,nullptr,"another variant");
    }
    player->limit=1;deposit();
    for(auto& gear:enchantedGear){assert(count(*player,gear)==1 && count(armorBank,gear)==5);
        assert(player->rows[&gear].extras.front()->metadata=="worn");
        assert(std::ranges::any_of(armorBank.rows[&gear].extras,[&](auto& x){return x->enchantment && x->enchantment->enchantment==&normal && x->owner==&foreign;}));
    }
    resetTransfer();player->Put(&ring,70000,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    RE::SCRIPT_FUNCTION::equipped.insert(&ring);deposit();assert(count(*player,ring)==1 && count(armorBank,ring)==70000);
    resetTransfer();player->Put(&ring,5,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    RE::SCRIPT_FUNCTION::equipped.insert(&ring);deposit(2,2);assert(count(*player,ring)==4 && count(armorBank,ring)==2);
    deposit(0,2);assert(count(*player,ring)==2 && count(armorBank,ring)==4);
    resetTransfer();player->Put(&ring,4,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    deposit();assert(count(*player,ring)==1 && count(armorBank,ring)==4);
    for(int failure=0;failure<10;++failure){resetTransfer();player->Put(&ring,2,1,nullptr,"equipped");
        player->rows[&ring].extras.front()->uiWorn=true;RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        switch(failure){case 0:RE::UI::factoryFails=true;break;case 1:RE::UI::factoryFails=true;break;
        case 2:RE::InventoryMenu::empty=true;break;case 3:RE::InventoryMenu::missingFields=true;break;
        case 4:RE::InventoryMenu::wrongOwner=true;break;case 5:RE::InventoryMenu::wrongCount=true;break;
        case 6:RE::InventoryMenu::nan=true;break;case 7:player->rows[&ring].extras.front()->uiWorn=false;break;
        case 8:RE::InventoryMenu::wrongStateType=true;break;case 9:RE::InventoryMenu::wrongEquippedType=true;break;}
        deposit();assert(count(*player,ring)==3 && count(armorBank,ring)==0);}
    resetTransfer();player->Put(&ring,2,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    RE::SCRIPT_FUNCTION::equipped.insert(&ring);RE::InventoryMenu::grouped=true;
    deposit();assert(count(*player,ring)==3 && count(armorBank,ring)==0);
    RE::InventoryMenu::grouped=false;player->rows[&ring].extras.front()->uiWorn=false;RE::SCRIPT_FUNCTION::equipped.clear();
    deposit();assert(count(*player,ring)==0 && count(armorBank,ring)==3);
    for(int protection=0;protection<3;++protection){resetTransfer();player->Put(&ring,3);
        if(protection==0)player->rows[&ring].quest=true;else if(protection==1)player->rows[&ring].favorite=true;else s->ignored.insert(&ring);
        deposit(0,0,true);assert(count(*player,ring)==3 && count(armorBank,ring)==0);}
    for(int failure=0;failure<4;++failure){resetTransfer();player->Put(&ring,3,1,nullptr,"equipped");
        player->rows[&ring].extras.front()->uiWorn=true;RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        if(failure==0)RE::allocationFails=true;else if(failure==1)player->refuse=true;
        else if(failure==2)player->rows[&ring].duplicate=true;else player->rows[&ring].total=0;
        const int before=count(*player,ring);deposit();assert(count(*player,ring)==before && count(armorBank,ring)==0);}
    resetTransfer();player->Put(&ring,2,1,nullptr,"native worn");player->rows[&ring].extras.front()->worn=true;
    RE::SCRIPT_FUNCTION::available=false;deposit();assert(count(*player,ring)==1 && count(armorBank,ring)==2);
    assert(RE::InventoryMenu::created==RE::InventoryMenu::destroyed);

    resetTransfer();player->Put(&ring,2,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    const auto baseline=RE::input;const auto shows=RE::UIMessageQueue::GetSingleton()->shows;
    ui->messageBox=true;bool done=false;
    menu->OffloadItems([&]{assert(!ui->menu && RE::input==baseline);done=true;});
    tasks->Run();assert(!done && RE::UIMessageQueue::GetSingleton()->shows==shows);
    ui->messageBox=false;pump([&]{return done;});assert(count(*player,ring)==1 && count(armorBank,ring)==2);
    resetTransfer();player->Put(&ring,3);bool cancelledComplete=false;
    menu->OffloadItems([&]{cancelledComplete=true;});PlayerEquipment::Reset();
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();tasks->RunUI();tasks->Run();
    assert(!cancelledComplete && count(*player,ring)==3 && !ui->menu && RE::input==baseline);
    resetTransfer();player->Put(&ring,3);RE::UIMessageQueue::GetSingleton()->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kShow,nullptr);
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();auto* borrowed=ui->menu;bool borrowedDone=false;
    menu->OffloadItems([&]{borrowedDone=true;});assert(borrowedDone && ui->menu==borrowed && count(*player,ring)==3);
    RE::UIMessageQueue::GetSingleton()->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();assert(RE::input==baseline);

    resetTransfer();player->Put(&ring,3);bool threwDone=false;
    PlayerEquipment::Run([]{throw std::runtime_error("transfer failure");},[&]{threwDone=true;});
    pump([&]{return threwDone;});assert(!ui->menu && RE::input==baseline && PlayerEquipment::Current()==nullptr);
    resetTransfer();player->Put(&ring,3);bool afterOpenComplete=false;
    menu->OffloadItems([&]{afterOpenComplete=true;});RE::UIMessageQueue::GetSingleton()->ProcessCommands();
    assert(ui->menu && RE::input!=baseline);PlayerEquipment::Reset();
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();tasks->RunUI();tasks->Run();
    assert(!afterOpenComplete && !ui->menu && RE::input==baseline && count(*player,ring)==3);
    resetTransfer();player->Put(&ring,2,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    RE::UIMessageQueue::rejectHides=1;const auto retries=RE::UIMessageQueue::GetSingleton()->hides;deposit();
    assert(RE::UIMessageQueue::GetSingleton()->hides>=retries+2 && count(*player,ring)==1);
    resetTransfer();player->Put(&ring,2,1,nullptr,"equipped");player->rows[&ring].extras.front()->uiWorn=true;
    RE::InventoryMenu::empty=RE::InventoryMenu::uninitialized=true;bool initializedDone=false;
    menu->OffloadItems([&]{initializedDone=true;});RE::UIMessageQueue::GetSingleton()->ProcessCommands();
    auto* inspection=static_cast<RE::InventoryMenu*>(ui->menu);const auto refreshes=RE::ItemList::refreshes;
    PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
    assert(!initializedDone && inspection->uiMovie->visible && RE::ItemList::refreshes==refreshes);
    assert(std::ranges::find(RE::UIMessageQueue::GetSingleton()->commands,RE::UI_MESSAGE_TYPE::kInventoryUpdate)!=RE::UIMessageQueue::GetSingleton()->commands.end());
    RE::InventoryMenu::empty=false;RE::UIMessageQueue::GetSingleton()->ProcessCommands();
    PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
    assert(RE::ItemList::refreshes==refreshes+1 && !inspection->uiMovie->visible);
    assert(std::ranges::find(RE::UIMessageQueue::GetSingleton()->commands,RE::UI_MESSAGE_TYPE::kHide)!=RE::UIMessageQueue::GetSingleton()->commands.end());
    assert(count(*player,ring)==3);
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();
    assert(initializedDone && count(*player,ring)==1 && count(armorBank,ring)==2);
    resetTransfer();player->Put(&ring,3);RE::InventoryMenu::empty=true;bool emptyDone=false;
    menu->OffloadItems([&]{emptyDone=true;});RE::UIMessageQueue::GetSingleton()->ProcessCommands();
    const auto emptyRefreshes=RE::ItemList::refreshes;
    PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
    assert(RE::ItemList::refreshes==emptyRefreshes+1 && !emptyDone && count(*player,ring)==3);
    assert(std::ranges::find(RE::UIMessageQueue::GetSingleton()->commands,RE::UI_MESSAGE_TYPE::kHide)!=RE::UIMessageQueue::GetSingleton()->commands.end());
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();
    assert(emptyDone && count(*player,ring)==3 && count(armorBank,ring)==0);
    resetTransfer();player->Put(&ring,3);bool refusedDone=false;
    RE::UIMessageQueue::refuseHide=true;
    menu->OffloadItems([&]{refusedDone=true;});
    const auto revealDeadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
    bool hidden=false;
    while(!hidden || !ui->menu || !ui->menu->uiMovie->visible){
        assert(std::chrono::steady_clock::now()<revealDeadline);
        RE::UIMessageQueue::GetSingleton()->ProcessCommands();tasks->RunUI();tasks->Run();
        if(ui->menu && !ui->menu->uiMovie->visible)hidden=true;
        std::this_thread::sleep_for(std::chrono::milliseconds(2));
    }
    assert(!refusedDone && count(*player,ring)==3 && count(armorBank,ring)==0);RE::UIMessageQueue::refuseHide=false;
    RE::UIMessageQueue::GetSingleton()->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);
    pump([&]{return refusedDone;});assert(!ui->menu && RE::input==baseline);

}
'''
if __name__ == "__main__":
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
    print("PASS: UI-managed equipment inspection, exact worn/spare transfers, restored native input masks/contexts, delayed completion, cancellation and borrowed-menu protection; stolen and enchanted archive gathering, returns, clearing, recovery and menus")
