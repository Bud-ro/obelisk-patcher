#!/usr/bin/env python3
"""Patch Obelisk Miner v2.2.30 libyoyo.so (arm64) so every value pack / perk / gem unlock
loads as owned.

In gml_Script_funLoad, each of the three ini_read_real loops does
    bl   YYGML_ini_read_real
    fmov d8, d0            ; keep loaded value
and later stores d8 into global.lvlValuePack[i] / lvlPerk[i] / lvlGemUnlocks[i].
We replace `fmov d8, d0` with `fmov d8, #1.0` so the stored value is always 1.0.

usage: patch_libyoyo.py in.so out.so [--profile base|internal]
"""
import struct, sys

# (vaddr, old bytes, new bytes, description)   .text file offset == vaddr for this ELF
FMOV_D8_D0   = bytes.fromhex("0840601e")   # fmov d8, d0
FMOV_D8_ONE  = bytes.fromhex("08106e1e")   # fmov d8, #1.0

PATCHES_BASE = [
    (0x1b28124, FMOV_D8_D0, FMOV_D8_ONE, "funLoad: valuePack_N -> 1.0"),
    (0x1b2841c, FMOV_D8_D0, FMOV_D8_ONE, "funLoad: perk_N -> 1.0"),
    (0x1b2b3ec, FMOV_D8_D0, FMOV_D8_ONE, "funLoad: gemUnlock_N -> 1.0"),
]

# Founder: force global.isFounder = 1.0 on every save load (founder bomb,
# founder supply drops, VIP benefits). Same fmov trick at the isFounder read site.
PATCHES_FOUNDER = PATCHES_BASE + [
    (0x1b3b2d4, FMOV_D8_D0, FMOV_D8_ONE, "funLoad: isFounder -> 1.0"),
]

# Function-body stubs: overwrite a function's start with a "return undefined" stub.
# Verified first-instruction guard, then the 20-byte stub:
#   movz w8,#5 ; str w8,[x2,#12] ; str xzr,[x2] ; mov x0,x2 ; ret
RETURN_UNDEF_STUB = bytes.fromhex("a8008052480c00b95f0000f9e00302aac0035fd6")

# get_vip_points -> return 1e8, so get_vip_my_tier's loop clears every threshold
# and returns the maximum founder tier -> all Founder's Lounge / VIP buffs active.
#   movz x8,#0xD784,lsl#32 ; movk x8,#0x4197,lsl#48 ; str x8,[x2] ; str wzr,[x2,#12] ; mov x0,x2 ; ret
VIP_POINTS_MAX_STUB = bytes.fromhex("88f0dad2e832e8f2480000f95f0c00b9e00302aac0035fd6")

STUBS_FOUNDER = [
    # Neuter online code claims: no code packet is ever built or sent. Cloud save untouched.
    (0x15d4e14, bytes.fromhex("ff8304d1"), RETURN_UNDEF_STUB,
     "send_claim_code_packet -> return undefined (no online code claims)"),
    # Max founder tier.
    (0x1bf3cc4, bytes.fromhex("ff8301d1"), VIP_POINTS_MAX_STUB,
     "get_vip_points -> 1e8 (max founder tier, all lounge buffs)"),
]

PROFILES = {"base": PATCHES_BASE, "founder": PATCHES_FOUNDER}
STUB_PROFILES = {"founder": STUBS_FOUNDER}

def vaddr_to_off(data, vaddr):
    # parse program headers to map vaddr -> file offset
    e_phoff = struct.unpack_from("<Q", data, 0x20)[0]
    e_phentsize, e_phnum = struct.unpack_from("<HH", data, 0x36)
    for i in range(e_phnum):
        p = e_phoff + i * e_phentsize
        p_type, p_flags, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz = struct.unpack_from("<IIQQQQQ", data, p)
        if p_type == 1 and p_vaddr <= vaddr < p_vaddr + p_filesz:
            return vaddr - p_vaddr + p_offset
    raise ValueError(f"vaddr {vaddr:#x} not in any LOAD segment")

def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    src, dst = a[0], a[1]
    profile = a[a.index("--profile") + 1] if "--profile" in a else "base"
    data = bytearray(open(src, "rb").read())
    for vaddr, old, new, desc in PROFILES[profile]:
        off = vaddr_to_off(data, vaddr)
        cur = bytes(data[off:off + len(old)])
        if cur == new:
            print(f"  already patched {vaddr:#x} {desc}")
            continue
        if cur != old:
            sys.exit(f"mismatch at {vaddr:#x} ({desc}): found {cur.hex()} expected {old.hex()}")
        data[off:off + len(new)] = new
        print(f"  patched {vaddr:#x} (file {off:#x}): {desc}")
    for vaddr, guard, stub, desc in STUB_PROFILES.get(profile, []):
        off = vaddr_to_off(data, vaddr)
        cur = bytes(data[off:off + len(guard)])
        if bytes(data[off:off + len(stub)]) == stub:
            print(f"  already stubbed {vaddr:#x} {desc}")
            continue
        if cur != guard:
            sys.exit(f"stub guard mismatch at {vaddr:#x} ({desc}): found {cur.hex()} expected {guard.hex()}")
        data[off:off + len(stub)] = stub
        print(f"  stubbed {vaddr:#x} (file {off:#x}): {desc}")
    open(dst, "wb").write(data)
    print(f"wrote {dst}")

if __name__ == "__main__":
    main()
