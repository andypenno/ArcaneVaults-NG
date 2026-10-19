"""Exercise stolen-stack gathering, returns, clearing, recovery, and menus."""
from pathlib import Path
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
from support.engine import common
program = common
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
