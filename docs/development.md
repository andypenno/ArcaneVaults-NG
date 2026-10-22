# Development and verification

Use the [source map](README.md#source-map) to find the owning operation, then enumerate callers before changing it. Inventory movement, assignment, and classification have multiple entry paths. A fix in a single message-box action can leave hotkey, spell, loan, or archive behavior unchanged.

## Change paths

| Change | Files and contracts to inspect |
| --- | --- |
| Transfer protection or counts | `Stores` shared helpers; callers from menu actions, OffloadItems, SortItems, and Events crafting loans |
| Category/classification | `ItemClass` enums, masks, categoryNames, parser/formatter/expansion; Utility recipe caches; bundled overrides; settings/UI selectors; sort order |
| New vault/archive | Container enum/translation key; Utility registry and companion ESP reference; Stores action and parent cleanup; assignment group; translation data |
| Setting | Settings.h default; ForEachINIOption key; behavior consumer; AVUI control if exposed |
| Binding or activation | Utility eligibility; Stores assignment; ContainerSelectionState; RedirectManager; Events hooks; QuickLoot callback; persistence |
| Crafting | Furniture hook and CraftingMenu close in Events; Utility bench detection; Stores protection and archive cleanup |
| Save format or mode | Serialization record checks/version; Settings stable identifiers and INI; mode switch; load/revert side effects |
| UI/string | Stores message boxes; ContainerMenu movie paths and callback; AVUI wrappers; translation JSON; base-container names |
| Runtime/dependency/version | Root and CommonLib xmake; gitlinks/lockfile; generated metadata; plugin.h; hook layouts and external APIs |

Keep first-party changes outside `extern/` and `lib/` unless dependency work is explicitly required. Editing inside a submodule changes a separate repository; root Git records only its commit pointer. Never assume a header dependency is a runtime DLL packaged by this build.

## Source-visible limitations

These are observations from the named source, not confirmed game failures or fixes requested by the documentation task.

| Location | Observation and consequence to verify |
| --- | --- |
| `AVUI::RenderTransfer` | Staff label binds `GSC_OffloadTwoHand`; TwoHand label binds `GSC_OffloadStaffHand`. `OffloadItems` uses the members according to their actual names |
| `ClassifyItem` | Misc Treasure/Gemstone classification depends on overrides |
| `AVTranslation::Install`, `Settings::get_value` | JSON/value conversion errors can throw without local handling |
| `Utility::LoadAllForms` and consumers | Missing required forms only log; later code uses some pointers without guards. Campfire Creation Club lookup is also treated as required by default |
| `CraftingLoanState`, `Soulgems` | Non-gem loans still return by category; gem loans preserve pre-loan counts but unrecognized form changes remain on the player. Carpenter benches use the loaded Hearthfire crafting keyword |
| `ContainerMenuCloseCallback` | One pending callback; load/revert callbacks do not explicitly reset this menu state |
| `RedirectedContainerState` | Begin/Cancel are not wired into current call sites; cannot assume its close behavior runs |
| `main.cpp` | Configuration spell reconciliation explicitly covers loaded games, not a new-game message |
| `pch.h` | `RELOCATION_OFFSET` sets the VR variant offset to zero; no first-party use found. VR options are not runtime compatibility proof |
| Build/version | Duplicate runtime option defaults, prebuilt runtime conflict, and version sources described in [build.md](build.md) |

Before turning an observation into a patch, reproduce the relevant case and establish the intended behavior. External ESP/script/movie semantics may explain a source pattern the repository alone cannot settle.

## Verification available here

The documentation pass inspected first-party source, build scripts, lockfile, submodule pins, integration headers, and the extracted release. It checked documentation links, registry IDs against the actual ESP, and Git whitespace/scope. The [Wine release build](wine-build.md) and documented rebuild/install passed; Windows x64 format, SKSE exports, staging bytes, and lockfile preservation were checked. No Skyrim loading or game scenario ran. Future reports must distinguish compilation and static artifact checks from execution in the game.

The [ESP](esp-editing.md) and [release](release-build.md) tools have runnable checks. The committed [test framework](../tests/README.md) provides unit, integration, regression, performance and package suites. CommonLib has an optional `commonlibsse-ng-tests` target behind `--tests=y`; those are dependency tests, not proof of Arcane Vaults behavior. For a logic change, leave the smallest runnable regression check that exercises the changed contract. Avoid adding a test framework just to mirror implementation.

## Windows and in-game checks

Build with the explicit runtime configuration from [build.md](build.md). Inspect generated metadata/defines when changing runtime support. Use a disposable mod profile and saves for inventory/persistence tests; inspect build installation variables first because the dependency rule can auto-install.

Choose checks relevant to the change and record runtime, load order, starting inventory, actions, and resulting inventory/mapping. Suggested cases:

| Area | Reproduction and expected contract |
| --- | --- |
| Startup | Load with companion assets and data directory present; confirm form loading, hooks, natives, and optional integration status; separately start a new game when changing spell provisioning |
| Assignment | Bind a container and a linked activator to Master, Sort, Vault, and Archive; cover owned cell, unowned interior, exterior non-respawn, locked container, cancellation, removal, and rebinding |
| Destination list | Keyboard and gamepad choose distinct rows; Back/Exit do not create mappings; selected row matches destination |
| Animation/menu | Activate animated and nonstandard models; close matching destination and unrelated menus; confirm return action and source closure, including activation failure/timeout |
| Player transfers | Mixed ordinary/quest/favorite/worn inventory, multiple categories, and per-item count; compare both player and destination inventories |
| Sorting/archives | Mixed Sort contents including unmatched and multi-category items; visit each changed archive through both direct binding and parent menu; verify cleanup and no stranded items |
| Classification/overrides | Built-in item, bundled override, user replacement/removal, comma-separated categories, unknown category, and malformed/unresolved form entry |
| Crafting | Each changed bench, consumed/remaining materials, protected player items, failed activation, and disabling the option during crafting; check inventory on exit |
| Per-save persistence | GlobalRedirect off; save/reload, another save, revert/new game, and changed load order; mappings must resolve through SKSE |
| Global persistence | GlobalRedirect on; save/reload and another character; static references restore across saves even when unloaded; dynamic assignments survive their own save reload but never appear on another character; verify linked blocking after removal/revert |
| Mode switch | Switch both directions and save/reload; document current behavior rather than assume migration |
| Optional APIs | Test without each optional DLL and with supported installed versions; QuickLoot stops redirected containers and continues ordinary ones |
| Configuration/translation | Save/reload options, test hotkeys/spells, check missing/malformed data according to the intended contract, and confirm container names |

Logging uses `SKSE::log` through the `logger` alias. The entry point does not explicitly configure a file sink/path, so inspect the active runtime's logging setup rather than inventing a plugin log filename.

Dragon Heartscales (`Skyrim.esm|0x0D0756`) have a bundled Treasure override. Native quest-marked entries are skipped by player transfers. Without that mark, enabled Treasure transfers route them into the directly accessible Treasure vault. Local regressions cover both states and Sort routing; the reported in-game disappearance is not reproduced. Reagent access gathers and opens Reagent, then returns leftovers to Alchemy.
