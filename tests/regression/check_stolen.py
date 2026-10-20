"""Exercise physical equipment, stolen and enchanted archive regressions."""
from support.physical import *
common += '\nstruct ProbeClock {using time_point=std::chrono::steady_clock::time_point;inline static time_point tick{};static time_point now(){return tick;}};\n'
equipment=modules['PlayerEquipment'].replace('using Clock = std::chrono::steady_clock;', 'using Clock = ProbeClock;')
start=equipment.index('        void Later(')
end=equipment.index('\n        void Close(', start)
modules['PlayerEquipment']=equipment[:start]+'        void Later(const std::shared_ptr<Request>&) {}\n'+equipment[end:]
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
        const auto deadline=ProbeClock::now()+std::chrono::seconds(2);
        while(!done()){
            assert(ProbeClock::now()<deadline);
            RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
            ProbeClock::tick+=std::chrono::milliseconds(2);
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
    assert(RE::ItemList::rowVisits>=rings.size()*2 && RE::ItemList::rowVisits<=rings.size()*3);assert(RE::InventoryMenu::created==capturesBefore+1);
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
    assert(InventoryStacks::Count(player,&ring)==3 && RE::TESObjectREFR::inventoryCopies==0);
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
    assert(!initializedDone && !inspection->uiMovie->visible && RE::ItemList::refreshes==refreshes);
    assert(std::ranges::find(RE::UIMessageQueue::GetSingleton()->commands,RE::UI_MESSAGE_TYPE::kInventoryUpdate)==RE::UIMessageQueue::GetSingleton()->commands.end());
    pump([&]{return std::ranges::find(RE::UIMessageQueue::GetSingleton()->commands,RE::UI_MESSAGE_TYPE::kInventoryUpdate)!=RE::UIMessageQueue::GetSingleton()->commands.end();});
    assert(!initializedDone && !inspection->uiMovie->visible && count(*player,ring)==3);
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
    assert(RE::ItemList::refreshes==emptyRefreshes && !emptyDone && count(*player,ring)==3);
    pump([&]{return RE::ItemList::refreshes==emptyRefreshes+1;});
    assert(!emptyDone && count(*player,ring)==3);
    pump([&]{return std::ranges::find(RE::UIMessageQueue::GetSingleton()->commands,RE::UI_MESSAGE_TYPE::kHide)!=RE::UIMessageQueue::GetSingleton()->commands.end();});
    RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
    assert(emptyDone && count(*player,ring)==3 && count(armorBank,ring)==0);
    resetTransfer();player->Put(&ring,3);bool refusedDone=false;
    RE::UIMessageQueue::refuseHide=true;
    menu->OffloadItems([&]{refusedDone=true;});
    const auto revealDeadline=ProbeClock::now()+std::chrono::seconds(2);
    bool hidden=false;
    while(!hidden || !ui->menu || !ui->menu->uiMovie->visible){
        assert(ProbeClock::now()<revealDeadline);
        RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();
        if(ui->menu && !ui->menu->uiMovie->visible)hidden=true;
        ProbeClock::tick+=std::chrono::milliseconds(2);
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
