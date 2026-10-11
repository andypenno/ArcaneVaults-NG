# Storage and persistence

The shared operations are in [Stores.cpp](../src/Stores.cpp); classification lives in [ItemClass.cpp](../src/ItemClass.cpp); [Utility.cpp](../src/Utility.cpp) binds enum values to external game references. Redirect persistence does not serialize item inventories. Skyrim owns the inventories of the companion references and saves their game state.

## Transfers and sorting

| Operation | Selection and protection |
| --- | --- |
| `PlayerToStore` | Positive inventory counts matching a category; skips quest, favorited, and worn entries; optional retained count keeps that many per carried base item |
| `StoreToPlayer` | Positive counts matching a category, without the player's protection checks |
| `StoreToStore` | Positive counts matching a category, without quest/favorite/worn checks |
| `AllToStore` | `InventoryChanges::RemoveAllItems`; rejects identical source/destination enums |
| `AllToPlayer` | `InventoryChanges::RemoveAllItems` from the selected store |

The category helpers iterate inventory snapshots and call `RemoveItem` with `kStoreInContainer` and a null extra-list argument. `PlayerToStore` uses the actual available count for zero requests and clamps positive requests to that count. The retained count is subtracted before clamping; negative requests or reserves are rejected, and deposits never withdraw stored items. `StoreToStore` uses the actual count, including stacks above 9999. `StoreToPlayer` also uses actual counts for zero requests, clamps positive requests to available counts, and rejects negative requests. Claims about individual enchanted instances or extra data require runtime checks.

`SortItems` first recovers physical soul gems from Sort and Smithing storage into the Soulgem Vault, then drains Sort in this order: Gold, Ammunition, Keys, Smithing, Food, Alchemy, Scroll, Book, Treasure, Armor, Weapon, Concoction. Each pass sees the remaining inventory. An item with multiple category bits goes to the first applicable store; a final AllToStore pass moves every remaining item into Junk. The Alchemy pass selects the parent bit and includes Ingredients, Reagents, and Catalysts.

`OffloadItems` independently checks configured leaf categories and moves matching player items to parent stores. See [configuration.md](configuration.md) for defaults. Master is a menu entry point; Sort is the sorting inbox; Personal is direct storage without a classification pass. Junk is independent storage for the final Sort remainder, including items deliberately skipped by other passes. Quick Transfer never sweeps unmatched player inventory into Junk.

## Vaults and archives

Most archive actions temporarily move matching items from their parent vault into an archive reference, activate it, and return its entire inventory to the parent on close. The menu may then return to the parent message box or close the source animation. Archives are real game inventories, not filtered UI views. New items deposited in an archive also return to its parent.

| Parent | Archives |
| --- | --- |
| Smithing | Crafting, Smelting, Tanning, Construction, Gemstone |
| Alchemy | Reagent, labeled Spice in storage UI |
| Concoction | Potion, Poison, Restorative |
| Food | CookedFood, RawFood |
| Armor | Clothing, HeavyArmor, LightArmor, Jewelry |
| Weapon | Archery, OneHand, TwoHand, Staff |

Do not assume every parent menu consolidates exactly the same children. `ShowVaultDetail1Menu` has its own consolidation actions, while category-specific menus have others. The Armor/Weapon Unclassified actions drain children, separate recognized types into archives, open the parent with the remainder, then reunite them on close.

Alchemy Transfer All selects the Alchemy parent category, including Ingredients, Reagents, and Catalysts, and preserves quest, favourited, and worn entries.

Keep One/Keep Three labels do not define transfer semantics. The Alchemy Keep One action deposits ingredients then withdraws one per item. Book Transfer One Copy and Scroll Keep One/Keep Three first withdraw the entire store, then deposit one or three per item. Verify the actual inventory delta when changing those menus.

Ammunition is an independent vault for arrows and bolts. Its menu offers Keep N, Store All, Take All, Open, and Exit. N comes from the Options setting described in [configuration.md](configuration.md). Keep N deposits only the excess above N per carried ammunition record; it never tops up smaller stacks from storage. Equipped, favorited, and quest entries remain untouched. Take All returns the entire inventory. Ammunition appears on the second main-vault page and in the vault binding list.

Keys is an independent vault. Its menu offers Keep One, Store All, Take All, Open, and Exit. Keep One retains one of each carried key record and deposits only duplicates. Take All returns the entire vault inventory, including manual deposits. Keys also appears in the second main-vault page and the vault binding list. Quick Transfer defaults are described in [configuration.md](configuration.md).

Valuables is a composite archive reached through Bind Archive. Its menu offers Open, Exit, Keep N Septims, Store All Septims, and Take All Septims. Exit is the cancel action. Treasure opens directly without a Valuables submenu. The Septim actions deposit into or retrieve from Treasure; Keep N uses Gold Keep Amount in Options. Take All Septims selects Gold only and handles counts above 9999.

Open temporarily gathers Gold from Treasure, Gemstone and PreciousIngot from Smithing, and Jewelry from Armor. Closing returns gems and precious ingots to Smithing, jewelry to Armor, and Gold plus unrelated manual deposits to Treasure. Materials therefore remain available to the existing Smithing crafting loan. The Gemstone and Jewelry archives keep their existing parents. Opening the Valuables menu also returns any contents left in its reference, including contents persisted while the archive was open. All three parent destinations must exist before gathering or returning.

## Soul gem storage

[Soulgems.cpp](../src/Soulgems.cpp) handles physical `TESSoulGem` records independently of category overrides. Generic category transfers skip them. Quick Transfer deposits all eligible filled gems and retains up to the configured number of empties per base record. It never withdraws to refill a reserve. The bank menu offers Keep N Empty, Store All, Filled Soulgems, Empty Soulgems, Open Vault, and Exit. Empty Soulgems offers Take All Empty Soulgems, Open, and Exit; Filled Soulgems opens directly. Both archives are bindable near an enchanter and return their inventories to the existing bank on close.

Stack classification uses explicit `ExtraSoul` data, including an explicit zero, before the base record's soul. Each extra list supplies its own count; the remainder uses base-record state. Duplicate extra-list pointers, invalid soul levels, or counts exceeding the inventory total leave that record untouched. Moves preserve base records and pass the selected extra list to Skyrim. Splitting moves explicit stacks first so null extra-list transfers cannot select another state. Deposits temporarily park retained explicit empties when the base record is filled, then return them to the player.

Quest, favorited, and equipped inventory entries are skipped. Vanilla Azura's Star and Black Star, plus records linked to them, are excluded from automatic transfers. Flawed Varla Stones and mod-added native soul gems use the same state and metadata rules. No soul-trap, filling, consumption, or gem-conversion logic is replaced.

Bank access, Quick Transfer, Sort, and gem loans recover misplaced soul gems from Smithing, its Crafting/Smelting/Construction/Tanning/Gemstone archives, and Sort. Existing Soulgem storage IDs are preserved. Both new archives consolidate before bank operations and loans, including contents saved while an archive was open.

## Classification

[ItemClass.h](../src/ItemClass.h) defines separate `Container`, `ItemCategory`, `ContainerGroup`, and `BenchType` enums. `CategoryMask` is a 64-bit integer; a category's underlying value chooses its bit and None maps to zero. Keep bit positions within mask width when extending it.

Physical soul gems always route through the dedicated soul gem transfer path. Other items retain user override, bundled override, then built-in precedence. An override replaces built-in classification; `ExpandCategories` adds parent bits for weapon, armor, concoction, smithing, food, and alchemy leaf categories. It does not infer every related leaf bit. For example, overriding SpellTome does not add Book, and Potion does not imply Restorative.

| Engine type | Built-in classification |
| --- | --- |
| `TESObjectMISC` | Crafting/Smelting/Tanning/Construction plus Smithing when present in recipe caches; otherwise no category |
| `IngredientItem` | Alchemy plus Reagent if food or a cooking input; otherwise Catalyst if a smithing input; otherwise Ingredient |
| `AlchemyItem` food | Food plus RawFood when raw keyword or cooking cache matches, otherwise CookedFood |
| Other `AlchemyItem` | Concoction plus Potion/Poison; adds Restorative if any effect matches health/magicka/stamina restoration |
| Armor | Armor plus Jewelry by keyword or ring/amulet/circlet slots; otherwise Clothing/HeavyArmor/LightArmor |
| Weapon | Weapon plus OneHand, TwoHand, Archery, or Staff according to weapon type |
| Book | Note scrolls become Scroll; other books become Book and spell-teaching books also SpellTome |
| Soul gem | Soulgem before miscellaneous items and overrides; filled/empty state belongs to inventory stacks |
| Gold | `TESForm::IsGold()` identifies Septims; its separate Gold category does not expand to Treasure |
| Gold/silver ingots | PreciousIngot and Smithing, plus the existing recipe-derived categories |
| Ammunition | Ammunition; `TESAmmo` covers arrows and bolts, after override precedence |
| Key | Keys; checked before the miscellaneous-item branch because `TESKey` derives from `TESObjectMISC` |
| Other types | No built-in category |

The vanilla precious ingot IDs are Gold `0x0005AD9E` and Silver `0x0005ACE3`, verified against [UESP](https://en.uesp.net/wiki/Skyrim:Ores_and_Ingots). Gemstones retain the bundled Gemstone overrides. Mods can classify additional records through Gemstone or PreciousIngot overrides.

Native `RE::ScrollItem` has no explicit built-in branch. Gemstone and Treasure rely on overrides rather than generic misc-item rules. Legacy EmptySoulgem/FilledSoulgem/GrandSoulgem enum values remain reserved; the soul gem module evaluates physical state.

`Utility::CacheTemperRecipes` scans loaded constructible objects once at data load. Despite its name, it gathers recipe input FormIDs from forge, smelting, tanning, carpenter/building, and cooking keywords. Construction also accepts bench editor IDs containing `BYOHBuilding` or `BYOHHouse`. Mods' loaded recipes affect classification. `CookingMap` is declared but not populated or consumed in current code; `RawFoodMap` is the cooking-input cache actually used.

## Redirect persistence

[Serialization.h](../src/Serialization.h) sets plugin ID `'AVLS'`, record type `'RDIR'`, and version 1. [Serialization.cpp](../src/Serialization.cpp) chooses the storage mode using the current GlobalRedirect setting.

| Mode | Save | Load/revert |
| --- | --- | --- |
| GlobalRedirect enabled, default | Write global redirects INI; no per-save redirect record | Clear mappings and load global INI |
| GlobalRedirect disabled | Write SKSE record | Load clears mappings, reads records, resolves saved FormIDs; revert clears mappings |

The per-save record contains a 32-bit entry count followed by pairs of source and destination FormIDs. Load checks record type/version and truncation, caps count to record capacity, resolves both IDs through SKSE, and requires reference forms before adding mappings. Preserve these checks and plan migration before changing the format/version.

Global mode uses `[Redirects]` entries with stable plugin-local identifiers. Example syntax:

```ini
[Redirects]
ExampleHouse.esp|0x123 = ArcaneVaults-LinkedStorage.esp|0xD95
```

This is illustrative, not a real source reference. `MakeFormIdentifier` refuses dynamic forms and forms without a file identity. Loading requires valid fully consumed hexadecimal IDs and resolvable reference forms, skips invalid entries, and re-adds mappings so activator-linked containers are blocked again. Saving replaces the Redirects section while preserving other sections.

Assignment changes update memory immediately. Global redirects are written by the SKSE save callback, not by every assignment. Switching persistence mode in the settings UI does not migrate existing records or INI data. Global refers to the mapping across saves, not item inventories shared across games.

## Companion reference registry

The table below is extracted from `Utility::LoadContainers`. IDs are local reference IDs in `ArcaneVaults-LinkedStorage.esp`, not load-order-prefixed runtime IDs. The release build generates that ESP from the working record definition. `AddContainer` requires a reference, translates and renames a container base when available, and registers a menu action. Enum names and IDs must stay coordinated with the generated plugin.

| Container | Local ID | Group | Stores action |
| --- | --- | --- | --- |
| Master | `0xD93` | Special | `VaultMenu` |
| Sort | `0xDB9` | Special | `SortingMenu` |
| Smithing | `0xDA7` | Vault | `SmithMenu` |
| Crafting | `0xDA8` | Archive | `SmithCraftMenu` |
| Smelting | `0xDAA` | Archive | `SmithSmeltMenu` |
| Tanning | `0xDAB` | Archive | `SmithTanMenu` |
| Construction | `0xDA9` | Archive | `SmithConstructMenu` |
| Gemstone | `0xDA2` | Archive | `GemstoneMenu` |
| Alchemy | `0xD94` | Vault | `AlchemyMenu` |
| Concoction | `0xDA3` | Vault | `PotionMenu` |
| Potion | `0xDA4` | Archive | `PotionPositiveMenu` |
| Poison | `0xDA5` | Archive | `PotionNegativeMenu` |
| Restorative | `0xDA6` | Archive | `PotionRestoreMenu` |
| Soulgem | `0xDAC` | Vault | `SoulgemMenu` |
| Food | `0xD9D` | Vault | `FoodMenu` |
| Reagent | `0xDA0` | Archive | `FoodSaltMenu` |
| RawFood | `0xD9F` | Archive | `FoodRawMenu` |
| CookedFood | `0xD9E` | Archive | `FoodCookedMenu` |
| Weapon | `0xDAF` | Vault | `WeaponMenu` |
| Archery | `0xDB0` | Archive | `WeaponArcheryMenu` |
| Staff | `0xDB3` | Archive | `WeaponStaffMenu` |
| OneHand | `0xDB1` | Archive | `WeaponOneHandMenu` |
| TwoHand | `0xDB2` | Archive | `WeaponTwoHandMenu` |
| Armor | `0xD95` | Vault | `ArmorMenu` |
| HeavyArmor | `0xD97` | Archive | `ArmorHeavyMenu` |
| LightArmor | `0xD98` | Archive | `ArmorLightMenu` |
| Jewelry | `0xD99` | Archive | `ArmorJewelryMenu` |
| Clothing | `0xD96` | Archive | `ArmorClothingMenu` |
| Book | `0xD9A` | Vault | `BookMenu` |
| Scroll | `0xD9B` | Vault | `ScrollMenu` |
| Treasure | `0xDAD` | Vault | `TreasureMenu` |
| Personal | `0xDA1` | Vault | `PersonalMenu` |
| Junk | `0xDCF` | Vault | `JunkMenu` |
| Keys | `0xDC5` | Vault | `KeysMenu` |
| Ammunition | `0xDC7` | Vault | `AmmunitionMenu` |
| FilledSoulgems | `0xDCB` | Archive | `FilledSoulgemsMenu` |
| EmptySoulgems | `0xDCD` | Archive | `EmptySoulgemsMenu` |
| Valuables | `0xDC9` | Archive | `ValuablesMenu` |
