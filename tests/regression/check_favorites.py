"""Check favourite physical copies through Quick Transfer and Sort deposits."""
import argparse
from pathlib import Path
import subprocess
import tempfile
from support import engine as harness

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-ref')
parser.add_argument('--sanitize',action='store_true')
args=parser.parse_args()
ROOT=harness.ROOT
def source(name):
    return subprocess.check_output(['git','show',f'{args.source_ref}:src/{name}.cpp'],text=True,cwd=ROOT) if args.source_ref else (ROOT/f'src/{name}.cpp').read_text()
def body(text,signature,ending='\n}\n'):
    a=text.index(signature)
    return text[a:text.index(ending,a)+len(ending)]
common=harness.common.replace("struct Settings {","struct Settings {bool GSC_ReturnIgnoredItems=true;").replace('struct Stores {','struct Stores {\n    std::unordered_set<RE::FormID> sortFavorites_;\n    void CaptureSortFavorites();bool ReturnSortFavorites();void StoreToStore(ItemCategory,Container,Container);')
common=common.replace('    void AllToStore(Container from,', '    void UnusedAllToStore(Container from,',1).replace('    void UnusedAllToStore(', '    void AllToStore(Container,Container);\n    void UnusedAllToStore(',1)
common=common.replace('inline bool inspectionOpen=false;','inline std::function<void()> afterRemoval;inline bool refuseReturn=false;inline bool inspectionOpen=false;')
common=common.replace('assert(!inspectionOpen);if(refuse)return;', 'assert(!inspectionOpen);if(refuse || (refuseReturn && target->id==0x14))return;')
common=common.replace('ScriptEventSourceHolder::GetSingleton()->Send({id,target->id,item->id,count});', 'if(afterRemoval){auto callback=std::exchange(afterRemoval,{});callback();}ScriptEventSourceHolder::GetSingleton()->Send({id,target->id,item->id,count});')
stores=source('Stores')
program='#include "common.hpp"\n#include <utility>\n'+body(stores,'    int MoveItems(','\n    }')
for name in ('PlayerToStore','StoreToStore','AllToStore','CaptureSortFavorites'):
    program+=body(stores,'void Stores::'+name+'(')
program+=body(stores,'bool Stores::ReturnSortFavorites(')
program+=r'''
int main(){
    auto* player=RE::PlayerCharacter::GetSingleton();auto* u=Utility::GetSingleton();auto* stores=Stores::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    RE::TESObjectREFR bank{1001},sort{1002},junk{1003};RE::TESForm owner{300};RE::EnchantmentItem fire;
    u->containers[Container::Weapon]=&bank;u->containers[Container::Sort]=&sort;u->containers[Container::Junk]=&junk;
    RE::TESBoundObject sword{200,true};
    auto count=[&](auto& ref){return InventoryStacks::Count(&ref,&sword);};
    bool bareCopies=false;
    auto seed=[&]{player->rows.clear();bank.rows.clear();sort.rows.clear();junk.rows.clear();stores->sortFavorites_.clear();RE::refuseReturn=false;
        player->Put(&sword,0,1,&owner,"renamed favourite");auto& favorite=player->rows[&sword].extras.back();favorite->hotkey=true;favorite->enchantment=RE::ExtraEnchantment{&fire};
        if(bareCopies)player->Put(&sword,1);else player->Put(&sword,0,1,&owner,"ordinary");};
    for(bool bare:{false,true}){bareCopies=bare;
    seed();bool finished=false;PlayerEquipment::Run([&]{stores->PlayerToStore(ItemCategory::Weapon,Container::Weapon);},[&]{finished=true;});
    for(int i=0;!finished && i<200;++i){RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();std::this_thread::sleep_for(std::chrono::milliseconds(2));}
    assert(finished && count(*player)==1 && count(bank)==1);
    assert(player->rows[&sword].extras.front()->metadata=="renamed favourite" && player->rows[&sword].extras.front()->hotkey);
    assert(player->rows[&sword].extras.front()->enchantment->enchantment==&fire && bank.rows[&sword].extras.front()->metadata==(bareCopies?"":"ordinary"));
    }
    for(bool bare:{false,true})for(bool refused:{false,true})for(bool junkOnly:{false,true}){
        bareCopies=bare;
        seed();stores->CaptureSortFavorites();assert(stores->sortFavorites_.empty());
        while(count(*player)){
            auto stacks=InventoryStacks::Read(player);assert(InventoryStacks::Move(stacks.front(),&sort)>0);
        }
        for(auto& extra:sort.rows[&sword].extras)extra->hotkey=false;
        RE::refuseReturn=refused;assert(stores->ReturnSortFavorites()==!refused);
        if(!junkOnly)stores->StoreToStore(ItemCategory::Weapon,Container::Sort,Container::Weapon);
        stores->AllToStore(Container::Sort,Container::Junk);
        assert(count(bank)==(junkOnly?0:1) && count(junk)==(junkOnly?1:0) && count(sort)==(refused?1:0) && count(*player)==(refused?0:1));
        RE::refuseReturn=false;if(refused)assert(stores->ReturnSortFavorites());
        assert(count(*player)==1 && count(sort)==0);
        const auto& favorite=player->rows[&sword].extras.front();assert(favorite->metadata=="renamed favourite" && favorite->enchantment->enchantment==&fire && favorite->owner==&owner && favorite->hotkey);
        assert(!InventoryStacks::HasOrigin(favorite.get(),&RE::TESDataHandler::GetSingleton()->favoriteKeyword));
    }
    player->rows.clear();bank.rows.clear();player->Put(&sword,3);player->limit=1;
    RE::afterRemoval=[&]{auto extra=std::make_shared<RE::ExtraDataList>();extra->count=1;extra->hotkey=true;extra->metadata="new favourite";player->rows[&sword].extras.push_back(extra);};
    bool finished=false;PlayerEquipment::Run([&]{stores->PlayerToStore(ItemCategory::Weapon,Container::Weapon);},[&]{finished=true;});
    for(int i=0;!finished && i<200;++i){RE::UIMessageQueue::GetSingleton()->ProcessCommands();PlayerEquipment::PollForCheck();tasks->RunUI();tasks->Run();std::this_thread::sleep_for(std::chrono::milliseconds(2));}
    assert(finished && count(*player)==1 && count(bank)==2 && player->rows[&sword].extras.front()->hotkey);

}
'''
with tempfile.TemporaryDirectory(prefix='av-favorites-') as directory:
    root=Path(directory);(root/'common.hpp').write_text('#pragma once\n#include <utility>\n'+common);(root/'check.cpp').write_text(program)
    modules=[]
    for name in ('InventoryStacks','PlayerEquipment'):
        text=source(name)
        if name=='PlayerEquipment':text+='\nnamespace PlayerEquipment {void PollForCheck(){if(auto request=pending)Poll(request);}}\n'
        path=root/f'{name}.cpp';path.write_text('#include "common.hpp"\n'+'\n'.join(line for line in text.splitlines() if not line.startswith('#include')));modules.append(str(path))
    flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if args.sanitize else []
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror',*flags,'-I',str(ROOT),str(root/'check.cpp'),*modules,'-o',str(root/'check')],check=True,timeout=90)
    subprocess.run([str(root/'check')],check=True,timeout=15)
print('PASS: same-base favourite/plain copies, metadata, Sort favourite clearing, refused returns and Junk protection')
