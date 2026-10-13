# Build and dependencies

Sources of truth are [root xmake.lua](../xmake.lua), [CommonLib xmake.lua](../lib/commonlibsse-ng/xmake.lua), [the lockfile](../xmake-requires.lock), and [.gitmodules](../.gitmodules). The root build includes CommonLib's rules; it does not build the other dependency projects.

## Windows build

For Linux, see the [Wine setup and rebuild command](wine-build.md). The native Windows recipe below remains the reference for the intended toolchain.

Use a Windows x64 MSVC environment with a Windows SDK/resource compiler, Git, xmake 3.0.1 or newer, and Ninja available for the configured toolset. The project selects C++23, all-extra warnings, and the `msvc`, `ninja` toolset values. CommonLib supplies Windows system links, public compiler flags, and engine headers.

From the repository root, initialize pinned submodules, explicitly configure a runtime set, and build the DLL. These are source-derived commands, not a tested recipe on this Linux checkout.

```powershell
git submodule update --init --recursive
xmake f -p windows -a x64 -m releasedbg --skyrim_se=y --skyrim_ae=y --skyrim_vr=n
xmake build ArcaneVaults-NG
```

The recursive update also obtains nested projects that are not needed for header-only integrations. Do not use `git submodule update --remote` for a reproducible build. The gitlink commits, rather than branch tips, select dependencies.

| Runtime | Explicit configuration flags |
| --- | --- |
| SE and AE | `--skyrim_se=y --skyrim_ae=y --skyrim_vr=n` |
| SE only | `--skyrim_se=y --skyrim_ae=n --skyrim_vr=n` |
| AE only | `--skyrim_se=n --skyrim_ae=y --skyrim_vr=n` |
| VR only | `--skyrim_se=n --skyrim_ae=n --skyrim_vr=y` |

Modes are `debug`, `releasedbg`, and `release`. Root options default to false, while the included CommonLib file also declares the runtime options with true defaults. Specify all three instead of relying on how duplicate option declarations resolve. The root rejects VR combined with SE/AE; when neither SE nor AE is selected and VR is off, it adds both SE and AE defines anyway.

The target compiles `src/**.cpp`, uses `src/pch.h` as a PCH, and links the `commonlibsse-ng` target. The root's `runtime` rule argument is selected as `se_ae`, `se`, `ae`, or `vr`, but the pinned CommonLib rule does not read that argument. Inspect generated metadata and actual defines when assessing compatibility. Build options alone are not proof of runtime support.

CommonLib generates a resource file and plugin-info C++ file beneath xmake's target autogeneration directory. Its [plugin-info template](../lib/commonlibsse-ng/res/commonlibsse-ng-plugin.cpp.in) emits `SKSEPluginInfo`, with Address Library version independence and independent struct compatibility by default. Plugin name/author/description come from the root rule configuration. Version metadata comes from xmake's version, while startup logging uses `Plugin::VERSION` in [plugin.h](../src/plugin.h). Both currently say 1.0, despite the latest root commit message saying 1.2.

Compilation databases are generated into `.vscode`; CommonLib also enables Visual Studio project autoupdate. Build and editor output are gitignored.

## Installation and packaging

CommonLib's plugin rule installs the target DLL and symbol file into `SKSE/Plugins` beneath the chosen installation directory. Its `after_build` handler invokes installation when the target changes and install files exist. Environment variables can therefore make an ordinary build write into a mod or game directory.

| Environment variable | Installation directory |
| --- | --- |
| `XSE_TES5_MODS_PATH` | `<value>/ArcaneVaults-NG`, takes precedence |
| `XSE_TES5_GAME_PATH` | `<value>/Data` |

Inspect these variables before building. Prefer a disposable mod staging directory for verification. The CommonLib packaging handler uses a `Data` archive prefix and writes to the configured build directory's `packages` subdirectory. Root xmake declares no install files for `ini/`, the ESP, scripts, or interface assets. A DLL build or dependency packaging action does not produce the complete mod.

Use the [complete release build](release-build.md) for the 10-file ZIP. It builds the DLL, generates the ESP, compiles Papyrus, and stages declared assets separately from CommonLib's DLL-only packaging. Runtime layout expected by the source and generated installation rules:

```text
Data/
  ArcaneVaults-LinkedStorage.esp           external companion plugin
  SKSE/Plugins/
    ArcaneVaults-NG.dll                   compiled target
    ArcaneVault/
      ArcaneVaultOverrides.ini            copy from ini/
      ArcaneVaultTranslation.json         copy from ini/
      ArcaneVaultSettings.ini             written by settings code
      ArcaneVaultUserOverrides.ini         written by override editor
      ArcaneVaultRedirects.ini             written in global redirect mode
  Interface/uilib/UILIB_1_ListMenu.swf     upstream SkyUILib movie
  Interface/uilib/buttonArt.swf            upstream SkyUILib asset
  Scripts/                               compiled scripts and their Source/ files
```

The settings code does not create parent directories. Ensure `Data/SKSE/Plugins/ArcaneVault` exists. The two bundled files are runtime data and release-staging inputs; C++ does not compile them.

## Direct submodules

Commit prefixes below identify the documented checkout; obtain current exact pins with `git submodule status` or `git ls-files --stage`. Upstream URLs live in `.gitmodules`.

| Path | Pin prefix | Use in this project |
| --- | --- | --- |
| `lib/commonlibsse-ng` | `8b48fb1b` | Compiled static library or prebuilt, engine RE types, REL relocation, SKSE APIs, logging, metadata/install rules |
| `extern/json` | `734fd305` | Header-only nlohmann JSON used by `Translation.cpp` |
| `extern/simpleini` | `e260c321` | `SimpleIni.h` used by settings, override, and global redirect persistence |
| `extern/sksemenuframework` | `3a65dc01` | `resources/SKSEMenuFramework.h` API wrappers and `ImGuiMCP`; calls installed framework DLL exports |
| `extern/QuickLootIE` | `08dfab1b` | `include/QuickLootAPI.h` and request client; optional runtime integration |
| `extern/xbyak` | `1230a6ce` | Included by the PCH; no first-party Xbyak code emitter found |
| `extern/clib-util` | `7162f73e` | Include path configured; no direct first-party CLIBUtil use found |
| `extern/fmt` | `21d4cc15` | Include path configured; first-party formatting uses `std::format`, no direct fmt use found |

The last three observations are reasons to inspect before touching dependencies, not instructions to remove them. CommonLib's package graph is separate from the vendored include paths.

Nested submodules include CommonLib's `extern/openvr`, plus separate CommonLib copies within QuickLootIE and SKSE Menu Framework. Root compilation does not include the latter projects' build files. OpenVR headers matter to CommonLib source builds with VR enabled. At documentation time all three nested gitlinks reported uninitialized; the direct submodules matched their root pins.

## Package graph and prebuilt behavior

CommonLib requires DirectXMath `2024.02`, DirectXTK `24.2.0`, and spdlog `v1.16.0`. Spdlog is compiled, wide-character enabled, and uses standard formatting. Optional CommonLib settings add SimpleIni, nlohmann JSON, toml11, Xbyak, rapidcsv for VR, or Catch2 for its own tests. Those optional package versions are defined in CommonLib's xmake file. The root lockfile has a `windows|x64` package set and pins package-repository revisions as well as versions, including CMake and Ninja build tools.

CommonLib normally compiles its source. A `lib/commonlibsse-ng.lib` bundle beside its build file selects prebuilt mode. With `GITHUB_ACTIONS` or `COMMONLIB_PREBUILT`, a clean release tag can trigger tag fetching and a SHA256-checked release download. Cache and failure markers live under CommonLib's `build/.prebuilt/<tag>`; a failed fetch falls back to source compilation.

That prebuilt requires SE, AE, and VR all enabled, with `rex_json` and `rex_toml` disabled. The root explicitly forbids that combined runtime set. Do not assume the pinned prebuilt can be used by this root target. Keep prebuilt-triggering environment variables unset for the source recipe and check for an existing bundle if configuration reports a prebuilt mismatch.

## Vendor diagnostics and Windows macros

`src/pch.h` scopes CommonLib's intentional layout-extension warnings C4200/C4201 to dependency headers. The pinned SKSE Menu Framework header has a struct/class declaration mismatch, deprecated UTF conversion and mixed-enum operations; C4099/C4996/C5054 are suppressed only while including that header. The CommonLib target disables C4100 only for Trampoline.cpp, whose API retains unused compatibility parameters. Project warning levels remain unchanged. The PCH also removes Windows GDI's GetObject macro after vendor includes so CommonLib's GetObject method retains its name.
