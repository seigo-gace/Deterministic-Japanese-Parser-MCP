import regex
from .models import Metaphor
from .normalizer import span_to_original

class MetaphorMatcher:
    def __init__(self,doc:dict): self.entries=doc.get("entries",[])
    def find(self,text,mapping,original)->list[Metaphor]:
        out=[]
        for item in self.entries:
            matches=[]
            for expression in [item["expression"],*item.get("aliases",[])]:
                start=0
                while True:
                    pos=text.find(expression,start)
                    if pos<0: break
                    matches.append((pos,pos+len(expression)));start=pos+len(expression)
            for pattern in item.get("patterns",[]):
                for match in regex.finditer(pattern,text,timeout=0.025): matches.append((match.start(),match.end()))
            for a,b in matches:
                contexts=[c for c in item.get("context",[]) if c in text]
                out.append(Metaphor(expression=item["expression"],interpretation=item["interpretation"],domain=item.get("domain","general"),context_matches=contexts,span=span_to_original(a,b,mapping,original)))
        unique={}
        for entry in sorted(out,key=lambda z:(z.span.start,-len(z.span.source_text),z.expression)): unique.setdefault((entry.span.start,entry.span.end,entry.expression),entry)
        return list(unique.values())
