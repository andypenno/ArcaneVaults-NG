# Complete release build

[build_release.py](../tools/release/build_release.py) produces `build/releases/ArcaneVaults-NG.zip` with the same 10 file paths as the Arcane Vaults 1.2 sample. Its inputs are repository files and pinned tool dependencies. A normal build neither reads Downloads nor opens an upstream release ZIP.

Set up the [Wine/MSVC environment](wine-build.md) first. It must mount this checkout at `/repo` and its tools directory at `/work`. The release script checks these mounts and starts an existing stopped container. Python 3 and Podman are needed on the host. Caprica 0.3.0 is downloaded once from its official release and cached under `/work/release-tools`; the archive and executable hashes are pinned in [release/inputs.json](../release/inputs.json).

From the repository root:

```bash
python3 tools/release/build_release.py
python3 tools/release/check.py
python3 tools/release/check_keys.py
python3 tools/release/check_soulgems.py
python3 tools/release/check_trade.py
python3 tools/release/check_misc.py
python3 tools/release/check_navigation.py
python3 tools/release/check_archives.py
python3 tools/release/check_redirects.py
python3 tools/release/check_ignores.py
python3 tools/release/check_learning.py
python3 tools/release/check_stolen.py
python3 tools/release/check_enchanted_loans.py
```

Use `--container NAME` on the build command if the dedicated Wine container has a different name. Compiler output goes to `build/releases/build.log`. `artifact.json` beside the ZIP records the ZIP checksum, packaged file checksums, and validation results. Neither that report nor the build log goes into the mod package.

The release command disables xmake's C++ compiler cache for MSVC through Wine. After an invalid-object linker failure, remove the affected object and dependency file before retrying; disabling the cache does not replace an existing object by itself. Keep failed-build logs separate from the next run's `build.log`.

## Inputs and staging

| Component | Build input and action |
| --- | --- |
| DLL | Build the pinned C++/CommonLib sources with Wine/MSVC, release mode, SE and AE enabled, VR disabled. `/Brepro` requests a deterministic linker timestamp |
| ESP | Generate [release/ArcaneVaults-LinkedStorage.json](../release/ArcaneVaults-LinkedStorage.json) through [esp.py](../tools/release/esp.py) |
| PEX | Compile [scripts/Source](../scripts/Source) with Caprica's Skyrim target; normalize compiler metadata and correct its object-size fields |
| PSC | Package the exact source files compiled into PEX |
| INI and translation JSON | Copy the repository's `ini/` files |
| UI | Copy the vendored movies under [assets/skyui-lib](../assets/skyui-lib), checking their pinned upstream hashes |

The script stages into a fresh temporary directory. It checks the exact path population declared in `release/inputs.json`, rejects missing, extra, or empty files, validates the assets, creates the ZIP, and reopens it for validation. Only then does it replace the previous generated artifact. Temporary staging is removed on success or failure. Compilation or validation failure exits nonzero and leaves the prior ZIP unchanged. The caller must respect the exit status rather than treating an old ZIP as a successful new build.

ZIP entries have sorted paths, fixed timestamps, and fixed file permissions. PEX header timestamps, source paths, usernames, and machine names are normalized. With the documented toolchain, two separate DLL builds after enabling `/Brepro` produced identical bytes. The other nine package files matched across three complete release runs. The regression check repackaged the final files twice and matched the produced ZIP byte-for-byte. Byte-for-byte builds on a different toolchain or compression-library version have not been established; use the pinned toolchain and recorded hashes to compare outputs.

## ESP authoring and upstream updates

The working ESP definition is separate from [release/upstream/esp.json](../release/upstream/esp.json). The baseline includes the original Papyrus sources and a release ZIP/file hash record. It retains no released DLL or PEX. The two UI movies came from the pinned SkyUILib repository, not from the downloaded mod package.

ESP definitions retain record IDs, flags, version fields, group metadata, ordering, and subrecord bytes. Text fields and placed-reference `NAME` IDs are exposed directly. Other fields, including VMAD script properties, remain hex data. Original compressed record payloads are reused when their decoded fields are unchanged; editing them causes recompression. Duplicate IDs and malformed lengths fail. Unsupported extended subrecords fail explicitly during import instead of being discarded.

Edit the working definition for ordinary record changes. For typed operations, generate an ESP, modify it with the [Mutagen tool](esp-editing.md), then import the edited ESP into a new JSON file with `esp.py import INPUT OUTPUT`. Review and replace the working definition with that result. The importer verifies a byte-exact round-trip before writing any definition.

Adding a destination also changes the C++ enum, registry, operations, and translation data. Preserve retained IDs. Update HEDR's count of records plus groups and its next-form boundary when adding records; package validation rejects stale values. [storage.md](storage.md) describes the runtime contracts.

For a new upstream release, run `python3 tools/release/import_release.py NEW_RELEASE.zip NEW_CANDIDATE_DIRECTORY`. The candidate directory must not exist. This command recovers the ESP definition and original PSC sources and records hashes of the release's file population. It does not replace working inputs or reuse upstream compiled files.

Compare the old `release/upstream` baseline, our working definitions/sources, and the candidate. Merge the source changes in three ways, then replace the upstream baseline with the candidate and rebuild. Changed configuration or UI hashes in the candidate report need deliberate review against the tracked configuration and pinned UI dependency. An added release path requires updating `release/inputs.json`; assembly never silently includes new files.

## Papyrus compiler contracts

The [compile-only imports](../scripts/Imports) expose only the base classes and `OnEffectStart(Actor, Actor)` signature used by these scripts. They provide no runtime implementation and are excluded from the ZIP. Extend those interfaces if a source change uses another Skyrim native API; verify its actual game signature first.

Caprica requires `native` on the `ArcaneVaults` class to declare its native functions. That one-token source difference is kept in the working PSC, while `release/upstream/ArcaneVaults.psc` preserves the original. The generated functions remain global/native with no parameters and a None return type.

Caprica 0.3.0 emits the Skyrim object-size field in little endian and omits the four-byte size field from its count. [pex.py](../tools/release/pex.py) accepts that exact compiler defect only during normalization, then writes the big-endian size including those four bytes. Strict parsing of the final PEX checks the corrected size. The [PEX format reference](https://en.uesp.net/wiki/Skyrim_Mod:Compiled_Script_File_Format) specifies this layout.

## Validation boundary

The build validates Windows x64 PE format and the actual SKSE export table, ESP registry IDs, persistent non-respawning storage, container links, header counts/allocation, spell-effect script properties, and PEX native signatures. It executes the compiled dispatcher in a small bytecode check for `SpellType` 0, 1, and an unmatched value. The standalone check retains the upstream SHA/round-trip checks and validates the working ESP against the current registry. It also exercises compressed-record edits, compiler-size correction, deterministic ZIP bytes, and missing/extra-file rejection.

`check_keys.py` also executes the native potion effect classifier and archive callbacks. Cases cover restore/fortify/regeneration actor values, dual and mixed effects, food/poison and detrimental exclusions, missing effects, nonpositive/NaN magnitudes, override precedence, gather/return and residual-archive consolidation.

`check_keys.py` needs a native C++20 compiler. It extracts the real transfer, Sort, Quick Transfer, Gold/ammunition/miscellaneous classification branches, Valuables, Keys, Books, Alchemy, Scrolls, Soulgem vault, and direct Empty Soulgems archive callbacks, INI option mapping, and INI reader and runs them with inventory/settings stubs. It checks direct Archery gathering from Weapon/Ammunition and separate returns, including withdrawals, manual deposits, large stacks and failed returns; Keys duplicate retention, ammunition and Septim reserves, Valuables gathering/return and manual deposits, precious ingot crafting categories, protected entries, category selection, repeat deposits, large stacks, existing count requests, carried-target withdrawals, manual Alchemy/Scroll quantities, native spell-scroll sorting and overrides, Quick Transfer defaults/modes, reserve input validation, and generated ESP persistence/respawn flags. It does not run Skyrim's inventory engine or write game settings files.

`check_soulgems.py` compiles the actual soul gem module and crafting-loan session with inventory stubs. It exercises mixed extra-data stacks, explicit zero souls, metadata-preserving moves, deposit and top-up reserves, archive consolidation, protected/unique gems, recipe eligibility, reusable form changes, consumed gems, uncertain leftovers, and a setting changed during a loan. It models null-list removal preferring an explicit stack. These checks do not substitute for Skyrim inventory-engine testing.

`check_trade.py` compiles the actual sale and menu code with inventory stubs. It covers copy counts, variant prices, aggregate rounding, confirmation/cancellation, protected entries, failed and partial removal, repeat sale, and payment limits. Skyrim must verify engine-derived prices and item removal.

`check_misc.py` exercises actual page registration, Quantities and Options controls, and Quick Transfer UI with ImGui ID/persistence stubs and the actual override loader with optional-plugin and malformed-entry cases. `check_navigation.py` runs the actual message-box, close, registry-dispatch, and contextual-return code with UI/task stubs, including direct binding, cancellation, cleanup, and expired handles. `check_archives.py` runs both registered vault and archive lists and selection callbacks, including every storage handler, contextual returns, cancellation, and browsing without creating redirects.

`check_redirects.py` compiles the actual manager, identifier code, INI persistence, and SKSE callbacks with stubs. It covers unloaded sources, dynamic save isolation, both persistence modes, changed load order, global precedence, linked activator blocking, and malformed records.

`check_keys.py` also tests the shared player-transfer protection with ten virtual worn items exposed through `GetEquipped`, unequipped copies, changed condition hooks, non-armor items, and missing or failed condition checks alongside native protections.

`check_stolen.py` runs the actual PlayerToStore, PlayerEquipment and InventoryStacks code with UI-managed Show/Hide and separate UI/game task queues. It covers ten distinct worn ring bases with matching spares, native/UI-only equipment, unique-ID mapping, metadata, partial and large moves, reserves, protections and malformed rows. The fake UI manager changes input masks, stored masks, context stacks and the player block flag on Show, then restores them on Hide; completion requires that restoration. Cases cover originating message boxes, cancellation before Show, existing user-open menus and conservative inspection failure. The test rejects native factory calls, direct ProcessMessage dispatch and control-state writes in the inspector. Skyrim must verify the real menu lifecycle.

`check_quick_transfer_idle.py` runs 55 simulated-frame cases and three lifecycle-budget cases against production inspection and player-transfer code. Use `python3 tools/release/check_quick_transfer_idle.py --output build/regressions/quick-transfer-NEW.json`; output paths must be new. Cases cover idle/protected inventories and matching ring spares with display/plain/undefined roots, readable/delayed/invalid row objects, initialized empty lists and missing UI components. Undefined roots with empty or invalid rows finish without reaching the timeout. They assert bounded completion, worn/spare counts, one managed inventory update, closure before transfer and restored input masks/block state. `--source-ref REV` checks a prior inspector revision; `--sanitize` adds AddressSanitizer/UndefinedBehaviorSanitizer. Budget cases cover a blocked message box, a delayed Show with missing movie, and refused Hide followed by native recovery. Simulated milliseconds are not Skyrim runtime measurements.

`bench_quicksort.py` compares actual equipment snapshots and a protected single-category player transfer against the pre-optimization commit `3e7dd85`. It uses the same engine stubs and compiler flags for both versions, reverses their order in the second batch, verifies worn/spare counts and metadata, and records raw samples, source hashes and timing distributions. Run `python3 tools/release/bench_quicksort.py --output build/benchmarks/quicksort-NEW.json`; existing reports are never overwritten. Snapshot cases use 100, 1,000 and 5,000 base items; transfer cases use 100 and 1,000. The deterministic regression asserts one row traversal and filtered entry copies; these counters are disabled during timing. This CPU comparison excludes menu construction, polling and Skyrim runtime costs. It adds no runtime logging.

The package root corresponds to Skyrim's `Data` directory. It has no enclosing `Data` or project-name directory. Runtime prerequisites such as SKSE, Address Library, and SKSE Menu Framework remain external game dependencies described in [build.md](build.md). No Skyrim launch or gameplay scenario is verified by these artifact checks.

`check_ignores.py` runs the actual ignore loader/saver, activation dispatcher, picker completion, and SKSE management page with engine/UI/INI stubs. It checks unresolved-plugin preservation, rejected dynamic forms, metadata-carrying returns, failed activation/removal/saving, stale callbacks, name search, removal, and confirmed clearing. `check_keys.py` covers ignore-aware Sort/Quick Transfer and partial returns; `check_soulgems.py` covers the physical-gem path. Gameplay remains unverified.

`check_keys.py` also exercises Junk loans through every recognized bench, consumed items, carried baselines, overlapping normal loans, large stacks, failed removals, equipped entries, setting changes, reset, and the signed item-count boundary.

Book/Note cases in `check_keys.py` execute the real native-book classification branch, teaching/recipe precedence, override parent expansion, Sort/Quick Transfer separation, legacy Scroll migration, parent consolidation, archive menus and returns, and direct assignment close behaviour. Generated ESP checks cover all five new persistent, non-respawning destinations.

Selected-ammunition cases in `check_keys.py` run the real Keep/Take actions and selection helper in both modes, including favourite/current/native-worn/standard-equipped selection, duplicate selection, no selection, zero reserves, shortfalls, limited stock, over-target stacks, ignored/quest items, missing equipment hooks, large stacks, and failed moves. The actual menu callbacks and default INI key are checked; `check_misc.py` checks the default-off Options control and saves both states.

The attribute potion and combined Enchanted Items archives add four persistent container/reference pairs plus the `AV_EnchantedOrigin` keyword. The working ESP allocator advances to `0xDEE`; package validation checks the new origin keyword and reconciles the registry with every storage reference. `check_stolen.py` also exercises the shared InventoryStacks code and Enchanted Items module, including implicit stacks above 65535, mixed enchanted/plain copies, artifact restrictions, known and custom enchantments, metadata, source returns and failed transfers. These cases use engine stubs and do not verify Skyrim gameplay.

`check_enchanted_loans.py` compiles the actual enchanted archive, physical-stack helpers and crafting-session class. It checks the independent toggle, other bench exclusion, existing carried copies, ownership/enchantment metadata, consumption, protected records, partial and large moves, failed transfers/activation, same-base Junk loan ordering, delayed withdrawal callbacks, setting changes and reset. Additional cases replace remaining extra-list pointers after moves, preserve different enchantments on the same base with identical other metadata, retain plain/carried copies, validate malformed trailing stacks in first-stack reads, and exercise partial Junk lending, capacity failures and coalesced cleanup across reset/new loans. Bulk lending cases require one native archive-to-player call with ownership retained, reject capacity overflow and malformed staged stacks, and cover empty, missing-inventory, refused and partial delivery with carried copies preserved. `check_misc.py` verifies the disabled UI default and saving; `check_keys.py` verifies the General INI mapping. Run `python3 tools/release/check_enchanted_loans.py --sanitize` for AddressSanitizer and UndefinedBehaviorSanitizer checks on the native stub test. Skyrim must verify furniture activation and the disenchanting screen.

`bench_transfer_candidates.py` records behaviour and CPU baselines for reserve short-circuits, duplicate stack reads, equipment-entry detection and category withdrawals. Run `python3 tools/release/bench_transfer_candidates.py --output build/benchmarks/transfer-before.json` before editing production code. Reports save the exact working source in a sibling `.sources` directory, including uncommitted changes. After an optimization, run with `--baseline build/benchmarks/transfer-before.json --output build/benchmarks/transfer-after.json` to rebuild both versions with identical stubs and reverse their execution order between repeats.

The default matrix uses 0/100/300/1,000 types or same-base physical stacks and four samples. It verifies reserves, worn/spare counts, mixed custom enchantments, ownership/metadata, protected records, request limits, partial/refused moves, capacity/malformed stacks, top-ups and equipment presence/absence. Reports retain timing ranges and scan/copy/move counters; timing deltas are reviewed against noise rather than used as flaky pass/fail thresholds. `--sanitize` runs behaviour checks only. Native engine/UI latency and real classification are excluded.

`bench_crafting_loans.py` compiles the production crafting-session, transfer, Junk, soul-gem and enchanted code with engine stubs. Run `python3 tools/release/bench_crafting_loans.py --baseline HEAD --samples 4 --output build/benchmarks/crafting-loans-NEW.json`. The default matrix covers all five benches at 0, 100, 300 and 1,000 main types, plus 100/300/1,000 copies in one physical stack and that many distinct physical stacks sharing one base per family. Enchanted duplicate stacks alternate three custom enchantments. Each case also seeds matching Junk and, for Smithing/Enchanting, gems, while preserving 100 carried favourites. Select a subset with `--sizes`, `--benches` or `--scenarios types quantity stacks`.

Runs are serial and reverse baseline/working and manual/loan order between repeats. Reports retain source/header and harness hashes, raw samples, min/median/max timings, and inventory scan/copy/move counts and native bulk-call counts. Round trips assert quantities, ownership, per-stack metadata and custom enchantments, carried items and origin cleanup. Only completed round trips are marked validated; timeouts preserve partial phases and stop. Existing reports are never overwritten. Native engine, UI, animation and real classification costs are excluded; timings do not predict Skyrim latency.
