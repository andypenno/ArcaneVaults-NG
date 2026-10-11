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
| `ArcaneVaultTranslation.json` | Flat translation object, supplied by [ini/ArcaneVaultTranslation.json](../ini/ArcaneVaultTranslation.json) |

Settings initialization loads options, then bundled overrides, then user overrides. Missing keys get in-memory defaults and are added to the temporary INI object, but an existing settings file is only written by `SaveINI`. UI changes call `SaveINI`; no file watcher reloads changes while running. `AmmunitionKeepAmount`, `GoldKeepAmount`, and `SoulgemKeepAmount` use `from_chars` with full input and nonnegative validation; invalid or overflowing values fall back to 100, 5000, and 25 respectively. Other integer settings use `stoi` without a local exception handler. Most settings read/write return codes are not reported, unlike user-override and redirect save failures.

## Options

The `ForEachINIOption` helper shares one mapping between reads and writes.

| General key | Default | Meaning |
| --- | --- | --- |
| `GlobalRedirect` | true | Select global INI rather than per-save mapping persistence |
| `AssignKeyCode` | -1 | Assignment input code; disabled by default |
| `QuickKeyCode` | -1 | Quick offload input code; disabled by default |
| `CraftingLoan` | false | Lend and return crafting materials |
| `AssignOnlyOwn` | true | Restrict binding according to ownership/exterior non-respawn rules |
| `AssignSpell` | true | Enable external assignment spell |
| `SortSpell` | true | Enable external sorting/offload spell |
| `AmmunitionKeepAmount` | 100 | Retain this many per carried arrow or bolt record; zero retains none |
| `GoldKeepAmount` | 5000 | Retain this many carried Septims; zero deposits all eligible Gold |
| `SoulgemKeepAmount` | 25 | Retain this many empty soul gems per base record; filled gems have no reserve |

In `[Offload]`, enabled defaults are `Reagent`, `Catalyst`, `Ingredient`, `Crafting`, `Construction`, `Gemstone`, `Smelting`, `Tanning`, `RawFood`, `Soulgems`, `Ammunition`, `Gold`, `Keys`, and `KeysKeepOne`. Disabled defaults are `Clothing`, `HeavyArmor`, `LightArmor`, `Jewelry`, `Books`, `Scrolls`, `Spelltomes`, `Potion`, `Poison`, `CookedFood`, `Treasure`, `Archery`, `OneHand`, `TwoHand`, and `StaffHand`. Exact spelling matters, including `Spelltomes` and `StaffHand`.

Options exposes Ammunition Keep Amount as a nonnegative integer control. Quick Transfer only exposes an Ammunition enable checkbox under More. `[Offload] Ammunition=true` enables ammunition deposits using the same reserve as the vault Keep N action. Missing values default to enabled and 100. The amount applies per ammunition base record, not to the combined arrow/bolt count.

Options exposes Gold Keep Amount with the same nonnegative integer control as ammunition. Quick Transfer exposes only a Septims enable checkbox under More, persisted as `[Offload] Gold=true`. The reserve applies to Quick Transfer, its hotkey/spell, and Valuables' Keep N Septims action. Sorting Gold already in Sort moves the entire amount to Treasure. Gold has no Treasure category bit, so enabling the Treasure offload toggle cannot bypass the Gold reserve.

Quick Transfer exposes one Soulgem checkbox, persisted as `[Offload] Soulgems=true`. Options exposes Empty Soulgems Keep Amount, default 25. The retired `EmptySoulgem`, `FilledSoulgem`, and `GrandSoulgem` INI keys are ignored and existing files may retain them. Filled/empty classification is instance-based and is not controlled by overrides. The new policy defaults to enabled even when only old keys exist.

Quick Transfer shows Keys and Keep One under More. `Keys=true` enables key deposits through the menu, hotkey, and offload spell. `KeysKeepOne=true` deposits duplicates while retaining one per carried key record. Disabling Keep One deposits all eligible keys. Both default to true when missing from an existing settings file. Sort moves keys already deposited into its inbox to the Keys vault; it does not withdraw a copy to the player.

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

The override loader resolves IDs to `TESBoundObject` forms and stores runtime FormIDs in memory. A malformed key, parse error, or unresolved item returns from the whole loader rather than skipping only that entry. Hex parsing there does not check full text consumption. Keep this difference from the stricter global redirect parser in mind when debugging partial loads.

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
