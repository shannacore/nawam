"""Build Nawam x64 using the audited upstream MinGW build graph."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--clean", action="store_true", help="Remove generated object/library files first")
parser.add_argument("--jobs", type=int, default=4)
args = parser.parse_args()
if not 1 <= args.jobs <= 32:
    parser.error("--jobs must be between 1 and 32")
bin_dir = ROOT / "tools/w64devkit/bin"
if not (bin_dir / "gcc.exe").exists():
    raise SystemExit("Extract verified w64devkit x64 2.10.0 into tools/w64devkit first (see README.md).")
sys.path.insert(0, str(ROOT / "tools/python"))
try:
    import pefile
except ImportError:
    raise SystemExit("Install pefile locally: uv pip install --target tools/python pefile==2024.8.26")
env = os.environ.copy()
# Keep MSYS and Windows PATH parsing separate. All build subprocesses use
# native BusyBox sh, with the environment documented by w64devkit/etc/profile.
env.update(PATH=bin_dir.as_posix() + ";" + os.environ["SystemRoot"] + "/System32",
           SHELL="sh", CONFIG_SHELL="sh", PATH_SEPARATOR=";",
           ac_executable_extensions=".exe", build_alias="x86_64-w64-mingw32",
           PYTHONPATH=str(ROOT / "tools/python"))
(ROOT / "docs").mkdir(exist_ok=True)
(ROOT / "dist").mkdir(exist_ok=True)
log_path = ROOT / "docs/build-x64.log"
with log_path.open("w", encoding="utf-8") as log:
    def run(command):
        log.write("COMMAND: " + subprocess.list2cmdline([str(x) for x in command]) + "\n")
        log.flush()
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f"Build failed ({result.returncode}); see {log_path}")

    if args.clean:
        upstream = json.loads((ROOT / "docs/upstream-sha256.json").read_text())
        for directory in (ROOT / "src", ROOT / ".mingw"):
            for file in directory.rglob("*"):
                if (file.is_file() and file.suffix in (".o", ".a", ".lib")
                        and file.relative_to(ROOT).as_posix() not in upstream):
                    file.unlink()
    # Upstream disables dependency tracking. Invalidate main objects so every
    # branding/policy/header change is guaranteed to enter the next executable.
    for file in (ROOT / "src").glob("rufus-*.o"):
        file.unlink()
    (ROOT / "src/rufus_rc.o").unlink(missing_ok=True)
    run([str(bin_dir / "gcc.exe"), "-m32", "-Os", "-s",
         "-Wl,--nxcompat,--dynamicbase,--no-insert-timestamp",
         "res/hogger/hogger.c", "-o", "res/hogger/nawam-hogger.exe"])
    run([str(bin_dir / "sh.exe"), "./configure", "--disable-debug", "SED=sed", "RM=rm"])
    run([str(bin_dir / "make.exe"), f"-j{args.jobs}", "MAKE=make", "SHELL=sh",
         "SED=sed", "RM=rm", "MKDIR_P=mkdir -p", "CFLAGS=-Os -fno-toplevel-reorder"])
    output = ROOT / "dist/Nawam.exe"
    staged = ROOT / "dist/Nawam.build.exe"
    shutil.copy2(ROOT / "src/rufus.exe", staged)
    # Preserve upstream DLL search hardening. Never rename its private marker.
    run([sys.executable, "res/scripts/loadcfg.py", str(staged)])
    pe = pefile.PE(str(staged))
    assert pe.FILE_HEADER.Machine == 0x8664, "Expected x64 PE"
    assert pe.OPTIONAL_HEADER.Subsystem == 2, "Expected Windows GUI application"
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x140 == 0x140, "DEP/ASLR missing"
    assert pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct.DependentLoadFlags == 0x800
    info = {k.decode(): v.decode() for group in pe.FileInfo for item in group
            if hasattr(item, "StringTable") for table in item.StringTable for k, v in table.entries.items()}
    assert info["ProductName"] == "Nawam" and info["FileVersion"] == "1.0.0"
    assert info["OriginalFilename"] == "Nawam.exe"
    pe.close()
    os.replace(staged, output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (ROOT / "dist/SHA256SUMS.txt").write_text(digest + "  Nawam.exe\n", encoding="ascii")
    (ROOT / "docs/executable-metadata.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
print("Built and verified:", output)
print("SHA256:", digest)
print("Log:", log_path)
