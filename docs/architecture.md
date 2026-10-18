# Runtime architecture

[main.cpp](../src/main.cpp) connects SKSE lifecycle callbacks to process-wide singletons. There is no application server, database, or standalone executable. Gameplay operations use engine objects directly.

## Startup order

| Trigger | Work, in source order |
| --- | --- |
| `SKSEPlugin_Load` | Reset REL module state; obtain messaging interface; log local plugin version; initialize SKSE; allocate 128-byte trampoline; register SKSE listener; register Papyrus functions; register serialization ID and save/load/revert callbacks |
| `kPostPostLoad` | Initialize QuickLoot API; register opening-menu handler if ready, otherwise log a warning |
| `kDataLoaded` | Install translations; load companion/game forms and recipe caches; initialize settings and overrides; install hooks/event sinks; register destination menu; register optional framework UI |
| `kPostLoadGame` | Add/remove configuration spells according to settings |

Load returns false if messaging, Papyrus registration, or serialization is unavailable. Missing form lookups log errors but do not stop `LoadAllForms`; some later consumers assume those pointers exist. New-game spell provisioning is not explicitly handled by the message switch. Verify that path in-game before claiming parity with loaded saves.

## Control and data flow

```mermaid
flowchart TD
    Entry[SKSEPlugin_Load] --> Life[SKSE lifecycle messages]
    Life --> Utility[Utility form registry and recipe caches]
    Life --> Settings[Settings and overrides]
    Life --> Events[Activation hooks and event sinks]
    Input[Hotkeys or Papyrus natives] --> Assign[Utility.ContainerRedirect]
    Assign --> Selection[Stores assignment message box and SkyUILib list]
    Selection --> Redirect[RedirectManager mapping]
    Events --> Redirect
    Redirect --> Action[Utility.RunContainerAction]
    Action --> Stores[Stores menus and transfers]
    Stores --> Classify[ClassifyItem]
    Classify --> Settings
    Classify --> Utility
    Stores --> Game[Player and ESP container inventories]
    Events --> Loan[Crafting loan]
    Loan --> Stores
    Save[SKSE save/load/revert] --> Persist[Serialization or global INI]
    Persist --> Redirect
```

## Activation and assignment

Assignment starts through the hotkey or Papyrus native, then [Utility::ContainerRedirect](../src/Utility.cpp) inspects the crosshair target. It accepts a container, or an activator with a default linked reference whose base is a container. With ownership restriction on, assignment requires an owned cell, or an exterior non-respawning container. Cell ownership means the player's actor base or a faction the player belongs to.

[Stores::VaultAssignment](../src/Stores.cpp) offers Master, Sort, Quick Transfer, grouped Vault/Archive choices, removal, and exit. Grouped choices are sorted by display name. [ContainerSelectionState](../src/ContainerMenu.cpp) retains the source smart pointer and exact displayed choices. Completion either runs a synthetic Back/Exit action or resolves the selected destination FormID and adds the mapping.

[Events.cpp](../src/Events.cpp) patches these vtable slots:

| Base type | Slot | Behavior |
| --- | --- | --- |
| `TESObjectCONT` | `0x37` | Player activation resolves a redirect and dispatches its registered action; locked containers keep original activation |
| `TESObjectACTI` | `0x37` | Player activation resolves a redirect and dispatches its action |
| Both above | `0x4C` | Call original activation-text function, then show `Search` plus destination display name for redirected crosshair target |
| `TESFurniture` | `0x37` | Lend materials before original player crafting activation when enabled and bench data is not `kNone` |

Container activation also has a thread-local guard, but the current source does not set it. Destination dispatch runs a registered `Stores` callback; it does not generically activate arbitrary redirected references. A missing action falls through to original activation. All containers registered in `Utility::LoadContainers` have actions in the current source.

[RedirectManager](../src/RedirectManager.cpp) maps source FormID to destination FormID. Add/update blocks a container linked to an activator; remove/clear unblocks it. It queues crosshair refresh after each change. The displayed name is supplied by the text hook, not persisted as part of the redirect.

## Menus and asynchronous work

Storage interaction has two UI implementations. `Stores` queues engine message boxes whose actions run through SKSE's task interface. Quick Transfer defers its completion callback until UI-managed equipment inspection has closed; its lifecycle is described in [storage.md](storage.md). `ContainerListMenu` registers as `GSCContainerListMenu`, pauses the game, uses cursor/menu input, and loads `uilib/uilib_1_listmenu` through Scaleform.

With SKSE Menu Framework installed, Quick Transfer draws a compact, centred sorting panel above existing menus, with a stationary gold sigil that pulses every 2.6 seconds, a single translated sorting label and a light background dim. Animation advances only while frames render. It starts inventory work after two overlay render callbacks, or a bounded 250 ms fallback if rendering does not run. Button presses are filtered while busy; releases pass through. The overlay does not write native control masks or replace the underlying menu. Completion removes it before returning to Arcane Vault. Failed inspection closure removes it to expose Skyrim's ordinary inventory recovery. Pre-load/new-game cancels both the overlay barrier and equipment request.

Message boxes with Exit display the physical Open action first, show withdrawals before Keep and Store All actions, preserve other storage actions, then show contextual Back and Exit. The shared builder recognizes the existing translated Open labels and maps cancellation to the final Exit. Confirmation boxes without Exit preserve their supplied order and cancel action. Armor and Weapon provide Open actions that consolidate their child archives before opening the entire parent vault.

Open Vaults and Open Archives share a registered, UI-managed SkyUILib list. The browser invokes the destination's registered action, carries contextual Back and Exit, and does not assign redirects. The former paginated vault menus are removed.

The SkyUILib bridge passes option labels as separate ActionScript arguments, configures gamepad mode, and replaces the movie's `exitMenu` callback. The callback reads `_root.listDialog.menuList.listState.activeEntry.itemIndex`, completes selection, and hides the registered menu. This movie contract is external to the repository.

`Stores::OpenStoreObject` and `CloseStoreObject` request engine open/close states. Animation polling delays 16 ms in a detached thread, then queues state inspection on the game thread. Polling uses an object handle and a five-second deadline. Timeout still invokes the callback; a vanished reference stops the poll. Keep engine access inside the queued task when modifying this path.

`OpenStorageMenu` registers one close callback for the destination, then activates that destination. The event sink only arms the callback when `ContainerMenu` opens on the matching target. On close it clears state before queuing the callback. Failed activation cancels the registration and invokes the return action. This is a single pending interaction, not a callback collection.

`RedirectedContainerState` also receives container open/close events, but its `Begin` and `Cancel` have no call sites in current first-party code. Do not infer an active second redirect lifecycle from the class name.

## Crafting loans

The furniture hook selects the bench through `Utility::GetBenchType`, which checks known keywords first and bench data second. `CraftingMenu` close returns materials through the same transfer helpers.

| Bench | Entry transfer | Exit transfer |
| --- | --- | --- |
| Alchemy, including grain mill keyword | Entire Alchemy inventory to player | Player items matching Alchemy to Alchemy |
| Smithing, including carpenter, forge, tanning, smelter, tempering keywords | Entire Smithing inventory plus Alchemy Catalysts and banked gems present in the existing recipe caches | Smithing items/Catalysts to their parent stores; identifiable unused gem loans to Soulgem |
| Cooking | Entire Food inventory plus Alchemy Reagents to player | Food and Reagents to their parent stores |
| Enchanting | Filled gems when Crafting Loan is enabled | Unused gems to Soulgem |
| Staff enchanting | Alchemy Catalysts to player | Catalysts to Alchemy |

All Crafting Materials is disabled by default. When enabled alongside Crafting Loan, every recognized station borrows Smithing, Food, Alchemy, eligible Junk and empty/filled soul gems, without recipe filtering. Armor, Weapons, Gear and other non-material vaults remain excluded. The session captures this mode on entry so changing either option while crafting does not alter its return path. Disabling the option preserves the station-specific table above.

Normal non-gem vault loans retain category-based returns and can include materials carried before the loan. Junk loans capture carried and verified moved counts and return excess to Junk before those category returns. Junk returns read only recorded loan forms; soul-gem snapshots exclude unrelated item data. Shared player deposits reject unrelated categories before fetching fresh entry data and reuse the physical transfer helper's verified moved count. Soul gems record pre-loan counts by base form and empty/filled state, plus borrowed and directly linked forms. Returns inspect current stacks, preserve pre-existing counts, and cap the returned total by the loan. Unrecognized mod transformations and ambiguous bare stacks stay on the player for explicit Quick Transfer. Consumed gems are not recreated. Both gem archives consolidate before lending.

Ignore-list activation and recovery are described in [storage.md](storage.md). Pre-load and new-game messages cancel the pending container callback and invalidate its picker session. Post-load and new-game tasks recover picker contents on the game thread.

Displayed storage names and menu titles consistently use the Vault suffix for both parent and archive destinations. Vault/Archive groups remain separate for browsing and routing; Quick Transfer retains its action name.

Crafting loans are controlled by Crafting Loan and contain materials and soul gems. Enchanted equipment is available only through manual vault access. The retired EnchantedItemsLoan INI key is ignored. Existing carried copies remain carried; normal archive recovery clears old origin markers without recreating items.

Carpenter stations bearing the loaded Hearthfire crafting keyword participate in ordinary Smithing loans. Construction materials already sort into Smithing; with Crafting Loan enabled they are present while constructing and unused amounts return afterwards. Hidden resource display remains controlled by Skyrim.
