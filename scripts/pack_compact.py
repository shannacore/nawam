"""Pack the current verified Nawam build, not unbuilt working-tree changes.
Requires official UPX 5.2.1 and pefile. Runs no disk-utility application code.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python'))
import pefile
UPX = ROOT / 'tools/upx/upx-5.2.1-win64/upx.exe'
SOURCE = ROOT / 'dist/Nawam.exe'
OUTPUT = ROOT / 'dist/compact/Nawam.exe'
from release_support import verify_provenance


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def resources(pe):
    result = {}
    def walk(entries, prefix=()):
        for entry in entries:
            key = prefix + (str(entry.name) if entry.name else entry.id,)
            if hasattr(entry, 'directory'):
                walk(entry.directory.entries, key)
            else:
                leaf = entry.data.struct
                result[key] = digest(pe.get_data(leaf.OffsetToData, leaf.Size))
    walk(pe.DIRECTORY_ENTRY_RESOURCE.entries)
    return result


def imports(pe):
    return {(entry.dll.lower(), symbol.name or symbol.ordinal, symbol.address)
            for entry in pe.DIRECTORY_ENTRY_IMPORT for symbol in entry.imports}


def metadata(pe):
    return {k.decode(): v.decode() for group in pe.FileInfo for item in group
            if hasattr(item, 'StringTable') for table in item.StringTable
            for k, v in table.entries.items()}


def validate_flags(pe):
    require(pe.FILE_HEADER.Machine == 0x8664, 'Architecture changed')
    require(pe.OPTIONAL_HEADER.Subsystem == 2, 'GUI subsystem changed')
    require(pe.OPTIONAL_HEADER.DllCharacteristics & 0x160 == 0x160, 'DEP/ASLR changed')
    require(pe.DIRECTORY_ENTRY_LOAD_CONFIG.struct.DependentLoadFlags == 0x800,
            'System32 DLL search policy changed')


original = SOURCE.read_bytes()
provenance = verify_provenance(ROOT, original)
EXPECTED = provenance['sha256']
require(UPX.is_file(), 'Extract official UPX 5.2.1 to tools/upx first')
OUTPUT.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(dir=OUTPUT.parent) as directory:
    packed = Path(directory) / 'Nawam.exe'
    packed.write_bytes(original)
    subprocess.run([str(UPX), '--lzma', '--best', '--strip-relocs=0', str(packed)], check=True)
    subprocess.run([str(UPX), '-t', str(packed)], check=True)
    unpacked = Path(directory) / 'unpacked.exe'
    subprocess.run([str(UPX), '-d', '-o', str(unpacked), str(packed)], check=True)
    with pefile.PE(data=original) as before, pefile.PE(str(unpacked)) as after, pefile.PE(str(packed)) as compact:
        for pe in (before, after, compact):
            validate_flags(pe)
        require(metadata(before) == metadata(after) == metadata(compact), 'Metadata changed')
        require(resources(before) == resources(after), 'Resource content changed')
        require(imports(before) == imports(after), 'Import symbols or IAT addresses changed')
        require(before.OPTIONAL_HEADER.AddressOfEntryPoint == after.OPTIONAL_HEADER.AddressOfEntryPoint,
                'Restored entrypoint changed')
        require([s.Name for s in before.sections] == [s.Name for s in after.sections], 'Restored section list changed')
        checked = []
        for old, new in zip(before.sections, after.sections):
            if old.Name.rstrip(b'\0') not in (b'.idata', b'.rsrc'):
                require(old.get_data() == new.get_data(), 'Section content changed: ' + str(old.Name))
                checked.append(old.Name.rstrip(b'\0').decode())
        report = dict(version=provenance['version'], packer='UPX 5.2.1', originalSha256=EXPECTED,
                      compressedSha256=digest(packed.read_bytes()), originalBytes=len(original),
                      compressedBytes=packed.stat().st_size, checkedSections=checked,
                      resourceCount=len(resources(before)), importCount=len(imports(before)),
                      resourceContentsIdentical=True, importsIdentical=True,
                      peHardeningPreserved=True, runtime='Not yet verified for compact variant',
                      note='UPX rebuilds import/resource layout and PE checksum; decompressed file need not be byte-identical.')
    OUTPUT.write_bytes(packed.read_bytes())
(ROOT / 'docs/compact-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
(OUTPUT.parent / 'SHA256SUMS.txt').write_text(report['compressedSha256'] + '  Nawam.exe\n', encoding='ascii')
print(json.dumps(report, indent=2))
