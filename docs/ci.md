# GitHub Actions

[ci.yml](../.github/workflows/ci.yml) runs on pull requests, pushes to `dev` or `master`, and manual dispatch. A newer run cancels the older run for that branch or pull request. Jobs use Ubuntu 24.04 and read-only repository permissions, except the cleanup job which has `actions: write` to delete temporary artifacts. The workflow does not publish GitHub Releases.

| Job | Work and dependencies |
| --- | --- |
| `plan` | Derive the verification matrix from the required release profile in `tests/manifest.json` |
| `build` | Provision Wine/MSVC, check its toolchain, build the DLL and inventory test executable, run Windows scenarios, and assemble an unverified candidate |
| `Verify (check)` | Run each required source check on its own runner after the candidate build succeeds, with up to eight checks at once and fail-fast disabled |
| `release` | Require successful build and verification jobs, check the complete report population against the candidate's commit/source fingerprint, validate the exact ZIP, run packaging checks, and upload its extracted contents |
| `cleanup` | After successful publication, require the install artifact and delete only this run's candidate/check artifacts |

Keep `release` as the required check in branch rules. It runs even when a dependency fails and reports failure rather than silently skipping publication. Manual dispatch becomes available after the workflow reaches the default branch.

Source checks initialize only the JSON and CommonLib test inputs. Only the ESP editor check installs .NET 10. The build initializes all recursive pinned submodules and runs MSVC, the Windows SDK and Caprica under Wine. Python 3.12 and GCC run portable verification. Performance has a separate runner and retains its existing serial, calibrated measurement policy.

Checks print their captured output in the Actions log on success and failure. Failed checks also emit an error annotation. Provisioning/compiler failures and failed benchmark subprocesses also expose their captured logs. Performance failures print the affected scenario, metric, baseline, observation and limit. Check output stays in Actions logs. Check artifacts contain only the small JSON gate reports.

## Bootstrap

[bootstrap_wine.py](../tools/ci/bootstrap_wine.py) creates `arcanevault-ci` with this checkout at `/repo`, a separate tools directory at `/work`, and the dependency package cache at `/root/.xmake/packages`. Podman's init process reaps Wine child processes. MSVC's `_CL_=/Z7` setting embeds compiler debug information in object files so its PDB server cannot retain CMake output pipes; linker-generated symbols remain available. An existing container must have the expected ownership label, pinned image, compiler setting and all three mounts before it can be started or provisioned.

[provision_wine.sh](../tools/ci/provision_wine.sh) installs the Wine build prerequisites, checks out the documented xmake and msvc-wine commits, downloads the toolchain using the checked-in Visual Studio manifest, and applies the existing adapters and DirectXTK patch. The CI manifest adapter verifies a merge before translating Wine's truncated update exit code to CMake's POSIX notification code. Bootstrap checks cover MSVC and CMake compilation/linking/execution, valid/invalid shaders, and changed/unchanged/invalid manifests. Logs and its completion report go under `results/ci/bootstrap/`.

The Wine cache holds Microsoft download payloads, checksum-verified Caprica assets and xmake dependency packages. Its key includes the bootstrap, Wine adapters/manifest, root xmake configuration, lockfile, submodule URLs and release manifest. Compiler intermediates, Wine prefixes, installed MSVC tools and test results are rebuilt. Pull requests can restore the Wine cache; only successful non-PR build jobs save it. The .NET setup action separately caches NuGet packages using the ESP editor's lockfile.

## Release and artifacts

The local [full release command](release-build.md) still runs every required check before assembly, then tests and atomically promotes the candidate. CI uses the same assembler through [pipeline.py](../tools/ci/pipeline.py), which keeps candidates unverified until every required check report matches the commit and source fingerprint. Missing, duplicate, failed or stale reports block promotion. Checksums bind final packaging verification to the built ZIP.

`candidate-<commit>` is an internal, unverified build artifact. It never replaces the normal install artifact. `check-<commit>-<check>` contains only that check's `report.json`, which final publication needs to verify the complete check population and source identity. Candidate/check names are scoped to the workflow run and overwritten when their job is rerun. Failed runs retain these inputs so failed jobs can reuse successful checks. Earlier job output remains in Actions logs. Build/bootstrap and final packaging report collections are not uploaded.

Only successful final verification uploads `ArcaneVaults-NG-<commit>-<attempt>`. It contains the extracted, validated package files. GitHub supplies the downloadable ZIP with `SKSE` and `Scripts` at its root, so that download is directly installable. Its file contents match the verified local ZIP; GitHub controls the outer archive metadata and compression. Artifacts have 14-day retention. Reports stay outside install ZIPs. Required sanitizers, performance limits, Windows scenarios and exact package checks remain enabled.

After successful publication, cleanup leaves only the install artifact. It checks the install artifact ID returned by the upload job, collects all artifact pages before deletion, matches exact candidate/check names and leaves other names alone. A partially completed cleanup can be retried independently. Fork pull requests have read-only tokens and skip deletion; their temporary artifacts expire normally. After successful cleanup, rerun all jobs to rebuild publication inputs rather than rerunning `release` alone.

The build cleanup removes only its `arcanevault-ci` container. CI does not update the developer's local release ZIP.

## Local reproduction

Install Podman and the host test prerequisites from [tests/README.md](../tests/README.md), including the .NET 10 SDK. Use a new work directory and a container name that is not used by another build.

```bash
python3 tools/ci/bootstrap_wine.py --work-dir /absolute/path/to/ci-tools --container arcanevault-ci
python3 tools/release/build_release.py --container arcanevault-ci
```

Use `--output results/ci/another-bootstrap` for a second bootstrap report. The script rejects an existing report directory. Actual Skyrim loading and gameplay still require the [game acceptance checks](../tests/game/README.md).
