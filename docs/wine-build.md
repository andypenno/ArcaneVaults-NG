# Wine build on Linux

This builds the Windows x64 DLL with MSVC running through Wine and native Linux xmake. The host needs x86_64 Linux and working rootless Podman. The commands use an Ubuntu container, so the host distribution and home directory do not affect the tool paths. Skyrim is not needed for compilation.

## Tool versions

| Component | Validated version |
| --- | --- |
| Container userspace | Ubuntu 24.04 |
| Wine | 9.0 |
| xmake | 3.0.1, commit `3350cc5abe65608f6ec06f348aeded9ade1a1237` |
| [msvc-wine](https://github.com/mstorsjo/msvc-wine) | Commit `514f8ea34842cd6d831804d0e9658d3a32870ae1` |
| Visual Studio channel | VS 2022, 17.14.41 |
| MSVC | Toolset 14.44.35207, compiler 19.44.35229, x64 |
| Windows SDK | 10.0.26100.0 |
| Native CMake and Ninja | 3.28.3 and 1.11.1 |

Microsoft's channel and Ubuntu package repositories can change. `--msvc-version 17.14` selects a compiler family, not an exact servicing revision. Keep the saved VS manifest and download cache to repeat the package selection; use `--manifest` with that file instead of `--major 17` on later installations. Preserve the container image and installed tool directory when exact tool versions matter.

## Create the environment

Run the host blocks in the same shell, starting at the repository root. Choose a writable tool directory and a container name that does not already exist. Only these host values vary; `/repo` and `/work` remain fixed inside the container, including in the supplied adapters.

```bash
AV_REPO="$(pwd -P)"
AV_WORK="${XDG_DATA_HOME:-$HOME/.local/share}/arcanevault-wine"
AV_CONTAINER=arcanevault-wine-build
mkdir -p "$AV_WORK"
git -C "$AV_REPO" submodule update --init --recursive
podman run -d --name "$AV_CONTAINER" \
  -v "$AV_REPO:/repo" -v "$AV_WORK:/work" \
  docker.io/library/ubuntu:24.04 sleep infinity
```

The following bootstrap runs once in a fresh environment. It installs container packages and builds native xmake; it does not install host packages.

```bash
podman exec "$AV_CONTAINER" bash -eu -c '
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  wine wine64 winbind python3 git msitools cabextract unzip p7zip-full \
  curl wget ca-certificates gcc g++ make cmake ninja-build bison flex \
  pkg-config libreadline-dev libncurses-dev patch
git clone --recursive --branch v3.0.1 https://github.com/xmake-io/xmake.git /work/xmake
git -C /work/xmake checkout 3350cc5abe65608f6ec06f348aeded9ade1a1237
git -C /work/xmake submodule update --init --recursive
git clone https://github.com/mstorsjo/msvc-wine.git /work/msvc-wine
git -C /work/msvc-wine checkout 514f8ea34842cd6d831804d0e9658d3a32870ae1
'
podman exec -w /work/xmake "$AV_CONTAINER" ./configure --prefix=/work/xmake-install
podman exec "$AV_CONTAINER" make -C /work/xmake -j4
podman exec "$AV_CONTAINER" make -C /work/xmake install
```

Download Microsoft's tools using the pinned VS 17.14.41 manifest and apply msvc-wine's case corrections and wrappers. `--accept-license` accepts the Microsoft license referenced by the downloader. The SDK selector omits the final `.0`; the installed directory includes it.

```bash
podman exec "$AV_CONTAINER" python3 -c 'import gzip; from pathlib import Path; Path("/work/vs2022.manifest").write_bytes(gzip.open("/repo/docs/wine/vs2022-17.14.41.manifest.gz", "rb").read())'
podman exec -w /work "$AV_CONTAINER" \
  python3 /work/msvc-wine/vsdownload.py \
  --manifest /work/vs2022.manifest --msvc-version 17.14 --sdk-version 10.0.26100 \
  --architecture x64 --host-arch x64 --accept-license \
  --cache /work/download-cache --dest /work/msvc
podman exec -w /work \
  -e WINEPREFIX=/work/wine -e WINEDEBUG=-all \
  "$AV_CONTAINER" bash /work/msvc-wine/install.sh /work/msvc
podman exec "$AV_CONTAINER" python3 /repo/docs/wine/adapt-toolchain.py
```

The compressed manifest is the saved Microsoft package catalogue used for the validated toolchain. It pins the channel's patch release rather than selecting a newer VS 2022 manifest during bootstrap.

## Patch the dependency recipe

The [DirectXTK patch](wine/directxtk.patch) belongs in xmake's locked package repository, not the mod or CommonLib submodule. Populate this cache before the first configuration so shader compilation uses the patched recipe. These commit and cache values match the root lockfile documented at `8d9644b`; revisit them if that lockfile changes.

```bash
podman exec "$AV_CONTAINER" bash -eu -c '
recipe=/repo/.xmake/linux/x86_64/repositories/64a282d801e6426ca117847bece7d140.lock
git clone --no-checkout https://gitlab.com/tboox/xmake-repo.git "$recipe"
git -C "$recipe" checkout 1c4a5226d098031c7980196c162975781e1627cd
git -C "$recipe" apply --check /repo/docs/wine/directxtk.patch
git -C "$recipe" apply /repo/docs/wine/directxtk.patch
'
```

Skip cloning on subsequent builds. If xmake already created this cache during a failed configuration, apply the patch to that checkout instead. `git apply --reverse --check` confirms an already-applied patch. Clearing `.xmake` loses the recipe patch.

| Adapter | Failure it addresses |
| --- | --- |
| [Toolchain adapter](wine/adapt-toolchain.py), Wine launcher | Closes inherited file descriptors before starting Wine. Background processes otherwise retain xmake's project lock |
| Same adapter, xmake resource detector | xmake 3.0.1 refuses resource-compiler detection on Linux unless its Windows host guard also allows Linux |
| Same adapter, MSVC wrapper | Appends `/cgthreads1` to override CommonLib's `/cgthreads8`. The unchanged `InputMap.cpp` command fails with eight internal threads and passes with one |
| `WINE_MSVC_RAW_STDOUT=1` | Bypasses msvc-wine's output helper, which exits without diagnostics on the one-thread command |
| DirectXTK `BUILD_TOOLS=OFF` | Omits optional XWBTool, whose source paths have inconsistent case |
| DirectXTK shader command | Uses Wine `cmd`, a Windows `Z:` output path, SDK FXC, and native `d3dcompiler_47` |
| DirectXTK batch error check | Replaces `%fxc% || set error=1` with the invocation followed by `if errorlevel 1 set error=1`. Wine otherwise reports failure even after producing the expected shader headers |

The recipe patch assumes SDK 10.0.26100.0. Change its FXC path if selecting another SDK. The toolchain adapter can be run again; its assertions reject unexpected upstream file layouts. These adapters leave release `/O2` optimization and mod/library source unchanged.

## Configure and build

Run this block for the first build and later rebuilds. Keep the [game/mod installation and prebuilt variables](build.md) unset. The command confines installation to `/work/staging` and restores the root lockfile even on failure. Linux tool detection can otherwise change its Windows CMake/Ninja entries and add host dependencies. The generated cross-build lockfile remains in `/work/wine-requires.lock` for inspection.

```bash
podman start "$AV_CONTAINER"
podman exec -w /repo \
  -e XMAKE_ROOT=y -e WINEPREFIX=/work/wine -e WINEDEBUG=-all \
  -e WINE_MSVC_RAW_STDOUT=1 \
  -e PATH=/work/wine-bin:/work/msvc/bin/x64:/work/xmake-install/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
  "$AV_CONTAINER" python3 -c '
from pathlib import Path
import os
import subprocess
for name in ["XSE_TES5_MODS_PATH", "XSE_TES5_GAME_PATH", "GITHUB_ACTIONS", "COMMONLIB_PREBUILT"]:
    os.environ.pop(name, None)
os.environ["XSE_TES5_MODS_PATH"] = "/work/staging"
lock = Path("/repo/xmake-requires.lock")
original = lock.read_bytes()
try:
    subprocess.run(["xmake", "f", "-p", "windows", "-a", "x64", "-m", "release", "--toolchain=msvc", "--sdk=/work/msvc", "--mrc=/work/msvc/bin/x64/rc.exe", "--skyrim_se=y", "--skyrim_ae=y", "--skyrim_vr=n", "-o", ".build", "-y"], check=True)
    subprocess.run(["xmake", "build", "-j4", "ArcaneVaults-NG"], check=True)
    subprocess.run(["xmake", "install", "ArcaneVaults-NG"], check=True)
finally:
    try:
        Path("/work/wine-requires.lock").write_bytes(lock.read_bytes())
    finally:
        lock.write_bytes(original)
'
podman exec "$AV_CONTAINER" python3 /repo/tests/integration/shaders.py
```

`XMAKE_ROOT=y` permits xmake to run as root inside the rootless container. The Python block sets `XSE_TES5_MODS_PATH` only to the disposable staging directory; xmake 3.0.1 does not accept an `--installdir` configuration flag. Four xmake jobs are separate from MSVC's internal thread count. Reduce `-j4` to `-j1` on a machine with insufficient resources; keep the `/cgthreads1` adapter.

The DLL belongs under `.build/windows/x64/release/` in the host checkout. The installed copy is `/work/staging/ArcaneVaults-NG/SKSE/Plugins/ArcaneVaults-NG.dll`, beneath the host tool directory. Inspect the resulting file with `file` and `objdump -p`, including its SKSE exports. Stop the dedicated environment with `podman stop "$AV_CONTAINER"`; starting it again preserves the tools and caches. To retain a build log, redirect the build block's output to a file under `$AV_WORK`.

## Verification boundary

The FXC [regression check](../tests/integration/shaders.py) asserts return code 0 for a valid shader and 1 for an invalid shader. The dependency shader build generated the 187 expected headers. `InputMap.cpp` passed with one internal thread, failed again with eight, then passed again with one.

The release DLL build and the documented configure/build/install block passed with SE and AE enabled and VR disabled. PE inspection confirmed Windows x64 and `SKSEPlugin_Load`, `SKSEPlugin_Query`, and `SKSEPlugin_Version`. The staged DLL matches the build output byte for byte, and the tracked lockfile retains its original bytes. A fresh locked-recipe clone and patch application passed; running the toolchain adapter twice passed its assertions.

The fresh bootstrap recipe is edited, not verified from an empty tool directory. It consolidates the commands and versions used to establish the working environment. This environment cannot verify Skyrim loading or gameplay. Use the [complete release build](release-build.md) to generate the mod ZIP after setting up this toolchain.
