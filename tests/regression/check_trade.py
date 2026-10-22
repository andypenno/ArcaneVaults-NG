"""Compile the actual Trade sale and menu code against inventory stubs."""

from pathlib import Path
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
translations = json.loads((ROOT / "ini/ArcaneVaultTranslation.json").read_text())
for filename in ["src/Stores.cpp", "src/AVUI.cpp"]:
    for key in re.findall(r'Translate\("([^"\n]+)"\)', (ROOT / filename).read_text()):
        assert key in translations, f"Missing translation: {key}"
program = r'''
#include <algorithm>
#include <cassert>
#include <functional>
#include <map>
#include <memory>
#include <optional>
#include <sstream>
#include <string>
#include <vector>
namespace RE {
struct ExtraDataList {
    int count, value;
    int GetCount() const { return count; }
};
struct TESBoundObject {
    int value;
    bool gold = false;
    bool IsGold() const { return gold; }
};
TESBoundObject gold{1, true};
struct TESForm {
    template<class T> static T* LookupByID(unsigned id) { assert(id == 0xF); return &gold; }
};
struct InventoryEntryData {
    TESBoundObject* object;
    bool quest = false, favorite = false, worn = false;
    std::vector<ExtraDataList*> lists;
    std::vector<ExtraDataList*>* extraLists = &lists;
    InventoryEntryData(TESBoundObject* item, int) : object(item) {}
    bool IsQuestObject() const { return quest; }
    bool IsFavorited() const { return favorite; }
    bool IsWorn() const { return worn; }
    void AddExtraList(ExtraDataList* extra) { lists.push_back(extra); }
    int GetValue() const { return lists.empty() ? object->value : lists.front()->value; }
};
enum class ITEM_REMOVE_REASON { kRemove };
struct TESObjectREFR;
struct Handle {
    TESObjectREFR* object;
    struct Pointer {
        TESObjectREFR* object;
        explicit operator bool() const { return object != nullptr; }
        TESObjectREFR* get() const { return object; }
    };
    Pointer get() const;
};
struct TESObjectREFR {
    using Inventory = std::map<TESBoundObject*, std::pair<int, std::shared_ptr<InventoryEntryData>>>;
    Inventory inventory;
    ExtraDataList* failExtra = nullptr;
    int removeLimit = 2147483647;
    bool alive = true;
    Handle GetHandle() { return {this}; }
    Inventory GetInventory() const { return inventory; }
    std::map<TESBoundObject*, int> GetInventoryCounts() const {
        std::map<TESBoundObject*, int> counts;
        for (auto& [item, data] : inventory) counts[item] = data.first;
        return counts;
    }
    void RemoveItem(TESBoundObject* item, int count, ITEM_REMOVE_REASON reason,
        ExtraDataList* extra, TESObjectREFR* destination) {
        assert(reason == ITEM_REMOVE_REASON::kRemove && destination == nullptr);
        if (extra && extra == failExtra) return;
        auto& [total, entry] = inventory.at(item);
        count = std::min(count, removeLimit);
        assert(count > 0 && count <= total);
        if (extra) {
            assert(count <= extra->count);
            extra->count -= count;
            if (extra->count == 0) std::erase(entry->lists, extra);
        } else {
            assert(entry->lists.empty());
        }
        total -= count;
    }
    void AddObjectToContainer(TESBoundObject* item, ExtraDataList* extra, int count, TESObjectREFR* from) {
        assert(item == &gold && extra == nullptr && from == nullptr && count > 0);
        inventory[item].first += count;
    }
};
Handle::Pointer Handle::get() const { return {object->alive ? object : nullptr}; }
struct PlayerCharacter : TESObjectREFR {
    static PlayerCharacter* GetSingleton() { static PlayerCharacter player; return &player; }
};
std::string lastHUD;
struct SendHUDMessage { static void ShowHUDMessage(const char* text) { lastHUD = text; } };
}
'''
program += '#include "src/Trade.h"\n'
program += (ROOT / "src/Trade.cpp").read_text().replace('#include "Trade.h"', '')
program += r'''
namespace std {
    template<class... Args> string format(const char* text, Args... args) {
        string result{text};
        const auto replace = [&](const auto& arg) {
            ostringstream value; value << arg;
            const auto at = result.find("{}");
            if (at != string::npos) result.replace(at, 2, value.str());
        };
        (replace(args), ...);
        return result;
    }
}
enum class Container { Trade };
struct Utility {
    RE::TESObjectREFR trade;
    static Utility* GetSingleton() { static Utility utility; return &utility; }
    RE::TESObjectREFR* GetContainer(Container) { return &trade; }
};
struct Settings {
    int GSC_SalePercentage = 30;
    static Settings* GetSingleton() { static Settings setting; return &setting; }
};
const char* Translate(const char* key);
struct MenuOption { std::string text; std::function<void()> action; };
struct Stores {
    std::string message;
    std::vector<MenuOption> options;
    int cancel = -1, opened = 0, closed = 0, taken = 0;
    void TradeMenu(RE::TESObjectREFR*);
    void ShowTradeMenu(RE::TESObjectREFR*);
    void ShowDynamicMessageBox(std::string_view title, std::vector<MenuOption> buttons, int index) {
        message = title; options = std::move(buttons); cancel = index;
    }
    void OpenStoreObject(RE::TESObjectREFR* source, std::function<void(RE::TESObjectREFR*)> callback) { callback(source); }
    void OpenStorageMenu(Container, RE::TESObjectREFR* source, std::function<void(RE::TESObjectREFR*)> callback) {
        ++opened; callback(source);
    }
    void CloseStoreObject(RE::TESObjectREFR*) { ++closed; }
    void AllToPlayer(Container) { ++taken; }
};
'''
program += 'const char* Translate(const char* key) {\n'
for key in ["Vault.NoSale", "Vault.SaleExclusions", "Vault.SaleOverflow", "Vault.SaleChanged"]:
    program += f'if (std::string_view{{key}} == {json.dumps(key)}) return {json.dumps(translations[key])};\n'
program += 'return key; }\n'
assert "Favourited" in translations["Vault.NoSale"] and "limit" not in translations["Vault.NoSale"]
stores = (ROOT / "src/Stores.cpp").read_text()
for name in ["TradeMenu", "ShowTradeMenu"]:
    start = stores.index(f"void Stores::{name}(")
    program += stores[start:stores.index("\n}\n", start) + 3]
program += r'''
int main() {
    auto* player = RE::PlayerCharacter::GetSingleton();
    RE::TESObjectREFR bank;
    RE::TESBoundObject cheap{1}, sword{10}, protectedItem{100};
    auto put = [&](RE::TESBoundObject* item, int count) {
        auto entry = std::make_shared<RE::InventoryEntryData>(item, count);
        bank.inventory[item] = {count, entry}; return entry;
    };
    put(&cheap, 4);
    auto quote = Trade::GetQuote(&bank, 30);
    assert(quote.valid && quote.copies == 4 && quote.payout == 1);
    assert(Trade::Sell(&bank, quote) == 1 && player->inventory[&RE::gold].first == 1);
    assert(!Trade::Sell(&bank, quote) && player->inventory[&RE::gold].first == 1);
    assert(Trade::GetQuote(&bank, 30).copies == 0);

    bank.inventory.clear(); player->inventory.clear();
    auto entry = put(&sword, 7);
    RE::ExtraDataList enchanted{2, 100}, tempered{3, 20};
    entry->lists = {&enchanted, &tempered};
    quote = Trade::GetQuote(&bank, 30);
    assert(quote.copies == 7 && quote.payout == 84);
    assert(Trade::Sell(&bank, quote) == 84 && bank.inventory[&sword].first == 0);
    assert(enchanted.count == 0 && tempered.count == 0);

    bank.inventory.clear();
    for (int flag = 0; flag < 3; ++flag) {
        entry = put(&protectedItem, 3);
        entry->quest = flag == 0; entry->favorite = flag == 1; entry->worn = flag == 2;
        put(&RE::gold, 100);
        assert(Trade::GetQuote(&bank, 30).copies == 0);
    }
    bank.inventory.clear(); put(&cheap, 25000);
    assert(Trade::GetQuote(&bank, 30).payout == 7500);
    assert(Trade::GetQuote(&bank, 1).payout == 250);
    assert(Trade::GetQuote(&bank, 100).payout == 25000);
    assert(!Trade::GetQuote(&bank, 0).valid && !Trade::GetQuote(&bank, 101).valid);
    quote = Trade::GetQuote(&bank, 30);
    assert(Trade::Sell(&bank, quote) == 7500 && bank.inventory[&cheap].first == 0);
    put(&cheap, 25000);
    quote = Trade::GetQuote(&bank, 30); bank.inventory[&cheap].first++;
    assert(!Trade::Sell(&bank, quote));
    quote = Trade::GetQuote(&bank, 30); cheap.value = 2;
    assert(!Trade::Sell(&bank, quote)); cheap.value = 1;

    bank.inventory.clear(); entry = put(&sword, 5);
    enchanted = {2, 100}; entry->lists = {&enchanted, &enchanted};
    assert(Trade::GetQuote(&bank, 30).copies == 0);
    enchanted.count = 6; entry->lists = {&enchanted};
    assert(Trade::GetQuote(&bank, 30).copies == 0);
    enchanted.count = 0;
    assert(Trade::GetQuote(&bank, 30).copies == 0);
    enchanted.count = 2; bank.failExtra = &enchanted;
    quote = Trade::GetQuote(&bank, 30);
    assert(Trade::Sell(&bank, quote) == 0 && bank.inventory[&sword].first == 5);
    bank.failExtra = nullptr; bank.removeLimit = 1;
    assert(Trade::Sell(&bank, quote) == 30 && bank.inventory[&sword].first == 4);
    bank.removeLimit = 2147483647;

    bank.inventory.clear(); sword.value = 2147483647; put(&sword, 4);
    quote = Trade::GetQuote(&bank, 100);
    assert(quote.valid && quote.copies == 4 && quote.payout == 8589934588LL);
    assert(!Trade::CanReceive(quote) && !Trade::Sell(&bank, quote));
    assert(bank.inventory[&sword].first == 4);
    bank.inventory.clear(); put(&sword, 1); player->inventory.clear();
    quote = Trade::GetQuote(&bank, 100);
    assert(quote.valid && Trade::CanReceive(quote));
    assert(Trade::Sell(&bank, quote) == 2147483647 && bank.inventory[&sword].first == 0);
    player->inventory.clear();
    bank.inventory.clear(); sword.value = 10; put(&sword, 1);
    player->inventory[&RE::gold].first = 2147483647;
    assert(!Trade::Sell(&bank, Trade::GetQuote(&bank, 30)));
    assert(bank.inventory[&sword].first == 1);
    assert(!Trade::Sell(player, Trade::GetQuote(player, 30)));

    Stores menus; RE::TESObjectREFR source;
    auto* trade = &Utility::GetSingleton()->trade;
    trade->inventory = bank.inventory; player->inventory.clear();
    menus.TradeMenu(&source);
    assert(menus.options.size() == 4 && menus.cancel == 1);
    assert(menus.options[0].text == "Vault.OpenContainer" && menus.options[1].text == "Vault.Exit");
    assert(menus.options[2].text == "Vault.TakeAll" && menus.options[3].text == "Vault.SellAll");
    auto action = menus.options[0].action; action(); assert(menus.opened == 1);
    action = menus.options[2].action; action(); assert(menus.taken == 1);
    action = menus.options[3].action; action();
    assert(menus.options.size() == 2 && menus.cancel == 0);
    assert(menus.message.starts_with("Vault.Sell 1 Vault.ItemsFor 3 Vault.Septims?\n"));
    assert(menus.message.find("Favourited") != std::string::npos);
    action = menus.options[0].action; action(); assert(trade->inventory[&sword].first == 1);
    action = menus.options[3].action; action();
    Settings::GetSingleton()->GSC_SalePercentage = 50;
    action = menus.options[1].action; action(); assert(trade->inventory[&sword].first == 1);
    action = menus.options[3].action; action(); action = menus.options[1].action; action();
    assert(trade->inventory[&sword].first == 0 && player->inventory[&RE::gold].first == 5);
    trade->inventory[&sword] = {1, std::make_shared<RE::InventoryEntryData>(&sword, 1)};
    player->inventory[&RE::gold].first = 2147483647;
    menus.ShowTradeMenu(&source); action = menus.options[3].action; action();
    assert(menus.options.size() == 2);
    action = menus.options[1].action; action();
    assert(RE::lastHUD == "Skyrim cannot hold the resulting Septim count. No items were sold.");
    assert(trade->inventory[&sword].first == 1);
    player->inventory[&RE::gold].first = 5;
    trade->inventory.clear();
    auto favorite = std::make_shared<RE::InventoryEntryData>(&sword, 3); favorite->favorite = true;
    trade->inventory[&sword] = {3, favorite};
    menus.ShowTradeMenu(&source); action = menus.options[3].action; action();
    assert(RE::lastHUD.find("Favourited") != std::string::npos && RE::lastHUD.find("limit") == std::string::npos);
    assert(trade->inventory[&sword].first == 3 && menus.options.size() == 4);
    menus.ShowTradeMenu(&source); source.alive = false;
    action = menus.options[3].action; action();
    assert(player->inventory[&RE::gold].first == 5);
}
'''
with tempfile.TemporaryDirectory(prefix="arcanevault-trade-check-") as directory:
    path = Path(directory)
    (path / "check.cpp").write_text(program)
    subprocess.run(["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT),
                    str(path / "check.cpp"), "-o", str(path / "check")], check=True)
    subprocess.run([str(path / "check")], check=True)
print("PASS: Trade copies, variant prices, aggregate rounding, protections, limits, stale confirmation, partial removal, repeat sale, and menu actions")
