"""Check transfer contracts and record CPU baselines for small optimization candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile

import bench_crafting_loans as loans

ROOT = loans.ROOT
FILES = ("src/Stores.cpp", "src/PlayerEquipment.cpp", "src/InventoryStacks.cpp",
         "src/InventoryStacks.h", "src/PlayerEquipment.h")
SCENARIOS = ("reserve_below", "reserve_equal", "reserve_above", "deposit_types",
             "deposit_stacks", "withdraw_category", "equipment_present", "equipment_absent")

MAIN = r'''
int main(int argc,char** argv) {
    assert(argc==4);const std::string scenario=argv[1];const int size=std::stoi(argv[2]),sample=std::stoi(argv[3]);
    auto* player=RE::PlayerCharacter::GetSingleton();auto* stores=Stores::GetSingleton();
    auto* utility=Utility::GetSingleton();auto* settings=Settings::GetSingleton();
    auto* queue=RE::UIMessageQueue::GetSingleton();auto* ui=RE::UI::GetSingleton();
    RE::TESObjectREFR bank{9000},alchemy{9001};RE::TESForm owner{8000,false};
    utility->containers[Container::Armor]=utility->containers[Container::Gear]=&bank;
    utility->containers[Container::Alchemy]=&alchemy;
    std::array<RE::EnchantmentItem,3> enchantments;
    auto reset=[&]{
        PlayerEquipment::Reset();queue->ProcessCommands();
        for(auto* ref:std::array<RE::TESObjectREFR*,3>{player,&bank,&alchemy}){ref->rows.clear();ref->refuse=false;ref->limit=INT_MAX;}
        settings->ignored.clear();RE::SCRIPT_FUNCTION::equipped.clear();DepositLearning::moved=0;
    };
    auto count=[](RE::TESObjectREFR* ref,RE::TESBoundObject* item){return InventoryStacks::Count(ref,item);};
    auto capture=[&]{
        const bool blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        PlayerEquipment::Snapshot snapshot;
        {
            RE::InventoryMenu menu;RE::InventoryUpdateData data{player->id};
            RE::UIMessage message{std::string(RE::InventoryMenu::MENU_NAME),RE::UI_MESSAGE_TYPE::kInventoryUpdate,&data};
            menu.ProcessMessage(message);snapshot=PlayerEquipment::Read(&menu,player);
        }
        RE::PlayerControls::GetSingleton()->blockPlayerInput=blocked;
        return snapshot;
    };
    auto deposit=[&](const PlayerEquipment::Snapshot& snapshot,int keep=0,int maximum=0){
        auto request=std::make_shared<PlayerEquipment::Request>();
        request->work=[&]{stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor,maximum,keep,true);};
        PlayerEquipment::Work(request,snapshot);
    };
    auto variants=[&](RE::TESObjectREFR* ref,RE::TESBoundObject* item){
        std::array<int,3> counts{};
        for(const auto& extra:ref->rows[item].extras){
            assert(extra->owner==&owner && extra->metadata=="ring" && extra->enchantment);
            auto* enchantment=extra->enchantment->enchantment;
            assert(enchantment>=enchantments.data() && enchantment<enchantments.data()+3);
            counts[enchantment-enchantments.data()]+=extra->count;
        }
        return counts;
    };
    auto ring=[&](RE::TESBoundObject* item,int count,int variant,bool worn=false){
        player->Put(item,0,count,&owner,"ring");auto& extra=player->rows[item].extras.back();
        extra->enchantment=RE::ExtraEnchantment{&enchantments[variant]};extra->uiWorn=worn;
        if(worn)RE::SCRIPT_FUNCTION::equipped.insert(item);
    };
    if(scenario=="regression") {
        RE::TESBoundObject item{1000};item.armor=true;item.categories=ToMask(ItemCategory::Jewelry);
        for(int held:{0,2,3,7}) {
            reset();if(held)ring(&item,held,1);
            stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor,0,3,true);
            assert(count(player,&item)==std::min(held,3) && count(&bank,&item)==std::max(0,held-3));
        }
        for(bool partial:{false,true}) {
            reset();ring(&item,1,0,true);ring(&item,2,1);ring(&item,2,2);
            if(partial)player->limit=1;
            deposit(capture(),2);
            assert((variants(player,&item)==std::array{1,0,1}));
            assert((variants(&bank,&item)==std::array{0,2,1}));
            assert(player->rows[&item].extras.front()->uiWorn && DepositLearning::moved==3);
        }
        reset();ring(&item,1,0,true);ring(&item,2,1);ring(&item,2,2);deposit(capture(),0,2);
        assert((variants(player,&item)==std::array{1,0,2}));assert((variants(&bank,&item)==std::array{0,2,0}));
        for(int protection=0;protection<4;++protection) {
            reset();ring(&item,4,1);
            if(protection==0)player->rows[&item].quest=true;
            if(protection==1)player->rows[&item].favorite=true;
            if(protection==2)settings->ignored.insert(&item);
            if(protection==3)player->rows[&item].extras.front()->worn=true;
            stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor,0,0,true);
            assert(count(player,&item)==4 && count(&bank,&item)==0);
        }
        reset();ring(&item,5,1);stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor,-1);
        stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor,0,-1);
        stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor,0,0,true,ToMask(ItemCategory::Jewelry));
        assert(count(player,&item)==5 && count(&bank,&item)==0);
        for(int fault=0;fault<4;++fault) {
            reset();ring(&item,5,1);
            if(fault==0)player->refuse=true;
            if(fault==1)bank.Put(&item,INT_MAX);
            if(fault==2)player->rows[&item].duplicate=true;
            if(fault==3)player->rows[&item].extras.front()->count=6;
            stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor);
            assert(count(player,&item)==5 && count(&bank,&item)==(fault==1?INT_MAX:0));
        }
        RE::TESBoundObject reagent{1001},other{1002};reagent.categories=ToMask(ItemCategory::Catalyst);other.categories=ToMask(ItemCategory::Ingredient);
        reset();alchemy.Put(&reagent,0,5,&owner,"recipe");alchemy.Put(&other,0,8,&owner,"unrelated");player->Put(&reagent,0,2,&owner,"carried");
        stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,0,0);
        stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,0,-1);
        stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,-1);
        assert(count(player,&reagent)==2 && count(&alchemy,&reagent)==5);
        alchemy.limit=1;stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,0,4);
        assert(count(player,&reagent)==4 && count(&alchemy,&reagent)==3 && count(&alchemy,&other)==8);
        stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,0,4);assert(count(player,&reagent)==4);
        alchemy.refuse=true;stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy);
        assert(count(player,&reagent)==4 && count(&alchemy,&reagent)==3);
        reset();RE::TESSoulGem gem;gem.id=1003;gem.gem=true;gem.categories=ToMask(ItemCategory::Catalyst);alchemy.Put(&gem,0,5,&owner,"gem");
        stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,0,4);assert(count(&alchemy,&gem)==5 && count(player,&gem)==0);
        for(int kind=0;kind<3;++kind){
            reset();item.armor=kind!=1;item.weapon=kind==1;player->Put(&item,0,kind==2?0:1,&owner,"equipment");
            int worked=0,completed=0;const auto input=RE::input;const bool blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
            PlayerEquipment::Run([&]{++worked;},[&]{++completed;});
            if(kind==2)assert(worked==1 && completed==1 && !PlayerEquipment::pending && queue->commands.empty());
            else assert(worked==0 && completed==0 && PlayerEquipment::pending && queue->commands.size()==1);
            PlayerEquipment::Reset();queue->ProcessCommands();assert(!ui->menu && RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);
        }
        reset();std::cout<<"{\"regression\":true}\n";return 0;
    }
    reset();std::vector<RE::TESBoundObject> items(size);std::array<RE::TESBoundObject,3> matches{};
    RE::TESBoundObject gear{7000};gear.armor=true;gear.categories=ToMask(ItemCategory::Jewelry);
    PlayerEquipment::Snapshot snapshot;int worked=0,completed=0;
    const auto input=RE::input;const bool blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
    const bool reserve=scenario.starts_with("reserve_");
    const int held=scenario=="reserve_below"?2:scenario=="reserve_equal"?3:7;
    if(reserve || scenario=="deposit_types") {
        for(int i=0;i<size;++i){auto& item=items[i];item.id=10000+i;
            item.categories=ToMask(reserve?ItemCategory::Lockpick:ItemCategory::Jewelry);item.armor=!reserve;
            if(reserve)player->Put(&item,0,held,&owner,"reserve");
            else {ring(&item,1,0,true);ring(&item,2,1);ring(&item,2,2);}
        }
        if(!reserve)snapshot=capture();
    } else if(scenario=="deposit_stacks") {
        if(size){ring(&gear,1,0,true);for(int i=0;i<size;++i)ring(&gear,1,1+i%2);snapshot=capture();}
    } else {
        for(int i=0;i<size;++i){auto& item=items[i];item.id=10000+i;item.categories=ToMask(ItemCategory::Ingredient);
            if(scenario=="withdraw_category")alchemy.Put(&item,0,5,&owner,"unrelated");
            else player->Put(&item,0,5,&owner,"unrelated");
        }
        if(scenario=="withdraw_category") {
            for(int i=0;i<3;++i){matches[i].id=20000+i;matches[i].categories=ToMask(ItemCategory::Catalyst);alchemy.Put(&matches[i],0,5,&owner,"recipe");}
            player->Put(&matches[0],0,2,&owner,"carried");
        } else if(scenario=="equipment_present") {ring(&gear,1,0,true);player->rows[&gear].favorite=true;settings->ignored.insert(&gear);}
        else assert(scenario=="equipment_absent");
    }
    RE::Counters::Reset();const auto start=std::chrono::steady_clock::now();
    if(reserve)stores->PlayerToStore(ItemCategory::Lockpick,Container::Gear,0,3,true);
    else if(scenario=="deposit_types" || scenario=="deposit_stacks")deposit(snapshot);
    else if(scenario=="withdraw_category")stores->StoreToPlayer(ItemCategory::Catalyst,Container::Alchemy,0,4);
    else PlayerEquipment::Run([&]{++worked;},[&]{++completed;});
    const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
    const auto calls=RE::Counters::calls,visits=RE::Counters::visits,copies=RE::Counters::copies,moves=RE::Counters::moves;
    if(reserve)for(auto& item:items){assert(count(player,&item)==std::min(held,3) && count(&bank,&item)==std::max(0,held-3));
        for(auto* ref:{static_cast<RE::TESObjectREFR*>(player),&bank})for(const auto& extra:ref->rows[&item].extras)assert(extra->metadata=="reserve");
    }
    if(scenario=="deposit_types")for(auto& item:items){assert((variants(player,&item)==std::array{1,0,0}));assert((variants(&bank,&item)==std::array{0,2,2}));assert(player->rows[&item].extras.front()->uiWorn);}
    if(scenario=="deposit_stacks" && size){assert((variants(player,&gear)==std::array{1,0,0}));assert((variants(&bank,&gear)==std::array{0,(size+1)/2,size/2}));assert(player->rows[&gear].extras.front()->uiWorn);}
    if(scenario=="withdraw_category") {
        for(int i=0;i<3;++i){assert(count(player,&matches[i])==4 && count(&alchemy,&matches[i])==(i==0?3:1));
            std::map<std::string,int> metadata;for(const auto& extra:player->rows[&matches[i]].extras)metadata[extra->metadata]+=extra->count;
            assert(metadata==(i==0?std::map<std::string,int>{{"carried",2},{"recipe",2}}:std::map<std::string,int>{{"recipe",4}}));
        }
        for(auto& item:items){assert(count(&alchemy,&item)==5 && count(player,&item)==0);for(const auto& extra:alchemy.rows[&item].extras)assert(extra->metadata=="unrelated");}
    }
    if(scenario.starts_with("equipment_")) {
        if(scenario=="equipment_present")assert(PlayerEquipment::pending && worked==0 && completed==0 && queue->commands.size()==1);
        else assert(!PlayerEquipment::pending && worked==1 && completed==1 && queue->commands.empty());
        for(auto& item:items)assert(count(player,&item)==5);
        PlayerEquipment::Reset();queue->ProcessCommands();
        assert(!ui->menu && RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);
    }
    for(auto* ref:std::array<RE::TESObjectREFR*,3>{player,&bank,&alchemy})for(const auto& [item,row]:ref->rows){
        (void)item;for(const auto& extra:row.extras)assert(extra->owner==&owner);
    }
    std::cout<<"{\"scenario\":\""<<scenario<<"\",\"size\":"<<size<<",\"sample\":"<<sample<<",\"ms\":"<<ms
        <<",\"inventory_calls\":"<<calls<<",\"entries_visited\":"<<visits<<",\"entries_copied\":"<<copies<<",\"moves\":"<<moves<<"}\n";
}
'''


def program(sources):
    stores = sources["src/Stores.cpp"]
    methods = loans.body(stores, "    int MoveItems(", "\n    }")
    for name in ("PlayerToStore", "StoreToPlayer"):
        methods += loans.body(stores, "void Stores::" + name + "(")
    equipment = sources["src/PlayerEquipment.cpp"]
    main = MAIN
    if "Snapshot Capture(" in equipment:
        main=main.replace("PlayerEquipment::Read(&menu,player)", "PlayerEquipment::Read(&menu,PlayerEquipment::Capture(player),player->GetHandle().native_handle())")
    start = equipment.index("        void Later(")
    end = equipment.index("\n        void Close(", start)
    equipment = equipment[:start] + "        void Later(const std::shared_ptr<Request>&) {}\n" + equipment[end:]
    modules = "\n".join(line for name in ("src/InventoryStacks.cpp",) for line in sources[name].splitlines() if not line.startswith("#include"))
    equipment = "\n".join(line for line in equipment.splitlines() if not line.startswith("#include"))
    return '#include "common.hpp"\n#include <climits>\n' + modules + equipment + methods + main


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, help="Earlier report whose frozen working sources will be compared")
    parser.add_argument("--sizes", type=int, nargs="+", default=[0, 100, 300, 1000])
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sanitize", action="store_true", help="Run behaviour checks only with native sanitizers")
    args = parser.parse_args()
    source_dir = args.output.with_suffix(".sources")
    if args.output.exists() or source_dir.exists():
        parser.error("Choose a new output path to preserve reports and frozen sources")
    if args.samples < 2 or args.timeout <= 0 or not all(0 <= n <= 1000 for n in args.sizes):
        parser.error("Use at least two samples, a positive timeout and sizes from 0 to 1000")
    variants = {"working": {p: (ROOT / p).read_text() for p in FILES}}
    if args.baseline:
        previous = json.loads(args.baseline.read_text())
        directory = args.baseline.parent / previous["source_directory"] / "working"
        baseline = {p: (directory / p).read_text() for p in FILES}
        assert all(hashlib.sha256(s.encode()).hexdigest() == previous["sources"]["working"][p] for p, s in baseline.items())
        variants = {"baseline": baseline, **variants}
    common = loans.common_source().replace("namespace PlayerEquipment { inline const Snapshot* Current(){return nullptr;} }", "")
    report = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "boundary": "Instrumented Linux CPU model of actual transfers and equipment-entry detection. Native UI, engine latency and real classification are excluded. Equipment cases stop at queued Show or immediate no-equipment completion; snapshot setup and reset/closure are untimed. Poll delays are stubbed out. Sanitized runs perform behaviour checks only.",
              "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
              "harness_sha256": hashlib.sha256((common + MAIN).encode()).hexdigest(),
              "source_directory": source_dir.name, "baseline": str(args.baseline) if args.baseline else None,
              "sources": {v: {p: hashlib.sha256(s.encode()).hexdigest() for p, s in sources.items()} for v, sources in variants.items()},
              "regressions": [], "samples": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for variant, sources in variants.items():
        for name, source in sources.items():
            path = source_dir / variant / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(source)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="av-transfer-candidates-") as tmp:
        binaries = {}
        for variant, sources in variants.items():
            root = Path(tmp) / variant; (root / "src").mkdir(parents=True)
            for name in ("InventoryStacks", "PlayerEquipment", "StolenItems", "EnchantedItems"):
                path = "src/" + name + ".h"
                (root / path).write_text(sources[path] if path in sources else (ROOT / path).read_text())
            (root / "common.hpp").write_text("#pragma once\n" + common)
            cpp = root / "check.cpp"; cpp.write_text(program(sources)); binaries[variant] = root / "check"
            flags = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if args.sanitize else ["-O2"]
            subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", *flags, "-I", str(root), "-I", str(ROOT), str(cpp), "-o", str(binaries[variant])], check=True, timeout=90)
            subprocess.run([str(binaries[variant]), "regression", "0", "0"], check=True, timeout=args.timeout, stdout=subprocess.DEVNULL)
            report["regressions"].append({"variant": variant, "passed": True, "sanitized": args.sanitize})
            args.output.write_text(json.dumps(report, indent=2) + "\n")
        if not args.sanitize:
            for size in args.sizes:
                for scenario in SCENARIOS:
                    for sample in range(args.samples):
                        order = list(binaries) if sample % 2 == 0 else list(reversed(binaries))
                        for variant in order:
                            command = [str(binaries[variant]), scenario, str(size), str(sample)]
                            try:
                                result = subprocess.check_output(command, text=True, timeout=args.timeout)
                            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
                                report["failure"] = {"variant": variant, "scenario": scenario, "size": size, "sample": sample, "error": type(error).__name__}
                                args.output.write_text(json.dumps(report, indent=2) + "\n"); raise
                            report["samples"].append({**json.loads(result), "variant": variant, "validated": True})
                            args.output.write_text(json.dumps(report, indent=2) + "\n")
                    print(f"Checked {scenario}, size {size}", flush=True)
    groups = {}
    for sample in report["samples"]:
        groups.setdefault((sample["scenario"], sample["size"], sample["variant"]), []).append(sample)
    report["summary"] = [{"scenario": key[0], "size": key[1], "variant": key[2],
                          "min_ms": min(r["ms"] for r in rows), "median_ms": statistics.median(r["ms"] for r in rows), "max_ms": max(r["ms"] for r in rows),
                          **{name: rows[0][name] for name in ("inventory_calls", "entries_visited", "entries_copied", "moves")}} for key, rows in groups.items()]
    if args.baseline and not args.sanitize:
        summaries = {(r["scenario"], r["size"], r["variant"]): r for r in report["summary"]}
        report["comparisons"] = [{"scenario": scenario, "size": size, "speedup": summaries[scenario, size, "baseline"]["median_ms"] / summaries[scenario, size, "working"]["median_ms"]} for size in args.sizes for scenario in SCENARIOS]
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: transfer contracts and {'sanitizer checks' if args.sanitize else 'CPU samples'} in {args.output}")


if __name__ == "__main__":
    main()
