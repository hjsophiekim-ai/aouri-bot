"""사업팀 전달본 — 같은 최종 검토 데이터에서 결론과 실행사항만 뽑는다 (2026-10-30).

실측(천안 상가 임대차·실제 AI): 다운로드 보고서가 거래 판단·보호수단 평가·요청 답변·조항별 상세를 모두 싣고, 같은 손실
경로 문장이 한 쟁점에 5번(핵심 위험·요청 답변·조항 문제점·손실 경로·실무상 이유) 반복됐다. 내부 상태코드와 "AI 자체 판단"
같은 처리 과정 표현, 주차장 사용권에 붙은 저작권법 설명, "…" 로 잘린 수정 문구가 같은 문서에 섞여 사업팀이 해야 할 일을
바로 찾을 수 없었다.

원칙
  1. 입력은 내부 분석본과 같은 최종 데이터다(final_findings·clause_results·deal_assessment·요청 답변 행·전체반영 검사).
     여기서 새 판단을 만들지 않는다 — 문장은 그 데이터의 문장을 고르고 줄이며, 연결 낱말만 붙인다.
  2. 쟁점 하나는 한 번만 — 수정사항·확인사항·결정사항 중 한 곳에 싣고, 요청 답변은 그 항목 번호로 잇는다.
  3. 항목마다 "현재 조건 → 우리에게 생길 문제 → 해야 할 일". 내부 코드·AI 처리 과정·법률 강의는 싣지 않는다.
  4. 수정 문구는 별첨에 자르지 않고 싣는다. 위치와 문안의 조항번호가 어긋나거나, 함께 반영할 때 보류됐거나,
     원문·답변에 없는 금액·기간이 들어 있으면 숨기지 않고 "법무 추가 확인 중" / "미확정" 으로 표시한다.
  5. 사용자 답변을 위험 수용으로 넓혀 읽지 않는다 — 명시적으로 받아들인 위험만 "수용 결정" 이고, 나머지는 사업부 결정사항.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

STATUS_PENDING = "법무 추가 확인 중"

KIND_REVISION = "revision"
KIND_CHECK = "check"
KIND_DECISION = "decision"

_CAT_MUST = "필수수정"
_CAT_PRECHECK = "체결 전 확인"
_CAT_SHOULD = "권장수정"
_CAT_ACCEPT = "수용 가능한 위험"


@dataclass
class CheckRow:
    what: str
    who: str
    when: str


@dataclass
class BriefItem:
    no: str                 # "수정 1" · "확인 2" · "결정 1"
    kind: str
    level: str              # 필수 / 권장 / 중요 / 확인 / 결정
    title: str
    clauses: list[str]
    current: str            # 현재 조건
    problem: str            # 우리에게 생길 문제
    action: str             # 해야 할 일
    checks: list[CheckRow] = field(default_factory=list)
    status: str = ""        # "" | 법무 추가 확인 중
    status_reason: str = ""
    impact: str = ""        # 상태가 체결 판단에 미치는 영향
    undecided: list[str] = field(default_factory=list)
    appendix: str = ""      # 별첨 번호
    sources: list[str] = field(default_factory=list)
    see: str = ""           # 같은 쟁점을 설명한 항목 번호(설명을 되풀이하지 않는다)
    loss: str = ""          # 손실 한 줄(결론용 — 본문 "문제" 문장을 되풀이하지 않는다)


@dataclass
class AppendixEdit:
    no: str
    item_no: str
    location: str
    mode: str               # 문장 교체 / 문장 추가 / 항 신설 / 조항 교체
    current_text: str
    new_text: str           # 바로 붙여 넣을 완성 문구(자르지 않는다)
    added_text: str = ""    # 기존 문장 뒤에 덧붙는 부분(있을 때)
    undecided: list[str] = field(default_factory=list)


@dataclass
class RequestAnswer:
    index: str
    request: str
    answer: str
    items: list[str] = field(default_factory=list)


@dataclass
class BusinessBrief:
    title: str
    verdict: str
    conclusion: list[str]
    requests: list[RequestAnswer]
    revisions: list[BriefItem]
    checks: list[BriefItem]
    general_checks: list[CheckRow]
    decisions: list[BriefItem]
    appendix: list[AppendixEdit]
    pending: list[str]
    keep_count: int = 0
    trace: dict[str, list[str]] = field(default_factory=dict)   # finding id → 항목 번호들(내부 대조용, 출력하지 않는다)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── 문장 다듬기 ──────────────────────────────────────────────────────────────

_RX_INTERNAL = re.compile(
    r"\b(?:REVIEW|STATUS|REVISION|TRIAGE)_[A-Z_]+\b|\b(?:KR|EN|CP|MI|MR|DLR)-[\w-]+|\b(?:clr|eb|deal|fnd|isr|svc|sppc|counsel|sp)_[\w-]+"
    r"|\b(?:HIGH|MEDIUM|LOW)\b|\bfinding\b|\btriage\b"
)
_RX_PROCESS = re.compile(r"AI\s*(?:자체\s*)?(?:판단|분석|검토)|자동\s*(?:검증|분석|판단)|게이트|에이전트|모델이|파이프라인")
_LAW_WORDS = (
    r"상가건물\s*임대차\s*보호법|주택임대차보호법|저작권법|하도급법|대리점법|공정거래법|전자상거래법|표시광고법|개인정보\s*보호법"
    r"|약관규제법|약관의\s*규제에\s*관한\s*법률|부정경쟁방지법|민사집행법|채무자회생법|부가가치세법|소득세법|상법|민법|판례|대법원"
)
_RX_LAW_ASSERT = re.compile(rf"(?:{_LAW_WORDS})")
_RX_CITE_PAREN = re.compile(rf"\s*\((?:[^()]*?(?:{_LAW_WORDS})[^()]*?)\)")

#: 법률용어 — 전달본에 처음 나올 때 한 번만 쉬운 말을 붙인다.
_GLOSSARY: tuple[tuple[str, str], ...] = (
    ("근저당", "부동산을 담보로 잡아 경매 때 정한 최고액까지 먼저 돌려받는 권리"),
    ("질권", "예금 같은 채권을 담보로 잡아 은행에서 직접 돌려받는 권리"),
    ("물상보증", "제3자가 자기 재산을 담보로 내놓는 것"),
    ("연대보증", "임대인 등 주채무자가 못 갚으면 보증인에게 곧바로 청구할 수 있는 보증"),
    ("대위변제", "상대방 빚을 대신 갚고 그만큼을 받을 권리를 갖는 것"),
    ("상계", "서로 줄 돈을 맞비겨 없애는 것"),
    ("전대", "빌린 공간을 다시 남에게 빌려주는 것"),
    ("대항력", "새 소유자 등 제3자에게도 임차권을 주장할 수 있는 힘"),
    ("이용허락", "저작물을 정해진 범위에서 쓸 수 있게 허락받는 것"),
)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", _s(s)).strip()


def _sentences(text: str) -> list[str]:
    t = _flat(text)
    if not t:
        return []
    parts = re.split(r"(?<=[다요음함됨])\.\s+|(?<=[.!?])\s+(?=[가-힣A-Z“\"'(])", t)
    return [p.strip() for p in parts if p.strip()]


def _clean(text: str, *, keep_law: bool = False) -> str:
    """내부 코드·처리 과정·근거 없는 법률 단정 문장을 걷어 낸 문장."""
    out: list[str] = []
    for sent in _sentences(text):
        if _RX_PROCESS.search(sent):
            continue
        if not keep_law and _RX_LAW_ASSERT.search(_RX_CITE_PAREN.sub("", sent)):
            # 조문을 확인하지 못한 "…법상 …이다" 식 단정은 전달본에 싣지 않는다(지시 4항) — 근거는 내부 분석본에 남는다.
            continue
        sent = _RX_CITE_PAREN.sub("", sent)
        sent = _RX_INTERNAL.sub("", sent)
        sent = re.sub(r"\s{2,}", " ", sent).strip(" ,;/")
        if sent:
            out.append(_end(sent))
    return " ".join(out).strip()


def _first(text: str, *, limit: int = 260, keep_law: bool = False) -> str:
    """첫 문장(들). 문장 중간을 "…" 로 자르지 않는다 — 길면 첫 문장만 통째로 둔다."""
    sents = _sentences(_clean(text, keep_law=keep_law))
    if not sents:
        return ""
    out = _end(sents[0])
    for s in sents[1:]:
        if len(out) + len(s) + 1 > limit:
            break
        out += " " + _end(s)
    return out


def _end(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    return s if re.search(r"[.!?」”]$", s) else s + "."


def _split_arrow(loss_path: str) -> tuple[str, str, str]:
    parts = [p.strip() for p in re.split(r"\s+→\s+", _s(loss_path)) if p.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1], " → ".join(parts[2:])
    return ("", "", parts[0]) if parts else ("", "", "")


# ── 실행 주체·시점 ────────────────────────────────────────────────────────────

def _who(text: str) -> str:
    t = _s(text)
    if re.search(r"협상|확인\s*결과", t):
        return "사업부·법무"
    if re.search(r"세무|부가세|부가가치세|세금계산서|원천징수|재경|회계", t):
        return "재경"
    if re.search(r"사업부\s*(?:판단|결정)", t):
        return "사업부"
    if re.search(r"효력|법리|문구|조항|협상|자필\s*서명|기명날인|법무|했는지\s*확인", t) and not re.search(r"증명|대장|서류|확인서|승낙서|등기부", t):
        return "법무"
    return "사업부"


def _when(text: str) -> str:
    t = _s(text)
    if re.search(r"협상|확인\s*결과", t):
        return "계약 체결 전"
    if re.search(r"계약금", t):
        return "계약금 지급 전(같은 날 맞바꿈)" if re.search(r"맞바꿔|같은\s*날|동시", t) else "계약금 지급 전"
    if re.search(r"잔금|예치", t):
        return "잔금 지급 전"
    if re.search(r"인도\s*즉시|사업자등록", t):
        return "인도 즉시"
    if re.search(r"체결\s*전", t):
        return "계약 체결 전"
    if re.search(r"서명|날인|체결", t):
        return "계약 체결 시"
    return "계약 체결 전"


def _check_text(raw: str) -> str:
    t = re.sub(r"^\s*(?:체결\s*전|확인|필수)\s*[:：]\s*", "", _s(raw)).strip()
    t = re.sub(r"^\s*□\s*", "", t)
    return (_clean(t, keep_law=True) or t).rstrip(".")


_DOC_KEYS = (
    "등기사항전부증명서", "완납증명", "건축물대장", "질권설정 승낙서", "상계권 불행사", "사업자등록", "감정평가",
    "자필 서명", "보증인 재산", "공유자", "근저당권설정 등기", "선순위 대출", "재예치", "투자 예산", "용도변경 비용",
)


def _check_key(text: str) -> str:
    t = re.sub(r"\s+", "", _s(text))
    for k in _DOC_KEYS:
        if re.sub(r"\s+", "", k) in t:
            return k
    return re.sub(r"[^가-힣A-Za-z0-9]", "", t)[:24]


# ── 미확정 조건 ──────────────────────────────────────────────────────────────

_RX_TERM = re.compile(
    r"(?:금\s*[일이삼사오육칠팔구십백천만억]+\s*원|₩\s*[\d,]+|[\d][\d,.]*\s*(?:%|퍼센트|억\s*원|만\s*원|천만\s*원|원|영업일|일|개월|년|회|건|시간|주))"
)
_RX_PLACEHOLDER = re.compile(r"○+|□+|\[\s*\]|\(\s*\)|OO|XX|_{2,}|\?\?")


def _norm(s: str) -> str:
    return re.sub(r"[\s,]", "", _s(s))


def undecided_terms(new_text: str, *, contract_text: str, answers_text: str) -> list[str]:
    """수정 문구에 든 금액·기간·횟수 가운데 원문과 사용자 답변 어디에도 없는 것 — 임의로 채운 조건이다."""
    have = _norm(contract_text) + "|" + _norm(answers_text)
    out: list[str] = []
    for m in _RX_TERM.finditer(_s(new_text)):
        term = m.group(0).strip()
        if _norm(term) and _norm(term) not in have and term not in out:
            out.append(term)
    t = _s(new_text)
    for m in _RX_PLACEHOLDER.finditer(t):
        # 빈칸이 무엇의 빈칸인지 앞말과 함께 적는다 — "최고액은 금 [ ]원".
        ctx = re.split(r"[,.]\s*", t[max(0, m.start() - 16):m.start()])[-1].strip()
        unit = t[m.end():m.end() + 1] if re.match(r"[원일월년%회건]", t[m.end():m.end() + 1]) else ""
        label = f"{ctx} {m.group(0)}{unit}".strip()
        if label not in out:
            out.append(label)
    return out


# ── 원문 위치 대조 ───────────────────────────────────────────────────────────

def _art_of(path: str) -> str:
    m = re.search(r"제\s*(\d+)\s*조", _s(path))
    return m.group(1) if m else ""


def _host_paths(target: str, clauses: list[Any] | None) -> list[str]:
    """고칠 문장이 실제로 들어 있는 조항 경로들(가장 좁은 것 먼저)."""
    key = _flat(target)[:40]
    if not key:
        return []
    hits: list[tuple[int, str]] = []
    for c in clauses or []:
        text = c.get("text") if isinstance(c, dict) else getattr(c, "text", "")
        path = c.get("display_path") if isinstance(c, dict) else getattr(c, "display_path", "")
        if path and key in _flat(text):
            hits.append((len(_s(text)), _s(path)))
    return [p for _n, p in sorted(hits)]


# ── 항목 만들기 ──────────────────────────────────────────────────────────────

_RX_PARA_HEAD = re.compile(r"(?m)^\s*(?:\((\d{1,2})\)|([①-⑳]))\s*")


def _best_paragraph(original: str, new_text: str) -> tuple[str, str] | None:
    """여러 항으로 된 원문에서 새 문안과 가장 비슷한 항(번호, 문구). 항이 하나뿐이면 None."""
    import difflib

    heads = list(_RX_PARA_HEAD.finditer(_s(original)))
    if len(heads) < 2:
        return None
    best: tuple[float, str, str] | None = None
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(original)
        chunk = original[m.start():end].strip()
        no = m.group(1) or str("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳".index(m.group(2)) + 1)
        score = difflib.SequenceMatcher(None, _flat(chunk)[:400], _flat(new_text)[:400]).ratio()
        if best is None or score > best[0]:
            best = (score, no, chunk)
    return (best[1], best[2]) if best and best[0] >= 0.25 else None


def _fid(d: dict[str, Any]) -> str:
    return _s(d.get("finding_id") or d.get("clause_id"))


def _rewrite_of(full: dict[str, Any], issue: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    ri = full.get("redline_instruction") if isinstance(full.get("redline_instruction"), dict) else None
    ri = ri or (issue.get("redline_instruction") if isinstance(issue.get("redline_instruction"), dict) else {}) or {}
    text = _s(ri.get("final_clause_text") or ri.get("replacement_text")
              or full.get("suggested_rewrite") or issue.get("proposed_revision")).strip()
    if full.get("action_only") or issue.get("action_only"):
        text = ""
    return text, ri


def _title(issue: dict[str, Any], full: dict[str, Any], art_titles: dict[str, str] | None = None) -> str:
    t = _s(issue.get("issue_title") or full.get("issue_title")).strip()
    t = re.sub(r"^\s*\[[^\]]{1,20}\]\s*", "", t)
    if not t or len(t) > 60:
        # 제목이 없거나 문제 서술 그대로인 지적은 조 제목으로 부른다 — 문제는 "현재·문제" 칸이 한 번 말한다.
        ct = re.sub(r"^\s*제\s*\d+\s*조\s*", "", _s(issue.get("clause_title") or full.get("clause_title")))
        if not ct.strip(" []()") and art_titles:
            ct = art_titles.get(_art_of(_s(issue.get("display_path") or full.get("display_path"))), "")
        ct = re.sub(r"^[\[(]|[\])]$", "", ct.strip()).strip()
        if ct:
            return f"{ct} 문구 보완"
        head = re.split(r"\s+—\s+|:\s|;\s", _clean(t, keep_law=bool(full.get("is_deal_core_risk"))) or t)[0]
        return (head if len(head) <= 70 else re.split(r",\s", head)[0]).rstrip(". ") or "문구 보완"
    t = _clean(t, keep_law=bool(full.get("is_deal_core_risk"))) or t
    return t.rstrip(".")


def _level(issue: dict[str, Any], full: dict[str, Any]) -> str:
    cat = _s(full.get("review_category") or issue.get("review_category"))
    if cat:
        return {"필수수정": "필수", "권장수정": "권장", "체결 전 확인": "중요", "수용 가능한 위험": "결정"}.get(cat, "권장")
    sev = _s(issue.get("severity") or full.get("risk_tier")).upper()
    return "필수" if sev == "HIGH" else "권장"


def _plain_triplet(issue: dict[str, Any], full: dict[str, Any], core: dict[str, Any] | None) -> tuple[str, str]:
    """(현재 조건, 우리에게 생길 문제) — 데이터의 문장에서 고른다."""
    if core:
        current = _first(core.get("failed_protection"), limit=220, keep_law=True)
        problem = _first(f"{_s(core.get('event')).rstrip('.')}하면 {_s(core.get('loss'))}".replace("하면하면", "하면"),
                         limit=220, keep_law=True)
        return _end(current), _end(problem)
    lp = _s(full.get("loss_path_text") or issue.get("loss_path_text"))
    if lp:
        ev, failed, loss = _split_arrow(lp)
        if failed and loss:
            return _end(_first(failed, limit=220)), _end(_first(f"{ev} → {loss}" if ev else loss, limit=220))
    problem_src = _s(full.get("problem") or issue.get("problem") or full.get("rewrite_reason"))
    risk_src = _s(full.get("our_company_risk") or full.get("legal_business_reason") or issue.get("legal_business_reason"))
    current = _first(problem_src, limit=200)
    problem = _first(risk_src, limit=200)
    if not problem or _flat(problem) == _flat(current):
        rest = _sentences(_clean(problem_src))
        problem = " ".join(rest[1:3]) if len(rest) > 1 else ""
    return _end(current), _end(problem)


def _action_text(issue: dict[str, Any], full: dict[str, Any], core: dict[str, Any] | None, has_rw: bool) -> str:
    acts = [str(a) for a in (core or {}).get("action") or full.get("required_actions") or issue.get("required_actions") or []]
    first_act = next((a for a in acts if not re.search(r"^\s*(?:체결\s*전|사업부)", a)), "")
    if has_rw:
        base = _clean(first_act, keep_law=True) if first_act else ""
        if not base:
            neg = _s(full.get("negotiation_position") or issue.get("negotiation_position"))
            base = _first(neg, limit=160) if neg and not re.search(r"반발 가능성|명확화 차원", neg) else ""
        return _end(base or "별첨 문구로 수정을 요청합니다")
    return _end(_clean(first_act, keep_law=True) if first_act else "아래 확인 결과에 따라 협상 여부를 정합니다")


def build_business_brief(
    *,
    clause_results: list[dict[str, Any]] | None,
    high_issues: list[dict[str, Any]] | None,
    medium_issues: list[dict[str, Any]] | None,
    user_review_coverage: list[dict[str, Any]] | None = None,
    deal_assessment: dict[str, Any] | None = None,
    revision_set_check: dict[str, Any] | None = None,
    delivery_remediations: list[dict[str, Any]] | None = None,
    clauses: list[Any] | None = None,
    contract_text: str = "",
    answers: dict[str, Any] | None = None,
    filename: str | None = None,
    our_role: str = "",
) -> BusinessBrief:
    deal = deal_assessment if isinstance(deal_assessment, dict) and deal_assessment.get("active") else None
    core_by_id = {_s(c.get("id")): c for c in (deal or {}).get("core_risks") or [] if isinstance(c, dict)}
    by_id: dict[str, dict[str, Any]] = {}
    for cr in clause_results or []:
        if isinstance(cr, dict):
            for k in (_s(cr.get("finding_id")), _s(cr.get("clause_id"))):
                if k:
                    by_id.setdefault(k, cr)
    held_ids = {
        _s(h.get("clause_id")) for h in ((revision_set_check or {}).get("held") or []) if isinstance(h, dict)
    }
    held_reason = {
        _s(h.get("clause_id")): _s(h.get("reason")) for h in ((revision_set_check or {}).get("held") or []) if isinstance(h, dict)
    }
    withdrawn = {
        p.strip() for r in (delivery_remediations or []) if isinstance(r, dict)
        and re.search(r"LANGUAGE_QUALITY|STATUTE|GROUNDING", _s(r.get("code")))
        for p in re.split(r"[,;]", _s(r.get("clauses"))) if p.strip()
    }
    answers_text = " ".join(_s(v) for v in (answers or {}).values())
    art_titles: dict[str, str] = {}
    for c in clauses or []:
        num = _s(c.get("article_number") if isinstance(c, dict) else getattr(c, "article_number", ""))
        ttl = _s(c.get("clause_title") or c.get("title") if isinstance(c, dict) else getattr(c, "title", ""))
        if num and ttl.strip() and num not in art_titles:
            art_titles[num] = ttl.strip()

    revisions: list[BriefItem] = []
    checks: list[BriefItem] = []
    decisions: list[BriefItem] = []
    appendix: list[AppendixEdit] = []
    trace: dict[str, list[str]] = {}
    seen_topics: set[str] = set()

    issues = [d for d in (high_issues or []) if isinstance(d, dict)] + [d for d in (medium_issues or []) if isinstance(d, dict)]
    for issue in issues:
        fid = _fid(issue)
        full = by_id.get(_s(issue.get("clause_id"))) or by_id.get(fid) or {}
        cid = _s(full.get("clause_id") or issue.get("clause_id"))
        core = core_by_id.get(cid)
        topic_key = f"core:{cid}" if core else f"f:{fid}"
        if topic_key in seen_topics:
            continue
        seen_topics.add(topic_key)
        rw, ri = _rewrite_of(full, issue)
        cat = _s(full.get("review_category") or issue.get("review_category") or (core or {}).get("category"))
        title = _title(issue, full, art_titles)
        path = _s(issue.get("display_path") or full.get("display_path"))
        current, problem = _plain_triplet(issue, full, core)
        status, status_reason, impact = "", "", ""
        if rw and (ri.get("held") or cid in held_ids):
            status = STATUS_PENDING
            status_reason = (_clean(_s(ri.get("hold_reason") or held_reason.get(cid)), keep_law=True)
                             or "수정안을 함께 반영할 때 기존 보호가 줄어드는지 확인하지 못했다").rstrip(".")
            impact = ("필수 수정이라 이 확인이 끝나기 전에는 체결을 미뤄야 합니다." if _level(issue, full) == "필수"
                      else "권장 수정이라 체결을 막지는 않지만, 확인 전까지 현재 문구가 유지됩니다.")
            rw = ""
        if rw and path and path in withdrawn:
            status, status_reason = STATUS_PENDING, "수정 문구가 완결되지 않아 다시 쓰는 중"
            impact = "확인 전까지 현재 문구가 유지됩니다."
            rw = ""
        level = _level(issue, full)
        # 미확정 조건·위치 대조는 별첨에 실을 문구로 한다.
        undecided: list[str] = []
        edit: AppendixEdit | None = None
        if rw:
            target = _s(ri.get("target_text")).strip()
            loc = _s(ri.get("edit_location") or path).strip()
            edit_type = _s(ri.get("edit_type") or "replace")
            loc_clean = re.sub(r"\s*(?:교체|해당 문장 보완)\s*$", "", loc)
            if edit_type == "replace" and target:
                hosts = _host_paths(target, clauses)
                if hosts and _art_of(loc) and all(_art_of(h) != _art_of(loc) for h in hosts):
                    status, status_reason = STATUS_PENDING, f"수정 위치({loc_clean})와 고칠 문장이 있는 조항({hosts[0]})이 다르다"
                    impact = "위치를 바로잡기 전에는 별첨 문구를 반영하지 않습니다."
                elif hosts and hosts[0] != loc_clean and re.search(r"제\s*\d+\s*(?:항|호)", hosts[0]):
                    # 고칠 문장이 실제로 든 가장 좁은 항·호로 적는다 — 위치와 문안의 조항번호를 맞춘다.
                    loc_clean = hosts[0]
            undecided = undecided_terms(rw, contract_text=contract_text, answers_text=answers_text)
            if status != STATUS_PENDING:
                replace_part = _s(ri.get("replacement_text")).strip() or rw
                if edit_type in ("insert_after", "new_clause"):
                    mode, cur, new, added = "항 신설", "", rw, ""
                elif target and replace_part.startswith(target.rstrip(" ‘’'\"“”")) and len(replace_part) > len(target):
                    # 원문 끝의 짝 없는 따옴표(원본 문서의 군더더기)는 무시하고 덧붙는 문장만 보인다.
                    base = target.rstrip(" ‘’'\"“”")
                    mode, cur, new, added = "문장 추가", base, replace_part, replace_part[len(base):].strip()
                elif target and len(target) < len(_s(full.get("original_text"))):
                    mode, cur, new, added = "문장 교체", target, replace_part, ""
                else:
                    mode, cur, new, added = "조항 교체", target or _s(full.get("original_text")), rw, ""
                    para = _best_paragraph(cur, rw)
                    if para is not None:
                        # 여러 항으로 된 조를 한 단락 문안으로 "조항 교체" 하면 다른 항이 사라진 것처럼 읽힌다 — 수정본이 실제로
                        # 바꾸는 항(가장 비슷한 단락)만 위치·현재 문구로 적는다(docx_redline 과 같은 기준).
                        no, cur = para
                        loc_clean = re.sub(r"\s*제\s*\d+\s*항.*$", "", loc_clean) + f" 제{no}항"
                        mode = "항 교체"
                edit = AppendixEdit(no="", item_no="", location=loc_clean, mode=mode, current_text=cur.strip(),
                                    new_text=new.strip(), added_text=added, undecided=undecided)
        kind = KIND_REVISION if (rw or (status == STATUS_PENDING)) else KIND_CHECK
        if cat == _CAT_ACCEPT:
            kind = KIND_DECISION
        acts = [str(a) for a in ((core or {}).get("action") or full.get("required_actions") or issue.get("required_actions") or [])]
        item = BriefItem(
            no="", kind=kind, level=level, title=title, clauses=[path] if path else [],
            current=current, problem=problem, action=_action_text(issue, full, core, bool(rw) or status == STATUS_PENDING),
            loss=_s((core or {}).get("loss")),
            status=status, status_reason=status_reason, impact=impact, undecided=undecided, sources=[fid, cid],
        )
        # 조치 가운데 확인·결정은 해당 절로 보낸다(설명은 이 항목에서 한 번).
        used_action = next((a for a in acts if not re.match(r"^\s*(?:체결\s*전|사업부)", a)), "") if kind == KIND_REVISION else ""
        for a in acts:
            if re.match(r"^\s*사업부\s*(?:판단|결정)", a):
                dec = BriefItem(
                    no="", kind=KIND_DECISION, level="결정", title=title, clauses=item.clauses,
                    current="", problem="",
                    action=_end(_clean(re.sub(r"^\s*사업부\s*(?:판단|결정)\s*(?:필요)?\s*[:：]\s*", "", a), keep_law=True)),
                    sources=[fid, cid],
                )
                setattr(dec, "_owner", item)
                decisions.append(dec)
            elif a != used_action:
                item.checks.append(CheckRow(what=_check_text(a), who=_who(a), when=_when(a)))
        if kind == KIND_CHECK and not item.checks:
            item.checks.append(CheckRow(what=item.action.rstrip("."), who=_who(item.action), when=_when(item.action)))
        # 협상 메모가 사업부에 남긴 선택("수치는 사업부가 정할 사항", "분할 지급은 사업부가 판단할 협상안")은 결정사항으로 —
        # 수정 문구에 숫자를 지어 넣지 않은 대신 누가 정하는지 보여야 한다.
        neg = _s(full.get("negotiation_position") or issue.get("negotiation_position"))
        for sent in _sentences(neg):
            for part in re.split(r"(?<=[고며])\s*,\s*|,\s+", sent):
                if re.search(r"사업부가?\s*(?:정할|판단할|결정할|정해야|판단해야)", part):
                    dec = BriefItem(no="", kind=KIND_DECISION, level="결정", title=title, clauses=item.clauses,
                                    current="", problem="",
                                    action=_end(re.sub(r"(?:이고|이며|고|며)\s*$", "", _clean(part, keep_law=True).rstrip(". "))),
                                    sources=[fid, cid])
                    setattr(dec, "_owner", item)
                    decisions.append(dec)
        if kind == KIND_DECISION:
            item.action = _end(_clean(acts[0], keep_law=True)) if acts else "남는 위험을 감수할지 사업부가 정합니다."
        {KIND_REVISION: revisions, KIND_CHECK: checks, KIND_DECISION: decisions}[kind].append(item)
        if edit is not None:
            item_ref = item
            edit.item_no = ""  # 번호는 아래에서
            appendix.append(edit)
            item_ref.appendix = "pending-link"
            setattr(edit, "_item", item_ref)

    # 거래 판단 핵심 위험 가운데 조항 finding 이 아닌 것(수용 위험·순수 확인) — 같은 쟁점이 이미 실렸으면 넘긴다.
    for cid, core in core_by_id.items():
        if f"core:{cid}" in seen_topics:
            continue
        seen_topics.add(f"core:{cid}")
        acts = [str(a) for a in core.get("action") or []]
        current, problem = _plain_triplet({}, {}, core)
        decided = [a for a in acts if re.match(r"^\s*사업부\s*(?:판단|결정)", a)]
        title = _clean(_s(core.get("title")), keep_law=True).rstrip(".")
        if core.get("category") == _CAT_ACCEPT:
            decisions.append(BriefItem(no="", kind=KIND_DECISION, level="결정", title=title, clauses=[_s(core.get("path"))],
                                       current=current, problem=problem,
                                       action=_end(_clean(decided[0] if decided else "남는 위험의 수용 여부를 사업부가 정합니다", keep_law=True)),
                                       sources=[cid]))
            continue
        item = BriefItem(no="", kind=KIND_CHECK, level="중요" if _s(core.get("tier")) == "HIGH" else "확인", title=title,
                         loss=_s(core.get("loss")),
                         clauses=[_s(core.get("path"))] if core.get("path") else [], current=current, problem=problem,
                         action=_end(_clean(next((a for a in acts if a not in decided), "아래 사항을 확인합니다"), keep_law=True)),
                         sources=[cid])
        for a in acts:
            if a in decided:
                dec = BriefItem(no="", kind=KIND_DECISION, level="결정", title=title, clauses=item.clauses,
                                current="", problem="",
                                action=_end(_clean(re.sub(r"^\s*사업부\s*(?:판단|결정)\s*(?:필요)?\s*[:：]\s*", "", a), keep_law=True)),
                                sources=[cid])
                setattr(dec, "_owner", item)
                decisions.append(dec)
            else:
                item.checks.append(CheckRow(what=_check_text(a), who=_who(a), when=_when(a)))
        if item.checks:
            checks.append(item)

    # 그 밖의 체결 전 확인(거래 판단의 체크리스트) — 이미 항목에 실린 확인은 빼고, 사업부 판단은 결정사항으로.
    general: list[CheckRow] = []
    used = {_check_key(c.what) for it in revisions + checks for c in it.checks}
    for line in (deal or {}).get("closing_checklist") or []:
        line = _s(line)
        if re.search(r"사업부\s*(?:판단|결정)", line):
            act = re.sub(r"\s*(?:을|를)?\s*사업부\s*(?:판단|결정)\s*(?:필요)?\s*$", "", _clean(line, keep_law=True).rstrip("."))
            decisions.append(BriefItem(no="", kind=KIND_DECISION, level="결정", title="", clauses=[], current="", problem="",
                                       action=_end(act)))
            continue
        k = _check_key(line)
        if k in used:
            continue
        used.add(k)
        general.append(CheckRow(what=_check_text(line), who=_who(line), when=_when(line)))

    # 연결된 항목이 없는 요청의 조치(예: 우리가 임대인일 때 "우리 측 부담" 요청) — 답만 있고 할 일이 사라지지 않게 한다.
    for row in user_review_coverage or []:
        if not isinstance(row, dict):
            continue
        ids = row.get("matched_finding_ids") or []
        if isinstance(ids, str):
            ids = re.findall(r"[\w\-]+", ids)
        if ids or row.get("is_comprehensive_scope"):
            continue
        for a in re.split(r";\s*|\n", _s(row.get("required_action"))):
            a = a.strip()
            if not a or re.match(r"^\s*선택\s*[:：]", a) or re.search(r"사업부\s*(?:판단|결정)", a):
                continue   # 선택 사항은 답에, 사업부 판단은 결정사항에 — 확인 목록에 또 싣지 않는다
            k = _check_key(a)
            if k in used:
                continue
            used.add(k)
            general.append(CheckRow(what=_check_text(a), who=_who(a), when=_when(a)))
        judg = _s(row.get("judgment") or row.get("conclusion"))
        if re.search(r"사업부\s*(?:판단|결정)", judg):
            risks = [x.strip() for x in _s(row.get("residual_risk")).splitlines() if x.strip()]
            decisions.append(BriefItem(
                no="", kind=KIND_DECISION, level="결정", title=_flat(_s(row.get("normalized_issue")))[:80],
                clauses=[], current="", problem=_end("; ".join(_clean(x, keep_law=True).rstrip(".") for x in risks[:3])),
                action=("위 부담 가운데 받아들일 범위를 정합니다(사업부 판단)." if re.search(r"수용\s*범위", judg)
                        else _end(_clean(judg, keep_law=True))),
                sources=[_s(row.get("issue_id"))],
            ))
        # 답이 문장 추가를 권하면(proposed_clauses) 그 문장을 별첨에 싣고, 넣을지는 사업부 결정으로 — 답에 "아래 한 문장" 이라
        # 적혀 있는데 전달본에 문장이 없으면 할 일을 알 수 없다(11-02 실측, 용역 재위탁). 위치가 정해지지 않은 선택 문장이라
        # 수정본에 자동 반영된 것으로 보이지 않게 "선택 시 추가" 로 둔다.
        props = row.get("proposed_clauses") or []
        if isinstance(props, str):
            props = [props] if props.strip() and not props.strip().startswith("[") else []
        props = [_s(x).strip() for x in props if _s(x).strip()]
        if props:
            dec = BriefItem(
                no="", kind=KIND_DECISION, level="결정", title=_flat(_s(row.get("normalized_issue")))[:80],
                clauses=[_s(p) for p in (row.get("relevant_clause_paths") or []) if isinstance(row.get("relevant_clause_paths"), list)][:2],
                current="", problem="",   # 이유는 요청 답변이 이미 말한다 — 되풀이하지 않는다
                action="별첨 문장을 넣을지 정합니다 — 넣기로 하면 법무가 넣을 조항을 정합니다.",
                sources=[_s(row.get("issue_id"))],
            )
            decisions.append(dec)
            for ptxt in props:
                e = AppendixEdit(no="", item_no="", location="위치 미정 — 업무 범위 조항 또는 부속합의서", mode="선택 시 추가",
                                 current_text="", new_text=ptxt,
                                 undecided=undecided_terms(ptxt, contract_text=contract_text, answers_text=answers_text))
                setattr(e, "_item", dec)
                appendix.append(e)

    # 사용자 답변이 정한 사업 결정(예: 주차장 부지 담보 미설정) — 그 결정의 범위만 적는다.
    for p in (deal or {}).get("protections") or []:
        if not isinstance(p, dict):
            continue
        m = re.search(r"사용자 결정:\s*([^)]+)\)", _s(p.get("assessment")))
        if m:
            decisions.append(BriefItem(
                no="", kind=KIND_DECISION, level="결정됨", title=_s(p.get("label")), clauses=[_s(p.get("path"))],
                current="", problem=_end(_first(_s((p.get("limits") or [""])[0]) or _s(p.get("assessment")).split("—")[0],
                                                limit=200, keep_law=True)),
                action=_end(f"사업부 답변대로 진행(‘{m.group(1).strip()[:40]}’) — 이 결정은 이 담보에 한정되며 다른 위험의 수용을 뜻하지 않습니다"),
                sources=[_s(p.get("key"))],
            ))

    # 번호 매기기
    for n, it in enumerate(revisions, 1):
        it.no = f"수정 {n}"
    for n, it in enumerate(checks, 1):
        it.no = f"확인 {n}"
    # 같은 결정 문장 중복 제거
    uniq_dec: list[BriefItem] = []
    for d in decisions:
        if any(_flat(d.action) == _flat(x.action) for x in uniq_dec):
            continue
        uniq_dec.append(d)
    decisions = uniq_dec
    for n, it in enumerate(decisions, 1):
        it.no = f"결정 {n}"
        owner_item = getattr(it, "_owner", None)
        if owner_item is not None and owner_item.no:
            it.see = owner_item.no
    for n, e in enumerate(appendix, 1):
        e.no = f"별첨 {n}"
        owner: BriefItem = getattr(e, "_item")
        e.item_no = owner.no
        owner.appendix = e.no
        owner.action = _end(owner.action.rstrip(".") + f" (완성 문구: {e.no})")
    for it in revisions + checks + decisions:
        for src in it.sources:
            if src and it.no not in trace.setdefault(src, []):
                trace[src].append(it.no)

    # 요청사항 답변 — 빠짐없이, 항목 번호로 잇는다.
    reqs: list[RequestAnswer] = []
    for row in user_review_coverage or []:
        if not isinstance(row, dict):
            continue
        ids = row.get("matched_finding_ids") or []
        if isinstance(ids, str):
            ids = re.findall(r"[\w\-]+", ids)
        order = {"수정": 0, "확인": 1, "결정": 2}
        ids = list(ids) + [_s(row.get("issue_id"))]
        linked = sorted({no for i in ids for no in trace.get(i, [])},
                        key=lambda x: (order.get(x.split()[0], 9), int(x.split()[1])))
        ans = _s(row.get("judgment") or row.get("direct_answer") or row.get("conclusion"))
        topic = _s(row.get("topic"))
        if row.get("is_comprehensive_scope") or topic == "deal:draft":
            # 건수는 이 전달본의 항목 수로 말한다 — 내부 분류(필수수정·체결 전 확인…)의 건수를 옮기면 본문과 숫자가 어긋난다.
            ans = (f"계약서 전체를 검토했습니다 — 수정 {len(revisions)}건, 계약 전 확인 {len(checks)}건"
                   + (f"(그 밖의 확인 {len(general)}건)" if general else "") + f", 사업부 결정 {len(decisions)}건")
            linked = []
        elif topic == "deal:other":
            ans = "계약 문언보다 서류 확인과 지급·등기 순서가 결론을 좌우합니다 — 3절 계약 전 확인사항에 모두 모았습니다"
            linked = []
        else:
            ans = re.sub(r"^거래 전체 판단:\s*", "", ans)
            head, sep, _tail = ans.partition(":")
            if sep and len(head.strip()) >= 4:
                ans = head.strip()   # 판단 요지만 — 근거 목록은 연결된 항목이 설명한다
            ans = _first(ans, limit=180, keep_law=True)
        ans = re.sub(r"아래\s*(?:한\s*)?문장", "별첨 문장", ans)   # 전달본에서 "아래" 는 가리키는 곳이 없다
        opt = _s(row.get("required_action"))
        if re.match(r"^\s*선택\s*[:：]", opt):
            ans = _end(ans) + " (선택) " + _end(_clean(re.sub(r"^\s*선택\s*[:：]\s*", "", opt), keep_law=True))
        reqs.append(RequestAnswer(
            index=_s(row.get("request_index") or len(reqs) + 1),
            request=_flat(_s(row.get("normalized_issue") or row.get("original_user_text")))[:120],
            answer=_end(ans), items=linked,
        ))

    # 검토 결론 3~5문장
    pending = [f"{it.no} {it.title}: {it.status_reason}" for it in revisions + checks if it.status == STATUS_PENDING]
    must = [it for it in revisions if it.level == "필수"]
    key_checks = [it for it in checks if it.level == "중요"]
    if any(it.level == "필수" and it.status == STATUS_PENDING for it in revisions):
        verdict = "진행 보류 — 법무 추가 확인 후 판단"
    elif must or key_checks:
        verdict = "조건부 진행 가능"
    elif revisions or checks:
        verdict = "진행 가능(권장 수정 협의)"
    else:
        verdict = "진행 가능"
    concl: list[str] = []
    if verdict.startswith("조건부"):
        if must and key_checks:
            cond = f"필수 수정 {len(must)}건을 반영하고 중요 확인 {len(key_checks)}건을 마치면"
        elif must:
            cond = f"필수 수정 {len(must)}건을 반영하면"
        else:
            cond = f"중요 확인 {len(key_checks)}건을 마치면"
        concl.append(f"조건부로 진행할 수 있습니다 — {cond} 체결할 수 있습니다.")
    elif verdict.startswith("진행 보류"):
        concl.append("필수 수정 가운데 법무가 추가로 확인 중인 항목이 있어, 그 결과가 나오기 전에는 체결을 미루는 것이 좋습니다.")
    elif verdict.startswith("진행 가능("):
        concl.append(f"진행할 수 있습니다 — 다만 권장 수정 {len(revisions)}건은 협상에서 요청하는 것이 좋습니다.")
    else:
        concl.append("현재 문안으로 진행할 수 있습니다.")
    top = (must + key_checks)[:2]
    if top:
        concl.append("선행조건: " + "; ".join(f"{it.title}({it.no})" for it in top) + ".")
    biggest = next((it for it in key_checks + must if it.loss), None) or next(iter(key_checks + must), None)
    if biggest is not None:
        # 본문 "문제" 문장을 되풀이하지 않는다 — 손실 한 줄 또는 항목 번호로 가리킨다.
        if biggest.loss:
            concl.append(f"가장 큰 잔존 위험: {_first(biggest.loss, limit=160, keep_law=True).rstrip('.')}({biggest.no}).")
        else:
            concl.append(f"가장 큰 잔존 위험은 {biggest.no}({biggest.title})이 반영되지 않을 때 남는 문제입니다.")
    if decisions:
        open_dec = [d for d in decisions if d.level != "결정됨"]
        if open_dec:
            concl.append(f"사업부가 정해야 할 사항이 {len(open_dec)}건 있습니다({', '.join(d.no for d in open_dec[:3])}).")
    if pending:
        concl.append(f"법무 추가 확인 중인 항목이 {len(pending)}건 있으며, 각 항목에 체결 판단에 미치는 영향을 적었습니다.")
    concl = concl[:5]

    _gloss_apply([], revisions, checks, decisions)
    keep_count = sum(1 for cr in clause_results or [] if isinstance(cr, dict) and cr.get("keep_as_is")
                     and not cr.get("dedup_suppressed"))
    title = "계약 검토 결과 (사업팀 전달본)"
    if filename:
        title += f" — {re.sub(r'^input_', '', _s(filename))}"
    return BusinessBrief(
        title=title, verdict=verdict, conclusion=concl, requests=reqs, revisions=revisions, checks=checks,
        general_checks=general, decisions=decisions, appendix=appendix, pending=pending, keep_count=keep_count, trace=trace,
    )


def _gloss_apply(concl: list[str], *groups: list[BriefItem]) -> None:
    """법률용어는 전달본에 처음 나오는 곳에 한 번만 쉬운 말을 붙인다."""
    done: set[str] = set()

    def fix(s: str) -> str:
        for term, plain in _GLOSSARY:
            if term in done or term not in s:
                continue
            i = s.find(term)
            j = i + len(term)
            # 낱말 끝(조사 앞)까지 — "근저당권은" 의 "근저당권" 뒤에 붙인다.
            m = re.match(r"[권인자]?", s[j:])
            j += len(m.group(0)) if m else 0
            if s[j:j + 1] in ("(", "（"):
                continue   # 이미 괄호가 붙은 낱말(근저당권(채권최고액 3억 원))에 설명 괄호를 또 붙이지 않는다
            s = s[:j] + f"({plain})" + s[j:]
            done.add(term)
        return s

    for k, c in enumerate(concl):
        concl[k] = fix(c)
    for group in groups:
        for it in group:
            it.current = fix(it.current)
            it.problem = fix(it.problem)


# ── 렌더링용 줄 ──────────────────────────────────────────────────────────────

def brief_sections(b: BusinessBrief) -> list[tuple[str, list[tuple[str, str]]]]:
    """(절 제목, [(스타일, 문장)]) — DOCX·PDF·화면이 같은 줄을 쓴다. 스타일: h(항목 제목)·p·k(강조)·m(보조)·t(완성 문구)."""
    out: list[tuple[str, list[tuple[str, str]]]] = []
    s1: list[tuple[str, str]] = [("k", f"판단: {b.verdict}")]
    s1 += [("p", c) for c in b.conclusion]
    if b.requests:
        s1.append(("h", "요청하신 사항"))
        for r in b.requests:
            link = f" → {', '.join(r.items)}" if r.items else ""
            s1.append(("p", f"요청 {r.index}. {r.request}: {r.answer}{link}"))
    out.append(("1. 검토 결론", s1))

    s2: list[tuple[str, str]] = []
    for it in b.revisions:
        tag = f"[{it.level}]" + (f" [{it.status}]" if it.status else "")
        s2.append(("h", f"{it.no} {tag} {it.title} — {', '.join(c for c in it.clauses if c)}"))
        if it.current:
            s2.append(("p", f"현재: {it.current}"))
        if it.problem:
            s2.append(("p", f"문제: {it.problem}"))
        s2.append(("k", f"할 일: {it.action}"))
        if it.status:
            s2.append(("k", f"{it.status}: {it.status_reason}. 체결 영향: {it.impact}"))
        if it.undecided:
            dec = next((d.no for d in b.decisions if set(d.sources) & set(it.sources)), "")
            s2.append(("k", f"미확정 조건: {', '.join(it.undecided)} — 원문·답변에 없는 조건이라 "
                            + (f"{dec}에서 정한 뒤 별첨 문구에 넣습니다" if dec else "확정 전 사업부·상대방과 정합니다")))
        for c in it.checks:
            s2.append(("m", f"함께 확인: {c.what} — {c.who} / {c.when}"))
    if not s2:
        s2.append(("p", "고칠 조항이 없습니다."))
    out.append(("2. 계약서 수정사항", s2))

    s3: list[tuple[str, str]] = []
    if b.checks or b.general_checks:
        s3.append(("m", "서류는 사업부가 상대방에게 받아 법무에 넘기면 법무가 내용을 확인합니다."))
    for it in b.checks:
        tag = f"[{it.level}]" + (f" [{it.status}]" if it.status else "")
        s3.append(("h", f"{it.no} {tag} {it.title}" + (f" — {', '.join(c for c in it.clauses if c)}" if it.clauses else "")))
        if it.current:
            s3.append(("p", f"현재: {it.current}"))
        if it.problem:
            s3.append(("p", f"문제: {it.problem}"))
        for c in it.checks:
            s3.append(("p", f"□ {c.what} — 누가: {c.who} / 언제까지: {c.when}"))
    if b.general_checks:
        s3.append(("h", "그 밖의 계약 전 확인"))
        for c in b.general_checks:
            s3.append(("p", f"□ {c.what} — 누가: {c.who} / 언제까지: {c.when}"))
    if not s3:
        s3.append(("p", "계약 전에 따로 확인할 사항이 없습니다."))
    out.append(("3. 계약 전 확인사항", s3))

    s4: list[tuple[str, str]] = []
    for it in b.decisions:
        if it.title:
            s4.append(("h", f"{it.no} [{it.level}] {it.title}" + (f" — {', '.join(c for c in it.clauses if c)}" if any(it.clauses) else "")))
            if it.problem:
                s4.append(("p", f"선택에 따라 남는 위험: {it.problem}"))
            elif it.see:
                s4.append(("p", f"남는 위험: {it.see} 참고"))
            s4.append(("k", f"{'결정 내용' if it.level == '결정됨' else '정할 것'}: {it.action}"))
        else:
            s4.append(("k", f"{it.no} [{it.level}] 정할 것: {it.action}"))
    if not s4:
        s4.append(("p", "사업부가 따로 정할 상업조건이 없습니다."))
    out.append(("4. 사업부 결정사항", s4))

    s5: list[tuple[str, str]] = []
    for e in b.appendix:
        s5.append(("h", f"{e.no} ({e.item_no}) {e.location} — {e.mode}"))
        if e.current_text and e.mode != "문장 추가":
            s5.append(("m", f"현재 문구: {e.current_text}"))
        if e.mode == "문장 추가":
            # 덧붙일 문장 자체가 완성 문장이다 — 반영 후 전체 문구를 또 싣으면 같은 문장이 두 번 나온다.
            s5.append(("m", f"{e.location} 끝에 아래 문장을 덧붙입니다."))
            s5.append(("t", e.added_text))
        else:
            s5.append(("t", e.new_text))
        if e.undecided:
            s5.append(("k", f"미확정: {', '.join(e.undecided)} — 확정 전에는 이 값을 그대로 쓰지 말고 사업부·상대방과 정합니다."))
    if not s5:
        s5.append(("p", "반영할 수정 문구가 없습니다."))
    tail = "상세 근거·법률 검토 기록은 법무 내부 분석본에 보관합니다."
    if b.keep_count:
        tail = f"현재 문구로 충분하다고 본 조항 {b.keep_count}건과 " + tail
    s5.append(("m", tail))
    out.append(("별첨. 수정 위치와 완성 문구", s5))
    return out


def brief_text(b: BusinessBrief) -> str:
    lines = [b.title]
    for head, rows in brief_sections(b):
        lines.append("")
        lines.append(head)
        lines += [r for _s_, r in rows]
    return "\n".join(lines)


# ── DOCX·PDF ────────────────────────────────────────────────────────────────

def build_business_brief_docx(brief: BusinessBrief) -> bytes:
    import xml.etree.ElementTree as ET

    from runtime.review import legal_review_docx as L

    doc = ET.Element(L._w("document"))
    body = ET.SubElement(doc, L._w("body"))
    L._heading1(body, brief.title)
    for head, rows in brief_sections(brief):
        L._blank(body)
        L._heading1(body, head)
        for style, text in rows:
            if style == "h":
                L._para(body, text, bold=True)
            elif style == "k":
                L._para(body, text, bold=True, color=L.COLOR_HIGH if STATUS_PENDING in text or text.startswith("미확정") else None)
            elif style == "m":
                L._para(body, text, italic=True, indent=1)
            elif style == "t":
                for line in text.splitlines() or [""]:
                    if line.strip():
                        L._para(body, line.strip(), indent=2, color=L.COLOR_MEDIUM)
            else:
                L._para(body, text, indent=1 if text.startswith("□") else 0)
    ET.SubElement(body, L._w("sectPr"))
    return L.pack_document(doc)


def build_business_brief_pdf(brief: BusinessBrief) -> bytes:
    from fpdf import FPDF

    from runtime.review import legal_review_pdf as P

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    P._ensure_font(pdf)
    pdf.add_page()
    P._heading(pdf, brief.title, size=14)
    for head, rows in brief_sections(brief):
        P._heading(pdf, head, size=12)
        for style, text in rows:
            if style == "h":
                P._label(pdf, text)
            elif style == "k":
                pdf.set_font(P._FONT_FAMILY, "B", 10)
                pdf.set_text_color(*(P.COLOR_HIGH if STATUS_PENDING in text or text.startswith("미확정") else P.COLOR_DARK))
                P._mc(pdf, 0, 6, text)
                pdf.set_text_color(0, 0, 0)
            elif style == "m":
                pdf.set_font(P._FONT_FAMILY, "", 9)
                pdf.set_text_color(*P.COLOR_MUTED)
                P._mc(pdf, 0, 5, text)
                pdf.set_text_color(0, 0, 0)
            elif style == "t":
                pdf.set_font(P._FONT_FAMILY, "", 10)
                pdf.set_text_color(*P.COLOR_MEDIUM)
                P._mc(pdf, 0, 6, text)
                pdf.set_text_color(0, 0, 0)
            else:
                P._body(pdf, text)
    return bytes(pdf.output())


__all__ = [
    "AppendixEdit", "BriefItem", "BusinessBrief", "CheckRow", "RequestAnswer", "STATUS_PENDING",
    "brief_sections", "brief_text", "build_business_brief", "build_business_brief_docx", "build_business_brief_pdf",
    "undecided_terms",
]
