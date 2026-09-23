"""Elevated, non-destructive UI QA for the exact Nawam executable only.
No START/format command exists in this script. User grants elevation manually.
"""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import time

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("action", choices=["inspect", "close-dialogs", "about", "log", "updates", "select", "close"])
p.add_argument("--iso", type=Path)
a = p.parse_args()
u = C.WinDLL("user32", use_last_error=True)
k = C.WinDLL("kernel32", use_last_error=True)
ENUM = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
u.EnumWindows.argtypes = [ENUM, W.LPARAM]
u.EnumChildWindows.argtypes = [W.HWND, ENUM, W.LPARAM]
u.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
u.GetDlgCtrlID.argtypes = [W.HWND]
u.IsWindowVisible.argtypes = [W.HWND]
u.IsWindowEnabled.argtypes = [W.HWND]
u.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u.SendMessageW.restype = W.LPARAM
u.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
u.SetWindowTextW.argtypes = [W.HWND, W.LPCWSTR]
u.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
k.CloseHandle.argtypes = [W.HANDLE]
EXPECTED = str((ROOT / "dist/Nawam.exe").resolve()).lower()


def executable(pid):
    handle = k.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""
    try:
        buf = C.create_unicode_buffer(32768)
        size = W.DWORD(len(buf))
        return buf.value.lower() if k.QueryFullProcessImageNameW(handle, 0, buf, C.byref(size)) else ""
    finally:
        k.CloseHandle(handle)


def text(handle, child=False):
    buf = C.create_unicode_buffer(65536)
    if child:
        u.SendMessageW(handle, 13, len(buf), C.addressof(buf))
    else:
        u.GetWindowTextW(handle, buf, len(buf))
    return buf.value


def describe(handle):
    cls = C.create_unicode_buffer(256)
    u.GetClassNameW(handle, cls, len(cls))
    item = dict(hwnd=int(handle), id=u.GetDlgCtrlID(handle), cls=cls.value,
                text=text(handle, True), enabled=bool(u.IsWindowEnabled(handle)),
                visible=bool(u.IsWindowVisible(handle)))
    if cls.value == "ComboBox":
        count = u.SendMessageW(handle, 0x146, 0, 0)
        item["items"] = []
        for index in range(max(0, min(count, 128))):
            buf = C.create_unicode_buffer(8192)
            u.SendMessageW(handle, 0x148, index, C.addressof(buf))
            item["items"].append(buf.value)
        item["selected"] = u.SendMessageW(handle, 0x147, 0, 0)
    return item


def windows():
    found = []
    @ENUM
    def cb(handle, unused):
        pid = W.DWORD()
        u.GetWindowThreadProcessId(handle, C.byref(pid))
        if executable(pid.value) == EXPECTED:
            found.append(dict(hwnd=int(handle), pid=pid.value, title=text(handle),
                              visible=bool(u.IsWindowVisible(handle))))
        return True
    u.EnumWindows(cb, 0)
    return found


def children(handle):
    found = []
    @ENUM
    def cb(h, unused):
        found.append(describe(h))
        return True
    u.EnumChildWindows(handle, cb, 0)
    return found


if not C.windll.shell32.IsUserAnAdmin():
    raise SystemExit("QA requires user-approved elevation to inspect the elevated application.")
all_windows = windows()
main = next((w for w in all_windows if w["title"].startswith("Nawam 1.0.1")), None)
if not main:
    raise SystemExit("Exact dist/Nawam.exe main window not found")
handle = main["hwnd"]
if a.action in ("close-dialogs", "close"):
    for window in all_windows:
        if window["hwnd"] != handle and window["visible"]:
            # Close/cancel dialogs only, never activate a default confirmation.
            u.PostMessageW(window["hwnd"], 0x10, 0, 0)
    time.sleep(0.4)
    if a.action == "close":
        u.PostMessageW(handle, 0x10, 0, 0)
elif a.action in ("about", "log", "updates", "select"):
    commands = {"about": 1052, "log": 1054, "updates": 1053, "select": 1014}
    u.PostMessageW(handle, 0x111, commands[a.action], 0)
    time.sleep(0.8)
    if a.action == "select" and a.iso:
        iso = a.iso.resolve()
        if not iso.is_file() or iso.suffix.lower() != ".iso":
            raise SystemExit("An existing ISO is required")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            dialogs = [w for w in windows() if w["visible"] and w["hwnd"] != handle]
            candidates = [(w, c) for w in dialogs for c in children(w["hwnd"])
                          if c["cls"] == "Edit" and c["id"] == 1148]
            if candidates:
                dialog, edit = candidates[0]
                u.SetWindowTextW(edit["hwnd"], str(iso))
                u.PostMessageW(dialog["hwnd"], 0x111, 1, 0)  # File Open, NOT main Start.
                break
            time.sleep(0.2)
        else:
            raise SystemExit("File name field not found; no further input sent")
        time.sleep(3)
report = []
for window in windows():
    window["controls"] = children(window["hwnd"])
    report.append(window)
path = ROOT / "docs" / ("qa-" + a.action + ".json")
path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(path)
