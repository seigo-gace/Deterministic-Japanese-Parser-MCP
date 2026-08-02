import re
from .models import ReferenceResolution, ItemStatus
from .normalizer import span_to_original

PATTERN=re.compile(r"これ|それ|あれ|前の案|先ほどの内容|上記|下記|同じもの|この内容|その件")
class AnaphoraResolver:
    def resolve(self,text,mapping,original,context:list[str],known:list[str])->list[ReferenceResolution]:
        out=[]
        pool=[x for x in [*reversed(context),*known] if x]
        for m in PATTERN.finditer(text):
            candidates=pool[:5]
            selected=candidates[0] if len(candidates)==1 else None
            status=ItemStatus.RESOLVED if selected else (ItemStatus.AMBIGUOUS if candidates else ItemStatus.INSUFFICIENT)
            out.append(ReferenceResolution(expression=m.group(0),candidates=candidates,selected=selected,span=span_to_original(m.start(),m.end(),mapping,original),status=status))
        return out
