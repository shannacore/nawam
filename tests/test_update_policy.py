"""Compile actual disabled entrypoints with hostile settings; no network mocks."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function_body(file, signature):
    text = (ROOT / file).read_text(encoding="utf-8")
    start = text.index(signature)
    brace = text.index("{", start)
    level = 1
    end = brace + 1
    while level:
        level += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class UpdateTests(unittest.TestCase):
    def test_disabled_update_entrypoints(self):
        net = function_body("src/net.c", "BOOL CheckForUpdates(BOOL force)")
        stdlg = function_body("src/stdlg.c", "BOOL SetUpdateCheck(void)")
        download = function_body("src/stdlg.c", "void DownloadNewVersion(void)")
        # Preprocess actual policy and entrypoint code; all legacy branches must
        # disappear. Undefined network/UI symbols then deliberately fail linkage.
        header = ROOT / "src/nawam_policy.h"
        self.assertTrue(header.exists(), "Nawam requires an explicit update policy")
        stub = '#include "nawam_policy.h"\n'
        stub += '#define BOOL int\n#define FALSE 0\n#define IGNORE_RETVAL(x) (void)(x)\n'
        stub += '#define uprintf(...) ((void)0)\n'
        stub += net + "\n" + stdlg + "\n" + download
        stub += '\nint main(void) { DownloadNewVersion(); return CheckForUpdates(1) || CheckForUpdates(0) || SetUpdateCheck(); }\n'
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            src = Path(directory) / "policy.c"
            exe = src.with_suffix(".exe")
            src.write_text(stub)
            compiler = ROOT / "tools/w64devkit/bin/gcc.exe"
            subprocess.run([str(compiler), "-I", str(header.parent), str(src), "-o", str(exe)], check=True)
            self.assertEqual(subprocess.run([str(exe)]).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
