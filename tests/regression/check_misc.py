"""Exercise actual settings pages, Quick Transfer UI, and override loading."""

from pathlib import Path
import json
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
#include <ranges>
#include <set>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>
#include "src/TransferFeedback.h"
namespace TransferFeedback {void Register(){}}
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
namespace logger { template<class... Args> void info(const char*, Args...) {} template<class... Args> void warn(const char*, Args...) {} }
'''
program += "struct Settings {\n" + settings_fields + r'''
    int saves = 0;
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    void SaveINI() { ++saves; }
    void ProcessOverrideFile(const wchar_t*, std::unordered_map<RE::FormID, CategoryMask>&);
    std::unordered_map<RE::FormID,CategoryMask> overrides_,userOverrides_;
    void SetUserOverride(RE::TESBoundObject*,CategoryMask);
    bool RemoveUserOverride(RE::FormID);
    std::optional<CategoryMask> FindOverride(const RE::TESBoundObject*) const;
    std::optional<CategoryMask> FindOverride(RE::FormID) const;
};
struct Utility {
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    int spellUpdates = 0;
    void ConfigurationSpells() { ++spellUpdates; }
};
const char* Translate(const char* key) { return key; }
constexpr int ImGuiTreeNodeFlags_DefaultOpen = 1;
std::set<std::string> ids;
std::vector<std::string> scope;
bool duplicate = false;
std::vector<std::string> shownControls;
bool toggleSpells = false;
bool toggleNotes = false;
bool toggleGear = false;
bool toggleLearning = false;
bool toggleAutomaticLearning = false;
bool toggleStolenTags = false;
bool toggleSelectedAmmo = false;
bool toggleAllMaterials = false;
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
void Text(const char* label) { shownControls.emplace_back(label); }
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
    shownControls.emplace_back(label);
    if (toggleAllMaterials && value == &Settings::GetSingleton()->GSC_AllCraftingMaterials) { *value = !*value; return true; }
    if (toggleSpells && (value == &Settings::GetSingleton()->GSC_AssignSpell || value == &Settings::GetSingleton()->GSC_SortSpell)) { *value = !*value; return true; }
    if (!ids.insert(ID(label)).second) { duplicate = true; return false; }
    if (toggleSelectedAmmo && value == &Settings::GetSingleton()->GSC_KeepSelectedAmmunition) { *value = !*value; return true; }
    if (toggleStolenTags && value == &Settings::GetSingleton()->GSC_AllowRemovingStolenTags) { *value = !*value; return true; }
    if (toggleLearning && value == &Settings::GetSingleton()->GSC_LearnDepositOverrides) { *value = !*value; return true; }
    if (toggleAutomaticLearning && value == &Settings::GetSingleton()->GSC_AllowAutomaticLearning) { *value = !*value; return true; }
    if (toggleGear && value == &Settings::GetSingleton()->GSC_OffloadGear) { *value = !*value; return true; }
    if (toggleNotes && value == &Settings::GetSingleton()->GSC_OffloadNotes) { *value = !*value; return true; }
    if (value == &Settings::GetSingleton()->GSC_OffloadBooks) { *value = !*value; return true; }
    return false;
}
void SameLine() {}
void PushID(const char* id) { scope.emplace_back(id); }
void PopID() { assert(!scope.empty()); scope.pop_back(); }
bool InputInt(const char* label, int* value) {
    shownControls.emplace_back(label);
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
category_source=(ROOT/'src/ItemClass.cpp').read_text()
program+=category_source[category_source.index('CategoryMask ToMask('):category_source.index('namespace {')]
for signature in ('void Settings::SetUserOverride(', 'bool Settings::RemoveUserOverride(',
                  'std::optional<CategoryMask> Settings::FindOverride(const RE::TESBoundObject*',
                  'std::optional<CategoryMask> Settings::FindOverride(RE::FormID'):
    start=settings.index(signature)
    program+=settings[start:settings.index('\n}',start)+2]
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
    assert((shownInputs==std::vector<std::string>{"Options.AmmunitionKeepAmount","Options.GoldKeepAmount","Options.LockpickKeepAmount","Options.SoulgemKeepAmount","Options.AlchemyKeepAmount","Options.ScrollKeepAmount"}));
    assert(settings->GSC_AmmunitionKeepAmount==100 && settings->GSC_GoldKeepAmount==5000 && settings->GSC_SoulgemKeepAmount==25);
    assert(settings->saves==2);
    assert(settings->GSC_AlchemyKeepAmount==1 && settings->GSC_LockpickKeepAmount==25);
    assert(settings->GSC_ScrollKeepAmount==3);
    inputs={{"Options.AmmunitionKeepAmount",150},{"Options.GoldKeepAmount",4200},{"Options.SoulgemKeepAmount",7},{"Options.LockpickKeepAmount",12},{"Options.AlchemyKeepAmount",6},{"Options.ScrollKeepAmount",5}};
    ids.clear();RenderQuantities();
    assert(settings->GSC_AmmunitionKeepAmount==150 && settings->GSC_GoldKeepAmount==4200 && settings->GSC_SoulgemKeepAmount==7);
    assert(settings->saves==3 && settings->GSC_SalePercentage==30);
    assert(settings->GSC_AlchemyKeepAmount==6 && settings->GSC_LockpickKeepAmount==12);
    assert(settings->GSC_ScrollKeepAmount==5);
    inputs={{"Options.AmmunitionKeepAmount",-1},{"Options.GoldKeepAmount",-100},{"Options.SoulgemKeepAmount",-25},{"Options.LockpickKeepAmount",-1},{"Options.AlchemyKeepAmount",-1},{"Options.ScrollKeepAmount",-3}};
    ids.clear();RenderQuantities();
    assert(settings->GSC_AmmunitionKeepAmount==0 && settings->GSC_GoldKeepAmount==0 && settings->GSC_SoulgemKeepAmount==0);
    assert(settings->saves==4);
    assert(settings->GSC_AlchemyKeepAmount==0 && settings->GSC_LockpickKeepAmount==0);
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
    toggleNotes=false;const int beforeGear=settings->saves;
    assert(!settings->GSC_OffloadGear);toggleGear=true;ids.clear();RenderTransfer();
    assert(settings->GSC_OffloadGear && settings->saves==beforeGear+1);
    ids.clear();RenderTransfer();assert(!settings->GSC_OffloadGear && settings->saves==beforeGear+2);toggleGear=false;



    const int beforeSelectedAmmo=settings->saves;
    assert(!settings->GSC_KeepSelectedAmmunition);toggleSelectedAmmo=true;ids.clear();RenderOptions();
    assert(settings->GSC_KeepSelectedAmmunition && settings->saves==beforeSelectedAmmo+1);
    ids.clear();RenderOptions();assert(!settings->GSC_KeepSelectedAmmunition && settings->saves==beforeSelectedAmmo+2);

    assert(!settings->GSC_LearnDepositOverrides);inputs.clear();ids.clear();toggleLearning=true;
    const auto beforeLearning=settings->saves;RenderOptions();assert(settings->GSC_LearnDepositOverrides && settings->saves==beforeLearning+1);
    ids.clear();RenderOptions();assert(!settings->GSC_LearnDepositOverrides && settings->saves==beforeLearning+2);

    toggleLearning=false;toggleSelectedAmmo=false;toggleAutomaticLearning=true;
    ids.clear();shownControls.clear();const auto beforeAutomatic=settings->saves;
    assert(!settings->GSC_AllowAutomaticLearning);RenderOptions();
    assert(!settings->GSC_AllowAutomaticLearning && settings->saves==beforeAutomatic);
    assert(std::ranges::find(shownControls,"Options.AllowAutomaticLearning")==shownControls.end());
    settings->GSC_LearnDepositOverrides=true;ids.clear();shownControls.clear();RenderOptions();
    assert(settings->GSC_AllowAutomaticLearning && settings->saves==beforeAutomatic+1);
    assert(std::ranges::find(shownControls,"Options.AllowAutomaticLearning")!=shownControls.end());
    ids.clear();RenderOptions();assert(!settings->GSC_AllowAutomaticLearning && settings->saves==beforeAutomatic+2);
    settings->GSC_LearnDepositOverrides=false;toggleAutomaticLearning=false;

    toggleLearning=false;toggleStolenTags=true;ids.clear();assert(!settings->GSC_AllowRemovingStolenTags);
    const auto beforeStolenTags=settings->saves;RenderOptions();assert(settings->GSC_AllowRemovingStolenTags && settings->saves==beforeStolenTags+1);
    ids.clear();RenderOptions();assert(!settings->GSC_AllowRemovingStolenTags && settings->saves==beforeStolenTags+2);

    toggleStolenTags=false;toggleSelectedAmmo=false;toggleSpells=true;ids.clear();
    const auto beforeSpells=settings->saves;
    const bool assignSpell=settings->GSC_AssignSpell, sortSpell=settings->GSC_SortSpell;
    RenderOptions();
    assert(settings->GSC_AssignSpell==!assignSpell && settings->GSC_SortSpell==!sortSpell);
    assert(Utility::GetSingleton()->spellUpdates==2 && settings->saves==beforeSpells+1);
    ids.clear();scope.clear();toggleAllMaterials=true;
    const int savesBeforeAllMaterials=settings->saves;
    const bool allMaterialsBefore=settings->GSC_AllCraftingMaterials;
    RenderOptions();
    assert(settings->GSC_AllCraftingMaterials!=allMaterialsBefore && settings->saves==savesBeforeAllMaterials+1);
    toggleAllMaterials=false;

    ids.clear();scope.clear();shownControls.clear();RenderTransfer();
    assert(std::ranges::find(shownControls,"Options.LastTransfer")==shownControls.end());

}
'''
overrides = (ROOT / "ini/ArcaneVaultOverrides.ini").read_text()
assert "ccBGSSSE037-Curios.esl|0x000800 = Treasure" in overrides.splitlines()
fishing = json.loads((ROOT / 'tests/fixtures/fishing-maps.json').read_text())
keys = [line.split('=', 1)[0].strip() for line in overrides.splitlines() if line.startswith(fishing['plugin'] + '|') and line.split('=', 1)[1].strip() == 'Map']
assert len(keys) == len(fishing['maps']) == 8
fishing_check = r'''
    std::array<RE::TESBoundObject,8> fishingMaps{};
    const std::array<const char*,8> fishingKeys{FISHING_KEYS};
    const std::array<unsigned,8> fishingIDs{FISHING_IDS};
    data->forms.clear();CSimpleIniA::entries.clear();overrides.clear();
    for(unsigned i=0;i<fishingMaps.size();++i) {
        fishingMaps[i].id=0x09000000|fishingIDs[i];
        data->forms[{"ccBGSSSE001-Fish.esm",fishingIDs[i]}]={&fishingMaps[i]};
        CSimpleIniA::entries.push_back({{fishingKeys[i]},"Map"});
    }
    settings->ProcessOverrideFile(L"bundled.ini",overrides);assert(overrides.size()==8);
    for(auto& map:fishingMaps)assert(overrides.at(map.id)==ParseCategories("Map"));
    CSimpleIniA::entries={{{fishingKeys[0]},"Ingredient"}};
    settings->ProcessOverrideFile(L"user.ini",overrides);
    assert(overrides.at(fishingMaps[0].id)==ParseCategories("Ingredient"));
    data->forms.clear();overrides.clear();CSimpleIniA::entries.clear();
    for(const auto* key:fishingKeys)CSimpleIniA::entries.push_back({{key},"Map"});
    settings->ProcessOverrideFile(L"bundled.ini",overrides);assert(overrides.empty());
    data->forms[{"Skyrim.esm",0x123}]={&ingredient};CSimpleIniA::entries.push_back({{"Skyrim.esm|0x123"},"Ingredient"});
    settings->ProcessOverrideFile(L"bundled.ini",overrides);assert(overrides.size()==1 && overrides.contains(ingredient.id));
    RE::TESBoundObject logs{0x0800300E};data->forms[{"HearthFires.esm",0x300E}]={&logs};
    CSimpleIniA::entries={{{"HearthFires.esm|0x00300E"},"Ignore"}};
    settings->ProcessOverrideFile(L"bundled.ini",settings->overrides_);
    assert(settings->FindOverride(&logs)==ParseCategories("Ignore"));
    assert(FormatCategories(*settings->FindOverride(&logs))=="Ignore");
    settings->SetUserOverride(&logs,ParseCategories("Construction"));
    assert(settings->FindOverride(&logs)==ParseCategories("Construction"));
    assert(settings->RemoveUserOverride(logs.id));
    assert(settings->FindOverride(&logs)==ParseCategories("Ignore"));
    CSimpleIniA::entries={{{"HearthFires.esm|0x00300E"},"Ignore"}};
    settings->ProcessOverrideFile(L"user.ini",settings->userOverrides_);
    assert(settings->FindOverride(&logs)==ParseCategories("Ignore"));
'''
fishing_check = fishing_check.replace('FISHING_KEYS', ','.join(json.dumps(key) for key in keys))
fishing_check = fishing_check.replace('FISHING_IDS', ','.join(key.split('|')[1] for key in keys))
program = program.replace('    const int beforeNotes=settings->saves;', fishing_check + '\n    const int beforeNotes=settings->saves;')
with tempfile.TemporaryDirectory(prefix="arcanevault-misc-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: Quantities registration/controls/validation, unchanged defaults, Options sale percentage, Books UI IDs/persistence, optional plugins, and malformed override recovery")
