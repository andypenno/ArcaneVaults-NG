# Project context

Start with [docs/README.md](docs/README.md). Read the document for the area being changed, then verify its claims against current source.

| Area | Reference |
| --- | --- |
| Build, install, submodules, packages, runtime flags | [docs/build.md](docs/build.md) |
| Release contents and asset sources | [docs/distribution.md](docs/distribution.md) |
| Build the ZIP, import upstream assets, validate packaging | [docs/release-build.md](docs/release-build.md) |
| Wine build on Linux | [docs/wine-build.md](docs/wine-build.md) |
| Edit companion ESP records through code | [docs/esp-editing.md](docs/esp-editing.md) |
| Startup, hooks, events, menus, crafting flow | [docs/architecture.md](docs/architecture.md) |
| Transfers, classification, reference IDs, persistence | [docs/storage.md](docs/storage.md) |
| Settings, overrides, translations, external APIs | [docs/configuration.md](docs/configuration.md) |
| Change paths, known limitations, verification | [docs/development.md](docs/development.md) |

Change shared operations after checking their callers. Preserve inventory protections, save-format validation, reference lifetimes, and game-thread access rules described in the docs.

Harden compatibility through standard engine or public API contracts while preserving vanilla behavior. Avoid mod-specific branches and private mod state when a shared contract can solve the problem.

Read the working ESP definition and script sources before changing records or wiring. Preserve the imported upstream baseline for three-way updates. Keep dependency changes explicit; do not update submodule pins as routine setup.

Check build installation environment variables before compiling because CommonLib can auto-install. A Linux static check does not verify this Windows SKSE plugin. Report build and game checks actually performed, and identify verification that could not run.

Update the owning docs when changing a documented contract. Keep project knowledge there rather than duplicating it in this file.
