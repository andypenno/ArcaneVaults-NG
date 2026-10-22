# Storage and persistence

The shared operations are in [Stores.cpp](../src/Stores.cpp); classification lives in [ItemClass.cpp](../src/ItemClass.cpp); [Utility.cpp](../src/Utility.cpp) binds enum values to external game references. Redirect persistence does not serialize item inventories. Skyrim owns the inventories of the companion references and saves their game state.

## Transfers and sorting

| Operation | Selection and protection |
| --- | --- |
| `PlayerToStore` | Positive inventory counts matching a category; skips quest, favorited, and worn entries; optional keep-one mode retains one per carried base item |
| `StoreToPlayer` | Positive counts matching a category, without the player's protection checks |
| `StoreToStore` | Positive counts matching a category, without quest/favorite/worn checks |
| `AllToStore` | `InventoryChanges::RemoveAllItems`; rejects identical source/destination enums |
| `AllToPlayer` | `InventoryChanges::RemoveAllItems` from the selected store |

The category helpers iterate inventory snapshots and use `MoveItems` to call `RemoveItem` with `kStoreInContainer` and a null extra-list argument. It checks the remaining source count after each removal and retries partial moves until the requested quantity is transferred. A refused move stops immediately; no fixed 9999 cap is imposed. This includes non-gem crafting-loan returns. `PlayerToStore` uses the actual available count for zero requests and clamps positive requests to that count. The retained count is subtracted before clamping; negative requests or reserves are rejected, and deposits never withdraw stored items. `StoreToStore` uses the actual count, including stacks above 9999. `StoreToPlayer` also uses actual counts for zero requests, clamps positive requests to available counts, and rejects negative requests. Its optional carried target additionally limits withdrawals to the shortfall per base record; a target of zero withdraws nothing. Claims about individual enchanted instances or extra data require runtime checks.

`PlayerToStore` also evaluates Skyrim's standard `GetEquipped` condition for matching items. It resolves the current function on each transfer so mod-installed condition hooks are respected. A successful nonzero result protects the whole base-item stack, as native worn flags already do. Missing or failed condition evaluation leaves the existing quest, favourite, and worn checks in force. Mods keeping worn state private without exposing native flags or this condition cannot be detected through these checks.

`SortItems` drains the Sort container in this order: Keys, Smithing, Food, Alchemy, Soulgem, Scroll, Book, Treasure, Armor, Weapon, Concoction. Each pass sees the remaining inventory. An item with multiple category bits goes to the first applicable store; unmatched items stay in Sort. The Alchemy pass selects the parent bit and includes Ingredients, Reagents, and Catalysts.

`OffloadItems` independently checks configured leaf categories and moves matching player items to parent stores. See [configuration.md](configuration.md) for defaults. Master is a menu entry point; Sort is the sorting inbox; Personal is direct storage without a classification pass.

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

Keep One/Keep Three labels do not define transfer semantics. The Alchemy Keep One action deposits ingredients then withdraws one per item. Book Transfer One Copy and Scroll Keep One/Keep Three first withdraw the entire store, then deposit one or three per item. Verify the actual inventory delta when changing those menus.

Keys is an independent vault. Its menu offers Keep One, Store All, Take Up To 1, Take All, Open, and Exit. Keep One retains one of each carried key record and deposits only duplicates. Take Up To 1 withdraws only missing key records and leaves carried duplicates unchanged. Take All returns the entire vault inventory, including manual deposits. Keys also appears in the second main-vault page and the vault binding list. Quick Transfer defaults are described in [configuration.md](configuration.md).

## Classification

[ItemClass.h](../src/ItemClass.h) defines separate `Container`, `ItemCategory`, `ContainerGroup`, and `BenchType` enums. `CategoryMask` is a 64-bit integer; a category's underlying value chooses its bit and None maps to zero. Keep bit positions within mask width when extending it.

Classification precedence is user override, bundled override, then built-in rules. An override replaces built-in classification; `ExpandCategories` adds parent bits for weapon, armor, concoction, smithing, food, and alchemy leaf categories. It does not infer every related leaf bit. For example, overriding SpellTome does not add Book, and Potion does not imply Restorative.

| Engine type | Built-in classification |
| --- | --- |
| `TESObjectMISC` | Crafting/Smelting/Tanning/Construction plus Smithing when present in recipe caches; otherwise no category |
| `IngredientItem` | Alchemy plus Reagent if food or a cooking input; otherwise Catalyst if a smithing input; otherwise Ingredient |
| `AlchemyItem` food | Food plus RawFood when raw keyword or cooking cache matches, otherwise CookedFood |
| Other `AlchemyItem` | Concoction plus Potion/Poison; adds Restorative if any effect matches health/magicka/stamina restoration |
| Armor | Armor plus Jewelry for non-Head-slot jewelry-keyword records or accessories excluding helmets, chestpieces, boots, gauntlets, and shields; otherwise Clothing/HeavyArmor/LightArmor |
| Weapon | Weapon plus OneHand, TwoHand, Archery, or Staff according to weapon type |
| Book | Note scrolls become Scroll; other books become Book and spell-teaching books also SpellTome |
| Native spell scroll | Scroll |
| Soul gem | Soulgem plus EmptySoulgem/FilledSoulgem and optionally GrandSoulgem by maximum capacity |
| Key | Keys; checked before the miscellaneous-item branch because `TESKey` derives from `TESObjectMISC` |
| Other types | No built-in category |

Ammunition has no explicit built-in branch. Gemstone and Treasure rely on overrides rather than generic misc-item rules. A grand-capacity gem need not contain a grand soul to match GrandSoulgem.

`Utility::CacheTemperRecipes` scans loaded constructible objects once at data load. Despite its name, it gathers recipe input FormIDs from forge, smelting, tanning, carpenter/building, and cooking keywords. Construction also accepts bench editor IDs containing `BYOHBuilding` or `BYOHHouse`. Mods' loaded recipes affect classification. `CookingMap` is declared but not populated or consumed in current code; `RawFoodMap` is the cooking-input cache actually used.

## Redirect persistence

[Serialization.h](../src/Serialization.h) sets plugin ID `'AVLS'`, record type `'RDIR'`, and version 1. [Serialization.cpp](../src/Serialization.cpp) chooses the storage mode using the current GlobalRedirect setting.

| Mode | Save | Load/revert |
| --- | --- | --- |
| GlobalRedirect enabled, default | Write static mappings to global INI and all mappings to the SKSE record | Load global INI, then restore only dynamic sources from the save; revert reloads only global mappings |
| GlobalRedirect disabled | Write SKSE record | Load clears mappings, reads records, resolves saved FormIDs; revert clears mappings |

The per-save record contains a 32-bit entry count followed by pairs of source and destination FormIDs. Load checks record type/version and truncation, caps count to record capacity, resolves both IDs through SKSE, and requires a reference destination. A source may be unloaded; an already loaded non-reference source is rejected. Preserve these checks and plan migration before changing the format/version.

Global mode uses `[Redirects]` entries with stable plugin-local identifiers. Example syntax:

```ini
[Redirects]
ExampleHouse.esp|0x123 = ArcaneVaults-LinkedStorage.esp|0xD95
```

This is illustrative, not a real source reference. `MakeFormIdentifier` refuses dynamic forms and forms without a file identity. Loading requires fully consumed hexadecimal IDs, a plugin-resolved source ID, and a reference destination. Source references may be unloaded. Assignment and global loading cache stable identifiers so subsequent saves do not erase unloaded mappings. Saving replaces the Redirects section while preserving other sections. Linked activator containers are blocked on assignment and when a restored source is next queried.

Assignment changes update memory immediately. Global redirects are written by the SKSE save callback, not by every assignment. Switching persistence mode in the settings UI does not migrate existing records or INI data. Plugin-backed mappings are global across saves. Dynamic placed or constructed references are saved with the character and never shared across games. Global-mode saves from earlier builds contain no dynamic redirect snapshot; lost assignments must be made again once. Item inventories remain owned by the game save.

## Menu navigation

Main-vault pages retain their source handle and a callback to rebuild the originating page. Submenus append Back when that context exists, preserving their existing Exit/cancel index. Confirmations without Exit do not gain Back. Plain-container close callbacks queue a return after archive cleanup; explicit Exit clears the context and closes the source.

Direct bound-container activation clears navigation before running its action, so it shows no contextual Back. Assignment and pre-load/new-game handling also clear navigation. The stored callback resolves a handle rather than retaining a raw source pointer.

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
| Keys | `0xDC5` | Vault | `KeysMenu` |

## Ignore picker

The appended hidden `Container::Ignore` uses reference `0xDD3` and base `0xDD2`. It is persistent, non-respawning, empty, and excluded from assignment choices. Sneaking is checked in the shared activation dispatcher for Master and Sort only. The close callback is target-specific; a session counter invalidates queued callbacks across game loads. Post-load and new-game tasks finish any residual picker inventory and return its contents. Failed returns stay in the persistent picker and prevent reopening it until recovery succeeds.

Sort first returns ignored records when Return Ignored Items is enabled. Its category transfers exclude any ignored copies left after a failed return. Disabling the option restores normal sorting. Player deposit helpers accept an explicit ignore flag; only Quick Transfer passes it, so manual deposits and crafting returns retain their existing policy.
