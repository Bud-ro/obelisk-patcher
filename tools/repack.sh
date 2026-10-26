#!/usr/bin/env bash
# Repack, align, and sign all splits for Obelisk Miner.
# Applies raw AXML patch to base.apk so the rebuilt build is debuggable (android:debuggable="true"),
# and inserts the patched libyoyo.so into split_config.arm64_v8a.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
cd "$HERE"

# Find build tools (apksigner, zipalign)
for p in \
  /opt/homebrew/share/android-commandlinetools/build-tools/* \
  "$HOME/Library/Android/sdk/build-tools/"* \
  /usr/local/share/android-commandlinetools/build-tools/*; do
  if [ -d "$p" ]; then
    export PATH="$p:$PATH"
  fi
done

command -v zipalign >/dev/null 2>&1 || { echo "Error: zipalign not found on PATH" >&2; exit 1; }
command -v apksigner >/dev/null 2>&1 || { echo "Error: apksigner not found on PATH" >&2; exit 1; }

mkdir -p build/release build/patched
# Never sign intermediates left over from a previous run
rm -f build/base.unsigned.apk build/split_config.arm64_v8a.unsigned.apk

# 1. Create debug keystore if missing
if [ ! -f build/debug.keystore ]; then
  echo "Generating build/debug.keystore..."
  keytool -genkeypair -v -keystore build/debug.keystore -storepass android \
          -keypass android -alias dbg -keyalg RSA -keysize 2048 -validity 10000 \
          -dname "CN=Obelisk Mod"
fi

# 2. Patch base.apk manifest so the rebuilt app is debuggable
echo "Patching base.apk manifest (raw AXML patch for debug mode)..."
python3 tools/patch_manifest.py input/base.apk build/base.unsigned.apk

# 3. Repack arm64 split with patched libyoyo.so if present
if [ -f build/patched/libyoyo.so ]; then
  echo "Repacking split_config.arm64_v8a with patched libyoyo.so..."
  python3 -c 'from tools.patch_manifest import rezip
rezip("input/split_config.arm64_v8a.apk", "build/split_config.arm64_v8a.unsigned.apk",
      {"lib/arm64-v8a/libyoyo.so": open("build/patched/libyoyo.so", "rb").read()})'
else
  echo "Warning: build/patched/libyoyo.so not found; shipping the stock arm64 split" >&2
fi

# 4. Align and sign all splits
echo "Aligning and signing splits into build/release/..."
for f in base split_config.arm64_v8a split_config.en split_config.xxhdpi; do
  SRC="input/$f.apk"
  [ "$f" = base ] && [ -f build/base.unsigned.apk ] && SRC="build/base.unsigned.apk"
  [ "$f" = split_config.arm64_v8a ] && [ -f build/split_config.arm64_v8a.unsigned.apk ] && SRC="build/split_config.arm64_v8a.unsigned.apk"
  zipalign -p -f 4 "$SRC" "build/release/$f.aligned.apk"
  apksigner sign --ks build/debug.keystore --ks-pass pass:android \
    --key-pass pass:android --ks-key-alias dbg \
    --out "build/release/$f.apk" "build/release/$f.aligned.apk"
done
rm -f build/release/*.aligned.apk build/release/*.idsig

echo "Build complete. Release APKs are ready in build/release/"
