"""Exercise actual settings pages, Quick Transfer UI, and override loading."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
settings_fields = "\n".join(line for line in (ROOT / "src/Settings.h").read_text().splitlines()
                            if line.strip().startswith(("bool GSC_", "int GSC_")))
program = r'''
#include <algorithm>
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
struct Utility {
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    void ConfigurationSpells() {}
};
const char* Translate(const char* key) { return key; }
constexpr int ImGuiTreeNodeFlags_DefaultOpen = 1;
std::set<std::string> ids;
std::vector<std::string> scope;
bool duplicate = false;
bool toggleNotes = false;
bool toggleLearning = false;
bool toggleStolenTags = false;
bool toggleSelectedAmmo = false;
bool waitKey = false;
using ImGuiKey = int;
constexpr int ImGuiKey_NamedKey_BEGIN = 0, ImGuiKey_NamedKey_END = 1;
namespace HelperFunctions {
    int IDCodeToImGuiKey(int key) { return key; }
    int ImGuiKeyToIDCode(int key) { return key; }
}
const char* GetKeyName(ImGuiKey) { return "Key"; }
bool Button(const char*) { return false; }
bool IsKeyPressed(int) { return false; }
void Text(const char*) {}
void RenderOptions(); void RenderQuantities(); void RenderTransfer();
void RenderOverrides() {}
void RenderIgnoredItems() {}
namespace SKSEMenuFramework {
    bool installed = true;
    std::vector<std::pair<std::string,void(*)()>> sections;
    bool IsInstalled() { return installed; }
    void SetSection(const char*) {}
    void AddSectionItem(const char* label, void(*render)()) { sections.emplace_back(label,render); }
}
std::map<std::string,int> inputs;
std::vector<std::string> shownInputs;
std::string ID(const char* label) {
    std::string result;
    for (const auto& part : scope) result += part + "/";
    return result + label;
}
bool CollapsingHeader(const char* label, int) { assert(ids.insert(ID(label)).second); return true; }
bool Checkbox(const char* label, bool* value) {
    if (!ids.insert(ID(label)).second) { duplicate = true; return false; }
    if (toggleSelectedAmmo && value == &Settings::GetSingleton()->GSC_KeepSelectedAmmunition) { *value = !*value; return true; }
    if (toggleStolenTags && value == &Settings::GetSingleton()->GSC_AllowRemovingStolenTags) { *value = !*value; return true; }
    if (toggleLearning && value == &Settings::GetSingleton()->GSC_LearnDepositOverrides) { *value = !*value; return true; }
    if (toggleNotes && value == &Settings::GetSingleton()->GSC_OffloadNotes) { *value = !*value; return true; }
    if (value == &Settings::GetSingleton()->GSC_OffloadBooks) { *value = !*value; return true; }
    return false;
}
void SameLine() {}
void PushID(const char* id) { scope.emplace_back(id); }
void PopID() { assert(!scope.empty()); scope.pop_back(); }
bool InputInt(const char* label, int* value) {
    assert(ids.insert(ID(label)).second); shownInputs.emplace_back(label);
    auto found=inputs.find(label); if (found==inputs.end()) return false;
    *value=found->second; return true;
}
'''
ui = (ROOT / "src/AVUI.cpp").read_text()
for signature in ["\tvoid Register()", "\tvoid __stdcall RenderOptions()",
                  "\tvoid __stdcall RenderQuantities()", "\tvoid __stdcall RenderTransfer()"]:
    start = ui.index(signature)
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
    SKSEMenuFramework::installed=false;Register();assert(SKSEMenuFramework::sections.empty());
    SKSEMenuFramework::installed=true;Register();
    assert(SKSEMenuFramework::sections.size()==5);
    assert(SKSEMenuFramework::sections[1].first=="Quantities" && SKSEMenuFramework::sections[1].second==RenderQuantities);
    ids.clear();RenderOptions();
    assert((shownInputs==std::vector<std::string>{"Options.SalePercentage"}));
    ids.clear();shownInputs.clear();RenderQuantities();
    assert((shownInputs==std::vector<std::string>{"Options.AmmunitionKeepAmount","Options.GoldKeepAmount","Options.SoulgemKeepAmount","Options.AlchemyKeepAmount","Options.ScrollKeepAmount"}));
    assert(settings->GSC_AmmunitionKeepAmount==100 && settings->GSC_GoldKeepAmount==5000 && settings->GSC_SoulgemKeepAmount==25);
    assert(settings->saves==2);
    assert(settings->GSC_AlchemyKeepAmount==1);
    assert(settings->GSC_ScrollKeepAmount==3);
    inputs={{"Options.AmmunitionKeepAmount",150},{"Options.GoldKeepAmount",4200},{"Options.SoulgemKeepAmount",7},{"Options.AlchemyKeepAmount",6},{"Options.ScrollKeepAmount",5}};
    ids.clear();RenderQuantities();
    assert(settings->GSC_AmmunitionKeepAmount==150 && settings->GSC_GoldKeepAmount==4200 && settings->GSC_SoulgemKeepAmount==7);
    assert(settings->saves==3 && settings->GSC_SalePercentage==30);
    assert(settings->GSC_AlchemyKeepAmount==6);
    assert(settings->GSC_ScrollKeepAmount==5);
    inputs={{"Options.AmmunitionKeepAmount",-1},{"Options.GoldKeepAmount",-100},{"Options.SoulgemKeepAmount",-25},{"Options.AlchemyKeepAmount",-1},{"Options.ScrollKeepAmount",-3}};
    ids.clear();RenderQuantities();
    assert(settings->GSC_AmmunitionKeepAmount==0 && settings->GSC_GoldKeepAmount==0 && settings->GSC_SoulgemKeepAmount==0);
    assert(settings->saves==4);
    assert(settings->GSC_AlchemyKeepAmount==0);
    assert(settings->GSC_ScrollKeepAmount==0);
    inputs={{"Options.SalePercentage",0}};ids.clear();RenderOptions();
    assert(settings->GSC_SalePercentage==1 && settings->saves==5);
    inputs["Options.SalePercentage"]=101;ids.clear();RenderOptions();
    assert(settings->GSC_SalePercentage==100 && settings->saves==6);
    assert(settings->GSC_AmmunitionKeepAmount==0 && settings->GSC_GoldKeepAmount==0 && settings->GSC_SoulgemKeepAmount==0);
    inputs.clear();ids.clear();RenderQuantities();assert(settings->saves==6 && !duplicate && scope.empty());
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
    const int beforeNotes=settings->saves;
    assert(!settings->GSC_OffloadNotes);toggleNotes=true;ids.clear();RenderTransfer();
    assert(settings->GSC_OffloadNotes && settings->saves==beforeNotes+1);

    const int beforeSelectedAmmo=settings->saves;
    assert(!settings->GSC_KeepSelectedAmmunition);toggleSelectedAmmo=true;ids.clear();RenderOptions();
    assert(settings->GSC_KeepSelectedAmmunition && settings->saves==beforeSelectedAmmo+1);
    ids.clear();RenderOptions();assert(!settings->GSC_KeepSelectedAmmunition && settings->saves==beforeSelectedAmmo+2);

    assert(!settings->GSC_LearnDepositOverrides);inputs.clear();ids.clear();toggleLearning=true;
    const auto beforeLearning=settings->saves;RenderOptions();assert(settings->GSC_LearnDepositOverrides && settings->saves==beforeLearning+1);
    ids.clear();RenderOptions();assert(!settings->GSC_LearnDepositOverrides && settings->saves==beforeLearning+2);

    toggleLearning=false;toggleStolenTags=true;ids.clear();assert(!settings->GSC_AllowRemovingStolenTags);
    const auto beforeStolenTags=settings->saves;RenderOptions();assert(settings->GSC_AllowRemovingStolenTags && settings->saves==beforeStolenTags+1);
    ids.clear();RenderOptions();assert(!settings->GSC_AllowRemovingStolenTags && settings->saves==beforeStolenTags+2);

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
print("PASS: Quantities registration/controls/validation, unchanged defaults, Options sale percentage, Books UI IDs/persistence, optional plugins, and malformed override recovery")
