#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
packages=(wine wine64 winbind python3 git msitools cabextract unzip p7zip-full curl wget
          ca-certificates gcc g++ make cmake ninja-build bison flex pkg-config
          libreadline-dev libncurses-dev patch)
if ! dpkg-query -W "${packages[@]}" >/dev/null 2>&1; then
    apt-get update
    apt-get install -y --no-install-recommends "${packages[@]}"
fi

checkout() {
    local url=$1 revision=$2 destination=$3
    if [[ ! -d "$destination/.git" ]]; then
        git init "$destination"
        git -C "$destination" remote add origin "$url"
        git -C "$destination" fetch --depth=1 origin "$revision"
        git -C "$destination" checkout --detach FETCH_HEAD
    fi
    [[ $(git -C "$destination" rev-parse HEAD) == "$revision" ]]
}

checkout https://github.com/xmake-io/xmake.git 3350cc5abe65608f6ec06f348aeded9ade1a1237 /work/xmake
git -C /work/xmake submodule update --init --recursive --depth=1
if [[ ! -x /work/xmake-install/bin/xmake ]]; then
    (cd /work/xmake; ./configure --prefix=/work/xmake-install; make -j4; make install)
fi
checkout https://github.com/mstorsjo/msvc-wine.git 514f8ea34842cd6d831804d0e9658d3a32870ae1 /work/msvc-wine
if [[ ! -f /work/msvc/bin/x64/cl.exe ]]; then
    python3 -c 'import gzip; from pathlib import Path; Path("/work/vs2022.manifest").write_bytes(gzip.open("/repo/docs/wine/vs2022-17.14.41.manifest.gz", "rb").read())'
    python3 /work/msvc-wine/vsdownload.py --manifest /work/vs2022.manifest \
        --msvc-version 17.14 --sdk-version 10.0.26100 --architecture x64 --host-arch x64 \
        --accept-license --cache /work/download-cache --dest /work/msvc
    WINEPREFIX=/work/wine WINEDEBUG=-all bash /work/msvc-wine/install.sh /work/msvc
fi
python3 /repo/docs/wine/adapt-toolchain.py
if [[ ! -f /work/msvc/bin/x64/mt-wine ]]; then
    mv /work/msvc/bin/x64/mt /work/msvc/bin/x64/mt-wine
fi
install -m 755 /repo/tools/ci/manifest.py /work/msvc/bin/x64/mt

recipe=/repo/.xmake/linux/x86_64/repositories/64a282d801e6426ca117847bece7d140.lock
checkout https://gitlab.com/tboox/xmake-repo.git 1c4a5226d098031c7980196c162975781e1627cd "$recipe"
if ! git -C "$recipe" apply --reverse --check /repo/docs/wine/directxtk.patch >/dev/null 2>&1; then
    git -C "$recipe" apply --check /repo/docs/wine/directxtk.patch
    git -C "$recipe" apply /repo/docs/wine/directxtk.patch
fi

export XMAKE_ROOT=y WINEPREFIX=/work/wine WINEDEBUG=-all WINE_MSVC_RAW_STDOUT=1
export PATH=/work/wine-bin:/work/msvc/bin/x64:/work/xmake-install/bin:$PATH
xmake --version
smoke=$(mktemp -d /work/ci-smoke.XXXXXX)
trap 'rm -rf "$smoke"' EXIT
(
    cd "$smoke"
    printf '#include <stdio.h>\nint main(void){puts("MSVC/Wine smoke passed");return 0;}\n' > smoke.c
    cl.exe /nologo smoke.c /Fe:smoke.exe
    wine smoke.exe
)
python3 /repo/tests/integration/shaders.py
python3 - <<'PY'
from pathlib import Path
import subprocess
import tempfile

with tempfile.TemporaryDirectory(dir='/work') as temporary:
    directory = Path(temporary)
    (directory / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nproject(probe C CXX)\nadd_executable(probe probe.cpp)\n')
    (directory / 'probe.cpp').write_text('int main(){return 0;}\n')
    subprocess.run(['cmake', '-G', 'Ninja', '-S', str(directory), '-B', str(directory / 'build'),
        '-DCMAKE_SYSTEM_NAME=Windows', '-DCMAKE_C_COMPILER=/work/msvc/bin/x64/cl.exe',
        '-DCMAKE_CXX_COMPILER=/work/msvc/bin/x64/cl.exe', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded'],
        check=True, timeout=60)
    subprocess.run(['cmake', '--build', str(directory / 'build')], check=True, timeout=60)
    subprocess.run(['wine', str(directory / 'build/probe.exe')], check=True, timeout=30)
    print('CMake compiler checks, incremental manifest link and execution passed')
with tempfile.TemporaryDirectory(dir='/work') as temporary:
    directory = Path(temporary)
    source, output = directory / 'input.manifest', directory / 'output.manifest'
    source.write_text('<?xml version="1.0"?><assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0"/>')
    command = ['mt', '/nologo', '/manifest', str(source), '/out:' + str(output), '/notify_update']
    for expected in (187, 0):
        result = subprocess.run(command).returncode
        assert result == expected, (result, expected)
    source.write_text('invalid manifest')
    result = subprocess.run(command).returncode
    assert result not in (0, 187), result
    print('Manifest changed, unchanged and invalid-input checks passed')
PY
