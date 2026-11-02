"""거래 전체 판단(Deal Assessment) — 조항을 읽기 전에 거래를 먼저 본다 (2026-10-30).

무엇이 문제였나 (천안 상가 임대차 실측, 2026-10-29 사용자 세션)
─────────────────────────────────────────────────────────
검토요청은 "보증금 5억 중 2.5억 근저당·2.5억 예금질권, 경락률이 나빠 제14조 특약으로 보완, 주차장
공동담보 여부, 토지주 연대보증, 계열사 전대, 투자비 안전장치" 였다. 결과는
  - 요청 6건 전부 "이 쟁점을 직접 다루는 조항을 찾지 못했습니다", 보증금·주차장 요청은 "적정 — 커버됨"
  - 보증금 미회수 HIGH 는 Triage 낱말 점수(2/5)로 DROP, 화면에는 인도 지연 의견만 남음
  - 부동산 임대차가 "렌탈"(제품 렌탈·대리점 필드, 가구렌탈 법령), 당사자 역할이 공급자/구매자
조항마다 낱말로 위험을 찾았을 뿐, 거래 — 무엇을 내고 무엇을 돌려받는지, 그 회수를 무엇이 지키는지,
그 보호가 실제로 작동하는지 — 를 아무도 보지 않았다.

이 모듈이 하는 일
────────────────
1. 거래 모델: 사업 목적 · 주고받는 돈과 권리 · 당사자와 제3자의 기능(물상보증인·연대보증인) · 이행 순서 ·
   잃을 수 있는 것 · 이미 확보된 보호 · 확인되지 않은 사실. 전부 원문 인용(evidence)과 함께.
   검토요청서의 수치(감정가·선순위 등)는 **사용자 제시 · 미확인** 으로만 쓴다.
2. 실제 거래로 분류: 부동산 임대차와 제품 렌탈은 이름이 비슷해도 다른 거래다(목적물·명도·등기 vs 렌탈료·반납).
3. 보호수단 실효성: 근저당·예금질권·상계·대위변제·연대보증·물상보증·손해배상/위약벌·환급·사용권을
   누구에게 / 언제·어떤 절차로 / 무엇이 제한하는지(순위·한도·예외·제3자) / 상대방 지급불능에도 남는지 /
   다른 조항과 함께 보면 공백이 있는지로 평가한다. "있다" 와 "작동한다" 를 구분한다.
4. 핵심 위험: "어떤 사건 → 어떤 보호가 작동하지 않음 → 어떤 손실" 로만 세운다. 필수수정 · 체결 전 확인 ·
   권장수정 · 수용 가능한 위험으로 나눈다. 막연한 분쟁 가능성·일방성은 위험의 근거가 아니다.
5. 요청 답변: 번호 요청마다 판단 / 근거 / 기존 보호 / 남은 위험 / 필요 조치. 요청 주제에 묶인 보호수단과
   위험만 쓴다 — 보증금 질문에 인도 지연을 답하지 않는다.

방향(누구의 보호인가)은 원문의 권리자 표지("“X”를 근저당권자로", "“X”에게 질권", "“X”는 … 상계할 수
있다")로 읽는다. 회사명·조번호·계약서 이름은 신호로 쓰지 않는다.
법률효과는 조건부로 적는다 — 등기부·감정서·재무자료 없이 회수 가능성을 확정하지 않는다.
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# ── 분류 값 ──────────────────────────────────────────────────────────────────

NATURE_REAL_ESTATE_LEASE = "real_estate_lease"
NATURE_GOODS_RENTAL = "goods_rental"

NATURE_LABELS = {
    NATURE_REAL_ESTATE_LEASE: "부동산(상가) 임대차계약",
    NATURE_GOODS_RENTAL: "물품 렌탈·임대계약",
}

CAT_MUST = "필수수정"
CAT_PRECHECK = "체결 전 확인"
CAT_SHOULD = "권장수정"
CAT_ACCEPT = "수용 가능한 위험"
CATEGORY_ORDER = (CAT_MUST, CAT_PRECHECK, CAT_SHOULD, CAT_ACCEPT)

V_EFFECTIVE = "effective"
V_CONDITIONAL = "conditional"
V_PARTIAL = "partial"
V_WEAK = "weak"
VERDICT_LABELS = {
    V_EFFECTIVE: "작동함(요건 확인 전제)",
    V_CONDITIONAL: "조건부 — 자료 확인 전 단정 불가",
    V_PARTIAL: "일부만 작동",
    V_WEAK: "실효성 낮음",
}


# ── 데이터 구조 ──────────────────────────────────────────────────────────────

@dataclass
class Evidence:
    path: str
    quote: str


@dataclass
class PartyInfo:
    label: str
    entity: str = ""
    is_us: bool = False
    person: bool = False
    functions: list[str] = field(default_factory=list)


@dataclass
class MoneyFlow:
    kind: str
    label: str
    amount: int | None
    payer: str
    payee: str
    returnable: bool = False
    due: str = ""
    evidence: Evidence | None = None


@dataclass
class Protection:
    key: str
    kind: str
    label: str
    ours: bool
    path: str
    quote: str
    secures: str = ""
    against: str = ""
    procedure: str = ""
    limits: list[str] = field(default_factory=list)
    insolvency: str = ""
    conflicts: list[str] = field(default_factory=list)
    verdict: str = V_CONDITIONAL
    assessment: str = ""
    needed_docs: list[str] = field(default_factory=list)
    statutes: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)

    @property
    def verdict_label(self) -> str:
        return VERDICT_LABELS.get(self.verdict, self.verdict)


@dataclass
class CoreRisk:
    id: str
    title: str
    category: str
    tier: str
    event: str
    failed_protection: str
    loss: str
    topic: str
    amount: int | None = None
    article: str = ""
    path: str = ""
    action: list[str] = field(default_factory=list)
    needed_docs: list[str] = field(default_factory=list)
    conditional: bool = True
    statutes: list[str] = field(default_factory=list)
    #: (교체 대상 문장, 바꿀 문장) — 관련 문장의 최소 보완. 조 전체 교체가 아니다.
    edit: tuple[str, str] | None = None
    #: 조항 finding 으로 내보낼지(수용 위험·순수 확인사항은 거래 판단에만 싣는다)
    as_finding: bool = True


@dataclass
class RequestAnswer:
    index: int
    question: str
    details: list[str]
    topic: str
    verdict: str
    judgment: str
    basis: str
    existing_protection: str
    residual_risk: str
    required_action: str
    needed_documents: list[str] = field(default_factory=list)
    clause_paths: list[str] = field(default_factory=list)
    core_risk_ids: list[str] = field(default_factory=list)
    substantive: bool = True


@dataclass
class DealAssessment:
    nature: str = ""
    nature_basis: list[str] = field(default_factory=list)
    our_label: str = ""
    our_role: str = ""
    purpose: list[str] = field(default_factory=list)
    parties: list[PartyInfo] = field(default_factory=list)
    money_flows: list[MoneyFlow] = field(default_factory=list)
    sequence: list[str] = field(default_factory=list)
    exposures: list[dict[str, Any]] = field(default_factory=list)
    protections: list[Protection] = field(default_factory=list)
    unknowns: list[dict[str, str]] = field(default_factory=list)
    user_facts: list[str] = field(default_factory=list)
    core_risks: list[CoreRisk] = field(default_factory=list)
    request_answers: list[RequestAnswer] = field(default_factory=list)
    closing_checklist: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        """거래 판단이 조항 검토를 이끌 만큼 확인됐는가(보호수단·노출이 원문에서 확인됨)."""
        return bool(self.nature) and bool(self.protections or self.exposures)

    @property
    def nature_label(self) -> str:
        return NATURE_LABELS.get(self.nature, "")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["nature_label"] = self.nature_label
        d["active"] = self.active
        d["request_rows"] = coverage_rows(self.request_answers)
        d["numbered_requests"] = list(getattr(self, "_numbered_requests", []))
        for p, src in zip(d["protections"], self.protections):
            p["verdict_label"] = src.verdict_label
        for c in d["core_risks"]:
            c["loss_path_text"] = loss_path_text(c)
        return d


def loss_path_text(c: dict[str, Any] | CoreRisk) -> str:
    g = (lambda k: getattr(c, k)) if isinstance(c, CoreRisk) else c.get
    return f"{g('event')} → {g('failed_protection')} → {g('loss')}"


# ── 원문 도구 ────────────────────────────────────────────────────────────────

def _attr(c: Any, name: str) -> str:
    v = c.get(name) if isinstance(c, dict) else getattr(c, name, "")
    return "" if v is None else str(v)


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


@dataclass
class _Article:
    num: str
    path: str
    title: str
    text: str
    clause: Any


def _articles(clauses: list[Any] | None) -> list[_Article]:
    out: list[_Article] = []
    for c in clauses or []:
        num = _attr(c, "article_number")
        if not num or _attr(c, "paragraph_number") or _attr(c, "item_number"):
            continue
        out.append(_Article(num, _attr(c, "display_path") or f"제{num}조",
                            _attr(c, "clause_title") or _attr(c, "title"), _attr(c, "text"), c))
    return out


_RX_PARA = re.compile(r"(?m)^\s*(?:\((\d{1,2})\)|([①-⑳]))\s*")
_RX_ITEM = re.compile(r"(?m)^\s*(\d{1,2})\.\s+")


@dataclass
class _Span:
    art: _Article
    para: str
    item: str
    text: str

    @property
    def path(self) -> str:
        p = f"제{self.art.num}조"
        if self.para:
            p += f" 제{self.para}항"
        if self.item:
            p += f" 제{self.item}호"
        return p


def _spans(arts: list[_Article]) -> list[_Span]:
    """조 → 항 → 호 단위 조각. 항 표지가 없으면 조 전체가 한 조각이다."""
    out: list[_Span] = []
    for a in arts:
        body = a.text
        heads = list(_RX_PARA.finditer(body))
        paras: list[tuple[str, str]] = []
        if not heads:
            paras.append(("", body))
        else:
            for i, m in enumerate(heads):
                end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
                no = m.group(1) or str("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳".index(m.group(2)) + 1)
                paras.append((no, body[m.end():end]))
        for no, ptxt in paras:
            items = list(_RX_ITEM.finditer(ptxt))
            lead = ptxt[: items[0].start()] if items else ptxt
            out.append(_Span(a, no, "", lead.strip()))
            for j, im in enumerate(items):
                iend = items[j + 1].start() if j + 1 < len(items) else len(ptxt)
                out.append(_Span(a, no, im.group(1), ptxt[im.end():iend].strip()))
    return out


def _sentences(s: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[다음함])\.\s*|\n", str(s or "")) if x.strip()]


def _find(spans: list[_Span], rx: str, *, need: str = "") -> _Span | None:
    for sp in spans:
        t = _flat(sp.text)
        if re.search(rx, t) and (not need or re.search(need, t)):
            return sp
    return None


def _sentence_with(text: str, rx: str) -> str:
    for s in _sentences(text):
        if re.search(rx, s):
            return s
    return ""


# ── 금액 ─────────────────────────────────────────────────────────────────────

_KDIG = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}
_KSMALL = {"십": 10, "백": 100, "천": 1000}
_KBIG = {"만": 10 ** 4, "억": 10 ** 8, "조": 10 ** 12}


def parse_korean_amount(s: str) -> int | None:
    """"이억오천만" → 250000000. 숫자가 섞이면(“2억5천만”) 그것도 읽는다."""
    s = re.sub(r"[\s,금원₩\\]", "", str(s or ""))
    if not s:
        return None
    if re.fullmatch(r"\d+", s):
        return int(s)
    total, section, num = 0, 0, 0
    i = 0
    found = False
    while i < len(s):
        ch = s[i]
        m = re.match(r"\d+(?:\.\d+)?", s[i:])
        if m:
            num = float(m.group(0))
            i += len(m.group(0))
            found = True
            continue
        if ch in _KDIG:
            num = _KDIG[ch]
            found = True
        elif ch in _KSMALL:
            section += (num or 1) * _KSMALL[ch]
            num = 0
            found = True
        elif ch in _KBIG:
            section += num
            total += (section or 1) * _KBIG[ch]
            section, num = 0, 0
            found = True
        else:
            return None
        i += 1
    if not found:
        return None
    return int(total + section + num)


_RX_PAREN_DIGITS = re.compile(r"[(（]\s*[₩\\￦]?\s*([\d,]{5,})\s*원?\s*[)）]")
_RX_GEUM = re.compile(r"(?:金|금)\s*([일이삼사오육칠팔구십백천만억조\d,.\s]{1,20}?)\s*원")


def amounts_in(s: str) -> list[int]:
    out: list[int] = []
    for m in _RX_PAREN_DIGITS.finditer(s or ""):
        out.append(int(m.group(1).replace(",", "")))
    if out:
        return out
    for m in _RX_GEUM.finditer(s or ""):
        v = parse_korean_amount(m.group(1))
        if v:
            out.append(v)
    return out


def won(v: int | None) -> str:
    if not v:
        return "금액 미상"
    if v >= 10 ** 8:
        e = v / 10 ** 8
        return f"{e:g}억 원"
    if v >= 10 ** 4:
        return f"{v // 10 ** 4:,}만 원"
    return f"{v:,}원"


# ── 당사자 ───────────────────────────────────────────────────────────────────

_RX_DEFINE = re.compile(
    r"([^,()“”\"'\n]{2,40}?)\s*\(\s*이하\s*[“\"'‘]([^”\"'’]{1,12})[”\"'’]\s*(?:이)?라\s*(?:한다|함)\s*\)")
_RX_CORP = re.compile(r"주식회사|㈜|\(주\)|유한회사|법인|재단|조합|공사|Inc|Ltd|Co\.|Corp|LLC", re.IGNORECASE)


def _parties(text: str, entity: str, our_labels: list[str] | None) -> list[PartyInfo]:
    out: list[PartyInfo] = []
    head = str(text or "")[:1500]
    for m in _RX_DEFINE.finditer(head):
        ent = re.sub(r"^(?:본\s*\S+\s*계약은|및|과|와|,)\s*", "", m.group(1)).strip(" ,")
        ent = re.sub(r"^.*?(?:계약은|사이에|간에)\s*", "", ent).strip()
        ent = re.sub(r"^(?:및|과|와)\s*", "", ent).strip()
        label = m.group(2).strip()
        if any(p.label == label for p in out) or re.search(r"목적물|물건|본건|계약|부동산|건물|토지$", label):
            continue
        out.append(PartyInfo(label=label, entity=ent,
                             person=bool(ent) and not _RX_CORP.search(ent) and bool(re.fullmatch(r"[가-힣]{2,4}", ent))))
    ent_core = re.sub(r"주식회사|㈜|\(주\)|\s", "", str(entity or ""))
    labels = {str(x) for x in our_labels or []}
    for p in out:
        core = re.sub(r"주식회사|㈜|\(주\)|\s", "", p.entity)
        if (ent_core and ent_core in core) or (p.label in labels and not any(
                q.label in labels for q in out if q is not p)):
            p.is_us = True
    return out


def _q(label: str, text: str) -> str:
    """원문이 쓰는 따옴표 모양 그대로의 약칭."""
    m = re.search(rf"([“\"‘']){re.escape(label)}([”\"’'])", text or "")
    return f"{m.group(1)}{label}{m.group(2)}" if m else f"“{label}”"


# ── 분류 ─────────────────────────────────────────────────────────────────────

_RX_RE_SIGNALS = (
    (r"부동산|소재지", "부동산·소재지 표시"),
    (r"토지|대지", "토지·대지"),
    (r"건물|\d+\s*층|B\d", "건물·층"),
    (r"㎡|평방|\d+\s*평", "면적(㎡·평)"),
    (r"명도", "명도"),
    (r"등기|근저당|전세권", "등기·담보권"),
    (r"용도\s*변경|건축물|불법\s*건축", "건축물 용도"),
)
_RX_RENTAL_SIGNALS = (
    (r"렌\s*탈\s*료|렌탈\s*(?:기간|업자|사|계약)", "렌탈료·렌탈 구조"),
    (r"제품[^.\n]{0,15}(?:임대|렌탈)|(?:임대|렌탈)\s*(?:제품|물품|장비)", "제품 임대"),
    (r"반\s*납|회\s*수\s*(?:조건|시점)", "제품 반납"),
    (r"소모품|필터|A/S|방문\s*관리", "제품 관리"),
)


def classify_nature(text: str, labels: list[str]) -> tuple[str, list[str]]:
    t = str(text or "")
    lease_parties = any("임대인" in x for x in labels) and any("임차인" in x for x in labels)
    if not lease_parties and not re.search(r"임\s*대\s*인", t):
        return "", []
    re_hits = [lab for rx, lab in _RX_RE_SIGNALS if re.search(rx, t)]
    rent_hits = [lab for rx, lab in _RX_RENTAL_SIGNALS if re.search(rx, t)]
    if len(re_hits) >= 3 and len(re_hits) > 2 * len(rent_hits):
        return NATURE_REAL_ESTATE_LEASE, re_hits
    if rent_hits:
        return NATURE_GOODS_RENTAL, rent_hits
    return "", []


# ── 사용자 제시 사실(미확인) ──────────────────────────────────────────────────

_RX_UF_APPRAISAL = re.compile(r"감정\s*(?:평가)?\s*(?:가|액|금액)?\s*[:：]?\s*(\d+(?:\.\d+)?)\s*억")
_RX_UF_SENIOR = re.compile(r"선순위[^\d\n]{0,14}(\d+(?:\.\d+)?)\s*억")
_RX_UF_AUCTION = re.compile(r"경[락략]\s*[율률]|낙찰\s*가?\s*[율률]")


def _user_facts(review_focus: str) -> dict[str, Any]:
    t = str(review_focus or "")
    out: dict[str, Any] = {}
    m = _RX_UF_APPRAISAL.search(t)
    if m:
        out["appraisal"] = int(float(m.group(1)) * 10 ** 8)
    m = _RX_UF_SENIOR.search(t)
    if m:
        out["senior"] = int(float(m.group(1)) * 10 ** 8)
    m = _RX_UF_AUCTION.search(t)
    if m:
        out["auction_concern"] = _flat(t[max(0, m.start() - 20): m.end() + 30])
    return out


def qa_pairs(review_focus: str, answers: dict[str, Any] | None, asked_questions: list[Any] | None) -> list[tuple[str, str]]:
    """사전질문 답변 (질문, 답). 검토요청에 붙은 "[사용자 확인 답변]" 줄과 answers 를 함께 본다."""
    out: list[tuple[str, str]] = []
    m = re.search(r"\[사용자 확인 답변\]([\s\S]*)", str(review_focus or ""))
    if m:
        for line in m.group(1).splitlines():
            mm = re.match(r"\s*-\s*(.+?\?)\s*:\s*(.+?)\s*$", line)
            if mm:
                out.append((mm.group(1), mm.group(2)))
    titles: dict[str, str] = {}
    for q in asked_questions or []:
        qid = _attr(q, "question_id") or _attr(q, "id")
        if qid:
            titles[qid] = _attr(q, "title") or _attr(q, "question")
    for k, v in (answers or {}).items():
        if str(k).startswith("_") or not isinstance(v, (str, int, float)) or not str(v).strip():
            continue
        out.append((titles.get(str(k), str(k)), str(v)))
    return out


_RX_QUOTED = re.compile(r"'[^']*'|‘[^’]*’|“[^”]*”|\"[^\"]*\"|「[^」]*」")


#: 질문 하나는 주제 하나 — 순서가 우선순위다. 괄호·따옴표 안의 인용(계약 문구·보충 설명)은 주제가 아니다.
_QUESTION_TOPICS: tuple[tuple[str, str], ...] = (
    ("parking", r"주차장"),
    ("sublease", r"전대|공동\s*사용"),
    ("guarantee", r"연대\s*보증|보증인|보증\s*범위"),
    ("use_change", r"용도\s*변경|인허가"),
    ("restoration", r"원상\s*회복|철거"),
    ("investment", r"투자비|인테리어|시설비"),
)


def _question_topic(q: str) -> str:
    core = re.sub(r"\([^()]*\)|（[^（）]*）", " ", _RX_QUOTED.sub(" ", str(q or "")))
    return next((t for t, rx in _QUESTION_TOPICS if re.search(rx, core)), "")


def _answer_for(qa: list[tuple[str, str]], topic: str) -> str:
    """주제가 같은 질문의 답만 쓴다. 낱말이 스친 질문의 답을 끌어오면 안 된다 — 연대보증 질문이 "(일룸 투자비 한도)"
    를 언급했다고 그 답("임대보증금 한도입니다")을 투자비 안전장치 답으로 인용했다(2026-10-30·11-02 실측, 따옴표 유무와 무관)."""
    for q, a in qa:
        if _question_topic(q) == topic and str(a or "").strip():
            return str(a).strip()
    return ""


# ── 보호수단 추출·평가 ────────────────────────────────────────────────────────

def _beneficiary(sentence: str, pattern: str) -> str:
    m = re.search(pattern, sentence)
    return m.group(1) if m else ""


def build_deal_assessment(
    *,
    clauses: list[Any] | None,
    contract_text: str,
    entity: str = "",
    our_labels: list[str] | None = None,
    review_focus: str = "",
    qa: list[tuple[str, str]] | None = None,
) -> DealAssessment:
    """원문·검토요청·답변으로 거래 전체 판단을 세운다. 확인 못 한 것은 unknowns 로 남긴다."""
    text = str(contract_text or "")
    qa = list(qa or [])
    da = DealAssessment()
    arts = _articles(clauses)
    spans = _spans(arts)
    da.parties = _parties(text, entity, our_labels)
    labels = [p.label for p in da.parties]
    da.nature, da.nature_basis = classify_nature(text, labels)
    us = next((p for p in da.parties if p.is_us), None)
    if not da.nature or us is None:
        return da
    da.our_label, da.our_role = us.label, us.label
    L = lambda lab: _q(lab, text)  # noqa: E731
    lessor = next((p for p in da.parties if "임대인" in p.label), None)
    lessee = next((p for p in da.parties if "임차인" in p.label), None)
    we_tenant = lessee is not None and lessee.is_us
    others = [p for p in da.parties if not p.is_us]

    # 제3자 기능(물상보증·연대보증) — 원문 문형으로
    for p in others:
        if re.search(rf"[“\"]{re.escape(p.label)}[”\"]가\s*물상보증인", text):
            p.functions.append("물상보증인")
        sp = _find(spans, rf"연대하여\s*보증|연대\s*보증")
        if sp and re.search(rf"[“\"]{re.escape(p.label)}[”\"]는\s*다음\s*사항을\s*확약", sp.art.text):
            p.functions.append("연대보증인")

    # 사업 목적
    sp = _find(spans, r"목적이\s*있다|목적으로\s*한다")
    if sp:
        da.purpose.append(_sentence_with(sp.text, r"목적이\s*있다|목적으로\s*한다") or _flat(sp.text)[:160])
    m = re.search(r"([가-힣A-Za-z]{2,12})\s*매장", review_focus or "")
    if m:
        da.purpose.append(f"검토요청: {m.group(0)} 운영(사용자 설명)")

    # 돈의 흐름
    dep_sp = _find(spans, r"보증금은\s*(?:금|₩)")
    deposit = (amounts_in(dep_sp.text) or [None])[0] if dep_sp else None
    if dep_sp and deposit and lessee and lessor:
        da.money_flows.append(MoneyFlow("deposit", "임대보증금", deposit, lessee.label, lessor.label, True,
                                        "계약 종료·명도 시 반환", Evidence(dep_sp.path, _flat(dep_sp.text)[:160])))
    flat = _flat(text)
    installments: dict[str, tuple[int, str]] = {}
    for m in re.finditer(r"(계약금|중도금|잔금)\s*(?:\(\s*\d+\s*%\s*\))?\s*(?:금[^₩\\(]{0,20})?[(（]?\s*[₩\\]\s*([\d,]{6,})\s*[)）]?\s*(\d{2,4}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2})?", flat):
        if m.group(1) not in installments:
            installments[m.group(1)] = (int(m.group(2).replace(",", "")), (m.group(3) or "").replace(" ", ""))
    for k, (amt, due) in installments.items():
        da.money_flows.append(MoneyFlow(k, f"보증금 {k}", amt, lessee.label if lessee else "", lessor.label if lessor else "",
                                        True, due))
    rent_art = next((a for a in arts if re.search(r"임대료|차임", a.title)), None)
    rent = None
    if rent_art:
        cands = [v for s in _sentences(rent_art.text) if not re.search(r"렌트\s*프리|개월분|연체|이율", s)
                 for v in amounts_in(s)]
        rent = cands[0] if cands else None
        if rent and lessee and lessor:
            vat = "부가세 별도" if re.search(r"VAT\s*별도|부가가치세\s*별도", rent_art.text) else ""
            da.money_flows.append(MoneyFlow("rent", "월 임대료", rent, lessee.label, lessor.label, False,
                                            vat, Evidence(rent_art.path, "")))
    m = re.search(r"월\s*임대료\s*(\d+)\s*개월분[^.]{0,40}렌트\s*프리|렌트\s*프리[^.]{0,30}?(\d+)\s*개월", flat)
    rent_free = int(m.group(1) or m.group(2)) if m else 0
    term = re.search(r"(\d{4})년\s*0?(\d{1,2})월\s*0?(\d{1,2})일부터\s*(\d{4})년\s*0?(\d{1,2})월\s*0?(\d{1,2})일\s*\(?\s*(\d+)\s*개월", flat)
    term_months = int(term.group(7)) if term else 0
    cost_sp = _find(spans, r"반반|각\s*50\s*%|절반", need=r"부담")
    if cost_sp:
        da.money_flows.append(MoneyFlow("cost_share", "비용 분담", None, "", "", False, "",
                                        Evidence(cost_sp.path, _sentence_with(cost_sp.text, r"반반|50\s*%|절반"))))

    # 이행 순서
    if term:
        da.sequence.append(f"임대차 기간 {term.group(1)}.{term.group(2)}.{term.group(3)} ~ "
                           f"{term.group(4)}.{term.group(5)}.{term.group(6)} ({term_months}개월)")
    for k, (amt, due) in installments.items():
        da.sequence.append(f"{k} {won(amt)} 지급" + (f" — {due}" if due else ""))
    if rent_free:
        da.sequence.append(f"렌트프리 {rent_free}개월")

    uf = _user_facts(review_focus)
    if uf.get("appraisal"):
        da.user_facts.append(f"감정평가액 {won(uf['appraisal'])} (사용자 제시 · 감정평가서 미확인)")
    if uf.get("senior"):
        da.user_facts.append(f"선순위 근저당 {won(uf['senior'])} (사용자 제시 · 등기부 미확인)")
    if uf.get("auction_concern"):
        da.user_facts.append(f"경락률 우려: “{uf['auction_concern']}” (사용자 설명)")

    # "선순위 담보권이 없음을 보증한다" 는 선순위가 **없다** 는 문장이다 — 부정문은 세지 않는다.
    senior_sp = next((sp for sp in spans
                      if any(re.search(r"선순위\s*(?:담보|근저당|저당)", x) and not re.search(r"없(?:음|다|을|는|이)|아니", x)
                             for x in _sentences(sp.text))), None)
    senior_denied = bool(re.search(r"선순위[^\n.]{0,12}없", (review_focus or "") + " " + text))
    senior_present = (bool(senior_sp) or bool(uf.get("senior"))) and not (senior_denied and not uf.get("senior"))
    real_estate = da.nature == NATURE_REAL_ESTATE_LEASE

    # 보증금 중 질권으로 담보되는 금액(잔금) — 원문 문형
    pledge_sp = _find(spans, r"질권", need=r"예금|예치")
    pledged_amt = None
    if pledge_sp:
        m = re.search(r"잔금\s*상당액", pledge_sp.text)
        if m and "잔금" in installments:
            pledged_amt = installments["잔금"][0]
        else:
            vals = amounts_in(_sentence_with(text, r"질권\s*설정"))
            pledged_amt = vals[0] if vals else None

    prot: list[Protection] = []
    unknowns: list[dict[str, str]] = []

    # 근저당
    mort_sp = _find(spans, r"근저당권")
    mortgage = None
    if mort_sp:
        s = _sentence_with(mort_sp.text, r"근저당권자로|근저당권을")
        holder = _beneficiary(s, r"[“\"]([^”\"]+)[”\"]을\s*근저당권자로")
        mmax = (amounts_in(_sentence_with(mort_sp.text, r"채권최고액")) or [None])[0]
        scope = _sentence_with(mort_sp.text, r"피담보채권")
        thirdp = _beneficiary(mort_sp.text, r"[“\"]([^”\"]+)[”\"]가\s*물상보증인")
        secured_portion = (deposit - pledged_amt) if deposit and pledged_amt else (deposit or None)
        ours = bool(holder) and holder == da.our_label
        limits: list[str] = []
        if senior_present:
            limits.append("선순위 담보권이 있어 경매 시 낙찰대금에서 선순위 채권이 먼저 배당된다"
                          + (f"(원문 {senior_sp.path}가 선순위 담보채무를 전제)" if senior_sp else "(사용자 설명)"))
        if mmax:
            limits.append(f"배당은 채권최고액 {won(mmax)} 한도")
        if scope and re.search(r"일체", scope):
            limits.append("피담보채권이 '본 계약에 따른 채권 일체' 라서 손해배상·지연이자도 같은 최고액을 나눠 쓴다")
        limits.append("당해세 등 조세채권·경매비용은 저당권보다 먼저 공제될 수 있다(체납 여부 미확인)")
        timing = _sentence_with(mort_sp.text, r"동시에")
        assess = []
        coverage = ""
        if ours and uf.get("appraisal") and (uf.get("senior") is not None) and mmax:
            need = (uf["senior"] + mmax) / uf["appraisal"]
            rows = []
            for r in (0.8, 0.7, 0.6):
                got = max(0, min(mmax, int(uf["appraisal"] * r) - uf["senior"]))
                rows.append(f"낙찰가율 {int(r * 100)}% → 배당 약 {won(got) if got else '0원'}")
            coverage = (f"사용자 제시 수치로 단순 계산하면 선순위 {won(uf['senior'])} + 우리 최고액 {won(mmax)} = "
                        f"감정가의 약 {need * 100:.0f}% — 낙찰가율이 그 아래면 우리 몫이 줄어든다("
                        + "; ".join(rows) + ", 조세·경매비용 제외)")
            assess.append(coverage)
        verdict = V_CONDITIONAL if senior_present or not ours else V_EFFECTIVE
        if ours and senior_present and uf.get("appraisal") and uf.get("senior") is not None and mmax \
                and (uf["senior"] + mmax) / uf["appraisal"] >= 0.7:
            verdict = V_PARTIAL
        mortgage = Protection(
            key="mortgage", kind="근저당권", label=f"근저당권(채권최고액 {won(mmax)})", ours=ours,
            path=mort_sp.path, quote=s[:220],
            secures=(scope or "보증금 반환채권")[:160],
            against=("임대차 목적물(건물)·대지" + (f" — 대지는 {L(thirdp)}가 물상보증" if thirdp else "")),
            procedure="보증금 반환기(명도 완료) 도래 후 임의경매 신청, 또는 다른 채권자 경매에서 순위에 따라 배당",
            limits=limits,
            insolvency="임대인 회생 시 회생담보권·파산 시 별제권 — 일반채권보다 강하나 실제 회수액은 담보가치 − 선순위",
            verdict=verdict,
            assessment=(f"{'후순위' if senior_present else ''} 근저당으로 보증금 중 {won(secured_portion)} 을 담보하나, "
                        f"{'회수액은 선순위 채권액과 낙찰가에 달려 있어 등기부·감정서 없이 확정할 수 없다' if senior_present else '순위·선순위 채권은 등기부로 확인해야 한다'}"
                        + (". " + coverage if coverage else "")),
            needed_docs=["건물·대지 등기사항전부증명서(선순위 채권최고액·순위·가압류)", "국세·지방세 완납증명(당해세 우선 여부)",
                         "감정평가서"],
            statutes=["민법 제357조(근저당 — 채권최고액 한도)", "민사집행법 제145조(배당 순위)"],
            topics=["deposit"],
        )
        if timing:
            mortgage.conflicts.append(f"설정 시점: “{timing[:80]}” — 계약금 지급과 등기 신청 접수를 맞바꾸지 않으면 그 사이 무담보")
        prot.append(mortgage)
        if thirdp:
            prot.append(Protection(
                key="third_party_collateral", kind="물상보증", label=f"대지 물상보증({L(thirdp)})", ours=ours,
                path=mort_sp.path, quote=_sentence_with(mort_sp.text, r"물상보증인")[:160],
                secures="같은 근저당(공동담보)", against=f"{L(thirdp)} 소유 대지",
                procedure="공동근저당 실행 시 건물과 함께 경매",
                limits=["물상보증인은 담보물 가치 한도에서만 책임 — 개인 재산 전체에 대한 책임이 아니다"],
                verdict=V_CONDITIONAL,
                assessment="대지까지 공동담보로 묶여 담보가치는 높아지나, 근저당과 같은 순위·최고액 한계를 공유한다",
                topics=["deposit", "guarantee"],
            ))

    # 예금질권
    if pledge_sp:
        s = _flat(pledge_sp.text)
        holder = _beneficiary(s, r"[“\"]([^”\"]+)[”\"]에게\s*질권")
        ours = bool(holder) and holder == da.our_label
        have = {
            "제3채무자(은행) 승낙": bool(re.search(r"승낙", s)),
            "확정일자": bool(re.search(r"확정일자", s)),
            "은행 상계권 불행사 확약": bool(re.search(r"상계권\s*불행사", s)),
            "임대인 대출 없는 은행": bool(re.search(r"대출\s*채권이\s*없는", s)),
            "해지·인출 금지": bool(re.search(r"(?:해지|인출)[^.]{0,10}(?:않|금지)", s)),
        }
        redeposit = _sentence_with(pledge_sp.text, r"재예치")
        gap_redeposit = bool(redeposit) and not re.search(r"같은\s*날|동시에|즉시|당일", redeposit)
        missing = [k for k, v in have.items() if not v]
        verdict = V_EFFECTIVE if not missing else (V_WEAK if not have["제3채무자(은행) 승낙"] or not have["확정일자"] else V_PARTIAL)
        limits = []
        if missing:
            limits.append("원문에 없는 요건: " + ", ".join(missing))
        if gap_redeposit:
            limits.append("만기 재예치 때 기존 예금 해지와 새 예금 질권 대항요건(승낙·확정일자) 사이에 공백이 생길 수 있다")
        prot.append(Protection(
            key="deposit_pledge", kind="예금질권", label=f"예금질권({won(pledged_amt)})", ours=ours,
            path=pledge_sp.path, quote=_sentence_with(pledge_sp.text, r"질권을?\s*설정")[:220],
            secures=f"보증금 중 {won(pledged_amt)}", against="임대인 명의 예금반환채권(예치 은행)",
            procedure="보증금 반환기 도래 시 질권자가 은행에 직접 청구(민법 제353조)",
            limits=limits,
            insolvency="임대인 파산 시 별제권 — 대항요건을 갖췄다면 임대인 지급불능에도 회수 가능성이 가장 높은 수단",
            verdict=verdict,
            assessment=("은행 승낙·확정일자·상계권 불행사·인출 금지가 모두 원문에 있어, 실제로 서류를 받으면 임대인 신용과 무관하게 "
                        "작동하는 보호다" if not missing else "대항요건 일부가 원문에 없어 임대인 채권자·은행 상계에 밀릴 수 있다")
                       + (" — 다만 재예치 시점의 공백은 남는다" if gap_redeposit else ""),
            needed_docs=["예치 은행의 질권설정 승낙서(확정일자)", "은행의 상계권 불행사 확약서", "예금 실제 예치 확인(통장 사본)"],
            statutes=["민법 제349조·제450조(지명채권 질권 대항요건)", "민법 제353조(질권자의 직접청구)"],
            topics=["deposit"],
        ))
        if gap_redeposit and ours:
            unknowns.append({"fact": "재예치 시 질권 연속성", "doc": "은행의 재예치·질권 존속 처리 방식 확인",
                             "impact": "공백이 있으면 그 기간 동안 질권 담보분이 무담보가 된다"})

    # 기한도래 간주 + 상계
    setoff_sp = _find(spans, r"상계할\s*수\s*있", need=r"기한이\s*도래|월\s*임대료|차임")
    if setoff_sp:
        lead = next((sp for sp in spans if sp.art is setoff_sp.art and sp.para == setoff_sp.para and not sp.item), setoff_sp)
        s = _flat(lead.text)
        actor = _beneficiary(s, r"[“\"]([^”\"]+)[”\"]은\s*(?:이후\s*)?[^.]{0,30}상계할\s*수")
        ours = bool(actor) and actor == da.our_label
        amt = (amounts_in(s) or [None])[0]
        triggers = [_flat(sp.text) for sp in spans if sp.art is lead.art and sp.para == lead.para and sp.item]
        months = math.ceil(amt / rent) if amt and rent else None
        auction_trigger = any(re.search(r"경매", t) for t in triggers)
        insolv_trigger = any(re.search(r"회생|파산", t) for t in triggers)
        limits = []
        if months:
            limits.append(f"상계 재원은 앞으로 낼 월 임대료뿐 — {won(amt)}을 모두 상계하려면 임대차가 약 {months}개월 더 이어져야 한다")
        if rent_free:
            limits.append(f"렌트프리 {rent_free}개월 동안은 상계할 임대료가 없다")
        if auction_trigger and real_estate and senior_present:
            limits.append("경매로 매각되면 선순위 담보보다 늦은 임차권은 소멸하는 것이 원칙이어서, 매각 후에는 상계할 임대료 자체가 없다"
                          " — 경매개시부터 매각까지의 임대료만큼만 작동")
        if insolv_trigger:
            limits.append("회생절차 개시 후 발생하는 임대료 채무와의 상계는 채무자회생법상 상계 제한에 걸릴 수 있다(법무 확인)")
        exempt = _sentence_with(lead.text, r"해지\s*사유에\s*해당하지\s*않|연체에?\s*해당하지\s*않")
        prot.append(Protection(
            key="setoff", kind="기한이익 상실·상계", label=f"기한도래 간주 + 월 임대료 상계({won(amt)})", ours=ours,
            path=lead.path, quote=s[:220], secures=f"질권으로 담보되지 않는 {won(amt)}" if amt else "보증금 일부",
            against="임대인에게 낼 월 임대료(자기 채무와 맞바꿈)",
            procedure="열거 사유(" + "; ".join(re.sub(r"\s+", " ", t).strip(" .")[:40] for t in triggers[:4])
                      + ") 발생 → 기한 도래 간주 → 이후 임대료와 상계",
            limits=limits,
            insolvency="상대방 지급불능에도 우리가 낼 돈과 맞바꾸므로 현금 회수가 필요 없다 — 단, 맞바꿀 임대료가 남아 있어야 한다",
            conflicts=[f"연체·해지 사유 제외 특칙 있음: “{exempt[:70]}”"] if exempt else [],
            verdict=V_PARTIAL if limits else V_EFFECTIVE,
            assessment=("근저당이 경매에서 부족할 때를 대비한 보완책이지만, 상계는 임대차가 계속될 때만 작동한다. "
                        + (f"{won(amt)} 전액을 상계하려면 약 {months}개월분 임대료가 필요하고, " if months else "")
                        + ("경매로 매각되면 그 이후엔 상계 대상이 없다 — 독립된 회수수단으로 보면 안 된다" if auction_trigger and real_estate else "")),
            needed_docs=["선순위 대출 연체·만기 현황(임대인 금융거래 확인서)"],
            statutes=["민법 제492조(상계의 요건)", "채무자회생법 제144조·제145조(회생절차 중 상계)"],
            topics=["deposit", "investment"],
        ))

    # 대위변제
    sub_sp = _find(spans, r"대신\s*변제")
    if sub_sp:
        s = _flat(sub_sp.text)
        actor = _beneficiary(s, r"[“\"]([^”\"]+)[”\"]은\s*[^.]{0,40}대신\s*변제")
        prot.append(Protection(
            key="subrogation", kind="대위변제", label="선순위 담보채무 대위변제 + 상계", ours=actor == da.our_label,
            path=sub_sp.path, quote=s[:200], secures="경매 방지(영업 지속)",
            against="대신 변제한 금액은 이후 임대료와 상계",
            procedure="임대인이 선순위 이자·원리금 연체 시 우리가 대신 변제 → 법정이자 포함 임대료와 상계",
            limits=["대신 변제한 돈도 임대료로만 회수 — 임대차가 끝나면 회수 수단이 일반채권만 남는다",
                    "대신 변제 한도가 없어 우리 현금 노출이 커질 수 있다"],
            verdict=V_PARTIAL,
            assessment="경매를 막아 영업을 지킬 수 있는 유용한 권리지만, 투입한 돈의 회수는 상계 한계를 그대로 가진다",
            statutes=["민법 제481조(변제자대위)"], topics=["deposit", "investment"],
        ))

    # 연대보증
    g_sp = _find(spans, r"연대하여\s*보증|연대\s*보증한다")
    guarantee = None
    if g_sp:
        s = _flat(g_sp.text)
        guarantor = next((p for p in others if "연대보증인" in p.functions), None)
        g_label = guarantor.label if guarantor else ""
        undefined_caps = [m.group(0) for m in re.finditer(r"\(([^()]*?)한도\)", s)
                          if not amounts_in(m.group(1)) and not re.search(r"\d", m.group(1))]
        uncertain_debt = bool(re.search(r"손해배상채무|일체의\s*채무|모든\s*채무", s))
        fixed_cap = bool(re.search(r"최고액[^.]{0,15}(?:금|₩|\d)", s))
        individual = bool(guarantor and guarantor.person) or bool(re.search(r"연대보증인[\s\S]{0,60}주\s*민", text))
        limits = []
        if uncertain_debt and not fixed_cap:
            limits.append("불확정 채무(손해배상)까지 보증하면서 최고액이 금액으로 특정되지 않았다"
                          + (f" — “{undefined_caps[0]}” 는 금액이 아니다" if undefined_caps else ""))
        limits.append("보증인 재산(이미 물상보증한 대지 외)이 확인되지 않았다 — 보증의 실익은 보증인 자력에 달려 있다")
        verdict = V_WEAK if (uncertain_debt and not fixed_cap) else V_CONDITIONAL
        guarantee = Protection(
            key="joint_guarantee", kind="연대보증", label=f"{L(g_label) if g_label else '제3자'} 연대보증", ours=we_tenant,
            path=g_sp.path, quote=s[:220], secures=s[:120],
            against=(f"{L(g_label)}" + (" 개인" if individual else "")) if g_label else "보증인",
            procedure="주채무(보증금 반환·손해배상) 불이행 시 보증인에게 직접 청구(최고·검색 항변 없음 — 연대보증)",
            limits=limits,
            insolvency="임대인 지급불능에도 보증인 재산으로 회수 가능 — 단 보증인 자력이 있을 때만",
            verdict=verdict,
            assessment=("보증금 반환채무는 금액이 특정되어 있으나, 손해배상 부분은 최고액이 금액으로 정해지지 않아 "
                        "민법 제428조의3에 따라 그 부분 보증의 효력이 다투어질 수 있다" if uncertain_debt and not fixed_cap
                        else "금액이 특정된 연대보증 — 실익은 보증인 재산에 달려 있다"),
            needed_docs=["보증인 재산 현황(부동산 등기사항전부증명서 등)", "보증인 자필 서명·기명날인(민법 제428조의2)"],
            statutes=["민법 제428조의2(보증의 방식)", "민법 제428조의3(근보증 — 최고액 서면 특정)"],
            topics=["guarantee", "investment", "deposit"],
        )
        prot.append(guarantee)

    # 손해배상·위약벌(상대방 귀책 → 우리 손실 보전)
    dmg_sp = None
    for sp in spans:
        t = _flat(sp.text)
        if re.search(r"위약벌|손해를?\s*배상", t) and re.search(r"시설비|투자비|영업손실|인테리어", t):
            dmg_sp = sp
            break
    if dmg_sp:
        s = _flat(dmg_sp.text)
        joint = bool(re.search(r"연대하여", s))
        prot.append(Protection(
            key="damages", kind="손해배상·위약벌", label="상대방 귀책 해지 시 시설비·영업손실 배상", ours=we_tenant,
            path=dmg_sp.path, quote=_sentence_with(dmg_sp.text, r"시설비|영업손실")[:240],
            secures="투자한 시설비와 영업손실", against="임대인" + (" 및 토지소유자(연대)" if joint else ""),
            procedure="상대방 귀책으로 해지한 뒤 금전 청구 — 판결·집행이 필요한 일반채권",
            limits=["청구권일 뿐 담보가 아니다 — 근저당 최고액(보증금과 공유)과 연대보증 한도 밖은 무담보",
                    "이 조항이 쓰이는 상황(경매·회생·파산)이 바로 상대방이 돈을 못 내는 상황이다"],
            insolvency="임대인 지급불능이면 일반 회생·파산채권으로 비율 변제 — 사실상 회수가 어렵다",
            verdict=V_WEAK,
            assessment="배상 약정이 있다는 것이 투자비 회수가 확보됐다는 뜻은 아니다 — 담보·보증으로 받쳐진 범위만 실제 회수를 기대할 수 있다",
            statutes=["민법 제398조(손해배상액의 예정)", "민법 제390조"], topics=["investment"],
        ))

    # 계약금 반환(목적 달성 불능 시)
    ref_sp = _find(spans, r"계약금\s*전액을?\s*(?:즉시\s*)?반환")
    if ref_sp:
        prot.append(Protection(
            key="refund", kind="환급", label="용도변경·불법건축 시 해지 + 계약금 반환", ours=we_tenant,
            path=ref_sp.path, quote=_flat(ref_sp.text)[:200], secures="계약금", against="임대인",
            procedure="해지 통지 후 즉시 반환 청구",
            limits=["반환 대상이 계약금뿐 — 우리가 분담한 용도변경 비용·철거비는 반환 대상이 아니다"] if cost_sp else [],
            insolvency="계약금 반환채권도 근저당 피담보채권('채권 일체')에 포함되면 담보된다",
            verdict=V_EFFECTIVE if not cost_sp else V_PARTIAL,
            assessment="목적 달성 불능(용도변경 실패) 시 해지·계약금 반환이 원문에 있다 — 사용자 의도와 일치",
            topics=["draft", "other"],
        ))

    # 사용권(목적물 밖 제3자 소유 부분) — 승계 범위·공유 관계. 승인 문장마다 따로 본다.
    parking = None
    for use_sp in [sp for sp in spans if re.search(r"사용(?:을)?\s*(?:승인|승낙)한다", _flat(sp.text))]:
        s = _flat(use_sp.text)
        is_parking = "주차장" in s
        obj_name = "주차장" if is_parking else ("토지" if "토지" in s else "목적물 외 부분")
        grantor = _beneficiary(use_sp.art.text, r"[“\"]([^”\"]+)[”\"]는\s*다음\s*사항을\s*확약")
        succ = _sentence_with(use_sp.art.text, r"양수인이[^.]*승계")
        covered = set(re.findall(r"제\s*(\d+)\s*호", succ))
        gap = bool(succ) and bool(use_sp.item) and use_sp.item not in covered
        share = None
        if is_parking:
            for m in re.finditer(r"주차장[^()\n]{0,10}\(\s*([\d.,]+)\s*분의\s*([\d.,]+)\s*\)", text):
                try:
                    share = float(m.group(2).replace(",", "")) / float(m.group(1).replace(",", ""))
                except (ValueError, ZeroDivisionError):
                    share = None
                break
        limits = []
        if gap:
            limits.append(f"양수인 승계 조항이 제{', '.join(sorted(covered))}호만 대상 — 이 {obj_name} 사용 승인(제{use_sp.item}호)은 "
                          "지분·토지가 넘어가면 양수인에게 주장할 근거가 없다")
        limits.append("승인은 승인자 개인과의 채권적 약정 — 등기된 권리가 아니어서 제3자(양수인·다른 공유자)에게 대항하지 못한다")
        if share is not None:
            limits.append(f"승인자의 지분이 약 {share * 100:.1f}%뿐 — 공유물의 특정 부분 사용은 지분 과반수로 정하는 관리 사항이어서"
                          " 다른 공유자가 이의하면 사용이 보장되지 않을 수 있다(민법 제265조)")
        weak = gap or share is not None
        up = Protection(
            key="use_right_parking" if is_parking else f"use_right_{use_sp.item or use_sp.para or 'x'}",
            kind="사용권", label=f"{obj_name} 사용 승인", ours=we_tenant,
            path=use_sp.path, quote=s[:200], secures=f"영업에 필요한 {obj_name} 사용",
            against=f"{L(grantor)}" if grantor else "승인자", procedure="임대차기간 동안 사용(계약상 승인)",
            limits=limits if weak else limits[:0] + [x for x in limits if "채권적" not in x],
            verdict=V_WEAK if weak else V_EFFECTIVE,
            assessment=(f"{obj_name} 사용은 계약으로 승인됐지만, 승인자 지분 양도·다른 공유자 이의에는 무력하다"
                        + (" — 승계 조항이 이 승인을 빠뜨렸다" if gap else "")) if weak else
                       f"{obj_name} 사용 승낙과 양수인 승계가 함께 규정되어 있다",
            needed_docs=(["주차장 부지 등기사항전부증명서(공유자·지분·담보)", "다른 공유자와의 사용 약정 또는 구분소유적 공유 여부"]
                         if is_parking else []),
            statutes=["민법 제265조(공유물의 관리)"] if share is not None else [],
            topics=["parking"] if is_parking else ["continuity"],
        )
        up.conflicts.append(f"승계 조항: “{succ[:80]}”" if succ else "승계 조항 없음")
        prot.append(up)
        if is_parking:
            parking = up
            da._parking_share = share  # type: ignore[attr-defined]
            da._parking_gap = (gap, use_sp, succ)  # type: ignore[attr-defined]
            if re.search(r"주차장", review_focus or "") and re.search(r"담보", review_focus or ""):
                decided = _answer_for(qa, "parking")
                prot.append(Protection(
                    key="parking_collateral", kind="담보가치(미설정)", label="주차장 지분 담보가치", ours=we_tenant,
                    path=use_sp.path, quote=_flat(next((x for x in _sentences(text) if "주차장" in x and "분의" in x), ""))[:160],
                    secures="(담보 미설정)", against="승인자 소유 주차장 지분",
                    procedure="공동담보로 추가 설정 시 지분에 근저당 — 실행은 지분 경매",
                    limits=[("승인자 지분이 약 %.1f%%인 공유지분이라 단독 경매 시 매수 수요가 적어 낙찰가가 낮고" % (share * 100)
                             if share is not None else "공유지분이라 단독 경매 시 낙찰가가 낮고")
                            + " 감정평가에서도 빠져 있어, 추가 담보로 얻는 회수 실익은 제한적이다"],
                    verdict=V_WEAK,
                    assessment=("주차장의 문제는 담보가치가 아니라 사용권이다 — 지분 담보의 실익은 작고(" + (f"사용자 결정: {decided[:30]}" if decided else "담보 설정 여부는 사업부 결정")
                                + "), 영업에 필요한 것은 임대차기간 내내 주차장을 쓸 수 있는 권리다"),
                    topics=["parking"],
                ))

    # 전대 동의
    sub_lease = _find(spans, r"전대")
    if sub_lease and re.search(r"동의", sub_lease.text):
        prot.append(Protection(
            key="sublease_consent", kind="전대 동의", label="계열사 공동사용·전대 사전 동의" if "계열사" in sub_lease.text else "전대 사전 동의",
            ours=we_tenant, path=sub_lease.path, quote=_flat(sub_lease.text)[:160],
            secures="매장 공동사용·전대", against="임대인", procedure="별도 동의 없이 전대 가능(사전 동의)",
            limits=(["'계열사' 의 범위가 정의되어 있지 않다"] if "계열사" in sub_lease.text and not re.search(r"계열회사|정의", sub_lease.text) else []),
            verdict=V_EFFECTIVE, assessment="전대에 대한 임대인의 사전 동의가 원문에 있다(민법 제629조의 동의 요건 충족)",
            statutes=["민법 제629조(임차권의 양도·전대 제한)"], topics=["sublease"],
        ))

    da.protections = prot

    # ── 노출(잃을 수 있는 것) ────────────────────────────────────────────────
    ours_p = [p for p in prot if p.ours]
    if we_tenant and deposit:
        da.exposures.append({"key": "deposit", "label": f"임대보증금 {won(deposit)}",
                             "amount": deposit, "protected_by": [p.label for p in ours_p if "deposit" in p.topics]})
    if we_tenant and real_estate:
        inv_words = re.search(r"인테리어|시설비|투자비", text + " " + str(review_focus or ""))
        if inv_words:
            da.exposures.append({"key": "investment", "label": "매장 투자비(인테리어·시설비) — 금액 원문 미기재",
                                 "amount": None, "protected_by": [p.label for p in ours_p if "investment" in p.topics]})
        da.exposures.append({"key": "continuity", "label": f"영업 지속(임대차 {term_months or '?'}개월)",
                             "amount": None, "protected_by": [p.label for p in ours_p if p.key in ("subrogation",)]})
        if parking:
            da.exposures.append({"key": "use_right", "label": parking.label, "amount": None,
                                 "protected_by": [parking.label]})
    if not we_tenant and lessor and lessor.is_us and rent:
        months = (deposit // rent) if deposit and rent else 0
        da.exposures.append({"key": "rent", "label": f"월 임대료 {won(rent)} 미지급", "amount": rent,
                             "protected_by": [f"보증금 {won(deposit)}(약 {months}개월분) 공제"] if deposit else []})

    # ── 확인되지 않은 사실 ─────────────────────────────────────────────────
    if real_estate:
        unknowns += [
            {"fact": "선순위 채권액·순위·가압류", "doc": "건물·대지 등기사항전부증명서",
             "impact": "근저당 배당 가능액 — 보증금 회수 가능성의 핵심 변수"},
            {"fact": "임대인 조세 체납", "doc": "국세·지방세 완납증명",
             "impact": "당해세는 저당권보다 먼저 배당될 수 있다"},
            {"fact": "건축물 용도·불법건축 여부", "doc": "건축물대장",
             "impact": "용도변경 가능성·해지 사유(불법건축) 판단"},
        ]
    if guarantee:
        unknowns.append({"fact": "보증인 재산", "doc": "보증인 소유 부동산 등기사항전부증명서 등",
                         "impact": "연대보증으로 실제 회수할 수 있는 금액"})
    if parking:
        unknowns.append({"fact": "주차장 공유 관계", "doc": "주차장 부지 등기사항전부증명서·공유자 약정",
                         "impact": "다른 공유자 이의 시 주차장 사용 지속 여부"})
    if we_tenant and real_estate:
        unknowns.append({"fact": "투자비 규모", "doc": "매장 인테리어·시설 투자 예산",
                         "impact": "담보·보증 밖에 남는 무담보 노출 규모"})
    seen = set()
    da.unknowns = [u for u in unknowns if not (u["fact"] in seen or seen.add(u["fact"]))]

    _core_risks(da, text=text, deposit=deposit, pledged_amt=pledged_amt, rent=rent, uf=uf, qa=qa,
                deposit_path=dep_sp.path if dep_sp else "",
                senior_present=senior_present, real_estate=real_estate, we_tenant=we_tenant,
                mortgage=mortgage, guarantee=guarantee, parking=parking, lessor=lessor)
    _closing_checklist(da, text=text, installments=installments, real_estate=real_estate, we_tenant=we_tenant,
                       cost_sp=cost_sp)
    return da


# ── 핵심 위험 ────────────────────────────────────────────────────────────────

def _core_risks(da: DealAssessment, *, text: str, deposit: int | None, pledged_amt: int | None, rent: int | None,
                deposit_path: str,
                uf: dict[str, Any], qa: list[tuple[str, str]], senior_present: bool, real_estate: bool,
                we_tenant: bool, mortgage: Protection | None, guarantee: Protection | None,
                parking: Protection | None, lessor: PartyInfo | None) -> None:
    prot = {p.key: p for p in da.protections}
    out: list[CoreRisk] = []
    if not we_tenant:
        return

    # 1) 보증금 — 담보 부족 또는 담보 회수의 조건성
    secured_by_mortgage = (deposit - pledged_amt) if deposit and pledged_amt else deposit
    if deposit and not mortgage and "deposit_pledge" not in prot and real_estate and deposit >= 10 ** 8:
        out.append(CoreRisk(
            id="deal_deposit_unsecured", title="임대보증금 무담보 — 회수 수단이 임대인 신용뿐",
            category=CAT_PRECHECK, tier="HIGH", topic="deposit", amount=deposit,
            path=deposit_path, article=deposit_path.split()[0] if deposit_path else "",
            event="임대인 재산에 경매·가압류가 들어오거나 임대인이 지급불능",
            failed_protection="보증금 반환을 지키는 근저당·질권·보증이 원문에 없고, 환산보증금이 상가건물 임대차보호법 기준을 넘으면 "
                              "확정일자 우선변제도 기대하기 어렵다",
            loss=f"보증금 {won(deposit)} 전부 또는 일부 미회수",
            action=["체결 전: 건물 등기사항전부증명서로 선순위 채권·가압류 확인",
                    "협상: 보증금 반환채권을 담보할 근저당권·예금질권·보증보험 중 하나 확보",
                    "인도 즉시 사업자등록으로 대항력 확보(상가건물 임대차보호법 제3조)"],
            needed_docs=["건물 등기사항전부증명서", "국세·지방세 완납증명"],
            statutes=["상가건물 임대차보호법 제2조·제3조·제5조(적용범위·대항력·우선변제 — 환산보증금 기준 확인 필요)"],
            as_finding=True,
        ))
    elif mortgage and mortgage.ours and senior_present:
        so = prot.get("setoff")
        months_txt = ""
        if so and rent:
            vals = amounts_in(so.secures)
            if vals:
                months_txt = f"(전액 상계에 약 {math.ceil(vals[0] / rent)}개월분 임대료 필요)"
        partial = mortgage.verdict == V_PARTIAL
        out.append(CoreRisk(
            id="deal_deposit_mortgage_recovery",
            title=f"보증금 근저당 담보분({won(secured_by_mortgage)}) 회수 — 선순위·낙찰가에 좌우",
            category=CAT_PRECHECK, tier="HIGH" if partial or uf.get("auction_concern") else "MEDIUM",
            topic="deposit", amount=secured_by_mortgage, article=mortgage.path.split()[0], path=mortgage.path,
            event="임대인 신용 악화로 선순위 담보권자가 경매를 신청하거나 임대인이 회생·파산",
            failed_protection=("후순위 근저당은 낙찰대금에서 선순위 채권을 뺀 나머지에서만, 채권최고액 한도로 배당받는다. "
                               + (f"상계 특칙({so.path})은 매각으로 임대차가 끝나면 상계할 임대료가 없어 경매 진행 기간의 임대료만큼만 작동한다{months_txt}"
                                  if so else "이를 보완하는 다른 회수 수단이 없다")),
            loss=f"보증금 중 질권으로 담보되지 않은 {won(secured_by_mortgage)}의 전부 또는 일부 미회수",
            action=["체결 전: 건물·대지 등기사항전부증명서로 선순위 채권최고액·순위·가압류 확인",
                    "체결 전: 국세·지방세 완납증명(당해세 우선 여부), 선순위 대출 연체·만기 확인",
                    "계약금 지급은 근저당권설정 등기 신청 접수와 맞바꿔 진행",
                    "확인 결과 부족하면 협상: 질권 비중 확대(계약금 일부도 예치·질권), 채권최고액 상향, 또는 보증보험"],
            needed_docs=list(mortgage.needed_docs),
            statutes=["민법 제357조", "민사집행법 제91조 제3항·제145조(매각에 따른 권리 소멸·배당)"],
            as_finding=True,
        ))
    elif mortgage and mortgage.ours:
        out.append(CoreRisk(
            id="deal_deposit_mortgage_check", title="보증금 근저당 — 순위·담보가치 확인 전 회수 가능성 미확정",
            category=CAT_PRECHECK, tier="MEDIUM", topic="deposit", amount=secured_by_mortgage, path=mortgage.path,
            article=mortgage.path.split()[0],
            event="임대인이 보증금을 반환하지 못해 근저당을 실행",
            failed_protection="등기부를 보기 전에는 우리 근저당의 순위와 선순위 채권액을 알 수 없다",
            loss=f"근저당 담보분 {won(secured_by_mortgage)} 회수액 미확정",
            action=["체결 전: 등기사항전부증명서로 순위·선순위 채권 확인"], needed_docs=list(mortgage.needed_docs),
            as_finding=False,
        ))

    # 2) 예금질권 — 대항요건 누락은 필수, 재예치 공백은 권장
    pl = prot.get("deposit_pledge")
    if pl and pl.ours:
        if pl.verdict == V_WEAK:
            out.append(CoreRisk(
                id="deal_pledge_perfection", title="예금질권 대항요건(은행 승낙·확정일자) 미기재",
                category=CAT_MUST, tier="HIGH", topic="deposit", path=pl.path, article=pl.path.split()[0],
                event="임대인의 다른 채권자가 예금을 압류하거나 은행이 대출채권과 상계",
                failed_protection="제3채무자(은행)의 확정일자 있는 승낙이 없으면 질권을 그들에게 주장할 수 없다",
                loss="질권 담보분 보증금 미회수", action=["원문에 은행의 확정일자 있는 승낙·상계권 불행사 확약을 명시"],
                statutes=["민법 제349조·제450조"],
            ))
        elif any("재예치" in x for x in pl.limits):
            sent = _sentence_with(pl.quote + " " + text, r"재예치").lstrip(") ")
            target = re.search(r"만기\s*시\s*재예치[^.]*?(?:진행한다|한다)", text)
            edit = None
            if target:
                edit = (target.group(0), "만기 시 같은 금융기관에 재예치하되, 기존 예금의 해지와 재예치 및 새 예금에 대한 질권설정"
                                         "(예치 은행의 확정일자 있는 승낙과 상계권 불행사 확약 포함)은 같은 날 진행한다")
            out.append(CoreRisk(
                id="deal_pledge_redeposit_gap", title="예금질권 — 만기 재예치 때 질권 공백",
                category=CAT_SHOULD, tier="MEDIUM", topic="deposit", amount=pledged_amt, path=pl.path,
                article=pl.path.split()[0],
                event="예금 만기에 기존 예금을 해지하고 새로 예치하는 사이 임대인 채권자가 새 예금을 압류",
                failed_protection=f"원문은 '{sent[:40]}…' 로 재질권을 약속할 뿐 같은 날 처리를 요구하지 않아, 새 예금의 대항요건이 갖춰지기 전 공백이 생긴다",
                loss=f"질권 담보분 {won(pledged_amt)} 회수 공백",
                action=["재예치·재질권을 같은 날 처리하도록 문장 보완", "가능하면 자동 재예치(같은 계좌 만기 연장) 상품으로 예치"],
                edit=edit, statutes=["민법 제349조·제450조"],
            ))

    # 3) 연대보증 — 최고액 미특정
    if guarantee and guarantee.ours and guarantee.verdict == V_WEAK:
        ans = _answer_for(qa, "guarantee")
        cap_amt = deposit if re.search(r"보증금\s*한도|임대보증금", ans) else None
        g_text = re.search(r"[^.\n]*연대하여\s*보증한다", text)
        edit = None
        if g_text and cap_amt:
            edit = (g_text.group(0).strip(), g_text.group(0).strip()
                    + f". 이 보증채무의 최고액은 금{_korean_won(cap_amt)}(₩{cap_amt:,})으로 한다")
        elif g_text:
            # 최고액을 사용자가 정하지 않았다 — 금액을 지어내지 않고 빈칸으로 둔 완성 문장을 낸다. 빈칸은 전달본에서
            # "미확정" 으로, 금액 결정은 사업부 결정사항으로 나간다(2026-10-30 지시 5항).
            edit = (g_text.group(0).strip(), g_text.group(0).strip() + ". 이 보증채무의 최고액은 금 [    ]원으로 한다")
        out.append(CoreRisk(
            id="deal_guarantee_max_amount", title="연대보증 — 손해배상 부분 최고액 미특정(효력 다툼 위험)",
            category=CAT_MUST, tier="HIGH", topic="guarantee", path=guarantee.path, article=guarantee.path.split()[0],
            event="임대인이 지급불능이 되어 보증인에게 손해배상(투자비·영업손실)까지 청구",
            failed_protection="보증 범위의 손해배상채무는 최고액이 금액으로 특정되지 않아(“…한도”가 금액이 아님) 근보증 최고액 서면 특정 요건"
                              "(민법 제428조의3)을 못 갖췄다는 항변을 받을 수 있다",
            loss="투자비·영업손실 배상의 보증 회수 불가 — 남는 것은 지급불능 상태의 임대인에 대한 일반채권",
            action=(["보증 문장에 최고액을 금액으로 명시" + (f"(사용자 답변 '임대보증금 한도' → 금 {won(cap_amt)})" if cap_amt else "")]
                    + ["보증인 자필 서명·기명날인 확인, 보증인 재산 확인"]
                    + ([] if cap_amt else ["사업부 판단 필요: 보증 최고액(금액) — 보증금 반환분만 담보할지, 투자비 배상까지 담보할 금액으로 정할지"])),
            edit=edit, conditional=True,
            statutes=["민법 제428조의2", "민법 제428조의3"],
        ))

    # 4) 사용권 — 승계 누락
    if parking and parking.ours and (any("승계" in x for x in parking.limits) or any("공유" in x for x in parking.limits)):
        gap, use_sp, succ = getattr(da, "_parking_gap", (False, None, ""))
        edit = None
        if gap and succ and use_sp is not None:
            m = re.search(r"제\s*(\d+)\s*호의\s*승낙", succ)
            if m:
                edit = (m.group(0), f"{m.group(0)} 및 제{use_sp.item}호의 사용 승인")
        out.append(CoreRisk(
            id="deal_use_right_succession",
            title="주차장 사용권 — " + ("양수인 승계 누락·" if gap else "") + "공유자 동의 미확인",
            category=CAT_SHOULD, tier="MEDIUM", topic="parking", path=parking.path, article=parking.path.split()[0],
            event="승인자가 주차장 지분을 양도하거나 다른 공유자가 사용에 이의",
            failed_protection="승계 조항이 주차장 사용 승인을 빠뜨렸고, 승인은 승인자 개인의 채권적 약정이라 양수인·다른 공유자에게 주장할 수 없다",
            loss="고객 주차장을 쓰지 못해 매장 영업 차질(건물에 자체 주차장이 없는 경우)",
            action=["승계 조항에 주차장 사용 승인을 추가", "체결 전: 주차장 부지 등기부로 공유자·지분 확인, 필요하면 공유자 사용 동의서"],
            needed_docs=list(parking.needed_docs), edit=edit,
            statutes=["민법 제265조"],
        ))

    # 5) 영업 지속·투자비 — 담보로 받쳐지지 않는 부분(수용 여부는 사업부)
    if real_estate and senior_present:
        ans = _answer_for(qa, "investment")
        # "특별히 없습니다" 는 추가 요구가 없다는 답이지 투자비 무담보 위험을 받아들인다는 결정이 아니다 — 위험을 안고 가겠다고
        # 명시했을 때만 수용으로 본다. 아니면 사업부 결정사항으로 남긴다(2026-10-30 지시 4항).
        accepted = bool(ans) and bool(re.search(r"수용|감수|감내|안고\s*가|위험[^.]{0,10}(?:인지|알고)|부담하겠", ans))
        out.append(CoreRisk(
            id="deal_continuity_investment", title="영업 지속·투자비 회수 — 선순위 담보 실행 시 임차권 소멸, 투자비는 무담보",
            category=CAT_ACCEPT if accepted else CAT_PRECHECK, tier="MEDIUM", topic="investment",
            event="선순위 담보권 실행으로 건물이 매각",
            failed_protection="선순위 담보보다 늦은 임차권은 매각으로 소멸하는 것이 원칙이라 매수인에게 영업 계속을 주장할 수 없고, "
                              "시설비·영업손실 배상(위약벌) 약정은 담보 없는 청구권이라 지급불능 상태의 임대인에게서는 회수가 어렵다",
            loss="10년 영업 계획 중단, 미상각 인테리어·시설 투자비 손실(보증금 회수와 별개)",
            action=(["사업부 판단: 추가 담보 없이 수용(사용자 답변: '" + ans[:30] + "')"] if accepted else
                    ["사업부 판단 필요: 투자비 규모 대비 추가 보호(보증 최고액 상향·투자비 상각표 연동 배상) 여부"
                     + (f" — 사용자 답변 '{ans[:30]}' 은 추가 요구가 없다는 뜻으로 보았고, 남는 위험의 수용 여부는 결정되지 않았다"
                        if ans else "")])
            + ["체결 전: 선순위 대출 만기·연체 확인 — 대위변제권(원문)으로 경매를 막을 수 있는지 판단"],
            as_finding=False,
        ))

    da.core_risks = out


def _korean_won(v: int) -> str:
    """500000000 → "오억원"."""
    digits = "영일이삼사오육칠팔구"
    def four(n: int) -> str:
        s = ""
        for unit, d in ((1000, "천"), (100, "백"), (10, "십"), (1, "")):
            q = n // unit % 10
            if q:
                s += ("" if q == 1 and d else digits[q]) + d
        return s
    eok, man, rest = v // 10 ** 8, v // 10 ** 4 % 10 ** 4, v % 10 ** 4
    out = (four(eok) + "억" if eok else "") + (four(man) + "만" if man else "") + four(rest)
    return out + "원"


def _closing_checklist(da: DealAssessment, *, text: str, installments: dict[str, tuple[int, str]],
                       real_estate: bool, we_tenant: bool, cost_sp: _Span | None) -> None:
    out: list[str] = []
    prot = {p.key: p for p in da.protections}
    if "mortgage" in prot and prot["mortgage"].ours and "계약금" in installments:
        out.append("계약금 지급과 근저당권설정 등기 신청 접수를 같은 날 맞바꿔 진행(원문 '계약금 지급과 동시에' 의 실행)")
    if "deposit_pledge" in prot and prot["deposit_pledge"].ours:
        out.append("잔금 전 예치 은행의 질권설정 승낙서(확정일자)·상계권 불행사 확약서 원본 수령")
    if real_estate:
        out.append("건물·대지(및 주차장 부지) 등기사항전부증명서 — 선순위 채권최고액·가압류·소유자 확인")
        out.append("국세·지방세 완납증명 — 당해세 우선 여부")
        out.append("건축물대장 — 현재 용도·위반건축물 표시(용도변경 가능성·해지 사유)")
    if real_estate and we_tenant:
        out.append("인도 즉시 사업자등록(지점) — 상가건물 임대차보호법상 대항력. 환산보증금이 지역 기준을 넘으면 확정일자 우선변제는 "
                   "적용되지 않을 수 있어 담보(근저당·질권)가 실제 회수 수단이다")
    if "parking_collateral" in prot or "use_right_parking" in prot:
        out.append("주차장 부지 등기사항전부증명서로 공유자·지분·담보 확인 — 다른 공유자의 사용 동의(또는 공유자 간 사용 약정) 확보 여부 판단")
    if "joint_guarantee" in prot:
        out.append("연대보증인 자필 서명·기명날인과 보증 최고액 기재 확인(민법 제428조의2·제428조의3)")
    if cost_sp and "refund" in prot:
        out.append("용도변경 실패로 해지할 때 우리가 이미 낸 용도변경 비용 분담분의 반환 여부를 정해 둘지 사업부 판단")
    da.closing_checklist = out


# ── 요청 답변 ────────────────────────────────────────────────────────────────

_TOPIC_RX = (
    ("deposit", r"보증금|근저당|질권|담보"),
    ("guarantee", r"연대\s*보증|보증인|물상\s*보증"),
    ("sublease", r"전대|공동\s*사용|전차"),
    ("investment", r"투자비|인테리어|시설비|안전\s*장치"),
    ("parking", r"주차장"),
    ("other", r"기타|체크|확인\s*사항|유의"),
    ("draft", r"초안|전반|계약서\s*검토|검토\s*요청"),
)


def request_topic(question: str) -> str:
    for key, rx in _TOPIC_RX:
        if re.search(rx, question or ""):
            return key
    return ""


def _prot_line(p: Protection) -> str:
    return f"{p.label}({p.path}) — {p.verdict_label}: {p.assessment}"


def build_request_answers(da: DealAssessment, requests: list[tuple[int, str, list[str]]]) -> list[RequestAnswer]:
    """번호 요청마다 판단 / 근거 / 기존 보호 / 남은 위험 / 필요 조치. 요청 주제에 묶인 것만 쓴다."""
    out: list[RequestAnswer] = []
    da._numbered_requests = [q + ("\n" + "\n".join(d) if d else "") for _, q, d in requests]  # type: ignore[attr-defined]
    if not da.active:
        return out
    prot = da.protections
    risks = da.core_risks
    for idx, q, details in requests:
        topic = request_topic(q)
        sub_topics = {request_topic(d) for d in details} - {""}
        topics = {topic} | sub_topics
        if topic == "draft":
            topics = {"draft"}
        ps = [p for p in prot if p.ours and (set(p.topics) & topics)]
        rs = [r for r in risks if r.topic in topics]
        needed: list[str] = []
        for p in ps:
            needed += [d for d in p.needed_docs if d not in needed]
        for r in rs:
            needed += [d for d in r.needed_docs if d not in needed]
        paths = sorted({p.path for p in ps} | {r.path for r in rs if r.path},
                       key=lambda s: [int(x) for x in re.findall(r"\d+", s)] or [0])

        if topic == "draft":
            cats = {c: [r for r in risks if r.category == c] for c in CATEGORY_ORDER}
            judgment = ("거래 전체 판단: " + ", ".join(f"{c} {len(v)}건" for c, v in cats.items() if v)
                        + " — " + (f"핵심은 {risks[0].title}" if risks else "핵심 위험 없음(자료 확인 전제)"))
            out.append(RequestAnswer(
                idx, q, details, topic, "SUPPLEMENT" if risks else "KEEP", judgment,
                basis=f"{da.nature_label} · 우리 지위 {da.our_role} · " + "; ".join(da.sequence[:4]),
                existing_protection="; ".join(f"{p.label}({p.verdict_label})" for p in prot if p.ours) or "확인된 보호수단 없음",
                residual_risk="; ".join(f"[{r.category}] {r.title}" for r in risks) or "남은 위험 없음(자료 확인 전제)",
                required_action="; ".join(da.closing_checklist[:4]) or "추가 조치 없음",
                needed_documents=[u["doc"] for u in da.unknowns],
                clause_paths=[], core_risk_ids=[r.id for r in risks],
            ))
            continue
        if topic == "other":
            out.append(RequestAnswer(
                idx, q, details, topic, "NEEDS_FACTS" if da.unknowns else "KEEP",
                judgment="체결 전 확인사항 " + str(len(da.closing_checklist)) + "건 — 계약 문언보다 서류·이행 순서가 결론을 좌우한다",
                basis="; ".join(da.sequence) or "이행 순서 원문 확인",
                existing_protection="; ".join(f"{p.label}({p.path})" for p in prot if p.ours and p.verdict == V_EFFECTIVE) or "—",
                residual_risk="; ".join(f"{u['fact']} 미확인 → {u['impact']}" for u in da.unknowns),
                required_action="; ".join(da.closing_checklist),
                needed_documents=[u["doc"] for u in da.unknowns], core_risk_ids=[],
            ))
            continue
        if topic == "sublease":
            sp = [p for p in prot if p.key == "sublease_consent"]
            if sp:
                p = sp[0]
                out.append(RequestAnswer(
                    idx, q, details, topic, "KEEP",
                    judgment="현행 유지 — 임대인의 계열사 공동사용·전대 사전 동의가 이미 있다",
                    basis=f"{p.path}: “{p.quote[:90]}”", existing_protection=_prot_line(p),
                    residual_risk=("; ".join(p.limits) + " — 다툼 소지는 작다") if p.limits else "남은 위험 작음",
                    required_action=("선택: '계열사' 를 '독점규제 및 공정거래에 관한 법률상 계열회사' 로 정의하면 범위 다툼을 줄일 수 있다"
                                     if p.limits else "추가 조치 없음"),
                    clause_paths=[p.path],
                ))
                continue
        if not topic:
            continue  # 거래 판단이 다루지 않는 주제 — 다른 답변기(상거래 요청·자유서술)의 답을 그대로 둔다
        burdens = [p for p in prot if not p.ours and (set(p.topics) & topics)]
        if not ps and not rs and burdens:
            # 우리가 담보·보증을 **제공하는** 쪽이다 — 같은 장치가 우리에게는 보호가 아니라 부담이다(역할 반전).
            out.append(RequestAnswer(
                idx, q, details, topic, "NEEDS_FACTS",
                judgment="우리 측 부담 — 상대방 보호를 위해 우리가 제공하는 담보·약정이다(수용 범위는 사업부 판단)",
                basis="; ".join(f"{p.path} “{p.quote[:70]}”" for p in burdens[:4]),
                existing_protection="우리 보호가 아니라 상대방 보호: " + "; ".join(f"{p.label}({p.path})" for p in burdens),
                residual_risk="\n".join(
                    [f"{p.label}: " + {"mortgage": "목적물·대지에 근저당 등기 — 처분·추가 대출 시 제약",
                                       "deposit_pledge": "예치금 인출·해지 불가 — 그 금액만큼 유동성 묶임",
                                       "setoff": "열거 사유 발생 시 상대방이 임대료를 내지 않고 보증금과 상계 — 임대료 수입 중단",
                                       "subrogation": "상대방의 대위변제 후 임대료 상계 — 임대료 수입 감소",
                                       "joint_guarantee": "보증인(우리 측 관계자)의 개인 책임",
                                       "damages": "우리 귀책 해지 시 시설비·영업손실 배상(위약벌) 부담"}.get(p.key, "부담 내용 확인")
                     for p in burdens]),
                required_action="담보 제공 범위(채권최고액·질권 금액)와 상계 사유를 보증금 범위로 한정했는지 확인; 기한이익 상실 사유가 "
                                "우리 신용 사건에만 걸리는지 확인",
                clause_paths=sorted({p.path for p in burdens}),
            ))
            continue
        if not ps and not rs:
            out.append(RequestAnswer(
                idx, q, details, topic or "unknown", "NEEDS_FACTS",
                judgment="이 요청을 판단할 보호수단·노출을 원문에서 확인하지 못했다",
                basis="원문에 해당 조항 없음", existing_protection="없음",
                residual_risk="판단 불가", required_action="관련 자료·조건을 확인한 뒤 재검토",
                substantive=False,
            ))
            continue
        main = [r for r in rs if r.category in (CAT_MUST, CAT_PRECHECK)]
        if any(r.category == CAT_MUST for r in rs):
            verdict, head = "SUPPLEMENT", "수정 필요"
        elif main:
            verdict, head = "NEEDS_FACTS", "부분 보호 — 체결 전 확인 필요"
        elif rs:
            verdict, head = "SUPPLEMENT", "대체로 작동 — 일부 보완 권고"
        else:
            verdict, head = "KEEP", "현행 보호로 작동(요건 이행 전제)"
        judgment = head + ": " + "; ".join(f"{p.kind} {p.verdict_label}" for p in ps)
        out.append(RequestAnswer(
            idx, q, details, topic, verdict, judgment,
            basis="; ".join(f"{p.path} “{p.quote[:70]}”" for p in ps[:4]),
            existing_protection="\n".join(_prot_line(p) for p in ps),
            residual_risk="\n".join(f"[{r.category}] {r.title}: {loss_path_text(r)}" for r in rs)
            or "; ".join(x for p in ps for x in p.limits[:1]),
            required_action="\n".join(a for r in rs for a in r.action) or "추가 조치 없음",
            needed_documents=needed, clause_paths=paths, core_risk_ids=[r.id for r in rs],
        ))
    return out


def coverage_rows(answers: list[RequestAnswer]) -> list[dict[str, Any]]:
    """기존 user_review_coverage 행 형식 + 다섯 칸."""
    rows = []
    for a in answers:
        rows.append({
            "issue_id": f"deal_request_{a.index}",
            "source": "deal_request",
            "request_index": a.index,
            "original_user_text": a.question + ("\n" + "\n".join(f"- {d}" for d in a.details) if a.details else ""),
            "normalized_issue": a.question,
            "topic": f"deal:{a.topic}",
            "relevant_clause_paths": list(a.clause_paths),
            "answer_clause_paths": list(a.clause_paths),
            "review_status": {"KEEP": "적정", "SUPPLEMENT": "수정 필요", "NEEDS_FACTS": "사실관계 추가확인"}.get(a.verdict, a.verdict),
            "needs_revision": a.verdict == "SUPPLEMENT",
            "conclusion": a.judgment,
            "direct_answer": a.judgment,
            "judgment": a.judgment,
            "basis": a.basis,
            "existing_protection": a.existing_protection,
            "residual_risk": a.residual_risk,
            "required_action": a.required_action,
            "needed_documents": list(a.needed_documents),
            "matched_finding_ids": list(a.core_risk_ids),
            "substantive": a.substantive,
            "proposed_clauses": [],
        })
    return rows


_DEAL_TOPICS = ("deposit", "guarantee", "sublease", "investment", "parking")
#: 자유서술 파서가 검토요청을 문장·쉼표·낱말로 쪼개 만든 행, 지정 조항 행.
_SUPERSEDED_SOURCES = ("explicit_user_request", "user_focus_target", "user_request", "request_context")
STATUS_INCOMPLETE = "REVIEW_INCOMPLETE_UNANSWERED_REQUEST"


def overlay_deal_rows(coverage: list[dict[str, Any]] | None, deal: dict[str, Any] | None) -> list[dict[str, Any]]:
    """요청 답변 행을 coverage 맨 앞에 싣고, 같은 주제를 낱말로만 답한 기존 행은 걷어낸다.

    2026-10-30 실측: 검토요청서의 "신청배경·계약조건" 문장이 요청으로 파싱돼 "주차장 … 판단: 적정 — 관련 조항이
    계약에 존재" 처럼 조항이 있다는 이유만으로 적정 판정을 받았다. 거래 판단이 같은 주제에 답했으면 그 행은 버리고,
    남는 행은 위험 판단이 아니라 "요청서 조건에 대응하는 조항 확인" 으로 낮춰 적는다. UI·DOCX·PDF 가 같은 함수를 쓴다.
    """
    rows_new = [dict(r) for r in (deal or {}).get("request_rows") or [] if isinstance(r, dict)]
    if not rows_new:
        return [dict(r) for r in coverage or [] if isinstance(r, dict)]
    out = list(rows_new)
    answered = {str(r.get("topic") or "").split(":", 1)[-1] for r in rows_new}
    deal_articles = {re.sub(r"\s*제\s*\d+\s*[항호].*$", "", p) for r in rows_new for p in r.get("relevant_clause_paths") or []}
    squash = lambda t: re.sub(r"[\s\-–·•]+", "", str(t or ""))  # noqa: E731
    answered_texts = [squash(r.get("original_user_text")) for r in rows_new]
    unanswered_texts = [squash(t) for t in (deal or {}).get("numbered_requests") or []
                        if not any(squash(t)[:14] in a for a in answered_texts)]

    def _in_numbered(t: str) -> bool:
        # 답한 번호 요청(세부 줄 포함)의 일부인가. 답하지 못한 번호 요청의 일부면 False — 그 행은 남긴다.
        k = squash(t)[:14]
        return bool(k) and any(k in a for a in answered_texts) and not any(k in u for u in unanswered_texts)

    def _background(t: str) -> bool:
        k = squash(t)[:14]
        return bool(k) and not any(k in a for a in answered_texts + unanswered_texts)

    for r in coverage or []:
        if not isinstance(r, dict) or r.get("source") == "deal_request":
            continue
        text = str(r.get("original_user_text") or "")
        src = str(r.get("source") or "")
        if src == "user_focus_target":
            # 지정 조항("제14조 특약으로 진행")은 그 조항을 평가한 번호 요청 답 안에서 다룬다.
            if set(r.get("relevant_clause_paths") or []) & deal_articles:
                continue
        elif src in _SUPERSEDED_SOURCES:
            # 번호 요청이 있으면 번호가 요청이다(v16). 답한 번호 요청의 조각, 같은 주제에 이미 답한 행, 번호 요청 밖의
            # 배경·계약조건 문장을 쪼갠 조각은 걷어낸다 — 조항이 있다는 이유만으로 "적정" 이 붙어 있던 행들이다.
            if (_in_numbered(text) or _background(text)
                    or request_topic(text + " " + str(r.get("normalized_issue") or "")) in answered):
                continue
        row = dict(r)
        if str(row.get("review_status") or "") == "적정" and not row.get("matched_finding_ids"):
            row["source"] = "request_context"
            row["review_status"] = "조건 대응 조항 확인"
            row["conclusion"] = ("요청서에 적힌 계약조건에 대응하는 조항: " + (", ".join(row.get("relevant_clause_paths") or []) or "없음")
                                 + " — 조항이 있다는 것만으로 적정을 판단하지 않는다(위험 판단은 '거래 전체 판단' 참조)")
            row["direct_answer"] = row["conclusion"]
            row["needs_revision"] = False
        out.append(row)
    return out


def completion(deal: dict[str, Any] | None) -> dict[str, Any]:
    """요청마다 실질 답이 있는가 — 없으면 검토완료로 표시하지 않는다."""
    rows = [r for r in (deal or {}).get("request_rows") or [] if isinstance(r, dict)]
    fields = ("judgment", "basis", "existing_protection", "residual_risk", "required_action")
    missing = [str(r.get("normalized_issue") or "") for r in rows
               if not r.get("substantive", True) or not all(str(r.get(k) or "").strip() for k in fields)]
    return {"complete": bool(rows) and not missing, "unanswered": missing, "request_count": len(rows)}


# ── 조항 finding ─────────────────────────────────────────────────────────────

def _statute_row(s: str) -> dict[str, str]:
    """ "민법 제357조(근저당 — 채권최고액 한도)" → 조문·제목을 나눈다(보고서가 "(None)" 을 붙이지 않게)."""
    m = re.match(r"\s*(.+?)\s*\((.+)\)\s*$", s)
    cite, title = (m.group(1), m.group(2)) if m else (s.strip(), "")
    return {"citation": cite, "title": title, "role": "조건부 판단 근거"}


def core_risk_findings(da: DealAssessment, clauses: list[Any] | None) -> list[dict[str, Any]]:
    """조항 finding 으로 내보낼 핵심 위험. 수정문구는 관련 문장만 바꾼다(조 전체 교체 금지)."""
    out: list[dict[str, Any]] = []
    arts = {a.num: a for a in _articles(clauses)}
    for r in da.core_risks:
        if not r.as_finding:
            continue
        num = re.sub(r"\D", "", r.article.split("조")[0]) if r.article else ""
        art = arts.get(num)
        if art is None:
            continue
        original = art.text
        rw = ""
        ri = None
        if r.edit and r.edit[0] and r.edit[0] in original:
            from runtime.review.redline_instruction import build_redline_instruction

            # 고칠 낱말이 아니라 그 낱말이 든 **문장** 을 바꾼다 — 그대로 붙여 넣을 수 있는 완성 문장이어야 하고,
            # 조 전체를 짧은 문장으로 갈아 끼우면 같은 조의 다른 보호(질권·상계·보증)가 사라진다.
            target = next((x for x in re.split(r"(?<=다\.)\s*|\n", original) if r.edit[0] in x), r.edit[0]).strip()
            target = re.sub(r"^\s*(?:\(\d+\)|\d+\.)\s*", "", target)
            target = target.lstrip(") ").strip()
            rw = target.replace(r.edit[0], r.edit[1], 1)
            # 수정 위치는 고칠 문장이 실제로 있는 항·호다 — 보호수단이 있는 호(주차장 승인 제2호)가 아니라 승계 문장이 든
            # 제3호를 고치는데 "제2호 해당 문장 보완" 으로 적혀 위치와 문안이 어긋났다(2026-10-30 실측).
            _host = next((sp for sp in _spans([art]) if sp.text and target[:40] in _flat(sp.text)), None)
            edit_path = _host.path if _host is not None else r.path
            # 수정본은 단락(줄) 하나를 바꾼다 — 조 전체를 원문으로 주면 그 단락 자리에 조 전체가 들어가 중복된다(2026-10-30 실측).
            line = next((ln for ln in original.splitlines() if target in ln), original).strip()
            ri = build_redline_instruction(
                clause_id=r.id, severity=r.tier, edit_location=f"{edit_path} 해당 문장 보완", edit_type="replace",
                target_text=target, replacement_text=rw, original_text=line,
                reason=r.title,
            )
            original = line
        problem = f"{r.event} → {r.failed_protection} → {r.loss}"
        f = {
            "clause_id": r.id, "finding_id": r.id,
            "clause_title": art.title, "display_path": art.path, "article_number": art.num,
            "original_text": original,
            "issue_title": r.title, "detected_issue_list": [{"issue_title": r.title}],
            "problem": problem, "rewrite_reason": problem,
            "legal_business_reason": r.loss,
            "risk_tier": r.tier, "severity": r.tier, "confidence": 0.95,
            "review_category": r.category,
            "loss_path": {"event": r.event, "failed_protection": r.failed_protection, "loss": r.loss},
            "loss_path_text": loss_path_text(r),
            "required_actions": list(r.action), "needed_documents": list(r.needed_docs),
            "conditional_judgment": r.conditional,
            "negotiation_position": " / ".join(r.action[:2]),
            "is_common_legal_risk": True, "is_transaction_package": True, "is_deal_core_risk": True,
            "legal_grounding": {"contract_clauses": [art.path], "statutes": [_statute_row(s) for s in r.statutes],
                                "relations": [], "legal_reason": r.failed_protection, "business_reason": r.loss},
            "suggested_rewrite": rw, "recommendation_text": rw, "proposed_revision": rw,
            "has_rewrite_change": bool(rw),
            "must_fix": r.category == CAT_MUST,
            # 고칠 문장이 없는 핵심 위험(체결 전 확인·사업부 판단)은 조치로 답한다 — 수정본에 적용할 문구가 없다.
            "action_only": not rw,
            "advisory_only": not rw,
            # 기존 "사실확인 선행" 구조와 같은 뜻 — 무엇을 확인할지가 적혀 있어야 완결이다(final_counsel_gate 9항).
            "fact_confirmation_required": r.category if not rw else "",
            "fact_confirmation_items": list(r.action) if not rw else [],
            "review_tier": "MUST" if r.tier == "HIGH" else "SUGGEST",
        }
        if ri:
            f["redline_instruction"] = ri
        out.append(f)
    return out


__all__ = [
    "CAT_ACCEPT", "CAT_MUST", "CAT_PRECHECK", "CAT_SHOULD", "CATEGORY_ORDER", "DealAssessment",
    "NATURE_GOODS_RENTAL", "NATURE_LABELS", "NATURE_REAL_ESTATE_LEASE", "amounts_in", "build_deal_assessment",
    "build_request_answers", "classify_nature", "core_risk_findings", "coverage_rows", "loss_path_text",
    "STATUS_INCOMPLETE", "completion", "overlay_deal_rows",
    "parse_korean_amount", "qa_pairs", "request_topic", "won",
]
