# GitHub Actions

[ci.yml](../.github/workflows/ci.yml) runs on pull requests, pushes to `dev` or `master`, and manual dispatch. A newer run cancels the older run for that branch or pull request. The single Ubuntu 24.04 job has a 90-minute limit and read-only repository permissions. It does not publish GitHub Releases.

To block merges on failures, make the `release` job a required check in the repository's branch rules. The workflow does not change those rules. Manual dispatch becomes available after the workflow reaches the default branch.

The checkout includes full Git history for the performance baseline and recursive pinned submodules. Python 3.12 runs the existing test/release scripts; .NET 10 builds the independent ESP editor. GCC executes the portable tests on the host. MSVC, the Windows SDK and Caprica run under Wine in an isolated Podman container.

## Bootstrap

[bootstrap_wine.py](../tools/ci/bootstrap_wine.py) creates `arcanevault-ci` with this checkout at `/repo`, a separate tools directory at `/work`, and the dependency package cache at `/root/.xmake/packages`. Podman's init process reaps Wine child processes. MSVC's `_CL_=/Z7` setting embeds compiler debug information in object files so its PDB server cannot retain CMake output pipes; linker-generated symbols remain available. An existing container must have the expected ownership label, pinned image, compiler setting and all three mounts before it can be started or provisioned.

[provision_wine.sh](../tools/ci/provision_wine.sh) installs the Wine build prerequisites, checks out the documented xmake and msvc-wine commits, downloads the toolchain using the checked-in Visual Studio manifest, and applies the existing adapters and DirectXTK patch. The CI manifest adapter verifies a merge before translating Wine's truncated update exit code to CMake's POSIX notification code. Bootstrap checks cover MSVC and CMake compilation/linking/execution, valid/invalid shaders, and changed/unchanged/invalid manifests. Logs and its completion report go under `results/ci/bootstrap/`.

The Wine cache holds Microsoft download payloads, checksum-verified Caprica assets and xmake dependency packages. Its key includes the bootstrap, Wine adapters/manifest, root xmake configuration, lockfile, submodule URLs and release manifest. Compiler intermediates, Wine prefixes, installed MSVC tools and test results are rebuilt. Pull requests can restore the Wine cache; only successful non-PR runs save it. The .NET setup action separately caches NuGet packages using the ESP editor's lockfile.

## Release and artifacts

The job invokes the same [full release command](release-build.md) used locally. Required tests, sanitizers, the paired performance gate, Windows inventory scenarios and exact ZIP validation remain mandatory. There is no CI-only skip-tests option. The existing performance policy still rejects unresolved timing noise.

Only a successful release command reaches the install-artifact upload. `ArcaneVaults-NG-<commit>-<attempt>` contains the verified `ArcaneVaults-NG.zip`. Downloading a GitHub artifact may add an outer archive; install the inner ZIP. `verification-<commit>-<attempt>` contains bootstrap/release logs, source fingerprints, checksums, provenance and test reports, including available diagnostics after failure. Both have 14-day retention. Results remain outside `build/` and outside the install ZIP.

The cleanup step removes only the job's `arcanevault-ci` container. Hosted runner storage is disposable; the repository's local verified ZIP is not a remote latest-build store. Each successful workflow run retains its own artifact.

## Local reproduction

Install Podman and the host test prerequisites from [tests/README.md](../tests/README.md), including the .NET 10 SDK. Use a new work directory and a container name that is not used by another build.

```bash
python3 tools/ci/bootstrap_wine.py --work-dir /absolute/path/to/ci-tools --container arcanevault-ci
python3 tools/release/build_release.py --container arcanevault-ci
```

Use `--output results/ci/another-bootstrap` for a second bootstrap report. The script rejects an existing report directory. Actual Skyrim loading and gameplay still require the [game acceptance checks](../tests/game/README.md).
