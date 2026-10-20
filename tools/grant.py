#!/usr/bin/env python3
"""Obelisk Miner one-shot code granter.

Reads a decoded save.ini (or a save.dat via savetool), and for every reward code
whose in-game prerequisite is currently met AND that has not been claimed yet
(the game's own isGiftCode_<i> flag is 0), adds the code's rewards to the save
and sets isGiftCode_<i> = 1. Idempotent: re-run after you progress and it only
grants newly-eligible, unclaimed codes.

  grant.py <save.dat>              apply in place (edits the .dat)
  grant.py <save.dat> --dry        show what it would grant, change nothing

Prereqs read from the save: lvlWorld, obeliskLvl, isFounder.
Reward currencies map to these save keys (added, not overwritten):
  gifts->crackers  relic->relicChests  mythic->mythicChests  divine->divineChests
  gems->gems  skill->skillpoints  fuel->fuel  items->item_<n> (magnet=8 cow=13 sushi=17)
"""
import re, sys, struct

# code: (isGiftCode index, prereq, rewards)
#   prereq: None | ("world",n) | ("obelisk",n) | ("founder",) | ("tier",10)
#   rewards keys: gifts relic mythic divine gems skill fuel  item8 item13 item17
CODES = {
    "WOOPWOOPCLOUDSAVE":      (0,  None,            {"relic": 25}),
    "WORLDTWOBABY":           (1,  ("world", 2),    {"gifts": 20}),
    "OMGPETS":                (3,  None,            {"item8": 50, "item13": 10}),
    "SOMANYFOUNDERS":         (4,  None,            {"mythic": 1, "item13": 10}),
    "ITSABOUTTIME":           (24, None,            {"divine": 1}),
    "ANYCODESQUESTIONMARK":   (25, None,            {"gems": 250, "item8": 50}),
    "NEWOFFLINE":             (27, None,            {"relic": 25, "gifts": 5}),
    "KOSH":                   (31, None,            {"relic": 50, "item13": 10}),
    "KOSHROUNDTWO":           (32, None,            {"gems": 250, "skill": 2}),
    "ONEPOINTSEVEN":          (33, None,            {"skill": 3, "relic": 25, "gifts": 5}),
    "OSRS":                   (34, None,            {"relic": 25, "gifts": 10}),
    "WTHREEPTWO":             (38, ("world", 3),    {"gifts": 30}),
    "TWENTYGIFTSPLS":         (39, None,            {"gifts": 20}),
    "PETQUESTS":              (40, None,            {"relic": 25, "gifts": 5, "skill": 2}),
    "LEFTOVERSUSHI":          (43, ("obelisk", 37), {"item17": 50}),
    "ANOTHERWORLDMAKEITSTOP": (44, ("world", 4),    {"gifts": 40}),
    "FOUNDERCODE":            (45, ("founder",),     {"gifts": 50}),
    "FUELMEUP":               (48, ("obelisk", 18), {"fuel": 50}),
    "FOUNDERTIERTEN":         (49, ("tier", 10),     {"gifts": 100}),
}

# reward key -> (section hint, save key).  section None = auto-locate.
REWARD_KEY = {
    "gifts":  "crackers", "relic": "relicChests", "mythic": "mythicChests",
    "divine": "divineChests", "gems": "gems", "skill": "skillpoints", "fuel": "fuel",
    "item8":  "item_8", "item13": "item_13", "item17": "item_17",
}

def decode(path):
    d = bytes.fromhex(open(path).read().strip())
    nl = struct.unpack("<I", d[12:16])[0]
    v, ln = struct.unpack("<2I", d[16 + nl:24 + nl])
    txt = d[24 + nl:24 + nl + ln].decode("utf-8")
    return d[:16 + nl], v, txt

def encode(path, head, v, txt):
    body = txt.encode("utf-8")
    out = head + struct.pack("<2I", v, len(body)) + body
    open(path, "w").write(out.hex().upper())

def getnum(txt, key):
    m = re.search(r'^' + re.escape(key) + r'="?(-?[0-9.]+)"?\r?$', txt, re.M)
    return float(m.group(1)) if m else None

def setnum(txt, key, value):
    def repl(m):
        return f'{key}="{value:.6f}"'
    new, n = re.subn(r'^' + re.escape(key) + r'="?-?[0-9.]+"?(?=\r?$)', repl, txt, count=1, flags=re.M)
    if n == 0:
        raise KeyError(key)
    return new

def main():
    path = sys.argv[1]
    dry = "--dry" in sys.argv
    head, v, txt = decode(path)
    world = getnum(txt, "lvlWorld") or 0
    obelisk = getnum(txt, "obeliskLvl") or 0
    founder = (getnum(txt, "isFounder") or 0) >= 1
    print(f"state: world={world:.0f} obelisk={obelisk:.0f} founder={founder}")

    def prereq_met(p):
        if p is None: return True
        if p[0] == "world": return world >= p[1]
        if p[0] == "obelisk": return obelisk >= p[1]
        if p[0] == "founder": return founder
        if p[0] == "tier": return founder  # all value packs owned -> max VIP; tier gate approximated by founder status
        return False

    granted, skipped_locked, already = [], [], []
    for code, (idx, prereq, rewards) in CODES.items():
        flag = f"isGiftCode_{idx}"
        cur = getnum(txt, flag)
        if cur is None:
            print(f"  ! {code}: {flag} not in save, skipping"); continue
        if cur >= 1:
            already.append(code); continue
        if not prereq_met(prereq):
            skipped_locked.append((code, prereq)); continue
        # grant
        for rk, amt in rewards.items():
            key = REWARD_KEY[rk]
            old = getnum(txt, key)
            if old is None:
                print(f"  ! {code}: reward key {key} not found, skipping that reward"); continue
            if not dry:
                txt = setnum(txt, key, old + amt)
        if not dry:
            txt = setnum(txt, flag, 1.0)
        granted.append((code, rewards))

    print(f"\nGRANT {len(granted)} codes:")
    for code, r in granted: print(f"  + {code}: {r}")
    print(f"LOCKED (prereq not met) {len(skipped_locked)}:")
    for code, p in skipped_locked: print(f"  - {code}: needs {p}")
    print(f"ALREADY CLAIMED {len(already)}: {', '.join(already) or '(none)'}")
    if not dry:
        encode(path, head, v, txt)
        print(f"\nwrote {path}")
    else:
        print("\n(dry run, no changes)")

if __name__ == "__main__":
    main()
