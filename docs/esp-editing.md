# Scripted ESP editing on Linux

[tools/esp](../tools/esp/Program.cs) uses Mutagen to read and edit Skyrim SE plugins on native Linux .NET 10. No Wine, GUI, game installation, or registry discovery is needed for the tested container-label edit. Mutagen 0.54.4 and its transitive dependencies are pinned by [packages.lock.json](../tools/esp/packages.lock.json).

The tool accepts explicit file paths. `inspect` prints the master list, record counts, and container IDs/names as JSON. `rename-container` changes one local container's embedded name and saves a new ESP. It refuses existing output, blank names, invalid IDs, missing containers, and a changed plugin filename. Keep the original filename in a separate output directory so the plugin identity and self-references remain stable.

## Setup and verification

Python 3 and the [.NET 10 SDK](https://learn.microsoft.com/dotnet/core/install/linux) are required. The following Bash block installs a local SDK under a user-owned tool directory if needed. Set `repo` to an absolute path and choose an unused `input_esp` path; generation refuses existing output. The check creates and removes disposable edited output outside the repository.

```bash
set -eu
repo=/absolute/path/to/ArcaneVaults-NG
input_esp="$repo/build/esp-editing/ArcaneVaults-LinkedStorage.esp"
esp_tools="${XDG_DATA_HOME:-$HOME/.local/share}/arcanevault-esp-tools"
mkdir -p "$esp_tools"
dotnet_cli="$esp_tools/dotnet/dotnet"
if [ ! -x "$dotnet_cli" ]; then
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o "$esp_tools/dotnet-install.sh"
    bash "$esp_tools/dotnet-install.sh" --channel 10.0 --install-dir "$esp_tools/dotnet" --no-path
fi
python3 "$repo/tools/release/esp.py" generate "$repo/release/ArcaneVaults-LinkedStorage.json" "$input_esp"
"$dotnet_cli" restore "$repo/tools/esp/ArcaneVaults.Esp.csproj" --locked-mode
"$dotnet_cli" build "$repo/tools/esp/ArcaneVaults.Esp.csproj" --configuration Release --no-restore
"$dotnet_cli" "$repo/tools/esp/bin/Release/net10.0/ArcaneVaults.Esp.dll" inspect "$input_esp"
python3 "$repo/tools/esp/check.py" "$dotnet_cli" "$input_esp"

# Optional real label edit. Choose an ID from inspect and an unused output directory.
# "$dotnet_cli" "$repo/tools/esp/bin/Release/net10.0/ArcaneVaults.Esp.dll" \
#     rename-container "$input_esp" /absolute/path/to/output/ArcaneVaults-LinkedStorage.esp \
#     000D6E "Arcane Vault"
```

Native Linux SDK 10.0.401 built the tool and passed the check against the Arcane Vaults 1.2 companion ESP. It loaded 32 containers, 32 placed references, one cell, two spells, and two magic effects. The check renamed local container `000D6E`, saved, and reopened it. Independent binary assertions compared all 70 records including TES4 and the group hierarchy. Only the chosen container's `FULL` payload changed. The original input stayed byte-identical, and invalid-edit/overwrite checks passed. No `Skyrim.esm` file was supplied.

The check validates this companion ESP, not arbitrary plugins. Its independent subrecord comparison expects one embedded container name and ordinary subrecord lengths. The editor fails on unknown subrecords instead of silently dropping them. Names use Mutagen's default Skyrim embedded-string encoding, Windows-1252; the check uses an ASCII name. Localized plugins and other encodings have not been verified.

## Adding a vault or archive

The current Mutagen CLI provides the read/edit/write route and a label operation. The [release tools](release-build.md) generate the ESP from its working definition. Extend the C# operation when a specific destination is requested. Mutagen exposes typed container, placed-object, and cell records, so those changes can be expressed and tested in code without asking a user to operate an editor.

Read [storage.md](storage.md) and [distribution.md](distribution.md) before adding records. Preserve existing form IDs and links, allocate new IDs without collisions, attach the reference to the intended cell group, and update the header's next-form boundary for new records. The label-only writer deliberately preserves the current boundary; do not reuse that setting for record allocation. Update the C++ destination enum/registry, operations, and translation keys together with the ESP.

After a typed edit, import the resulting ESP into the working record definition as described in [release-build.md](release-build.md). Resolving or validating links to Skyrim base records would require the actual master files; the tested name change does not resolve those links. Neither binary checks nor a successful DLL build verify Skyrim gameplay.

The API's explicit-path import and export behavior is described in Mutagen's [importing](https://mutagen-modding.github.io/Mutagen/plugins/Importing/) and [exporting](https://mutagen-modding.github.io/Mutagen/plugins/Exporting/) documentation. Avoid automatic game/load-order discovery on Linux.
