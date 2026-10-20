#!/usr/bin/env python3
"""Obelisk Miner save.dat codec.

save.dat = uppercase hex of a GameMaker buffer:
  u32 403 | u32 1 | u32 1 | u32 namelen | "save" | u32 1 | u32 textlen | INI text (CRLF)

  savetool.py decode save.dat out.ini
  savetool.py encode in.ini save.dat
  savetool.py get    save.dat section key
  savetool.py set    save.dat section key value [section key value ...]   (in place)
  savetool.py dump   save.dat [section]
"""
import re, struct, sys

def decode(path):
    d = bytes.fromhex(open(path, "rb").read().decode().strip())
    hdr = struct.unpack("<4I", d[:16])
    nl = hdr[3]
    name = d[16:16 + nl]
    v, ln = struct.unpack("<2I", d[16 + nl:24 + nl])
    txt = d[24 + nl:24 + nl + ln]
    assert len(txt) == ln, "truncated save"
    return (hdr, name, v), txt.decode("utf-8")

def encode(path, meta, txt):
    hdr, name, v = meta
    body = txt.encode("utf-8")
    out = struct.pack("<4I", *hdr) + name + struct.pack("<2I", v, len(body)) + body
    with open(path, "w") as f:
        f.write(out.hex().upper())

def parse(txt):
    """Return ordered list of (section, [(key, value)...]) keeping raw lines for re-emit."""
    return txt

def get(txt, section, key):
    m = re.search(r"^\[" + re.escape(section) + r"\]\r?\n(.*?)(?=^\[|\Z)", txt, re.S | re.M)
    if not m:
        raise KeyError(f"no section [{section}]")
    km = re.search(r"^" + re.escape(key) + r'="?([^"\r\n]*)"?\r?$', m.group(1), re.M)
    if not km:
        raise KeyError(f"no key {key} in [{section}]")
    return km.group(1)

def set_(txt, section, key, value):
    m = re.search(r"^\[" + re.escape(section) + r"\]\r?\n", txt, re.M)
    if not m:
        raise KeyError(f"no section [{section}]")
    start = m.end()
    nxt = re.search(r"^\[", txt[start:], re.M)
    end = start + nxt.start() if nxt else len(txt)
    block = txt[start:end]
    pat = re.compile(r"^(" + re.escape(key) + r')=("?)[^"\r\n]*("?)(\r?)$', re.M)
    if pat.search(block):
        block = pat.sub(lambda mm: f'{mm.group(1)}={mm.group(2)}{value}{mm.group(3)}{mm.group(4)}', block, count=1)
    else:
        block = block + f'{key}="{value}"\r\n'
    return txt[:start] + block + txt[end:]

def num(v):
    """Format a number the way the game writes it."""
    try:
        return f"{float(v):.6f}"
    except ValueError:
        return v

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "decode":
        meta, txt = decode(a[1]); open(a[2], "w", newline="").write(txt); print(meta)
    elif a[0] == "encode":
        meta, _ = decode(a[2]) if len(a) > 2 and a[2].endswith(".dat") else (((403, 1, 1, 4), b"save", 1), None)
        txt = open(a[1], newline="").read(); encode(a[2], meta, txt); print("encoded", len(txt))
    elif a[0] == "get":
        _, txt = decode(a[1]); print(get(txt, a[2], a[3]))
    elif a[0] == "set":
        meta, txt = decode(a[1])
        trip = a[2:]
        for i in range(0, len(trip), 3):
            s, k, v = trip[i:i + 3]
            old = get(txt, s, k) if True else None
            txt = set_(txt, s, k, num(v))
            print(f"[{s}] {k}: {old} -> {num(v)}")
        encode(a[1], meta, txt)
    elif a[0] == "dump":
        _, txt = decode(a[1])
        if len(a) > 2:
            m = re.search(r"^\[" + re.escape(a[2]) + r"\]\r?\n(.*?)(?=^\[|\Z)", txt, re.S | re.M)
            print(m.group(1) if m else "no such section")
        else:
            print(txt)
    else:
        sys.exit(__doc__)
