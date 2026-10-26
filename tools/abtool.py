#!/usr/bin/env python3
"""Unpack / repack Android `adb backup` archives (.ab), unencrypted only.

  abtool.py unpack  backup.ab  outdir      -> extracts the inner tar into outdir, writes outdir/.ab_header
  abtool.py pack    indir      backup.ab   -> rebuilds backup.ab from indir (uses saved header and member order)
  abtool.py ls      backup.ab              -> list members
"""
import io, os, sys, tarfile, zlib, json

MAGIC = b"ANDROID BACKUP\n"

def read_ab(path):
    with open(path, "rb") as f:
        data = f.read()
    assert data.startswith(MAGIC), "not an adb backup"
    parts = data.split(b"\n", 4)
    version, compressed, enc = parts[1].decode(), parts[2].decode(), parts[3].decode()
    body = parts[4]
    if enc != "none":
        sys.exit("encrypted backups are not supported; redo the backup with no password")
    if compressed == "1":
        body = zlib.decompress(body)
    return {"version": version, "compressed": compressed}, body

def write_ab(path, header, tar_bytes):
    body = zlib.compress(tar_bytes, 9) if header["compressed"] == "1" else tar_bytes
    with open(path, "wb") as f:
        f.write(MAGIC + header["version"].encode() + b"\n" + header["compressed"].encode() + b"\nnone\n" + body)

def cmd_ls(ab):
    _, body = read_ab(ab)
    with tarfile.open(fileobj=io.BytesIO(body)) as t:
        for m in t.getmembers():
            print(f"{m.size:10d}  {m.name}")

def cmd_unpack(ab, outdir):
    header, body = read_ab(ab)
    os.makedirs(outdir, exist_ok=True)
    order = []
    with tarfile.open(fileobj=io.BytesIO(body)) as t:
        for m in t.getmembers():
            order.append({"name": m.name, "type": m.type.decode(), "mode": m.mode, "uid": m.uid, "gid": m.gid, "mtime": m.mtime})
        if hasattr(tarfile, "data_filter"):
            t.extractall(outdir, filter="data")
        else:  # Python < 3.12 without the backport (e.g. macOS's 3.9): reject links / escaping paths by hand
            root = os.path.realpath(outdir)
            for m in t.getmembers():
                dest = os.path.realpath(os.path.join(outdir, m.name))
                if not ((m.isfile() or m.isdir()) and os.path.commonpath([root, dest]) == root):
                    raise ValueError(f"unsafe member {m.name}")
            t.extractall(outdir)
    header["order"] = order
    with open(os.path.join(outdir, ".ab_header"), "w") as f:
        json.dump(header, f, indent=1)
    print(f"unpacked {len(order)} members to {outdir}")

def cmd_pack(indir, ab):
    with open(os.path.join(indir, ".ab_header")) as f:
        header = json.load(f)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for e in header["order"]:
            p = os.path.join(indir, e["name"])
            ti = tarfile.TarInfo(e["name"])
            ti.type = e["type"].encode()
            ti.mode, ti.uid, ti.gid, ti.mtime = e["mode"], e["uid"], e["gid"], e["mtime"]
            if ti.type == tarfile.DIRTYPE:
                t.addfile(ti)
            else:
                with open(p, "rb") as fh:
                    data = fh.read()
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
    write_ab(ab, header, buf.getvalue())
    print(f"packed {len(header['order'])} members into {ab}")

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    if a[0] == "ls": cmd_ls(a[1])
    elif a[0] == "unpack": cmd_unpack(a[1], a[2])
    elif a[0] == "pack": cmd_pack(a[1], a[2])
    else: sys.exit(__doc__)
