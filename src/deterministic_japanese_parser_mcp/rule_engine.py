import regex
from .models import Intent, ItemStatus
from .normalizer import span_to_original

class RuleEngine:
    def __init__(self,doc:dict):
        self.timeout=max(0.001,doc.get("timeout_ms",25)/1000)
        self.compiled=[]
        for intent,items in doc.get("intents",{}).items():
            for item in items:
                if not item.get("enabled",True): continue
                self.compiled.append((intent,item,regex.compile(item["pattern"])))
    def extract(self,text,mapping,original)->tuple[list[Intent],list[dict]]:
        found=[]; timeouts=[]
        for intent,item,pattern in self.compiled:
            try:
                for m in pattern.finditer(text,timeout=self.timeout):
                    captures={k:v for k,v in m.groupdict().items() if v is not None}
                    value=next(iter(captures.values()),m.group(0))
                    found.append(Intent(type=intent,value=value.strip(),captures={k:v.strip() for k,v in captures.items()},rule_id=item["id"],priority=item.get("priority",0),span=span_to_original(m.start(),m.end(),mapping,original),status=ItemStatus.RESOLVED))
            except TimeoutError: timeouts.append({"rule_id":item["id"],"status":"TIMEOUT"})
        unique={}
        for x in sorted(found,key=lambda z:(z.span.start,-z.priority,z.rule_id or "")): unique.setdefault((x.type,x.span.start,x.span.end,x.value),x)
        return list(unique.values()),timeouts
