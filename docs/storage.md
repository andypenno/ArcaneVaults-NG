# Storage and persistence

The shared operations are in [Stores.cpp](../src/Stores.cpp); classification lives in [ItemClass.cpp](../src/ItemClass.cpp); [Utility.cpp](../src/Utility.cpp) binds enum values to external game references. Redirect persistence does not serialize item inventories. Skyrim owns the inventories of the companion references and saves their game state.

## Transfers and sorting

| Operation | Selection and protection |
| --- | --- |
| `PlayerToStore` | Positive counts matching a category; skips quest records and favourited physical copies; Quick Transfer protects equipped physical copies and ambiguous groups; optional retained count keeps that many per carried base item |
| `StoreToPlayer` | Positive counts matching a category, without the player's protection checks |
| `StoreToStore` | Positive counts matching a category; Sort protects favourites and configured ignores |
| `AllToStore` | `InventoryChanges::RemoveAllItems` outside Sort; Sort protects favourites and configured ignores; rejects identical source/destination enums |
| `AllToPlayer` | `InventoryChanges::RemoveAllItems` from the selected store |

The category helpers iterate inventory snapshots. `StoreToStore` and `StoreToPlayer` use `MoveItems` with a null extra-list argument. `PlayerToStore` uses `InventoryStacks` to select physical copies and passes their extra lists to `RemoveItem`. Both paths use `kStoreInContainer`, observe source counts and retry partial moves until the requested quantity transfers. A refused move stops immediately; no fixed 9999 cap is imposed. This includes non-gem crafting-loan returns. `PlayerToStore` subtracts its retained count before clamping a positive request; negative requests or reserves are rejected, and deposits never withdraw stored items. `StoreToPlayer` clamps requests to available counts. Its optional carried target limits withdrawals to the shortfall per base record; a target of zero withdraws nothing. Engine preservation of individual enchanted instances still requires runtime checks.

`PlayerToStore` skips bases already at or below Keep N before equipment and physical-stack reads. It reuses the initial stack read until the first move, then refreshes after each successful move that needs another iteration. Category withdrawals filter entries before copying them. Equipment capture filters out non-equipment before copying inventory entries.

Quick Transfer uses `PlayerEquipment::Run` to inspect ambiguous armor/weapon groups. Quest, fully favourite, ignored and disabled-category groups require no inspection. Inspection eligibility uses the same enabled category rules as the queued deposits. A single carried copy already proven worn by native flags or the standard GetEquipped condition also needs no inspection. Empty and fully protected equipment inventories finish conservatively without opening InventoryMenu. Unprotected or uncertain copies retain fresh UI inspection, including duplicate bases. An existing item menu receives conservative protection. It waits for the originating message box to close, opens the registered InventoryMenu through `UIMessageQueue`, reads standard equipState/isEquipped fields, and closes that menu before running transfers. Inspection polls until candidate rows have matching physical identities, counts and valid equipment fields within the shared acquisition deadline. A group reported equipped by GetEquipped also needs an identified equipped row. One recovery refresh is allowed after 750 ms of menu ownership; opening delays never extend the acquisition deadline. Missing or malformed groups remain protected at expiry. Equipment reads reject non-object row values before accessing their fields. Skyrim owns the menu, input contexts and control restoration. The plugin never invokes the native menu factory or ProcessMessage directly and never resets control flags. Completion callbacks run only after the inspection menu closes. Arcane Vault returns directly to its message box without requesting another physical opening animation. Assigned Quick Transfer and the hotkey share the same inspection path.

Equipment capture and post-menu validation use `InventoryStacks::ReadPart` in bounded steps. Each step reads fresh per-base entry data and retains offsets, primitive stack identities and counts rather than native iterators. This is not an atomic snapshot; validation and each deposit recheck the completed identities. UI inspection indexes captured pointers/unique IDs and parses large row lists across frames. A resumed grouped row rechecks its owner, count and equipment markers. Player equip events invalidate changed base groups before validation or deposit. Item-specific physical reads and count checks use CommonLib's filtered inventory APIs, so unrelated entry data is not copied on every transfer check. Counts and physical stacks are still refreshed after each move. Player deposits obtain fresh entry data per base form and recheck quest, favourite and native worn protections during partial transfers.

Only armor/weapon groups enter the equipment snapshot; unrelated menu rows do not participate. Physical counts and extra-list identities are captured by value on the game thread before opening InventoryMenu. The UI callback reads only menu rows and matches those stored values through pointer identity or unambiguous ExtraUniqueID pairs; it does not query or initialise the player inventory. Captured pointers are compared as identities, never dereferenced after crossing into the UI callback. Row owner, type and counts must match. After menu closure, physical pointers, counts, unique IDs and native worn flags must still match fresh inventory before the captured equipment selection is used. Changed groups receive conservative protection. Missing/malformed rows protect the whole armor/weapon base; a positive GetEquipped/native worn result without an identified worn row also protects the whole base. An equipped row grouping indistinguishable copies protects the entire group. Clearly unworn matching spares can transfer. Native ExtraWorn/ExtraWornLeft remain protected. Quest/favourite records, configured ignores and current ammunition retain their protections.

An already open item menu is left untouched and equipment receives conservative protection. Inspection failure falls back to conservative transfers. Requests serialize Quick Transfer operations and use bounded delayed polling rather than draining the global UI queue. Waiting for the originating message box, opening and reading share a one-second acquisition deadline. The first chunked row pass taking over 100 ms grants one additional acquisition budget after that finite pass. Native closure has its own one-second recovery deadline; it never forces control flags or transfers before Hide completes. Opening/reading timeout queues normal Hide; normal Hide is retried while the request owns the menu. Closing timeout cancels the transfer and reveals the ordinary menu so it can be exited. Pre-load/new-game cancels work and queues Hide for the owned inspection menu, including a pending Show. No inventory transfer runs from a stale request. The user verified the managed lifecycle and worn/spare ring behavior in Skyrim. The row-index and filtered-lookup optimizations still need game testing.

Outside the scoped Quick Transfer snapshot, player deposits use native worn flags and the standard GetEquipped condition to protect whole equipped base records. Manual vault actions and crafting returns therefore still retain matching spares when equipped copies cannot be identified safely.

Quick Transfer skips physical revalidation when there is no equipment snapshot. Archive and player count listings retain owned count maps and consume bounded ranges between frames. Populated archives recover through verified per-item moves. Soul-gem recovery/deposit actions select one base and resume from fresh state after a successful move; retained explicit gems stay carried rather than being parked in a buffer across frames. Bulk helpers remain synchronous outside Quick Transfer.

Player transfers re-read physical stacks after each removal. When explicit equipped copies remain protected, bare copies receive game-heap extra lists in signed-16-bit chunks so null-list removal cannot choose the worn copy. Failed allocation or transfer leaves remaining copies on the player; malformed counts and duplicate extra-list pointers leave that record untouched. The shared Materialize helper also supplies extra lists for archive origin markers.


`SortItems` consolidates book/note archives and old note storage, returns favourited records, returns ignored records when configured, recovers physical soul gems, then drains Sort in this order: Personal, Gear, Gold, Ammunition, Keys, Smithing, Food, Alchemy, Scroll, Note, Book, Treasure, Armor, Weapon, Concoction. Each pass sees the remaining inventory. An item with multiple category bits goes to the first applicable store; a final AllToStore pass moves every remaining item into Junk. The Alchemy pass selects the parent bit and includes Ingredients, Reagents, and Catalysts.

`ItemCategory::Ignore` is appended without changing older category ordinals. It overrides other category bits and native soul-gem classification. Sort returns these records regardless of Return Ignored Items and excludes failed returns from category passes, soul-gem recovery and the Junk fallback. Quick Transfer and material-loan returns leave them carried. Junk and soul-gem loan cleanup also preserve them. The separate ignore list and its Sort toggle retain their existing rules.

Sawn Logs have a bundled Ignore override. `RecoverSawnLogs` resolves HearthFires.esm local 0x300E and transfers existing non-quest stock from Smithing, Construction, Crafting, Smelting, Tanning, Gemstone, Sort and Junk using verified physical moves. It runs on the game thread after loading a save and before a crafting loan. Each move rereads stock; refusal stops that source and preserves the remainder. Missing forms/containers are skipped, repeated recovery does not duplicate stock, and a user classification replacing Ignore disables recovery. It never grants replacement logs or changes Hearthfire globals. Skyrim still controls their hidden display and construction behaviour.

Opening Sort captures favourite physical copies using native ExtraHotkey data and the dedicated AV_SortFavorite keyword at 0xDF0 before deposit can clear their favourite metadata. Closing Sort returns marked/favourited copies and restores their favourite state; ordinary copies sharing their base can sort normally. The notification reports actual returns. Return Ignored Items does not disable favourite protection. Failed returns remain in Sort, excluded from category transfers, soul-gem recovery and Junk. Their captured identities survive reopening while items remain in Sort; loading a save or starting a game clears the transient capture.

`OffloadItems` independently checks configured leaf categories and moves matching player items to parent stores. Quick Transfer queues ordered category and per-base actions, retaining only base forms and equipment identities between frames. Each resumed equipment deposit compares fresh physical identities, protects changed groups, and refreshes expected identities after successful moves. Shared helpers remain synchronous outside the scoped Quick Transfer batch. Load/reset discards pending actions and suppresses stale confirmation/menu callbacks. Yielding permits rendering but adds scheduling time; it does not shorten an individual native call. See [configuration.md](configuration.md) for defaults. Master is a menu entry point; Sort is the sorting inbox; Personal opens directly for manual storage and receives items explicitly classified as Personal. All main vaults, including Personal, Junk, Trade and Gear, appear in the scrolling Open Vaults list. Junk is independent storage for the final Sort remainder, including items deliberately skipped by other passes. Quick Transfer never sweeps unmatched player inventory into Junk.

A Quick Transfer assignment runs `OffloadItems` and returns to gameplay without opening the assigned container or reopening Arcane Vault. Quick Transfer uses appended enum value `Container::QuickTransfer`, non-respawning base `0xDEE` and persistent reference `0xDEF`. It is a Special destination, excluded from vault/archive browsing, crafting loans and archive gathering. Assignments use the existing reference-based global/per-save persistence. Sneaking opens the ignore picker. Normal activation retains every shared Quick Transfer protection and quantity setting.

## Vaults and archives

Most archive actions temporarily move matching items from their parent vault into an archive reference, activate it, and return its entire inventory to the parent on close. The menu may then return to the parent message box or close the source animation. Archives are real game inventories, not filtered UI views. New items deposited in an archive also return to its parent.

| Parent | Archives |
| --- | --- |
| Smithing | Crafting, Smelting, Tanning, Construction, Gemstone |
| Alchemy | Reagent, labeled Spice in storage UI |
| Concoction | Potion, Poison, Restorative, HealthPotions, MagickaPotions, StaminaPotions |
| Food | CookedFood, RawFood |
| Armor | Clothing, HeavyArmor, LightArmor, Jewelry |
| Weapon | Archery, OneHand, TwoHand, Staff |

Direct Archery archive access pools bows/crossbows from Weapon and arrows/bolts from Ammunition. Closing returns ammunition to its own vault before returning the remainder to Weapon. Failed ammunition returns leave the archive contents in place for a later direct visit. The Weapon menu and its Archery shortcut retain their existing weapon-only behavior.

Parent menus consolidate their own child archives; the scrolling vault browser invokes those registered menu actions. The Armor/Weapon Unclassified actions drain children, separate recognized types into archives, open the parent with the remainder, then reunite them on close.

Alchemy Transfer All selects the Alchemy parent category, including Ingredients, Reagents, and Catalysts, and preserves quest, favourited, and worn entries.

Alchemy Keep N deposits only excess matching the full Alchemy category, and Take Up To N withdraws only its shortfall per base record. Both use Alchemy Keep Amount in Quantities, default 1. Store All still deposits all eligible Alchemy items. Scroll Keep N and Take Up To N use Scroll Keep Amount in Quantities, default 3. Keep N deposits only excess per base record; Take Up To N withdraws only the shortfall. Neither action empties the vault first. Zero deposits all eligible copies through Keep N and withdraws nothing through Take Up To N.

Ammunition is an independent vault for arrows and bolts. Its menu offers Keep N, Store All, Take Up To N, Take All, Open, and Exit. N comes from Ammunition Keep Amount in Quantities, default 100. Keep Selected Ammunition in Options selects the reserve policy below. Take All returns the entire inventory. Ammunition appears in the scrolling vault browser and in the vault binding list.

Keys is an independent vault. Its menu offers Keep One, Store All, Take Up To 1, Take All, Open, and Exit. Keep One retains one of each carried key record and deposits only duplicates. Take Up To 1 withdraws only missing key records and leaves carried duplicates unchanged. Take All returns the entire vault inventory, including manual deposits. Keys also appears in the scrolling vault browser and the vault binding list. Quick Transfer defaults are described in [configuration.md](configuration.md).

Books offers Take Up To 1 in place of Transfer One Copy. It withdraws only missing book records, without emptying the vault or depositing carried duplicates. Store All, Gather Spell Tomes, Open, and Exit retain their existing actions. Archives opens Spell Tomes and Skill Books.

Valuables is a composite archive reached through Bind Archive. Its menu offers Open, Exit, Keep N Septims, Store All Septims, and Take All Septims. Exit is the cancel action. Treasure opens directly without a Valuables submenu. The Septim actions deposit into or retrieve from Treasure; Keep N uses Gold Keep Amount in Quantities. Take All Septims selects Gold only and handles counts above 9999.

Open temporarily gathers Gold from Treasure, Gemstone and PreciousIngot from Smithing, and Jewelry from Armor. Closing returns gems and precious ingots to Smithing, jewelry to Armor, and Gold plus unrelated manual deposits to Treasure. Materials therefore remain available to the existing Smithing crafting loan. The Gemstone and Jewelry archives keep their existing parents. Opening the Valuables menu also returns any contents left in its reference, including contents persisted while the archive was open. All three parent destinations must exist before gathering or returning.

Trade is manual storage. Sort and Quick Transfer never deposit into it. Its menu is Open, Exit, Take All, Sell All, with Exit as the cancel button. Sell All quotes the total eligible copy count and Septim payout, then asks for confirmation and reminds the user that favourited, equipped and quest items, and Septims, are excluded. The no-eligible-items message states those exclusions explicitly. Cancelling keeps the items. Take All retrieves the pile for manual merchant trading.

[Trade.cpp](../src/Trade.cpp) prices each explicit extra-data stack through Skyrim's InventoryEntryData::GetValue, then prices the bare remainder separately. It passes the matching extra list to RemoveItem. Quest, favorite, worn, and Septim entries are excluded. Malformed counts or repeated extra lists leave that base record untouched. Payout is floor(sum(unit inventory value * copies actually removed) * SalePercentage / 100), rounded once for the sale. Speech, perks, and barter bonuses do not affect it; selling grants no Speech experience.

Confirmation rechecks stack identity, counts, prices, and the configured percentage. Changed quotes cancel without removing anything. Sale totals use signed 64-bit arithmetic with no mod-defined item-count or sale-value cap. Skyrim's inventory counts are signed 32-bit, so a payout exceeding the player's remaining Septim capacity cancels before removing anything and reports an engine-capacity error separately. Explicit stacks move before bare copies; a partial or failed removal skips the rest of that base record. Only the observed inventory count reduction receives payment. Reusing an old confirmation cannot pay twice. Engine valuation and removal still need in-game checks for enchanted and tempered items.

## Soul gem storage

[Soulgems.cpp](../src/Soulgems.cpp) handles physical `TESSoulGem` records independently of category overrides. Generic category transfers skip them. Quick Transfer deposits all eligible filled gems and retains up to the configured number of empties per base record. It never withdraws to refill a reserve. The bank menu offers Open Vault, Take Up To N empty gems, Keep N Empty, Store All, Filled Soulgems, Empty Soulgems, contextual Back, and Exit. Both soul gem archives open directly. Both archives are bindable near an enchanter and return their inventories to the existing bank on close.

Take Up To N withdraws only the shortfall below the configured empty reserve per base record. Existing filled copies do not count toward that reserve; stacks already above the target stay unchanged. Zero withdraws nothing. Malformed carried stacks prevent top-up for that record. Top-up consolidates the archives afterwards.

Stack classification uses explicit `ExtraSoul` data, including an explicit zero, before the base record's soul. Each extra list supplies its own count; the remainder uses base-record state. Duplicate extra-list pointers, invalid soul levels, or counts exceeding the inventory total leave that record untouched. Moves preserve base records and pass the selected extra list to Skyrim. Splitting moves explicit stacks first so null extra-list transfers cannot select another state. Deposits temporarily park retained explicit empties when the base record is filled, then return them to the player.

Quest, favorited, and equipped inventory entries are skipped. Vanilla Azura's Star and Black Star, plus records linked to them, are excluded from automatic transfers. Flawed Varla Stones and mod-added native soul gems use the same state and metadata rules. No soul-trap, filling, consumption, or gem-conversion logic is replaced.

Bank access, Quick Transfer, Sort, and gem loans recover misplaced soul gems from Smithing, its Crafting/Smelting/Construction/Tanning/Gemstone archives, and Sort. Existing Soulgem storage IDs are preserved. Both new archives consolidate before bank operations and loans, including contents saved while an archive was open.

## Classification

[ItemClass.h](../src/ItemClass.h) defines separate `Container`, `ItemCategory`, `ContainerGroup`, and `BenchType` enums. `CategoryMask` is a 64-bit integer; a category's underlying value chooses its bit and None maps to zero. Keep bit positions within mask width when extending it.

Physical soul gems always route through the dedicated soul gem transfer path. Other items retain user override, bundled override, then built-in precedence. An override replaces built-in classification; `ExpandCategories` adds parent bits for weapon, armor, concoction, smithing, food, alchemy, book, and note leaf categories. SpellTome and SkillBook imply Book; Recipe and Map imply Note; Lockpick and Instrument imply Gear. It does not infer every related leaf bit; Potion does not imply Restorative.

| Engine type | Built-in classification |
| --- | --- |
| `TESObjectMISC` | Crafting/Smelting/Tanning/Construction plus Smithing when present in recipe caches; otherwise no category |
| `IngredientItem` | Alchemy plus Reagent if food or a cooking input; otherwise Catalyst if a smithing input; otherwise Ingredient |
| `AlchemyItem` food | Food plus RawFood when raw keyword or cooking cache matches, otherwise CookedFood |
| Other `AlchemyItem` | Concoction plus Potion/Poison; adds Restorative if any effect matches health/magicka/stamina restoration |
| Armor | Armor plus Jewelry when the Head slot is absent and either the jewelry keyword or CommonLib accessory detection matches. Accessory detection also excludes helmets, chestpieces, boots, gauntlets, and shields; otherwise Clothing/HeavyArmor/LightArmor |
| Weapon | Weapon plus OneHand, TwoHand, Archery, or Staff according to weapon type |
| Native spell scroll | Scroll through the engine ScrollItem type; explicit overrides still win |
| Book | Spell-teaching forms become Book/SpellTome; skill-teaching forms become Book/SkillBook; recipe-keyword forms become Note/Recipe; forms with Note/Scroll type or "note" in their mesh path become Note; remaining forms become Book |
| Soul gem | Soulgem before miscellaneous items and overrides; filled/empty state belongs to inventory stacks |
| Gold | `TESForm::IsGold()` identifies Septims; its separate Gold category does not expand to Treasure |
| Gold/silver ingots | PreciousIngot and Smithing, plus the existing recipe-derived categories |
| Ammunition | Ammunition; `TESAmmo` covers arrows and bolts, after override precedence |
| Key | Keys; checked before the miscellaneous-item branch because `TESKey` derives from `TESObjectMISC` |
| Other types | No built-in category |

The vanilla precious ingot IDs are Gold `0x0005AD9E` and Silver `0x0005ACE3`, verified against [UESP](https://en.uesp.net/wiki/Skyrim:Ores_and_Ingots). Gemstones retain the bundled Gemstone overrides. Mods can classify additional records through Gemstone or PreciousIngot overrides.

Rare Curios Welkynd Stones use the bundled `ccBGSSSE037-Curios.esl|0x000800 = Treasure` override. The identity is documented by the [Rare Curios/The Cause patch author](https://www.nexusmods.com/skyrimspecialedition/mods/189779). Other plugins' stone records are not inferred from display names.

Native `RE::ScrollItem` records, including mod-added spell scrolls, classify as Scroll without per-form overrides. Dragonborn's throwable spider scrolls use the same path; a [published KID configuration and runtime log](https://www.nexusmods.com/skyrimspecialedition/mods/55728?comment_id=110378683&tab=posts) identifies `DLC2ExpSpider` items through its native Scroll filter. Note-style BOOK records belong to Notes; native SCRL records remain Scroll. Gemstone and Treasure rely on overrides rather than generic misc-item rules. Legacy EmptySoulgem/FilledSoulgem/GrandSoulgem enum values remain reserved; the soul gem module evaluates physical state.

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

Vault and archive browsers retain their source handle and a callback to rebuild the originating list. Submenus include Back when that context exists, with Exit last and cancellation mapped to Exit. Confirmations without Exit do not gain Back. Plain-container close callbacks queue a return after archive cleanup; explicit Exit clears the context and closes the source.

Arcane Vault's Open Vaults and Open Archives actions share the scrolling SkyUILib browser. Entries are sorted by display name and selecting one invokes its registered storage action; contextual Back returns to the originating list. Back or cancellation in either list returns to Arcane Vault, and Exit closes the source. Browse choices always carry actions and never create redirects.

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
| Notes | `0xDD5` | Vault | `NotesMenu` |
| SpellTomes | `0xDD7` | Archive | `OpenBookArchive` from Book |
| SkillBooks | `0xDD9` | Archive | `OpenBookArchive` from Book |
| Recipes | `0xDDB` | Archive | `OpenBookArchive` from Notes |
| Maps | `0xDDD` | Archive | `OpenBookArchive` from Notes |
| StolenItems | `0xDDF` | Archive | `StolenItemsMenu` |
| Scroll | `0xD9B` | Vault | `ScrollMenu` |
| Treasure | `0xDAD` | Vault | `TreasureMenu` |
| Personal | `0xDA1` | Vault | `PersonalMenu` |
| Gear | `0xDE2` | Vault | `GearMenu` |
| Instruments | `0xDE4` | Archive | `OpenBookArchive` from Gear |
| HealthPotions | `0xDE6` | Archive | `OpenBookArchive` from Concoction |
| MagickaPotions | `0xDE8` | Archive | `OpenBookArchive` from Concoction |
| StaminaPotions | `0xDEA` | Archive | `OpenBookArchive` from Concoction |
| EnchantedItems | `0xDEC` | Archive | `EnchantedItemsMenu` |
| Junk | `0xDCF` | Vault | `JunkMenu` |
| Trade | `0xDD1` | Vault | `TradeMenu` |
| Keys | `0xDC5` | Vault | `KeysMenu` |
| Ammunition | `0xDC7` | Vault | `AmmunitionMenu` |
| FilledSoulgems | `0xDCB` | Archive | `FilledSoulgemsMenu` |
| EmptySoulgems | `0xDCD` | Archive | `EmptySoulgemsMenu` |
| Valuables | `0xDC9` | Archive | `ValuablesMenu` |

## Gear and Instruments

Gear receives ordinary lockpicks and native carryable lights, including mod-added torches. Explicit overrides retain priority. Instruments use bundled overrides for Skyrim's flutes `0xDABA7` and `0x105177`, lute `0xDABAB`, and drum `0xDABA9`, documented in [UESP's miscellaneous items](https://en.uesp.net/wiki/Skyrim:Miscellaneous_Items). Quest copies share those records and retain normal player-transfer protections. Camping and other equipment can learn a Gear override; the Instruments archive can learn Instrument, which implies Gear.

The Gear menu is Open, Exit, contextual Back, Keep N Lockpicks, Take Up To N Lockpicks. Exit cancels. Back appears only when entered through another menu. Amount actions affect Lockpick records only. Keep N deposits excess; Take Up To N fills the carried shortfall from available stock. Zero deposits all eligible lockpicks and withdraws none. Manual actions retain normal player protections but disregard Quick Transfer ignores.

The Gear Quick Transfer checkbox defaults off. When enabled, lockpicks use Lockpick Keep Amount and other Gear items deposit without a reserve. Quick Transfer preserves quest, favourite, worn, standard-equipped and ignored records. Sort deposits all eligible Gear without a carried reserve. The Skeleton Key retains its existing classification.

Instruments has no Gear-menu shortcut. Open Archives and direct archive assignments gather Instrument records from Gear, then return the archive inventory to Gear on close. Gear opening, Sort and Quick Transfer also return residual archive items to Gear. The persistent, non-respawning ESP bases are `0xDE1` and `0xDE3`; their references are listed above.

## Ignore picker

The appended hidden `Container::Ignore` uses reference `0xDD3` and base `0xDD2`. It is persistent, non-respawning, empty, and excluded from assignment choices. Sneaking is checked in the shared activation dispatcher for Master, Sort and Quick Transfer. The close callback is target-specific; a session counter invalidates queued callbacks across game loads. Post-load and new-game tasks finish any residual picker inventory and return its contents. Failed returns stay in the persistent picker and prevent reopening it until recovery succeeds.

Sort first returns ignored records when Return Ignored Items is enabled. Its category transfers, soul-gem recovery, and Junk fallback exclude any ignored copies left after a failed return. Disabling the option restores normal sorting. Player deposit helpers accept an explicit ignore flag; only Quick Transfer passes it, so manual deposits and crafting returns retain their existing policy.

## Junk crafting loans

Every recognized crafting bench also borrows eligible Junk items when Crafting Loan is enabled. The Junk session starts after normal vault loans and records carried counts plus actual borrowed counts per base record. On exit it returns up to the borrowed amount above the captured carried count to Junk, before soul-gem and category returns. Consumed items are not recreated; partial engine moves use the shared retry helper. Quest, favourited, worn, and standard GetEquipped-protected player entries are retained. Quick Transfer ignores do not suppress this explicit loan.

Loan counts use runtime form IDs only during the active session. Load/reset discards bookkeeping without transferring saved inventory, as with existing crafting loans. A transformed item with a different base record stays on the player. The ledger preserves counts, not identities of copies sharing a base record; engine removal selects the returned copies and preserves their extra data. Carpenter bench detection is unchanged.

## Books and Notes archives

Books has direct Spell Tomes and Skill Books archive actions. Notes has direct Recipes and Maps archive actions. Each archive is also directly assignable. Opening gathers matching items from the parent. Closing returns all contents to that parent, including manually added items. Books archive visits return to Books; Notes archive visits return to Notes. A direct archive assignment closes the source. Parent menus retain contextual Back to the originating Arcane Vault page. Both parents offer Store All, Take Up To 1, Open, and Exit.

`ConsolidateBooks` returns child contents to parents and migrates Note/Book records from legacy Scroll storage, plus Note records from Books. It runs before Books/Notes/archive menus, Sort, and Quick Transfer. Native scrolls remain in Scroll. If a source disappears before the close callback runs, the next consolidation recovers the archive contents. Player protections and the ignore list still apply through their existing transfer paths.

Skill-book identities are captured from loaded native book records during `kDataLoaded`, before saved read state is applied. Skyrim consumes skill-teaching data when a book is read, so classification also checks that cache. It survives save loads and new games, requires no save record, and includes mod-added native skill books. Explicit overrides still win; spell tomes retain priority.

Spell/skill-teaching flags and cached skill-book identity take precedence over the recipe keyword and note detection. Ordinary notes match either the Note/Scroll type or a mesh path containing "note", ignoring case, as SKSE does for SkyUI. Special Edition no longer reliably uses the type field. This also migrates matching notes already stored in Books during consolidation. Recipes use `VendorItemRecipe`; no translated item names are matched. Maps use bundled plugin-local overrides for vanilla, Dragonborn and Fishing records. Unmarked mod-added maps use their ordinary Book/Note classification until an override assigns Map. The displayed name is Maps Vault; the category is Map, the destination is Maps and the translation key is Vault.Maps. The retired category spelling is not accepted. Missing optional plugins are skipped by the normal override loader, and user overrides take precedence.

The [published in-game record extraction](https://www.nexusmods.com/skyrimspecialedition/mods/32763?tab=docs) identifies the vanilla and Dragonborn records. UESP's linked map entries identify the Fishing records, supplied by [ccBGSSSE001-Fish.esm](https://en.uesp.net/wiki/Skyrim:Fishing):

| Map | Plugin | Local ID |
| --- | --- | --- |
| I | Skyrim.esm | `0x0EF07A` |
| II | Skyrim.esm | `0x0F33CE` |
| III | Skyrim.esm | `0x0F33CF` |
| IV | Skyrim.esm | `0x0F33D1` |
| V | Skyrim.esm | `0x0F33D4` |
| VI | Skyrim.esm | `0x0F33D0` |
| VII | Skyrim.esm | `0x0F33D5` |
| VIII | Skyrim.esm | `0x0F33D3` |
| IX | Skyrim.esm | `0x0F33CD` |
| X | Skyrim.esm | `0x0F33E0` |
| Fort Neugrad | Skyrim.esm | `0x0F33D2` |
| Velehk Sain | Skyrim.esm | `0x0DDEFB` |
| Deathbrand | Dragonborn.esm | `0x02BAAE` |
| [Fishing: Eastmarch](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_Eastmarch) | ccBGSSSE001-Fish.esm | `0x070CCC` |
| [Fishing: Falkreath](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_Falkreath) | ccBGSSSE001-Fish.esm | `0x070CCD` |
| [Fishing: Haafingar](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_Haafingar) | ccBGSSSE001-Fish.esm | `0x070CCE` |
| [Fishing: Hjaalmarch](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_Hjaalmarch) | ccBGSSSE001-Fish.esm | `0x070CCF` |
| [Fishing: The Pale](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_The_Pale) | ccBGSSSE001-Fish.esm | `0x070CD0` |
| [Fishing: The Reach](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_The_Reach) | ccBGSSSE001-Fish.esm | `0x070CD1` |
| [Fishing: The Rift](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_The_Rift) | ccBGSSSE001-Fish.esm | `0x070CD2` |
| [Fishing: Whiterun](https://en.uesp.net/wiki/Skyrim:Fishing_Map_-_Whiterun) | ccBGSSSE001-Fish.esm | `0x070CD3` |

## Ammunition reserve modes

Keep Selected Ammunition defaults off. Selection is the union of current ammunition from `GetCurrentAmmo`, native worn/favourite inventory flags, and the standard GetEquipped condition. It is captured once at the beginning of an action. Being equipped and favourited gives one reserve per base record; several selected records each have their own reserve. No item-name or mod-specific rules are used.

| Action | Toggle off | Toggle on |
| --- | --- | --- |
| Quick Transfer or Keep N | Leave selected stacks untouched; keep up to N of every other eligible type | Keep up to N of selected types; deposit every other eligible type completely |
| Take Up To N | Top up each stored ammunition type to N carried copies | Top up only selected types to N carried copies |
| No selection | Deposits keep N per type; withdrawal tops up all stored types | Deposit every eligible type; withdraw nothing |
| N = 0 | Deposit unselected types completely; keep selected stacks; withdraw nothing | Deposit all eligible types, including selected; withdraw nothing |

Quest items remain protected from player deposits. Quick Transfer always exempts ignored records entirely. Manual Keep N and Take Up To N disregard that ignore list. Neither deposit action withdraws to fill a reserve; withdrawal counts carried copies, takes only the shortfall and available stock, and never deposits excess. The engine may clear equipped/favourite state when the last copy is deposited at N = 0; the mod does not restore selection by recreating items.

Store All is independent of the toggle and preserves quest, favourite, native worn, standard GetEquipped, and current-ammunition protections. Take All and Open retain their existing behavior. Sort moves deposited ammunition without a reserve, subject to Return Ignored Items. Shared transfers still preserve other item categories' equipment/favourite protections.

## Broad category overrides

Override parsing and formatting accept parent categories and Restorative. Parent categories do not expand into children. Quick Transfer deposits a parent-only override when any checkbox in that family is enabled; it excludes named child bits so a disabled subtype remains protected. These transfers use the shared quest, favourite, equipment, and ignore checks. Manual parent vault transfers and Sort already match the parent bit. [configuration.md](configuration.md#learning-from-deposits) describes the opt-in deposit workflow.

## Stolen Items archive

[StolenItems.cpp](../src/StolenItems.cpp) gathers ownership-bearing physical stacks from registered main vaults, including Personal and Junk, and excludes Sort, Ignore, Trade, and archives. It uses `InventoryEntryData::IsOwnedBy(player, stackOwner, true)` for each extra list. The aggregate base-record owner does not select clean copies. Implicit copies without an ownership extra are clean. Malformed counts or duplicate extra-list pointers are skipped without moving the affected record.

The companion adds container `0xDDE`, persistent reference `0xDDF`, and private keyword `AV_StolenOrigin` at `0xDE0`. Gathering adds a keyword-qualified `ExtraLinkedRef` to the source vault on each selected stack. The design relies on native extra-data comparison distinguishing source links and native inventory saves remapping them. The regression model covers these contracts; actual engine merge/save behavior remains unverified. No new SKSE co-save record is added. Return removes only the private link, preserving other linked references and item metadata. Withdrawn copies keep their ownership and lose the private marker through the container event handler. Untagged manual deposits return to the player on close.

Each explicit transfer checks observed source/destination count changes and re-reads stacks after progress. It handles partial engine removals without keeping destroyed list pointers. Destination count capacity is checked before transfer. A refused move, an unresolved marked source, or inconsistent archive counts leaves remaining contents for recovery. Opening the archive allows withdrawal of retained contents even after a recovery failure. New-game/load resets invalidate queued withdrawal cleanup and clearing confirmations; post-load/new-game tasks recover archive contents and remove stale markers from vault/player inventories.

Arcane Vault has an Archives entry containing Stolen Items. Binding the archive directly also works. With the default-off clearing option disabled, activation opens the gathered inventory directly. Enabled activation shows Open, Exit, and Remove All Stolen Tags. Contextual Back appears before the clearing action. Clearing requires confirmation, defaults to No, rechecks the setting and game generation, gathers current stolen copies, removes only `ExtraOwnership`, then returns them to their sources. Successful clearing leaves the next opening empty unless new stolen copies arrive. Transfer failures preserve remaining inventory and show a recovery message.

`check_stolen.py` exercises the actual selector, transfer/recovery code, and archive menus. Its save/load check models native link persistence and load-order remapping. Native extra-data comparison and save handling still require in-game verification.

## Attribute potion archives

Health Potions, Magicka Potions and Stamina Potions gather their matching categories from Concoction. `ClassifyPotionEffects` reads loaded native effects rather than matching vanilla potion IDs. Automatic classification excludes food, poisons, hostile or detrimental effects, and nonpositive magnitudes. ValueModifier, PeakValueModifier and DualValueModifier effects select the corresponding Health, Magicka or Stamina category through the attribute, regeneration rate or regeneration multiplier actor value. Dual modifiers also consider the secondary attribute when its weight is positive. Script-only effects without this metadata need an explicit override.

HealthPotion, MagickaPotion and StaminaPotion imply Potion and Concoction. Explicit overrides retain priority. A potion affecting several attributes matches several archives; opening one moves the existing copies rather than duplicating them. `ConsolidatePotions` returns all six potion/poison archives to Concoction before opening a potion view or running Sort or Quick Transfer. Closing a new archive returns its remaining contents to Concoction. All three are available through Open Archives and direct assignment.

## Enchanted Items archive

`EnchantedItems.cpp` pools qualifying physical stacks from Weapon and Armor after consolidating their category archives. Armor includes clothing and jewelry. Each stack uses its ExtraEnchantment when present, otherwise the base item's enchantment. Plain copies sharing an enchanted copy's base record remain in their vault.

The filter uses Skyrim's default-object disallow-enchanting keyword on the item, effective enchantment and inherited base-enchantment chain. Known enchantments and player-applied enchantments remain eligible. Quest entries, staves, staff enchantments, blocked artifacts, cyclic enchantment chains and uncertain eligibility are excluded. Eligibility depends on loaded record metadata, not artifact names or mod-specific lists. Missing restriction metadata leaves items in their parent vault.

`InventoryStacks.cpp` shares stack validation, count checks, transfers and origin-marker cleanup with Stolen Items. Duplicate extra-list pointers or inconsistent counts reject the affected inventory entry. Implicit enchanted stacks receive live extra lists in signed-16-bit count chunks before moving. MarkOrigin allocates game-heap storage and invokes the SE/AE/VR engine constructor through Address Library; CommonLib declares but does not implement its C++ constructor. The separate `AV_EnchantedOrigin` keyword at `0xDED` records each stack's source without replacing ownership or enchantment data. Closing or post-load recovery returns marked items to their original vault; unmarked manual deposits return to the player. Withdrawn items lose only this archive's origin marker. Failed returns stay stored for recovery.

Enchanted Items is available through Open Archives and direct assignment. It has no new sale action or Quick Transfer category, and its mixed, per-copy filter cannot teach a base-record override.

Ordinary items explicitly classified as Soulgem route to the Soulgem vault through Sort and enabled Quick Transfer. They remain ordinary inventory items; soul states, empty-gem reserves and gem-specific loans apply only to native soul gems.

Explicit Junk overrides are routed before other Sort categories and have an independent Quick Transfer checkbox. Unclassified player inventory is never swept into Junk. Existing Junk crafting loans still return unused borrowed items to Junk.

Favourite selection uses per-copy ExtraHotkey metadata. Ambiguous aggregate favourites retain conservative base protection. The Sort marker survives transfers and save/load, and failed favourite returns stay protected in Sort. Ordinary same-base implicit copies are materialized before removal so native null-list selection cannot take the favourite.
