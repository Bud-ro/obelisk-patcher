# Setup

You need: a computer with `adb`, a Java JDK (for `apksigner`/`zipalign`/`keytool`),
Android build-tools (`apksigner`, `zipalign`), Python 3, and an Android target to run on
(a device, or an **arm64** Android emulator such as a 64-bit BlueStacks instance).

Everything below uses placeholders — there are no personal paths in this repo.

## 1. Get your own copy of the game's APKs

Obelisk Miner installs as a **split APK**, so you need all the pieces, not just `base.apk`.
Install the game from the Play Store on your device or emulator, then pull every split:

```bash
# list the installed split paths
adb shell pm path com.checkbox.minershminer

# pull each one into ./input/
mkdir -p input
adb shell pm path com.checkbox.minershminer \
  | sed 's/^package://' \
  | while read p; do adb pull "$p" input/; done
```

You should end up with `input/base.apk`, `input/split_config.arm64_v8a.apk`, and a
couple of smaller `split_config.*.apk` files. The `arm64_v8a` one contains `libyoyo.so`,
which is the file the mod patches.

> The patch offsets target game version **2.2.30**. A different version won't match;
> the patcher will refuse rather than corrupt anything.

## 2. Patch the native library

```bash
# unpack libyoyo.so from the arm64 split
mkdir -p build/patched
unzip -o input/split_config.arm64_v8a.apk lib/arm64-v8a/libyoyo.so -d build/unzip
python3 tools/patch_libyoyo.py build/unzip/lib/arm64-v8a/libyoyo.so \
        build/patched/libyoyo.so --profile founder
```

The patcher verifies each site before writing and prints what it changed.

## 3. Repack, align, and sign

Make a signing key once (any key works; the game is self-signed after this, so Play
sign-in / billing won't be available — that's expected for a modded build):

```bash
keytool -genkeypair -v -keystore build/debug.keystore -storepass android \
        -keypass android -alias dbg -keyalg RSA -keysize 2048 -validity 10000 \
        -dname "CN=Obelisk Mod"
```

Put the patched `libyoyo.so` back into the arm64 split, apply the raw AXML patch
to `base.apk` so the rebuilt build is in debug mode (`android:debuggable="true"`),
and sign every split with the same key (splits must share a signature):

```bash
# Apply raw AXML patch to base.apk so the build is debuggable
python3 tools/patch_manifest.py input/base.apk build/base.unsigned.apk

# Repack the arm64 split with patched libyoyo.so
python3 -c 'from tools.patch_manifest import rezip
rezip("input/split_config.arm64_v8a.apk", "build/split_config.arm64_v8a.unsigned.apk",
      {"lib/arm64-v8a/libyoyo.so": open("build/patched/libyoyo.so", "rb").read()})'

mkdir -p build/release
for f in base split_config.arm64_v8a split_config.en split_config.xxhdpi; do
  SRC="input/$f.apk"
  [ "$f" = base ] && SRC="build/base.unsigned.apk"
  [ "$f" = split_config.arm64_v8a ] && SRC="build/split_config.arm64_v8a.unsigned.apk"
  zipalign -p -f 4 "$SRC" "build/release/$f.aligned.apk"
  apksigner sign --ks build/debug.keystore --ks-pass pass:android \
    --key-pass pass:android --ks-key-alias dbg \
    --out "build/release/$f.apk" "build/release/$f.aligned.apk"
done
rm -f build/release/*.aligned.apk build/release/*.idsig
```

*(Alternatively, run `tools/repack.sh` which executes all of the above steps).*

## 4. Install

```bash
adb uninstall com.checkbox.minershminer   # if the Play version is installed
adb install-multiple build/release/base.apk \
  build/release/split_config.arm64_v8a.apk \
  build/release/split_config.en.apk \
  build/release/split_config.xxhdpi.apk
```

Launch the game once so it creates a save, then close it.

### Reinstalling a new patch later

`adb install-multiple` over an existing install can wipe the app's data (your save).
Use the helper instead, which backs up the current save, reinstalls, and restores it:

```bash
tools/bs.sh install build/release          # retains the current save
tools/bs.sh install build/release --wipe   # only if you want a fresh start
```

### Running more than one save

`backup`/`restore` take a slot name, so you can keep several saves and switch between
them. `install` always preserves whichever save is live.

```bash
tools/bs.sh backup main       # stash the current save as "main"
tools/bs.sh restore alt       # load a previously stashed "alt" save
```

## 5. Apply options and redeem eligible codes to your save

The native patch already gives you the packs, founder status, and max tier. These last
steps apply the preferred options and redeem code rewards into your save file.

Getting the save off the device without root is easiest via `adb backup` (the app allows
it). `tools/bs.sh` automates the backup/edit/restore loop, including tapping the on-device
confirm dialogs; configure it with environment variables (see the header of
[`tools/bs.sh`](tools/bs.sh)) — at minimum `ADB` and, on WSL+Windows, `XFER`/`XFER_NATIVE`.

```bash
# pull + unpack the current save
tools/bs.sh backup mysave

# edit the unpacked save.dat
SAVE=saves/mysave/apps/com.checkbox.minershminer/f/save.dat
python3 tools/apply_options.py "$SAVE"     # mute music/sfx + preferred toggles
python3 tools/grant.py "$SAVE"             # redeem codes whose prereqs you now meet

# repack + restore
tools/bs.sh restore mysave
```

Re-run `grant.py` (and `restore`) whenever you reach a new World or Obelisk level to pick
up codes that were previously locked. It never double-grants.

Prefer to edit a save by hand? `tools/savetool.py` decodes `save.dat` to plain INI and
back (`decode` / `encode` / `get` / `set` / `dump`), and `tools/abtool.py` unpacks and
repacks the `adb backup` archive.
