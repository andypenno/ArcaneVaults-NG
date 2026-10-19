"""Exercise actual redirect management, INI persistence, and SKSE callbacks."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
program = r'''
#include <cassert>
#include <charconv>
#include <cstdint>
#include <cstring>
#include <functional>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>
namespace std {
string format(string_view, string_view plugin, unsigned id) {
    ostringstream text; text << plugin << "|0x" << hex << uppercase << id; return text.str();
}
}
namespace logger {
template<class... Args> void info(const char*, Args...) {}
template<class... Args> void warn(const char*, Args...) {}
template<class... Args> void error(const char*, Args...) {}
}
namespace RE {
using FormID = std::uint32_t;
struct TESFile { std::string name; std::string_view GetFilename() const { return name; } };
struct TESForm {
    inline static std::map<FormID, TESForm*> loaded;
    FormID id; TESFile* file = nullptr; FormID local = 0;
    explicit TESForm(FormID value) : id(value) { loaded[id] = this; }
    virtual ~TESForm() = default;
    template<class T> T* As() { return dynamic_cast<T*>(this); }
    template<class T> const T* As() const { return dynamic_cast<const T*>(this); }
    FormID GetFormID() const { return id; }
    FormID GetLocalFormID() const { return local; }
    bool IsDynamicForm() const { return id >= 0xFF000000; }
    TESFile* GetFile(int) const { return file; }
    static TESForm* LookupByID(FormID id) { auto it = loaded.find(id); return it == loaded.end() ? nullptr : it->second; }
    template<class T> static T* LookupByID(FormID id) { auto* form = LookupByID(id); return form ? form->As<T>() : nullptr; }
};
struct TESBoundObject : TESForm { using TESForm::TESForm; };
struct TESObjectACTI : TESBoundObject { using TESBoundObject::TESBoundObject; };
struct TESObjectCONT : TESBoundObject { using TESBoundObject::TESBoundObject; };
struct TESObjectREFR : TESForm {
    using TESForm::TESForm;
    TESBoundObject* base = nullptr; TESObjectREFR* linked = nullptr; bool blocked = false;
    TESBoundObject* GetBaseObject() { return base; }
    const TESBoundObject* GetBaseObject() const { return base; }
    TESObjectREFR* GetLinkedRef(void*) { return linked; }
    void SetActivationBlocked(bool value) { blocked = value; }
};
struct TESDataHandler {
    std::map<std::pair<std::string, FormID>, FormID> ids;
    static TESDataHandler* GetSingleton() { static TESDataHandler data; return &data; }
    FormID LookupFormID(FormID local, std::string_view plugin) {
        auto it = ids.find({std::string(plugin),local}); return it == ids.end() ? 0 : it->second;
    }
    TESForm* LookupForm(FormID local, std::string_view plugin) { return TESForm::LookupByID(LookupFormID(local,plugin)); }
};
struct PlayerCharacter {
    struct { struct { bool shouldUpdateCrosshair = false; } playerFlags; } data;
    static PlayerCharacter* GetSingleton() { static PlayerCharacter player; return &player; }
    auto& GetPlayerRuntimeData() { return data; }
    void UpdateCrosshairs() {}
};
}
struct CSimpleIniA {
    inline static std::map<std::pair<std::string,std::string>,std::string> disk;
    struct Key { const char* pItem; };
    using TKeyVal = std::vector<std::pair<Key,const char*>>;
    TKeyVal entries;
    void SetUnicode() {}
    int LoadFile(const wchar_t*) { return 0; }
    int SaveFile(const wchar_t*) { return 0; }
    void Delete(const char* section, const char*) {
        for (auto it = disk.begin(); it != disk.end();) {
            if (it->first.first == section) it = disk.erase(it); else ++it;
        }
    }
    void SetValue(const char* section, const char* key, const char* value) { disk[{section,key}] = value; }
    const TKeyVal* GetSection(const char* section) {
        entries.clear();
        for (const auto& [key,value] : disk) if (key.first == section) entries.push_back({{key.second.c_str()},value.c_str()});
        return entries.empty() ? nullptr : &entries;
    }
};
namespace SKSE {
struct Tasks { void AddTask(std::function<void()> action) { action(); } };
Tasks* GetTaskInterface() { static Tasks tasks; return &tasks; }
struct SerializationInterface {
    struct Record { std::uint32_t type, version, length; std::vector<char> data; };
    std::vector<Record> records;
    std::map<RE::FormID,RE::FormID> resolved;
    std::size_t next = 0, offset = 0; Record* active = nullptr;
    bool OpenRecord(std::uint32_t type, std::uint32_t version) {
        records.push_back({type,version,0,{}}); active = &records.back(); return true;
    }
    bool WriteRecordData(const void* data, std::uint32_t size) {
        auto* bytes = static_cast<const char*>(data); active->data.insert(active->data.end(),bytes,bytes+size);
        active->length += size; return true;
    }
    bool GetNextRecordInfo(std::uint32_t& type, std::uint32_t& version, std::uint32_t& length) {
        if (next == records.size()) return false;
        active = &records[next++]; offset = 0; type=active->type; version=active->version; length=active->length; return true;
    }
    template<class T> std::uint32_t ReadRecordData(T& value) {
        if (offset + sizeof(T) > active->data.size()) return 0;
        std::memcpy(&value,active->data.data()+offset,sizeof(T)); offset += sizeof(T); return sizeof(T);
    }
    bool ResolveFormID(RE::FormID saved, RE::FormID& current) {
        auto it = resolved.find(saved); if (it == resolved.end()) return false; current = it->second; return true;
    }
    void Rewind() { next=offset=0; active=nullptr; }
};
}
struct Settings {
    bool GSC_GlobalRedirects = true;
    static constexpr const wchar_t* redirect_path = L"redirects.ini";
    static Settings* GetSingleton() { static Settings settings; return &settings; }
    static std::optional<std::string> MakeFormIdentifier(const RE::TESForm*);
    void SaveRedirects() const;
    void LoadRedirects();
};
#include "src/RedirectManager.h"
#include "src/Serialization.h"
'''
settings = (ROOT / "src/Settings.cpp").read_text()
program += 'constexpr std::string_view redirectSection = "Redirects";\n'
start = settings.index("\tstd::optional<std::pair<std::string_view, RE::FormID>> ParseFormIdentifier(")
program += settings[start:settings.index("\n\t}", start) + 3]
for signature in ["std::optional<std::string> Settings::MakeFormIdentifier(",
                  "void Settings::SaveRedirects(", "void Settings::LoadRedirects("]:
    start = settings.index(signature)
    program += settings[start:settings.index("\n}", start) + 2]
for filename in ["RedirectManager.cpp", "Serialization.cpp"]:
    program += "\n" + "\n".join(line for line in (ROOT / "src" / filename).read_text().splitlines()
                                if not line.startswith("#include"))
program += r'''
int main() {
    auto* manager = RedirectManager::GetSingleton(); auto* settings = Settings::GetSingleton();
    auto* data = RE::TESDataHandler::GetSingleton();
    RE::TESFile house{"HearthFires.esm"}, mod{"ArcaneVaults-LinkedStorage.esp"};
    RE::TESObjectREFR chest{0x03000100}, vault{0x05000200}, placed{0xFF000001}, linked{0xFF000002};
    RE::TESObjectACTI activator{0x03000300}; RE::TESObjectCONT container{0x03000400};
    chest.file=&house; chest.local=0x100; chest.base=&activator; chest.linked=&linked; linked.base=&container;
    vault.file=&mod; vault.local=0x200;
    data->ids[{{"HearthFires.esm"},0x100}] = chest.id; data->ids[{{"ArcaneVaults-LinkedStorage.esp"},0x200}] = vault.id;
    assert(!Settings::MakeFormIdentifier(&placed));
    assert(!manager->Add(nullptr,&vault) && !manager->Add(&chest,nullptr) && !manager->Add(&vault,&vault));
    assert(manager->Add(&chest,&vault) && linked.blocked && manager->Add(&placed,&vault));
    // Unloaded plugin references must retain their stable INI identifiers.
    RE::TESForm::loaded.erase(chest.id);
    CSimpleIniA::disk[{{"Other"},{"Preserve"}}] = "yes";
    SKSE::SerializationInterface save;
    Serialization::SaveCallback(&save);
    assert(save.records.size()==1 && save.records[0].version==1 && save.records[0].length==20);
    assert(CSimpleIniA::disk.size()==2);
    assert(CSimpleIniA::disk.at({"Redirects","HearthFires.esm|0x100"})=="ArcaneVaults-LinkedStorage.esp|0x200");
    manager->Clear(); settings->LoadRedirects();
    assert(manager->GetRedirects().size()==1 && manager->GetRedirects().contains(chest.id));
    settings->SaveRedirects(); assert(CSimpleIniA::disk.size()==2);
    // Changed load order and dynamic IDs resolve independently of live source lookup.
    RE::TESObjectREFR movedVault{0x08000200}; movedVault.file=&mod; movedVault.local=0x200;
    data->ids[{"HearthFires.esm",0x100}]=0x06000100;
    data->ids[{"ArcaneVaults-LinkedStorage.esp",0x200}]=movedVault.id;
    save.resolved={{chest.id,0x06000100},{vault.id,movedVault.id},{placed.id,0xFF000010}};
    Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().size()==2 && manager->GetRedirects().contains(0xFF000010));
    RE::TESObjectREFR movedChest{0x06000100}, movedPlaced{0xFF000010};
    movedChest.base=&activator; movedChest.linked=&linked; linked.blocked=false;
    assert(manager->FindDestination(&movedChest)==&movedVault && linked.blocked);
    assert(manager->FindDestination(&movedPlaced)==&movedVault);
    Serialization::RevertCallback(nullptr);
    assert(manager->GetRedirects().size()==1 && manager->GetRedirects().contains(movedChest.id));
    save.Rewind(); Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().size()==2);
    // Global INI changes take precedence over static rows in older saves.
    CSimpleIniA::disk.erase({"Redirects","HearthFires.esm|0x100"}); save.Rewind();
    Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().size()==1 && !manager->GetRedirects().contains(movedChest.id));
    Serialization::RevertCallback(nullptr); assert(manager->GetRedirects().empty());
    SKSE::SerializationInterface otherSave; Serialization::LoadCallback(&otherSave);
    assert(manager->GetRedirects().empty());
    // Per-save mode restores unloaded static and dynamic sources without the INI.
    settings->GSC_GlobalRedirects=false; save.Rewind(); RE::TESForm::loaded.erase(movedChest.id);
    RE::TESForm::loaded.erase(movedPlaced.id); Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().size()==2);
    SKSE::SerializationInterface repeated; Serialization::SaveCallback(&repeated);
    repeated.resolved={{movedChest.id,movedChest.id},{movedVault.id,movedVault.id},{movedPlaced.id,movedPlaced.id}};
    Serialization::LoadCallback(&repeated); assert(manager->GetRedirects().size()==2);
    assert(CSimpleIniA::disk.size()==1);
    // A known non-reference, invalid destination, or unresolved ID cannot become a binding.
    RE::TESForm wrong{movedChest.id}; save.Rewind(); Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().size()==1 && !manager->GetRedirects().contains(wrong.id));
    save.resolved.erase(vault.id); save.Rewind(); Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().empty());
    save.resolved[vault.id]=wrong.id; save.Rewind(); Serialization::LoadCallback(&save);
    assert(manager->GetRedirects().empty());
    assert(!manager->Restore(0,&vault) && !manager->Restore(wrong.id,&vault) && !manager->Restore(chest.id,nullptr));
    assert(manager->Add(&chest,&vault)); assert(manager->Remove(&chest) && !linked.blocked);
    assert(!manager->Remove(&chest));
    // Legacy empty saves, unknown versions, exaggerated counts, and short reads remain safe.
    SKSE::SerializationInterface bad;
    bad.OpenRecord(123,1); bad.OpenRecord(Serialization::SerializationType,2);
    bad.OpenRecord(Serialization::SerializationType,1);
    std::uint32_t count=100; bad.WriteRecordData(&count,sizeof(count));
    bad.WriteRecordData(&chest.id,sizeof(chest.id)); bad.WriteRecordData(&vault.id,sizeof(vault.id));
    bad.resolved={{chest.id,chest.id},{vault.id,vault.id}};
    Serialization::LoadCallback(&bad); assert(manager->GetRedirects().size()==1);
    bad.records.back().data.resize(8); bad.Rewind(); Serialization::LoadCallback(&bad);
    assert(manager->GetRedirects().empty());
    bad.records.back().data.resize(2); bad.Rewind(); Serialization::LoadCallback(&bad);
    assert(manager->GetRedirects().empty());
    settings->GSC_GlobalRedirects=true; CSimpleIniA::disk[{"Redirects","missing.esm|0x100"}]="ArcaneVaults-LinkedStorage.esp|0x200";
    CSimpleIniA::disk[{"Redirects","bad"}]="bad";
    CSimpleIniA::disk[{"Redirects","HearthFires.esm|0x100junk"}]="ArcaneVaults-LinkedStorage.esp|0x200";
    data->ids[{"HearthFires.esm",0x100}]=wrong.id;
    settings->LoadRedirects(); assert(manager->GetRedirects().empty());
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-redirect-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-multichar", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: dynamic/global/per-save bindings, unloaded references, load-order remapping, INI precedence, save isolation, activator blocking, and malformed records")
