import re, unicodedata
from .models import OriginalSpan

_PROTECTED = re.compile(r"```[\s\S]*?```|`[^`]*`|https?://[^\s]+")

def normalize_with_map(text: str) -> tuple[str, list[tuple[int,int]]]:
    protected=[]
    for m in _PROTECTED.finditer(text): protected.append((m.start(),m.end()))
    def is_protected(i:int)->bool: return any(a<=i<b for a,b in protected)
    out=[]; mapping=[]
    i=0
    while i < len(text):
        if is_protected(i): out.append(text[i]); mapping.append((i,i+1)); i+=1; continue
        n=unicodedata.normalize("NFKC", text[i])
        if not n: i+=1; continue
        for ch in n: out.append(ch); mapping.append((i,i+1))
        i+=1
    return "".join(out), mapping

def span_to_original(start:int,end:int,mapping:list[tuple[int,int]],original:str)->OriginalSpan:
    if not mapping or start>=len(mapping): return OriginalSpan(start=0,end=0,source_text="")
    end=max(start+1,min(end,len(mapping)))
    ostart=mapping[start][0]; oend=max(x[1] for x in mapping[start:end])
    return OriginalSpan(start=ostart,end=oend,source_text=original[ostart:oend])
