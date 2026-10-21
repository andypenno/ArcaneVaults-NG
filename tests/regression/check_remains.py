"""Exercise production remains recovery, archive lifecycle and crafting sessions."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from performance.bench_crafting_loans import FILES, MAIN, ROOT, body, build_program, common_source


CHECK = r'''
int main(){
 auto* stores=Stores::GetSingleton();auto* u=Utility::GetSingleton();auto* player=RE::PlayerCharacter::GetSingleton();
 auto* settings=Settings::GetSingleton();auto* loan=CraftingLoanState::GetSingleton();
 std::map<Container,std::unique_ptr<RE::TESObjectREFR>> banks;
 for(auto kind:{Container::Smithing,Container::Remains,Container::Junk,Container::Alchemy,Container::Food,
     Container::Soulgem,Container::EmptySoulgems,Container::FilledSoulgems,Container::EnchantedItems}){
  banks[kind]=std::make_unique<RE::TESObjectREFR>(9000+static_cast<unsigned>(kind));u->containers[kind]=banks[kind].get();
 }
 auto* smith=banks[Container::Smithing].get();auto* archive=banks[Container::Remains].get();auto* junk=banks[Container::Junk].get();
 RE::TESBoundObject skull,pelt,kept,ignored;skull.id=1;pelt.id=2;kept.id=3;ignored.id=4;
 skull.categories=ToMask(ItemCategory::Remains)|ToMask(ItemCategory::Smithing);
 pelt.categories=ToMask(ItemCategory::Tanning)|ToMask(ItemCategory::Smithing);
 kept.categories=ToMask(ItemCategory::Junk);ignored.categories=ToMask(ItemCategory::Ignore);
 RE::TESObjectREFR source{8000},consumed{8001};RE::TESForm owner{7000};
 auto count=[](auto* bank,auto* item){return InventoryStacks::Count(bank,item);};int cases=0;
 for(int limit:{1,7,9999}){
  player->rows.clear();for(auto& [kind,bank]:banks){(void)kind;bank->rows.clear();bank->limit=limit;bank->changes.bulkLimit=9999;bank->changes.bulkRefuse=false;}
  junk->Put(&skull,0,8,&owner,"legacy skulls");junk->Put(&kept,2);junk->Put(&ignored,3);
  archive->Put(&skull,0,5,&owner,"interrupted visit");smith->Put(&pelt,9);
  junk->refuse=true;stores->ConsolidateRemains();assert(count(junk,&skull)==8 && count(smith,&skull)==5);
  junk->refuse=false;RE::TESObjectREFR::inventoryCopies=0;
  stores->StoreToStore(ItemCategory::Remains,Container::Junk,Container::Smithing);
  assert(RE::TESObjectREFR::inventoryCopies==0);stores->ConsolidateRemains();stores->ConsolidateRemains();
  assert(count(smith,&skull)==13 && count(junk,&skull)==0 && count(archive,&skull)==0);
  assert(count(junk,&kept)==2 && count(junk,&ignored)==3 && count(smith,&pelt)==9);
  stores->closed=false;stores->OpenBookArchive(Container::Remains,Container::Smithing,ItemCategory::Remains,&source);
  assert(stores->opened==Container::Remains && count(archive,&skull)==13 && count(smith,&pelt)==9);
  archive->Put(&skull,0,4,&owner,"manual deposit");archive->changes.bulkRefuse=true;
  stores->onClose(&source);assert(stores->closed && count(archive,&skull)==17 && count(smith,&skull)==0);
  archive->changes.bulkRefuse=false;stores->ConsolidateRemains();assert(count(smith,&skull)==17);
  for(const auto& stack:InventoryStacks::Read(smith,{},&skull))assert(stack.extra && stack.extra->owner==&owner);
  stores->OpenBookArchive(Container::Remains,Container::Smithing,ItemCategory::Remains,&source,true);
  archive->changes.bulkLimit=2;stores->onClose(&source);
  assert(count(smith,&skull)+count(archive,&skull)==17 && count(archive,&skull)>0);
  archive->changes.bulkLimit=9999;stores->ConsolidateRemains();assert(count(smith,&skull)==17);
  stores->ShowSmithMenu(&source);
  auto option=std::ranges::find_if(stores->options,[](auto& value){return value.text=="Vault.Remains Vault.Vault";});
  assert(option!=stores->options.end());auto action=option->action;action();
  assert(stores->opened==Container::Remains && count(archive,&skull)==17);stores->onClose(&source);
  assert(count(smith,&skull)==17);++cases;
 }
 for(auto bench:{BenchType::Smithing,BenchType::Alchemy,BenchType::Cooking,BenchType::Enchanting,BenchType::StaffEnchanting})
 for(bool all:{false,true})for(int limit:{1,7,9999}){
  loan->Reset();player->rows.clear();consumed.rows.clear();
  for(auto& [kind,bank]:banks){(void)kind;bank->rows.clear();bank->limit=limit;bank->changes.bulkLimit=9999;bank->changes.bulkRefuse=false;}
  archive->Put(&skull,0,6,&owner,"loan archive");junk->Put(&skull,0,4,&owner,"loan junk");
  player->Put(&skull,0,2,&owner,"carried favorite");player->rows[&skull].extras.front()->hotkey=true;
  settings->GSC_CraftingLoan=true;settings->GSC_AllCraftingMaterials=all;u->bench=bench;
  const bool eligible=all || bench==BenchType::Smithing;int available=10;
  for(int visit=0;visit<2;++visit){
   loan->EnterCrafting(&source);
   assert(count(player,&skull)==2+(eligible?available:0));
   if(eligible){
    assert(count(archive,&skull)==0 && count(junk,&skull)==0 && count(smith,&skull)==0);
    const auto stacks=InventoryStacks::Read(player,[](auto*,auto&,auto* extra){return extra && !extra->hotkey;},&skull);
    assert(!stacks.empty() && InventoryStacks::Move({player,&skull,stacks.front().extra,1},&consumed)==1);--available;
   }
   loan->ExitCrafting();loan->ExitCrafting();assert(count(player,&skull)==2);
   assert(player->rows[&skull].extras.front()->hotkey && player->rows[&skull].extras.front()->metadata=="carried favorite");
   int total=count(player,&skull)+count(&consumed,&skull);for(auto& [kind,bank]:banks){(void)kind;total+=count(bank.get(),&skull);}assert(total==12);
   if(eligible)assert(count(smith,&skull)==available);
  }
  ++cases;
 }
 std::cout<<"{\"passed\":true,\"cases\":"<<cases<<"}\n";
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--sanitize', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new output path')
    sources = {name: (ROOT / name).read_text() for name in FILES}
    program = build_program(sources)
    common = common_source()
    start = common.index('    void AllToStore(Container from,')
    end = common.index('\n    }', start) + 6
    common = common[:start] + '    void AllToStore(Container,Container);\n' + common[end:]
    common = common.replace('struct Stores {', 'struct Stores {void ConsolidateBooks(){}void ConsolidatePotions(){}void BookMenu(RE::TESObjectREFR*){}void NotesMenu(RE::TESObjectREFR*){}void SmithMenu(RE::TESObjectREFR*);void ShowSmithMenu(RE::TESObjectREFR*);void OpenBookArchive(Container,Container,ItemCategory,RE::TESObjectREFR*,bool=false);')
    common = common.replace('namespace std {', 'namespace std {inline string format(const char*,const char* a,const char* b){return string(a)+" "+b;}')
    extra = ''.join(body(sources['src/Stores.cpp'], 'void Stores::' + name + '(')
                    for name in ('AllToStore', 'OpenBookArchive', 'SmithMenu', 'ShowSmithMenu'))
    with tempfile.TemporaryDirectory(prefix='av-remains-') as directory:
        root = Path(directory)
        (root / 'common.hpp').write_text('#pragma once\n' + common)
        (root / 'check.cpp').write_text(program[:-len(MAIN)] + extra + CHECK)
        files = [str(root / 'check.cpp')]
        for name in ('InventoryStacks', 'Soulgems'):
            module = root / f'{name}.cpp'
            module.write_text('#include "common.hpp"\n' + '\n'.join(
                line for line in sources[f'src/{name}.cpp'].splitlines() if not line.startswith('#include')))
            files.append(str(module))
        flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
        subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(root), '-I', str(ROOT),
                        *files, '-o', str(root / 'check')], check=True, timeout=90)
        output = subprocess.check_output([str(root / 'check')], text=True, timeout=20)
        report = json.loads(output)
        report['boundary'] = 'Production archive/recovery/loan code with supplied engine inventories; not Skyrim execution.'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(f'Remains: {report["cases"]} cases passed; {args.output}')


if __name__ == '__main__':
    main()
