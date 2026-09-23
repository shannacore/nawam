# Build Nawam

## Windows x64

Required: Python 3.11+, w64devkit 2.10.0 x64, pefile 2024.8.26.

1. Extract the compiler into tools/w64devkit.
2. Install the Python package locally:

       python -m pip install --target tools/python pefile==2024.8.26

3. Build from the project root:

       python scripts/build.py
       python scripts/verify_about_build.py

4. For the compact executable, extract official UPX 5.2.1 win64 into
   tools/upx/upx-5.2.1-win64, then run:

       python scripts/pack_compact.py

Outputs:
- dist/Nawam.exe: uncompressed build.
- dist/compact/Nawam.exe: compact distribution build.

Close Nawam before rebuilding. The build verifies resource versions, x64 GUI,
DEP/ASLR and DLL search hardening, then records matching source hashes.
The packer tests UPX integrity and compares decompressed code, resources and imports.

## Visual Studio

Open Nawam.sln. Main project: .vs/Nawam.vcxproj. Toolset: v145 with Windows SDK.
The Win32 and ARM64 configurations are retained but are not verified release targets.
The bundled command-line helper is rebuilt by the command-line build script.

## Tests

    python -m unittest discover -s tests -v
    python -O -m unittest discover -s tests -p test_release_pipeline.py -v

No automated test may format or write a physical USB drive. Native UI tests may
require manually approved administrator permission. Resource/logic tests do not
replace manual boot and physical-media compatibility testing.

Toolchain archives: https://github.com/skeeto/w64devkit/releases/tag/v2.10.0
UPX: https://github.com/upx/upx/releases/tag/v5.2.1
Preserved internal source filenames and identifiers are implementation details;
do not rename low-level contracts or dependency trust anchors cosmetically.
