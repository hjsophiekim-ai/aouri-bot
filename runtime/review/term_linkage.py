"""존속·해지·위약금·요금 연결 검토 — 조항 제목이 아니라 '계약에서 어떻게 빠져나오는가' 를 한 흐름으로 읽는다 (2026-11-12).

검토 요청의 '중도해지' 와 '위약금' 은 별개 질문이다.
  ① 중도해지가 가능한가 — 우리에게 사유 없는(임의) 해지권이 있는가, 해지 사유는 무엇인가, 갱신 거절로 끝낼 수 있는가.
  ② 해지하면 얼마를 내는가 — 위약금 산식의 기준 금액을 별지 요금표와 맞춰 실제 금액을 계산하고, 자동 연장 기간 적용·
     종료 정산(이미 이용한 대금)을 함께 본다.
자동갱신(존속) → 해지 사유 → 위약금 → 별지 요금 → 종료 정산을 연결해 읽고, 수정이 필요하면 실제 조에 넣을 완성 문구를
만든다(편집 지시문이 아니라 계약 문장). 회사명·조항 번호는 코드에 없다 — 당사자 호칭·문장 구조·별지 표 줄로 찾는다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_RX_HEAD = re.compile(r"(?m)^\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*(?:[\(（]\s*([^)）\n]{1,40})\s*[\)）])?")
_RX_SIGN_START = re.compile(r"(?m)^\s*(?:\(서명|본\s*계약의\s*체결을\s*증명|위\s*계약을\s*증명|이상의\s*계약|IN WITNESS)")
_RX_ANNEX = re.compile(r"(?m)^\s*(?:\[?\s*별지|별첨|부속\s*서류|Annex|Schedule|Exhibit)\s*\d*")


def _s(v: Any) -> str:
    return str(v or "").strip()


def _ws(v: Any) -> str:
    return " ".join(str(v or "").split())


def _squash(v: Any) -> str:
    return re.sub(r"[\s“”\"'‘’『』「」()（）\[\]]", "", str(v or ""))


def josa(word: str, pair: str) -> str:
    """받침에 맞춘 조사 — pair 는 '이가'·'은는'·'을를'·'과와'·'으로로'."""
    w = re.sub(r"[\s”\"’')）\]』」]+$", "", word or "")
    if not w:
        return pair[1:] if pair != "으로로" else "로"
    ch = w[-1]
    if "가" <= ch <= "힣":
        jong = (ord(ch) - 0xAC00) % 28
        if pair == "으로로":
            return "로" if jong in (0, 8) else "으로"
        return pair[0] if jong else pair[1]
    return pair[1] if pair != "으로로" else "로"


# ── 조·별지 분리 ─────────────────────────────────────────────────────────────

@dataclass
class Article:
    no: str              # "15" 또는 "8의2"
    title: str
    body: str
    path: str            # "제15조"


def art_path(no: str) -> str:
    """"15" → "제15조", "8의2" → "제8조의2"."""
    base, _, sub = str(no).partition("의")
    return f"제{base}조" + (f"의{sub}" if sub else "")


def articles(text: str) -> tuple[list[Article], str]:
    """(본문 조 목록, 별지 이후 텍스트). 서명란 이후 문단은 조 본문에서 뺀다."""
    t = str(text or "")
    sign = _RX_SIGN_START.search(t)
    annex_m = None
    for m in _RX_ANNEX.finditer(t):
        if sign is None or m.start() > sign.start():
            annex_m = m
            break
    body_end = sign.start() if sign else (annex_m.start() if annex_m else len(t))
    annex = t[annex_m.start():] if annex_m else ""
    heads = [m for m in _RX_HEAD.finditer(t[:body_end])]
    out: list[Article] = []
    seen: set[str] = set()
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else body_end
        no = m.group(1) + (f"의{m.group(2)}" if m.group(2) else "")
        line_end = t.find("\n", m.start())
        rest_of_line = t[m.end():line_end if line_end != -1 else end].strip()
        if rest_of_line and not m.group(3):
            # 문장 중간의 "제13조에 따라" 같은 상호참조 줄은 머리글이 아니다
            continue
        if no in seen:
            continue
        seen.add(no)
        body = t[m.end():end].strip()
        out.append(Article(no=no, title=_s(m.group(3)), body=body, path=art_path(no)))
    return out, annex


def units(body: str) -> list[str]:
    """조 본문을 항 단위로 묶는다 — '다음 각 호' 뒤의 번호 줄은 앞 항에 붙인다."""
    lines = [ln.strip() for ln in str(body or "").split("\n") if ln.strip()]
    out: list[str] = []
    for ln in lines:
        if out and re.match(r"^\d+\s*\.\s|^[가-하]\s*\.\s", ln) and re.search(r"다음|각\s*호|아래", out[-1]):
            out[-1] = out[-1] + " " + ln
        elif out and re.match(r"^\(단|^단[,\s]", ln):
            out[-1] = out[-1] + " " + ln
        else:
            out.append(ln)
    return out


def next_number(body: str) -> tuple[str, str]:
    """(다음 항 번호 표지, 번호 형식). 원문의 항 번호 형식을 따른다 — (n) / ① / n. / 없음."""
    lines = [ln.strip() for ln in str(body or "").split("\n") if ln.strip()]
    paren = [int(m.group(1)) for ln in lines for m in [re.match(r"^\((\d+)\)", ln)] if m]
    circ = [_CIRCLED.index(m.group(1)) + 1 for ln in lines for m in [re.match(f"^([{_CIRCLED}])", ln)] if m]
    if paren:
        return f"({max(paren) + 1})", "paren"
    if circ:
        n = max(circ) + 1
        return (_CIRCLED[n - 1] if n <= len(_CIRCLED) else f"({n})"), "circled"
    return "", "none"


def number_style(text: str) -> str:
    t = str(text or "")
    paren = len(re.findall(r"(?m)^\s*\(\d+\)\s", t))
    circ = len(re.findall(f"(?m)^\\s*[{_CIRCLED}]", t))
    return "paren" if paren >= circ and paren else "circled" if circ else "paren"


def label_quote(text: str, label: str) -> str:
    """원문이 당사자 호칭을 따옴표로 감쌌으면 같은 따옴표로 쓴다."""
    if f"“{label}”" in (text or ""):
        return f"“{label}”"
    if f"\"{label}\"" in (text or ""):
        return f"\"{label}\""
    return label


# ── 연결 분석 ────────────────────────────────────────────────────────────────

_RX_RENEW = re.compile(r"자동\s*(?:으로\s*)?(?:연장|갱신)|묵시적\s*(?:으로\s*)?갱신|automatically\s+(?:renew|extend)", re.I)
_RX_TERM = re.compile(r"해지할\s*수\s*있|해지\s*할\s*수\s*있|해제\s*또는\s*해지할\s*수|terminate\s+this", re.I)
_RX_BREACH = re.compile(r"위반|불이행|의무\s*이행|시정|최고|귀책|breach", re.I)
_RX_INSOLV = re.compile(r"파산|회생|청산|해산|부도|지급\s*불능|거래\s*정지|강제\s*집행|가압류|압류|insolven|bankrupt", re.I)
_RX_CONV = re.compile(r"언제든지|임의로|사유\s*(?:와\s*관계\s*)?없이|for\s+convenience|"
                      r"\d+\s*일\s*(?:전|이전)(?:에|까지)?\s*(?:상대방[^.]{0,10})?(?:에게\s*)?(?:서면\s*)?(?:으로\s*)?통지(?:하여|함으로써|로써|로)?[^.]{0,20}해지", re.I)
_RX_PENALTY = re.compile(r"위약금|위약벌|해지\s*수수료|중도\s*해지\s*수수료|early\s+termination\s+fee|liquidated\s+damages", re.I)
_RX_FEE_NOUN = re.compile(r"(?:[가-힣]{1,10}\s)?(?:서비스\s*)?(?:수수료|이용료|사용료|요금|관리비)")
_RX_FEE_CORE = re.compile(r"(?:서비스\s*)?(?:수수료|이용료|사용료|요금|관리비)")
_BOTH = r"(?:상대방\s*당사자|어느\s*(?:한\s*)?당사자|각\s*당사자|일방\s*당사자|당사자\s*(?:일방|쌍방)|쌍방|양\s*당사자)"


@dataclass
class TermUnit:
    path: str
    text: str
    holder: str          # 우리 호칭 / 상대방 호칭 / "양 당사자"
    kind: str            # breach / insolvency / convenience / other


@dataclass
class Fee:
    name: str
    value: str
    free: bool
    line: str


@dataclass
class Linkage:
    active: bool = False
    renewal: dict[str, Any] = field(default_factory=dict)
    terminations: list[TermUnit] = field(default_factory=list)
    our_convenience: list[TermUnit] = field(default_factory=list)
    term_article: str = ""                 # 해지 조
    penalty: dict[str, Any] = field(default_factory=dict)
    fees: list[Fee] = field(default_factory=list)
    settlement: dict[str, Any] = field(default_factory=dict)
    other_payments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def _holder(sentence: str, ours: str, theirs: str) -> str:
    s = sentence
    m_both = re.search(_BOTH + r"\s*(?:은|는|이|가)?", s)
    for lab in (ours, theirs):
        if lab and re.search(rf"[“\"']?{re.escape(lab)}[”\"']?\s*(?:은|는|이|가)\s", s):
            # "위반 당사자가 … 상대방 당사자는 해지" 처럼 주어가 여럿이면 해지 동사 바로 앞의 주어를 쓴다
            before = s[:_RX_TERM.search(s).start()] if _RX_TERM.search(s) else s
            last_lab = max(((before.rfind(x), x) for x in (ours, theirs) if x and x in before), default=(-1, ""))
            last_both = max((m.start() for m in re.finditer(_BOTH, before)), default=-1)
            if last_both > last_lab[0]:
                return "양 당사자"
            return last_lab[1] or lab
    if m_both:
        return "양 당사자"
    return ""


def analyze(text: str, *, ours: str, theirs: str) -> Linkage:
    arts, annex = articles(text)
    lk = Linkage()
    if not arts:
        return lk
    for a in arts:
        for u in units(a.body):
            if not lk.renewal and _RX_RENEW.search(u):
                nd = re.search(r"만료(?:되기|일)?\s*(\d+)\s*일\s*(?:전|이전)", u)
                per = re.search(r"(\d+)\s*(년|개월)", a.body)
                lk.renewal = {"path": a.path, "sentence": _ws(u), "notice_days": int(nd.group(1)) if nd else None,
                              "period": (per.group(1) + per.group(2)) if per else "",
                              "same_terms": bool(re.search(r"동일\s*(?:한\s*)?(?:기간|조건)", u))}
            if _RX_TERM.search(u):
                kind = ("insolvency" if _RX_INSOLV.search(u) else "breach" if _RX_BREACH.search(u)
                        else "convenience" if _RX_CONV.search(u) else "other")
                tu = TermUnit(path=a.path, text=_ws(u), holder=_holder(u, ours, theirs), kind=kind)
                lk.terminations.append(tu)
                if not lk.term_article and re.search(r"해지|해제|termination", a.title or a.body[:40], re.I):
                    lk.term_article = a.no
            if not lk.settlement and re.search(r"(?:종료|해지)[^.]{0,90}정산|정산[^.]{0,60}(?:종료|해지)", u):
                lk.settlement = {"path": a.path, "sentence": _ws(u)}
        if not lk.penalty and _RX_PENALTY.search(a.title + " " + a.body):
            lk.penalty = _penalty(a, ours, theirs)
    if not lk.term_article and lk.terminations:
        lk.term_article = re.sub(r"^제|조$", "", lk.terminations[0].path)
    lk.our_convenience = [t for t in lk.terminations if t.kind == "convenience" and t.holder in (ours, "양 당사자")]
    lk.fees = _fees(annex or text)
    lk.other_payments = _other_payments(text, lk)
    if lk.penalty:
        _bind_fee(lk, text, arts)
    lk.active = bool(lk.penalty or lk.renewal) and bool(lk.terminations or lk.penalty)
    return lk


def _penalty(a: Article, ours: str, theirs: str) -> dict[str, Any]:
    body = a.body
    flat = _ws(body)
    payer = payee = ""
    for x, y in ((ours, theirs), (theirs, ours)):
        if not (x and y):
            continue
        if re.search(rf"{re.escape(y)}[”\"']?\s*(?:은|는|이|가)\s*[“\"']?{re.escape(x)}[”\"']?\s*(?:에게|에)\s*(?:위약금|위약벌)", flat) or \
                re.search(rf"{re.escape(x)}[”\"']?\s*(?:은|는|이|가)\s*[^.]{{0,40}}(?:위약금|위약벌)[^.]{{0,20}}(?:지급|송금|배상)", flat):
            payer, payee = x, y
            break
    trigger = ""
    if re.search(r"임의|사유\s*없이|중도\s*해지|편의|자신의\s*사정", flat):
        trigger = "임의 해지"
    elif re.search(r"귀책|위반", flat):
        trigger = "귀책 해지"
    pct = re.search(r"(\d+(?:\.\d+)?)\s*%", flat)
    months = re.search(r"(?:과거|직전)\s*(?:평균\s*)?(\d+)\s*개월", flat)
    formula = next((_ws(u) for u in units(body) if re.search(r"[x×*]\s*|%|잔여\s*(?:계약\s*)?기간", u) and _RX_FEE_NOUN.search(u)), "")
    fee_nouns = list(dict.fromkeys(_ws(m.group(0)) for m in _RX_FEE_CORE.finditer(formula or flat)))
    return {"path": a.path, "article": a.no, "title": a.title, "text": flat, "body": body, "payer": payer, "payee": payee,
            "trigger": trigger, "pct": float(pct.group(1)) if pct else None, "avg_months": int(months.group(1)) if months else None,
            "remaining_term": bool(re.search(r"잔여\s*(?:계약\s*)?기간", flat)), "formula": formula,
            "fee_nouns": fee_nouns, "applies_to_renewal": bool(_RX_RENEW.search(flat) or re.search(r"연장(?:에\s*따른|된)\s*계약\s*기간", flat)),
            "annex_ref": (re.search(r"별지\s*\d*|별첨\s*\d*", flat).group(0).replace(" ", " ") if re.search(r"별지\s*\d*|별첨\s*\d*", flat) else ""),
            "base_fee": "", "base_fee_value": "", "base_free": None, "undefined_terms": []}


def _fees(annex: str) -> list[Fee]:
    out: list[Fee] = []
    for ln in str(annex or "").split("\n"):
        m = re.match(r"^\s*[■•▪\-*]?\s*([^:：\n]{2,40}?)\s*[:：]\s*(.{1,60})$", ln)
        if not m:
            continue
        name, val = _ws(m.group(1)), _ws(m.group(2))
        if not _RX_FEE_NOUN.search(name):
            continue
        free = bool(re.search(r"무료|면제|무상|^0\s*원|없음", val))
        if not (free or re.search(r"\d", val)):
            continue
        out.append(Fee(name=name, value=val, free=free, line=_ws(ln)))
    return out


def _other_payments(text: str, lk: Linkage) -> list[str]:
    names: list[str] = []
    for m in re.finditer(r"『\s*([^』]{2,30}?)\s*』", text or ""):
        n = _ws(m.group(1))
        if re.search(r"대금|이용료|관리비|요금|수수료", n) and not re.search(r"합계|서비스\s*대금$|명세서|지급기한", n):
            names.append(n)
    for f in lk.fees:
        names.append(f.name)
    return list(dict.fromkeys(names))


def _bind_fee(lk: Linkage, text: str, arts: list[Article]) -> None:
    p = lk.penalty
    sq = _squash(p.get("formula") or p.get("text"))
    base = next((f for f in sorted(lk.fees, key=lambda f: -len(f.name)) if _squash(f.name) in sq), None)
    if base:
        p["base_fee"], p["base_fee_value"], p["base_free"] = base.name, base.value, base.free
    # 산식에 쓰인 요금 명칭 가운데 위약금 조 밖 어디에도 없는 것 — 정의 없는 기준이라 다른 금액으로 읽힐 수 있다
    outside = _squash(" ".join(a.body for a in arts if a.no != p["article"]) + " " + " ".join(f.name for f in lk.fees))
    undefined = []
    for n in p.get("fee_nouns") or []:
        core = n
        if _squash(core) and _squash(core) not in outside and not (base and _squash(core) in _squash(base.name)):
            undefined.append(core)
    p["undefined_terms"] = list(dict.fromkeys(undefined))


# ── 요청 분리·답 ─────────────────────────────────────────────────────────────

_RX_ASK_EXIT = re.compile(r"중도\s*해지|임의\s*해지|해지\s*(?:가|이)?\s*가능|해지할\s*수\s*있|빠져\s*나|중도\s*종료|해지\s*여부|중도해지")
_RX_ASK_COST = re.compile(r"위약금|위약벌|비용|손해\s*배상|얼마|금액|수수료")


def is_termination_request(t: str) -> bool:
    return bool(re.search(r"해지|해제|위약금|위약벌|중도\s*종료|갱신", t or ""))


def split_questions(t: str) -> list[str]:
    """한 요청 안의 '중도해지 가능 여부' 와 '해지 시 위약금·비용' 을 별개 질문으로 나눈다."""
    out = []
    if _RX_ASK_EXIT.search(t or "") or (re.search(r"해지", t or "") and not _RX_ASK_COST.search(t or "")):
        out.append("exit")
    if _RX_ASK_COST.search(t or ""):
        if "exit" not in out and re.search(r"중도|임의|해지\s*시", t or ""):
            out.append("exit")     # 위약금은 해지가 전제다 — 해지 가능 여부를 연결 질문으로 먼저 답한다
        out.append("cost")
    return out or ["exit"]


def _fmt_units(us: list[TermUnit]) -> str:
    return "; ".join(f"{u.path} “{u.text[:70]}”" for u in us)


def answer_exit(lk: Linkage, *, ours: str, theirs: str) -> dict[str, Any]:
    paths = list(dict.fromkeys([t.path for t in lk.terminations] + ([lk.renewal["path"]] if lk.renewal else [])
                               + ([lk.penalty["path"]] if lk.penalty else [])))
    rn = lk.renewal
    renew_txt = ""
    if rn:
        renew_txt = (f"계약기간 만료로 끝내는 방법: {rn['path']}에 따라 만료 {rn['notice_days']}일 전까지 갱신 거절을 통지하면 "
                     f"자동 연장 없이 종료되고 위약금이 생기지 않습니다(통지를 놓치면 {rn.get('period') or '같은 기간'} 자동 연장)."
                     if rn.get("notice_days") else f"{rn['path']}에 자동 연장 조항이 있습니다 — 갱신 거절 통지 기한을 확인해야 합니다.")
    if lk.our_convenience:
        concl = f"가능합니다 — {_fmt_units(lk.our_convenience)}."
        status, need = "적정", False
        action = "유지 — 임의 해지권이 원문에 있음"
    else:
        reasons = [t for t in lk.terminations if t.kind in ("breach", "insolvency")]
        kinds = sorted({"상대방 의무 위반(최고·시정기간 경과 후)" if t.kind == "breach" else "도산·지급불능 사유" for t in reasons})
        concl = (f"{ours}가 사유 없이 계약기간 중 해지할 수 있다는 조항은 없습니다. 해지할 수 있는 경우는 "
                 f"{'·'.join(kinds) or '원문에 정한 사유'}뿐입니다({', '.join(dict.fromkeys(t.path for t in reasons)) or '해지 조항'}).")
        if lk.penalty and lk.penalty.get("trigger") == "임의 해지" and lk.penalty.get("payer") == ours:
            concl += (f" 다만 {lk.penalty['path']}가 ‘{ours}의 임의’ 해지를 전제로 위약금을 정하고 있어, 위약금을 부담하는 조건으로 "
                      f"임의 해지가 예정된 것으로 읽힐 여지는 있으나 통지 기간·방법이 없어 해지 효력을 두고 다툼이 생길 수 있습니다.")
        status, need = "수정 필요", True
        action = (f"수정 필요 — 제{lk.term_article}조에 {ours}의 서면 통지에 의한 임의 해지권을 신설"
                  + (f"하고, {lk.penalty['path']} 위약금 외 추가 책임이 없음을 명시" if lk.penalty else ""))
    if renew_txt:
        concl += " " + renew_txt
    checks = []
    if rn and rn.get("notice_days"):
        checks.append(f"서비스 시작일 기준 만료일과 갱신 거절 통지 기한({rn['notice_days']}일 전) 일정 관리")
    checks.append("운영회사 약관 등 계약서 밖 문서에 별도 해지 제한·해지 수수료가 있는지(계약서와 충돌 시 우선순위)")
    return {"question": "중도해지 가능 여부", "basis": "; ".join(paths), "judgment": concl, "required_action": action,
            "additional_checks": checks, "review_status": status, "needs_revision": need, "answer_clause_paths": paths}


def answer_cost(lk: Linkage, *, ours: str, theirs: str) -> dict[str, Any]:
    p = lk.penalty
    if not p:
        return {"question": "해지 시 위약금·비용", "basis": "위약금 조항 없음",
                "judgment": "계약서에 위약금(해지 수수료) 조항이 없습니다. 해지가 적법하면 별도 위약금은 없고, 종료 시 이미 이용한 대금만 정산합니다."
                            + (f" ({lk.settlement['path']})" if lk.settlement else ""),
                "required_action": "유지", "additional_checks": [], "review_status": "적정", "needs_revision": False,
                "answer_clause_paths": [lk.settlement["path"]] if lk.settlement else []}
    paths = list(dict.fromkeys([p["path"]] + ([lk.renewal["path"]] if lk.renewal and p.get("applies_to_renewal") else [])
                               + ([lk.settlement["path"]] if lk.settlement else [])))
    parts = [f"{p['path']} 산식: “{(p.get('formula') or p['text'])[:160]}”."]
    if p.get("payer"):
        parts.append(f"부담자 {p['payer']}, 청구권자 {p.get('payee') or theirs}, 발생 사유 {p.get('trigger') or '원문 참조'}.")
    amount = ""
    if p.get("base_fee"):
        if p.get("base_free"):
            amount = (f"기준 금액인 {p.get('annex_ref') or '별지'}의 ‘{p['base_fee']}’{josa(p['base_fee'], '이가')} "
                      f"‘{p['base_fee_value']}’이므로 현재 문언대로 계산하면 위약금은 0원입니다.")
        else:
            amount = (f"기준 금액은 {p.get('annex_ref') or '별지'}의 ‘{p['base_fee']}’({p['base_fee_value']})입니다 — "
                      f"해지 직전 {p.get('avg_months') or '일정 기간'}개월 평균액 × 잔여기간"
                      + (f" × {p['pct']:g}%" if p.get("pct") is not None else "") + "로 계산합니다.")
    else:
        amount = "산식의 기준 금액이 별지 요금표의 어느 항목인지 원문으로 특정되지 않습니다."
    parts.append(amount)
    if p.get("undefined_terms"):
        others = [x for x in lk.other_payments if _squash(x) != _squash(p.get("base_fee"))]
        parts.append(f"다만 산식에 계약서 다른 곳에 정의되지 않은 ‘{'’, ‘'.join(p['undefined_terms'])}’라는 표현이 섞여 있어, "
                     + (f"{', '.join(others[:3])} 등 다른 금액을 기준으로 청구될 여지가 있습니다." if others else "기준 금액을 두고 다툼이 생길 수 있습니다."))
    if p.get("applies_to_renewal"):
        parts.append("위약금은 자동 연장된 기간에도 적용됩니다.")
    if lk.settlement:
        parts.append(f"위약금과 별도로 {lk.settlement['path']}에 따라 종료일 기준으로 이미 이용한 대금을 정산해야 합니다.")
    if p.get("base_free") and p.get("base_fee"):
        parts.append(f"요금표가 유상으로 바뀌면(당사자 합의로 변경 가능) 위약금도 그 금액을 기준으로 발생합니다.")
    need = bool(p.get("payer") == ours and (p.get("undefined_terms") or p.get("base_free") or not p.get("base_fee")))
    action = ((f"수정 필요 — {p['path']}에 산정 기준 금액(별지 요금 항목만)·무료 기간 위약금 없음·우리 귀책 아닌 종료 시 위약금 없음·"
               f"위약금 외 추가 배상 없음을 명시") if need else "유지 — 산식이 별지 요금과 일치")
    checks = ["실제 이용 예정 기간 중 요금표(별지) 변경 계획 여부",
              "해지 직전 미정산 이용 대금 규모(위약금과 별도로 정산)"]
    short = (("현재 별지 기준 위약금 0원" if p.get("base_free") and p.get("base_fee") else "기준 금액 확인 필요")
             + (f" — 다만 정의 없는 ‘{'’, ‘'.join(p['undefined_terms'])}’ 기준이 섞여 다른 금액으로 청구될 여지" if p.get("undefined_terms") else "")
             + (", 자동 연장 기간에도 적용" if p.get("applies_to_renewal") else "")
             + (", 이용 대금은 별도 정산" if lk.settlement else "") + ".")
    return {"question": "해지 시 위약금·비용", "basis": "; ".join(paths), "judgment": " ".join(parts), "required_action": action, "short": short,
            "additional_checks": checks, "review_status": "수정 필요" if need else "적정", "needs_revision": need,
            "answer_clause_paths": paths}


# ── 수정 문구 ────────────────────────────────────────────────────────────────

def revisions(lk: Linkage, text: str, *, ours: str, theirs: str, request_asks_exit: bool) -> list[dict[str, Any]]:
    """우리가 위약금을 부담하는 쪽일 때만 — 실제 조에 넣을 완성 문구(항 신설). 편집 지시문은 메모로."""
    if not (lk.active and ours and theirs):
        return []
    arts, _annex = articles(text)
    by_no = {a.no: a for a in arts}
    O, T = label_quote(text, ours), label_quote(text, theirs)
    out: list[dict[str, Any]] = []
    p = lk.penalty
    ours_pays = bool(p and p.get("payer") == ours)
    term_art = by_no.get(lk.term_article)
    if term_art and not lk.our_convenience and (request_asks_exit or (ours_pays and p.get("trigger") == "임의 해지")):
        mark, _st = next_number(term_art.body)
        line = (f"{mark} {O}{josa(ours, '은는')} [30]일 전에 {T}에게 서면으로 통지하여 본 계약을 해지할 수 있다."
                + (f" 이 경우 {O}{josa(ours, '은는')} 제{p['article']}조에서 정한 위약금 외에 해지로 인한 손해배상 책임을 부담하지 아니한다."
                   if ours_pays else "")).strip()
        out.append({"key": "convenience_termination", "article": term_art, "lines": [line],
                    "location": f"{term_art.path} {mark} 신설" if mark else f"{term_art.path} 끝 문단 신설",
                    "issue_title": f"{ours}의 중도(임의) 해지권 명시",
                    "problem": (f"{ours}가 계약기간 중 사유 없이 해지할 수 있는 조항이 없습니다. 해지 사유는 상대방 의무 위반·도산뿐이고"
                                + (f", {p['path']}는 ‘{ours}의 임의’ 해지를 전제로 위약금만 정하고 있어 해지 가능 여부와 효력 시점이 불명확합니다."
                                   if ours_pays and p.get("trigger") == "임의 해지" else ".")),
                    "memo": "통지 기간 [30]일은 협의 값입니다. 해지권과 위약금은 별개 문제 — 해지권은 이 조에, 금액은 위약금 조에서 정합니다.",
                    "tier": "MEDIUM"})
    if ours_pays:
        pa = by_no.get(p["article"])
        if pa is not None:
            mark1, st = next_number(pa.body)
            lines = []
            if p.get("base_fee") or p.get("undefined_terms"):
                others = [x for x in lk.other_payments if _squash(x) != _squash(p.get("base_fee"))]
                base = p.get("base_fee") or "별지에 정한 서비스 요금"
                annex = p.get("annex_ref") or "별지"
                s1 = f"{mark1} 본 조의 위약금 산정 기준 금액은 {annex}에 기재된 {base}에 한한다."
                if others:
                    s1 = (f"{mark1} 본 조의 위약금 산정 기준 금액은 {annex}에 기재된 {base}에 한하며, {', '.join(others[:3])} 등 "
                          f"그 밖에 {O}{josa(ours, '이가')} {T}에게 지급하는 금액은 포함하지 아니한다.")
                if p.get("base_free"):
                    s1 += f" {annex}에 따라 {base}{josa(base, '이가')} 무료인 기간에 대하여는 위약금이 발생하지 아니한다."
                lines.append(s1)
            mark2 = _bump(mark1, st, len(lines))
            ta = by_no.get(lk.term_article)
            has_p2 = bool(ta and re.search(r"(?m)^\s*\(2\)", ta.body))
            if lk.term_article and has_p2:
                reason = f"{T}의 의무 위반 또는 {T}에게 발생한 제{lk.term_article}조 제(2)항 각 호의 사유로 {O}{josa(ours, '이가')} 본 계약을 해지하거나"
            elif lk.term_article:
                reason = f"{T}의 의무 위반 등 제{lk.term_article}조에 정한 {T}측 사유로 {O}{josa(ours, '이가')} 본 계약을 해지하거나"
            else:
                reason = f"{T}의 의무 위반으로 {O}{josa(ours, '이가')} 본 계약을 해지하거나"
            s2 = (f"{mark2} {reason} 계약기간 만료 또는 갱신 거절로 본 계약이 종료되는 경우에는 위약금이 발생하지 아니한다. "
                  f"본 조의 위약금은 {O}의 임의 해지로 인한 손해배상액의 예정으로 보며, {T}{josa(theirs, '은는')} 이를 초과하는 손해의 배상을 청구하지 아니한다.")
            lines.append(s2)
            out.append({"key": "penalty_scope", "article": pa, "lines": lines,
                        "location": f"{pa.path} {mark1} 신설" if mark1 else f"{pa.path} 끝 문단 신설",
                        "issue_title": "위약금 산정 기준·적용 범위 명확화",
                        "problem": (f"{p['path']}의 위약금은 {p.get('annex_ref') or '별지'} 요금을 기준으로 하는데"
                                    + (f" 산식에 정의되지 않은 ‘{'’, ‘'.join(p['undefined_terms'])}’가 섞여 있어 다른 금액(이용 대금 등)을 기준으로 청구될 수 있고"
                                       if p.get("undefined_terms") else "")
                                    + (", 현재 요금이 무료라 0원이어야 할 위약금이 문언상 명확하지 않습니다" if p.get("base_free") else "")
                                    + (". 자동 연장 기간에도 적용되며" if p.get("applies_to_renewal") else ".")
                                    + f" {T} 귀책·만료로 끝나는 경우의 위약금 배제와 추가 배상 여부도 정하지 않았습니다."),
                        "memo": "위약금 금액 자체(50% 등 비율)를 낮출지는 협상 판단입니다 — 이 문구는 기준 금액과 적용 범위를 확정합니다.",
                        "tier": "MEDIUM"})
    return out


def _bump(mark: str, style: str, n: int) -> str:
    if not mark or n == 0:
        return mark
    if style == "paren":
        return f"({int(mark.strip('()')) + n})"
    if style == "circled" and mark in _CIRCLED:
        i = _CIRCLED.index(mark) + n
        return _CIRCLED[i] if i < len(_CIRCLED) else f"({i + 1})"
    return mark


def to_findings(revs: list[dict[str, Any]], clauses: list[Any] | None, *, prefix: str = "link") -> list[dict[str, Any]]:
    """수정 문구 → clause_results 항목(조 끝에 항 신설). 조 원문은 추출된 조항에서 가져온다."""
    out = []
    for r in revs:
        a: Article = r["article"]
        host = _host_clause(clauses, a)
        orig = _ws(_attr(host, "text")) if host is not None else _ws(a.body)
        path = f"제{a.no}조"
        added = "\n".join(r["lines"])
        cid = f"{prefix}_{r['key']}__{_attr(host, 'clause_id') or path}"
        tier = r.get("tier", "MEDIUM")
        out.append({
            "clause_id": cid, "clause_title": a.title, "display_path": path, "article_number": a.no.split("의")[0],
            "paragraph_number": "", "original_text": orig, "is_checklist_item": False,
            "risk_tier": tier, "severity": tier, "counsel_severity": tier,
            "review_category": "필수수정" if tier == "HIGH" else "권장수정",
            "issue_title": r["issue_title"], "problem": r["problem"], "rewrite_reason": r["problem"],
            "brief_action": f"{r['location']}: " + " / ".join(x[:60] for x in r["lines"]),
            "brief_risk": r["problem"], "legal_business_reason": r["problem"], "drafting_memo": r.get("memo", ""),
            "suggested_rewrite": added, "recommendation_text": added,
            "has_rewrite_change": True, "has_addition": False, "is_deal_flow_revision": True, "is_linked_revision": True,
            "linked_topic": r["key"],
            "redline_instruction": {"finding_id": cid, "clause_id": cid, "severity": tier, "edit_location": r["location"],
                                    "edit_type": "new_clause" if r.get("new_article") else "insert_after",
                                    "edit_mode": "new_paragraph", "new_paragraph_number": "", "target_text": "",
                                    "replacement_text": added, "final_clause_text": added, "reason": r["problem"]},
            "undecided_terms": [f"{m} — 협의 값" for m in sorted(set(re.findall(r"\[\d+\][가-힣]*", added)))],
        })
    return out


def _attr(c: Any, name: str) -> str:
    return _s(c.get(name) if isinstance(c, dict) else getattr(c, name, ""))


def _host_clause(clauses: list[Any] | None, a: Article) -> Any | None:
    path = a.path
    exact = next((c for c in clauses or [] if _attr(c, "display_path") == path), None)
    if exact is not None:
        return exact
    # 항으로 나뉜 조는 첫 항을 근거 조항으로 쓴다(신설 위치는 조 끝)
    return next((c for c in clauses or [] if _attr(c, "display_path").startswith(path + " ")), None)


__all__ = ["Article", "art_path", "Linkage", "analyze", "answer_cost", "answer_exit", "articles", "is_termination_request", "josa",
           "label_quote", "next_number", "number_style", "revisions", "split_questions", "to_findings", "units"]
