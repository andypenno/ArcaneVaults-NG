"""Compare the actual equipment/transfer CPU path with a git baseline using engine stubs."""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile

import check_stolen

ROOT = check_stolen.ROOT
BASELINE = "3e7dd85"
FILES = ("src/PlayerEquipment.cpp", "src/InventoryStacks.cpp", "src/Stores.cpp", "src/InventoryStacks.h", "src/PlayerEquipment.h")

MAIN = r'''
int main() {
    using Clock=std::chrono::steady_clock;
    auto* player=RE::PlayerCharacter::GetSingleton();
    auto* stores=Stores::GetSingleton();
    RE::TESObjectREFR bank{0x9000};Utility::GetSingleton()->containers[Container::Armor]=&bank;
    for(int size:{100,1000,5000}) for(bool transfer:{false,true}) {
        if(transfer && size>1000)continue;
        for(int sample=0;sample<(transfer?2:6);++sample) {
            player->rows.clear();bank.rows.clear();RE::SCRIPT_FUNCTION::equipped.clear();
            std::vector<RE::TESBoundObject> items(size);
            for(int i=0;i<size;++i) {
                auto& item=items[i];item.id=0x10000+i;item.armor=true;
                player->Put(&item,0,1,nullptr,"worn");
                player->rows[&item].extras.front()->uiWorn=true;
                player->Put(&item,0,2,nullptr,"spare");
                RE::SCRIPT_FUNCTION::equipped.insert(&item);
            }
            RE::InventoryMenu menu;
            RE::InventoryUpdateData data{player->id};
            RE::UIMessage message{std::string(RE::InventoryMenu::MENU_NAME),RE::UI_MESSAGE_TYPE::kInventoryUpdate,&data};
            menu.ProcessMessage(message);
            const auto begin=Clock::now();
            const auto snapshot=PlayerEquipment::Read(&menu,player);
            if(transfer) {
                auto request=std::make_shared<PlayerEquipment::Request>();
                request->work=[&]{stores->PlayerToStore(ItemCategory::Jewelry,Container::Armor);};
                PlayerEquipment::Work(request,snapshot);
            }
            const auto micros=std::chrono::duration<double,std::micro>(Clock::now()-begin).count();
            assert(snapshot.size()==items.size());
            for(auto& item:items) {
                const auto& row=player->rows.at(&item);
                assert(snapshot.at(&item).equipped.size()==1 && snapshot.at(&item).equipped.contains(row.extras.front().get()));
                assert(row.total==(transfer?1:3) && row.extras.front()->metadata=="worn");
                if(transfer)assert(bank.rows.at(&item).total==2 && bank.rows.at(&item).extras.front()->metadata=="spare");
            }
            std::cout<<size<<' '<<transfer<<' '<<micros<<'\n';
        }
    }
}
'''


def source_program(sources):
    equipment = "\n".join(line for line in sources[FILES[0]].splitlines() if not line.startswith("#include"))
    inventory = "\n".join(line for line in sources[FILES[1]].splitlines() if not line.startswith("#include"))
    stores = sources[FILES[2]]
    start = stores.index("void Stores::PlayerToStore(")
    method = stores[start:stores.index("\n}\n", start) + 3]
    main_source = MAIN if 'ItemEquipment' in sources[FILES[4]] else MAIN.replace('.equipped', '')
    return '#include "common.hpp"\n#include <iostream>\n' + inventory + equipment + method + main_source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--output", type=Path, default=ROOT / "build/benchmarks/quicksort.json")
    args = parser.parse_args()
    baseline = {p: subprocess.check_output(["git", "show", f"{args.baseline}:{p}"], cwd=ROOT, text=True) for p in FILES}
    current = {p: (ROOT / p).read_text() for p in FILES}
    common = check_stolen.common.replace("++rowVisits;", "").replace("++inventoryCopies;", "")
    report = {
        "baseline": subprocess.check_output(["git", "rev-parse", args.baseline], cwd=ROOT, text=True).strip(),
        "boundary": "Actual equipment snapshot and single-category protected transfer CPU path with engine stubs. Menu construction, UI scheduling, waiting, and Skyrim runtime costs are excluded.",
        "compiler": subprocess.check_output(["g++", "--version"], text=True).splitlines()[0],
        "harness_sha256": hashlib.sha256(common.encode()).hexdigest(),
        "source_sha256": {label: {p: hashlib.sha256(s.encode()).hexdigest() for p, s in sources.items()} for label, sources in (("before", baseline), ("after", current))},
        "batches": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    assert not args.output.exists(), "Choose a new result path to preserve earlier measurements"
    with tempfile.TemporaryDirectory(prefix="quicksort-bench-") as tmp:
        tmp = Path(tmp)
        for label, sources in (("before", baseline), ("after", current)):
            variant = tmp / label
            (variant / "src").mkdir(parents=True)
            (variant / "common.hpp").write_text("#pragma once\n" + common)
            (variant / "src/InventoryStacks.h").write_text(sources[FILES[3]])
            for name in ("StolenItems", "EnchantedItems", "PlayerEquipment"):
                (variant / f"src/{name}.h").write_text(sources[FILES[4]] if name == "PlayerEquipment" else (ROOT / f"src/{name}.h").read_text())
            cpp = variant / "bench.cpp"
            cpp.write_text(source_program(sources))
            subprocess.run(["g++", "-O2", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(variant), "-I", str(ROOT), str(cpp), "-o", str(variant / "quicksort-bench")], check=True, timeout=60)
        for batch in range(2):
            for label in (("before", "after") if batch == 0 else ("after", "before")):
                output = subprocess.check_output([str(tmp / label / "quicksort-bench")], text=True, timeout=45)
                samples = []
                for line in output.splitlines():
                    size, transfer, micros = line.split()
                    samples.append({"items": int(size), "phase": "snapshot_and_transfer" if bool(int(transfer)) else "snapshot", "microseconds": float(micros)})
                report["batches"].append({"batch": batch, "version": label, "samples": samples})
                args.output.write_text(json.dumps(report, indent=2) + "\n")
        report["comparisons"] = []
        for size, phase in ((100, "snapshot"), (1000, "snapshot"), (5000, "snapshot"), (100, "snapshot_and_transfer"), (1000, "snapshot_and_transfer")):
            values = {label: [s["microseconds"] for b in report["batches"] if b["version"] == label for s in b["samples"] if s["items"] == size and s["phase"] == phase] for label in ("before", "after")}
            medians = {label: statistics.median(v) for label, v in values.items()}
            report["comparisons"].append({"items": size, "phase": phase, "microseconds": {label: {"min": min(v), "median": medians[label], "max": max(v)} for label, v in values.items()}, "speedup": medians["before"] / medians["after"]})
        assert all(c["speedup"] > 1 for c in report["comparisons"] if c["items"] >= 1000), "Large-case improvement did not reproduce"
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: unchanged worn/spare outcomes, before/after CPU timings in {args.output}")


if __name__ == "__main__":
    main()
