# Release files and source inputs

The [complete release build](release-build.md) produces the same 10 file paths as Arcane Vaults 1.2. The root xmake target builds the DLL; the release script generates the ESP, compiles Papyrus, and stages declared assets.

| Release path | Source or authoring input | Current build coverage |
| --- | --- | --- |
| `SKSE/Plugins/ArcaneVaults-NG.dll` | Repository C++ and pinned dependencies | Compile and link with Wine/MSVC |
| `SKSE/Plugins/ArcaneVault/ArcaneVaultOverrides.ini` | `ini/ArcaneVaultOverrides.ini` | Copy source data |
| `SKSE/Plugins/ArcaneVault/ArcaneVaultTranslation.json` | `ini/ArcaneVaultTranslation.json` | Copy source data |
| `ArcaneVaults-LinkedStorage.esp` | `release/ArcaneVaults-LinkedStorage.json` | Generate authored records |
| `Scripts/Source/ArcaneVaults.psc` | `scripts/Source/ArcaneVaults.psc` | Copy exact compiled source |
| `Scripts/Source/ArcaneSpells.psc` | `scripts/Source/ArcaneSpells.psc` | Copy exact compiled source |
| `Scripts/ArcaneVaults.pex` | `scripts/Source/ArcaneVaults.psc` | Compile with pinned Caprica, normalize PEX |
| `Scripts/ArcaneSpells.pex` | `scripts/Source/ArcaneSpells.psc` and compile-only interfaces | Compile with pinned Caprica, normalize PEX |
| `Interface/uilib/UILIB_1_ListMenu.swf` | `assets/skyui-lib/uilib/UILIB_1_ListMenu.swf` | Copy hash-checked upstream movie |
| `Interface/uilib/buttonArt.swf` | `assets/skyui-lib/uilib/buttonArt.swf` | Copy hash-checked upstream movie |

The ESP is authored record data, separate from the C++ and Papyrus compilers. Its record definition preserves the IDs and script attachments consumed by [Utility.cpp](../src/Utility.cpp). [Scripted ESP editing](esp-editing.md) supports typed changes to a generated plugin; [release-build.md](release-build.md) describes importing those changes back into the definition and updating the upstream baseline.

`ArcaneVaults.psc` declares the two global natives registered in [Papyrus.cpp](../src/Papyrus.cpp). `ArcaneSpells.psc` handles `OnEffectStart`; `SpellType` 0 calls `ContainerRedirect` and 1 calls `OffloadItems`. Both PEX files are compiled from the packaged PSC sources. Compiler flags and the minimal interfaces needed by these sources live under `scripts/Imports` and are excluded from the package.

## SkyUILib provenance

The vendored movies and original release movies are byte-identical to `build/uilib/` in [schlangster/skyui-lib](https://github.com/schlangster/skyui-lib) at commit `6802d39861bfbd5c35248134de73846ec2a6b4cd`. Their revision and checksums are declared in `release/inputs.json`.

That upstream also contains `src-flash/UILIB_1/UILIB_1_ListMenu.fla` and ActionScript. The FLA is an Adobe Flash authoring document. Its tree has no `buttonArt.fla` or automated movie-publication command. Recompiling the menu requires a separate Flash toolchain; the current Wine/MSVC environment does not provide one. Obtaining a pinned upstream SWF is reproducible dependency acquisition, not verification of a Flash source build.

The C++ menu loader requests `uilib/uilib_1_listmenu`. Preserve the distribution's actual filenames and include `buttonArt.swf` when assembling a package; Windows resolves the menu's case difference.

## Which changes affect these files

| Change | Release files affected |
| --- | --- |
| Transfers, sorting rules, inventory protections, crafting loans, persistence, hooks, hotkeys, optional integrations, or runtime compatibility | Rebuild the DLL. Existing spells and storage records can keep their current assets |
| Classify a particular item differently using an existing category | Overrides INI. Changing the classification algorithm or category definitions also changes the DLL |
| Translate or rename an existing translated label | Translation JSON. New keys require their C++ consumers; the destination title `Select destination` is currently hard-coded in `ContainerMenu.cpp` |
| Add/remove a vault or archive, change its underlying container/reference, or change the storage cell | ESP and C++ registry/operations; update translation data for new labels. Preserve established form IDs when retaining existing destinations |
| Change spell names, costs, casting/effect records, or their script attachments/properties | ESP. New native actions or `SpellType` values also require C++ and/or Papyrus changes |
| Change the spell-event dispatcher or native Papyrus interface | Edit PSC, rebuild corresponding PEX, and ship both. Native signature/name changes must match C++ registration and callers |
| Change destination-dialog layout, scrolling widgets, or ActionScript event behavior | List-menu SWF and its Flash source. Changes to the methods/symbols called by C++ also require the DLL |
| Change destination choices, their ordering, the passed title, platform selection, or the C++ close callback | DLL; those values/functions are supplied to the existing movie at runtime |
| Change button glyph artwork | `buttonArt.swf` and its authoring source. Ordinary hotkey changes do not require new artwork |
| Change the SKSE Menu Framework settings interface | DLL through `AVUI.cpp`, plus translation data where used. This interface is separate from the destination-dialog SWF |

The working ESP has `Skyrim.esm` as its sole master. It contains 37 container base records, 37 placed storage references, the `TheVault` cell, two spells, and two magic effects. Keys adds container `0xDC4` and persistent reference `0xDC5`. Ammunition adds container `0xDC6` and persistent reference `0xDC7`. Valuables adds container `0xDC8` and persistent reference `0xDC9`. Filled/Empty Soulgems add bases `0xDCA`/`0xDCC` and persistent references `0xDCB`/`0xDCD`; the imported upstream baseline retains the original 32 pairs. Every placed storage reference matches a form ID registered by `Utility::LoadContainers`. The assignment and transference spells use local IDs `0xDC0` and `0xDC1`. Their effects attach `ArcaneSpells` with `SpellType` 0 and 1 respectively.

The PSC/PEX pair is a bridge to native functions, not the inventory implementation. Changing how `Stores::OffloadItems` works does not itself require recompiling the spell scripts. Renaming `ArcaneVaults.OffloadItems` requires coordinated native registration, source, and PEX changes.

The list-menu movie imports `ButtonArt` from `buttonart.swf` and `$EverywhereMediumFont` from `gfxfontlib.swf`. The package supplies the button movie; Skyrim's interface environment supplies the font library. C++ calls `_root.listDialog.setPlatform`, `initListData`, and `initListParams`, and replaces `exitMenu`. Preserve that interface when replacing or rebuilding the movie.

## What is established

The upstream root commit `8d9644b` supplied none of the mod-specific ESP, PSC, PEX, or SWF files. The repository's release inputs recover the missing authored ESP/PSC data and vendor the verified upstream movies. Released DLL and PEX bytes are recorded only as provenance hashes and are not build inputs.

The imported release's configuration files matched root commit `8d9644b` after newline normalization. The working translation also has the Keys, Ammunition, and Valuables menu strings. The built and released DLLs export `SKSEPlugin_Load`, `SKSEPlugin_Query`, and `SKSEPlugin_Version`, and their Windows version resources say `1.0.0`. The release label `1.2` does not establish a different embedded DLL version. The DLL bytes differ; matching exports and metadata do not prove identical behavior.

Normal builds consume repository authoring inputs and declared tool dependencies. The upstream ZIP is used only for deliberate baseline imports. A Skyrim test remains necessary after packaging.
