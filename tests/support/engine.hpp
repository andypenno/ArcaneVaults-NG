#pragma once

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
    std::string displayName{};double charge{},temper{};int fixtureSoul{};
    int GetCount() const { return count; }
    void SetCount(std::uint16_t value) { count=value; }
    TESForm* GetOwner() { return owner; }
    template<class T> T* GetByType() { if constexpr(std::is_same_v<T,ExtraEnchantment>)return enchantment?&*enchantment:nullptr;else if constexpr(std::is_same_v<T,ExtraUniqueID>)return unique?&*unique:nullptr;else return links.linkedRefs.empty()?nullptr:&links; }
    template<class T> bool HasType()const{if constexpr(std::is_same_v<T,ExtraHotkey>)return hotkey;else if constexpr(std::is_same_v<T,ExtraWorn>)return worn;else return leftWorn;}
    TESObjectREFR* GetLinkedRef(BGSKeyword* key) { for(auto& link:links.linkedRefs) if(link.keyword==key)return link.refr;return nullptr; }
    void SetLinkedRef(TESObjectREFR* ref,BGSKeyword* key) { for(auto& link:links.linkedRefs)if(link.keyword==key){link.refr=ref;return;}links.linkedRefs.push_back({key,ref}); }
    bool RemoveByType(ExtraDataType type) { if(type==ExtraDataType::kOwnership)owner=nullptr;else links.linkedRefs.clear();return true; }
    bool Same(const ExtraDataList& other) const {
        if(displayName!=other.displayName || charge!=other.charge || temper!=other.temper || fixtureSoul!=other.fixtureSoul)return false;
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
    void RecoverSawnLogs() {}
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

namespace PlayerEquipment { void PollForCheck(); }
