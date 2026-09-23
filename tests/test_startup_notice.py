"""Exercise the real startup gate in isolation; never launch Nawam or touch drives."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source():
    return (ROOT / "src/rufus.c").read_text(encoding="utf-8")


def block_after(text, marker):
    start = text.index(marker)
    brace = text.index("{", start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class StartupNoticeTests(unittest.TestCase):
    def compile_run(self, code):
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            src = Path(directory) / "notice.c"
            exe = src.with_suffix(".exe")
            src.write_text(code, encoding="utf-8")
            subprocess.run([str(ROOT / "tools/w64devkit/bin/gcc.exe"),
                            "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src"),
                            str(src), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_notice_is_explicit_and_fail_closed_once_per_process(self):
        text = source()
        declaration = re.search(r"BOOL startup_notice_accepted = FALSE;", text)
        self.assertIsNotNone(declaration, "Startup needs its own process-only notice state, not signer/VS trust")
        gate = block_after(text, "if (!startup_notice_accepted)")
        code = r'''
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "nawam_policy.h"
#define MB_IS_RTL 0
static WORD selected_langid = MAKELANGID(LANG_ENGLISH, SUBLANG_DEFAULT);
static int calls, response, bad;
static int MessageBoxExU(HWND owner, const char* text, const char* title, UINT flags, WORD lang) {
    (void)owner;
    calls++;
    int indonesian = PRIMARYLANGID(selected_langid) == LANG_INDONESIAN;
    if (!strstr(text, "Nawam") || !strstr(text, "SHA-256") ||
        !strstr(text, "checksum") || !strstr(text, "Authenticode")) bad = 1;
    if (indonesian) {
        if (!strstr(text, "tanpa tanda tangan digital") || !strstr(text, "kode sumber") ||
            !strstr(text, "Lanjutkan?") || strcmp(title, "Nawam - Build kustom tanpa tanda tangan") != 0) bad = 2;
    } else if (!strstr(text, "unsigned/custom build") || !strstr(text, "source") ||
               !strstr(text, "Continue?") || strcmp(title, "Nawam - Unsigned/custom build") != 0) bad = 2;
    if (lang != selected_langid) bad = 4;
    if ((flags & MB_TYPEMASK) != MB_YESNO || (flags & MB_DEFMASK) != MB_DEFBUTTON2 ||
        !(flags & MB_ICONWARNING) || !(flags & MB_SYSTEMMODAL)) bad = 3;
    return response;
}
static int process_startup(void) {
''' + declaration[0] + r'''
    for (int relaunch = 0; relaunch < 3; relaunch++) {
''' + gate + r'''
    }
    return 1;
out:
    return 0;
}
int main(void) {
    const int answers[] = {IDYES, IDNO, IDCANCEL, 0};
    const WORD languages[] = {0x0409, 0x0421, 0x0c21, 0x040c};
    for (unsigned l = 0; l < sizeof(languages)/sizeof(languages[0]); l++) {
        selected_langid = languages[l];
        for (unsigned i = 0; i < sizeof(answers)/sizeof(answers[0]); i++) {
            calls = bad = 0;
            response = answers[i];
            int continued = process_startup();
            if (continued != (response == IDYES) || calls != 1 || bad) {
                fprintf(stderr, "lang=%u answer=%d continued=%d calls=%d bad=%d\n",
                        selected_langid, response, continued, calls, bad);
                return 1;
            }
        }
    }
    return 0;
}
'''
        self.compile_run(code)

    def test_shared_mutex_error_names_both_applications(self):
        text = source()
        failure = block_after(text, "if ((mutex == NULL) || (GetLastError() == ERROR_ALREADY_EXISTS))")
        call = re.search(r"MessageBoxExU\(.*?;", failure, re.S)[0]
        code = r'''
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "nawam_policy.h"
#define MB_IS_RTL 0
#define MSG_001 1
#define MSG_002 2
#define lmprintf(id) ((id) == MSG_001 ? "Nawam" : "Another Nawam instance is running.")
static WORD selected_langid;
static int bad, calls;
static int MessageBoxExU(HWND owner, const char* text, const char* title, UINT flags, WORD lang) {
    (void)owner; (void)title;
    calls++;
    if (!strstr(text, "Nawam") || !strstr(text, "Rufus")) bad = 1;
    if (PRIMARYLANGID(lang) == LANG_INDONESIAN) {
        if (!strstr(text, "Tutup") || !strstr(text, "kunci")) bad = 2;
    } else if (!strstr(text, "Close") || !strstr(text, "lock")) bad = 3;
    if (!(flags & MB_ICONERROR) || !(flags & MB_SYSTEMMODAL)) bad = 4;
    return IDOK;
}
int main(void) {
    const WORD languages[] = {0x0409, 0x0421, 0x040c};
    for (unsigned l = 0; l < sizeof(languages)/sizeof(languages[0]); l++) {
        selected_langid = languages[l];
''' + call + r'''
        if (bad) { fprintf(stderr, "mutex notice failed: %d\n", bad); return 1; }
    }
    return calls != 3;
}
'''
        self.compile_run(code)

    def test_startup_cannot_infer_trust_or_suppress_notice(self):
        text = source()
        startup = text[text.index("int WINAPI WinMain("):]
        for forbidden in ("vs_reg", "cert_name", "GetSignatureName", "github_thumbprint",
                          "lmprintf(MSG_296)", "lmprintf(MSG_295)"):
            self.assertNotIn(forbidden, startup)
        self.assertNotRegex(startup, r"\bvc\b")
        self.assertEqual(startup.count("startup_notice_accepted"), 3)
        self.assertLess(startup.index("BOOL startup_notice_accepted = FALSE;"), startup.index("relaunch:"))
        self.assertLess(startup.index("selected_langid = get_language_id"),
                        startup.index("if (!startup_notice_accepted)"))
        self.assertLess(startup.index("if (!startup_notice_accepted)"), startup.index("hDlg = MyCreateDialog"))

    def test_dependency_trust_and_shared_lock_are_unchanged(self):
        upstream = ROOT.with_name("rufus-master")
        self.assertEqual((ROOT / "src/pki.c").read_bytes(), (upstream / "src/pki.c").read_bytes())
        before = (upstream / "src/rufus.c").read_text(encoding="utf-8")
        # Nawam already preserves the upstream macro-expanded mutex name literally.
        before = before.replace('"Global/" APPLICATION_NAME', '"Global/Rufus"')
        start = '// Prevent 2 applications from running at the same time'
        stop = 'if ((mutex == NULL) || (GetLastError() == ERROR_ALREADY_EXISTS))'
        self.assertEqual(source().split(start, 1)[1].split(stop, 1)[0],
                         before.split(start, 1)[1].split(stop, 1)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
