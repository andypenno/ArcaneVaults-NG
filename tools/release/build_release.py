"""Build the DLL, ESP, scripts, and exact release ZIP without an upstream release."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import zipfile

from esp import generate_esp
from pex import normalize_pex
from validate import require, validate_files, validate_zip

ROOT = Path(__file__).resolve().parents[2]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_zip(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data, compresslevel=9)


def build(container):
    manifest = json.loads((ROOT / "release/inputs.json").read_text())
    output = ROOT / "build/releases"
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "build.log"
    info = json.loads(subprocess.check_output(["podman", "inspect", container]))[0]
    mounts = {mount["Destination"]: Path(mount["Source"]).resolve() for mount in info["Mounts"]}
    require(mounts.get("/repo") == ROOT, "Build container /repo must mount this checkout")
    require("/work" in mounts, "Build container needs the documented /work tools mount")
    work = mounts["/work"]
    if not info["State"]["Running"]:
        subprocess.run(["podman", "start", container], check=True, stdout=subprocess.DEVNULL)
    for path, expected in manifest["skyui_lib"]["files"].items():
        require(digest((ROOT / path).read_bytes()) == expected, f"Pinned UI asset hash differs: {path}")
    compiler = work / "release-tools/caprica/Caprica.exe"
    dependency = manifest["caprica"]
    archive = work / "release-tools/Caprica.v0.3.0.7z"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(dependency["url"], timeout=60) as response:
            data = response.read()
        require(digest(data) == dependency["sha256"], "Caprica download checksum differs")
        with archive.open("xb") as cached:
            cached.write(data)
    require(digest(archive.read_bytes()) == dependency["sha256"], "Cached Caprica checksum differs")
    with log_path.open("w") as log:
        def run(args, wine=False):
            command = ["podman", "exec", "-w", "/repo"]
            if wine:
                command += ["-e", "WINEPREFIX=/work/wine", "-e", "WINEDEBUG=-all"]
            subprocess.run(command + [container] + args, check=True, stdout=log, stderr=subprocess.STDOUT)

        if not compiler.exists():
            run(["7z", "x", "/work/release-tools/Caprica.v0.3.0.7z", "-o/work/release-tools/caprica", "-y"])
        require(digest(compiler.read_bytes()) == dependency["exe_sha256"], "Caprica executable checksum differs")
        lock = ROOT / "xmake-requires.lock"
        original = lock.read_bytes()
        print("Building Windows x64 DLL; compiler output is in build/releases/build.log", flush=True)
        try:
            command = ["podman", "exec", "-w", "/repo", "-e", "XMAKE_ROOT=y", "-e", "WINEPREFIX=/work/wine",
                       "-e", "WINEDEBUG=-all", "-e", "WINE_MSVC_RAW_STDOUT=1", "-e",
                       "PATH=/work/wine-bin:/work/msvc/bin/x64:/work/xmake-install/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                       container, "python3", "-c", """
import os, subprocess
for key in ['XSE_TES5_MODS_PATH','XSE_TES5_GAME_PATH','GITHUB_ACTIONS','COMMONLIB_PREBUILT']:
    os.environ.pop(key, None)
subprocess.run(['xmake','f','-p','windows','-a','x64','-m','release','--toolchain=msvc','--sdk=/work/msvc','--mrc=/work/msvc/bin/x64/rc.exe','--skyrim_se=y','--skyrim_ae=y','--skyrim_vr=n','-y'],check=True)
subprocess.run(['xmake','build','-j4','ArcaneVaults-NG'],check=True)
"""]
            subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
        finally:
            lock.write_bytes(original)
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=output) as directory:
            stage = Path(directory)
            for name, source in manifest["copies"].items():
                require(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe package path")
                require((ROOT / source).resolve().is_relative_to(ROOT), "Package source must be inside the repository")
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / source).read_bytes())
            definition = json.loads((ROOT / "release/ArcaneVaults-LinkedStorage.json").read_text())
            (stage / "ArcaneVaults-LinkedStorage.esp").write_bytes(generate_esp(definition))
            dll = stage / "SKSE/Plugins/ArcaneVaults-NG.dll"
            dll.parent.mkdir(parents=True, exist_ok=True)
            dll.write_bytes((ROOT / "build/windows/x64/release/ArcaneVaults-NG.dll").read_bytes())
            destination = "Z:\\repo\\" + str((stage / "Scripts").relative_to(ROOT)).replace("/", "\\")
            source_directory = destination + "\\Source"
            print("Generating ESP and compiling Papyrus sources", flush=True)
            run(["wine", "/work/release-tools/caprica/Caprica.exe", "--game=skyrim",
                 f"--import={source_directory};Z:\\repo\\scripts\\Imports",
                 "--flags=Z:\\repo\\scripts\\Imports\\TESV_Papyrus_Flags.flg",
                 f"--output={destination}", "--enable-debug-info=0", "--release", "--ignorecwd",
                 source_directory], wine=True)
            for script in ["ArcaneVaults", "ArcaneSpells"]:
                path = stage / f"Scripts/{script}.pex"
                path.write_bytes(normalize_pex(path.read_bytes(), script + ".psc"))
            files = {str(path.relative_to(stage)): path.read_bytes() for path in stage.rglob("*") if path.is_file()}
            checks = validate_files(ROOT, files)
            temporary_zip = stage / "artifact.zip"
            write_zip(temporary_zip, files)
            require(validate_zip(ROOT, temporary_zip) == checks, "ZIP revalidation differs")
            final = output / "ArcaneVaults-NG.zip"
            os.replace(temporary_zip, final)
            report = {"zip_sha256": digest(final.read_bytes()), "checks": checks,
                      "files": {name: digest(data) for name, data in sorted(files.items())}}
            (output / "artifact.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"Built {final}\nSHA256 {report['zip_sha256']}\nValidated {checks['files']} paths and {checks['esp_records']} ESP records")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", default="arcanevault-wine-build")
    args = parser.parse_args()
    try:
        build(args.container)
    except Exception as error:
        raise SystemExit(f"Release build failed: {error}. See build/releases/build.log")
