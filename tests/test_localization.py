"""Static Nawam About/localization regressions; never read generated embedded.loc.

Preservation checks use the read-only sibling rufus-master source tree.
Run: python -m unittest discover -s tests -p test_localization.py -v
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT.with_name("rufus-master")


def source(relative, root=ROOT):
    return (root / relative).read_text(encoding="utf-8-sig")


def about_format(text):
    return text.split("const char* about_blurb_format =", 1)[1].split(";", 1)[0]


class AboutTests(unittest.TestCase):
    def test_simple_about_and_separate_legal_notices(self):
        header = source("src/license.h")
        template = about_format(header)
        for text in ("Nawam", "Bootable USB Creator", "Shanna Studio",
                     "https://nawam.shanna.id"):
            self.assertIn(text, template)
        for text in ("Rufus", "Pete Batard", "Axialis", "MSG_176", "Developed by", "SHANNA Digital Systems"):
            self.assertNotIn(text, template)
        self.assertEqual(template.count("%d"), 3)
        dialogs = source("src/stdlg.c")
        about = dialogs.split("INT_PTR CALLBACK AboutCallback", 1)[1].split("INT_PTR CreateAboutBox", 1)[0]
        self.assertNotIn("additional_copyrights", about)
        legal = dialogs.split("INT_PTR CALLBACK LicenseCallback", 1)[1].split("INT_PTR CALLBACK AboutCallback", 1)[0]
        self.assertIn("additional_copyrights", legal)
        self.assertIn("legal_notice_format", legal)
        self.assertIn("gplv3", legal)
        self.assertIn("MSG_176", legal)
        self.assertIn("Nawam is based on the open-source Rufus project.", header)
        self.assertIn("Copyright © 2011-2026 Pete Batard", header)

    def test_gpl_and_other_attributions_unchanged(self):
        if not UPSTREAM.is_dir():
            self.skipTest("read-only sibling rufus-master required for preservation audit")
        old = source("src/license.h", UPSTREAM)
        new = source("src/license.h")
        self.assertEqual(old.split("const char* gplv3 =", 1)[1],
                         new.split("const char* gplv3 =", 1)[1])
        self.assertEqual(old.split("const char* about_blurb_format =", 1)[0],
                         new.split("const char* about_blurb_format =", 1)[0])
        self.assertEqual(
            old.split("const char* additional_copyrights =", 1)[1],
            new.split("const char* additional_copyrights =", 1)[1].replace(
                "Upstream Rufus icon by PC Unleashed (unused retained asset):",
                "Rufus icon by PC Unleashed:",
            ),
        )


# Audited in all translations, not just English: these IDs describe this app.
# MSG_294 (historical Rufus releases), MSG_349 (Rufus MBR), and MSG_176
# (original translator/contact attributions) are deliberately NOT included.
APPLICATION_IDS = frozenset("""
IDD_ABOUTBOX IDD_LICENSE IDD_NEW_VERSION IDD_LOG IDC_WEBSITE
IDS_NEW_VERSION_AVAIL_TXT MSG_001 MSG_002 MSG_004 MSG_005 MSG_048 MSG_049
MSG_080 MSG_082 MSG_084 MSG_104 MSG_108 MSG_114 MSG_116 MSG_133 MSG_134
MSG_174 MSG_182 MSG_184 MSG_186 MSG_196 MSG_243 MSG_246 MSG_247 MSG_248
MSG_249 MSG_255 MSG_275 MSG_285 MSG_296 MSG_298 MSG_300 MSG_337 MSG_339
MSG_354 MSG_900
""".split())
BRAND = re.compile(r"rufus|روفوس|ルーファス|руфус", re.I)
URL = re.compile(r"(?:https?://|mailto:)[^\s\"<>\\]+", re.I)
PRINTF = re.compile(
    r"%(?:\d+\$)?[-+ #0]*(?:\*|\d+)?(?:\.(?:\*|\d+))?"
    r"(?:hh|ll|I64|I32|[hljztL])?[diouxXfFeEgGaAcspn%]"
)
TEXT_LINE = re.compile(r'^(\s*(?:t\s+(\S+)\s+)?)("(?:[^"\\]|\\.)*")(.*)$')


def localized_lines(text):
    """Yield (locale, group, ID), quoted payload, and unchanged syntax per line."""
    locale = group = identifier = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        newline = line[len(body):]
        if body.startswith('l "'):
            locale = re.match(r'l "([^"]+)"', body)[1]
            group = identifier = None
        elif body.startswith("g "):
            group = body.split()[1]
            identifier = None
        match = TEXT_LINE.fullmatch(body)
        if match and (match[2] or identifier):
            identifier = match[2] or identifier
            yield (locale, group, identifier), match[3], (match[1], match[4], newline)
        else:
            yield None, None, (line,)


def expected_application_text(key, payload):
    if key[2] == "MSG_174":
        return '"Nawam - Bootable USB Creator"'
    # Preserve upstream URLs verbatim, even if an app message gains one later.
    result = []
    start = 0
    for match in URL.finditer(payload):
        result.append(rename_brand(payload[start:match.start()]))
        result.append(match[0])
        start = match.end()
    result.append(rename_brand(payload[start:]))
    return "".join(result)


def rename_brand(text):
    # These original translations spell the brand twice in different scripts.
    text = text.replace("روفوس Rufus", "Nawam")
    text = text.replace("Rufus (ルーファス)", "Nawam")
    return BRAND.sub("Nawam", text)


class LocalizationTests(unittest.TestCase):
    def test_every_application_message_uses_nawam(self):
        stale = []
        titles = []
        for key, payload, _ in localized_lines(source("res/loc/rufus.loc")):
            if key is None or key[2] in {"MSG_294", "MSG_349", "MSG_176"}:
                continue
            if BRAND.search(URL.sub("", payload)):
                stale.append(key)
            if key[2] == "MSG_174":
                titles.append((key[0], payload))
        self.assertEqual(stale, [], f"stale application messages: {stale[:8]}")
        self.assertEqual(len(titles), 38)
        self.assertEqual({text for _, text in titles}, {'"Nawam - Bootable USB Creator"'})

    def test_audited_diff_preserves_warnings_formats_and_exceptions(self):
        if not UPSTREAM.is_dir():
            self.skipTest("read-only sibling rufus-master required for preservation audit")
        # Read bytes to also verify original CRLFs, BOM and final-newline state.
        old_bytes = (UPSTREAM / "res/loc/rufus.loc").read_bytes()
        new_bytes = (ROOT / "res/loc/rufus.loc").read_bytes()
        old = list(localized_lines(old_bytes.decode("utf-8")))
        new = list(localized_lines(new_bytes.decode("utf-8")))
        self.assertEqual(len(old), len(new))
        changed_ids = set()
        for before, after in zip(old, new):
            key, payload, syntax = before
            self.assertEqual(key, after[0])
            self.assertEqual(syntax, after[2], key)
            if key is None:
                continue
            actual = after[1]
            self.assertEqual(PRINTF.findall(payload), PRINTF.findall(actual), key)
            self.assertEqual(URL.findall(payload), URL.findall(actual), key)
            if key[2] in APPLICATION_IDS:
                self.assertEqual(actual, expected_application_text(key, payload), key)
                if payload != actual:
                    changed_ids.add(key[2])
            else:
                self.assertEqual(payload, actual, key)
        self.assertEqual(changed_ids, APPLICATION_IDS)
        self.assertEqual(len({key[0] for key, _, _ in old if key}), 38)


if __name__ == "__main__":
    unittest.main(verbosity=2)
