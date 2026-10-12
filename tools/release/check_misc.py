"""Exercise the actual Quick Transfer UI and optional-plugin override loader."""

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
namespace RE { struct TESBoundObject; }
#include "src/ItemClass.h"
namespace RE {
using FormID = unsigned;
struct TESBoundObject { unsigned id; unsigned GetFormID() const { return id; } };
struct TESForm {
    TESBoundObject* item;
    template<class T> T* As() { return item; }
};
struct TESDataHandler {
    std::map<std::pair<std::string, unsigned>, TESForm> forms;
    static TESDataHandler* GetSingleton() { static TESDataHandler data; return &data; }
    TESForm* LookupForm(unsigned id, std::string_view plugin) {
        auto it = forms.find({std::string(plugin), id});
        return it == forms.end() ? nullptr : &it->second;
    }
};
}
struct CSimpleIniA {
    struct Key { const char* pItem; };
    using TKeyVal = std::vector<std::pair<Key, const char*>>;
    inline static TKeyVal entries;
    void SetUnicode() {}
    void SetMultiKey(bool) {}
    void LoadFile(const wchar_t*) {}
    const TKeyVal* GetSection(const char*) { return &entries; }
};
namespace logger { template<class... Args> void info(const char*, Args...) {} }
CategoryMask ParseCategories(std::string_view text) {
    if (text == "Treasure") return CategoryMask{1} << static_cast<unsigned>(ItemCategory::Treasure);
    return CategoryMask{1} << static_cast<unsigned>(ItemCategory::Ingredient);
}
'''
program += "struct Settings {\n" + settings_fields + r'''
    int saves = 0;
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    void SaveINI() { ++saves; }
    void ProcessOverrideFile(const wchar_t*, std::unordered_map<RE::FormID, CategoryMask>&);
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
settings = (ROOT / "src/Settings.cpp").read_text()
parse_start = settings.index("\tstd::optional<std::pair<std::string_view, RE::FormID>> ParseFormIdentifier(")
program += settings[parse_start:settings.index("\n\t}", parse_start) + 3]
start = settings.index("void Settings::ProcessOverrideFile(")
program += settings[start:settings.index("\n}", start) + 2]
program += r'''
int main() {
    auto* settings = Settings::GetSingleton();
    RenderTransfer();
    assert(!duplicate && scope.empty() && settings->GSC_OffloadBooks && settings->saves == 1);
    ids.clear(); RenderTransfer();
    assert(!duplicate && !settings->GSC_OffloadBooks && settings->saves == 2);
    RE::TESBoundObject stone{0xFE001800}, ingredient{0x123};
    auto* data = RE::TESDataHandler::GetSingleton();
    data->forms[{"ccBGSSSE037-Curios.esl", 0x800}] = {&stone};
    data->forms[{"Skyrim.esm", 0x123}] = {&ingredient};
    data->forms[{"Skyrim.esm", 0x124}] = {nullptr};
    CSimpleIniA::entries = {
        {{"bad key"}, "Treasure"}, {{"|0x800"}, "Treasure"}, {{"Skyrim.esm|"}, "Treasure"},
        {{"Skyrim.esm|0x123junk"}, "Treasure"}, {{"Skyrim.esm|0x124"}, "Treasure"},
        {{"Missing.esp|0x800"}, "Treasure"}, {{"Skyrim.esm|GG"}, "Treasure"},
        {{"ccBGSSSE037-Curios.esl|0x000800"}, "Treasure"}, {{"Skyrim.esm|0x123"}, "Ingredient"}
    };
    std::unordered_map<unsigned, CategoryMask> overrides;
    settings->ProcessOverrideFile(L"test.ini", overrides);
    assert(overrides.size() == 2 && overrides.at(stone.id) == ParseCategories("Treasure"));
    assert(overrides.at(ingredient.id) == ParseCategories("Ingredient"));
    data->forms.erase({"ccBGSSSE037-Curios.esl", 0x800}); overrides.clear();
    settings->ProcessOverrideFile(L"test.ini", overrides);
    assert(overrides.size() == 1 && overrides.contains(ingredient.id));
}
'''
overrides = (ROOT / "ini/ArcaneVaultOverrides.ini").read_text()
assert "ccBGSSSE037-Curios.esl|0x000800 = Treasure" in overrides.splitlines()
with tempfile.TemporaryDirectory(prefix="arcanevault-misc-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: Books UI IDs, toggling/persistence, Welkynd override, optional plugins, and malformed override recovery")
