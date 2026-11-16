"""Change prose formatting only; preserve policy words, tables, and code."""
from __future__ import annotations
import re


def _sentences(line: str) -> list[str]:
    protected=[m.span() for m in re.finditer(r'(`+).*?\1|\[[^\]]*\]\([^)]*\)',line)]
    boundaries=[m.span() for m in re.finditer(r'(?<=[.!?。]) +',line)
                if not any(start<=m.start()<end for start,end in protected)]
    result=[];start=0
    for a,b in boundaries:
        result.append(line[start:a]);start=b
    result.append(line[start:])
    return [part for part in result if part.strip()]


def bullet_prose(markdown: str) -> str:
    """Use one sentence per bullet outside structural Markdown blocks."""
    out=[];fence=None
    for line in markdown.splitlines():
        match=re.match(r'^\s*(`{3,}|~{3,})',line)
        if match:
            marker=match[1]
            if fence is None:fence=(marker[0],len(marker))
            elif marker[0]==fence[0] and len(marker)>=fence[1]:fence=None
            out.append(line);continue
        stripped=line.lstrip()
        structural=(not stripped or stripped.startswith(('#','|','>'))
            or re.match(r'^(?:[-*+]\s|\d+[.)]\s|[-*_]{3,}\s*$)',stripped)
            or line.startswith(('    ','\t')))
        if fence or structural:
            out.append(line)
        else:
            out.extend('- '+sentence.strip() for sentence in _sentences(line))
    return '\n'.join(out)+ ('\n' if markdown.endswith('\n') else '')
