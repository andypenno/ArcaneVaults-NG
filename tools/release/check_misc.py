"""Exercise the actual Books Quick Transfer controls."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
settings_fields = "\n".join(line for line in (ROOT / "src/Settings.h").read_text().splitlines()
                            if line.strip().startswith(("bool GSC_", "int GSC_")))
program = r'''
#include <array>
#include <cassert>
#include <charconv>
#include <functional>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
'''
program += "struct Settings {\n" + settings_fields + r'''
    int saves = 0;
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    void SaveINI() { ++saves; }
};
struct Utility { static Utility* GetSingleton() { static Utility utility; return &utility; } };
const char* Translate(const char* key) { return key; }
constexpr int ImGuiTreeNodeFlags_DefaultOpen = 1;
std::set<std::string> ids;
std::vector<std::string> scope;
bool duplicate = false;
std::string ID(const char* label) {
    std::string result;
    for (const auto& part : scope) result += part + "/";
    return result + label;
}
bool CollapsingHeader(const char* label, int) { assert(ids.insert(ID(label)).second); return true; }
bool Checkbox(const char* label, bool* value) {
    if (!ids.insert(ID(label)).second) { duplicate = true; return false; }
    if (value == &Settings::GetSingleton()->GSC_OffloadBooks) { *value = !*value; return true; }
    return false;
}
void SameLine() {}
void PushID(const char* id) { scope.emplace_back(id); }
void PopID() { assert(!scope.empty()); scope.pop_back(); }
'''
ui = (ROOT / "src/AVUI.cpp").read_text()
start = ui.index("\tvoid __stdcall RenderTransfer()")
program += ui[start:ui.index("\n\t}", start) + 3].replace("__stdcall ", "")
program += r'''
int main() {
    auto* settings = Settings::GetSingleton();
    RenderTransfer();
    assert(!duplicate && scope.empty() && settings->GSC_OffloadBooks && settings->saves == 1);
    ids.clear(); RenderTransfer();
    assert(!duplicate && !settings->GSC_OffloadBooks && settings->saves == 2);
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-misc-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: Books UI IDs and toggling/persistence")
