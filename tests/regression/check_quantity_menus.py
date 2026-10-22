"""Exercise quantity menu builders, ordering and callbacks with the retained inventory harness."""
import ast
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
harness = ROOT / 'tests/regression/check_keys.py'
tree = ast.parse(harness.read_text())
prefix = []
for statement in tree.body:
    if isinstance(statement, ast.With):
        break
    prefix.append(statement)
scope = {'__file__': str(harness)}
exec(compile(ast.Module(body=prefix, type_ignores=[]), str(harness), 'exec'), scope)
program = scope['program'].split('int main() {', 1)[0]
source = (ROOT / 'src/Stores.cpp').read_text()
quantity_menus = set()
for match in re.finditer(r'void Stores::(Show\w+Menu)\(', source):
    body = source[match.start():source.index('\n}\n', match.start())]
    if 'Translate("Vault.TakeUpToAmount")' in body:
        quantity_menus.add(match[1])
assert quantity_menus == {'Show' + name + 'Menu' for name in
    ('Keys', 'Ammunition', 'Alchemy', 'Soulgem', 'Book', 'Scroll', 'Valuables', 'Gear', 'Notes')}
start = program.index('    void ShowDynamicMessageBox(')
end = program.index('\n', start)
program = program[:start] + '''
    RE::ObjectRefHandle navigationSource_;
    int cancelIndex=-1;
    void ResetNavigation();
    void ShowDynamicMessageBox(std::string_view, std::vector<MenuOption>, std::int32_t);
''' + program[end:]
for name in ('ResetNavigation', 'ShowDynamicMessageBox'):
    start = source.index('void Stores::' + name + '(')
    body = source[start:source.index('\n}\n', start) + 3]
    if name == 'ShowDynamicMessageBox':
        body = body[:body.index('    // Start the strings')]
        body += '    title=a_message;options=std::move(a_options);cancelIndex=a_cancelOption;\n}\n'
    program += body
start = program.index('const char* Translate(const char* key) {')
end = program.index('\n', start)
labels = json.loads((ROOT / 'ini/ArcaneVaultTranslation.json').read_text())
rows = ','.join('{' + json.dumps(k) + ', ' + json.dumps(v) + '}' for k, v in labels.items())
program = program[:start] + '''
bool alternateLanguage=false;
const char* Translate(const char* key) {
    static const std::map<std::string,std::string> english={''' + rows + '''};
    static const auto alternate=[] {auto rows=english;for(auto& [key,text]:rows)text="ZZ "+text;return rows;}();
    const auto& labels=alternateLanguage?alternate:english;
    const auto found=labels.find(key);return found==labels.end()?key:found->second.c_str();
}
''' + program[end:]
program += r'''
int main() {
    Stores stores;RE::TESObjectREFR source;
    auto* settings=Settings::GetSingleton();auto* utility=Utility::GetSingleton();
    auto* player=RE::PlayerCharacter::GetSingleton();
    struct Case {const char* name;void(Stores::*show)(RE::TESObjectREFR*);ItemCategory category;Container container;int amount;const char* suffix;bool withdrawAll;};
    settings->GSC_AmmunitionKeepAmount=7;settings->GSC_KeepSelectedAmmunition=false;
    settings->GSC_AlchemyKeepAmount=7;settings->GSC_SoulgemKeepAmount=7;
    settings->GSC_ScrollKeepAmount=7;settings->GSC_GoldKeepAmount=7;settings->GSC_LockpickKeepAmount=7;
    const Case cases[]={
        {"Keys",&Stores::KeysMenu,ItemCategory::Keys,Container::Keys,1,"",true},
        {"Ammunition",&Stores::AmmunitionMenu,ItemCategory::Ammunition,Container::Ammunition,7,"",true},
        {"Alchemy",&Stores::AlchemyMenu,ItemCategory::Alchemy,Container::Alchemy,7,"",false},
        {"Soulgems",&Stores::SoulgemMenu,ItemCategory::Soulgem,Container::Soulgem,7,"Vault.Empty",false},
        {"Books",&Stores::BookMenu,ItemCategory::Book,Container::Book,1,"",false},
        {"Scrolls",&Stores::ScrollMenu,ItemCategory::Scroll,Container::Scroll,7,"",false},
        {"Valuables",&Stores::ValuablesMenu,ItemCategory::Gold,Container::Treasure,7,"Vault.Septims",true},
        {"Gear",&Stores::GearMenu,ItemCategory::Lockpick,Container::Gear,7,"Vault.Lockpicks",false},
        {"Notes",&Stores::NotesMenu,ItemCategory::Note,Container::Notes,1,"",false}};
    int failures=0;
    for(int reserve:{0,7})for(bool translated:{false,true})for(bool parent:{false,true})for(auto c:cases){
        if(c.amount!=1)c.amount=reserve;
        settings->GSC_AmmunitionKeepAmount=reserve;settings->GSC_AlchemyKeepAmount=reserve;
        settings->GSC_SoulgemKeepAmount=reserve;settings->GSC_ScrollKeepAmount=reserve;
        settings->GSC_GoldKeepAmount=reserve;settings->GSC_LockpickKeepAmount=reserve;
        alternateLanguage=translated;stores.closed=false;int backs=0;
        stores.returnToVault_=parent?std::function<void()>{[&]{++backs;}}:std::function<void()>{};
        (stores.*c.show)(&source);
        const std::string suffix=*c.suffix?" "+std::string(Translate(c.suffix)):"";
        const auto withdraw=std::string(Translate("Vault.TakeUpToAmount"))+" "+std::to_string(c.amount)+suffix;
        const auto keep=std::string(Translate("Vault.KeepAmount"))+" "+std::to_string(c.amount)+suffix;
        const auto store=std::string(Translate("Vault.StoreAll"))+(c.category==ItemCategory::Gold||c.category==ItemCategory::Lockpick?suffix:"");
        std::vector<std::string> expected{Translate("Vault.Open"),withdraw};
        if(c.withdrawAll)expected.push_back(std::string(Translate("Vault.WithdrawAll"))+(c.category==ItemCategory::Gold?suffix:""));
        expected.push_back(keep);expected.push_back(store);
        bool valid=stores.options.size()>=expected.size()+1;
        for(std::size_t i=0;i<expected.size();++i)
            valid=valid && i<stores.options.size() && stores.options[i].text==expected[i];
        for(const auto& label:expected)
            valid=valid && std::count_if(stores.options.begin(),stores.options.end(),[&](const auto& option){return option.text==label;})==1;
        valid=valid && stores.options.back().text==Translate("Vault.Exit") && stores.cancelIndex==static_cast<int>(stores.options.size()-1);
        if(parent)valid=valid && stores.options[stores.options.size()-2].text==Translate("Vault.Back");
        if(!valid){std::cout<<"Missing/incorrect contract "<<c.name<<" translated="<<translated<<" parent="<<parent<<'\n';++failures;continue;}
        auto click=[&](std::size_t index){auto action=stores.options.at(index).action;action();};
        if(parent){click(stores.options.size()-2);assert(backs==1);}
        if(c.category==ItemCategory::Soulgem){
            click(1);assert(Soulgems::lastTarget==c.amount);
        }else{
            auto* bank=utility->GetContainer(c.container);
            RE::TESBoundObject item{c.category},other{c.category==ItemCategory::Lockpick?ItemCategory::Gear:ItemCategory::Junk};
            const auto entry=[](int count,bool quest=false,bool favorite=false,bool worn=false){return std::pair{count,std::make_shared<RE::InventoryEntryData>(quest,favorite,worn)};};
            for(int initial:{0,std::max(0,c.amount-1),c.amount,c.amount+3})for(int stock:{0,2,20})for(bool refuse:{false,true})for(int limit:{2,INT_MAX}){
                player->inventory.clear();bank->inventory.clear();bank->rejectMove=refuse;
                bank->removeLimit=limit;
                player->inventory[&item]=entry(initial);bank->inventory[&item]=entry(stock);
                player->inventory[&other]=entry(9);
                click(1);assert(player->inventory[&item].first==initial+(refuse?0:std::min(stock,std::max(0,c.amount-initial))));
                assert(player->inventory[&other].first==9 && player->inventory[&item].first+bank->inventory[&item].first==initial+stock);
            }
            bank->rejectMove=false;bank->removeLimit=INT_MAX;
            const auto keepIndex=c.withdrawAll?3:2;
            for(int initial:{0,std::max(0,c.amount-1),c.amount,c.amount+3})for(bool refuse:{false,true}){
                player->inventory.clear();bank->inventory.clear();player->rejectMove=refuse;
                player->inventory[&item]=entry(initial);click(keepIndex);
                assert(player->inventory[&item].first==(refuse?initial:std::min(initial,c.amount)));
                assert(player->inventory[&item].first+bank->inventory[&item].first==initial);
            }
            player->rejectMove=false;
            for(int protection:{0,1,2,3}){
                player->inventory.clear();bank->inventory.clear();
                player->inventory[&item]=entry(c.amount+3,protection==1,protection==2,protection==3);
                player->inventory[&other]=entry(9);click(keepIndex+1);
                assert(player->inventory[&item].first==(protection?c.amount+3:0));
                assert(player->inventory[&other].first==9);
            }
            if(c.category==ItemCategory::Book || c.category==ItemCategory::Note){
                RE::TESBoundObject second{c.category},absent{c.category};
                player->inventory.clear();bank->inventory.clear();
                player->inventory[&item]=entry(5);player->inventory[&second]=entry(8);bank->inventory[&absent]=entry(10);
                click(keepIndex);
                assert(player->inventory[&item].first==1 && player->inventory[&second].first==1);
                assert(player->inventory[&absent].first==0 && bank->inventory[&absent].first==10);
                player->inventory.clear();bank->inventory.clear();
            }
            player->inventory.clear();bank->inventory.clear();
        }
        click(0);assert(stores.onClose);auto close=stores.onClose;close();
        assert(!stores.closed && stores.options.front().text==Translate("Vault.Open"));
        click(stores.cancelIndex);assert(stores.closed && !stores.returnToVault_);
    }
    std::cout<<"Quantity menu contract failures="<<failures<<'\n';return failures?1:0;
}
'''
with tempfile.TemporaryDirectory(prefix='arcanevault-quantity-menus-') as temporary:
    path = Path(temporary)
    (path / 'check.cpp').write_text(program)
    subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT),
                    str(path / 'check.cpp'), '-o', str(path / 'check')], check=True)
    subprocess.run([str(path / 'check')], check=True)
