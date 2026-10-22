# Project knowledge base

Arcane Vaults NG is a Windows x64 SKSE plugin for Skyrim. It binds world containers or linked activators to storage references supplied by a companion ESP, presents storage menus, classifies and transfers items, and optionally lends stored materials while crafting. There is no network storage implementation.

These notes are for agents changing the project. They describe the source and release inputs, not a verified game session. Re-read the named source when making a change.

| Task | Read |
| --- | --- |
| Configure, build, install, or change dependencies | [Build and dependencies](build.md) |
| Account for every release file and source input | [Release files and source inputs](distribution.md) |
| Produce a complete ZIP or import a new upstream release | [Complete release build](release-build.md) |
| Build on Linux through Wine | [Wine build on Linux](wine-build.md) |
| Edit companion ESP records through code on Linux | [Scripted ESP editing](esp-editing.md) |
| Understand startup, hooks, events, and menu control | [Runtime architecture](architecture.md) |
| Change transfers, sorting, categories, containers, or save data | [Storage and persistence](storage.md) |
| Change settings, overrides, translations, hotkeys, or integrations | [Configuration and integrations](configuration.md) |
| Locate a change, verify it, or check known limitations | [Development and verification](development.md) |

## Source map

Paths below are relative to the repository root. Headers hold declarations and singleton state; corresponding C++ files hold behavior unless noted.

| Files | Responsibility |
| --- | --- |
| [xmake.lua](../xmake.lua), [xmake-requires.lock](../xmake-requires.lock), [.gitmodules](../.gitmodules) | Plugin target, locked packages, dependency repositories |
| [src/main.cpp](../src/main.cpp), [src/plugin.h](../src/plugin.h), [src/pch.h](../src/pch.h) | SKSE entry point, local version constants, shared engine/API includes |
| [src/Utility.cpp](../src/Utility.cpp), [src/Utility.h](../src/Utility.h) | Companion form registry, recipe caches, assignment eligibility, bench detection, configuration spells |
| [src/ItemClass.cpp](../src/ItemClass.cpp), [src/ItemClass.h](../src/ItemClass.h) | Container/category enums, bit masks, category text, classification |
| [src/Stores.cpp](../src/Stores.cpp), [src/Stores.h](../src/Stores.h) | Shared transfer operations, message boxes, animation polling, storage menu actions |
| [src/Events.cpp](../src/Events.cpp), [src/Events.h](../src/Events.h) | Engine hooks, container-close callbacks, crafting loans, hotkey events |
| [src/RedirectManager.cpp](../src/RedirectManager.cpp), [src/RedirectManager.h](../src/RedirectManager.h) | Source-to-destination map and linked-container activation blocking |
| [src/ContainerMenu.cpp](../src/ContainerMenu.cpp), [src/ContainerMenu.h](../src/ContainerMenu.h) | SkyUILib destination selection and selection state |
| [src/Serialization.cpp](../src/Serialization.cpp), [src/Serialization.h](../src/Serialization.h) | SKSE save/load/revert callbacks |
| [src/Settings.cpp](../src/Settings.cpp), [src/Settings.h](../src/Settings.h) | INI options, global redirects, bundled/user classification overrides |
| [src/AVUI.cpp](../src/AVUI.cpp), [src/AVUI.h](../src/AVUI.h) | SKSE Menu Framework settings and override editor |
| [src/Translation.cpp](../src/Translation.cpp), [src/Translation.h](../src/Translation.h) | Flat JSON string lookup |
| [src/Papyrus.cpp](../src/Papyrus.cpp), [src/Papyrus.h](../src/Papyrus.h) | Two native functions on the external `ArcaneVaults` script |
| [src/Compatibility.h](../src/Compatibility.h) | QuickLoot opening-menu callback, implemented in the header |
| [include/HelperFunctions.h](../include/HelperFunctions.h) | Inline engine/ImGui keyboard, mouse, and gamepad code conversion |
| [ini/ArcaneVaultOverrides.ini](../ini/ArcaneVaultOverrides.ini), [ini/ArcaneVaultTranslation.json](../ini/ArcaneVaultTranslation.json) | Bundled classification data and English strings |
| [.gitignore](../.gitignore) | Excludes build output, local xmake/editor state, archives, and compilation databases |
| [tools/esp/Program.cs](../tools/esp/Program.cs), [tools/esp/check.py](../tools/esp/check.py) | Mutagen CLI and independent ESP edit/reopen check |
| [tools/release](../tools/release), [release/inputs.json](../release/inputs.json) | Source import, ESP generation, PEX validation, and release assembly |
| [release/ArcaneVaults-LinkedStorage.json](../release/ArcaneVaults-LinkedStorage.json), [release/upstream](../release/upstream) | Working ESP definition and imported upstream baseline |
| [scripts/Source](../scripts/Source), [scripts/Imports](../scripts/Imports), [assets/skyui-lib](../assets/skyui-lib) | Papyrus source/interfaces and pinned distributed UI movies |

The root [README.md](../README.md) only names the project. The C++ plugin has no test target or CI configuration. The ESP and release tools have runnable checks in their respective guides. Dependency repositories contain their own tooling; that is not the plugin's verification setup.

## Evidence boundary

The checkout contains the eight direct submodules, but some nested submodules are uninitialized. Native Windows build commands were derived from the scripts. The [Wine guide](wine-build.md) describes container setup on x86_64 Linux. The repository includes the authored inputs and pinned movies needed by the [release build](release-build.md). Build and artifact checks do not verify Skyrim gameplay.
