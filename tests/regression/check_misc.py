"""Exercise the production override loader with malformed and unavailable records."""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
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

struct Settings {static Settings* GetSingleton(){static Settings settings;return &settings;}void ProcessOverrideFile(const wchar_t*,std::unordered_map<RE::FormID,CategoryMask>&);};
'''
category_source=(ROOT/'src/ItemClass.cpp').read_text()
program+=category_source[category_source.index('CategoryMask ToMask('):category_source.index('namespace {')]
settings=(ROOT/'src/Settings.cpp').read_text()
start=settings.index('\tstd::optional<std::pair<std::string_view, RE::FormID>> ParseFormIdentifier(')
program+=settings[start:settings.index('\n\t}',start)+3]
start=settings.index('void Settings::ProcessOverrideFile(')
program+=settings[start:settings.index('\n}',start)+2]
program += r'''int main(){auto* settings=Settings::GetSingleton();
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
with tempfile.TemporaryDirectory(prefix='arcanevault-overrides-') as directory:
    path=Path(directory);(path/'check.cpp').write_text(program)
    subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT),str(path/'check.cpp'),'-o',str(path/'check')],check=True)
    subprocess.run([str(path/'check')],check=True)
print('PASS: malformed, unresolved and non-item overrides do not prevent later valid entries')

fields = "\n".join(line for line in (ROOT / "src/Settings.h").read_text().splitlines()
                   if line.strip().startswith(("bool GSC_", "int GSC_")))
ui = (ROOT / "src/AVUI.cpp").read_text()
a=ui.index("\tvoid __stdcall RenderQuantities()")
method=ui[a:ui.index("\n\t}",a)+3].replace("__stdcall ", "")
program = r'''
#include <algorithm>
#include <cassert>
#include <map>
#include <string>
struct Settings {
''' + fields + r'''
    int saves=0;
    static Settings* GetSingleton(){static Settings settings;return &settings;}
    void SaveINI(){++saves;}
};
std::map<std::string,int> edits;
const char* Translate(const char* key){return key;}
bool InputInt(const char* key,int* value){if(!edits.contains(key))return false;*value=edits.at(key);return true;}
''' + method + r'''
int main(){
    auto* settings=Settings::GetSingleton();RenderQuantities();assert(settings->saves==0);
    edits={{"Options.AmmunitionKeepAmount",-1},{"Options.GoldKeepAmount",42},{"Options.SoulgemKeepAmount",0},{"Options.AlchemyKeepAmount",-10},{"Options.ScrollKeepAmount",1000}};
    RenderQuantities();assert(settings->saves==1 && settings->GSC_AmmunitionKeepAmount==0 && settings->GSC_GoldKeepAmount==42 && settings->GSC_SoulgemKeepAmount==0 && settings->GSC_AlchemyKeepAmount==0 && settings->GSC_ScrollKeepAmount==1000);
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-quantities-check-") as temporary:
    path=Path(temporary);(path / "check.cpp").write_text(program)
    subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",str(path / "check.cpp"),"-o",str(path / "check")],check=True)
    subprocess.run([str(path / "check")],check=True)
print("PASS: actual Quantities UI clamps and persists reserve edits")
