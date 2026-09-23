"""Non-destructive source/resource regression checks for Nawam."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8", errors="replace")


class BrandingTests(unittest.TestCase):
    def test_product_identity(self):
        header = source("src/rufus.h")
        resource = source("src/rufus.rc")
        self.assertRegex(header, r'#define APPLICATION_NAME\s+"Nawam"')
        self.assertRegex(header, r'#define COMPANY_NAME\s+"SHANNA Digital Systems"')
        for field, value in {
            "ProductName": "Nawam",
            "FileDescription": "Nawam Bootable USB Creator",
            "InternalName": "Nawam",
            "OriginalFilename": "Nawam.exe",
            "CompanyName": "Shanna Studio",
            "FileVersion": "1.0.2",
            "ProductVersion": "1.0.2",
            "Comments": "https://nawam.shanna.id",
        }.items():
            self.assertIn(f'VALUE "{field}", "{value}"', resource)
        self.assertIn('CAPTION "Nawam 1.0.2"', resource)
        self.assertIn("FILEVERSION 1,0,2,0", resource)
        self.assertIn("PRODUCTVERSION 1,0,2,0", resource)
        self.assertIn('"../res/nawam.ico"', resource)
        self.assertNotRegex(resource, r'CAPTION "[^"]*Rufus')
        self.assertIn("Pete Batard", resource)
        self.assertIn("2026 Shanna Studio", resource)


class IsolationTests(unittest.TestCase):
    def test_private_paths(self):
        main = source("src/rufus.c")
        for expected in ['"%snawam.ini"', '"nawam.log"', '"nawam.loc"',
                         '"%snawam.app"', '"Global/Nawam_CmdLine"']:
            self.assertIn(expected, main)
        for old in ['"%srufus.ini"', '"rufus.log"', '"rufus.loc"', '"%srufus.app"']:
            self.assertNotIn(old, main)
        registry = source("src/registry.h")
        self.assertIn('COMPANY_NAME "\\\\" APPLICATION_NAME', registry)

    def test_disk_safety_mutex_shared_with_upstream(self):
        main = source("src/rufus.c")
        self.assertEqual(main.count('CreateMutexA(NULL, TRUE, "Global/Rufus")'), 2)

    def test_about_semver_and_fork_support(self):
        about = source("src/license.h").split('const char* legal_notice_format', 1)[0]
        self.assertIn('Nawam %d.%d.%d', about)
        self.assertIn('https://nawam.shanna.id', about)

    def test_generated_branding_links(self):
        self.assertIn('LTEXT(NAWAM_WEBSITE)', source("src/icon.c"))
        self.assertIn('label, APPLICATION_NAME, NAWAM_WEBSITE', source("src/vhd.c"))
        self.assertIn('ShellExecuteA(hDlg, "open", NAWAM_WEBSITE', source("src/stdlg.c"))

    def test_update_controls_disabled(self):
        dialogs = source("src/stdlg.c")
        for expected in ['EnableWindow(hFrequency, FALSE)', 'EnableWindow(hBeta, FALSE)',
                         'EnableWindow(GetDlgItem(hDlg, IDC_CHECK_NOW), !op_in_progress && image_path == NULL)',
                         'No Nawam update server is configured.']:
            self.assertIn(expected, dialogs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
