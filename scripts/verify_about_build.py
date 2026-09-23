"""Verify the staged PE without executing application code or touching drives."""
from pathlib import Path
import ast
import json
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/python"))
import pefile

source = ROOT / "dist/Nawam.build.exe"
if not source.is_file():
    source = ROOT / "dist/Nawam.exe"
from release_support import require, sha256, validate_pe, verify_provenance

data = source.read_bytes()
metadata = validate_pe(ROOT, data)
provenance_path = (ROOT / 'dist/Nawam.build.provenance.json'
                   if source.name == 'Nawam.build.exe' else ROOT / 'docs/build-provenance.json')
verify_provenance(ROOT, data, provenance_path)
pe = pefile.PE(data=data)
header = (ROOT / "src/license.h").read_text(encoding="utf-8")
constants = {}
for name in ("about_blurb_format", "legal_notice_format", "additional_copyrights", "gplv3"):
    body = header.split("const char* " + name + " =", 1)[1]
    strings = re.match(r'\s*((?:"(?:[^"\\]|\\.)*"\s*)+);', body)[1]
    text = "".join(ast.literal_eval(m[0]) for m in re.finditer(r'"(?:[^"\\]|\\.)*"', strings))
    require(text.encode("utf-8") in data, name + " missing or truncated in PE")
    constants[name] = len(text.encode("utf-8"))


def dialog(resource_id):
    entry = next(t for t in pe.DIRECTORY_ENTRY_RESOURCE.entries if t.id == 5)
    item = next(t for t in entry.directory.entries if t.id == resource_id)
    leaf = item.directory.entries[0].data.struct
    raw = pe.get_data(leaf.OffsetToData, leaf.Size)
    offset = 26
    version, signature, _, _, style, count, x, y, width, height = struct.unpack_from("<HHIIIHhhhh", raw)
    require((version, signature) == (1, 65535), 'Expected extended dialog resource')

    def word_string():
        nonlocal offset
        word = struct.unpack_from("<H", raw, offset)[0]
        offset += 2
        if word == 65535:
            ordinal = struct.unpack_from("<H", raw, offset)[0]
            offset += 2
            return ordinal
        result = []
        while word:
            result.append(word)
            word = struct.unpack_from("<H", raw, offset)[0]
            offset += 2
        return "".join(chr(w) for w in result)

    word_string()
    word_string()
    title = word_string()
    if style & 0x40:
        offset += 6
        word_string()
    controls = []
    for _ in range(count):
        offset = (offset + 3) & ~3
        _, exstyle, control_style, cx, cy, cw, ch, identifier = struct.unpack_from("<IIIhhhhI", raw, offset)
        offset += 24
        cls, text = word_string(), word_string()
        extra = struct.unpack_from("<H", raw, offset)[0]
        offset += 2 + extra
        controls.append(dict(id=identifier, cls=cls, text=text, style=control_style,
                             x=cx, y=cy, width=cw, height=ch))
    return dict(title=title, width=width, height=height, controls=controls)


about, legal = dialog(102), dialog(105)
require(about["height"] == 128 and legal["height"] == 382, 'Unexpected About/legal dimensions')
require(1032 not in {c["id"] for c in about["controls"]}, 'Credits must be in legal dialog')
require(next(c for c in about["controls"] if c["id"] == 1030)["text"] == "License && Open Source",
        'Missing legal dialog button')
require(legal["title"] == "Nawam - License & Open Source", 'Unexpected legal title')
require(sum(bool(c["style"] & 0x200000) for c in legal["controls"]) == 3, 'Missing legal scrollbars')
require({1032, 1033}.issubset({c["id"] for c in legal["controls"]}), 'Missing legal controls')
pe.close()
digest = sha256(data)
output = ROOT / f"dist/Nawam-{metadata['FileVersion']}-x64.exe"
verify_provenance(ROOT, data, provenance_path)
if not output.exists() or sha256(output.read_bytes()) != digest:
    output.write_bytes(data)
require(sha256(output.read_bytes()) == digest, 'Versioned executable SHA256 mismatch')
(output.with_suffix(".exe.sha256")).write_text(digest + "  " + output.name + "\n", encoding="ascii")
report = dict(artifact=str(output), sha256=digest, bytes=len(data), metadata=metadata,
              embedded_text_bytes=constants, about=about, legal=legal,
              pe_checks="x64 Windows GUI, DEP, ASLR, DependentLoadFlags=0x800",
              live_ui="Not verified: QA process is not elevated",
              canonical_publish=("Verified: canonical executable matches this artifact"
                  if (ROOT / "dist/Nawam.exe").read_bytes() == data else "Staged artifact differs from canonical executable"))
(ROOT / "docs/about-build-validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
