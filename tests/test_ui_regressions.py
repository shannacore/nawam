"""Desktop UI regressions; no app build, launch, network or disk operations."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiRegressionTests(unittest.TestCase):
    def test_csm_question_mark_click_matches_current_tooltip(self):
        source = (ROOT / 'src/rufus.c').read_text(encoding='utf-8')
        command = source.split('INT_PTR CALLBACK MainCallback', 1)[-1]
        command = command.split('case WM_COMMAND:', 1)[1]
        match = re.search(r'case IDS_CSM_HELP_TXT:(.*?)(?=\n\t\tcase )',
                          command, re.S)
        self.assertIsNotNone(match, 'The question mark needs a WM_COMMAND handler')
        handler = match.group(1)
        self.assertIn('STN_CLICKED', handler)
        self.assertIn('Notification(MB_OK | MB_ICONINFORMATION', handler)
        self.assertIn('(target_type == TT_UEFI) ? MSG_152 : MSG_151', handler)

    def test_update_policy_links_use_existing_link_handler(self):
        source = (ROOT / 'src/stdlg.c').read_text(encoding='utf-8')
        callback = source.split('INT_PTR CALLBACK UpdateCallback', 1)[1]
        notify = callback.split('case WM_NOTIFY:', 1)[1].split('case WM_COMMAND:', 1)[0]
        self.assertIn('EN_LINK', notify, 'The update policy advertises links but ignores clicks')
        self.assertIn('OpenDialogLink(hDlg, lParam)', notify)
        self.assertIn('EN_REQUESTRESIZE', notify, 'Keep the existing resize notification')

    def test_license_layout_fits_monitor_at_100_150_200_percent(self):
        header = ROOT / 'src/nawam_layout.h'
        self.assertTrue(header.exists(), 'License layout needs a monitor-bound calculation')
        code = r'''
#include "nawam_layout.h"
#include <stdio.h>
#define CHECK(test) do { if (!(test)) { \
    fprintf(stderr, "layout check failed at line %d\n", __LINE__); return 1; } } while (0)
int main(void) {
    const int scales[] = {100, 150, 200};
    const NawamLayoutRect monitors[] = {
        {0, 0, 1280, 680}, {0, 40, 1366, 728},
        {-1920, -120, 1920, 1040}, {40, 0, 1040, 1920},
        {1920, 0, 3840, 2080}
    };
    const NawamLayoutRect template[] = {
        {14, 14, 912, 208}, {14, 238, 912, 20},
        {14, 264, 912, 164}, {14, 446, 912, 20},
        {14, 472, 912, 230}, {826, 724, 100, 32}
    };
    unsigned int s, m, i;
    int cases = 0;
    for (s = 0; s < sizeof(scales)/sizeof(scales[0]); s++) {
        for (m = 0; m < sizeof(monitors)/sizeof(monitors[0]); m++) {
            int scale = scales[s], frame_w = 16*scale/100, frame_h = 40*scale/100;
            NawamLayoutRect window = {-2500, -900, 956*scale/100, 804*scale/100};
            NawamLayoutRect controls[6];
            for (i = 0; i < 6; i++) {
                controls[i].x = template[i].x*scale/100;
                controls[i].y = template[i].y*scale/100;
                controls[i].width = template[i].width*scale/100;
                controls[i].height = template[i].height*scale/100;
            }
            CHECK(NawamFitLicenseLayout(&monitors[m], &window, frame_w, frame_h, controls));
            CHECK(window.x >= monitors[m].x && window.y >= monitors[m].y);
            CHECK(window.x + window.width <= monitors[m].x + monitors[m].width);
            CHECK(window.y + window.height <= monitors[m].y + monitors[m].height);
            CHECK(controls[1].height == 20*scale/100); /* Headings remain legible. */
            CHECK(controls[3].height == 20*scale/100);
            CHECK(controls[5].height == 32*scale/100); /* Never shrink Close. */
            CHECK(controls[5].width == 100*scale/100);
            for (i = 0; i < 6; i++) {
                CHECK(controls[i].x >= 0 && controls[i].y >= 0);
                CHECK(controls[i].width > 0 && controls[i].height > 0);
                CHECK(controls[i].x + controls[i].width <= window.width - frame_w);
                CHECK(controls[i].y + controls[i].height <= window.height - frame_h);
                if (i != 5) CHECK(controls[i].y + controls[i].height < controls[i+1].y);
                if (i == 0 || i == 2 || i == 4) CHECK(controls[i].height >= 26*scale/100);
            }
            cases++;
        }
    }
    printf("%d monitor/DPI layouts passed\n", cases);
    return 0;
}'''
        with tempfile.TemporaryDirectory(prefix='nawam-layout-') as directory:
            source = Path(directory) / 'layout.c'
            exe = source.with_suffix('.exe')
            source.write_text(code, encoding='utf-8')
            compiled = subprocess.run([str(ROOT / 'tools/w64devkit/bin/gcc.exe'),
                                       '-std=c99', '-Wall', '-Wextra', '-Werror',
                                       '-I', str(ROOT / 'src'), str(source), '-o', str(exe)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('15 monitor/DPI layouts passed', result.stdout)

    def test_native_fit_helper_compiles_against_win32(self):
        source = (ROOT / 'src/stdlg.c').read_text(encoding='utf-8')
        helper = source.split('static void FitLicenseDialog(HWND hDlg)', 1)[1]
        helper = 'static void FitLicenseDialog(HWND hDlg)' + helper.split(
            'INT_PTR CALLBACK LicenseCallback', 1)[0]
        code = '#include <windows.h>\n#include "resource.h"\n#include "nawam_layout.h"\n'
        code += helper + '\nvoid compile_probe(HWND window) { FitLicenseDialog(window); }\n'
        with tempfile.TemporaryDirectory(prefix='nawam-native-layout-') as directory:
            probe = Path(directory) / 'native-layout.c'
            probe.write_text(code, encoding='utf-8')
            result = subprocess.run([str(ROOT / 'tools/w64devkit/bin/gcc.exe'),
                                     '-std=c99', '-Wall', '-Wextra', '-Werror', '-fsyntax-only',
                                     '-I', str(ROOT / 'src'), str(probe)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_license_fit_uses_native_monitor_and_keeps_keyboard_scrolling(self):
        source = (ROOT / 'src/stdlg.c').read_text(encoding='utf-8')
        self.assertTrue('static void FitLicenseDialog(HWND hDlg)' in source,
                        'The Win32 dialog never fits the monitor work area')
        helper = source.split('static void FitLicenseDialog(HWND hDlg)', 1)[1]
        helper = helper.split('INT_PTR CALLBACK LicenseCallback', 1)[0]
        for required in ('MonitorFromWindow', 'MONITOR_DEFAULTTONEAREST', 'GetMonitorInfo',
                         'rcWork', 'GetWindowRect', 'GetClientRect', 'MapWindowPoints',
                         'NawamFitLicenseLayout', 'SetWindowPos', 'WS_TABSTOP', 'WS_VSCROLL',
                         'WM_NEXTDLGCTL', 'IDCANCEL', 'SWP_NOZORDER', 'SWP_NOACTIVATE'):
            self.assertIn(required, helper)
        callback = source.split('INT_PTR CALLBACK LicenseCallback', 1)[1]
        callback = callback.split('INT_PTR CALLBACK AboutCallback', 1)[0]
        self.assertIn('FitLicenseDialog(hDlg);', callback)
        self.assertLess(callback.index('ResizeButtonHeight'), callback.index('FitLicenseDialog'))
        self.assertIn('case IDCANCEL:', callback)
        self.assertIn('case IDOK:', callback)


if __name__ == '__main__':
    unittest.main(verbosity=2)
