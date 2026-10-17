"""Time production crafting transfers with engine stubs; exclude native menus and engine latency."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile

import check_stolen

ROOT = check_stolen.ROOT
FILES = ("src/Stores.cpp", "src/Events.cpp", "src/InventoryStacks.cpp", "src/InventoryStacks.h", "src/Soulgems.cpp")


def body(source, signature, ending="\n}\n"):
    start=source.index(signature)
    return source[start:source.index(ending,start)+len(ending)]


def common_source():
    text=check_stolen.common
    text=text.replace("struct TESObjectREFR;\nstruct BGSKeyword", "struct TESObjectREFR;struct TESSoulGem;\nstruct BGSKeyword",1)
    text=text.replace("struct TESSoulGem {};", "enum class SOUL_LEVEL {kNone,kPetty,kLesser,kCommon,kGreater,kGrand};\nstruct ExtraSoul { SOUL_LEVEL soul; SOUL_LEVEL GetContainedSoul()const{return soul;} };\nstruct TESSoulGem;")
    text=text.replace("bool weapon=false,armor=false;", "bool weapon=false,armor=false; bool gem=false; CategoryMask categories=0;")
    text=text.replace("else if constexpr(std::is_same_v<T,BGSKeywordForm>)", "else if constexpr(std::is_same_v<T,TESSoulGem>) return gem?reinterpret_cast<T*>(this):nullptr;\n        else if constexpr(std::is_same_v<T,BGSKeywordForm>)")
    text=text.replace("struct ExtraEnchantment {", "struct TESSoulGem:TESBoundObject { SOUL_LEVEL soul=SOUL_LEVEL::kGrand; TESSoulGem* linkedSoulGem=nullptr; SOUL_LEVEL GetContainedSoul()const{return soul;} };\nstruct ExtraEnchantment {")
    text=text.replace("std::optional<ExtraUniqueID> unique{};", "std::optional<ExtraUniqueID> unique{};std::optional<ExtraSoul> soul{};")
    text=text.replace("if constexpr(std::is_same_v<T,ExtraEnchantment>)", "if constexpr(std::is_same_v<T,ExtraSoul>)return soul?&*soul:nullptr;else if constexpr(std::is_same_v<T,ExtraEnchantment>)")
    text=text.replace("if(worn!=other.worn", "if((soul?soul->soul:SOUL_LEVEL::kNone)!=(other.soul?other.soul->soul:SOUL_LEVEL::kNone))return false;\n        if(worn!=other.worn")
    text=text.replace("inline static std::map<unsigned,TESObjectREFR*> refs;", "inline static std::map<unsigned,TESObjectREFR*> refs;inline static std::map<unsigned,void*> objects;")
    text=text.replace("return refs.contains(id)?refs[id]:nullptr;", "if constexpr(std::is_same_v<T,TESSoulGem>)return objects.contains(id)?static_cast<T*>(objects[id]):nullptr;else return refs.contains(id)?refs[id]:nullptr;")
    text=text.replace("auto GetInventory(std::function", "std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> GetInventory(std::function")
    text=text.replace("inline bool inspectionOpen=false;", "struct Counters { inline static std::uint64_t calls=0,visits=0,copies=0,moves=0,bulks=0;static void Reset(){calls=visits=copies=moves=bulks=0;} };\ninline bool inspectionOpen=false;")
    text=text.replace("++bulkTransfers;", "++bulkTransfers;++Counters::bulks;")
    text=text.replace("std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;", "++Counters::calls;std::map<TESBoundObject*,std::pair<int,std::shared_ptr<InventoryEntryData>>> result;")
    text=text.replace("for(const auto& [item,row]:rows){", "for(const auto& [item,row]:rows){++Counters::visits;")
    text=text.replace("++inventoryCopies;", "++inventoryCopies;++Counters::copies;")
    text=text.replace("assert(!inspectionOpen);if(refuse)return;", "++Counters::moves;assert(!inspectionOpen);if(refuse)return;")
    text=text.replace("struct Utility {", "struct Utility { BenchType bench=BenchType::None;BenchType GetBenchType(RE::TESObjectREFR*)const{return bench;} bool isSmithing(RE::FormID)const{return true;}")
    text=text.replace("struct Settings {", "struct Settings { bool GSC_CraftingLoan=true,GSC_ReturnIgnoredItems=true;")
    text=text.replace("return ToMask(item->armor?ItemCategory::Jewelry:ItemCategory::Weapon);", "return item->categories;")
    text=text.replace("struct Stores {", "struct Stores { std::unordered_map<RE::FormID,std::pair<int,int>> junkLoan_;void BeginJunkLoan();void EndJunkLoan();void ResetJunkLoan(){junkLoan_.clear();} void AllToPlayer(Container);void StoreToPlayer(ItemCategory,Container,int=0,std::optional<int> = {});")
    text += "\n#include <utility>\n#include <iostream>\n#include \"src/Soulgems.h\"\nnamespace PlayerEquipment { inline const Snapshot* Current(){return nullptr;} }\n"
    return text


MAIN = r'''
int main(int argc,char** argv){
 assert(argc==6);const int bench=std::stoi(argv[1]),size=std::stoi(argv[2]),mode=std::stoi(argv[3]),sample=std::stoi(argv[4]),scenario=std::stoi(argv[5]);
 const int types=scenario==0?size:1,mainCount=scenario==0?3:size,otherCount=scenario==0?2:size;
 auto* player=RE::PlayerCharacter::GetSingleton();auto* utility=Utility::GetSingleton();auto* stores=Stores::GetSingleton();
 std::map<Container,std::unique_ptr<RE::TESObjectREFR>> banks;
 for(auto kind:{Container::Alchemy,Container::Smithing,Container::Food,Container::Weapon,Container::Armor,Container::Junk,Container::EnchantedItems,Container::Soulgem,Container::EmptySoulgems,Container::FilledSoulgems}){
  banks[kind]=std::make_unique<RE::TESObjectREFR>(9000+static_cast<unsigned>(kind));utility->containers[kind]=banks[kind].get();
 }
 RE::TESObjectREFR furniture{8000};std::array<RE::EnchantmentItem,3> customEnchantments;RE::TESForm owner{7000,false};
 utility->bench=static_cast<BenchType>(bench);
 std::vector<RE::TESBoundObject> items(types),junk(types);std::vector<RE::TESSoulGem> gems(types);
 std::map<RE::TESBoundObject*,Container> origins;
 std::map<RE::TESBoundObject*,int> expectedCounts;
 std::map<RE::TESBoundObject*,std::map<std::pair<std::string,RE::EnchantmentItem*>,int>> expectedMetadata;
 auto seed=[&](RE::TESBoundObject* item,Container home,int count,const std::string& metadata){
  origins[item]=home;expectedCounts[item]=count;
  if(scenario==2){
   for(int n=0;n<count;++n){
    auto tag=metadata+std::to_string(n);banks[home]->Put(item,0,1,&owner,tag);
    auto* custom=item->weapon || item->armor?&customEnchantments[n%3]:nullptr;
    if(custom)banks[home]->rows[item].extras.back()->enchantment=RE::ExtraEnchantment{custom};
    expectedMetadata[item][{tag,custom}]=1;
   }
  }else{banks[home]->Put(item,0,count,&owner,metadata);if(count)expectedMetadata[item][{metadata,nullptr}]=count;}
 };
 for(int i=0;i<types;++i){
  auto& item=items[i];item.id=10000+i;auto home=Container::Alchemy;
  switch(utility->bench){
  case BenchType::Alchemy:item.categories=ToMask(ItemCategory::Alchemy);break;
  case BenchType::Smithing:home=Container::Smithing;item.categories=ToMask(ItemCategory::Smithing);break;
  case BenchType::Cooking:home=Container::Food;item.categories=ToMask(ItemCategory::Food);break;
  case BenchType::StaffEnchanting:item.categories=ToMask(ItemCategory::Catalyst)|ToMask(ItemCategory::Alchemy);break;
  case BenchType::Enchanting:break;
  default:assert(false);
  }
  if(utility->bench!=BenchType::Enchanting)seed(&item,home,mainCount,"loan");
  auto& spare=junk[i];spare.id=20000+i;spare.categories=0;seed(&spare,Container::Junk,otherCount,"junk loan");
  if(utility->bench==BenchType::Enchanting || utility->bench==BenchType::Smithing){
   auto& gem=gems[i];gem.id=30000+i;gem.gem=true;RE::TESForm::objects[gem.id]=&gem;
   seed(&gem,Container::Soulgem,otherCount,"gem loan");
  }
 }
 // Carried equipment makes return scans traverse inventory unrelated to this loan.
 std::vector<RE::TESBoundObject> carried(100);
 for(int i=0;i<100;++i){carried[i].id=40000+i;player->Put(&carried[i],0,1,&owner,"carried");player->rows[&carried[i]].favorite=true;}
 auto run=[&](const char* phase,const auto& action){
  RE::Counters::Reset();const auto start=std::chrono::steady_clock::now();action();SKSE::GetTaskInterface()->Run();
  const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
  std::cout<<"{\"bench\":"<<bench<<",\"size\":"<<size<<",\"mode\":"<<mode<<",\"sample\":"<<sample<<",\"scenario\":"<<scenario
   <<",\"phase\":\""<<phase<<"\",\"ms\":"<<ms<<",\"inventory_calls\":"<<RE::Counters::calls
   <<",\"entries_visited\":"<<RE::Counters::visits<<",\"entries_copied\":"<<RE::Counters::copies<<",\"moves\":"<<RE::Counters::moves
   <<",\"bulk_calls\":"<<RE::Counters::bulks<<"}\n"<<std::flush;
 };
 if(mode==0){
  run("take",[&]{
   for(auto home:{Container::Alchemy,Container::Smithing,Container::Food})stores->AllToPlayer(home);
   stores->AllToPlayer(Container::Soulgem);stores->AllToPlayer(Container::Junk);
  });
 }else run("take",[&]{CraftingLoanState::GetSingleton()->EnterCrafting(&furniture);});
 const auto borrowedCounts=player->GetInventoryCounts();
 for(auto& [item,home]:origins){(void)home;assert(borrowedCounts.at(item)==expectedCounts.at(item));}
 if(mode==0)run("return",[&]{
  for(auto category:{ItemCategory::Alchemy,ItemCategory::Smithing,ItemCategory::Food,ItemCategory::Weapon,ItemCategory::Armor}){
   const auto home=category==ItemCategory::Alchemy?Container::Alchemy:category==ItemCategory::Smithing?Container::Smithing:category==ItemCategory::Food?Container::Food:category==ItemCategory::Weapon?Container::Weapon:Container::Armor;
   stores->PlayerToStore(category,home);
  }
  for(auto& [item,home]:origins)if(home==Container::Junk || home==Container::Soulgem)
   while(InventoryStacks::Count(player,item)>0){auto stacks=InventoryStacks::Read(player,{},item);assert(!stacks.empty() && InventoryStacks::Move(stacks.front(),banks[home].get()));}
 });else run("return",[&]{CraftingLoanState::GetSingleton()->ExitCrafting();});
 const auto finalCarried=player->GetInventoryCounts();
 std::map<Container,std::map<RE::TESBoundObject*,int>> finalStored;
 for(auto& [home,bank]:banks)finalStored[home]=bank->GetInventoryCounts();
 for(auto& [item,home]:origins){
  assert(finalCarried.at(item)==0 && finalStored.at(home).at(item)==expectedCounts.at(item));
  std::map<std::pair<std::string,RE::EnchantmentItem*>,int> metadata;
  for(const auto& extra:banks[home]->rows[item].extras){
   assert(extra->owner==&owner);metadata[{extra->metadata,extra->enchantment?extra->enchantment->enchantment:nullptr}]+=extra->count;
   assert(!extra->GetLinkedRef(&RE::TESDataHandler::GetSingleton()->enchantedKeyword));
  }
  assert(metadata==expectedMetadata.at(item));
 }
 for(auto& item:carried)assert(finalCarried.at(&item)==1 && player->rows[&item].extras.front()->metadata=="carried");
 assert(InventoryStacks::Read(banks[Container::EnchantedItems].get()).empty());
}
'''


def build_program(sources):
    stores=sources["src/Stores.cpp"]
    signature="    int MoveItems(" if "    int MoveItems(" in stores else "    void MoveItems("
    methods=body(stores,signature,"\n    }")+"\n"
    for name in ("PlayerToStore","StoreToPlayer","AllToPlayer","BeginJunkLoan","EndJunkLoan"):
        methods+=body(stores,"void Stores::"+name+"(")
    events=sources["src/Events.cpp"]
    loan=events[events.index("class CraftingLoanState {"):events.index("class FurnitureActivation {")]
    return '#include "common.hpp"\n'+methods+loan+MAIN


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--sizes",type=int,nargs="+",default=[0,100,300,1000])
    parser.add_argument("--baseline",help="Git revision to compare with working sources in the same batch")
    parser.add_argument("--scenarios",nargs="+",choices=["types","quantity","stacks"],default=["types","quantity","stacks"])
    parser.add_argument("--samples",type=int,default=2)
    parser.add_argument("--timeout",type=int,default=60)
    parser.add_argument("--benches",type=int,nargs="+",default=[1,2,3,4,5],choices=[1,2,3,4,5])
    args=parser.parse_args()
    assert not args.output.exists(),"Choose a new output path to preserve earlier measurements"
    assert args.samples>=2 and args.timeout>0 and all(0<=n<=1000 for n in args.sizes)
    variants={"working":{p:(ROOT/p).read_text() for p in FILES}}
    if args.baseline:
      variants={"baseline":{p:subprocess.check_output(["git","show",f"{args.baseline}:{p}"],text=True,cwd=ROOT) for p in FILES},**variants}
    common=common_source()
    report={"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
      "boundary":"Linux CPU timings of actual crafting-session and transfers with instrumented engine stubs; native inventory/UI/animation costs and real classification are excluded. Manual includes deferred cleanup but excludes the Quick Transfer menu lifecycle. Types seeds N main and N Junk types, plus N gem types for Smithing/Enchanting. Quantity seeds N copies in one explicit stack per family. Stacks seeds N distinct metadata-bearing physical stacks sharing one base per family. All cases keep 100 unrelated carried favourites.",
      "benches":{1:"Alchemy",2:"Smithing",3:"Cooking",4:"Enchanting",5:"Staff enchanting"},"modes":{0:"manual",1:"loan"},
      "compiler":subprocess.check_output(["g++","--version"],text=True).splitlines()[0],
      "baseline":args.baseline,"scenarios":{0:"types",1:"quantity",2:"stacks"},
      "sources":{v:{p:hashlib.sha256(t.encode()).hexdigest() for p,t in sources.items()} for v,sources in variants.items()},
      "harness_sha256":hashlib.sha256((common+MAIN).encode()).hexdigest(),"samples":[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    with tempfile.TemporaryDirectory(prefix="av-loan-bench-") as directory:
      binaries={}
      for variant,sources in variants.items():
        root=Path(directory)/variant;root.mkdir();(root/"src").mkdir()
        (root/"src/InventoryStacks.h").write_text(sources["src/InventoryStacks.h"])
        (root/"src/StolenItems.h").write_text((ROOT/"src/StolenItems.h").read_text())
        (root/"src/PlayerEquipment.h").write_text((ROOT/"src/PlayerEquipment.h").read_text())
        (root/"common.hpp").write_text("#pragma once\n"+common);cpp=root/"bench.cpp";cpp.write_text(build_program(sources))
        files=[]
        for name in ("InventoryStacks","Soulgems"):
          file=root/(name+".cpp");file.write_text('#include "common.hpp"\n'+"\n".join(line for line in sources["src/"+name+".cpp"].splitlines() if not line.startswith("#include")));files.append(str(file))
        binaries[variant]=root/"bench"
        subprocess.run(["g++","-O2","-std=c++20","-Wall","-Wextra","-Werror","-I",str(root),"-I",str(ROOT),str(cpp),*files,"-o",str(binaries[variant])],check=True,timeout=90)
      for scenario in args.scenarios:
       scenario_id=["types","quantity","stacks"].index(scenario)
       for size in args.sizes:
        if size==0 and scenario_id:continue
        for bench in args.benches:
         for sample in range(args.samples):
          order=list(binaries) if sample%2==0 else list(reversed(binaries))
          for variant in order:
           for mode in ((0,1) if sample%2==0 else (1,0)):
            command=[str(binaries[variant]),str(bench),str(size),str(mode),str(sample),str(scenario_id)]
            try:
             output=subprocess.check_output(command,text=True,timeout=args.timeout)
            except subprocess.TimeoutExpired as error:
             output=error.stdout or b""
             if isinstance(output,bytes):output=output.decode()
             report["samples"].extend({**json.loads(line),"variant":variant,"validated":False} for line in output.splitlines() if line.endswith("}"))
             report.setdefault("timeouts",[]).append({"variant":variant,"scenario":scenario,"bench":bench,"size":size,"mode":mode,"sample":sample,"limit_seconds":args.timeout})
             args.output.write_text(json.dumps(report,indent=2)+"\n")
             raise
            report["samples"].extend({**json.loads(line),"variant":variant,"validated":True} for line in output.splitlines())
            args.output.write_text(json.dumps(report,indent=2)+"\n")
         print(f"Checked {scenario}, bench {bench}, size {size}",flush=True)
    groups={}
    for sample in report["samples"]:
      key=(sample["bench"],sample["size"],sample["mode"],sample["phase"],sample["variant"],sample["scenario"]);groups.setdefault(key,[]).append(sample)
    report["summary"]=[{"bench":key[0],"size":key[1],"mode":key[2],"phase":key[3],"variant":key[4],"scenario":key[5],
      "min_ms":min(s["ms"] for s in rows),"median_ms":statistics.median(s["ms"] for s in rows),"max_ms":max(s["ms"] for s in rows),
      "inventory_calls":rows[0]["inventory_calls"],"entries_visited":rows[0]["entries_visited"],"entries_copied":rows[0]["entries_copied"],"moves":rows[0]["moves"],"bulk_calls":rows[0]["bulk_calls"]} for key,rows in groups.items()]
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(f"PASS: crafting counts, metadata, carried items and loan/manual timings in {args.output}")


if __name__=="__main__":main()
