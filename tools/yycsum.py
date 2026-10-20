#!/usr/bin/env python3
"""Condense Ghidra decompiler output of GameMaker YYC code into a readable trace.

usage: yycsum.py file.c [more.c ...]   (reads string_consts.tsv next to this script's project if present)
"""
import os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STRMAP = {}
for cand in (os.path.join(HERE, "..", "ghidra_out3", "string_consts.tsv"),):
    if os.path.exists(cand):
        for line in open(cand, encoding="utf-8", errors="replace"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and not line.startswith("#"):
                STRMAP[parts[0]] = parts[1]

NOISE = [
    r"^\s*/\*\s*(catch|try)", r"CatchHandler", r"FREE_RValue__Pre", r"^\s*if \(\(1 << \(ulong\)",
    r"= 0x500000000;", r"= 0xffffff;", r"PushContextStack", r"PopContextStack", r"SYYStackTrace",
    r"tpidr_el0", r"__stack_chk_fail", r"YYFree\(", r"YYAlloc\(", r"memcpy\(__dest", r"g_ContextStack",
    r"^\s*(undefined\d*|uint|int|long|ulong|char|double|float|bool|void|RValue|YYRValue|CInstance|YYObjectBase|code|byte|short|ushort|undefined)\s*\**\s*[A-Za-z_0-9]+(\s*\[\d+\])?\s*;",
    r"^\s*\*\(undefined4 \*\)\(param_3 \+ 0xc\) = 5;", r"^\s*\*\(undefined8 \*\)param_3 = 0;",
    r"WARNING: Subroutine does not return", r"^\s*local_[0-9a-f]+ = 0;\s*$", r"pcStack_[0-9a-f]+ = \"gml_",
    r"^\s*lVar\d+ = tpidr", r"^\s*local_[0-9a-f]+ = \*\(long \*\)\(lVar", r"^\s*uVar\d+ = param_4;",
    r"^\s*if \(param_4 < \d\)", r"^\s*uVar\d+ = \d;\s*$", r"puVar\d+ = puVar\d+ \+", r"^\s*\} while \(\(int\)uVar",
    r"^\s*\*puVar\d+ = ", r"^\s*puVar\d+\[1\] = ", r"^\s*uVar\d+ = \(int\)uVar", r"^\s*uVar\d+ = \(ulong\)uVar",
    r"^\s*\*\(undefined4 \*\)\(puVar\d+ \+ 1\)", r"^\s*\*\(uint \*\)\(\(long\)puVar", r"^\s*FUN_[0-9a-f]+\(puVar",
    r"^\s*pYVar\d+ = \*param_5;", r"^\s*uVar\d+ = \*\(uint \*\)\(pYVar\d+ \+ 0xc\);", r"^\s*param_5 = param_5 \+ 1;",
    r"^\s*uVar\d+ = uVar\d+ - 1;", r"^\s*\} while \(uVar\d+ != 0\);", r"^\s*if \(param_4 == 1\) goto",
    r"^\s*local_[0-9a-f]+ = \(ulong\)\(uint\)local_", r"^\s*\*\(undefined8 \*\)\(pRVar\d+ \+ 8\) = 0x500000000",
    r"^\s*\*\(undefined8 \*\)pRVar\d+ = 0;", r"^\s*uVar\d+ = uVar\d+ \+ 1;", r"^\s*\} while \(uVar\d+ < uVar\d+\);",
    r"^\s*pRVar\d+ = \(RValue \*\)puVar\d+\[uVar\d+\];", r"^\s*if \(0 < \(int\)local_", r"^\s*uVar\d+ = 0;\s*$",
    r"^\s*do \{\s*$", r"^\s*puVar\d+ = local_", r"^\s*uVar\d+ = \(ulong\)local_", r"^\s*local_[0-9a-f]+ = uVar\d+;",
    r"^\s*local_[0-9a-f]+ = puVar", r"^\s*puVar\d+ = \(undefined8 \*\)YYAlloc", r"^\s*uVar\d+ = \(ulong\)\(uint\)param_4;",
    r"^\s*if \(\*\(long \*\)\(lVar\d+ \+ 0x28\)", r"^\s*return param_3;", r"^\s*\{\s*$",
]
NOISE_RE = [re.compile(p) for p in NOISE]

def dbl(hexstr):
    v = int(hexstr, 16)
    d = struct.unpack("<d", struct.pack("<Q", v))[0]
    return d

def fmt_const(m):
    h = m.group(0)
    v = int(h, 16)
    if v >> 32 == 0x1000001 or (v >> 32) & 0xffffff00 == 0x1000000:
        return f"REF(kind={v >> 32:#x},idx={v & 0xffffffff})"
    if len(h) >= 12:
        d = dbl(h)
        if d == d and abs(d) < 1e18 and (d == 0 or abs(d) > 1e-9):
            return repr(d)
    return h

def condense(src):
    out = []
    import collections
    cnt = collections.Counter(re.findall(r"^\s*(local_[0-9a-f]+) = (?:0x[0-9a-f]+|\d+);\s*$", src, re.M))
    linevar = cnt.most_common(1)[0][0] if cnt and cnt.most_common(1)[0][1] >= 3 else None
    for line in src.splitlines():
        s = line.rstrip()
        if not s.strip():
            continue
        if any(r.search(s) for r in NOISE_RE):
            continue
        # GML line numbers
        m = re.match(r"^\s*(local_[0-9a-f]+) = (0x[0-9a-f]+|\d+);\s*$", s)
        if m and m.group(1) == linevar:
            out.append(f"  #L{int(m.group(2), 0)}")
            continue
        s = re.sub(r"g_VAR_([A-Za-z0-9_]+)\._8_4_", r"$\1", s)
        s = re.sub(r"g_FUNC_([A-Za-z0-9_]+)\._8_4_", r"\1", s)
        s = re.sub(r"\(RValue \*\)|\(YYRValue \*\)|\(YYObjectBase \*\)|\(CInstance \*\)|\(undefined8 \*\)|\(undefined4 \*\)|\(ulong\)|\(uint\)|\(long\)|\(int\)", "", s)
        s = re.sub(r"&?(DAT_[0-9a-f]+)", lambda m: ('"' + STRMAP[m.group(1)].strip().strip('"') + '"') if m.group(1) in STRMAP else m.group(0), s)
        s = re.sub(r"&DAT_([0-9a-f]{16})", lambda m: repr(dbl(m.group(1))) if m.group(1) not in STRMAP and "DAT_"+m.group(1) not in STRMAP else m.group(0), s)
        s = re.sub(r"0x[0-9a-f]{9,16}", fmt_const, s)
        s = s.replace("YYRValue::operator=", "ASSIGN").replace("YYGML_Variable_GetValue", "GET").replace("YYGML_Variable_SetValue", "SET")
        s = s.replace("YYGML_CallLegacyFunction", "CALL").replace("ARRAY_LVAL_RValue", "ARR").replace("YYCompareVal", "CMP")
        s = s.replace("(**(code **)(*(long *)param_1 + 0x18))(param_1,", "SELF.(").replace("(**(code **)(*g_pGlobal + 0x10))(g_pGlobal,", "GLOBAL.(")
        s = s.replace("(**(code **)(*param_1 + 0x18))(param_1,", "SELF.(").replace("(**(code **)(*(long *)g_pGlobal + 0x10))(g_pGlobal,", "GLOBAL.(")
        s = s.replace("g_GMLMathEpsilon,", "").replace("param_1,param_2,", "")
        out.append(s)
    txt = "\n".join(out)
    # self.X[idx] = value   (ASSIGN form)
    txt = re.sub(r"p[YR]Var\d+ = \n?\s*SELF\.\(\$(\w+)\);\n\s*iVar\d+ = INT32_RValue\(&(local_\w+)\);\n\s*p[YR]Var\d+ = ARR\(p[YR]Var\d+,iVar\d+\);\n(?:\s*\}\n)?\s*ASSIGN\(p[YR]Var\d+,(.+?)\);", r"  self.\1[\2] = \3", txt)
    # self.X[idx] = number   (direct store form)
    txt = re.sub(r"p[YR]Var\d+ = \n?\s*SELF\.\(\$(\w+)\);\n\s*iVar\d+ = INT32_RValue\(&(local_\w+)\);\n\s*p[YR]Var\d+ = ARR\(p[YR]Var\d+,iVar\d+\);\n(?:\s*\}\n)?\s*\*\(p[YR]Var\d+ \+ 0xc\) = 0;\n\s*\*\(undefined1 \*\*\)p[YR]Var\d+ = (.+?);", r"  self.\1[\2] = \3", txt)
    txt = re.sub(r"p[YR]Var\d+ = \n?\s*SELF\.\(\$(\w+)\);\n\s*iVar\d+ = INT32_RValue\(&(local_\w+)\);\n\s*p[YR]Var\d+ = ARR\(p[YR]Var\d+,iVar\d+\);\n(?:\s*\}\n)?\s*\*\(p[YR]Var\d+ \+ 0xc\) = 0;", r"  self.\1[\2] = 0.0", txt)
    # global reads: local_80 = g_pGlobal; GET(&local_80,$Y,idx,&local_90,...)
    txt = re.sub(r"(local_\w+) = g_pGlobal;\n\s*GET\n?\s*\(&\1,\$(\w+),(-?\w+),&(local_\w+),false,false\);", r"  \4 = global.\2[\3]", txt)
    txt = re.sub(r"GET\n?\s*\(&(local_\w+),\$(\w+),(-?\w+),&(local_\w+),false,false\);", r"  \4 = \1.\2[\3]", txt)
    # comparisons
    txt = re.sub(r"(local_\w+) = ([-\d.e+]+|\d+\.\d+);\n\s*(iVar\d+) = CMP\(&(local_\w+),&\1,(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\3 == 0\)", r"  if (\4 == \2)", txt)
    txt = re.sub(r"(local_\w+) = ([-\d.e+]+|\d+\.\d+);\n\s*(iVar\d+) = CMP\(&(local_\w+),&\1,(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\3 != 0\)", r"  if (\4 != \2)", txt)
    txt = re.sub(r"(local_\w+) = ([-\d.e+]+|\d+\.\d+);\n\s*(iVar\d+) = CMP\(&(local_\w+),&\1,(?:true|false)\);\n(?:\s*\}\n)?\s*if \(-1 < \3\)", r"  if (\4 >= \2)", txt)
    txt = re.sub(r"(local_\w+) = ([-\d.e+]+|\d+\.\d+);\n\s*(iVar\d+) = CMP\(&(local_\w+),&\1,(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\3 < 0\)", r"  if (\4 < \2)", txt)
    txt = re.sub(r"(local_\w+) = ([-\d.e+]+|\d+\.\d+);\n\s*(iVar\d+) = CMP\(&(local_\w+),&\1,(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\3 < 1\)", r"  if (\4 <= \2)", txt)
    txt = re.sub(r"(local_\w+) = ([-\d.e+]+|\d+\.\d+);\n\s*(iVar\d+) = CMP\(&(local_\w+),&\1,(?:true|false)\);\n(?:\s*\}\n)?\s*if \(0 < \3\)", r"  if (\4 > \2)", txt)
    txt = re.sub(r"(iVar\d+) = CMP\(&(local_\w+),&(local_\w+),(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\1 == 0\)", r"  if (\2 == \3)", txt)
    txt = re.sub(r"(iVar\d+) = CMP\(&(local_\w+),&(local_\w+),(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\1 != 0\)", r"  if (\2 != \3)", txt)
    txt = re.sub(r"(iVar\d+) = CMP\(&(local_\w+),&(local_\w+),(?:true|false)\);\n(?:\s*\}\n)?\s*if \(-1 < \1\)", r"  if (\2 >= \3)", txt)
    txt = re.sub(r"(iVar\d+) = CMP\(&(local_\w+),&(local_\w+),(?:true|false)\);\n(?:\s*\}\n)?\s*if \(\1 < 0\)", r"  if (\2 < \3)", txt)
    txt = re.sub(r"\n\s*\}\n(\s*\}\n)+", "\n  }\n", txt)
    return txt

if __name__ == "__main__":
    for f in sys.argv[1:]:
        print(f"==== {os.path.basename(f)} ====")
        print(condense(open(f, encoding="utf-8", errors="replace").read()))
