"""Non-destructive checks for About/legal layout and safe UI QA commands."""
from pathlib import Path
import ast
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AboutDialogTests(unittest.TestCase):
    def test_legal_controls_moved_out_of_compact_about(self):
        resource = (ROOT / "src/rufus.rc").read_text(encoding="utf-8-sig")
        about = resource.split("IDD_ABOUTBOX DIALOGEX", 1)[1].split("END", 1)[0]
        legal = resource.split("IDD_LICENSE DIALOGEX", 1)[1].split("END", 1)[0]
        self.assertNotIn("IDC_ABOUT_COPYRIGHTS", about)
        self.assertIn('"License && Open Source"', about)
        self.assertIn('CAPTION "Nawam - License & Open Source"', legal)
        self.assertIn("IDC_ABOUT_COPYRIGHTS", legal)
        self.assertIn("IDC_LICENSE_TEXT", legal)
        self.assertGreaterEqual(legal.count("WS_VSCROLL"), 3)
        about_height = int(about.splitlines()[0].strip().split(",")[-1])
        legal_height = int(legal.splitlines()[0].strip().split(",")[-1])
        self.assertLess(about_height, 160)
        self.assertGreater(legal_height, 300)

    def test_qa_commands_match_resource_ids(self):
        resource = (ROOT / "src/resource.h").read_text()
        ids = dict(re.findall(r"#define\s+(IDC_\w+)\s+(\d+)", resource))
        tree = ast.parse((ROOT / "scripts/qa_ui.py").read_text())
        commands = next(ast.literal_eval(node.value) for node in ast.walk(tree)
                        if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "commands"
                                for t in node.targets))
        for action, symbol in {"about": "IDC_ABOUT", "updates": "IDC_SETTINGS",
                               "log": "IDC_LOG", "select": "IDC_SELECT"}.items():
            self.assertEqual(commands[action], int(ids[symbol]), action)
        self.assertNotIn(int(ids["IDC_START"]), commands.values())


if __name__ == "__main__":
    unittest.main()
