# Game acceptance

Record the exact verified ZIP checksum, Skyrim runtime, SKSE version, load order/profile and starting inventory. Use a disposable mod profile and saves. Automated release verification does not replace these checks.

1. Load the plugin, exercise registration/configuration spells, and check behaviour with optional integrations absent.
2. Run Quick Transfer from Arcane Vault, an assigned container and hotkey. Cover a protected loadout with no sortable items and large sortable inventories.
3. Keep worn and favourited equipment while transferring ordinary and differently enchanted/renamed copies sharing their bases. Compare quantities and per-copy metadata in both inventories.
4. Confirm the sorting sigil visibly animates, one completion appears, menus close/return correctly and player input is restored.
5. Exercise every crafting station with ordinary and All Crafting Materials loans. Consume some items, leave early, change settings during a session and inspect final inventories. Items must stop arriving after exit and unused loans must restore according to their contracts.
6. Open representative vaults/archives, withdraw/keep/store items and confirm parent returns. Cover construction resources and the reported missing Dragon Heartscales scenario with explicit counts in player/Treasure/Valuables.
7. Save/reload and start a new game. Check global/per-save assignments, changed load order and stale-request cancellation.

For Sawn Logs, buy 100, build at a carpenter station, exit and reopen. Remaining logs must stay on the player and remain usable; their weight and menu visibility stay controlled by Skyrim. Repeat with All Crafting Materials and Return Ignored Items disabled. Check that older stored stock returns without duplication after loading the save or entering crafting. A user override replacing Ignore should restore the chosen storage policy. Confirm ordinary ignore-list materials still follow their existing crafting-return behaviour.

Store observations and timings under ignored `results/game/<run-id>/`. Record failures as failures or unreproduced reports, not a simulated test success. A proper release needs acceptance evidence for engine behaviours affected by its changes.
