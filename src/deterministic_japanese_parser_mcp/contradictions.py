from .models import Intent

def _key(x:Intent)->str:
    return (x.captures.get("target") or x.captures.get("action") or x.value).replace(" ","")
def detect(intents:list[Intent])->list[dict]:
    result=[]
    prohibits=[x for x in intents if x.type=="prohibition"]
    actions=[x for x in intents if x.type in {"action","request","modify","remove"}]
    preserves=[x for x in intents if x.type=="preserve"]
    changes=[x for x in intents if x.type in {"modify","remove"}]
    for a in prohibits:
        for b in actions:
            ka,kb=_key(a),_key(b)
            if ka and kb and (ka in kb or kb in ka): result.append({"type":"prohibition_conflict","left":a.model_dump(),"right":b.model_dump()})
    for a in preserves:
        for b in changes:
            ka,kb=_key(a),_key(b)
            if ka and kb and (ka in kb or kb in ka): result.append({"type":"preserve_change_conflict","left":a.model_dump(),"right":b.model_dump()})
    return result
