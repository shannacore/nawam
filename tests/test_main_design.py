"""Native single-panel design invariants; never launches the disk utility."""
from pathlib import Path
import hashlib
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT.parent / "rufus-master"
SHIFT = 38
EXTRA_WIDTH = 40


def main_dialog(path):
    text = path.read_text(encoding="latin-1")
    return re.search(r"^IDD_DIALOG DIALOGEX.*?^END$", text, re.M | re.S).group()


def controls(dialog):
    body = dialog.split("BEGIN\n", 1)[1].rsplit("\nEND", 1)[0]
    body = re.sub(r"\n\s+(?=\")", " ", body)
    result = []
    for line in body.splitlines():
        match = re.search(r",\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\d+)(?=,|$)", line)
        if match:
            result.append((line[:match.start()], tuple(map(int, match.groups())), line[match.end():]))
    return result


class MainDesignTests(unittest.TestCase):
    def test_reserved_header_preserves_every_native_control(self):
        self.assertTrue(UPSTREAM.is_dir(), "Immutable upstream sibling required for comparison")
        old = main_dialog(UPSTREAM / "src/rufus.rc")
        new = main_dialog(ROOT / "src/rufus.rc")
        before, after = controls(old), controls(new)
        self.assertGreater(len(before), 35)
        self.assertEqual(len(before), len(after))
        for (old_prefix, old_rect, old_suffix), (prefix, rect, suffix) in zip(before, after):
            with self.subTest(control=old_prefix):
                self.assertEqual(prefix, old_prefix, "Native ID, label, class or sequence changed")
                self.assertEqual(suffix, old_suffix, "Native style/safety state changed")
                x, y, w, h = old_rect
                self.assertEqual(rect, (x, y + SHIFT, w + (EXTRA_WIDTH if "IDS_DEVICE_TXT" in prefix else 0), h))
        old_size = tuple(map(int, re.findall(r"\d+", old.splitlines()[0])))
        new_size = tuple(map(int, re.findall(r"\d+", new.splitlines()[0])))
        self.assertEqual(new_size, (*old_size[:2], old_size[2] + EXTRA_WIDTH, old_size[3] + SHIFT))
        self.assertEqual(re.search(r"^FONT.*$", old, re.M).group(), re.search(r"^FONT.*$", new, re.M).group())

    def test_existing_layout_and_disk_algorithms_untouched(self):
        # Paint-only additions must not disturb any of the carefully measured
        # row heights, hidden-control deltas, formatting or progress algorithms.
        old = (UPSTREAM / "src/ui.c").read_text(encoding="utf-8-sig")
        new = (ROOT / "src/ui.c").read_text(encoding="utf-8-sig")
        marker = "// Create the horizontal section lines"
        self.assertEqual(new.split(marker)[0], old.split(marker)[0])
        manifest = json.loads((ROOT / "docs/upstream-sha256.json").read_text())
        for name in ("src/format.c", "src/drive.c", "src/badblocks.c", "src/ui_data.h"):
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), manifest[name], name)

    def test_header_uses_original_resource_without_new_child_panel(self):
        source = (ROOT / "src/ui.c").read_text(encoding="utf-8-sig")
        paint = source.split("// Create the horizontal section lines", 1)[1]
        self.assertIn('L"Nawam"', paint)
        self.assertIn('MAKEINTRESOURCEW(IDI_ICON)', paint)
        self.assertIn('DrawIconEx', paint)
        self.assertIn('DestroyIcon', paint)
        self.assertIn('MapDialogRect', paint)
        self.assertIn('SPI_GETHIGHCONTRAST', paint)
        self.assertNotIn('CreateWindow', paint)
        self.assertNotIn('SetWindowTheme', paint)
        self.assertNotIn('EnableWindow', paint)
        self.assertIn('SaveDC', paint)
        self.assertIn('RestoreDC', paint)

    def test_workarea_guard_reports_without_resizing_fonts(self):
        source = (ROOT / "src/ui.c").read_text(encoding="utf-8-sig")
        self.assertIn('BOOL NawamCheckMainWorkArea(HWND hDlg)', source)
        guard = source.split('BOOL NawamCheckMainWorkArea(HWND hDlg)', 1)[1].split('void OnPaint', 1)[0]
        self.assertIn('GetMonitorInfo', guard)
        self.assertIn('GetWindowRect', guard)
        self.assertIn('uprintf', guard)
        self.assertIn('advanced_device_section_height', guard)
        self.assertIn('advanced_format_section_height', guard)
        self.assertNotIn('WM_SETFONT', guard)
        self.assertNotIn('MoveWindow', guard)
        self.assertEqual(guard.count('expanded_height += rh;'), 1)

    def test_main_dialog_uses_new_theme_hooks(self):
        source = (ROOT / "src/rufus.c").read_text(encoding="utf-8")
        self.assertIn("case WM_CTLCOLORDLG:", source)
        self.assertIn("NawamMainControlBrush", source)
        self.assertIn("NawamCheckMainWorkArea(hDlg)", source)

    def test_resource_scaling_has_constant_clearance(self):
        # Geometry scales rather than shrinking fonts: test each requested DPI.
        for dpi in (96, 144, 192):
            with self.subTest(dpi=dpi):
                old = controls(main_dialog(UPSTREAM / "src/rufus.rc"))
                new = controls(main_dialog(ROOT / "src/rufus.rc"))
                for (_, a, _), (_, b, _) in zip(old, new):
                    self.assertEqual((b[1] - a[1]) * dpi / 96, SHIFT * dpi / 96)


if __name__ == "__main__":
    unittest.main()
