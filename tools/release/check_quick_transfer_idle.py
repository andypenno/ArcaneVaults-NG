"""Check idle Quick Transfer and readiness stalls with production code and a simulated clock."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import check_stolen as harness

ROOT = harness.ROOT
OUTPUT = ROOT / "build/regressions/quick-transfer-idle.json"
MAIN = r'''
int main() {
    auto* player=RE::PlayerCharacter::GetSingleton();auto* tasks=SKSE::GetTaskInterface();
    auto* queue=RE::UIMessageQueue::GetSingleton();auto* ui=RE::UI::GetSingleton();
    RE::TESObjectREFR bank{900};Utility::GetSingleton()->containers[Container::Armor]=&bank;
    std::array<RE::TESBoundObject,10> rings{};
    for(unsigned i=0;i<rings.size();++i){rings[i].id=100+i;rings[i].armor=true;}
    for(int readiness=0;readiness<11;++readiness)for(int inventory=0;inventory<5;++inventory){
        player->rows.clear();bank.rows.clear();Settings::GetSingleton()->ignored.clear();
        RE::SCRIPT_FUNCTION::equipped.clear();ProbeClock::tick={};
        RE::InventoryMenu::uninitialized=readiness==1 || readiness==2 || readiness==4 || readiness==5 || readiness==7 || readiness==10;
        RE::InventoryMenu::empty=readiness==3 || readiness==4 || readiness==5;
        RE::InventoryMenu::missingMovie=readiness==8;
        RE::InventoryMenu::missingList=readiness==9;
        if(inventory==1 || inventory==4)for(auto& ring:rings){
            player->Put(&ring,0,1,nullptr,"worn");player->rows[&ring].extras.front()->uiWorn=true;
            RE::SCRIPT_FUNCTION::equipped.insert(&ring);
        }
        if(inventory==2){player->Put(&rings[0],3);player->rows[&rings[0]].favorite=true;}
        if(inventory==3){player->Put(&rings[0],3);Settings::GetSingleton()->ignored.insert(&rings[0]);}
        if(inventory==4)player->Put(&rings[0],3);
        const auto baseline=RE::input;const auto blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        const auto shows=queue->shows,refreshes=RE::ItemList::refreshes;bool done=false,timeout=false;
        int worked=0,readable=-1;std::vector<int> phases;
        PlayerEquipment::Run([&]{assert(!ui->menu);++worked;
            Stores::GetSingleton()->PlayerToStore(ItemCategory::Jewelry,Container::Armor,0,0,true);
        },[&]{assert(!ui->menu && RE::input==baseline && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);done=true;});
        for(int step=0;!done && step<440;++step){
            queue->ProcessCommands();
            if(ui->menu){
                auto* menu=static_cast<RE::InventoryMenu*>(ui->menu);
                if(readiness==2 || readiness==4)menu->list.root.kind=RE::GFxValue::Object;
                if(readiness==6 || readiness==7 || readiness==10)
                    for(auto* row:menu->list.items)row->obj.kind=readiness==7 && step>=3?RE::GFxValue::Object:RE::GFxValue::Undefined;
            }
            if(ui->menu && readable<0){
                readable=static_cast<int>(PlayerEquipment::Read(static_cast<RE::InventoryMenu*>(ui->menu),player).size());
                const bool unavailable=readiness>=3;
                assert(readable==(unavailable?0:inventory==1 || inventory==4?10:1));
            }
            auto request=PlayerEquipment::pending;assert(request);
            phases.push_back(static_cast<int>(request->phase));
            if((request->phase==PlayerEquipment::Phase::Opening || request->phase==PlayerEquipment::Phase::Reading) &&
                ProbeClock::now()>=request->deadline)timeout=true;
            PlayerEquipment::Poll(request);tasks->RunUI();tasks->Run();
            ProbeClock::tick+=std::chrono::milliseconds(16);
        }
        assert(done && worked==1 && !ui->menu);
        int deposited=0;for(const auto& [item,row]:bank.rows)deposited+=row.total;
        if(inventory<=3){assert(queue->shows==shows && !timeout);}
        else if(readiness!=8 && readiness!=9){assert(!timeout && ProbeClock::tick.time_since_epoch()<std::chrono::seconds(1));}
        else assert(timeout && ProbeClock::tick.time_since_epoch()>=std::chrono::seconds(1) && ProbeClock::tick.time_since_epoch()<std::chrono::milliseconds(1100));
        const bool usable=readiness==0 || readiness==1 || readiness==2 || readiness==7;
        assert(deposited==(inventory==4 && usable?3:0));
        for(auto& ring:rings){
            if(inventory==1 || inventory==4)assert(player->rows[&ring].extras.front()->metadata=="worn" && player->rows[&ring].extras.front()->uiWorn);
        }
        const int refreshed=RE::ItemList::refreshes-refreshes;
        assert(refreshed==(inventory==4 && ((readiness>=3 && readiness<=5) || readiness==7 || readiness==10)?1:0));
        std::cout<<"{\"inventory\":"<<inventory<<",\"readiness\":"<<readiness
            <<",\"simulated_ms\":"<<std::chrono::duration_cast<std::chrono::milliseconds>(ProbeClock::tick.time_since_epoch()).count()
            <<",\"readable_equipment_groups\":"<<readable<<",\"inspection_shows\":"<<queue->shows-shows<<",\"transferred\":"<<deposited
            <<",\"refreshes\":"<<refreshed<<",\"readiness_timeout\":"<<(timeout?"true":"false")<<",\"phases\":[";
        for(std::size_t i=0;i<phases.size();++i)std::cout<<(i?",":"")<<phases[i];
        std::cout<<"]}\n";
    }
    for(int budget=0;budget<3;++budget){
        player->rows.clear();bank.rows.clear();player->Put(&rings[0],3);ProbeClock::tick={};
        RE::InventoryMenu::empty=RE::InventoryMenu::uninitialized=RE::InventoryMenu::missingList=false;
        RE::InventoryMenu::missingMovie=budget==1;ui->messageBox=budget==0;queue->refuseHide=budget==2;
        const auto input=RE::input;const auto blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        bool done=false;int worked=0;long closeAt=-1,revealAt=-1;
        PlayerEquipment::Run([&]{assert(!ui->menu);++worked;},[&]{assert(!ui->menu && RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);done=true;});
        for(int step=0;!done && step<150;++step){
            const auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(ProbeClock::tick.time_since_epoch()).count();
            if(budget!=1 || ms>=752)queue->ProcessCommands();
            auto request=PlayerEquipment::pending;assert(request);PlayerEquipment::Poll(request);tasks->RunUI();tasks->Run();
            if(request->phase==PlayerEquipment::Phase::Closing && closeAt<0)closeAt=ms;
            if(budget==2 && ui->menu && request->worked && ui->menu->uiMovie->visible && revealAt<0)revealAt=ms;
            if(budget==2 && revealAt>=0){assert(worked==0);queue->refuseHide=false;queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);}
            ProbeClock::tick+=std::chrono::milliseconds(16);
        }
        assert(done && worked==(budget==2?0:1) && player->rows[&rings[0]].total==3);
        const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(ProbeClock::tick.time_since_epoch()).count();
        if(budget==0)assert(closeAt<0 && elapsed>=1000 && elapsed<1100);
        if(budget==1)assert(closeAt>=1000 && closeAt<1050 && elapsed<1100);
        if(budget==2)assert(revealAt-closeAt>=1000 && revealAt-closeAt<1050);
        ui->messageBox=false;RE::InventoryMenu::missingMovie=false;
        std::cout<<"{\"budget\":"<<budget<<",\"simulated_ms\":"<<elapsed<<",\"close_at\":"<<closeAt<<",\"reveal_at\":"<<revealAt<<"}\n";
    }
}
'''

SCHEDULING = r'''
    for(int scenario=0;scenario<8;++scenario){
        player->rows.clear();bank.rows.clear();player->Put(&rings[0],3);ProbeClock::tick={};
        RE::InventoryMenu::missingMovie=RE::InventoryMenu::missingList=RE::InventoryMenu::uninitialized=RE::InventoryMenu::empty=false;
        ui->messageBox=false;queue->refuseHide=false;queue->rejectHides=scenario==4?3:0;
        const auto input=RE::input;const auto blocked=RE::PlayerControls::GetSingleton()->blockPlayerInput;
        bool done=false,interrupted=false;int worked=0;long completed=-1;std::vector<int> phases;
        PlayerEquipment::Run([&]{assert(!ui->menu);++worked;},[&]{
            assert(!ui->menu && RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);
            done=true;completed=std::chrono::duration_cast<std::chrono::milliseconds>(ProbeClock::tick.time_since_epoch()).count();
        });
        for(int step=0;step<450;++step){
            const auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(ProbeClock::tick.time_since_epoch()).count();
            const bool commandsBlocked=scenario==0 && ms<5000;
            const bool uiTasksBlocked=scenario==1 && ms<5000;
            const bool pollBlocked=scenario==2 && ms>=16 && ms<5000;
            const bool gameTasksBlocked=(scenario==3 || (scenario==2 && ms>=16)) && ms<5000;
            if(scenario==5)queue->refuseHide=ms<5000;
            if(!commandsBlocked)queue->ProcessCommands();
            if(!done && !pollBlocked){
                auto request=PlayerEquipment::pending;assert(request);phases.push_back(static_cast<int>(request->phase));
                if(scenario==7 && request->phase==PlayerEquipment::Phase::Closing)ui->messageBox=true;
                PlayerEquipment::Poll(request);
                if(scenario==6 && request->phase==PlayerEquipment::Phase::Reading && !interrupted){
                    queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);queue->ProcessCommands();interrupted=true;
                }
            }
            if(!uiTasksBlocked)tasks->RunUI();
            if(!gameTasksBlocked)tasks->Run();
            if(scenario==5 && ms>=5000 && ui->menu){
                queue->AddMessage(RE::InventoryMenu::MENU_NAME,RE::UI_MESSAGE_TYPE::kHide,nullptr);
            }
            ProbeClock::tick+=std::chrono::milliseconds(16);
            if(done && tasks->ui.empty() && tasks->queue.empty() && queue->commands.empty())break;
        }
        assert(done && !ui->menu && worked<=1 && player->rows[&rings[0]].total==3);
        assert(RE::input==input && RE::PlayerControls::GetSingleton()->blockPlayerInput==blocked);
        if(scenario==6)assert(interrupted && worked==0);
        ui->messageBox=false;queue->refuseHide=false;
        std::cout<<"{\"schedule\":"<<scenario<<",\"completed_ms\":"<<completed<<",\"worked\":"<<worked<<",\"phases\":[";
        for(std::size_t i=0;i<phases.size();++i)std::cout<<(i?",":"")<<phases[i];
        std::cout<<"]}\n";
    }
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--source-ref", help="Run the regression against PlayerEquipment.cpp from a Git revision")
    parser.add_argument("--sanitize", action="store_true", help="Check native memory access and undefined behaviour")
    parser.add_argument("--probe-scheduling", action="store_true", help="Exercise delayed UI/game tasks, refused Hide and competing menus")
    args=parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new --output path to preserve earlier results")
    equipment = subprocess.check_output(["git","show",f"{args.source_ref}:src/PlayerEquipment.cpp"],text=True,cwd=ROOT) if args.source_ref else (ROOT / "src/PlayerEquipment.cpp").read_text()
    transformed = equipment.replace("using Clock = std::chrono::steady_clock;", "using Clock = ProbeClock;")
    start = transformed.index("        void Later(")
    end = transformed.index("\n        void Close(", start)
    transformed = transformed[:start] + "        void Later(const std::shared_ptr<Request>&) {}\n" + transformed[end:]
    transformed = "\n".join(line for line in transformed.splitlines() if not line.startswith("#include"))
    clock = "\nstruct ProbeClock { inline static std::chrono::steady_clock::time_point tick{}; using time_point=std::chrono::steady_clock::time_point; static time_point now(){return tick;} };\n"
    cases=MAIN if not args.probe_scheduling else MAIN[:MAIN.rindex("\n}")] + SCHEDULING + "\n}\n"
    if "Snapshot Capture(" in equipment:
        cases=cases.replace("PlayerEquipment::Read(static_cast<RE::InventoryMenu*>(ui->menu),player)", "PlayerEquipment::Read(static_cast<RE::InventoryMenu*>(ui->menu),PlayerEquipment::Capture(player),player->GetHandle().native_handle())")
    program = harness.program[:harness.program.index("int main(){")] + "\n#include <iostream>\n" + clock + transformed + cases
    with tempfile.TemporaryDirectory(prefix="av-idle-regression-") as directory:
        root=Path(directory)
        (root / "common.hpp").write_text("#pragma once\n" + harness.common)
        source=root / "probe.cpp";source.write_text(program)
        files=[]
        for name in ("InventoryStacks", "StolenItems", "EnchantedItems"):
            path=root / (name + ".cpp");path.write_text(harness.modules[name]);files.append(str(path))
        binary=root / "probe"
        sanitizers=["-fsanitize=address,undefined","-fno-omit-frame-pointer"] if args.sanitize else []
        subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", *sanitizers, "-I", str(root), "-I", str(ROOT), str(source), *files, "-o", str(binary)], check=True, timeout=90)
        output=subprocess.check_output([str(binary)], text=True, timeout=15)
    report={"commit":subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_ref":args.source_ref,
        "source_sha256":hashlib.sha256(equipment.encode()).hexdigest(),
        "boundary":"Production equipment lifecycle and player transfer with engine stubs. Clock advances by simulated frames; real Skyrim UI and elapsed times are not measured.",
        "inventory":["empty", "ten worn rings", "favourited only", "ignored only", "ten worn rings and three spares"],
        "readiness":["display root", "undefined root with readable rows", "plain-object root", "display root with empty rows", "plain-object root with empty rows", "undefined root with empty rows", "display root with invalid row objects", "delayed row objects", "missing movie", "missing list", "undefined root with invalid row objects"],
        "harness_sha256":hashlib.sha256(program.encode()).hexdigest(),
        "cases":[json.loads(line) for line in output.splitlines() if "\"budget\"" not in line and "\"schedule\"" not in line],
        "budgets":[json.loads(line) for line in output.splitlines() if "\"budget\"" in line],
        "scheduling_names":["UI messages withheld five seconds","UI inspection tasks withheld five seconds","game poll withheld five seconds","game completion tasks withheld five seconds","three rejected Hide messages","native Hide refused until user close at five seconds","menu disappears before capture","message box appears during close"],
        "scheduling":[json.loads(line) for line in output.splitlines() if "\"schedule\"" in line]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: 55 idle/transfer cases, 3 lifecycle-budget cases and {len(report['scheduling'])} scheduling cases; simulated results in {args.output}")


if __name__ == "__main__":
    main()
