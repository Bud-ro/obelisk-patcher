# Obelisk Miner — Pay-to-Win Removal Mod

A toolkit that patches the Android build of **Obelisk Miner** (`com.checkbox.minershminer`)
so its pay-to-win features are simply *on*, unlocked the moment their normal in-game
prerequisites are met — no purchases, no server.

It does **not** redistribute the game. You supply your own copy of the APK (see
[SETUP.md](SETUP.md)); the tools patch the native library inside it, re-sign it, and
help you move an edited save in and out.

## What it changes

Native patches to `libyoyo.so` (the GameMaker runtime that holds all game logic):

- **All value packs, perks, and gem unlocks read as owned.** The 49 value packs, 4
  perks, and 4 gem unlocks are forced on at save-load, so every pack feature is active
  once you reach whatever the feature itself requires in-game.
- **Founder status is always on** (`isFounder = 1`), enabling the founder bomb, founder
  supply drops, and the VIP / Founder's Lounge benefits.
- **Founder tier is maxed**, so every tier's lounge buff applies.
- **Online code claims are cut.** The function that sends a code to the server is
  stubbed out, so entering a code never phones home. Cloud save still works.

Save-side helpers (run against your own save file):

- **`apply_options.py`** sets sensible default preferences (music/SFX muted, bomb and
  UI toggles) from [`data/options.json`](data/options.json).
- **`grant.py`** redeems every reward code whose in-game prerequisite you currently meet,
  once each. It respects the World/Obelisk/Founder gates and marks codes claimed with the
  game's own flags, so re-running it after you progress only grants the newly-eligible codes.

## Why some things are save-side, not baked into the APK

The game's startup script sandbox can read globals but cannot write or persist them, and
per-code "claimed" state lives in the save as array entries that no single APK patch can
set individually. So founder status and the pack unlocks (which just need to be forced on
every load) are native patches, while one-time grants and per-index options are applied to
the save by the helper scripts. The setup flow runs both, so a fresh install still ends up
with everything.

## Legal / scope

For personal, offline use with a copy of the game you already have. Enabling paid features
without paying breaks the game's terms of service; only do this with your own install.
This repo contains no game code or assets — just patch offsets and tooling.

See [SETUP.md](SETUP.md) to build and install, and [TECHNICAL.md](TECHNICAL.md) for how the
patches were found and what each one does.
