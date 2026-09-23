"""Export upstream notices from the actual source without interpreting code."""
from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[2]
text = (ROOT / 'src/license.h').read_text(encoding='utf-8')
part = text.split('const char* additional_copyrights =', 1)[1].split(';', 1)[0]
chunks = re.findall(r'"(?:[^"\\]|\\.)*"', part)
raw = ''.join(ast.literal_eval(chunk) for chunk in chunks)
plain = raw.replace(r'\line', '\n').replace(r'{\rtf1\ansi', '').replace('}', '')
assert len(chunks) > 100 and 'Axialis' in plain and 'ms-sys' in plain
header = ('Nawam is based on the open-source Rufus project.\n'
          'Copyright 2011-2026 Pete Batard and contributors.\n'
          'Nawam modifications: Copyright 2026 SHANNA Digital Systems.\n'
          'GPL-3.0-or-later. Complete component licenses remain in source.\n\n')
path = ROOT / 'website/public/licenses/THIRD-PARTY-NOTICES.txt'
path.write_text(header + plain, encoding='utf-8')
print('Exported', len(chunks), 'source strings to', path)
