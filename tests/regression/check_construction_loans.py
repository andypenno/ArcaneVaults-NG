"""Check explicit construction loans and recovery against engine boundaries."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from performance.bench_crafting_loans import FILES, MAIN, ROOT, body, build_program, common_source
from support.data import load_json


def construction_engine():
    text = common_source()
    for before, after in (
        ('BGSKeyword keyword{0x01000DE0}', 'inline static TESBoundObject* sawnLogs=nullptr;BGSKeyword keyword{0x01000DE0}'),
        ('assert((id==0xDE0', 'if constexpr(std::is_same_v<T,TESBoundObject>){assert(id==0x300E && plugin=="HearthFires.esm");return sawnLogs;}else{assert((id==0xDE0'),
        ('&enchantedKeyword:&favoriteKeyword;} };', '&enchantedKeyword:&favoriteKeyword;}} };'),
        ('void RecoverSawnLogs() {}', 'void RecoverSawnLogs();'),
        ('bool weapon=false,armor=false;', 'bool playable=true;bool weapon=false,armor=false;'),
        ('bool bulkRefuse=false,lastKeepOwnership=false;',
         'inline static bool bulkSkipsNonPlayable=false;bool bulkRefuse=false,lastKeepOwnership=false;'),
        ('(void)total;while(source->rows[item].total>0',
         '(void)total;if(bulkSkipsNonPlayable && !item->playable)continue;while(source->rows[item].total>0'),
    ):
        assert text.count(before) == 1, f'Engine boundary changed: {before}'
        text = text.replace(before, after, 1)
    return text


CHECK = r'''
#include "extern/json/single_include/nlohmann/json.hpp"
#include <fstream>
int main(int argc,char** argv){
 assert(argc==3);nlohmann::json fixture;std::ifstream(argv[1])>>fixture;
 const bool bulkSkips=std::stoi(argv[2])!=0;
 RE::TESObjectREFR::Changes::bulkSkipsNonPlayable=bulkSkips;
 nlohmann::json report={{"bulk_skips_nonplayable_hypothesis",bulkSkips},{"visits",nlohmann::json::array()}};
 auto* player=RE::PlayerCharacter::GetSingleton();auto* utility=Utility::GetSingleton();
 auto* session=CraftingLoanState::GetSingleton();auto* settings=Settings::GetSingleton();
 RE::TESObjectREFR bench{8000};utility->bench=BenchType::Smithing;
 std::map<Container,std::unique_ptr<RE::TESObjectREFR>> banks;
 for(auto home:{Container::Smithing,Container::Food,Container::Alchemy,Container::Junk,
     Container::Soulgem,Container::EmptySoulgems,Container::FilledSoulgems}){
  banks[home]=std::make_unique<RE::TESObjectREFR>(9000+static_cast<unsigned>(home));
  utility->containers[home]=banks[home].get();
 }
 RE::TESBoundObject logs,ingot;ingot.id=100;
 logs.categories=ToMask(ItemCategory::Smithing)|ToMask(ItemCategory::Construction);
 ingot.categories=ToMask(ItemCategory::Smithing);
 auto* smithing=banks.at(Container::Smithing).get();
 auto count=[&](RE::TESObjectREFR* ref,RE::TESBoundObject* item){return InventoryStacks::Count(ref,item);};
 logs.id=0x0800300E;logs.playable=false;logs.categories=ToMask(ItemCategory::Ignore);
 RE::TESDataHandler::sawnLogs=&logs;
 RE::TESForm owner{7000};smithing->Put(&logs,0,100,&owner,"stored timber");
 smithing->limit=7;Stores::GetSingleton()->RecoverSawnLogs();
 assert(count(player,&logs)==100 && count(smithing,&logs)==0);
 const auto recovered=InventoryStacks::Read(player,{},&logs);
 assert(!recovered.empty());for(const auto& stack:recovered)assert(stack.extra && stack.extra->owner==&owner && stack.extra->metadata=="stored timber");
 Stores::GetSingleton()->RecoverSawnLogs();assert(count(player,&logs)==100);
 smithing->Put(&logs,8);smithing->refuse=true;Stores::GetSingleton()->RecoverSawnLogs();
 assert(count(player,&logs)==100 && count(smithing,&logs)==8);
 smithing->refuse=false;Stores::GetSingleton()->RecoverSawnLogs();
 assert(count(player,&logs)==108 && count(smithing,&logs)==0);
 player->rows.clear();smithing->rows.clear();logs.categories=ToMask(ItemCategory::Smithing)|ToMask(ItemCategory::Construction);
 int cases=0,failedVisits=0;
 for(const auto& test:fixture.at("cases"))for(bool all:{false,true})for(bool reload:{false,true})
 for(int prefix:{3,8})for(int limit:{1,9999})for(bool playable:{false,true}){
  session->Reset();player->rows.clear();for(auto& [home,bank]:banks){(void)home;bank->rows.clear();}
  logs.id=(static_cast<unsigned>(prefix)<<24)|std::stoul(fixture.at("local_id").get<std::string>(),nullptr,16);
  logs.playable=playable;
  settings->GSC_CraftingLoan=true;settings->GSC_AllCraftingMaterials=all;
  player->limit=smithing->limit=limit;
  int remaining=test.at("carried").get<int>()+test.at("banked").get<int>();
  player->Put(&logs,test.at("carried"));smithing->Put(&logs,test.at("banked"));
  smithing->Put(&ingot,10);
  auto visible=[&](RE::TESObjectREFR* ref){
   const auto inventory=ref->GetInventory([](RE::TESBoundObject& item){return item.playable;});
   const auto found=inventory.find(&logs);return found==inventory.end()?0:found->second.first;
  };
  auto conserved=[&]{
   int total=count(player,&logs);for(auto& [home,bank]:banks){(void)home;total+=count(bank.get(),&logs);}
   assert(total==remaining);
  };
  int visit=0;
  for(int consumed:test.at("consume")){
   session->EnterCrafting(&bench);
   const int available=count(player,&logs);
   const bool usable=available==remaining && count(smithing,&logs)==0;
   if(!usable)++failedVisits;
   conserved();
   assert(visible(player)==(playable?available:0));
   assert(visible(smithing)==(playable?count(smithing,&logs):0));
   assert(count(player,&ingot)==10 && count(smithing,&ingot)==0);
   report["visits"].push_back({{"case",test.at("name")},{"visit",++visit},{"all_materials",all},
    {"session_reset",reload},{"load_order_prefix",prefix},{"transfer_limit",limit},{"playable",playable},
    {"expected_carried",remaining},{"actual_carried",available},{"banked",count(smithing,&logs)},
    {"visible_carried",visible(player)},{"visible_banked",visible(smithing)},{"available",usable}});
   assert(consumed<=remaining);const int actualConsumption=std::min(consumed,available);
   player->rows[&logs].total-=actualConsumption;remaining-=actualConsumption;
   session->ExitCrafting();session->ExitCrafting();
   assert(count(player,&logs)==0 && count(smithing,&logs)==remaining);
   auto& observation=report["visits"].back();
   observation["consumed"]=actualConsumption;observation["post_exit_carried"]=count(player,&logs);
   observation["post_exit_banked"]=count(smithing,&logs);
   conserved();
   assert(count(player,&ingot)==0 && count(smithing,&ingot)==10);
   for(auto& [home,bank]:banks)if(home!=Container::Smithing)assert(count(bank.get(),&logs)==0);
   if(reload)session->Reset();
  }
  Stores::GetSingleton()->StoreToPlayer(ItemCategory::Smithing,Container::Smithing);
  assert(count(player,&logs)==remaining && count(smithing,&logs)==0);
  assert(visible(player)==(playable?remaining:0));conserved();
  ++cases;
 }
 report["cases"]=cases;report["failed_visits"]=failedVisits;report["passed"]=failedVisits==0;
 std::cout<<report.dump()<<'\n';return failedVisits?1:0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--bulk-skips-nonplayable', action='store_true',
                        help='Hypothetical native bulk exclusion, not a verified engine contract')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Choose a new result path')
    sources = {name: (ROOT / name).read_text() for name in FILES}
    program = build_program(sources)
    assert program.endswith(MAIN)
    with tempfile.TemporaryDirectory(prefix='av-construction-loans-') as directory:
        root = Path(directory)
        (root / 'src').mkdir()
        for name in ('InventoryStacks', 'StolenItems', 'PlayerEquipment'):
            (root / f'src/{name}.h').write_text((ROOT / f'src/{name}.h').read_text())
        (root / 'common.hpp').write_text('#pragma once\n' + construction_engine())
        recovery = body(sources['src/Stores.cpp'], 'void Stores::RecoverSawnLogs(')
        (root / 'check.cpp').write_text(program[:-len(MAIN)] + recovery + CHECK)
        files = [str(root / 'check.cpp')]
        for name in ('InventoryStacks', 'Soulgems'):
            module = root / f'{name}.cpp'
            module.write_text('#include "common.hpp"\n' + '\n'.join(
                line for line in sources[f'src/{name}.cpp'].splitlines() if not line.startswith('#include')))
            files.append(str(module))
        flags = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitize else []
        subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags,
                        '-I', str(root), '-I', str(ROOT), *files, '-o', str(root / 'check')],
                       check=True, timeout=90)
        result = subprocess.run([str(root / 'check'), str(ROOT / 'tests/fixtures/crafting/hearthfire-logs.json'),
                                 str(int(args.bulk_skips_nonplayable))],
                                text=True, stdout=subprocess.PIPE, check=False, timeout=15)
        report = load_json(result.stdout)
        report['boundary'] = ('Production loan sessions and physical transfers with supplied construction classification, '
                              'which opts out of the shipped Ignore default. Default retention is checked by keys. '
                              'Hidden UI and optional native bulk exclusion are models. Native activation, '
                              'purchase, house state, crafting conditions and real save/load are untested.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(f'{report["cases"]} cases; {report["failed_visits"]} visits failed availability; report {args.output}')
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
