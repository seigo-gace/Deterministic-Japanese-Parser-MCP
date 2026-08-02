from .models import Intent, Task, ItemStatus
class TaskDecomposer:
    def __init__(self,doc:dict): self.by_intent={x.get("intent"):x for x in doc.get("templates",[]) if x.get("intent")!="workflow"}
    def build(self,intents:list[Intent])->list[Task]:
        out=[]; executable={"request","modify","remove","comparison","action","decision","correction"}
        for i,x in enumerate(intents,1):
            if x.type not in executable: continue
            tpl=self.by_intent.get(x.type,{})
            target=x.captures.get("target") or x.captures.get("action") or x.value
            out.append(Task(task_id=f"T-{i:03d}",action=tpl.get("action",x.type),target=target,intent_type=x.type,execution_order=len(out)+1,verification_criteria=tpl.get("verification",[]),external_action=x.type in {"modify","remove","action"},status=ItemStatus.RESOLVED,original_span=x.span))
        return out
