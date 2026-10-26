#!/usr/bin/env python3
"""Patch AndroidManifest.xml (raw AXML or inside an APK) to enable android:debuggable="true".

Directly manipulates the binary XML (AXML) structures without requiring apktool or
recompiling resources:
  1. Locates or inserts "debuggable" into the String Pool.
  2. Ensures the Resource Map maps the string index to android.R.attr.debuggable (0x0101000f).
  3. Finds the <application> element and either updates an existing debuggable attribute
     or inserts a new android:debuggable="true" attribute.
  4. Fixes up chunk headers and offsets.

When targeting an APK, old META-INF/ signatures are stripped so the output is ready
for zipalign and apksigner.

Usage:
  tools/patch_manifest.py input.apk output.apk
  tools/patch_manifest.py AndroidManifest.xml AndroidManifest.patched.xml
"""

import os
import struct
import sys
import zipfile

ATTR_DEBUGGABLE_RES_ID = 0x0101000F
ANDROID_NS_URI = "http://schemas.android.com/apk/res/android"
TYPE_INT_BOOLEAN = 0x12
BOOL_TRUE_VAL = 0xFFFFFFFF


def parse_string_pool(data, sp_pos):
    """Parse AXML string pool chunk at sp_pos."""
    sp_type, sp_header_size, sp_size, str_count, style_count, flags, str_start, style_start = struct.unpack_from(
        "<HHIIIIII", data, sp_pos
    )
    is_utf8 = bool(flags & (1 << 8))
    offsets = list(struct.unpack_from(f"<{str_count}I", data, sp_pos + sp_header_size))

    strings = []
    for off in offsets:
        p = sp_pos + str_start + off
        if is_utf8:
            u16len = data[p]
            p += 1
            if u16len & 0x80:
                u16len = ((u16len & 0x7F) << 8) | data[p]
                p += 1
            u8len = data[p]
            p += 1
            if u8len & 0x80:
                u8len = ((u8len & 0x7F) << 8) | data[p]
                p += 1
            s = data[p : p + u8len].decode("utf-8", errors="replace")
        else:
            u16len = struct.unpack_from("<H", data, p)[0]
            p += 2
            if u16len & 0x8000:
                u16len = ((u16len & 0x7FFF) << 16) | struct.unpack_from("<H", data, p)[0]
                p += 2
            s = data[p : p + u16len * 2].decode("utf-16le", errors="replace")
        strings.append(s)

    return {
        "pos": sp_pos,
        "type": sp_type,
        "header_size": sp_header_size,
        "size": sp_size,
        "str_count": str_count,
        "style_count": style_count,
        "flags": flags,
        "is_utf8": is_utf8,
        "str_start": str_start,
        "style_start": style_start,
        "offsets": offsets,
        "strings": strings,
    }


def add_string(data, sp, new_str):
    """Add string to string pool if missing. Return (new_data, string_index, sp_size_delta)."""
    if new_str in sp["strings"]:
        return data, sp["strings"].index(new_str), 0

    is_utf8 = sp["is_utf8"]
    if is_utf8:
        u8 = new_str.encode("utf-8")
        u16_len = len(new_str)
        enc = bytearray()
        if u16_len > 0x7F:
            enc.extend([0x80 | ((u16_len >> 8) & 0x7F), u16_len & 0xFF])
        else:
            enc.append(u16_len)
        if len(u8) > 0x7F:
            enc.extend([0x80 | ((len(u8) >> 8) & 0x7F), len(u8) & 0xFF])
        else:
            enc.append(len(u8))
        enc.extend(u8)
        enc.append(0)
    else:
        u16 = new_str.encode("utf-16le")
        u16_len = len(new_str)
        enc = bytearray()
        if u16_len > 0x7FFF:
            enc.extend(struct.pack("<HH", 0x8000 | ((u16_len >> 16) & 0x7FFF), u16_len & 0xFFFF))
        else:
            enc.extend(struct.pack("<H", u16_len))
        enc.extend(u16)
        enc.extend(b"\x00\x00")

    sp_pos = sp["pos"]
    str_start = sp["str_start"]
    style_start = sp["style_start"]
    strings_end = style_start if style_start else sp["size"]
    new_offsets = sp["offsets"] + [strings_end - str_start]
    # Style offsets follow the string offsets and must be carried over unchanged
    so_pos = sp_pos + sp["header_size"] + sp["str_count"] * 4
    style_offsets = data[so_pos : so_pos + sp["style_count"] * 4]

    new_str_start = sp["header_size"] + len(new_offsets) * 4 + len(style_offsets)
    new_strings = data[sp_pos + str_start : sp_pos + strings_end] + bytes(enc)
    new_strings += b"\x00" * (-len(new_strings) % 4)  # style data must start 4-aligned
    old_styles = data[sp_pos + style_start : sp_pos + sp["size"]] if style_start else b""
    new_style_start = new_str_start + len(new_strings) if style_start else 0
    total_data = new_strings + old_styles
    if len(total_data) % 4 != 0:
        total_data += b"\x00" * (4 - (len(total_data) % 4))

    new_sp_size = new_str_start + len(total_data)
    new_sp_header = struct.pack(
        "<HHIIIIII",
        sp["type"],
        sp["header_size"],
        new_sp_size,
        len(new_offsets),
        sp["style_count"],
        sp["flags"] & ~1,  # appended string breaks SORTED_FLAG order
        new_str_start,
        new_style_start,
    )
    new_offsets_bytes = struct.pack(f"<{len(new_offsets)}I", *new_offsets)
    new_sp = new_sp_header + new_offsets_bytes + style_offsets + total_data

    new_data = data[:sp_pos] + new_sp + data[sp_pos + sp["size"] :]
    delta = len(new_sp) - sp["size"]
    new_idx = len(sp["strings"])
    return new_data, new_idx, delta


def patch_manifest_axml(axml_bytes):
    """Patch raw binary AXML bytes to set android:debuggable='true' on <application>.

    Returns patched bytes.
    """
    data = bytearray(axml_bytes)
    header_type, header_size, file_size = struct.unpack_from("<HHI", data, 0)
    assert header_type == 0x0003, f"Not an AXML file (type: 0x{header_type:04x})"

    # 1. Parse string pool
    sp_pos = header_size
    sp = parse_string_pool(data, sp_pos)

    # 2. Add or find "debuggable"
    data, debug_str_idx, sp_delta = add_string(data, sp, "debuggable")
    if sp_delta != 0:
        sp = parse_string_pool(data, sp_pos)

    # Find or add android namespace URI
    data, android_ns_idx, sp_delta2 = add_string(data, sp, ANDROID_NS_URI)
    if sp_delta2 != 0:
        sp = parse_string_pool(data, sp_pos)

    # 3. Update Resource Map
    rm_pos = sp_pos + sp["size"]
    rm_type, rm_header_size, rm_size = struct.unpack_from("<HHI", data, rm_pos)
    if rm_type == 0x0180:
        rm_count = (rm_size - rm_header_size) // 4
        res_ids = list(struct.unpack_from(f"<{rm_count}I", data, rm_pos + rm_header_size))
        # Ensure res_ids covers debug_str_idx
        while len(res_ids) <= debug_str_idx:
            res_ids.append(0)
        res_ids[debug_str_idx] = ATTR_DEBUGGABLE_RES_ID

        new_rm_size = rm_header_size + len(res_ids) * 4
        new_rm_header = struct.pack("<HHI", rm_type, rm_header_size, new_rm_size)
        new_rm = new_rm_header + struct.pack(f"<{len(res_ids)}I", *res_ids)
        data = data[:rm_pos] + new_rm + data[rm_pos + rm_size :]
        rm_size = new_rm_size
    else:
        # Create resource map if missing
        res_ids = [0] * (debug_str_idx + 1)
        res_ids[debug_str_idx] = ATTR_DEBUGGABLE_RES_ID
        rm_header_size = 8
        new_rm_size = rm_header_size + len(res_ids) * 4
        new_rm = struct.pack("<HHI", 0x0180, rm_header_size, new_rm_size) + struct.pack(f"<{len(res_ids)}I", *res_ids)
        data = data[:rm_pos] + new_rm + data[rm_pos:]
        rm_size = new_rm_size

    # 4. Walk XML chunks to locate <application>
    nodes_pos = rm_pos + rm_size
    pos = nodes_pos
    app_found = False

    while pos < len(data):
        chunk_type, chunk_header_size, chunk_size = struct.unpack_from("<HHI", data, pos)
        if chunk_size <= 0:
            break
        if chunk_type == 0x0102:  # RES_XML_START_ELEMENT_TYPE
            line_num, comment = struct.unpack_from("<II", data, pos + 8)
            ns, name, attr_start, attr_size, attr_count, id_idx, class_idx, style_idx = struct.unpack_from(
                "<IIHHHHHH", data, pos + 16
            )
            elem_name = sp["strings"][name] if name < len(sp["strings"]) else ""
            if elem_name == "application":
                app_found = True
                # Check if android:debuggable is already present; the framework identifies
                # it by resource ID, so tools:debuggable etc. don't count
                existing_attr_idx = -1
                for a in range(attr_count):
                    ap = pos + 16 + attr_start + a * attr_size
                    ans, aname = struct.unpack_from("<II", data, ap)
                    if ans == android_ns_idx and aname < len(res_ids) and res_ids[aname] == ATTR_DEBUGGABLE_RES_ID:
                        existing_attr_idx = a
                        break

                if existing_attr_idx >= 0:
                    # Update existing attribute in place: no raw string, typed boolean true
                    ap = pos + 16 + attr_start + existing_attr_idx * attr_size
                    struct.pack_into("<I", data, ap + 8, 0xFFFFFFFF)
                    struct.pack_into("<B", data, ap + 15, TYPE_INT_BOOLEAN)
                    struct.pack_into("<I", data, ap + 16, BOOL_TRUE_VAL)
                    print(f"  Updated existing android:debuggable attribute to true at index {existing_attr_idx}")
                else:
                    # Find insertion index to maintain sorted order by resource ID.
                    # Android's BackTrackingAttributeFinder assumes attributes within the
                    # framework package (0x01) are sorted by resource ID.
                    insert_idx = attr_count
                    for a in range(attr_count):
                        ap = pos + 16 + attr_start + a * attr_size
                        _, aname, _, _, _, _, _ = struct.unpack_from("<IIIHBBI", data, ap)
                        a_resid = res_ids[aname] if aname < len(res_ids) else 0
                        if a_resid > ATTR_DEBUGGABLE_RES_ID:
                            insert_idx = a
                            break

                    attr_insert_pos = pos + 16 + attr_start + insert_idx * attr_size
                    new_attr = struct.pack(
                        "<IIIHBBI",
                        android_ns_idx,
                        debug_str_idx,
                        0xFFFFFFFF,  # rawValue
                        8,           # typedValue size
                        0,           # res0
                        TYPE_INT_BOOLEAN,
                        BOOL_TRUE_VAL,
                    )
                    data[attr_insert_pos:attr_insert_pos] = new_attr
                    # Update application chunk header: chunk_size += len(new_attr), attr_count += 1
                    struct.pack_into("<I", data, pos + 4, chunk_size + len(new_attr))
                    struct.pack_into("<H", data, pos + 16 + 12, attr_count + 1)
                    # id/class/style indices are 1-based attribute positions (0 = none)
                    for off, idx in ((14, id_idx), (16, class_idx), (18, style_idx)):
                        if idx > insert_idx:
                            struct.pack_into("<H", data, pos + 16 + off, idx + 1)
                    print(f"  Inserted android:debuggable='true' attribute at index {insert_idx} in <application>")
                break
        pos += chunk_size

    assert app_found, "Could not find <application> element in manifest"

    # 5. Update root file_size
    struct.pack_into("<I", data, 4, len(data))
    return bytes(data)


def rezip(src_apk, dst_apk, replacements):
    """Copy src_apk to dst_apk without old signatures, swapping in replacements {name: bytes}."""
    os.makedirs(os.path.dirname(os.path.abspath(dst_apk)), exist_ok=True)
    with zipfile.ZipFile(src_apk, "r") as zin, zipfile.ZipFile(dst_apk, "w") as zout:
        for item in zin.infolist():
            if item.filename.startswith("META-INF/"):
                continue
            data = replacements[item.filename] if item.filename in replacements else zin.read(item.filename)
            ni = zipfile.ZipInfo(item.filename, date_time=item.date_time)
            ni.compress_type = item.compress_type
            ni.external_attr = item.external_attr
            zout.writestr(ni, data)


def patch_apk(src_apk, dst_apk):
    """Read src_apk, patch AndroidManifest.xml, drop old signatures, and write dst_apk."""
    with zipfile.ZipFile(src_apk, "r") as zin:
        manifest_bytes = zin.read("AndroidManifest.xml")
    rezip(src_apk, dst_apk, {"AndroidManifest.xml": patch_manifest_axml(manifest_bytes)})


def is_zip_file(path):
    try:
        with open(path, "rb") as f:
            magic = f.read(4)
            return magic == b"PK\x03\x04"
    except Exception:
        return False


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <input.apk|AndroidManifest.xml> <output.apk|AndroidManifest.patched.xml>")
        sys.exit(1)

    src = sys.argv[1]
    dst = sys.argv[2]

    if not os.path.exists(src):
        print(f"Error: input file '{src}' does not exist", file=sys.stderr)
        sys.exit(1)

    if is_zip_file(src) or src.endswith(".apk"):
        print(f"Patching APK: {src} -> {dst}")
        patch_apk(src, dst)
        print(f"Done. Unsigned APK written to {dst}")
    else:
        print(f"Patching raw AXML: {src} -> {dst}")
        raw = open(src, "rb").read()
        patched = patch_manifest_axml(raw)
        with open(dst, "wb") as f:
            f.write(patched)
        print(f"Done. Patched AXML written to {dst}")


if __name__ == "__main__":
    main()
