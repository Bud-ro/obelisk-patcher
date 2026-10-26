#!/usr/bin/env bash
# BlueStacks / Android helper for the save backup-edit-restore loop.
#   bs.sh backup  <name>     -> saves/<name>.ab  (+ unpacked to saves/<name>/)
#   bs.sh restore <name>     -> restores saves/<name>.ab (repacks saves/<name>/ first if present)
#   bs.sh install <dir>      -> reinstall the apks in <dir>, RETAINING the current save
#                               (add --wipe to install fresh instead)
#   bs.sh launch | stop | shot <png> | tap "<button text regex>"
#
# Named save slots: `backup`/`restore` take a slot name, so you can keep more than
# one save. To swap to a secondary save:
#     bs.sh backup slotA     # stash whatever is live as "slotA"
#     bs.sh restore slotB    # load a previously stashed "slotB" (fresh start: --wipe install)
# `install` always preserves the live save, so reinstalling a new patch never wipes it.
#
# Config via environment (all optional):
#   ADB      path to the adb binary (default: adb on PATH). On WSL targeting
#            Windows BlueStacks, point this at the Windows adb.exe.
#   SERIAL   adb device serial (default: none, adb picks the only attached device;
#            e.g. 127.0.0.1:5555 for a local emulator).
#   XFER     a directory both this shell and adb can read/write. On WSL+Windows
#            this must be a Windows path (adb.exe can't see WSL paths); set XFER
#            to its /mnt/c/... form and XFER_NATIVE to its C:\... form.
set -u
A="${ADB:-adb}"
B="${SERIAL:+-s $SERIAL}"
PKG=com.checkbox.minershminer
HERE=$(cd "$(dirname "$0")/.." && pwd)
WIN="${XFER:-$HERE/saves/xfer}"
WINP="${XFER_NATIVE:-$WIN}"
SEP="${XFER_SEP:-/}"  # set to a backslash when XFER_NATIVE is a Windows C:\... path
mkdir -p "$WIN" "$HERE/saves"

# macOS has no coreutils timeout; perl alarm is a drop-in.
command -v timeout >/dev/null || timeout() { perl -e 'alarm shift; exec @ARGV' "$@"; }

adb() { timeout 60 $A $B "$@"; }

tap_button() {   # $1 = regex on button text; polls up to ~20s
  for i in $(seq 1 10); do
    sleep 2
    adb shell "uiautomator dump /sdcard/ui.xml >/dev/null 2>&1; cat /sdcard/ui.xml" 2>/dev/null > "$HERE/saves/ui.xml"
    local xy
    xy=$(python3 -I - "$1" "$HERE/saves/ui.xml" <<'EOF'
import re,sys
pat,path=sys.argv[1],sys.argv[2]
x=open(path,encoding='utf-8',errors='replace').read()
for m in re.finditer(r'<node[^>]*class="android.widget.Button"[^>]*>',x):
    t=re.search(r'text="([^"]*)"',m.group(0)).group(1)
    if re.search(pat,t,re.I):
        b=re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',m.group(0))
        print((int(b.group(1))+int(b.group(3)))//2,(int(b.group(2))+int(b.group(4)))//2); break
EOF
)
    if [ -n "$xy" ]; then adb shell input tap $xy; echo "tapped '$1' at $xy"; return 0; fi
  done
  echo "button '$1' not found" >&2; return 1
}

case "${1:-}" in
  backup)
    n=$2; rm -f "$WIN/$n.ab"
    ( timeout 180 $A $B backup -f "$WINP$SEP$n.ab" -noapk $PKG > "$HERE/saves/$n.backup.log" 2>&1 & )
    tap_button 'back up my data'
    for i in $(seq 1 30); do sleep 2; [ -s "$WIN/$n.ab" ] && [ "$(wc -c < "$WIN/$n.ab")" -gt 1000 ] && break; done
    sleep 2; cp "$WIN/$n.ab" "$HERE/saves/$n.ab" && rm -rf "$HERE/saves/$n" && python3 -I "$HERE/tools/abtool.py" unpack "$HERE/saves/$n.ab" "$HERE/saves/$n"
    ;;
  restore)
    n=$2
    [ -d "$HERE/saves/$n" ] && python3 -I "$HERE/tools/abtool.py" pack "$HERE/saves/$n" "$HERE/saves/$n.ab"
    cp "$HERE/saves/$n.ab" "$WIN/$n.ab"
    adb shell am force-stop $PKG
    ( timeout 180 $A $B restore "$WINP$SEP$n.ab" > "$HERE/saves/$n.restore.log" 2>&1 & )
    tap_button 'restore my data'
    sleep 8; cat "$HERE/saves/$n.restore.log"
    ;;
  install)   # install <apkdir> [--wipe]
    # RETAINS the current save by default: back up -> uninstall -> install -> restore.
    # Pass --wipe to install fresh and discard the current save.
    d=$2; wipe=0; [ "${3:-}" = "--wipe" ] && wipe=1
    preserved=0
    if [ $wipe -eq 0 ] && $A $B shell pm path $PKG >/dev/null 2>&1; then
      echo "retaining current save (back up -> reinstall -> restore)..."
      rm -rf "$HERE/saves/_preinstall" "$HERE/saves/_preinstall.ab"  # a stale copy must not pass the check below
      "$0" backup _preinstall >/dev/null 2>&1
      [ -f "$HERE/saves/_preinstall/apps/$PKG/f/save.dat" ] && preserved=1
      [ $preserved -eq 1 ] || { echo "  ERROR: could not back up current save; aborting before uninstall (unlock the device, or use --wipe to discard it)" >&2; exit 1; }
      echo "  current progress saved"
    fi
    rm -rf "$WIN/apk"; mkdir -p "$WIN/apk"; cp "$d"/*.apk "$WIN/apk/"
    adb shell am force-stop $PKG; adb uninstall $PKG
    args=""; for f in "$WIN/apk"/*.apk; do args="$args $WINP${SEP}apk$SEP$(basename "$f")"; done
    timeout 300 $A $B install-multiple $args
    adb shell pm path $PKG | head -2
    if [ $preserved -eq 1 ]; then
      # If the new APKs are signed with a different key than the old install, the
      # backup's recorded cert won't match and restore is rejected; point SIGN_CERT
      # at a hex DER of the new signing cert to rewrite it. Same-key reinstall needs none.
      [ -n "${SIGN_CERT:-}" ] && [ -f "${SIGN_CERT}" ] && \
        python3 -I "$HERE/tools/fix_manifest.py" "$HERE/saves/_preinstall" "${SIGN_CERT}" >/dev/null 2>&1
      echo "restoring your save..."
      "$0" restore _preinstall >/dev/null 2>&1 && echo "  save restored"
    fi
    ;;
  launch) adb shell "monkey -p $PKG -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1; sleep 5; ps -A | grep -c $PKG" ;;
  stop)   adb shell am force-stop $PKG ;;
  home)   adb shell input keyevent KEYCODE_HOME ;;
  shot)   adb exec-out screencap -p > "$2" 2>/dev/null; ls -la "$2" ;;
  tap)    tap_button "$2" ;;
  *) echo "usage: $0 backup|restore <name> | install <dir> | launch | stop | home | shot <png> | tap <regex>"; exit 1 ;;
esac
