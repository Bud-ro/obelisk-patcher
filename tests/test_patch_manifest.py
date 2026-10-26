#!/usr/bin/env python3
"""Unit tests for tools/patch_manifest.py."""

import os
import struct
import shutil
import subprocess
import tempfile
import unittest
import zipfile

from tools.patch_manifest import (
    ANDROID_NS_URI,
    ATTR_DEBUGGABLE_RES_ID,
    parse_string_pool,
    patch_apk,
    patch_manifest_axml,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_APK = os.path.join(REPO_ROOT, "input", "base.apk")


def build_axml():
    """Minimal sorted UTF-16 AXML with one style span and <application theme allowBackup> (styleIndex=2)."""
    strings = ["theme", "allowBackup", ANDROID_NS_URI, "application", "styled"]
    enc, offs = b"", []
    for x in strings:
        offs.append(len(enc))
        enc += struct.pack("<H", len(x)) + x.encode("utf-16le") + b"\0\0"
    enc += b"\0" * (-len(enc) % 4)
    styles = struct.pack("<7I", 3, 0, 1, 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)[:24]
    str_start = 28 + len(strings) * 4 + 4
    sp = struct.pack("<HHIIIIII", 1, 28, str_start + len(enc) + len(styles), len(strings), 1, 1, str_start, str_start + len(enc))
    sp += struct.pack(f"<{len(strings)}I", *offs) + struct.pack("<I", 0) + enc + styles
    rm = struct.pack("<HHI2I", 0x0180, 8, 16, 0x01010000, 0x01010280)
    attrs = b"".join(struct.pack("<IIIHBBI", 2, n, 0xFFFFFFFF, 8, 0, 0x10, 1) for n in (0, 1))
    el = struct.pack("<HHIII", 0x0102, 16, 36 + len(attrs), 1, 0xFFFFFFFF)
    el += struct.pack("<IIHHHHHH", 0xFFFFFFFF, 3, 20, 20, 2, 0, 0, 2) + attrs
    body = sp + rm + el
    return struct.pack("<HHI", 3, 8, 8 + len(body)) + body


class TestSyntheticAxml(unittest.TestCase):
    def test_styles_indices_and_flags_survive(self):
        orig = build_axml()
        out = patch_manifest_axml(orig)
        before, after = parse_string_pool(orig, 8), parse_string_pool(out, 8)
        self.assertEqual(after["strings"][:5], before["strings"])
        self.assertEqual(after["style_count"], 1)
        self.assertEqual(after["style_start"] % 4, 0)
        self.assertEqual(out[8 + after["style_start"] : 8 + after["size"]],
                         orig[8 + before["style_start"] : 8 + before["size"]])
        self.assertEqual(after["flags"] & 1, 0)
        # <application>: debuggable lands between theme and allowBackup, styleIndex follows allowBackup
        el = 8 + after["size"] + struct.unpack_from("<I", out, 8 + after["size"] + 4)[0]
        count, _, _, style_idx = struct.unpack_from("<4H", out, el + 16 + 12)
        self.assertEqual((count, style_idx), (3, 3))
        names = [after["strings"][struct.unpack_from("<I", out, el + 36 + i * 20 + 4)[0]] for i in range(3)]
        self.assertEqual(names, ["theme", "debuggable", "allowBackup"])
        # Re-patching updates in place
        self.assertEqual(patch_manifest_axml(out), out)


@unittest.skipUnless(os.path.exists(BASE_APK), "input/base.apk not present (gitignored)")
class TestPatchManifest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.zin = zipfile.ZipFile(BASE_APK, "r")
        self.orig_manifest = self.zin.read("AndroidManifest.xml")

    def tearDown(self):
        self.zin.close()
        shutil.rmtree(self.tmpdir)

    def test_patch_raw_axml(self):
        """Test patching raw AXML manifest bytes."""
        patched = patch_manifest_axml(self.orig_manifest)
        self.assertGreater(len(patched), len(self.orig_manifest))

        # Check that debuggable is present in string pool
        sp = parse_string_pool(patched, 8)
        self.assertIn("debuggable", sp["strings"])
        debug_idx = sp["strings"].index("debuggable")

        # Verify resource map entry
        rm_pos = 8 + sp["size"]
        rm_type, rm_hdr_size, rm_size = struct_unpack_rm_hdr(patched, rm_pos)
        self.assertEqual(rm_type, 0x0180)
        res_ids = struct_unpack_res_ids(patched, rm_pos + rm_hdr_size, (rm_size - rm_hdr_size) // 4)
        self.assertEqual(res_ids[debug_idx], ATTR_DEBUGGABLE_RES_ID)

    def test_idempotent_patch(self):
        """Test patching an already-patched manifest updates in-place without error."""
        patched1 = patch_manifest_axml(self.orig_manifest)
        patched2 = patch_manifest_axml(patched1)
        self.assertEqual(len(patched1), len(patched2))

    def test_patch_apk(self):
        """Test patching an entire APK."""
        out_apk = os.path.join(self.tmpdir, "base.unsigned.apk")
        patch_apk(BASE_APK, out_apk)
        self.assertTrue(os.path.exists(out_apk))

        with zipfile.ZipFile(out_apk, "r") as zout:
            # META-INF should be stripped
            for name in zout.namelist():
                self.assertFalse(name.startswith("META-INF/"), f"META-INF file not stripped: {name}")

            # AndroidManifest.xml should be patched
            manifest = zout.read("AndroidManifest.xml")
            sp = parse_string_pool(manifest, 8)
            self.assertIn("debuggable", sp["strings"])


def struct_unpack_rm_hdr(data, pos):
    import struct
    return struct.unpack_from("<HHI", data, pos)


def struct_unpack_res_ids(data, pos, count):
    import struct
    return list(struct.unpack_from(f"<{count}I", data, pos))


if __name__ == "__main__":
    unittest.main()
