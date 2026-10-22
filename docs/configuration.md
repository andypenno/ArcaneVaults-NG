# Configuration and integrations

[Settings.h](../src/Settings.h) owns option defaults and paths. [Settings.cpp](../src/Settings.cpp) owns the keys, loading, and persistence. Prefix `GSC_` survives in member names and the destination menu's registration name; the installed plugin is named ArcaneVaults-NG.

## Runtime files

All paths below are relative to the game's working directory under `Data/SKSE/Plugins/ArcaneVault/`.

| File | Behavior |
| --- | --- |
| `ArcaneVaultSettings.ini` | General and Offload options; missing file is written with defaults |
| `ArcaneVaultOverrides.ini` | Bundled overrides, supplied by [ini/ArcaneVaultOverrides.ini](../ini/ArcaneVaultOverrides.ini) |
| `ArcaneVaultUserOverrides.ini` | User overrides edited by framework UI; takes precedence over bundled data |
| `ArcaneVaultRedirects.ini` | Global mappings; format and lifecycle in [storage.md](storage.md) |
| `ArcaneVaultIgnoredItems.ini` | Global ignore list with stable plugin-local identifiers under `[IgnoredItems]` |
| `ArcaneVaultTranslation.json` | Flat translation object, supplied by [ini/ArcaneVaultTranslation.json](../ini/ArcaneVaultTranslation.json) |

Settings initialization loads options, then bundled overrides, then user overrides. Missing keys get in-memory defaults and are added to the temporary INI object, but an existing settings file is only written by `SaveINI`. UI changes call `SaveINI`; no file watcher reloads changes while running. `AmmunitionKeepAmount`, `GoldKeepAmount`, and `SoulgemKeepAmount` use `from_chars` with full input and nonnegative validation; invalid or overflowing values fall back to 100, 5000, and 25 respectively. `SalePercentage` also requires fully consumed integer input, accepts 1..100, and falls back to 30 for invalid values. Other integer settings use `stoi` without a local exception handler. Most settings read/write return codes are not reported, unlike user-override and redirect save failures.

## Options

The `ForEachINIOption` helper shares one mapping between reads and writes.

| General key | Default | Meaning |
| --- | --- | --- |
| `GlobalRedirect` | true | Share static mappings through global INI; dynamic mappings always belong to the save |
| `AssignKeyCode` | -1 | Assignment input code; disabled by default |
| `QuickKeyCode` | -1 | Quick offload input code; disabled by default |
| `CraftingLoan` | false | Lend and return crafting materials |
| `AllCraftingMaterials` | false | With Crafting Loan enabled, lend Smithing, Food, Alchemy, eligible Junk and all eligible soul gems at every supported station |
| `AssignOnlyOwn` | true | Restrict binding according to ownership/exterior non-respawn rules |
| `AssignSpell` | true | Enable external assignment spell |
| `SortSpell` | true | Enable external sorting/offload spell |
| `AmmunitionKeepAmount` | 100 | Retain this many per carried arrow or bolt record; zero retains none |
| `KeepSelectedAmmunition` | false | Retain and top up only current, favourite, worn, or native-equipped ammunition records |
| `GoldKeepAmount` | 5000 | Retain this many carried Septims; zero deposits all eligible Gold |
| `SoulgemKeepAmount` | 25 | Retain this many empty soul gems per base record; filled gems have no reserve |
| `SalePercentage` | 30 | Trade pays this percentage of inventory item value; integer 1..100 |

In `[Offload]`, enabled defaults include Junk. Other enabled defaults are `Reagent`, `Catalyst`, `Ingredient`, `Crafting`, `Construction`, `Gemstone`, `Smelting`, `Tanning`, `RawFood`, `Soulgems`, `Ammunition`, `Gold`, `Keys`, and `KeysKeepOne`. Disabled defaults are `Clothing`, `HeavyArmor`, `LightArmor`, `Jewelry`, `Books`, `Scrolls`, `Spelltomes`, `Potion`, `Poison`, `CookedFood`, `Treasure`, `Archery`, `OneHand`, `TwoHand`, and `StaffHand`. Exact spelling matters, including `Spelltomes` and `StaffHand`.

Options exposes Sale Percentage, clamped to 1..100 and saved in General. Trade is manual storage and has no Quick Transfer toggle. The default 30% offers less than a new character's unboosted merchant sale.

Options exposes Ammunition Keep Amount as a nonnegative integer control. Quick Transfer only exposes an Ammunition enable checkbox under More. `[Offload] Ammunition=true` enables ammunition deposits using the same reserve as the vault Keep N action. Missing values default to enabled and 100. The amount applies per ammunition base record, not to the combined arrow/bolt count.

Options exposes Gold Keep Amount with the same nonnegative integer control as ammunition. Quick Transfer exposes only a Septims enable checkbox under More, persisted as `[Offload] Gold=true`. The reserve applies to Quick Transfer, its hotkey/spell, and Valuables' Keep N Septims action. Sorting Gold already in Sort moves the entire amount to Treasure. Gold has no Treasure category bit, so enabling the Treasure offload toggle cannot bypass the Gold reserve.

Quick Transfer exposes one Soulgem checkbox, persisted as `[Offload] Soulgems=true`. Options exposes Empty Soulgems Keep Amount, default 25. The retired `EmptySoulgem`, `FilledSoulgem`, and `GrandSoulgem` INI keys are ignored and existing files may retain them. Filled/empty classification is instance-based and is not controlled by overrides. The new policy defaults to enabled even when only old keys exist.

Quick Transfer shows Keys and Keep One under More. `Keys=true` enables key deposits through the menu, hotkey, and offload spell. `KeysKeepOne=true` deposits duplicates while retaining one per carried key record. Disabling Keep One deposits all eligible keys. Both default to true when missing from an existing settings file. Sort moves keys already deposited into its inbox to the Keys vault; it does not withdraw a copy to the player.

The Books Quick Transfer controls use a separate ImGui ID scope from their Books collapsing header. Their visible labels remain translated; the header and Books checkbox no longer share an ID.

The UI exposes assignment hotkey capture and most settings, plus per-category quick-transfer checkboxes. It has no QuickKeyCode capture control. [HelperFunctions.h](../include/HelperFunctions.h) converts engine codes to/from ImGui keys; keyboard uses engine scan codes, mouse uses 256 through 260, and gamepad uses 266 through 281. Input events trigger assignment/offload for keyboard and gamepad; the handler does not accept mouse even though conversion supports it. It also has no explicit gameplay/menu-state gate beyond singleton checks.

Configuration spells are looked up as local IDs `0xDC0` and `0xDC1` in the companion ESP. `ConfigurationSpells` reconciles player spells on post-load-game and on spell checkbox changes. The [Papyrus dispatcher](../scripts/Source/ArcaneSpells.psc) calls the same `OffloadItems` native as Quick Transfer, so the Keys settings also apply to that spell.

## Classification overrides

Override files use `[Overrides]`, plugin-local hexadecimal IDs, and comma-separated category names:

```ini
[Overrides]
Skyrim.esm|0x03AD5B = Reagent
Dragonborn.esm|0x017749 = Catalyst
```

These two entries are present in the bundled file. The accepted, case-sensitive names come from `categoryNames` in [ItemClass.h](../src/ItemClass.h). It is a leaf-category list, not the entire ItemCategory enum. Category text parsing trims spaces/tabs and warns on unknown names; a zero mask can suppress classification. Parent expansion happens during classification, not during file parsing.

The override loader resolves IDs to `TESBoundObject` forms and stores runtime FormIDs in memory. The override loader reuses the global redirect identifier parser. Malformed identifiers, partially consumed hex IDs, and unresolved or non-item records skip only that entry. Missing optional plugins do not stop later overrides from loading.

User edits replace one item's override. Save clears and rewrites only the Overrides section using stable file/local-ID identifiers, skips unstable forms, and preserves other sections. Deleting a user override reveals the bundled override or built-in classification. The UI accepts a full runtime FormID for lookup, while files store plugin-local identifiers. Its dropdown replaces the selection with one category; comma-separated files can represent multiple categories.

## Translation

[Translation.cpp](../src/Translation.cpp) reads a flat JSON object of string values at data load. Missing file/key yields `missing translation`; missing file is logged. JSON parsing and string conversion are not wrapped in exception handling, so malformed JSON or non-string values are not a supported fallback case. Existing `Vault.Restoritive` spelling is shared by source and data; preserve that key unless changing both.

`Utility::AddContainer` uses translations to set container base full names, which can affect references sharing that base. Valuables and Filled/Empty Soulgems use the Archive suffix; earlier destinations retain the Vault suffix. Some UI strings remain literal English, including `Search`, `Select destination`, Quick Transfer, and override errors. Translation changes must account for both message-box text and companion container naming.

## External APIs and assets

| Integration | Contract and optionality |
| --- | --- |
| SKSE/CommonLib/Address Library | Required engine/plugin APIs; generated plugin metadata declares Address Library version independence |
| `ArcaneVaults-LinkedStorage.esp` | Required storage references and configuration spells; source IDs listed in [storage.md](storage.md) |
| SkyUILib movie | Required for grouped destination selection; fixed ActionScript paths in [ContainerMenu.cpp](../src/ContainerMenu.cpp) |
| SKSE Menu Framework 3 | Optional configuration UI; `AVUI::Register` returns if its DLL is absent |
| QuickLoot IE | Optional integration; initializes at post-post-load and warns if API unavailable |
| External `ArcaneVaults` Papyrus script | Declares native `ContainerRedirect` and `OffloadItems`, both static, with no arguments or return value |

Framework wrappers come from its submodule's resources header and resolve `SKSEMenuFramework` DLL exports at runtime. Installation detection only checks `Data/SKSE/Plugins/SKSEMenuFramework.dll` existence. Do not treat that check as an API version handshake.

[Compatibility.h](../src/Compatibility.h) stops QuickLoot opening when its event container has a redirect. It does not redirect QuickLoot inventory itself. The QuickLoot submodule supplies request-client headers; the plugin does not link or build the QuickLoot DLL. Papyrus natives call the same shared assignment and offload operations as hotkeys.

## Ignore list

Sneak-activate a container assigned to Arcane Vault or Sort to open an empty Ignore List picker. Items remaining when it closes are added by base record, and every deposited copy is returned. Removing an item before closing cancels that addition. Normal activation, manual vault actions, and crafting loans do not use the list. Quick Transfer, its hotkey, and its spell always skip ignored records.

The Ignore List SKSE page searches names and plugin identifiers, removes individual entries, and confirms Clear All. Entries apply across saves like overrides. Unresolved plugin entries survive saving; dynamically created base forms cannot be persisted and trigger a notification. Save failure leaves the changes active for the running game and reports that they were not saved. Classification overrides remain independent.

With Keep Selected Ammunition enabled, Keep N retains N selected copies and deposits unselected ammunition. Quest records remain protected. Withdraw Up To N tops up selected records only. With it disabled, reserves apply to all ammunition records and the ordinary favourite, worn, and current-ammunition protections apply.

The Junk category supports classification overrides. Quick Transfer deposits explicitly classified Junk when its checkbox is enabled. It leaves unclassified player items carried. Sort sends unmatched deposits to Junk after category routing and ignored-item recovery.

The Quantities settings page edits ammunition, Septim, empty soul gem, Alchemy and Scroll reserves. Alchemy defaults to 1 per base record; Scroll defaults to 3. Keep N deposits excess without withdrawing. Withdraw Up To N tops up only the shortfall. Zero targets withdraw nothing. Invalid or overflowing values fall back to their defaults. Sale Percentage remains last on Options.

Notes has an independent Quick Transfer checkbox, disabled by default. Recipe overrides imply Note; SpellTome and SkillBook imply Book. Books and Notes Withdraw Up To 1 only supplies missing base records.

Gear Quick Transfer defaults off. `LockpickKeepAmount` defaults to 25 and appears on Quantities. Its integer validation rejects negative, malformed and overflowing values. Gear quicksorting retains this reserve and excludes lockpicks from the subsequent general Gear deposit.

Allow Removing Stolen Tags defaults off. Enabling it adds the explicit clearing action to Stolen Items. Confirmations recheck the option and load generation before changing ownership.

Parent vaults learn Alchemy, Armor, Weapon, Smithing, Food, or Concoction without choosing a subtype. Category archives learn their named category. Notes learns Note. Junk learns Junk; Personal learns Personal; Gear learns Gear; Instruments learns Instrument. Soulgem learns Soulgem for ordinary items; physical soul gems retain their dedicated classification unless explicitly overridden to Ignore. Health Potions, Magicka Potions and Stamina Potions learn HealthPotion, MagickaPotion and StaminaPotion. Enchanted Items, Valuables, filled/empty soul-gem storage, Trade, Sort, Ignore, and Arcane Vault cannot teach a single persistent category. Physical soul gems and forms without stable plugin identifiers never prompt, even in eligible destinations. Soul state remains per copy.

The override loader resolves IDs to `TESBoundObject` forms and stores runtime FormIDs in memory. Native soul gems keep their soul-gem classification except for an explicit Ignore override. The override loader reuses the global redirect identifier parser. Malformed identifiers, partially consumed hex IDs, and unresolved or non-item records skip only that entry. Missing optional plugins do not stop later overrides from loading.

The `Ignore` classification override is stronger than the ignore list. It keeps an item carried through Quick Transfer, returns it from Sort even with Return Ignored Items disabled, and excludes it from crafting-loan returns. Ignore takes precedence if combined with other categories. It is available in the override editor and INI files; user overrides still replace bundled defaults. Manual container deposits and withdrawals remain possible. The existing ignore list retains its sorting-only behaviour and does not change crafting returns.

Sawn Logs default to `HearthFires.esm|0x00300E = Ignore`. They remain hidden and weightless on the player, where Hearthfire expects them. On loading a save and before crafting, counted logs in the plugin's Smithing/material archives, Sort and Junk are explicitly returned to the player. Refused moves remain stored for a later retry; quest-protected stock stays untouched. A user override assigning logs to a different category opts out of this recovery and retention policy.
