# obelisk-patcher — reverse-engineering notes for Obelisk Miner (com.checkbox.minershminer)

Source: `input/Obelisk_Miner_base.apk` (v2.2.30, build "MinersIdle4", GM runtime data in `assets/game.droid`).
Extracted to `input/extracted/`. String table dumped to `input/strings.txt`, script names to `input/scripts.txt`, objects to `input/objects.txt`.

## Engine / build facts
- GameMaker Studio 2, compiled with **YYC** (options.ini has `[LLVM-Android]`; game.droid has no CODE/VARI/FUNC chunks).
  => All GML logic is native ARM code inside `libyoyo.so`. Function symbols are normally exported as
     `gml_Script_<name>` / `gml_Object_<obj>_<Event>_<n>`, which Ghidra can use directly.
- Manifest has `com.android.vending.splits.required` => this is a **split APK**. `libyoyo.so` lives in
  `split_config.arm64_v8a.apk` (and maybe `split_config.x86_64.apk`). Base alone will not run.
- Embedded scripting: Catspeak v3.3.0 (server "live patches"), GMLive (dev hot-reload, probably inert).
- Server: wss + https://api.idleobeliskminer.com (store/refunds, time, health), accounts.idleobeliskminer.com.
- Purchases: Google Play Billing -> `trigger_server_side_purchase_verification` -> `handle_verify_server_reply` -> `trigger_iap_unlock_function`.
  Server also serves a refund list (`check_for_refunds`, `funRefundGems`, `check_cap_and_refund_idols`).
- Live patches: `patches.dat` holding {patch_id, signature, data}; Catspeak code verified with ed25519
  public key `ox0uTKj1ynk1vDT7Zku1QxczuuI3FgkUtnV6E1UskoM=` (STRG index 506) via Java ext `Ed25519GM`.
  Swapping that 44-char key for our own (same length, no re-layout) would let us sign our own patches.

## Save format
- Files: `SaveNew.txt` (+ `SaveNew.txt.bkb` backup), legacy `Save.dat`, `saveSteam.dat`; export = `Idle_Obelisk_Miner_Backup_*.txt`.
- `encrypt_save_string` / `decrypt_save_string` wrap it; algorithm unknown until we see libyoyo.so or a sample save.
- Save keys of interest: `valuepacks`/`valuePack_N`, `perks`/`perk_N`, `gem_unlocks`/`gemUnlock_N`,
  `gem_upgrades`/`gemUpgrade_N`, `gem_perks`/`gemPerk_N`, `gems`, `founder_counter`, `is_pet_skin_a_owned_`, `gift_codes`.

## IAP SKUs (all `iap_shminer_*`)
gems1-4, founders, permadrone, perk2xore, perk2xpp, perk2xpickaxedamage, perk3xbombdamage, bundle_2xorepp, bundle_damage,
anglerbundle, arcanist, archbundle, ascensionbundle, baller, bankersbundle, biggerbanker, bigvalue, biggervalue, battery, bomber,
capitalistbundle, chiefexecutive, craftmasterbundle, divinebundle, doubledivine, dronecatalyst, fishingbundle, frogfrenzy, fuelmaster,
giftlovers, gofast, goldenlootbug, goldenorebundle, halfway, investment, legendaryhauler, limitedsale1, lootbugbonanza, megabomb,
mythicpack, omniportal, pettrainer, polychromepotency, progressionbundle, radiant, resourcepackmythic_multi, singularity,
skillpointpack, skillpointsgalore, skillsurgebundle, spellslinger, stargazingbundle, supergiantbundle, superstonks, threequarter,
transmuter, treasure, veinextractor, voidoverdrive.
Relevant scripts: add_all_iaps, add_iap, funIapSetValuePackInfo, funIapSetPerkBundles, hasValuePack, set_vip_benefits,
funCheckFounderPrereqs, funIsLimitedTimeSaleActive, upg_buy, do_we_have_the_currencies_to_buy_this.

## Dev/debug menu still compiled in
Strings 9306-9339 and 11566-11583: "Give Everything", "Complete Game", "Get gems", "Remove Value Packs", "Toggle Founder",
"Set all ores to", "Cheat 1hr Offline", "Opening debug menu", etc. Gate unknown (controllerDev / funCheatVars /
funInstantCheatFlag / "Cheating Flag: "). Finding the gate in libyoyo.so is likely the fastest path to a test harness.

## Candidate approaches (pick after seeing libyoyo.so)
1. Native patch of `gml_Script_hasValuePack` etc. in libyoyo.so so each pack reads as owned once its precondition passes; re-sign splits.
2. Save editor: decrypt SaveNew.txt, set valuePack_/perk_ flags, re-encrypt. Needs the cipher from libyoyo.so.
3. Signed live patch: replace ed25519 pubkey in game.droid, ship our own Catspeak patch in patches.dat.

## Update 2026-10-19 evening — save format + BlueStacks workflow (CONFIRMED)
- Save is NOT encrypted. `files/save.dat` = uppercase hex of a GM buffer: u32 403,1,1,namelen,"save",1,textlen, then plain INI (CRLF).
  `encrypt_save_string`/`decrypt_save_string` (RC4 via gml_Script_arc4) are only used for cloud/export paths.
- 46 INI sections; P2W-relevant: [valuepacks] valuePack_0..48, [perks] perk_0..3, [gem_unlocks], [gem_perks], [gem_upgrades],
  [single_vars] gems, isFounder, founder_counter, isPurchaseLimitIncreased, mythicPackStockBought, [firesale].
- BlueStacks 5 (Pie64, 1920x1080) reachable from WSL only via Windows adb: $ADB (Windows adb.exe) -s 127.0.0.1:5555
  (must run with sandbox disabled). Root/su and run-as are both broken there; bst.feature.rooting resets to 0 on launch.
- Working no-root round trip: `adb backup -f x.ab -noapk com.checkbox.minershminer` (allowBackup=true; Android 9 OK; user must
  click confirm in BlueStacks — uiautomator can't see the dialog) -> tools/abtool.py unpack -> tools/savetool.py set ... ->
  abtool.py pack -> `adb restore x.ab` (force-stop game first, user clicks confirm) -> relaunch. Verified with a miner-name change.
- Phone (Pixel 6, Android 16) refuses adb backup for non-debuggable apps; apktool rebuild of base.apk breaks a <meta-data>
  (unresolved @drawable refs 0x7f08007a/0x7f080082) so the debuggable rebuild route needs a raw AXML patch instead.
- Ghidra: full-analysis run in ghidra/ (slow); lean run in ghidra2/ exporting to ghidra_out2/.

## RESULT 2026-10-19 21:40 — patch built, installed and verified
Patch (tools/patch_libyoyo.py, profile "base"): three single-instruction edits in gml_Script_funLoad, each replacing
`fmov d8, d0` (keep ini_read_real result) with `fmov d8, #1.0`:
  0x1b28124 valuePack_N loop, 0x1b2841c perk_N loop, 0x1b2b3ec gemUnlock_N loop  (file offset == vaddr).
Effect: global.lvlValuePack[0..48], lvlPerk[0..3], lvlGemUnlocks[0..3] load as 1 on every launch regardless of the save,
and the game writes them back as 1 (verified in saves/bs3). Founder status and gem packs are consumable grants, untouched.
Verified in BlueStacks: permanent drone active on a fresh save, all bomb types recharge offline, Store "Value Packs" section empty.
Build: tools/patch_libyoyo.py -> build/patched/libyoyo.so -> zip-replace in split_config.arm64_v8a.apk -> zipalign -p ->
apksigner (build/debug.keystore, pass android, alias dbg) for all 4 splits -> build/release/*.apk.
Signature change => adb restore needs the backup _manifest cert replaced (tools/fix_manifest.py build/debug_cert.hex).
tools/bs.sh (run unsandboxed) automates backup/restore (auto-taps the confirm dialog via uiautomator), install, launch, screenshots.
Other findings: global IS_INTERNAL gates the dev build features (113 refs: dev keypresses, free IAP via trigger_iap_unlock_function,
debug menu); doomsday_counter/am_i_cheating/my_flag are cheat markers set externally (funInstantCheatFlag via live patch), not by a local detector.
Ghidra: durable project ghidra3/ (copies ghidra3b, ghidra3c for parallel headless runs); decompiles in ghidra_out3/4, condensed in sum/.

## Update 2026-10-19 late — founder, code granter, offline codes
Native patch profile "founder" (tools/patch_libyoyo.py) = base 3 fmov patches + :
- 0x1b3b2d4 funLoad: isFounder -> 1.0 (founder bomb + founder supply drops + VIP benefits, every save).
  Verified: save written with isFounder=1, founder_counter auto-accrues, VIP gem bonuses (+80/+320) in store.
- STUB 0x15d4e14 send_claim_code_packet -> 20-byte "return undefined" stub
  (movz w8,#5; str w8,[x2,#12]; str xzr,[x2]; mov x0,x2; ret). No code packet is built/sent. Cloud save untouched.
Founder bomb count reads highest_founder_recorded (66942 in the reference save) so it works offline w/o server_num_of_founders.

Code granter tools/grant.py: edits save.dat in place, idempotent, prereq-gated. For each reward code whose
prereq (lvlWorld/obeliskLvl/isFounder) is met AND isGiftCode_<i>==0, adds rewards and sets isGiftCode_<i>=1.
Re-run after progressing to pick up newly-eligible codes. Verified in-game: relic 152, mythic 1, divine 1, gems 701, skill 7, gifts(crackers) 195.
Reward->save key: gifts=crackers, relic=relicChests([chests]), mythic/divine=mythicChests/divineChests([single_vars]),
gems, skillpoints, fuel; items item_8=Charge Magnet item_13=Blue Cow item_17=Sushi (indices best-effort; the 3 are named consts atop grant.py).
Codes NOT included: Checkbox-only promo codes (server-gated, index-unmapped) and idx46/47 (ambiguous). Easter-egg/toggle codes excluded.

WHY NOT a signed startup Catspeak patch (the originally-described auto-on-boot design): the game's Catspeak sandbox
(set_up_catspeak_env) exposes variable_global_GET but NOT set, no array write, and funSave won't persist a custom
flag -> a startup patch can't durably mark a code claimed -> can't be made idempotent. So founder is baked natively
(auto every boot) and codes are a re-runnable save edit instead. Live-patch route would also need the ed25519 pubkey
(.rodata 0x953b50 + 0x96c8ff, sign_test does NOT gate loading) replaced + self-signed patches.dat; not used.

Still online (user scoped removal to codes): wss cloud save, server time, refunds, AppsFlyer/Sentry telemetry, server live-patch channel.

## Anti-cheat / flagging
The game has a client-side soft-penalty anti-cheat: globals `am_i_cheating` (compared to 0 in
loot/roll functions: funRollRocks, funCardsRollForCard, funPetRollForLevelUp, fun_roll_gift_loot,
etc. -> nerfed luck), `doomsday_counter` (persisted countdown, ticked by funTickDoomsday), and
`my_flag`. funUnfuckSave resets them to the clean state (-1 / "fish_stage_a"). There is NO local
setter for these flags anywhere in the code; they are raised only by (a) the server over the
live-patch / `update_variable` channel (Catspeak `update_var` is the sink) and (b) the method-ref
`funInstantCheatFlag` (sets doomsday_counter=3). Shadow validators (validRelic/validMythic/
validDivine/gemlimitnaughtynaughty/isCompletionPercentTooHigh/tastyValidator) are runtime-only,
not stored in the save.

Disabled in profile "founder":
- funInstantCheatFlag -> return-undefined stub (local flagger).
- update_var -> stub (no local game callers; blocks server variable injection incl. the flags).
- handle_live_patch_package -> stub (blocks server-pushed Catspeak patches / remote code).
- funLoad: doomsday_counter forced to -1 on every load (fmov d8,#-1.0 at the load site).
am_i_cheating is runtime-only and inits clean each session, so with the set-paths blocked it
stays 0. NOTE: server-SIDE detection from uploaded cloud-save data is outside client control; it
is only avoidable by turning cloud save off (not done, per scope).
