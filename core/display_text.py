# -*- coding: utf-8 -*-
"""Desktop-only text presentation helpers.

The menu database remains unchanged for website synchronization.  These
helpers only remove the restaurant brand from text shown by the POS desktop.
"""

import re


_ARABIC_BRAND = re.compile(r"(?<![\w])بروست(?![\w])")
_ENGLISH_BRAND = re.compile(r"\bBROOST\b", re.IGNORECASE)


def pos_text(value) -> str:
    if value is None:
        return ""
    lines = []
    for raw_line in str(value).splitlines() or [""]:
        line = _ARABIC_BRAND.sub("", raw_line)
        line = _ENGLISH_BRAND.sub("", line)
        line = re.sub(r"[ \t]+", " ", line)
        line = re.sub(r"\s+([،,:؛])", r"\1", line)
        lines.append(line.strip(" -–—"))
    return "\n".join(lines).strip()
