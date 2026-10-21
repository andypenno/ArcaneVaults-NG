# Complete release build

[build_release.py](../tools/release/build_release.py) produces `build/ArcaneVaults-NG.zip` after verifying a candidate in `build/history/`. The package paths are declared in the manifest. Its inputs are repository files and pinned tool dependencies. A normal build neither reads Downloads nor opens an upstream release ZIP.

Set up the [Wine/MSVC environment](wine-build.md) first. It must mount this checkout at `/repo` and its tools directory at `/work`. The release script checks these mounts and starts an existing stopped container. Python 3 and Podman are needed on the host. Caprica 0.3.0 is downloaded once from its official release and cached under `/work/release-tools`; the archive and executable hashes are pinned in [release/inputs.json](../release/inputs.json).

From the repository root:

```bash
python3 tests/run.py --suite unit static-data
python3 tests/run.py --suite regression integration --sanitize
python3 tools/release/build_release.py
```

The release command runs the mandatory test profile, compiles the Windows DLL and inventory test executable, runs its JSON scenarios through Wine, archives the candidate, tests that exact ZIP and atomically promotes it. A normal compile remains available for iteration. [GitHub Actions](ci.md) invokes this same command after provisioning an isolated Wine/MSVC toolchain.

| Output | Location |
| --- | --- |
| Single verified ZIP | `build/ArcaneVaults-NG.zip` |
| Immutable candidate ZIPs | `build/history/<UTC-date>-<commit>[-dirty]/ArcaneVaults-NG.zip` |
| Release log, hashes and gate reports | `results/releases/<same-run-id>/` |
| Test logs and raw measurements | `results/tests/<run-id>/` |
| Compiler intermediates and DLL | `.build/` |

Use `--container NAME` if the Wine container has a different name. Logs and reports never go inside the ZIP or the ZIP history. Failed tests or compilation leave the previous verified ZIP intact. A candidate that fails final checks remains in history with the failure log in results. Dirty builds record the source fingerprint and dirty state; game acceptance is separate from automated verification.

The release command disables xmake's C++ compiler cache for MSVC through Wine and restores the tracked lockfile after configuration. It clears game/mod auto-install environment variables and configures `.build` explicitly. After an invalid-object linker failure, move the affected object and dependency file to the trash before retrying; disabling the cache does not replace an existing object by itself.

## Inputs and staging

| Component | Build input and action |
| --- | --- |
| DLL | Build the pinned C++/CommonLib sources with Wine/MSVC, release mode, SE and AE enabled, VR disabled. `/Brepro` requests a deterministic linker timestamp |
| ESP | Generate [release/ArcaneVaults-LinkedStorage.json](../release/ArcaneVaults-LinkedStorage.json) through [esp.py](../tools/release/esp.py) |
| PEX | Compile [scripts/Source](../scripts/Source) with Caprica's Skyrim target; normalize compiler metadata and correct its object-size fields |
| PSC | Package the exact source files compiled into PEX |
| INI and translation JSON | Copy the repository's `ini/` files |
| UI | Copy the vendored movies under [assets/skyui-lib](../assets/skyui-lib), checking their pinned upstream hashes |

The script stages into a fresh temporary directory under the release results directory. It checks the exact path population declared in `release/inputs.json`, rejects missing, extra, or empty files, validates the assets, creates the ZIP, and reopens it for validation. It archives the candidate, runs packaging tests and only then replaces the single verified ZIP. Temporary staging is removed on success or failure. Compilation or validation failure exits nonzero and leaves the prior ZIP unchanged. The caller must respect the exit status rather than treating an old ZIP as a successful new build.

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

The committed [test guide](../tests/README.md) describes suite selection, fixture data, prerequisites, performance baselines and reports. The [coverage inventory](../tests/COVERAGE.md) records production paths and remaining engine-only verification. Packaging tests exercise invalid records, compressed ESP round-trips, PEX correction/dispatch, static installer data, exact manifest contents and deterministic archive assembly.

The package root corresponds to Skyrim's `Data` directory. Runtime prerequisites such as SKSE, Address Library and SKSE Menu Framework remain external game dependencies. Passing automated checks does not establish Skyrim loading or gameplay; follow the [game acceptance checklist](../tests/game/README.md).
