#!/usr/bin/env python3
"""Apply the mod's default player options to a save.dat.

Writes the toggles in data/options.json (mute music/sfx, bomb + UI preferences,
and the array-packed Options-menu toggles) into the save. Safe to re-run.

  apply_options.py <save.dat> [options.json]   (default: data/options.json)
"""
import json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))

def decode(path):
    d = bytes.fromhex(open(path).read().strip())
    nl = struct.unpack("<I", d[12:16])[0]
    v, ln = struct.unpack("<2I", d[16 + nl:24 + nl])
    return d[:16 + nl], v, d[24 + nl:24 + nl + ln].decode("utf-8")

def encode(path, head, v, txt):
    body = txt.encode("utf-8")
    open(path, "w").write((head + struct.pack("<2I", v, len(body)) + body).hex().upper())

def setnum(txt, key, value):
    new, n = re.subn(r'^(' + re.escape(key) + r')="?-?[0-9.]+"?(?=\r?$)',
                     lambda m: f'{m.group(1)}="{float(value):.6f}"', txt, count=1, flags=re.M)
    return new, n

def main():
    path = sys.argv[1]
    cfg = json.load(open(sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "data", "options.json")))
    head, v, txt = decode(path)
    applied, missing = [], []
    for group in ("single_vars", "options", "in_menu_options"):
        for key, val in cfg.get(group, {}).items():
            txt, n = setnum(txt, key, val)
            (applied if n else missing).append(key)
    encode(path, head, v, txt)
    print(f"applied {len(applied)} options: {', '.join(applied)}")
    if missing:
        print(f"not present in save (skipped): {', '.join(missing)}")
    print(f"wrote {path}")

if __name__ == "__main__":
    main()
