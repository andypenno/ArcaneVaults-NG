# Coverage inventory

| Contract | Test IDs / fixtures | Execution boundary |
| --- | --- | --- |
| Physical stack reads, counts, partial/refused moves, owner/enchantment preservation | inventory-scenarios, stolen, favorites, keys | Complete InventoryStacks module plus retained caller fixtures; game engine modelled |
| Worn/favourite same-base spares, implicit copies, renamed/custom enchantments | favorites, stolen, pipeline, JSON inventories | Production protection/inspection code; some Stores methods extracted |
| Quick Transfer entry paths, category ordering, reserves, archives, cancellation | quick_transfer_pipeline, quick_transfer_idle, engine_boundaries | Production controller/modules and extracted Stores methods; native menus modelled |
| Startup inspection eligibility, protected-query work, delayed initial rows/markers, stale polls and partial/refused archive consolidation | quick_transfer_pipeline, support/transfer_startup.cpp | Production inspection and transfer paths; explicit external UI-readiness schedules and API counts, not native game timing or a reproduced engine stall |
| Mixed inventories across every category, populated vaults, 500/1,000 stacks and protected loadouts | sorting-scenarios, sorting JSON catalog and inventories | Same production controller and transfer harness for all three entries; supplied classification masks, explicit destination/count assertions and per-copy metadata checks |
| Render frames, stale callbacks, headless/stalled renderer, input restoration | transfer_feedback, quick_transfer_pipeline, performance | Production feedback code with deterministic scheduler; actual rendering needs game |
| Frame starvation in capture, UI matching/retries, validation, job preparation and soul-gem recovery | quick_transfer_frames, support/transfer_frames.cpp | Actual targeted production loops with per-iteration synthetic cost, whole-interaction draw gaps and independent safety assertions. Opaque native controls expose indivisible stalls separately. Intentionally failing against 823cd6c; does not reproduce or time the user's Skyrim stall |
| All crafting benches, materials, consumption and returns | crafting_benches, soulgems, keys, engine_boundaries, performance | Production loan session and transfer methods; furniture/game events modelled |
| Purchased/carried construction stock, empty/banked starts, three visits, consumption, both loan modes and session resets | construction-loans, crafting/hearthfire-logs.json | Actual session and physical transfers; classification supplied, bulk engine modelled. Hidden UI and playable controls are separate from physical counts. Reset retains in-memory inventories, not a real save round-trip. Native hidden-resource handling, purchase, house state and activation remain unverified |
| Possible native bulk exclusion of non-playable construction stock | construction-bulk-filter-probe, experiments only | Deliberately changes only the fake native bulk boundary. Fails availability if the actual loan code strands hidden logs, retains conservation checks and verifies explicit manual retrieval. A failure supports the hypothesis without establishing native behaviour |
| Sawn Logs remain carried through Quick Transfer, Sort and repeated crafting exits | keys, crafting/hearthfire-logs.json retention | Actual classification branches, transfers and loan session. Applies real bundled log override if present; also exercises the existing ignore list. Ordinary ingots must still transfer. Requires the new retention policy, without hypothetical native filtering |
| Books/notes, spells, potion effects, ammunition, categories and overrides | keys, misc, static-data | Production classification branches and settings; native form data modelled |
| Vault registration, browsing, action order and direct navigation | archives, navigation | Actual registry/menu callbacks; native UI modelled |
| Redirect persistence, malformed saves, changed load order and dynamic references | redirects | Actual manager/serialization helpers; SKSE records modelled |
| Ignore picker, persistence, reset, failed operations | ignores, keys, soulgems | Actual handlers/helpers; engine and filesystem boundaries modelled |
| Sale counts/prices, partial failure and payment | trade | Production sale/menu code; engine prices modelled |
| Deposit learning, identity, reentrancy and rollback | learning, engine_boundaries | Production event/session code; event source modelled |
| Installer JSON/INI, duplicates, format arguments and source bytes | unit, static-data, packaging | Real committed/extracted bytes; form existence needs game data |
| ESP editor inspect/rename and independent binary preservation | esp-editor | Actual locked .NET tool, upstream and working ESPs |
| Wine shader compiler success/failure | wine-toolchain | Actual pinned FXC under Wine |
| ESP/PEX round-trip, malformed files, dispatch and retained storage IDs | packaging, storage-identities.json | Real generated binaries and committed compatibility expectations |
| Exact ZIP population, CRC, unsafe/colliding paths, deterministic assembly | packaging, unit promotion tests | Real candidate archive and atomic filesystem promotion |
| Time/work/render budgets and baseline failure behaviour | performance, unit policy tests | Compiled production paths with supplied native costs and measured host execution |
| Startup hooks, native ABI, optional DLL compatibility and save behaviour in Skyrim | game checklist, Windows compilation | Compilation is automated; real loading/hook compatibility remains game acceptance |

The legacy checks were moved without dropping their assertions. Fragment extraction remains in broad Stores, classification and crafting-session fixtures. It is not claimed as complete-module coverage. InventoryStacks has a direct complete-module target; further conversion must preserve existing cases and demonstrate the original failure before retiring a fragment fixture.

No test proves compatibility with every mod or the absence of all possible bugs. The runner reports the tested source and the evidence layer. UI lifecycle, construction resource visibility, reported missing-item scenarios and engine-level timing need the documented game checks.
