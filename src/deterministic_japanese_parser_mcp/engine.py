from time import perf_counter
from .config import SETTINGS, Settings
from .models import *
from .normalizer import normalize_with_map
from .dictionaries import DictionaryBundle
from .tokenizer import JapaneseTokenizer
from .rule_engine import RuleEngine
from .metaphor import MetaphorMatcher
from .anaphora import AnaphoraResolver
from .contradictions import detect
from .tasks import TaskDecomposer
from .logger import append_log
from .version import VERSION

class ParserEngine:
    def __init__(self,settings:Settings=SETTINGS):
        self.settings=settings
        self.bundle=DictionaryBundle(settings.system_dict_dir,settings.user_dict_dir)
        self.tokenizer=JapaneseTokenizer()
        self.rules=RuleEngine(self.bundle.rules)
        self.metaphors=MetaphorMatcher(self.bundle.metaphors)
        self.anaphora=AnaphoraResolver()
        self.tasks=TaskDecomposer(self.bundle.templates)
    def analyze(self,request:AnalyzeRequest)->AnalyzeResponse:
        start=perf_counter()
        if len(request.original_text)>self.settings.max_input_length: raise ValueError("input exceeds max_input_length")
        context=request.conversation_context[-self.settings.max_context_items:]
        normalized,mapping=normalize_with_map(request.original_text)
        intents,timeouts=self.rules.extract(normalized,mapping,request.original_text)
        metaphors=self.metaphors.find(normalized,mapping,request.original_text)
        references=self.anaphora.resolve(normalized,mapping,request.original_text,context,request.known_entities)
        contradictions=detect(intents)
        deep=bool(metaphors or references or contradictions or timeouts) or request.analysis_depth==AnalysisDepth.DEEP
        tasks=self.tasks.build(intents)
        unresolved=[r for r in references if r.status!=ItemStatus.RESOLVED]
        unsupported=[] if intents or metaphors else [{"text":request.original_text,"status":"UNSUPPORTED"}]
        overall=OverallStatus.COMPLETE
        if contradictions or unresolved or unsupported or timeouts: overall=OverallStatus.PARTIAL
        if not intents and not metaphors and not references: overall=OverallStatus.FAILED
        blocked=[]
        if request.execution_mode==ExecutionMode.EXTERNAL_ACTION:
            if contradictions: blocked.append("CONTRADICTORY")
            if unresolved: blocked.append("AMBIGUOUS_OR_INSUFFICIENT_REFERENCE")
            if unsupported: blocked.append("UNSUPPORTED")
            if timeouts: blocked.append("TIMEOUT")
        elapsed=(perf_counter()-start)*1000
        response=AnalyzeResponse(overall_status=overall,execution_allowed=not blocked,blocked_reasons=blocked,original_text=request.original_text,normalized_text=normalized,analysis_path="DEEP" if deep else "FAST",tokens=self.tokenizer.tokenize(normalized,mapping,request.original_text),intents=intents,metaphors=metaphors,references=references,tasks=tasks,ambiguities=[r.model_dump() for r in unresolved if r.status==ItemStatus.AMBIGUOUS],missing_information=[r.model_dump() for r in unresolved if r.status==ItemStatus.INSUFFICIENT],contradictions=contradictions,unsupported_elements=unsupported,versions=VERSION,metrics={"elapsed_ms":round(elapsed,3),"intent_count":len(intents),"task_count":len(tasks),"tokenizer_backend":self.tokenizer.backend})
        if overall!=OverallStatus.COMPLETE: append_log(self.settings.log_path,{"original_text":request.original_text,"overall_status":overall.value,"ambiguities":response.ambiguities,"unsupported_elements":unsupported,"contradictions":contradictions})
        return response
