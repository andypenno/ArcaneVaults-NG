using System.Globalization;
using System.Text.Json;
using Mutagen.Bethesda;
using Mutagen.Bethesda.Plugins;
using Mutagen.Bethesda.Skyrim;

try
{
    if (args.Length != 2 && args.Length != 5)
        throw new ArgumentException("Usage: inspect INPUT | rename-container INPUT OUTPUT LOCAL_HEX_ID NAME");
    if (args[0] != "inspect" && args[0] != "rename-container")
        throw new ArgumentException("Unknown command.");
    if ((args[0] == "inspect" && args.Length != 2) || (args[0] == "rename-container" && args.Length != 5))
        throw new ArgumentException("Wrong number of arguments for command.");

    var input = Path.GetFullPath(args[1]);
    var mod = SkyrimMod.Create(SkyrimRelease.SkyrimSE)
        .FromPath(input)
        .Mutable()
        .ThrowIfUnknownSubrecord(true)
        .Construct();

    if (args[0] == "inspect")
    {
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            plugin = mod.ModKey.ToString(),
            masters = mod.ModHeader.MasterReferences.Select(m => m.Master.ToString()),
            records = mod.EnumerateMajorRecords().GroupBy(r => r.GetType().Name)
                .OrderBy(g => g.Key).ToDictionary(g => g.Key, g => g.Count()),
            containers = mod.Containers.OrderBy(c => c.FormKey.ID).Select(c => new
            {
                id = c.FormKey.ID.ToString("X6"), c.EditorID, name = c.Name?.String
            })
        }, new JsonSerializerOptions { WriteIndented = true }));
        return 0;
    }

    var output = Path.GetFullPath(args[2]);
    if (!string.Equals(Path.GetFileName(input), Path.GetFileName(output), StringComparison.Ordinal))
        throw new ArgumentException("Output must retain the input plugin filename in a different directory.");
    if (File.Exists(output))
        throw new ArgumentException("Output already exists; overwriting is refused.");
    if (!uint.TryParse(args[3], NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out var id)
        || id > 0xFFFFFF)
        throw new ArgumentException("Use a local hexadecimal form ID without the load-order prefix or 0x.");
    if (string.IsNullOrWhiteSpace(args[4]))
        throw new ArgumentException("Container name cannot be blank.");
    var container = mod.Containers.SingleOrDefault(c => c.FormKey == new FormKey(mod.ModKey, id))
        ?? throw new ArgumentException("No local container has that form ID.");
    container.Name = args[4];

    Directory.CreateDirectory(Path.GetDirectoryName(output)!);
    // A label edit must retain the existing master order and form allocation boundary.
    mod.BeginWrite.ToPath(output)
        .WithLoadOrderFromHeaderMasters()
        .WithNoDataFolder()
        .NoMastersListContentCheck()
        .NoNextFormIDProcessing()
        .Write();
    Console.WriteLine(output);
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine(error.Message);
    return 1;
}
