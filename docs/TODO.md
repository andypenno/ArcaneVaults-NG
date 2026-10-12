# In-game feedback

User-reported issues and requests. Unchecked issues have unverified root causes. Completed corrections passed code-level checks; in-game verification remains outstanding.

## Corrections to previous commits

- [x] Alchemy Transfer All still leaves ingredients behind. Sorting through the Sort chest works, but the Alchemy menu needs the same coverage. Related commit `9ff8694`.
- [x] Remove the Valuables entry from the Treasure menu. That navigation link was not requested. Related commit `1fd956d`.
- [x] Put Open first and Exit second in the Valuables menu, ahead of the Septim actions. Related commit `1fd956d`.
- [x] Make Trade's rejection message explicit that favourited items will not be sold. The current message sounds like the item value is too high. Related commit `e45e4db`.
- [x] Remove Trade's sale-value limit and the limit wording from its message. Selling multiple copies must remain supported. Related commit `e45e4db`. Quotes use 64-bit totals without a mod-defined cap. Skyrim's signed 32-bit Septim capacity is still checked before removal to prevent item loss.

## Bugfixes

- [x] Ordinary spell scrolls do not automatically sort. Shared classification now recognises native ScrollItem forms, including mod-added scrolls, while preserving explicit overrides. Native Sort, Quick Transfer, protection, and manual quantity checks pass; gameplay is unverified.
- [x] Some container assignments are lost when loading a save. Global mode now also records dynamic bindings in the save, and static global bindings retain cached plugin-local identifiers when unloaded. Native persistence checks pass; Hearthfire and Solar's Portable Containers still need in-game verification. Previously lost dynamic bindings must be reassigned once.
- [x] Welkynd Stones appear to disappear during sorting. They should go into Treasure. Added the Rare Curios record override and verified Treasure routing; other plugins' stone identities remain unverified.
- [x] Quick Transfer removes worn rings when a mod allows additional equipped items. Shared player transfers retain native worn checks and consult the standard GetEquipped condition without mod-specific branches. Native checks cover ten virtual rings, unequipped spares, changed hooks, and vanilla fallback. Mods exposing only private worn state remain undetectable; gameplay is unverified.
- [x] Transfers stop at 9999 items. Sort leaves the excess behind; crafting loans lend the full stack but return only 9999, leaving the rest on the character. Category transfers now retry observed partial removals; 30000-item Sort and non-gem crafting-loan cases pass with a simulated 9999-per-call cap.
- [x] Jewelry and Valuables archives also gather helmets and clothing. Jewelry filtering must exclude those items. Shared classification now excludes helmets and body apparel from accessory-slot fallback.
- [x] Books cannot be selected for Quick Transfer. Separated the checkbox ImGui ID from its Books header; toggling and saving are checked.
- [x] Restore consistent menu traversal from an Arcane Vault assignment. Vaults without submenus can return to the previous menu, but vault submenus only offer Exit. Submenus reached through Arcane Vault should offer Back to the originating menu; opening a container assigned directly to that vault should not show Back. Added source-handle/page context, reset on direct activation, assignment, and game load. Native menu and close-callback checks pass.

## New features

- [x] Learn user classification overrides from mismatched manual deposits. Default-off Options toggle, broad vault categories, specific archive categories, queued confirmations during deposits, visit-scoped decline suppression, automatic-transfer suppression, and save-failure rollback are implemented. Personal, composite Valuables, soul-gem storage, Junk, Trade, Sort, and Ignore are excluded. Native checks pass; gameplay is unverified.
- [x] Add a separate Quantities page in the SKSE configuration menu and move the existing ammunition, Septim, and empty soul-gem reserve controls there. Defaults and General INI keys are unchanged. Sale Percentage remains in Options. Native UI checks pass; gameplay is unverified.
- [x] Review hard-coded item quantities. Keys and Books withdraw up to a fixed one per base record. Alchemy and Scrolls have configurable manual Keep N/Take Up To N targets in Quantities, default 1 and 3. Quick Transfer policy is unchanged. Operational sentinels and engine safeguards remain fixed. Native checks pass; gameplay is unverified.
- [x] Add an Empty Soulgems menu action to withdraw up to the configured carried reserve. Take Up To N tops up empty copies per base record, counts carried empties, and leaves filled or excess carried gems untouched. Take All remains available. Native checks pass; gameplay is unverified.
- [x] Add default-off Keep Selected Ammunition in Options. Enabled Keep/Quick Transfer retains N per equipped or favourited type and deposits other eligible ammunition. Disabled mode preserves selected stacks and keeps N per other type. Take Up To N withdraws shortfalls for selected types when enabled, or every stored type when disabled. Native checks pass; gameplay is unverified.
- [x] Add an easy-to-use Quick Transfer ignore list. Sneak-activate Arcane Vault or Sort to deposit examples into a separate picker; close to register base records and return copies. Global stable identifiers, SKSE search/removal/confirmed clearing, and default-on Return Ignored Items are implemented. Native checks pass; gameplay is unverified.
- [x] Add Books archives for Spell Tomes and Skill Books, plus a separate Notes vault with Recipes and Treasure Maps archives. Native book flags/recipe keyword and verified vanilla map overrides classify records; mod-added maps can use TreasureMap overrides. Notes has its own Quick Transfer toggle. Native checks pass; gameplay is unverified.

- [x] Include eligible Junk items in crafting loans at recognized benches. Borrowed excess returns to Junk before category-based returns. Native count/consumption/protection/partial-transfer checks pass; gameplay is unverified.

- [ ] Add a Stolen Items archive gathering stolen copies from the main vaults, excluding Sort, Ignore, and Trade. Mixed stacks must contribute only stolen copies, preserve item metadata, and return copies to their source vaults. Add a default-off SKSE option enabling Open, Exit, and Remove All Stolen Tags actions. Clearing tags must preserve counts and other metadata, then leave the archive empty on its next opening.
