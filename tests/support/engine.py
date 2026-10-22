"""Shared boundary definitions, not a second transfer implementation."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[2]
common = (ROOT / "tests/support/engine.hpp").read_text()


def rename_enum_references(source, previous_header, current_header=None):
    """Compile historical baseline logic with the current fixture's enum spellings."""
    current_header = current_header or (ROOT / 'src/ItemClass.h').read_text()
    for enum in ('Container', 'ItemCategory'):
        def names(header):
            match = re.search(r'enum class ' + enum + r'[^\{]*\{([^}]+)\}', header)
            if not match:
                raise ValueError(f'Missing baseline enum: {enum}')
            return re.findall(r'^\s*(\w+)\s*,?\s*$', match[1], re.M)
        before, after = names(previous_header), names(current_header)
        if not before or len(before) > len(after):
            raise ValueError(f'Baseline enum population changed: {enum}')
        if any(before.index(name) != after.index(name) for name in set(before) & set(after)):
            raise ValueError(f'Baseline enum positions changed: {enum}')
        replacements = dict(zip(before, after))
        source = re.sub(r'\b' + enum + r'::(\w+)', lambda m: enum + '::' + replacements[m[1]], source)
    return source
