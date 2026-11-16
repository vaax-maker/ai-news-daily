"""Source-bound knowledge gate: unanswered questions and reactions are excluded.

This deterministic check establishes literal source presence and basic information
shape. Semantic fact validation still belongs to the pipeline's evaluator.
"""
import copy
import re

KINDS={'answer','method','feature','constraint','observed_result','new_information'}
QUESTION=re.compile(r'\?|질문|궁금|물었|묻는|알고 싶|무엇인지|어떻게.*인지',re.I)
ANSWER=re.compile(r'답변|안내|설명|해결|방법[을이]|대신|설정.*가능')
REACTION=re.compile(r'걱정|우려|기대|고민|재미있|재미있다는|전환점|반응도|반응이')
ACTION=re.compile(r'답변|안내|설명|방법|설정해|설치하고|연결된|전사|단축키|호환성|근거 페이지|복원|접근할 수 없|접근하지 못|작동하지|업데이트|느렸|느리고|변경 기능이 없|변경.*없어|입력란|나눠 생성|이어 붙|기존 프로그램을 분석')
INFORMATION=re.compile(r'가능|지원|방법|인수인계|프로그램|디컴파일|모델|포인트|설정|설치|업데이트|접근|보관|기간|전사|단축키|연결|제한|한도|느[리렸]|속도|오류|작동|호환|메모리|함수|시그니처|근거|페이지|분석|생성|이어|넘기|변경|없[다어습]|못[하합]|안 됩|안됩|limitation|cannot|can.t|supports?|offline|shortcut|install|configur|error|memory|rebuild|reconstruct|compatib',re.I)
AFFIRMATIVE=re.compile(r'입니다|합니다|습니다|겁니다|됩니다|있습니다|없습니다|못합니다|했습니다|결정함|사라지지|쪼개|이어붙|만들어 준|제공|끝|=|[가-힣]+다고|가능|지원|설정|설치|느렸|느리고|순삭|\b(?:is|are|was|were|can|cannot|has|have|supports?|limitation|installed|built|tested|using)\b',re.I)


def normalize(value):
    return re.sub(r'\s+',' ',str(value or '')).strip()


def private_chat_exception(item):
    """Private chat summaries have no public source link or literal-link requirement."""
    names=item.get('sources') or []
    return not item.get('refs') and bool(names) and all(
        isinstance(name,str) and name.strip().startswith(('오픈채팅 · ', '단톡방 · '))
        for name in names)


def source_scope(item,corpus):
    """Web references bind to exactly their lines; chats bind to their room."""
    refs=item.get('refs') or []
    if refs:
        lines=[]
        for ref in refs:
            if not isinstance(ref,str):continue
            match=re.search(r'^\['+re.escape(ref)+r'\]\s*(.*)$',corpus,re.M)
            if match:lines.append(match.group(1))
        return '\n'.join(lines)
    names=[str(name).removeprefix('오픈채팅 · ').strip() for name in item.get('sources',[])]
    blocks=re.split(r'^===== \[(.*?)\] =====\s*$',corpus,flags=re.M)
    selected=[]
    for i in range(1,len(blocks),2):
        label=re.sub(r'\s*\(비공개 대화\)$','',blocks[i]).removeprefix('오픈채팅 · ').strip()
        if label in names:selected.append(blocks[i+1])
    return '\n'.join(selected)


def informative_excerpt(text):
    text=normalize(text)
    if not 15<=len(text)<=600 or not INFORMATION.search(text) or not AFFIRMATIVE.search(text):return False
    # An unresolved request does not become an answer because it names features.
    if (QUESTION.search(text) or text.endswith('?') or re.search(r'물어|궁금|해 줄 수|해줄 수|어떻게.*나요|뭐[예에]요|어떤.*좋[을아]|\b(?:which|how|what|does|anyone)\b.*\?',text,re.I)):
        return False
    return True


def classify_item(item,corpus,require_explicit=False):
    content=normalize(item.get('content'))
    if QUESTION.search(content) and not ANSWER.search(content):return {'keep':False,'reason':'unanswered_question'}
    if private_chat_exception(item):
        evidence=item.get('_knowledge') or {}
        kind=evidence.get('kind') if isinstance(evidence,dict) else None
        # Do not infer source failure from unavailable private chat references.
        # Information still needs to describe an answer, method or concrete experience.
        if not content:return {'keep':False,'reason':'empty_information'}
        if re.search(r'요청했|요청합|원합니다|바랍니다|있으면 좋',content) and not ANSWER.search(content):
            return {'keep':False,'reason':'request_without_answer'}
        if kind not in KINDS:
            return {'keep':False,'reason':'invalid_knowledge_kind'}
        if kind=='observed_result' and not re.search(r'\d|사용|써본|써보|실행|튕|꺼지|사라|응답|나타|로그|결과|작동|설정|연결',content):
            return {'keep':False,'reason':'reaction_without_transferable_information'}
        if REACTION.search(content) and not ACTION.search(content) and kind not in {'observed_result','constraint'}:
            return {'keep':False,'reason':'reaction_without_transferable_information'}
        return {'keep':True,'reason':'private_chat_source_exception','kind':kind,
                'evidence_mode':'private_chat_exception'}
    if REACTION.search(content) and not ACTION.search(content):return {'keep':False,'reason':'reaction_without_transferable_information'}
    scope=source_scope(item,corpus)
    if not scope:return {'keep':False,'reason':'missing_source_scope'}
    evidence=item.get('_knowledge')
    if isinstance(evidence,dict):
        excerpt=normalize(evidence.get('source_excerpt'))
        if evidence.get('kind') not in KINDS:return {'keep':False,'reason':'invalid_knowledge_kind'}
        if not excerpt or excerpt not in normalize(scope):return {'keep':False,'reason':'knowledge_excerpt_not_in_item_source'}
        if not informative_excerpt(excerpt):return {'keep':False,'reason':'source_excerpt_has_no_answer_or_information'}
        return {'keep':True,'reason':'literal_information_evidence','kind':evidence['kind'],'source_excerpt':excerpt}
    if require_explicit:return {'keep':False,'reason':'missing_explicit_knowledge_evidence'}
    # Legacy checkpoints predate _knowledge. Conservative source-bound recovery
    # requires a factual excerpt, never an invented answer added to the summary.
    candidates=[]
    tokens=set(re.findall(r'[A-Za-z][A-Za-z0-9_-]{2,}|[가-힣]{2,}',content+' '+str(item.get('issue',''))))
    tokens={re.sub(r'(?:했다|하며|하고|하는|처럼|에게|으로|에서|은|는|이|가|을|를)$','',token) for token in tokens}
    tokens={token[:3] if re.fullmatch(r'[가-힣]{4,}',token) else token for token in tokens
            if token not in {'이용자','사용자','질문','답변','안내','설명','경험','방식','공유','있다','없다','했다','나왔다','소개','있고','한다','있어'}}
    for line in scope.splitlines():
        for excerpt in re.split(r'(?<=[.!?])\s+',line):
            if not informative_excerpt(excerpt):continue
            overlap=sum(token.lower() in excerpt.lower() for token in tokens)
            if item.get('refs') or overlap>=2:candidates.append((overlap,excerpt))
    if not candidates:return {'keep':False,'reason':'no_source_information_evidence'}
    excerpt=max(candidates,key=lambda pair:pair[0])[1]
    return {'keep':True,'reason':'legacy_source_information_evidence','source_excerpt':normalize(excerpt)}


def filter_report(gen,corpus,require_explicit=False):
    result=copy.deepcopy(gen);kept=[];decisions=[];seen_excerpts=set()
    for index,item in enumerate(gen.get('items',[])):
        decision=classify_item(item,corpus,require_explicit=require_explicit)
        excerpt=normalize(decision.get('source_excerpt'))
        if decision['keep'] and excerpt and excerpt in seen_excerpts:
            decision={**decision,'keep':False,'reason':'duplicate_literal_information_evidence'}
        if decision['keep'] and excerpt:seen_excerpts.add(excerpt)
        decisions.append({'index':index,'publication_index':item.get('publication_index',index),'issue':item.get('issue',''),**decision})
        if decision['keep']:
            kept_item=copy.deepcopy(item)
            kept_item.setdefault('publication_index',index)
            kept.append(kept_item)
    result['items']=kept
    previous=gen.get('_knowledge_gate')
    if previous and previous.get('original_count')!=previous.get('kept_count'):
        result.setdefault('_knowledge_gate_history',[]).append(copy.deepcopy(previous))
    result['_knowledge_gate']={'version':1,'original_count':len(gen.get('items',[])),'kept_count':len(kept),'decisions':decisions}
    return result
