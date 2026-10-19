"""Run the native bench classifier, including Hearthfire carpenter stations."""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source-ref')
args=parser.parse_args()
source=subprocess.check_output(['git','show',f'{args.source_ref}:src/Utility.cpp'],cwd=ROOT,text=True) if args.source_ref else (ROOT/'src/Utility.cpp').read_text()
a=source.index('BenchType Utility::GetBenchType(');source=source[a:source.index('\n}\n',a)+3]
fields=['isAnvil','isForge','isTanning','isSmelter','isBlacksmith','isGrindStone','isWorkbench','craftCarpenter','isCookingPot','isOven','isCampfire','isAlchemy','isGrainMill','isEnchanter','isStaffEnchanter']
program=r'''
#include <array>
#include <string_view>
#include <cstdint>
#include <cassert>
#include <set>
namespace RE {struct TESBoundObject;}
#include "src/ItemClass.h"
namespace RE {
struct TESFurniture {
    struct WorkBenchData {enum class BenchType{kNone,kCreateObject,kSmithingWeapon,kEnchanting,kEnchantingExperiment,kAlchemy,kAlchemyExperiment,kSmithingArmor};};
    struct Value {WorkBenchData::BenchType value=WorkBenchData::BenchType::kNone;auto get()const{return value;}};
    struct {Value benchType;} workBenchData;
    template<class T>T* As(){return this;}
};
struct TESObjectREFR {
    std::set<int> keywords;TESFurniture base;
    bool HasKeyword(int key)const{return keywords.contains(key);}
    TESFurniture* GetBaseObject(){return &base;}
};
}
struct Utility {
FIELDS
    BenchType GetBenchType(RE::TESObjectREFR*);
};
'''.replace('FIELDS','\n'.join(f'    int {name}={i+1};' for i,name in enumerate(fields)))+source+r'''
int main(){
    Utility utility;RE::TESObjectREFR ref;
    assert(utility.GetBenchType(&ref)==BenchType::None);
    ref.base.workBenchData.benchType.value=RE::TESFurniture::WorkBenchData::BenchType::kCreateObject;
    ref.keywords.insert(utility.craftCarpenter);assert(utility.GetBenchType(&ref)==BenchType::Smithing);
    for(auto [key,expected]:std::array{std::pair{utility.isForge,BenchType::Smithing},std::pair{utility.isCookingPot,BenchType::Cooking},
        std::pair{utility.isAlchemy,BenchType::Alchemy},std::pair{utility.isEnchanter,BenchType::Enchanting},std::pair{utility.isStaffEnchanter,BenchType::StaffEnchanting}}){
        ref.keywords={key};assert(utility.GetBenchType(&ref)==expected);
    }
    ref.keywords.clear();ref.base.workBenchData.benchType.value=RE::TESFurniture::WorkBenchData::BenchType::kSmithingArmor;
    assert(utility.GetBenchType(&ref)==BenchType::Smithing);
}
'''
with tempfile.TemporaryDirectory(prefix='av-benches-') as directory:
    root=Path(directory);(root/'check.cpp').write_text(program)
    subprocess.run(['g++','-std=c++20','-Wall','-Wextra','-Werror','-I',str(ROOT),str(root/'check.cpp'),'-o',str(root/'check')],check=True,timeout=60)
    subprocess.run([str(root/'check')],check=True,timeout=10)
print('PASS: carpenter, ordinary keyword stations, native workbench fallback and unrecognised furniture')
