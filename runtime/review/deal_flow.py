"""거래 흐름 선검증 — 우리 역할 확정 → 실제 지급·인도·소유권 흐름 → 상황별 손실 → 숫자 재계산 → 요청별 답 (2026-11-09).

조항별 체크리스트보다 먼저 돈다. 계약마다 다음을 원문 근거와 함께 확정하고, 뒤 단계의 finding·수정안이 이 사실과 어긋나면
수정안 생성을 멈추고 사실관계부터 바로잡는다(프롬프트 주의사항이 아니라 코드 판정).

1. 우리 역할 — 검토 신청서와 계약서의 당사자 표시(서두)·정의·서명란을 대조한다. 법인명·계약상 호칭(갑/을/정의어)·거래 역할을
   근거와 함께 남기고, 브랜드·그룹사명·실제 계약 법인을 구분한다. 같은 법인이라도 계약마다 역할이 다르다(매입=매수인,
   재판매=매도인) — 판단은 이 계약 하나에 묶는다. 상대방 법인명·주소 공란은 역할 불명확과 다르다. 실제 자료가 충돌할 때만
   역할 판단을 보류하고 나머지 검토는 계속한다.
2. 거래 흐름 — 누가 누구에게 무엇을 언제 지급·인도하는지, 검수·소유권·위험 이전 시점을 원문 문장으로 정리한다.
3. 상황별 손실 — 미이행·일부 이행·상대방 지급불능에서 우리가 잃을 수 있는 금액과 권리. 청구권(반환·위약금)이 있다는 것과
   실제 담보·회수 가능성을 구분한다.
4. 숫자·공란 — 금액·환율·비율·차수별 합계·날짜를 다시 계산하고, 세금·증빙·법인 정보·서명권한의 공란과 불일치를 확인사항으로
   남긴다. 원문 오류를 찾아도 어느 숫자가 맞는지 정하지 않는다.
5. 요청별 답 — 근거 조항 → 원문상 결론 → 수정 또는 유지 이유 → 추가 확인사항. 원문이 없는 다른 계약의 요청은
   '원문 미제공으로 조항 효력 판단 보류' 로 두고 확인할 자료·조건만 적는다(다른 계약의 조항으로 대신 답하지 않는다).
6. 수정 지침과 계약 문구 분리 — 본문에는 당사자·발동 조건·의무·기한·불이행 시 조치가 있는 문장만. '담보를 요구한다',
   '세 가지 중 선택' 같은 검토 의견은 메모(drafting_memo)로 옮긴다.

회사명·조항 번호를 코드에 박지 않는다 — 당사자 호칭·역할 명사·문장 구조(주격·여격 조사)로 판단한다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

# ── 공통 ──────────────────────────────────────────────────────────────────────

_PARTY_LABELS = ("갑", "을", "병", "정")
_BUYER_ROLES = ("매수인", "구매자", "구매인", "발주자", "발주인", "수요자", "공급받는자", "공급받는 자", "구매회사",
                "buyer", "purchaser", "customer")
_SELLER_ROLES = ("매도인", "판매자", "판매인", "공급자", "공급인", "공급회사", "seller", "supplier", "vendor")
_NOT_ROLE = re.compile(r"^(?:날인|서명|인|서명\s*또는\s*날인|기명날인|signature|seal)$", re.I)


def _s(v: Any) -> str:
    return str(v or "").strip()


def _ws(v: Any) -> str:
    return " ".join(str(v or "").split())


def _attr(c: Any, name: str) -> str:
    return _s(c.get(name) if isinstance(c, dict) else getattr(c, name, ""))


def _num(s: str) -> float | None:
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _fmt(n: float | None) -> str:
    return "" if n is None else f"{n:,.2f}"


def role_kind(role: str) -> str:
    r = _s(role).lower().replace(" ", "")
    if any(x.replace(" ", "") == r or x.replace(" ", "") in r for x in _BUYER_ROLES):
        return "buyer"
    if any(x.replace(" ", "") == r or x.replace(" ", "") in r for x in _SELLER_ROLES):
        return "seller"
    return ""


ROLE_KO = {"buyer": "매수인", "seller": "매도인"}


# ── 1. 당사자 표시·서명란 ─────────────────────────────────────────────────────

@dataclass
class PartyEntry:
    label: str                       # 계약상 호칭(갑/을/정의어)
    role: str = ""                   # 서두·정의의 역할 명사(매수인 등)
    name: str = ""                   # 서두 법인명(괄호 미확정 표시는 벗긴 값)
    name_provisional: bool = False   # [ ] 안에 적힌 미확정 값
    sign_name: str = ""
    sign_provisional: bool = False
    fields: dict[str, str] = field(default_factory=dict)      # 통일사회신용코드·주소·법정대표자 …
    blank_fields: list[str] = field(default_factory=list)
    signers: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        return [x for x in (self.name, self.sign_name) if x]


_RX_BR = re.compile(r"^\s*\[\s*(.*?)\s*\]\s*$")


def _unbracket(v: str) -> tuple[str, bool]:
    m = _RX_BR.match(v or "")
    if m:
        return m.group(1).strip(), True
    return _s(v), False


_RX_PARTY_LINE = re.compile(
    r"^\s*(?P<label>갑|을|병|정)\s*[（(]\s*(?P<role>[^)）]{1,15})\s*[)）]\s*[:：]\s*(?P<name>.*)$")
_RX_PARTY_LINE2 = re.compile(
    r"^\s*(?P<role>[가-힣 ]{2,8})\s*[（(]\s*(?P<label>갑|을|병|정)\s*[)）]\s*[:：]\s*(?P<name>.*)$")
_RX_PARTY_LINE3 = re.compile(r"^\s*(?P<label>갑|을|병|정)\s*[:：]\s*(?P<name>.+)$")
_RX_HEREINAFTER = re.compile(
    r"(?P<name>[^\n,，(（]{2,60}?)\s*[（(]\s*(?:이하\s*)?[\"“'‘]?(?P<label>갑|을|병|정|[가-힣]{2,6})[\"”'’]?\s*"
    r"(?:이?라\s*(?:한다|함)|라고\s*한다)?\s*[)）]")
_RX_EN_PARTY = re.compile(
    r"(?P<name>[A-Z][^\n(]{2,80}?)\s*\((?:hereinafter\s+)?(?:referred\s+to\s+as\s+)?(?:the\s+)?[\"“](?P<label>[A-Za-z ]{2,20})[\"”]\)")
_RX_FIRST_ARTICLE = re.compile(r"^\s*(?:제\s*1\s*조|Article\s+1\b|1\.\s+[A-Z가-힣])", re.M)
_RX_SIGN_START = re.compile(r"이하\s*본문\s*없음|서명\s*페이지|IN\s+WITNESS|서명란|기명\s*날인")
_RX_FIELD = re.compile(r"(?P<k>[가-힣A-Za-z()（） ]{2,24}?)\s*[:：]\s*(?P<v>\[[^\]]*\]|[^/\n]*)")


_EN_NOT_PARTY = {"agreement", "effective date", "party", "parties", "territory", "products", "product", "services",
                 "confidential information", "term", "intellectual property", "deliverables", "purchase order", "affiliate"}
_RX_EN_DEF = re.compile(
    r"\(\s*(?:hereinafter\s+(?:referred\s+to\s+as\s+|called\s+)?|herein\s+)?(?:the\s+)?[\"“](?P<label>[A-Za-z][A-Za-z ]{1,19})[\"”]\s*\)")


def _en_party_defs(head: str) -> list[tuple[str, str, str]]:
    """영문 서두 'X, a corporation organized … (hereinafter referred to as the "Supplier")' — 여러 줄에 걸친 당사자 정의.

    정의어 앞 구간(직전 ';' / 'between:' / 'and' 경계부터)의 첫 쉼표 앞이 법인명이다. Agreement·Effective Date 같은
    문서 정의어는 당사자가 아니다(2026-11-13 시디즈 영문 공급계약: 'Agreement'·'Effective Date'를 당사자로 읽어 역할 미확정).
    """
    flat = re.sub(r"\s+", " ", head or "")
    out: list[tuple[str, str, str]] = []
    prev_end = 0
    for m in _RX_EN_DEF.finditer(flat):
        label = m.group("label").strip()
        seg = flat[prev_end:m.start()]
        prev_end = m.end()
        if label.lower() in _EN_NOT_PARTY:
            continue
        cut = max(seg.rfind(";"), seg.rfind(":"), seg.lower().rfind(" between "))
        seg = seg[cut + 1:] if cut >= 0 else seg
        seg = re.sub(r"^\s*(?:and|by and between|between)\s+", "", seg.strip(), flags=re.I)
        nm_m = re.match(r"^(?P<n>\[[^\]]*\]|.+?)(?:,\s*(?:a|an)\s+|\s*,\s*(?:organized|incorporated|having)\b|$)", seg)
        name = (nm_m.group("n") if nm_m else seg).strip().strip(",")
        if not name or len(name) > 90:
            continue
        out.append((label, name, m.group(0) if not seg else f"{seg[:60]} … {m.group(0)}"))
    return out


def _split_head_sign(text: str) -> tuple[str, str]:
    m = _RX_FIRST_ARTICLE.search(text)
    head = text[: m.start()] if m else text[:1500]
    sm = None
    for sm in _RX_SIGN_START.finditer(text):
        pass
    sign = text[sm.start():] if sm else text[-1200:]
    return head, sign


_RX_TBL_DEF = re.compile(r"^\s*[（(]\s*이하\s*[\"“'‘]\s*(?P<label>[가-힣A-Za-z]{2,10})\s*[\"”'’]\s*(?:이?라\s*(?:한다|함))?\s*[)）]\s*$")
_TBL_KEYS = {"법인명": "법인명", "상호": "법인명", "회사명": "법인명", "주소": "주소", "소재지": "주소", "대표자": "대표자",
             "대표이사": "대표자", "이메일": "이메일", "사업자등록번호": "사업자등록번호", "세금계산서수취이메일": "세금계산서 수취이메일",
             "세금계산서": "", "수취이메일": "세금계산서 수취이메일", "연락처": "연락처", "담당자": "담당자"}


def _tbl_key(line: str) -> str | None:
    k = re.sub(r"\s", "", line)
    return _TBL_KEYS.get(k) if k in _TBL_KEYS else None


def _parse_table_parties(head: str, sign: str) -> dict[str, PartyEntry]:
    """표 형식 당사자 칸 — '고객회사 / (이하 “고객회사”) / 법인명 / [값] / 주 소 / …' (표가 풀리며 칸이 줄로 남는다).

    값 칸이 비어 있으면 다음 줄이 곧바로 다른 항목명이 된다 — 그 항목은 공란으로 기록한다(2026-11-11 식권 플랫폼 계약)."""
    out: dict[str, PartyEntry] = {}
    lines = [ln.strip() for ln in head.splitlines() if ln.strip()]
    labels: list[str] = []
    for i, ln in enumerate(lines):
        m = _RX_TBL_DEF.match(ln)
        if m:
            labels.append(m.group("label"))

    def _fill(seq: list[str], *, sign_side: bool) -> None:
        cur: PartyEntry | None = None
        i = 0
        while i < len(seq):
            ln = seq[i]
            joined = re.sub(r"\s", "", ln + (seq[i + 1] if i + 1 < len(seq) else ""))
            hit = next((lb for lb in labels if re.sub(r"\s", "", ln) == lb), None)
            if hit is None and i + 1 < len(seq):
                hit2 = next((lb for lb in labels if joined == lb), None)
                if hit2 is not None:
                    hit = hit2
                    i += 1
            if hit is not None:
                cur = out.setdefault(hit, PartyEntry(label=hit, role=hit))
                cur.evidence.append(("서명란" if sign_side else "서두") + f" 표 '{hit}'")
                i += 1
                continue
            if _RX_TBL_DEF.match(ln):
                i += 1
                continue
            key = _tbl_key(ln)
            if cur is not None and key is not None:
                if not key:   # '세금계산서' + '수취이메일' 처럼 두 줄로 나뉜 항목명
                    i += 1
                    continue
                nxt = seq[i + 1] if i + 1 < len(seq) else ""
                val = ""
                if nxt and _tbl_key(nxt) is None and not any(re.sub(r"\s", "", nxt) == lb for lb in labels) \
                        and not re.match(r"^[（(]\s*인\s*[)）]$", nxt) and not _RX_TBL_DEF.match(nxt) \
                        and not any(re.sub(r"\s", "", nxt + (seq[i + 2] if i + 2 < len(seq) else "")) == lb for lb in labels):
                    val = nxt
                    i += 1
                if key == "법인명":
                    if sign_side:
                        cur.sign_name = val
                    else:
                        cur.name = val
                if val:
                    cur.fields.setdefault(key, val)
                elif key not in cur.blank_fields and not (sign_side and key in cur.fields):
                    cur.blank_fields.append(("서명란 " if sign_side else "") + key)
                i += 1
                continue
            if re.match(r"^\s*(?:별지|부속|첨부)", ln):
                cur = None
            i += 1

    if len(labels) >= 2:
        _fill(lines, sign_side=False)
        _fill([ln.strip() for ln in sign.splitlines() if ln.strip()], sign_side=True)
    return out if len(out) >= 2 else {}


def parse_parties(text: str) -> list[PartyEntry]:
    """서두의 당사자 표시와 서명란을 호칭별로 묶는다."""
    head, sign = _split_head_sign(str(text or ""))
    parties: dict[str, PartyEntry] = {}
    order: list[str] = []
    cur: PartyEntry | None = None
    _tbl = _parse_table_parties(head, sign)
    if _tbl:
        return list(_tbl.values())
    for raw in head.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _RX_PARTY_LINE.match(line) or _RX_PARTY_LINE2.match(line)
        if m and not _NOT_ROLE.match(_s(m.group("role"))):
            label = m.group("label")
            name, prov = _unbracket(_s(m.group("name")))
            pe = parties.get(label) or PartyEntry(label=label)
            pe.role = _s(m.group("role"))
            pe.name, pe.name_provisional = name, prov
            pe.evidence.append(f"서두 '{line[:80]}'")
            parties[label] = pe
            if label not in order:
                order.append(label)
            cur = pe
            continue
        if cur is not None and ("/" in line or re.search(r"[:：]", line)) and not _RX_PARTY_LINE3.match(line):
            for fm in _RX_FIELD.finditer(line):
                k = _s(fm.group("k")).strip("/ ")
                v, _prov = _unbracket(_s(fm.group("v")))
                if not k:
                    continue
                cur.fields[k] = v
                if not v:
                    cur.blank_fields.append(k)
            continue
        cur = None if not line.startswith(("통일", "법정", "주소", "담당", "사업자", "대표")) else cur
    if not parties:
        for m in _RX_HEREINAFTER.finditer(head):
            label = m.group("label")
            if label not in _PARTY_LABELS and not role_kind(label):
                continue
            name, prov = _unbracket(_s(m.group("name")).strip("는은이가와과 "))
            pe = parties.get(label) or PartyEntry(label=label)
            pe.name, pe.name_provisional = name, prov
            if role_kind(label):
                pe.role = label
            pe.evidence.append(f"서두 '{m.group(0)[:80]}'")
            parties[label] = pe
            if label not in order:
                order.append(label)
        for label, name, ev in _en_party_defs(head):
            pe = parties.get(label) or PartyEntry(label=label, role=label if role_kind(label) else "")
            pe.name, pe.name_provisional = _unbracket(name)
            pe.evidence.append(f"preamble '{ev[:80]}'")
            parties[label] = pe
            if label not in order:
                order.append(label)
        for m in ([] if parties else _RX_EN_PARTY.finditer(head)):
            label = _s(m.group("label"))
            if label.lower() in _EN_NOT_PARTY:
                continue
            pe = parties.get(label) or PartyEntry(label=label, role=label if role_kind(label) else "")
            pe.name = _s(m.group("name")).strip(", ")
            pe.evidence.append(f"preamble '{m.group(0)[:80]}'")
            parties[label] = pe
            if label not in order:
                order.append(label)
    # 서명란: 호칭별 법인명, 서명자
    sign_lines = [ln.strip() for ln in sign.splitlines() if ln.strip()]
    sig_labels: list[str] = []
    signers: list[str] = []
    for line in sign_lines:
        m = re.match(r"^\s*(?P<label>갑|을|병|정)\s*(?:[（(][^)）]*[)）])?\s*[:：]\s*(?P<name>.*)$", line)
        if m:
            label = m.group("label")
            name, prov = _unbracket(_s(m.group("name")))
            pe = parties.get(label) or PartyEntry(label=label)
            pe.sign_name, pe.sign_provisional = name, prov
            pe.evidence.append(f"서명란 '{line[:80]}'")
            parties[label] = pe
            if label not in order:
                order.append(label)
            sig_labels.append(label)
            continue
        m2 = re.match(r"^.*(?:대표자|수권대표|서명)[^:：]*[:：]\s*(?P<who>[^\s/]{2,30}.*)$", line)
        if m2 and not re.search(r"일자|날짜|date", line, re.I):
            signers.append(_s(m2.group("who")))
    # 영문 서명란: 'SUPPLIER' / 'SIDIZ, INC.' 처럼 정의어 대문자 줄 다음 줄이 법인명
    en_labels = {p.label.upper(): p.label for p in parties.values() if re.fullmatch(r"[A-Za-z ]{2,20}", p.label)}
    for i, line in enumerate(sign_lines[:-1]):
        lab = en_labels.get(line.strip().rstrip(":").upper())
        if lab:
            nxt = sign_lines[i + 1]
            if re.match(r"^(?:Name|Title|Signature|Date|By)\s*:", nxt, re.I):
                continue
            nm, prov = _unbracket(nxt)
            parties[lab].sign_name, parties[lab].sign_provisional = nm, prov
            parties[lab].evidence.append(f"signature block '{line} / {nxt[:60]}'")
    # 서명자 줄은 서명란 법인 줄의 순서대로 붙인다(표가 풀리며 순서만 남는다)
    for label, who in zip(sig_labels, signers):
        parties[label].signers.append(who)
    return [parties[k] for k in order]


# ── 1-2. 검토 신청서 구조 ─────────────────────────────────────────────────────

@dataclass
class RequestContract:
    index: str
    title: str
    side_a: str
    side_b: str
    line: str


@dataclass
class RequestItem:
    index: int
    text: str
    contract: str = ""        # RequestContract.index 또는 ""
    clause_refs: list[str] = field(default_factory=list)
    topic: str = "general"


_RX_REQ_CONTRACT = re.compile(
    r"^\s*(?P<idx>[①②③④⑤⑥⑦⑧⑨⑩]|\d+[.)]|[가-하][.)])?\s*(?P<title>[^()（）\n]{0,40}?(?:계약서?|약정서?|합의서))\s*"
    r"[（(]\s*(?P<a>[^()（）\n]{1,40}?)\s*[-–—~]\s*(?P<b>[^()（）\n]{1,40}?)\s*[)）]")
_RX_BULLET = re.compile(r"^\s*(?:[●•▪■□○◦▶※\-*]+|\d+\)|\(\d+\)|[가-하]\))\s*")
_TOPIC_RX = (
    ("advance", re.compile(r"선급|선지급|선급금|차액\s*반환|회수|말소|청산|지급\s*불능|부도|파산")),
    ("jurisdiction", re.compile(r"관할|법원|중재|분쟁\s*해결|준거법")),
    ("installment", re.compile(r"분할|할부|결제\s*조건|보전\s*장치|담보")),
    ("termination", re.compile(r"해지|위약금|위약벌|중도\s*종료|자동\s*(?:갱신|연장)")),
    ("blanks", re.compile(r"미확정|공란|\[\s*\]|부가세|부가가치세|세율|법인\s*정보|확인\s*중")),
)


def parse_request(request_text: str) -> tuple[list[RequestContract], list[RequestItem], str]:
    """(대상 계약 목록, 요청 항목, 배경 문단). '요청사항' 제목이 있으면 그 아래만 요청으로 본다."""
    text = str(request_text or "")
    text = text.split("[사용자 확인 답변]")[0]
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    start = next((i for i, ln in enumerate(lines) if re.match(r"^\s*(?:■|\[)?\s*요청\s*사항", ln)), None)
    background = "\n".join(lines[:start]) if start is not None else ""
    body = lines[start + 1:] if start is not None else lines
    contracts: list[RequestContract] = []
    items: list[RequestItem] = []
    cur_contract = ""
    cur: RequestItem | None = None
    # 한 줄에 "1. … 2. …" 로 이어 쓴 요청은 번호마다 나눈다(2026-11-12: "1. 중도해지가 가능한지 2. 위약금이 얼마인지")
    split_body: list[str] = []
    for ln in body:
        marks = list(re.finditer(r"(?:(?<=\s)|^)(\d{1,2})[.)]\s", ln))
        nums = [int(m.group(1)) for m in marks]
        if len(marks) >= 2 and nums == list(range(nums[0], nums[0] + len(nums))):
            head = ln[:marks[0].start()].strip()
            if head:
                split_body.append(head)
            for i, m in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(ln)
                split_body.append("- " + ln[m.end():end].strip())
        else:
            split_body.append(ln)
    body = split_body
    for ln in body:
        if not ln.strip():
            continue
        mc = _RX_REQ_CONTRACT.match(ln)
        if mc:
            idx = _s(mc.group("idx")) or str(len(contracts) + 1)
            contracts.append(RequestContract(idx, _s(mc.group("title")), _s(mc.group("a")), _s(mc.group("b")), ln.strip()))
            cur_contract = idx
            cur = None
            continue
        if _RX_BULLET.match(ln) or cur is None:
            cur = RequestItem(index=len(items) + 1, text=_RX_BULLET.sub("", ln, count=1).strip(), contract=cur_contract)
            items.append(cur)
        else:
            cur.text = (cur.text + " " + ln.strip()).strip()
    for it in items:
        it.clause_refs = sorted({f"제{n}조" for n in re.findall(r"제\s*(\d+)\s*조", it.text)}, key=lambda x: int(x[1:-1]))
        head = re.split(r"[:：]", it.text, maxsplit=1)[0]
        it.topic = next((k for k, rx in _TOPIC_RX if rx.search(head)), "") or \
            next((k for k, rx in _TOPIC_RX if rx.search(it.text)), "general")
    return contracts, items, background


def _tokens(s: str) -> list[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z0-9&.\-]{2,}|[가-힣]{2,}", s or "")
    stop = {"계약서", "계약", "주식회사", "유한회사", "co", "ltd", "inc", "trading", "company", "the", "and"}
    return [t for t in toks if t.lower().strip(".") not in stop]


def _contains_token(hay: str, tok: str) -> bool:
    return bool(tok) and tok.lower() in (hay or "").lower()


# ── 1-3. 우리 역할 확정 ────────────────────────────────────────────────────────

ROLE_CONFIRMED = "확정"
ROLE_CONFLICT = "자료 충돌 — 역할 판단 보류"
ROLE_UNKNOWN = "미확정 — 자료 부족"


@dataclass
class RoleResolution:
    status: str = ROLE_UNKNOWN
    our_label: str = ""
    our_role: str = ""                 # 매수인/매도인/역할 명사
    our_role_kind: str = ""            # buyer/seller/""
    our_contract_name: str = ""        # 계약서상 법인명(서두/서명란)
    our_request_name: str = ""         # 신청서 호칭(예: 시디즈 차이나)
    our_group_entity: str = ""         # 그룹 registry 상 법인
    counterparty_label: str = ""
    counterparty_role: str = ""
    counterparty_name: str = ""
    counterparty_blanks: list[str] = field(default_factory=list)
    brand_notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    request_contract: str = ""         # 이 계약에 대응하는 신청서 계약 표시
    parties: list[dict[str, Any]] = field(default_factory=list)
    basis_kind: str = ""               # 원문(서두·서명란) / 요청서 추론(서명란 공란)
    pre_sign_checks: list[str] = field(default_factory=list)   # 서명 전 확인사항(법인명 공란 등)

    @property
    def confirmed(self) -> bool:
        return self.status == ROLE_CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["confirmed"] = self.confirmed
        return d


def _norm_name(s: str) -> str:
    return re.sub(r"주식회사|㈜|\(\s*주\s*\)|有限公司|有限责任公司|co\.?|ltd\.?|inc\.?|limited|[\s()（）.,\-_·\[\]]", "",
                  _s(s), flags=re.I).lower()


def resolve_role(text: str, request_text: str = "", entity: str = "", flow_hint: dict[str, str] | None = None) -> RoleResolution:
    """우리 회사의 계약상 호칭·역할. 근거와 충돌을 함께 남긴다."""
    from runtime.review.group_entities import resolve_entity

    res = RoleResolution()
    parties = parse_parties(text)
    res.parties = [asdict(p) for p in parties]
    if len(parties) < 2:
        res.evidence.append(f"서두·서명란에서 당사자 표시를 {len(parties)}개만 찾음")
    contracts, _items, _bg = parse_request(request_text)
    votes: dict[str, list[str]] = {}

    # (a) 그룹 registry — 서두·서명란 법인명이 계열사인가
    for p in parties:
        for nm in p.names():
            ent = resolve_entity(nm)
            if ent is not None:
                votes.setdefault(p.label, []).append(f"계약서 '{nm}' = 그룹 계열사({ent.name})")
                res.our_group_entity = ent.legal_name_ko or ent.name

    # (b) 검토 신청서의 계약 표시 "(A - B)" — 이 계약에 대응하는 표시를 찾고 상대방 이름이 가리키는 당사자의 반대편이 우리
    title_line = next((ln.strip() for ln in str(text or "").splitlines() if ln.strip()), "")
    best: tuple[int, RequestContract | None] = (0, None)
    for rc in contracts:
        score = 0
        for side in (rc.side_a, rc.side_b):
            for tok in _tokens(side):
                if any(_contains_token(nm, tok) for p in parties for nm in p.names()):
                    score += 3
                elif _contains_token(text, tok):
                    score += 1
        if rc.title and _norm_name(rc.title) and _norm_name(rc.title) in _norm_name(title_line):
            score += 2
        if score > best[0]:
            best = (score, rc)
    rc = best[1]
    if rc is not None:
        res.request_contract = rc.line
        for ours_side, their_side in ((rc.side_a, rc.side_b), (rc.side_b, rc.side_a)):
            hit_their = [p for p in parties if any(_contains_token(nm, t) for nm in p.names() for t in _tokens(their_side))]
            hit_ours = [p for p in parties if any(_contains_token(nm, t) for nm in p.names() for t in _tokens(ours_side))]
            ours_group = resolve_entity(ours_side) is not None
            their_group = resolve_entity(their_side) is not None
            if their_group and not ours_group:
                continue   # 이 방향은 그룹사를 상대방으로 둔다 — 반대 방향을 본다
            if len(hit_their) == 1 and len(parties) == 2:
                other = next(p for p in parties if p.label != hit_their[0].label)
                votes.setdefault(other.label, []).append(
                    f"검토 신청서 '{rc.line[:60]}': 상대방 '{their_side}' = {hit_their[0].label}"
                    f"({hit_their[0].sign_name or hit_their[0].name}) → 우리 = {other.label}")
                res.our_request_name = ours_side
                break
            if len(hit_ours) == 1:
                votes.setdefault(hit_ours[0].label, []).append(
                    f"검토 신청서 '{rc.line[:60]}': 우리 '{ours_side}' = {hit_ours[0].label}")
                res.our_request_name = ours_side
                break
        if not res.our_request_name:
            # 이름이 원문에 없으면 그룹사 쪽을 신청서 호칭으로만 기록한다(역할은 정하지 않는다)
            res.our_request_name = rc.side_a if resolve_entity(rc.side_a) is not None else ""

    # (c) 화면에서 고른 법인(entity) — 원문 당사자와 일치할 때만 보조 근거
    ent = resolve_entity(entity) if entity else None
    if ent is not None:
        for p in parties:
            if any(resolve_entity(nm) is not None and resolve_entity(nm).key == ent.key for nm in p.names()):
                votes.setdefault(p.label, []).append(f"선택 법인 '{entity}' = {p.label}")

    # (d) 서명란·당사자 칸이 공란인 계약(2026-11-11): 원문 근거가 없을 때만, 요청서가 가리키는 상대방(원문에 이름이 적힌 쪽)의
    #     반대편 — 또는 요청서·선택 법인이 그룹사이고 이름이 적힌 당사자가 그룹사가 아니며 나머지 한쪽이 공란인 경우 그 공란 쪽 —
    #     을 우리로 본다. 정확한 법인명은 정하지 않고 서명 전 확인사항으로 남긴다.
    if not votes and len(parties) == 2:
        filled = [p for p in parties if p.names()]
        blank = [p for p in parties if not p.names()]
        req_l = str(request_text or "")
        our_grp = None
        for cand in [entity] + re.findall(r"[가-힣A-Za-z]{2,12}", req_l):
            if cand and resolve_entity(cand) is not None:
                our_grp = resolve_entity(cand)
                our_grp_word = cand
                break
        if len(filled) == 1 and len(blank) == 1 and all(resolve_entity(n) is None for n in filled[0].names()):
            cp_hit = any(_contains_token(req_l, t) for n in filled[0].names() for t in _tokens(n) if len(t) >= 2)
            if cp_hit or our_grp is not None:
                why = (f"요청서가 상대방으로 '{filled[0].names()[0]}'({filled[0].label})를 가리킴" if cp_hit
                       else f"요청서·선택 법인 '{our_grp_word}'은 그룹사이고 원문에 이름이 적힌 당사자는 '{filled[0].names()[0]}'({filled[0].label})")
                votes.setdefault(blank[0].label, []).append(f"{why} → 우리 = {blank[0].label}(당사자 칸 법인명 공란)")
                res.basis_kind = "요청서 추론(당사자 칸 공란)"
                if our_grp is not None:
                    res.our_request_name = res.our_request_name or our_grp_word
                    res.our_group_entity = our_grp.legal_name_ko or our_grp.name
                res.pre_sign_checks.append(
                    f"우리 당사자({blank[0].label}) 법인명·주소·대표자 칸이 공란입니다 — 서명 전 정확한 계약 법인"
                    + (f"(요청서 표기 '{our_grp_word}', 그룹 registry '{our_grp.legal_name_ko or our_grp.name}')" if our_grp else "")
                    + "의 등기 법인명을 확인해 기재하십시오.")
    labels = [k for k in votes if votes[k]]
    if len(labels) == 1:
        res.our_label = labels[0]
    elif len(labels) > 1:
        res.conflicts.append("근거가 서로 다른 당사자를 우리로 가리킴: "
                             + " / ".join(f"{k}: {'; '.join(v)}" for k, v in votes.items()))
    for k, v in votes.items():
        res.evidence.extend(v)

    by_label = {p.label: p for p in parties}
    ours = by_label.get(res.our_label)
    if ours is not None:
        # 같은 호칭의 서두 법인명과 서명란 법인명이 둘 다 확정값인데 서로 다르면 실제 충돌이다
        if ours.name and ours.sign_name and not ours.name_provisional and not ours.sign_provisional \
                and _norm_name(ours.name) != _norm_name(ours.sign_name):
            res.conflicts.append(f"우리 당사자({ours.label}) 서두 법인명 '{ours.name}' ≠ 서명란 '{ours.sign_name}'")
        res.our_contract_name = ours.name or ours.sign_name
        res.our_role = ours.role
        res.our_role_kind = role_kind(ours.role)
        others = [p for p in parties if p.label != ours.label]
        if len(others) == 1:
            cp = others[0]
            res.counterparty_label = cp.label
            res.counterparty_role = cp.role
            res.counterparty_name = cp.sign_name or cp.name
            if not cp.name:
                res.counterparty_blanks.append(f"{cp.label} 서두 법인명 공란" + (
                    f"(서명란 '{cp.sign_name}'{' — 미확정 괄호 표시' if cp.sign_provisional else ''})" if cp.sign_name else ""))
            elif cp.name_provisional:
                res.counterparty_blanks.append(f"{cp.label} 서두 법인명 미확정 괄호 표시('{cp.name}')")
            res.counterparty_blanks.extend(f"{cp.label} {k} 공란" for k in dict.fromkeys(cp.blank_fields))
            if cp.name and cp.sign_name and not cp.name_provisional and not cp.sign_provisional \
                    and _norm_name(cp.name) != _norm_name(cp.sign_name):
                res.conflicts.append(f"상대방({cp.label}) 서두 법인명 '{cp.name}' ≠ 서명란 '{cp.sign_name}'")
            # 같은 그룹 법인이 양쪽에 다 있으면 누가 우리인지 원문으로 정할 수 없다
            g_ours = {resolve_entity(n).key for n in ours.names() if resolve_entity(n)}
            g_cp = {resolve_entity(n).key for n in cp.names() if resolve_entity(n)}
            if g_ours and g_ours & g_cp:
                res.conflicts.append("같은 그룹 법인이 양 당사자 자리에 모두 기재됨")
        # 역할 명사와 실제 흐름(대금을 내는 쪽)이 다르면 충돌
        if flow_hint and res.our_role_kind:
            payer = flow_hint.get("price_payer", "")
            if payer and ((res.our_role_kind == "buyer" and payer != ours.label)
                          or (res.our_role_kind == "seller" and payer == ours.label)):
                res.conflicts.append(f"역할 표시 '{ours.role}'와 원문 대금 지급 방향(지급자: {payer})이 다름")
        if not res.our_role_kind and flow_hint:
            payer = flow_hint.get("price_payer", "")
            if payer:
                res.our_role_kind = "buyer" if payer == ours.label else "seller"
                res.our_role = res.our_role or ROLE_KO[res.our_role_kind] + "(대금 지급 방향으로 판단)"
    # 브랜드·그룹명·실제 계약 법인 구분
    for p in parties:
        for nm in p.names():
            if re.search(r"그룹|GROUP", nm):
                res.brand_notes.append(f"'{nm}'은 그룹 명칭 — 법인이 아니므로 실제 계약 법인 확인")
    brand_hits = sorted(set(re.findall(r"\b([a-zA-Z]{3,})\s*브랜드|([가-힣A-Za-z]{2,})\s*브랜드", str(text or ""))))
    for a, b in brand_hits:
        nm = a or b
        ent_b = resolve_entity(nm)
        if ent_b is not None and nm not in (res.our_contract_name or ""):
            res.brand_notes.append(f"'{nm}'은 상품 브랜드({ent_b.legal_name_ko or ent_b.name} 소유) — 이 계약의 당사자가 아님")
    if entity and ent is not None and res.our_label and ours is not None and ours.names() and not any(
            resolve_entity(n) is not None and resolve_entity(n).key == ent.key for n in (ours.names() if ours else [])):
        res.brand_notes.append(f"화면에서 고른 법인 '{entity}'은 이 계약의 당사자 표시와 다름 — 당사자 판단은 계약서·신청서 기준")
    if res.conflicts and any(c.startswith(("근거가", "우리 당사자", "같은 그룹", "역할 표시")) for c in res.conflicts):
        res.status = ROLE_CONFLICT
    elif res.our_label:
        res.status = ROLE_CONFIRMED
    return res


# ── 2. 거래 흐름 ──────────────────────────────────────────────────────────────

@dataclass
class FlowEvent:
    kind: str            # list_confirm / advance / delivery / inspection / ownership / risk / balance / refund / penalty / liquidation / security / setoff / termination
    path: str
    sentence: str
    actor: str = ""
    to: str = ""
    what: str = ""
    when: str = ""
    pct: float | None = None
    condition: str = ""


_RX_SENT = re.compile(r"[^.。\n]+(?:[.。](?!\d)|$)", re.M)
_RX_SUBNO = re.compile(r"^\s*(\d+\.\d+)\s+")


def clause_rows(clauses: list[Any] | None) -> list[tuple[str, str, str, str]]:
    """(display_path, article_number, title, text) — 조 단위."""
    out = []
    for c in clauses or []:
        p = _attr(c, "display_path")
        t = _attr(c, "text")
        if p and t:
            out.append((p, _attr(c, "article_number"), _attr(c, "title") or _attr(c, "clause_title"), t))
    return out


def _sentences(path: str, text: str) -> list[tuple[str, str]]:
    out = []
    sub = ""
    for line in str(text or "").splitlines():
        m = _RX_SUBNO.match(line)
        if m:
            sub = m.group(1)
            line = line[m.end():]
        for sm in _RX_SENT.finditer(line):
            s = sm.group(0).strip()
            # 서술어로 끝나는 문장만 — 조 제목("위험 및 소유권의 이전")·표 칸은 의무 문장이 아니다
            if len(s) >= 6 and re.search(r"(?:다|함|것)\s*[.。]?$", s):
                out.append((f"{path} {sub}".strip(), s))
    return out


def _subject(sentence: str, labels: list[str]) -> str:
    alt = "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True))
    m = re.search(rf"(?:^|[\s:：,])({alt})\s*(?:은|는|이|가)\s", sentence)
    return m.group(1) if m else ""


def _subject_before(sentence: str, labels: list[str], verb_rx: str) -> str:
    """동사 바로 앞 주어 — "을이 … 발행한 후 …, 갑은 … 잔액을 지급한다" 에서 지급의 주체는 갑이다."""
    vm = None
    for vm in re.finditer(verb_rx, sentence):
        pass
    if vm is None:
        return _subject(sentence, labels)
    alt = "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True))
    cands = [m for m in re.finditer(rf"(?:^|[\s:：,])({alt})\s*(?:은|는|이|가)\s", sentence) if m.start() < vm.start()]
    # 관형절 주어("을이 발행한 세금계산서를 받은 날부터 … 지급한다")는 본 동사의 주어가 아니다(2026-11-12 원자재 납품:
    # 대금을 내는 갑이 매도인으로 뒤집혔다) — 바로 뒤가 '…한/…된/…는 명사' 로 끝나는 주격은 건너뛴다.
    main = [m for m in cands if not re.match(r"[^,.;]{0,30}?[가-힣](?:한|된|던|은|는|할|ㄴ)\s+[가-힣]+(?:을|를|의|에|으로|로|이|가)?\s",
                                             sentence[m.end():]) or sentence[m.end() - 2:m.end()].strip().endswith(("은", "는"))]
    cands = main or cands
    return cands[-1].group(1) if cands else _subject(sentence, labels)


def _recipient(sentence: str, labels: list[str]) -> str:
    alt = "|".join(re.escape(x) for x in sorted(labels, key=len, reverse=True))
    m = re.search(rf"({alt})\s*에게", sentence)
    return m.group(1) if m else ""


@dataclass
class Tranche:
    name: str
    amount: float | None
    when: str


@dataclass
class DealFlow:
    events: list[FlowEvent] = field(default_factory=list)
    tranches: list[Tranche] = field(default_factory=list)
    tranche_total_stated: float | None = None
    tranche_path: str = ""
    total_amount: float | None = None
    total_path: str = ""
    currency: str = ""
    price_payer: str = ""
    price_payee: str = ""
    advance_pct: float | None = None
    advance_path: str = ""
    ownership_to: str = ""
    ownership_when: str = ""
    ownership_path: str = ""
    security_paths: list[str] = field(default_factory=list)
    setoff_paths: list[str] = field(default_factory=list)
    refund_paths: list[str] = field(default_factory=list)
    liquidation_paths: list[str] = field(default_factory=list)
    termination: list[dict[str, str]] = field(default_factory=list)

    def first(self, kind: str) -> FlowEvent | None:
        return next((e for e in self.events if e.kind == kind), None)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_RX_ADV = re.compile(r"선급금|선지급금|계약금|착수금|advance\s+payment|down\s*payment", re.I)
_RX_BAL = re.compile(r"잔금|잔액|잔대금|balance", re.I)
_RX_SECURITY = re.compile(r"보증(?:보험|증권|금)|이행보증|지급보증|연대보증|질권(?:을)?\s*설정|근저당(?:권)?(?:을)?\s*설정"
                          r"|담보(?:를)?\s*(?:제공|설정|교부)|에스크로|신용장|소유권\s*유보|letter\s+of\s+credit|escrow", re.I)


def extract_flow(clauses: list[Any] | None, labels: list[str], text: str = "") -> DealFlow:
    flow = DealFlow()
    labels = [x for x in labels if x] or list(_PARTY_LABELS)
    rows = clause_rows(clauses)
    for path, _art, _title, body in rows:
        for spath, s in _sentences(path, body):
            subj = _subject(s, labels)
            to = _recipient(s, labels)
            neg_security = re.search(r"설정되거나|사실이\s*없|없음을\s*보증", s)
            pays = bool(re.search(r"지급(?:한다|하여야|하며|하고|할\s*의무|하기로)", s))   # '기지급' 같은 명사는 지급 문장이 아니다
            if pays:
                subj = _subject_before(s, labels, r"지급(?:한다|하여야|하며|하고|할\s*의무)") or subj
            if pays and subj and not to and len(labels) == 2 and not re.search(r"지급하지|지급을\s*지연", s):
                to = next(x for x in labels if x != subj)   # 상대 호칭이 생략된 지급 문장("갑은 … 잔액을 지급한다")
            if pays and subj and to and subj != to:
                pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", s)
                obj = re.search(r"(\S+?)(?:을|를|으로|로)\s*(?:[^.\s]+\s*){0,3}지급(?:한다|하여야|하며)", s)
                obj_t = obj.group(1) if obj else ""
                kind = ("penalty" if re.search(r"위약금|지연\s*이자|손해", s) else
                        "balance" if re.search(r"잔금|잔액|잔대금", obj_t) or re.match(r"^\s*잔금", s) else
                        "advance" if _RX_ADV.search(obj_t) or re.search(r"선급금으로\s*\S+에게\s*지급", s) else
                        "balance" if _RX_BAL.search(s) else "payment")
                when = ""
                wm = re.search(r"([^,]*?(?:후|전|이내|때|까지)[^,]*?)(?:에|,)\s", s)
                if wm:
                    when = wm.group(1).strip()
                flow.events.append(FlowEvent(kind, spath, s, subj, to, "대금" if kind != "penalty" else "위약금", when,
                                             _num(pct_m.group(1)) if pct_m else None))
                if kind in ("advance", "balance", "payment") and not flow.price_payer:
                    flow.price_payer, flow.price_payee = subj, to
                if kind == "advance" and flow.advance_pct is None:
                    flow.advance_pct = _num(pct_m.group(1)) if pct_m else (100.0 if "전액" in s else None)
                    flow.advance_path = spath
            late = bool(re.search(r"지연한\s*경우|지체한\s*경우|위반한\s*경우", s))
            if re.search(r"출고|인도(?:한다|하여|하며)|납품|운송하여|운송한다", s) and subj and kind_ok(s) and not late:
                cond = ""
                cm = re.search(r"([가-힣]+(?:을|를)\s*수령한\s*후|확인을\s*받은\s*후[^,.]*)", s)
                if cm:
                    cond = cm.group(1)
                flow.events.append(FlowEvent("delivery", spath, s, subj, to, "상품", "", None, cond))
            if "검수" in s and re.search(r"검수한다|검수를\s*(?:한다|실시)|검수\s*결과를[^.]*통지", s):
                subj = subj or (re.search(r"(" + "|".join(map(re.escape, labels)) + r")\s*(?:또는|이|가)", s) or [None, ""])[1]
                flow.events.append(FlowEvent("inspection", spath, s, subj, to, "검수"))
            if "소유권" in s and re.search(r"이전|귀속", s):
                rcp = _recipient(s, labels) or (re.search(r"(" + "|".join(map(re.escape, labels)) + r")\s*에\s*귀속", s) or [None, ""])[1]
                wm = re.search(r"소유권(?:은|이)?\s*(.+?(?:때|날|시점|즉시))\s*(?:부터|에)?", s)
                flow.events.append(FlowEvent("ownership", spath, s, "", rcp or "", "소유권", wm.group(1) if wm else ""))
                if rcp and not flow.ownership_to:
                    flow.ownership_to, flow.ownership_path = rcp, spath
                    flow.ownership_when = wm.group(1) if wm else ""
            if "위험" in s and re.search(r"이전|부담", s) and re.search(r"훼손|멸실|위험", s):
                flow.events.append(FlowEvent("risk", spath, s, subj, to, "위험"))
            if "반환" in s and subj and not late:
                flow.events.append(FlowEvent("refund", spath, s, subj, to, (lambda mm: mm.group(1) if mm else "금원")(re.search(r"(차액|수령한\s*모든\s*대금|선급금(?:\s*전액)?|대금)(?:을|를)\s*(?:[^.\s]+\s*){0,2}반환", s))))
                flow.refund_paths.append(spath)
            if re.search(r"청산|말소|해산|파산|注销", s):
                flow.events.append(FlowEvent("liquidation", spath, s, subj, to, "청산"))
                flow.liquidation_paths.append(spath)
            if _RX_SECURITY.search(s) and not neg_security:
                flow.events.append(FlowEvent("security", spath, s, subj, to, "담보"))
                flow.security_paths.append(spath)
            if re.search(r"상계|공제할\s*수", s):
                flow.events.append(FlowEvent("setoff", spath, s, subj, to, "상계"))
                flow.setoff_paths.append(spath)
            if re.search(r"해제|해지", s) and re.search(r"할\s*수\s*있", s):
                trig = re.split(r"경우", s)[0] if "경우" in s else ""
                flow.events.append(FlowEvent("termination", spath, s, subj, to, "해제", "", None, trig))
                flow.termination.append({"path": spath, "who": subj, "trigger": trig.strip()})
            if re.search(r"(?:리스트를|목록을)\s*[^.]{0,20}제공", s) and subj:
                flow.events.append(FlowEvent("list_confirm", spath, s, subj, to, "출고 리스트"))
    _parse_tranches(flow, rows)
    _parse_total(flow, rows)
    return flow


def kind_ok(s: str) -> bool:
    # "출고 리스트" 제공 문장·"출고할 수 있다"(조건)는 인도 의무 문장이 아니다
    return not re.search(r"리스트를|목록을", s)


_RX_AMOUNT = re.compile(r"^\s*([\d,]+\.\d{1,2}|[\d]{1,3}(?:,\d{3})+)\s*$")


def _parse_tranches(flow: DealFlow, rows: list[tuple[str, str, str, str]]) -> None:
    for path, _a, _t, body in rows:
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        trs: list[Tranche] = []
        total = None
        for i, ln in enumerate(lines):
            m = re.match(r"^(\d+)\s*(차|회차|차수)$", ln)
            if m:
                amt = next((_num(x) for x in lines[i + 1:i + 3] if _RX_AMOUNT.match(x)), None)
                when = next((x for x in lines[i + 1:i + 4] if re.search(r"\d{4}\s*년|\d+\s*월", x)), "")
                trs.append(Tranche(f"{m.group(1)}{m.group(2)}", amt, when))
            elif ln in ("합계", "계", "총계", "Total") and i + 1 < len(lines) and _RX_AMOUNT.match(lines[i + 1]):
                total = _num(lines[i + 1])
            else:
                mi = re.match(r"^(\d+)\s*(차|회차)\s*[:：]?\s*([\d,]+(?:\.\d+)?)", ln)
                if mi:
                    trs.append(Tranche(f"{mi.group(1)}{mi.group(2)}", _num(mi.group(3)), ""))
        if len(trs) >= 2:
            flow.tranches, flow.tranche_total_stated, flow.tranche_path = trs, total, path
            return


def _parse_total(flow: DealFlow, rows: list[tuple[str, str, str, str]]) -> None:
    for path, _a, _t, body in rows:
        m = re.search(r"(?:예정\s*)?(?:총액|계약\s*금액|총\s*금액|총\s*대금)[ \t]*(?:은|는)[ \t]*(인민폐|미화|원화|USD|RMB|CNY|KRW)?[ \t]*"
                      r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2}|\d{4,})[ \t]*(위안|원|달러)?", body)
        if m:
            flow.total_amount = _num(m.group(2))
            flow.currency = _s(m.group(1) or m.group(3))
            flow.total_path = path
            return


def stages(flow: DealFlow, role: RoleResolution) -> list[dict[str, str]]:
    """누가 누구에게 무엇을 언제 — 원문 문장 근거. 거래 순서대로."""
    order = ["list_confirm", "advance", "delivery", "inspection", "ownership", "risk", "balance", "payment", "refund", "liquidation"]
    names = {"list_confirm": "출고 목록 제공·확인", "advance": "선급금 지급", "delivery": "출고·인도", "inspection": "검수",
             "ownership": "소유권 이전", "risk": "위험 부담·이전", "balance": "잔금 지급", "payment": "대금 지급",
             "refund": "반환", "liquidation": "청산 시 의무"}

    def who(x: str) -> str:
        if not x:
            return ""
        tag = "우리" if x == role.our_label else ("상대방" if x == role.counterparty_label else "")
        return f"{x}({tag})" if tag else x

    out = []
    seen: set[tuple[str, str]] = set()
    for k in order:
        for e in [e for e in flow.events if e.kind == k]:
            key = (k, e.path)
            if key in seen:
                continue
            seen.add(key)
            what = e.what
            if e.kind == "advance" and e.pct is not None:
                what = f"차수 예정 금액의 {e.pct:g}%" if "차수" in e.sentence else f"{e.pct:g}%"
            if e.kind == "ownership":
                what = "소유권" + ("·위험" if "위험" in e.sentence else "")
            out.append({"step": names[k], "path": e.path, "from": who(e.actor), "to": who(e.to), "what": what,
                        "when": e.when or e.condition or (flow.ownership_when if k == "ownership" else ""),
                        "quote": e.sentence[:160]})
    return out


# ── 3. 상황별 손실 ─────────────────────────────────────────────────────────────

def buyer_advance_exposure(flow: DealFlow, role: RoleResolution) -> bool:
    """우리가 상대방 인도 전에 대금 일부를 먼저 내고, 소유권은 인도·검수 뒤에 우리에게 오는 구조인가."""
    adv = flow.first("advance")
    return bool(role.our_label and adv is not None and adv.actor == role.our_label
                and flow.ownership_to == role.our_label)


def scenarios(flow: DealFlow, role: RoleResolution, answers_text: str = "") -> list[dict[str, Any]]:
    if not buyer_advance_exposure(flow, role):
        return []
    pct = (flow.advance_pct or 0.0) / 100.0
    ours, theirs = role.our_label, role.counterparty_label
    refund = [e for e in flow.events if e.kind == "refund" and e.actor == theirs]
    penalties = [e for e in flow.events if e.kind == "penalty" and e.actor == theirs]
    terms_ours = [t for t in flow.termination if t.get("who") == ours]
    security = list(flow.security_paths)
    setoff = list(flow.setoff_paths)
    liq = list(dict.fromkeys(flow.liquidation_paths))
    rows: list[dict[str, Any]] = []
    tr = [t for t in flow.tranches if t.amount is not None]
    per = [(t.name, t.amount, round((t.amount or 0) * pct, 2)) for t in tr]
    cum = round(sum(x[2] for x in per), 2) if per else (round((flow.total_amount or 0) * pct, 2) if flow.total_amount else None)
    max_one = max((x[2] for x in per), default=None)
    sec_txt = ("담보: " + ", ".join(security)) if security else "담보·보증·상계 장치 없음" if not setoff else "상계: " + ", ".join(setoff)
    refund_txt = ", ".join(sorted({e.path for e in refund})) or "없음"
    pen_txt = ", ".join(sorted({e.path for e in penalties})) or "없음"
    non_delivery_refund = [e for e in refund if re.search(r"출고하지|인도하지|이행하지|미출고|미인도", e.sentence)]
    term_txt = "; ".join(f"{t['path']}({t['trigger'][:40]})" for t in terms_ours) or "없음"
    rows.append({
        "situation": "선급금 지급 후 상대방 미출고(차수별)",
        "loss": (f"차수별 선급금 전액 — " + ", ".join(f"{n} {_fmt(a)}의 {pct * 100:g}% = {_fmt(v)}" for n, a, v in per)
                 + (f"; 한 차수 최대 {_fmt(max_one)}" if max_one is not None else "")) if per else
                (f"선급금 {pct * 100:g}%" + (f" = {_fmt(cum)}" if cum else "")),
        "claims": (f"미출고 시 선급금 반환을 직접 정한 조항: {'있음(' + ', '.join(e.path for e in non_delivery_refund) + ')' if non_delivery_refund else '없음'}"
                   f"; 지연 위약금: {pen_txt}; 우리 해제권: {term_txt}"),
        "recovery": f"{sec_txt} — 반환·위약금 청구권이 있어도 상대방 재산이 없으면 회수되지 않음",
        "amount": max_one,
    })
    rows.append({
        "situation": "일부 출고·검수 불합격으로 정산액이 선급금보다 적음",
        "loss": "선급금 − 검수 합격 정산액(최대: 그 차수 선급금 전액)",
        "claims": f"차액 반환 의무: {refund_txt}; 반환 지연 위약금: {pen_txt}",
        "recovery": f"{sec_txt} — 청구권(반환·위약금)만 있고 이를 확보하는 장치는 원문에 없음" if not security else sec_txt,
        "amount": max_one,
    })
    rows.append({
        "situation": "상대방 지급불능·청산·말소",
        "loss": (f"미회수 선급금(동시에 여러 차수 선급금이 지급된 경우 누적 최대 {_fmt(cum)})" if cum else "미회수 선급금"),
        "claims": (f"청산 관련 의무: {', '.join(liq)}" if liq else "청산 관련 조항 없음")
                  + f"; 차액 반환: {refund_txt}",
        "recovery": ("청산 절차의 일반채권 — 계약상 '말소 전 이행·청산조 승계' 의무는 청산조에 대한 청구 근거일 뿐 "
                     "변제 재원을 보장하지 않음") + ("" if not security else "; 담보: " + ", ".join(security)),
        "amount": cum,
        "note": ("검수 전에는 소유권이 상대방에게 있음(" + flow.ownership_path + ") — '재고를 가져오는' 방안은 "
                 "소유권 이전 전 우리 권리가 없어 다른 채권자·청산조와 다툼이 생길 수 있음")
        if re.search(r"재고를\s*가져|재고를\s*회수|물건을\s*가져", answers_text or "") and flow.ownership_path else "",
    })
    return rows


# ── 4. 숫자·공란 재계산 ────────────────────────────────────────────────────────

_RX_DATE = re.compile(r"(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def _dates_in(s: str, default_year: int | None) -> list[date]:
    out = []
    year = default_year
    for m in _RX_DATE.finditer(s):
        y = int(m.group(1)) if m.group(1) else year
        if y is None:
            continue
        year = y
        try:
            out.append(date(y, int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    return out


def figure_checks(text: str, flow: DealFlow, clauses: list[Any] | None, parties: list[PartyEntry],
                  answers_text: str = "") -> list[dict[str, str]]:
    """계산·대조 결과. 어느 값이 맞는지는 정하지 않는다(확인사항)."""
    out: list[dict[str, str]] = []
    t = str(text or "")
    # 차수별 합계
    if flow.tranches:
        s = round(sum(x.amount or 0 for x in flow.tranches), 2)
        if flow.tranche_total_stated is not None and abs(s - flow.tranche_total_stated) >= 0.005:
            out.append({"kind": "합계 불일치", "path": flow.tranche_path,
                        "detail": f"차수별 금액 합 {_fmt(s)} ≠ 표의 합계 {_fmt(flow.tranche_total_stated)} (차이 {_fmt(round(s - flow.tranche_total_stated, 2))})"})
        if flow.total_amount is not None and abs(s - flow.total_amount) >= 0.005:
            out.append({"kind": "합계 불일치", "path": f"{flow.total_path} / {flow.tranche_path}",
                        "detail": f"계약 총액 {_fmt(flow.total_amount)} ≠ 차수별 금액 합 {_fmt(s)} (차이 {_fmt(round(flow.total_amount - s, 2))})"})
        if flow.advance_pct:
            p = flow.advance_pct / 100
            adv = [(x.name, round((x.amount or 0) * p, 2)) for x in flow.tranches]
            out.append({"kind": "선급금 계산", "path": flow.advance_path,
                        "detail": "차수별 선급금 " + ", ".join(f"{n} {_fmt(v)}" for n, v in adv)
                        + f" — 합계 {_fmt(round(sum(v for _, v in adv), 2))}"
                        + (f"(총액 기준 {flow.advance_pct:g}%는 {_fmt(round(flow.total_amount * p, 2))})" if flow.total_amount else "")})
    # 환율
    for path, _a, _ti, body in clause_rows(clauses):
        fx = re.search(r"(?:미화|USD|US\$)\s*([\d,]+(?:\.\d+)?)\s*(?:달러)?", body)
        rate = re.search(r"환율\s*(?:은|는)?\s*([\d]+\.\d+)", body)
        local = re.search(r"(?:인민폐|RMB|CNY|원화|KRW)\s*([\d,]+(?:\.\d+)?)", body)
        if fx and rate and local:
            usd, r, loc = _num(fx.group(1)), _num(rate.group(1)), _num(local.group(1))
            if usd and r and loc:
                calc = round(usd * r, 2)
                if abs(calc - loc) >= 0.01:
                    out.append({"kind": "환율 환산 불일치", "path": path,
                                "detail": f"{_fmt(usd)} × {r:g} = {_fmt(calc)} ≠ 기재 금액 {_fmt(loc)} (차이 {_fmt(round(loc - calc, 2))}; "
                                          f"기재 금액이 맞다면 적용 환율 {loc / usd:.6f}) — 어느 값이 맞는지 당사자 확인"})
    # 날짜
    sm = re.search(r"체결일\s*[:：]?\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", t)
    if sm:
        sign_d = date(int(sm.group(1)), int(sm.group(2)), int(sm.group(3)))
        for path, _a, _ti, body in clause_rows(clauses):
            for line in body.splitlines():
                for d in _dates_in(line, sign_d.year):
                    if d > sign_d and re.search(r"고시한|공표한|완료하였다|발행한|확인하였다", line):
                        out.append({"kind": "날짜 불일치", "path": path,
                                    "detail": f"체결일 {sign_d.isoformat()}보다 뒤인 {d.isoformat()}을 이미 지난 사실로 기재('{_ws(line)[:70]}')"})
        if flow.tranches:
            for x in flow.tranches:
                for d in _dates_in(x.when, sign_d.year):
                    if d < sign_d:
                        out.append({"kind": "날짜 불일치", "path": flow.tranche_path,
                                    "detail": f"{x.name} 출고 예정일 {d.isoformat()}이 체결일 {sign_d.isoformat()}보다 앞섬"})
    # 서명 일자 공란
    if re.search(r"^\s*일자\s*[:：]\s*$", t, re.M):
        out.append({"kind": "공란", "path": "서명란", "detail": "서명 일자 공란 — 효력 발생일(서명·날인일) 특정 필요"})
    # 세금
    vm = re.search(r"부가가치세(?:는)?\s*\[\s*포함\s*/\s*별도\s*\]", t)
    rm = re.search(r"세율(?:은|는)?\s*(\d+(?:\.\d+)?)\s*%", t)
    if vm:
        ans = "별도" if re.search(r"포함되어\s*있지\s*않|별도", answers_text or "") else "포함" if re.search(r"포함되어\s*있", answers_text or "") else ""
        tax = ""
        if ans == "별도" and rm and flow.total_amount:
            tax = f" — 별도라면 예정 총액 기준 세액 {_fmt(round(flow.total_amount * float(rm.group(1)) / 100, 2))}이 추가 지급됨(조건부 계산)"
        out.append({"kind": "세금 미확정", "path": flow.total_path or "",
                    "detail": "부가가치세 [포함/별도] 미선택" + (f"; 답변은 '{ans}'" if ans else "")
                              + (f"; 세율 {rm.group(1)}% 기재" if rm else "") + tax + " — 본문 확정 필요"})
    if re.search(r"발표|세금계산서|invoice", t) and re.search(r"\[\s*전용\s*\]", t):
        out.append({"kind": "증빙 미확정", "path": "", "detail": "증치세 [전용] 발표 여부 괄호 표시 — 매입세액 공제 가능 여부와 연결되므로 확정 필요"})
    # 괄호 미확정 값
    br = [(p, m.group(0)) for p, _a, _ti, body in clause_rows(clauses) for m in re.finditer(r"\[\s*\d+\s*\]", body)]
    if br:
        out.append({"kind": "미확정 값", "path": ", ".join(dict.fromkeys(p for p, _ in br)),
                    "detail": f"괄호로 표시한 기한·수치 {len(br)}곳(" + ", ".join(dict.fromkeys(f'{p} {v}' for p, v in br[:8])) + ") — 서명 전 확정"})
    # 당사자 정보·서명권한
    for p in parties:
        if p.blank_fields:
            out.append({"kind": "법인 정보 공란", "path": "서두",
                        "detail": f"{p.label}: " + ", ".join(dict.fromkeys(p.blank_fields)) + " 공란"})
        rep = _s(p.fields.get("법정대표자") or p.fields.get("법정대표자(또는 청산조 책임자)") or p.fields.get("대표이사") or "")
        for who in p.signers:
            if rep and _norm_name(who) and _norm_name(rep) and _norm_name(who) != _norm_name(rep):
                out.append({"kind": "서명권한", "path": "서명란",
                            "detail": f"{p.label} 서명자 '{who}' ≠ 서두 법정대표자 '{rep}' — 수권대표라면 위임장·인감 확인"})
            elif not rep:
                out.append({"kind": "서명권한", "path": "서명란",
                            "detail": f"{p.label} 법정대표자 공란 — 서명자 '{who}'의 대표권·수권 확인"})
    am = re.search(r"서두에\s*기재된\s*(" + "|".join(re.escape(p.label) for p in parties) + r")?[^.]*계좌", t) if parties else None
    if am:
        for p in parties:
            if am.group(1) and p.label != am.group(1):
                continue
            if any("계좌" in k for k in p.blank_fields):
                out.append({"kind": "지급 계좌 공란", "path": "",
                            "detail": f"{p.label} 계좌번호 공란인데 본문은 서두 기재 계좌로만 지급하도록 정함 — 기재 전에는 지급 불가"})
    return out


# ── 5. 사실관계 대조 · 수정 지침 분리 ─────────────────────────────────────────

#: 계약 문구에는 나올 수 없는 표지 — 당사자가 있어도 지침이다.
_GUIDANCE_STRONG = re.compile(
    r"중\s*하나를\s*선택|세\s*가지\s*중|두\s*가지\s*중|위\s*둘이|보조\s*수단|우선\s*제안|사업부|법무팀|바람직|"
    r"(?:^|\s)우리(?:가|는|의|\s*회사)|할\s*것\s*[.。]?$|검토\s*의견|수정\s*이유\s*[:：]|"
    # 편집 지시("다음 문단을 추가한다", "아래 항을 신설한다") — 메모에만 쓰고 계약 본문에는 넣지 않는다(2026-11-11)
    r"(?:다음|아래|위|이하)\s*(?:의\s*)?(?:문단|단락|조항|조문|항|호|문구|문안|내용)(?:을|를)\s*(?:추가|신설|삽입|삭제|교체|수정|반영)"
    r"(?:한다|하십시오|하시기|할\s*것|합니다)|(?:문단|단락|조항|항|문구|문안)(?:을|를)\s*(?:추가|신설|삽입)(?:한다|합니다|하십시오)\s*[.。:：]?$")
#: 당사자가 없는 문장에서만 지침으로 보는 서술(“담보를 요구한다”, “(예: 착수 시 일부)”). 당사자가 주어면 계약 의무일 수 있다.
_GUIDANCE_PARTYLESS = re.compile(r"검토한다|요구한다|제안한다|권장한다|고려한다|\(예\s*[:：]|예컨대")
#: 계약이 당사자를 부르는 흔한 역할 명사 — 서두에서 호칭을 못 읽은 계약에서도 당사자가 주어인 문장을 지침으로 오인하지 않게.
_ROLE_NOUNS = ("위탁자", "수탁자", "발주자", "수급인", "도급인", "하수급인", "임대인", "임차인", "매수인", "매도인", "구매자", "판매자",
               "공급자", "공급받는 자", "협업자", "사업자", "회사", "고객", "이용자", "라이선서", "라이선시", "주관기관", "참여기관",
               "광고주", "대행사", "제작사", "용역사", "수행사", "본사", "대리점", "가맹본부", "가맹점사업자", "제공자", "수령자")
#: 파이프라인이 원문과 추가 문안을 나누는 표시용 표지 — 변경추적본 생성기가 지운다. 문장이 아니다.
_RX_DISPLAY_MARKER = re.compile(r"^\s*\[(?:추가\s*권고|신설\s*제안|수정\s*제안|추가\s*문안)\]\s*$")
_RX_ENDING = re.compile(r"(?:다|한다|된다|있다|없다|아니한다|않는다|본다|따른다)\s*[.。]?\s*$|[.;]\s*$")


def guidance_sentences(text: str, labels: list[str]) -> list[str]:
    """계약 본문에 들어가면 안 되는 문장 — 검토 지침·선택지·당사자 없는 지시."""
    from runtime.review.deal_scenarios import _alt as _party_alt

    # 조사 '을'(…방식을)을 당사자 '을'로 읽지 않게 경계를 둔다
    rx_party = re.compile(rf"(?:{_party_alt([x for x in labels if x] + list(_ROLE_NOUNS)).replace('(?<![가-힣])', r'(?<![가-힣)）\]])')}|양\s*당사자|각\s*당사자|당사자|Party|Parties)")
    out = []
    for raw in re.split(r"(?<=[.。])\s+|\n|(?=[①②③④⑤⑥⑦⑧⑨⑩]\s)", str(text or "")):
        s = raw.strip()
        if len(s) < 6 or _RX_DISPLAY_MARKER.match(s):
            continue
        if re.match(r"^\d+\.\d+\s|^제\s*\d+\s*조", s):
            s2 = re.sub(r"^\d+\.\d+\s|^제\s*\d+\s*조[^\s]*\s*", "", s)
        else:
            s2 = s
        if _GUIDANCE_STRONG.search(s2) or _RX_TEMPLATE_SLOT.search(s2) \
                or (not rx_party.search(s2) and (_GUIDANCE_WEAK_END.search(s2) or _GUIDANCE_PARTYLESS.search(s2))):
            out.append(s)
    return out


#: 당사자가 없는 문장이 이런 서술어로 끝나면 계약 문구가 아니라 작성 지시다("소유권 유보를 명시한다", "담보를 제공받는다").
_GUIDANCE_WEAK_END = re.compile(r"(?:명시|확보|보완|검토|요구)한다\s*[.。]?$|둔다\s*[.。]?$|제공받는다\s*[.。]?$|늦추고")
#: 채워 넣으라는 자리표시("[협의한 법률]", "[관할법원/중재기관]")
_RX_TEMPLATE_SLOT = re.compile(r"\[[^\]]*(?:협의한|기재|입력|관할법원|중재기관|법률\])[^\]]*\]|\[[^\]]*/[^\]]*기관[^\]]*\]")


def fact_errors(cr: dict[str, Any], flow: DealFlow, role: RoleResolution) -> list[dict[str, str]]:
    """finding 이 원문 사실(지급 비율·소유권 방향)을 뒤집었는가."""
    if not role.confirmed:
        return []
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
    hay = " ".join(_s(cr.get(k)) for k in ("problem", "rewrite_reason", "legal_business_reason", "suggested_rewrite",
                                           "recommendation_text", "worst_case_scenario"))
    hay += " " + _s(ri.get("replacement_text")) + " " + _s(ri.get("reason"))
    errs = []
    ours = re.escape(role.our_label)
    if flow.ownership_to and flow.ownership_to == role.our_label:
        if re.search(rf"(?:우리|당사|{ours})(?:가|는|이|도)?[^.。]{{0,40}}소유권(?:까지|을|도)?\s*(?:이전|넘기|넘겨)", hay) \
                or re.search(r"소유권\s*유보|소유권과\s*위험의\s*이전\s*시점을\s*상대방", hay):
            errs.append({"code": "OWNERSHIP_DIRECTION", "claim": "우리가 소유권을 이전(또는 유보)하는 구조로 서술",
                         "fact": f"{flow.ownership_path}: 소유권은 {flow.ownership_when or '원문 시점'}에 {role.our_label}(우리)에게 이전"})
    adv = flow.first("advance")
    if adv is not None and adv.actor == role.our_label and flow.advance_pct is not None and flow.advance_pct < 100:
        if re.search(r"(?:먼저\s*)?전부\s*(?:제공|선이행|이행)|전액\s*(?:선지급|선이행|먼저)|급부를\s*먼저\s*전부", hay):
            errs.append({"code": "ADVANCE_OVERSTATED", "claim": "일부 선급을 전부(전액) 선이행으로 서술",
                         "fact": f"{flow.advance_path}: 선급은 {flow.advance_pct:g}% — 잔금은 검수·증빙 후"})
    if flow.price_payer and flow.price_payer == role.our_label:
        if re.search(r"우리가\s*(?:대금|선급금)을?\s*(?:받|수령)|상대방이\s*(?:대금|선급금)을?\s*(?:지급|선지급)하", hay):
            errs.append({"code": "PAYMENT_DIRECTION", "claim": "대금 지급 방향을 반대로 서술",
                         "fact": f"원문: {role.our_label}(우리)가 {flow.price_payee}에게 대금 지급"})
    return errs


# ── 6. 핵심 위험 수정 문구(계약 본문) ─────────────────────────────────────────

def _next_sub(text: str, art: str) -> int:
    nums = [int(m.group(1)) for m in re.finditer(rf"(?m)^\s*{re.escape(art)}\.(\d+)\s", text or "")]
    return (max(nums) + 1) if nums else 1


def _clause_by_path(clauses: list[Any] | None, path: str) -> Any | None:
    return next((c for c in clauses or [] if _attr(c, "display_path") == path), None)


def core_revisions(flow: DealFlow, role: RoleResolution, clauses: list[Any] | None, *,
                   request_mentions_liquidation: bool = False) -> list[dict[str, Any]]:
    """선급금 노출 위험을 실제로 발생시키는 조항(선급금 조)과 연결 조항(청산 조)을 함께 고치는 계약 문구."""
    if not (role.confirmed and buyer_advance_exposure(flow, role)) or flow.security_paths:
        return []
    ours, theirs = role.our_label, role.counterparty_label
    if not theirs:
        return []
    adv_art = flow.advance_path.split()[0] if flow.advance_path else ""
    host = _clause_by_path(clauses, adv_art)
    if host is None:
        return []
    art_no = _attr(host, "article_number") or re.sub(r"\D", "", adv_art)
    host_text = _attr(host, "text")
    n = _next_sub(host_text, art_no)
    adv_word = re.search(r"선급금|선지급금|계약금|착수금", flow.first("advance").sentence).group(0)
    unit = "차수" if "차수" in flow.first("advance").sentence else "회차" if "회차" in host_text else ""
    unit_of = f"해당 {unit}" if unit else "해당"
    lines_adv = [
        f"{art_no}.{n} {theirs}이 {adv_word}을 수령한 날부터 [10]영업일 이내에 {unit_of} 상품을 출고하지 아니하는 경우, "
        f"{ours}은 {theirs}에게 서면으로 통지하여 {unit_of + ' ' if unit else ''}구매를 취소할 수 있으며, {theirs}은 그 통지를 받은 날부터 "
        f"[5]영업일 이내에 {unit_of + '에 관하여 ' if unit else ''}수령한 {adv_word} 전액을 {ours}에게 반환하여야 한다.",
    ]
    if not flow.setoff_paths:
        lines_adv.append(
            f"{art_no}.{n + 1} {theirs}이 {ours}에게 반환하거나 지급하여야 할 금액(차액, {adv_word}, 위약금 및 손해배상금을 포함한다)이 "
            f"있는 경우, {ours}은 그 금액을 {theirs}에게 지급할 잔금{' 또는 다른 ' + unit + '의 대금' if unit else ''}과 상계할 수 있다.")
    if unit:
        lines_adv.append(
            f"{art_no}.{n + len(lines_adv)} 직전 {unit}의 정산과 차액 반환이 완료되기 전에는 {ours}은 다음 {unit}의 {adv_word}을 "
            f"지급할 의무를 부담하지 아니한다.")
    out = [{
        "key": "advance_recovery", "host": host, "lines": lines_adv,
        "location": f"{adv_art} {art_no}.{n} 신설",
        "problem": (f"{ours}(우리)이 출고 전에 {unit_of} 예정 금액의 {flow.advance_pct:g}%를 {adv_word}으로 지급하고, "
                    f"소유권은 {flow.ownership_when or '인도 후'}에야 {ours}에게 이전됩니다({flow.ownership_path}). "
                    f"원문에는 {theirs}이 {adv_word}을 받고도 출고하지 않을 때 {adv_word} 반환·구매 취소를 정한 조항이 없고"
                    + (", 반환받을 금액을 잔금과 상계하는 조항도 없습니다." if not flow.setoff_paths else ".")),
        "memo": (f"담보(보증금·은행 지급보증·재고 질권 등)를 요구할지는 사업 판단입니다 — 계약 문구는 위 {art_no}.{n} 이하로 "
                 f"노출을 한 {unit or '회'} 선급금 이내로 묶고 회수 수단(취소·반환·상계)을 둡니다. 괄호 안 기한은 협의 값입니다."),
    }]
    liq_paths = [p for p in dict.fromkeys(flow.liquidation_paths)]
    liq_art = liq_paths[0].split()[0] if liq_paths else ""
    if liq_art and liq_art != adv_art:
        lc = _clause_by_path(clauses, liq_art)
        if lc is not None:
            ln_no = _attr(lc, "article_number") or re.sub(r"\D", "", liq_art)
            m = _next_sub(_attr(lc, "text"), ln_no)
            out.append({
                "key": "liquidation_trigger", "host": lc,
                "lines": [
                    f"{ln_no}.{m} {theirs}은 해산 결의, 청산조 구성 또는 말소 등기 신청 중 어느 하나의 사유가 발생한 날부터 [3]영업일 이내에 "
                    f"그 사실과 청산조 구성원을 {ours}에게 서면으로 통지하여야 한다. 이 경우 {ours}은 아직 출고되지 아니한 "
                    f"{unit + '의 ' if unit else ''}구매를 서면 통지로 취소할 수 있고, {theirs}(청산조를 포함한다)은 그 통지를 받은 날부터 "
                    f"[5]영업일 이내에 취소된 {unit + '에 관하여 ' if unit else ''}수령한 {adv_word} 전액을 {ours}에게 반환하여야 한다.",
                ],
                "location": f"{liq_art} {ln_no}.{m} 신설",
                "problem": (f"{liq_art}은 말소 전 이행과 청산조 승계를 정하지만, 청산 개시를 언제 알려야 하는지와 그때 우리가 "
                            f"남은 {unit or '거래'}를 멈추고 {adv_word}을 돌려받을 권리는 없습니다. {adv_art}의 {adv_word} 반환 조항과 "
                            f"같은 사건(상대방 청산)에 함께 작동해야 합니다."),
                "memo": "청산 개시 사실은 사업자 공시(국가기업신용정보공시시스템 등)로도 확인할 수 있습니다 — 사실 확인 절차는 계약 밖 조치입니다.",
            })
    elif request_mentions_liquidation and not liq_art:
        out[0]["lines"].append(
            f"{art_no}.{n + len(out[0]['lines'])} {theirs}에 대하여 해산·청산 또는 말소 절차가 개시된 경우, {ours}은 아직 출고되지 아니한 "
            f"{unit + '의 ' if unit else ''}구매를 서면 통지로 취소할 수 있고, {theirs}은 그 통지를 받은 날부터 [5]영업일 이내에 "
            f"취소된 부분에 관하여 수령한 {adv_word} 전액을 {ours}에게 반환하여야 한다.")
    return out


def revision_findings(revs: list[dict[str, Any]], flow: DealFlow) -> list[dict[str, Any]]:
    out = []
    for r in revs:
        host = r["host"]
        orig = _attr(host, "text")
        path = _attr(host, "display_path")
        added = "\n".join(r["lines"])
        cid = f"flow_{r['key']}__{_attr(host, 'clause_id') or path}"
        out.append({
            "clause_id": cid,
            "clause_title": _attr(host, "title") or _attr(host, "clause_title"),
            "display_path": path,
            "article_number": _attr(host, "article_number"),
            "paragraph_number": "",
            "original_text": orig,
            "is_checklist_item": False,
            "risk_tier": "HIGH",
            "severity": "HIGH",
            "counsel_severity": "HIGH",
            "review_category": "필수수정",
            "issue_title": "선급금 회수 장치(미출고·청산 시 취소·반환·상계)" if r["key"] == "advance_recovery" else "상대방 청산 개시 시 통지·취소·반환",
            "problem": r["problem"],
            "rewrite_reason": r["problem"],
            "brief_action": "출고 지연·청산 시 남은 구매 취소, 선급금 반환 기한, 반환금 상계, 다음 차수 선급금 지급 조건을 신설합니다.",
            "brief_risk": "상대방이 선급금을 받고 출고하지 않거나 청산되면 선급금을 일반채권으로만 청구하게 됩니다.",
            "legal_business_reason": "청구권이 있다는 것과 회수할 수 있다는 것은 다르다 — 반환 기한·취소권·상계로 노출을 줄인다.",
            "drafting_memo": r["memo"],
            "suggested_rewrite": orig + "\n" + added,
            "recommendation_text": added,
            "has_rewrite_change": True,
            "has_addition": False,
            "is_deal_flow_revision": True,
            "risk_chain_key": "pre_performance_recovery",
            "redline_instruction": {
                "finding_id": cid, "clause_id": cid, "severity": "HIGH",
                "edit_location": r["location"], "edit_type": "insert_after", "edit_mode": "new_paragraph",
                "new_paragraph_number": "", "target_text": "",
                "replacement_text": added, "final_clause_text": added,
                "reason": r["problem"],
            },
            "undecided_terms": [f"{m} — 기한(영업일) 협의" for m in sorted(set(re.findall(r"\[\d+\]영업일", added)))],
        })
    return out


# ── 7. 요청별 답 ──────────────────────────────────────────────────────────────

_LAW_BASIS = {
    "중화인민공화국": ("중국 민사소송법의 협의관할 규정 — 계약 분쟁 당사자는 서면으로 피고 주소지·계약 이행지·계약 체결지·"
                  "원고 주소지·목적물 소재지 등 분쟁과 실제로 연결된 곳의 인민법원을 선택할 수 있고, 급별관할·전속관할을 "
                  "위반할 수 없다(조문 번호는 개정 이력이 있어 현행 조문 확인 필요)"),
    "대한민국": "민사소송법 제29조(합의관할) — 일정한 법률관계로 인한 소에 관하여 서면으로 제1심 관할법원을 정할 수 있다",
}


def _law_of(text: str) -> str:
    m = re.search(r"(중화인민공화국|대한민국|일본국|미합중국|[가-힣]{2,10}국)\s*(?:의\s*)?(?:법|법률|민법전)", text or "")
    if m:
        return m.group(1)
    m = re.search(r"laws?\s+of\s+(?:the\s+)?([A-Z][A-Za-z ]{2,40}?)[,.)]", text or "")
    return m.group(1).strip() if m else ""


def _clause_text(clauses: list[Any] | None, path: str) -> str:
    c = _clause_by_path(clauses, path)
    return _attr(c, "text") if c is not None else ""


def answer_requests(*, items: list[RequestItem], contracts: list[RequestContract], role: RoleResolution, flow: DealFlow,
                    scen: list[dict[str, Any]], figs: list[dict[str, str]], revs: list[dict[str, Any]],
                    clauses: list[Any] | None, text: str, request_text: str, answers_text: str,
                    clause_results: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """요청 하나마다 한 번: 근거 조항 → 원문상 결론 → 수정 또는 유지 이유 → 추가 확인사항."""
    this_contract = next((c.index for c in contracts if c.line == role.request_contract), "")
    rows: list[dict[str, Any]] = []
    # 항 단위로 나뉜 조("제6조 제2항")도 조 번호로 찾는다
    existing_paths = {m.group(0).replace(" ", "") for p, *_ in clause_rows(clauses) for m in [re.match(r"제\s*\d+\s*조", p)] if m}
    for it in items:
        if not it.text or len(it.text) < 4:
            continue
        row: dict[str, Any] = {"request_index": len(rows) + 1, "original_user_text": it.text, "topic": it.topic,
                               "contract": it.contract}
        other = it.contract and this_contract and it.contract != this_contract
        if other or (it.contract and not this_contract and contracts):
            rc = next((c for c in contracts if c.index == it.contract), None)
            name = rc.line if rc else it.contract
            months = re.search(r"(\d+)\s*개월", it.text)
            checks = [f"{name} 원문(서명본 또는 최종안)",
                      "분할 회차별 금액·기한과 기한이익 상실 사유", "대금 완납 전 소유권 유보 조항과 그 제3자 대항 요건(적용법상 등기 등)",
                      "담보(보증금·연대보증·은행 지급보증 등) 조항", "지연 이자·위약금·해제와 반환 조항", "관할·집행 조항, 상대방 법인 정보·서명권한"]
            if re.search(r"전환|법인", request_text or ""):
                checks.append("신청서상 상대방의 거래 주체 변경(법인 전환) 예정 — 서명 당사자와 대금 지급 주체 일치 여부")
            gap = cross_contract_gap(flow, role, months=int(months.group(1)) if months else None)
            row.update({
                "basis": f"원문 미제공({name})",
                "judgment": "원문 미제공으로 조항 효력 판단 보류",
                "required_action": "판단 보류 — 제공된 다른 계약서의 조항으로 대신 답하지 않음" + (f". 계약 사이 공백: {gap}" if gap else ""),
                "additional_checks": checks,
                "review_status": "사실관계 추가확인", "needs_revision": False, "held": True,
                "request_status": "확인 필요", "request_status_reason": "원문 미제공",
                "brief_answer": f"원문 미제공으로 조항 효력 판단 보류 — {name} 원문(분할 조건·소유권 유보·담보 조항)을 받은 뒤 판단합니다.",
            })
            rows.append(row)
            continue
        if it.topic == "advance":
            paths = [p for p in dict.fromkeys([flow.advance_path, *flow.refund_paths, *flow.liquidation_paths, flow.ownership_path]) if p]
            s_nd = scen[0] if scen else {}
            s_ins = scen[2] if len(scen) > 2 else {}
            concl = []
            if flow.advance_pct is not None:
                concl.append(f"선급은 {('차수별 ' if flow.tranches else '')}예정 금액의 {flow.advance_pct:g}%이고 잔금은 검수·증빙 후 지급({flow.advance_path})")
            if flow.ownership_path:
                concl.append(f"소유권은 {flow.ownership_when or '원문 시점'}에 {flow.ownership_to}에게 이전({flow.ownership_path})")
            if s_nd:
                concl.append(f"미출고 시: {s_nd.get('claims')}")
            if s_ins:
                concl.append(f"청산·말소 시 손실: {s_ins.get('loss')} — {s_ins.get('recovery')}")
            if s_ins.get("note"):
                concl.append(s_ins["note"])
            fix = [f"{r['location']}: " + " / ".join(r["lines"]) for r in revs]
            row.update({
                "basis": "; ".join(f"{p} “{_ws(next((e.sentence for e in flow.events if e.path == p), ''))[:60]}”" for p in paths),
                "judgment": "; ".join(concl) or "선급 구조를 원문에서 확인하지 못함",
                "required_action": ("수정 필요 — 선급금 조와 청산 조를 함께 고친다: " + " || ".join(fix)) if fix else
                                   ("유지 — 원문에 담보·상계 장치가 있음(" + ", ".join(flow.security_paths + flow.setoff_paths) + ")"
                                    if flow.security_paths or flow.setoff_paths else "수정안 보류 — 우리 역할 또는 흐름 확인 필요"),
                "additional_checks": ["상대방 청산 개시 시점·청산조 구성원(신청서: 개시 예정)",
                                      "상품에 대한 담보권·압류 여부(보증 조항만으로는 실제 상태를 확인하지 못함 — 동산 담보 등기 등 조회)",
                                      "담보(보증금·지급보증 등) 요구 여부 — 사업 판단(계약 문구 아님)"]
                + [f"{f['path']}: {f['detail']}" for f in figs if f["kind"] == "선급금 계산"],
                "review_status": "수정 필요" if revs else "사실관계 추가확인", "needs_revision": bool(revs),
                "answer_clause_paths": [p.split()[0] for p in paths],
                "request_status": "부분 반영" if revs else "확인 필요",
                "request_status_reason": ("수정안(" + ", ".join(r["location"].replace(" 신설", "") for r in revs)
                                          + ") 반영 — 담보 확보 여부는 사업 판단으로 남음") if revs else "우리 역할·흐름 확인 필요",
                "brief_answer": (("보완 필요 — " if revs else "")
                                 + (f"선급은 예정 금액의 {flow.advance_pct:g}%" if flow.advance_pct is not None else "선급 구조")
                                 + (f"이고 소유권은 {flow.ownership_when or '인도 후'}에 우리에게 오지만, " if flow.ownership_to == role.our_label else ", ")
                                 + ("미출고·청산 시 선급금 반환·구매 취소·상계 조항이 없어 " if revs else "")
                                 + (f"한 차수 최대 {_fmt(s_nd.get('amount'))}" if s_nd.get("amount") else "")
                                 + (f"(누적 최대 {_fmt(s_ins.get('amount'))})" if s_ins.get("amount") else "")
                                 + ("을 일반채권으로만 청구하게 됩니다. " if revs else ". ")
                                 + ("수정안: " + ", ".join(r["location"] for r in revs) + "." if revs else "")),
            })
            rows.append(row)
            continue
        if it.topic == "jurisdiction":
            jur = [(p, s) for p, _a, _t, b in clause_rows(clauses) for p2, s in _sentences(p, b)
                   if re.search(r"관할|법원에\s*소|중재|jurisdiction|arbitration", s, re.I) for p in [p2]]
            gov = [(p, s) for p, _a, _t, b in clause_rows(clauses) for p2, s in _sentences(p, b)
                   if re.search(r"(?:법|법률|민법전)을\s*적용|준거법|governed\s+by", s, re.I) for p in [p2]]
            law = _law_of(" ".join(s for _, s in gov))
            basis_law = _LAW_BASIS.get(law, "")
            forum_label = ""
            if jur:
                fm = re.search(r"(" + "|".join(map(re.escape, [role.our_label, role.counterparty_label] if role.our_label else list(_PARTY_LABELS))) + r")\s*의\s*(?:소재지|주소지|본점)", jur[0][1])
                forum_label = fm.group(1) if fm else ""
            premise = []
            if re.search(r"중국\s*법인|모두\s*중국|both.*PRC", request_text or ""):
                premise.append("신청서: 양 당사자 모두 중국 법인")
            if re.search(r"통일사회신용코드", text or ""):
                premise.append("서두에 통일사회신용코드 기재(중국 법인 식별번호)")
            cm = re.search(r"체결지\s*[:：]\s*([^\n]+)", text or "")
            if cm:
                premise.append(f"체결지: {cm.group(1).strip()}")
            fl = next((p for p in role.parties if p.get("label") == forum_label), None)
            addr_blank = bool(fl and any("주소" in k for k in fl.get("blank_fields") or []))
            concl = []
            if gov:
                concl.append(f"적용법: {law or '원문 기재'}({gov[0][0]})")
            if jur:
                concl.append(f"관할: {_ws(jur[0][1])[:90]}({jur[0][0]})")
            if basis_law and forum_label:
                concl.append(f"근거: {basis_law}. {forum_label}은 계약 당사자이므로 그 소재지는 원고 또는 피고 주소지라는 연결점이 있어, "
                             "관할 합의 자체는 허용 범위에 든다고 볼 여지가 크다(구체 법원은 급별관할에 따라 정해짐)")
            elif not basis_law:
                concl.append("적용법상 관할 합의의 효력 근거를 확인하지 못함 — 효력 판단 보류")
            concl.append("판결의 실제 집행·회수 가능성은 상대방 재산 소재·청산 진행에 좌우되어 단정하지 않음")
            checks = []
            if addr_blank:
                checks.append(f"{forum_label} 주소가 서두에 공란 — '{forum_label}의 소재지' 특정을 위해 등록 주소 기재 필요")
            checks.append("상대방 재산(재고·예금) 소재지 — 집행 법원과 다를 수 있음")
            if basis_law and "확인 필요" in basis_law:
                checks.append("관할 근거 조문의 현행 번호 확인")
            row.update({
                "basis": "; ".join(f"{p} “{_ws(s)[:70]}”" for p, s in (gov[:1] + jur[:1])),
                "judgment": "; ".join(concl) + (" — 전제 사실: " + ", ".join(premise) if premise else ""),
                "required_action": "유지 가능 — 문구 수정 대신 소재지(등록 주소) 공란을 채운다" if forum_label and basis_law
                                   else "판단 보류 — 적용법·연결점 확인 후 결정",
                "additional_checks": checks,
                "review_status": "적정" if forum_label and basis_law else "사실관계 추가확인", "needs_revision": False,
                "answer_clause_paths": sorted({p.split()[0] for p, _ in gov[:1] + jur[:1]}),
                "request_status": "확인 필요" if addr_blank or not basis_law else "반영",
                "request_status_reason": (f"현행 유지 가능 — {forum_label} 등록 주소 기재 조건" if addr_blank else
                                          "현행 문구 유지" if basis_law else "적용법상 근거 확인 필요"),
                "brief_answer": ((f"현행 유지 가능 — {law}법상 당사자 소재지 법원을 고르는 합의는 분쟁과 연결된 곳이라 허용 범위로 볼 여지가 큽니다"
                                  if basis_law else "판단 보류 — 적용법상 관할 합의의 근거를 확인하지 못했습니다")
                                 + (f". 다만 {forum_label} 주소가 공란이라 등록 주소를 기재해야 합니다" if addr_blank else "")
                                 + ". 판결의 집행·회수 가능성은 상대방 재산에 좌우되어 단정하지 않습니다."),
            })
            rows.append(row)
            continue
        if it.topic == "blanks":
            fl = [f for f in figs if f["kind"] in ("세금 미확정", "증빙 미확정", "법인 정보 공란", "서명권한", "지급 계좌 공란", "공란", "미확정 값")]
            nums = [f for f in figs if f["kind"] in ("합계 불일치", "환율 환산 불일치", "날짜 불일치")]
            row.update({
                "basis": "; ".join(dict.fromkeys(f["path"] for f in fl if f["path"])) or "서두·제2조 등 괄호 표시",
                "judgment": "; ".join(f"[{f['kind']}] {f['detail']}" for f in fl) or "괄호 표시 미확정 항목 없음",
                "required_action": "수정이 아니라 확정·기재 — 어느 값이 맞는지 정하지 않고 확인사항으로 둔다",
                "additional_checks": [f"[{f['kind']}] {f['path']}: {f['detail']}" for f in nums]
                + ([f"상대방 법인 정보: " + "; ".join(role.counterparty_blanks)] if role.counterparty_blanks else []),
                "review_status": "사실관계 추가확인", "needs_revision": False,
                "request_status": "확인 필요", "request_status_reason": "서명 전 확정·기재 사항",
                "brief_answer": (f"서명 전 확정 필요 — 금액·환율·날짜 불일치 {len(nums)}건, 세금·증빙·법인 정보·서명권한 등 공란 "
                                 f"{len(fl)}건(어느 값이 맞는지는 정하지 않음)."),
            })
            rows.append(row)
            continue
        # 그 밖의 요청: 지목 조항 원문과 그 조항의 지적
        refs = [p for p in it.clause_refs if p in existing_paths]
        missing = [p for p in it.clause_refs if p not in existing_paths]
        crs = [cr for cr in clause_results or [] if isinstance(cr, dict) and _s(cr.get("display_path")).split(" ")[0] in refs
               and _s(cr.get("risk_tier")).upper() in ("HIGH", "MEDIUM") and not cr.get("dedup_suppressed")]
        if refs:
            continue   # 전용 판단이 없는 요청은 기존 분석기의 답을 그대로 둔다
        if refs:
            q = "; ".join(f"{p} “{_ws(_clause_text(clauses, p))[:70]}”" for p in refs)
            row.update({"basis": q,
                        "judgment": "; ".join(_s(cr.get("problem"))[:160] for cr in crs[:2]) or "지목 조항에서 수정이 필요한 위험을 찾지 못함",
                        "required_action": "수정 필요 — 해당 조항 수정안 참고" if crs else "유지 — 원문 문언 그대로 작동",
                        "additional_checks": [f"{p}: 원문에 없는 조항" for p in missing],
                        "review_status": "수정 필요" if crs else "적정", "needs_revision": bool(crs),
                        "answer_clause_paths": refs})
        elif missing:
            row.update({"basis": "없음", "judgment": f"지목한 {', '.join(missing)}가 원문에 없음 — 조항 효력 판단 보류",
                        "required_action": "판단 보류", "additional_checks": ["지목 조항 번호 또는 계약서 판본 확인"],
                        "review_status": "사실관계 추가확인", "needs_revision": False, "held": True})
        else:
            continue   # 조항 지목도 전용 판단도 없는 요청 — 기존 분석기의 답을 그대로 둔다
        rows.append(row)
    return rows


def cross_contract_gap(flow: DealFlow, role: RoleResolution, *, months: int | None) -> str:
    """제공된 매입계약의 지급·인도 일정과 신청서에 적힌 재판매 조건 사이의 공백(원문 없는 계약의 조항은 판단하지 않는다)."""
    if not (role.our_role_kind == "buyer" and (flow.total_amount or flow.tranches)):
        return ""
    last = flow.tranches[-1].when if flow.tranches else ""
    total = flow.total_amount or sum(t.amount or 0 for t in flow.tranches)
    s = f"매입 대금 {_fmt(total)}은 {('마지막 출고 예정 ' + last + ' 이후 검수·증빙 후') if last else '검수 후'} 지급을 마치는데"
    if months:
        s += (f", 재판매 대금은 {months}개월 분할로 들어온다(신청서) — 그 기간 동안 매입 대금 상당액을 우리가 부담하고, "
              f"재판매 상대방에게 상품이 먼저 넘어가면 미회수 분할금만큼 노출된다")
    s += (f". 인도 장소({flow.first('delivery').path if flow.first('delivery') else '원문'})가 재판매 상대방의 창고라면 "
          "검수·소유권 취득 시점과 재판매 인도 시점이 겹치는지 확인 필요")
    return s


# ── 8. 보고서 줄(DOCX·PDF 공통) ───────────────────────────────────────────────

SECTION_TITLE = "0-0. 우리 역할과 실제 거래 흐름 (조항 검토의 전제)"


def section_lines(df: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    if not isinstance(df, dict) or not df.get("active"):
        return []
    r = df.get("role") or {}
    out: list[tuple[str, str, str]] = [("heading", SECTION_TITLE, "")]
    tone = "" if r.get("confirmed") else "high"
    out.append(("bold", f"우리 역할: {r.get('status')}", tone))
    if r.get("our_label"):
        out.append(("bullet", f"계약상 호칭: {r.get('our_label')} / 역할: {r.get('our_role') or '역할 명사 없음'}"
                              f" / 계약서상 법인: {r.get('our_contract_name') or '원문 미기재'}"
                              + (f" / 신청서 호칭: {r.get('our_request_name')}" if r.get("our_request_name") else ""), ""))
    if r.get("counterparty_label"):
        out.append(("bullet", f"상대방: {r.get('counterparty_label')} / {r.get('counterparty_role') or ''} / "
                              f"{r.get('counterparty_name') or '법인명 공란'}", ""))
    for e in r.get("evidence") or []:
        out.append(("bullet", f"근거: {e}", ""))
    for c in r.get("conflicts") or []:
        out.append(("bullet", f"충돌: {c}", "high"))
    for b in r.get("counterparty_blanks") or []:
        out.append(("bullet", f"상대방 정보 공란(역할 판단과 별개): {b}", "medium"))
    for b in r.get("brand_notes") or []:
        out.append(("bullet", f"법인·브랜드 구분: {b}", ""))
    if df.get("stages"):
        out.append(("bold", "거래 흐름 — 누가 누구에게 무엇을 언제", ""))
        for st in df["stages"]:
            arrow = f"{st.get('from') or ''} → {st.get('to') or ''}".strip(" →")
            out.append(("bullet", f"[{st['path']}] {st['step']}: {arrow} {st.get('what') or ''}"
                                  + (f" — {st['when']}" if st.get("when") else ""), ""))
    if df.get("scenarios"):
        out.append(("bold", "상황별 손실 — 청구권과 실제 회수 가능성을 구분", ""))
        for sc in df["scenarios"]:
            out.append(("bold", f"■ {sc['situation']}", "medium"))
            out.append(("bullet", f"잃을 수 있는 것: {sc['loss']}", ""))
            out.append(("bullet", f"원문상 권리: {sc['claims']}", ""))
            out.append(("bullet", f"실제 회수: {sc['recovery']}", ""))
            if sc.get("note"):
                out.append(("bullet", f"주의: {sc['note']}", "high"))
    if df.get("figures"):
        out.append(("bold", "금액·환율·날짜·공란 재계산 (어느 값이 맞는지는 정하지 않음)", ""))
        for f in df["figures"]:
            tone_f = "high" if f["kind"] in ("합계 불일치", "환율 환산 불일치", "날짜 불일치") else ""
            out.append(("bullet", f"[{f['kind']}] {f['path'] + ': ' if f['path'] else ''}{f['detail']}", tone_f))
    if df.get("fact_corrections"):
        out.append(("bold", "사실관계 정정 — 원문과 다른 전제로 만든 수정안을 멈춤", "high"))
        for c in df["fact_corrections"]:
            out.append(("bullet", f"{c.get('path')}: '{c.get('claim')}' → 원문: {c.get('fact')} (수정안 '{c.get('action')}')", ""))
    if df.get("guidance_moved"):
        out.append(("bold", "본문에서 메모로 옮긴 검토 지침", ""))
        for g in df["guidance_moved"]:
            out.append(("bullet", f"{g.get('path')}: {g.get('sentence')[:120]}", ""))
    for pc in r.get("pre_sign_checks") or []:
        out.append(("bullet", f"서명 전 확인: {pc}", "medium"))
    out.extend(_linkage_lines(df.get("term_linkage")))
    if df.get("unresolved"):
        out.append(("bold", "보류 — 자료 부족·원문 충돌", "high"))
        for u in df["unresolved"]:
            out.append(("bullet", f"[{u.get('category')}] {u.get('detail')}", ""))
    from runtime.review.privacy_flow import section_lines as _privacy_lines

    out.extend(_privacy_lines(df.get("privacy")))
    return out


def _linkage_lines(lk: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    """존속·해지·위약금·요금 연결 — 조항을 따로 읽지 않고 한 흐름으로 보여 준다."""
    if not isinstance(lk, dict) or not lk.get("active"):
        return []
    out: list[tuple[str, str, str]] = [("bold", "계약에서 빠져나오는 길 — 자동갱신·해지·위약금·요금 연결", "")]
    rn = lk.get("renewal") or {}
    if rn:
        out.append(("bullet", f"[{rn['path']}] 존속: {rn.get('period') or '기간'}"
                              + (f", 만료 {rn['notice_days']}일 전까지 갱신 거절 없으면 자동 연장" if rn.get("notice_days") else ", 자동 연장"), ""))
    for t in lk.get("terminations") or []:
        kind = {"breach": "의무 위반(최고 후)", "insolvency": "도산·지급불능", "convenience": "임의 해지", "other": "기타"}.get(t["kind"], t["kind"])
        out.append(("bullet", f"[{t['path']}] 해지 사유: {kind} — 해지권자 {t.get('holder') or '원문 참조'}", ""))
    if not lk.get("our_convenience"):
        out.append(("bullet", "우리의 임의(중도) 해지권: 원문에 없음", "high"))
    pen = lk.get("penalty") or {}
    if pen:
        out.append(("bullet", f"[{pen['path']}] 위약금: 부담 {pen.get('payer') or '원문 참조'} / 사유 {pen.get('trigger') or '원문 참조'}"
                              + (f" / 기준 {pen.get('base_fee')}({pen.get('base_fee_value')})" if pen.get("base_fee") else "")
                              + (" / 자동 연장 기간에도 적용" if pen.get("applies_to_renewal") else ""), "medium"))
        if pen.get("undefined_terms"):
            out.append(("bullet", f"산식의 정의 없는 기준: {', '.join(pen['undefined_terms'])}", "high"))
    for f in lk.get("fees") or []:
        out.append(("bullet", f"[별지 요금] {f['name']}: {f['value']}", ""))
    st = lk.get("settlement") or {}
    if st:
        out.append(("bullet", f"[{st['path']}] 종료 정산: {st['sentence'][:100]}", ""))
    return out


def request_row_lines(r: dict[str, Any]) -> list[tuple[str, str, str]]:
    tone = {"수정 필요": "high", "사실관계 추가확인": "medium", "적정": "low"}.get(_s(r.get("review_status")), "")
    out: list[tuple[str, str, str]] = [("bold", f"요청 {r.get('request_index')}. {_s(r.get('original_user_text'))}", "")]
    out.append(("text", f"근거 조항: {_s(r.get('basis')) or '—'}", ""))
    out.append(("bold", f"원문상 결론: {_s(r.get('judgment')) or '—'}", tone))
    out.append(("text", f"수정 또는 유지 이유: {_s(r.get('required_action')) or '—'}", ""))
    checks = r.get("additional_checks") or []
    out.append(("text", "추가 확인사항: " + ("" if checks else "없음"), ""))
    for c in checks:
        out.append(("bullet", str(c), ""))
    return out


# ── 9. 단계 실행 ──────────────────────────────────────────────────────────────

CAT_FACT = "당사자·지급·소유권 방향 오류"
CAT_ROLE = "우리 역할 판단 보류(자료 충돌)"
CAT_GUIDE = "미완성 계약 문구(검토 지침 본문 삽입)"


def _hold(cr: dict[str, Any], reason: str) -> None:
    ri = cr.get("redline_instruction")
    if not isinstance(ri, dict):
        ri = {}
        cr["redline_instruction"] = ri
    ri["held"] = True
    ri["hold_reason"] = reason
    cr["verification_removed"] = reason


def _added_text(cr: dict[str, Any]) -> tuple[str, str]:
    """(본문에 새로 들어갈 문구, 그것을 담은 필드명)."""
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
    rep = _s(ri.get("final_clause_text") or ri.get("replacement_text"))
    if rep:
        return rep, "ri"
    return _s(cr.get("suggested_rewrite")), "sr"


def strip_guidance(cr: dict[str, Any], labels: list[str]) -> list[str]:
    """수정 문구에서 원문에 없던 지침 문장을 떼어 메모로 옮긴다. 남은 새 문구가 없으면 수정안을 보류한다."""
    orig = _ws(cr.get("original_text"))
    text, _src = _added_text(cr)
    if not text:
        return []
    bad = [s for s in guidance_sentences(text, labels) if _ws(s) not in orig]
    title = _s(cr.get("clause_title"))
    lines = text.split("\n")
    # 조 제목만 있는 첫 줄(원문 조항 본문에 없는 머리글)은 본문 중복을 만든다(실측: 제6조 제목·6.1·6.2 중복)
    head_dup = bool(lines and title and lines[0].strip() == title and not orig.startswith(title))
    if not bad and not head_dup:
        return []
    new = text
    if head_dup:
        new = "\n".join(lines[1:])
    for s in bad:
        new = new.replace(s, "")
    new = re.sub(r"[ \t]+\n", "\n", re.sub(r" {2,}", " ", new)).strip()
    memo = " ".join(bad)
    if memo:
        cr["drafting_memo"] = (_s(cr.get("drafting_memo")) + " " + memo).strip()
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else None
    if ri is not None:
        for k in ("replacement_text", "final_clause_text"):
            if _s(ri.get(k)):
                v = _s(ri[k])
                if head_dup and v.split("\n")[0].strip() == title:
                    v = "\n".join(v.split("\n")[1:])
                for s in bad:
                    v = v.replace(s, "")
                ri[k] = re.sub(r" {2,}", " ", v).strip()
    sr = _s(cr.get("suggested_rewrite"))
    for s in bad:
        sr = sr.replace(s, "")
    if head_dup and sr.split("\n")[0].strip() == title:
        sr = "\n".join(sr.split("\n")[1:])
    cr["suggested_rewrite"] = re.sub(r" {2,}", " ", sr).strip()
    for k in ("recommendation_text", "proposed_revision"):
        if _s(cr.get(k)):
            v = _s(cr[k])
            for s in bad:
                v = v.replace(s, "")
            if head_dup and v.split("\n")[0].strip() == title:
                v = "\n".join(v.split("\n")[1:])
            cr[k] = re.sub(r" {2,}", " ", v).strip()
    remain = _ws(_added_text(cr)[0])
    if not remain or remain == orig or _ws(remain).replace(" ", "") == orig.replace(" ", ""):
        _hold(cr, "계약 본문에 넣을 문구가 없음 — 검토 지침은 메모로 이동(수정안 보류)")
    return bad + ([f"[머리글 중복] {title}"] if head_dup else [])


def run_deal_flow_stage(*, text: str, clauses: list[Any] | None, clause_results: list[dict[str, Any]],
                        request_text: str = "", answers_text: str = "", entity: str = "",
                        known_role: dict[str, Any] | None = None) -> dict[str, Any]:
    """역할 → 흐름 → 상황 → 숫자 → 사실관계 대조·지침 분리 → 핵심 수정 → 요청별 답 → 재검사.

    `known_role`: 국제계약 레이어가 당사자 표의 지위 + 요청문(또는 사전질문 답)으로 확정한 관점. 있으면 그대로 쓴다 —
    관점 판단을 두 곳에서 따로 하면 국·영 좌우 병기 표의 당사자 칸을 읽지 못한 쪽이 "미확정"을 내 결과가 갈렸다(2026-11-27).
    """
    parties = parse_parties(text)
    labels = [p.label for p in parties] or list(_PARTY_LABELS)
    flow0 = extract_flow(clauses, labels, text)
    role = resolve_role(text, request_text, entity, flow_hint={"price_payer": flow0.price_payer})
    if known_role and known_role.get("confirmed") and known_role.get("our_label"):
        kind = str(known_role.get("our_role") or "")
        role.status = ROLE_CONFIRMED
        role.our_label = str(known_role["our_label"])
        role.our_role_kind = kind if kind in ("buyer", "seller") else ""
        role.our_role = {"buyer": "매수인(구매자)", "seller": "매도인(공급자)"}.get(kind, kind)
        role.counterparty_label = str(known_role.get("their_label") or role.counterparty_label or "")
        role.counterparty_role = {"buyer": "매도인(공급자)", "seller": "매수인(구매자)"}.get(kind, role.counterparty_role)
        role.conflicts = []
        role.evidence.insert(0, f"국제계약 관점: {known_role.get('basis', '당사자 표 지위 + 요청문')}")
    flow = flow0
    scen = scenarios(flow, role, answers_text)
    figs = figure_checks(text, flow, clauses, parties, answers_text)
    history: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    if role.status == ROLE_CONFLICT:
        # 자료가 실제로 충돌할 때만 미해결로 올린다 — 자료 부족(미확정)은 방향이 필요한 판단만 보류하고 나머지 검토는 계속한다
        unresolved.append({"category": CAT_ROLE, "detail": "; ".join(role.conflicts)})

    # 사실관계 대조 — 원문과 반대 전제로 만든 finding 은 수정안 생성을 멈추고 기록한다
    corrections: list[dict[str, str]] = []
    for cr in list(clause_results):
        if not isinstance(cr, dict) or cr.get("is_deal_flow_revision"):
            continue
        errs = fact_errors(cr, flow, role)
        if not errs:
            continue
        has_edit = bool(cr.get("has_rewrite_change"))
        for e in errs:
            corrections.append({"finding": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")), "claim": e["claim"],
                                "fact": e["fact"], "code": e["code"], "action": "삭제·재작성" if has_edit else "설명 삭제"})
        # 사실이 틀린 finding 은 문제 설명까지 틀렸으므로 결과에서 뺀다(같은 위험은 아래 흐름 기반 수정안이 다시 다룬다)
        clause_results.remove(cr)
    history.append({"step": "사실관계 대조", "corrections": len(corrections)})

    # 계약에 없는 당사자 호칭(갑·을 등)으로 쓴 수정안 — 다른 계약 유형 문안이 섞인 것이다. 근거 없는 문구라 보류한다(2026-11-12:
    # 식권 서비스 계약 제15조에 대리점 계약용 "갑이 비용 정산 … 판촉비/반품비" [추가] 문단이 붙어 ①② 가 중복됐다).
    foreign = ungrounded_labels(text, labels)
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_deal_flow_revision"):
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if ri.get("held") or not (cr.get("has_rewrite_change") or cr.get("has_addition")):
            continue
        body = " ".join(_s(x) for x in (ri.get("replacement_text"), ri.get("final_clause_text"), cr.get("suggested_rewrite"),
                                         cr.get("addition_text")))
        used = [lab for lab in foreign if re.search(rf"(?<![가-힣]){lab}(?:이|은|는|에게|의|과|와|가)\s", body)]
        if used:
            _hold(cr, f"계약에 없는 당사자 호칭({', '.join(used)})으로 쓴 수정 문구 — 다른 계약 문안이 섞여 보류")
            corrections.append({"finding": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")),
                                "claim": f"수정 문구의 당사자 호칭 {', '.join(used)}", "fact": f"계약상 호칭: {', '.join(labels)}",
                                "code": "FOREIGN_PARTY_LABEL", "action": "보류"})

    # 우리 역할과 반대편 관점의 체크리스트 문구 — 원문으로 확정한 우리 역할(매수인 등)에게 금지·부담을 지우는 신설 문구는 보류한다
    # (2026-11-12 원자재 납품: 그룹사=공급자 기본값으로 "구매자는 … 취소할 수 없다 / 비용을 부담한다" 를 우리에게 제안했다).
    if role.confirmed and role.our_role_kind in ("buyer", "seller"):
        mine = _BUYER_ROLES if role.our_role_kind == "buyer" else _SELLER_ROLES
        mine_rx = "|".join(re.escape(x) for x in mine if re.search(r"[가-힣]", x))
        for cr in clause_results:
            if not isinstance(cr, dict) or not cr.get("is_checklist_item") or cr.get("is_deal_flow_revision"):
                continue
            ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
            body = " ".join(_s(x) for x in (ri.get("replacement_text"), ri.get("final_clause_text"), cr.get("suggested_rewrite")))
            if ri.get("held") or not body.strip():
                continue
            hit = re.search(rf"(?:{mine_rx})(?:은|는|이|가)\s[^.]{{0,80}}?(?:할\s*수\s*없|부담한다|부담하여야|하여야\s*한다|제출하여야|지급하여야)", body)
            if hit:
                _hold(cr, f"우리 역할({role.our_role})에게 금지·부담을 지우는 반대편 관점 문구 — 보류: “{hit.group(0)[:60]}”")
                corrections.append({"finding": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")) or _s(ri.get("edit_location")),
                                    "claim": "체크리스트 신설 문구의 관점", "fact": f"우리 = {role.our_role}", "code": "OPPOSITE_SIDE_CHECKLIST",
                                    "action": "보류"})

    # 편집 지시문 분리 — "다음 문단을 추가한다: '…'" 는 메모로, 따옴표 안 계약 문장만 본문으로(2026-11-12)
    split_ins: list[dict[str, str]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_deal_flow_revision"):
            continue
        ins = split_edit_instruction(cr) if not (cr.get("redline_instruction") or {}).get("held") else ""
        if ins:
            split_ins.append({"finding": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")), "sentence": ins})
    history.append({"step": "편집 지시문 분리", "moved": len(split_ins)})

    # 수정 지침 분리 — 모든 남은 수정안
    moved: list[dict[str, str]] = list(split_ins)
    our_lab = [x for x in (role.our_label, role.counterparty_label) if x] or labels
    for cr in clause_results:
        if not isinstance(cr, dict) or not cr.get("has_rewrite_change") or cr.get("is_deal_flow_revision"):
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if ri.get("held"):
            continue
        for s in strip_guidance(cr, labels + our_lab):
            moved.append({"finding": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")), "sentence": s})
    history.append({"step": "검토 지침 분리", "moved": len(moved)})

    # 핵심 위험 수정 문구(선급금 조 + 연결 조)
    revs = core_revisions(flow, role, clauses,
                          request_mentions_liquidation=bool(re.search(r"청산|말소", request_text or "")))
    new_findings = revision_findings(revs, flow)
    # 같은 위험(선이행 회수)을 다른 규칙이 이미 다뤘다면 흐름 기반 수정안으로 대체한다
    if new_findings:
        for cr in list(clause_results):
            if isinstance(cr, dict) and _s(cr.get("risk_chain_key")) == "pre_performance_recovery" and not cr.get("is_deal_flow_revision"):
                clause_results.remove(cr)
                corrections.append({"finding": _s(cr.get("clause_id")), "path": _s(cr.get("display_path")),
                                    "claim": "선이행 회수 지적(원문 흐름 미반영)", "fact": "흐름 기반 수정안으로 대체", "code": "SUPERSEDED",
                                    "action": "대체"})
        clause_results.extend(new_findings)
    history.append({"step": "핵심 위험 수정 문구", "added": [f["clause_id"] for f in new_findings]})

    # 재검사 — 새로 만든 문구도 같은 기준(사실·지침)으로
    recheck = []
    for cr in new_findings:
        errs = fact_errors(cr, flow, role)
        g = [s for s in guidance_sentences(_s(cr["redline_instruction"]["replacement_text"]), labels) if s]
        if errs or g:
            recheck.append({"finding": cr["clause_id"], "errors": errs, "guidance": g})
            _hold(cr, "흐름 기반 수정안 재검사 실패 — 보류")
    history.append({"step": "재검사", "failed": recheck})
    for r in recheck:
        unresolved.append({"category": CAT_GUIDE if r["guidance"] else CAT_FACT,
                           "detail": f"{r['finding']}: 재작성 후에도 검사 실패 — 보류"})

    contracts, items, _bg = parse_request(request_text)

    # 존속·해지·위약금·요금 연결 검토와 개인정보 처리 흐름 검토(2026-11-12) — 조항 제목이 아니라 흐름으로 함께 읽는다
    linked = linked_review(text=text, clauses=clauses, clause_results=clause_results, role=role, items=items,
                           answers_text=answers_text, request_text=request_text)
    corrections.extend(linked["superseded"])
    history.append({"step": "해지·위약금 연결 검토",
                    "added": [f["clause_id"] for f in linked["findings"] if not str(f.get("linked_topic")).startswith("privacy")]})
    history.append({"step": "개인정보 처리 흐름 검토", "active": bool(linked["privacy"].get("active")),
                    "added": [f["clause_id"] for f in linked["findings"] if str(f.get("linked_topic")).startswith("privacy")]})

    rows = answer_requests(items=items, contracts=contracts, role=role, flow=flow, scen=scen, figs=figs, revs=revs,
                           clauses=clauses, text=text, request_text=request_text, answers_text=answers_text,
                           clause_results=clause_results)
    for r in rows:
        if r.get("topic") == "advance" and r.get("needs_revision"):
            r["matched_finding_ids"] = [f["clause_id"] for f in new_findings
                                        if not (f.get("redline_instruction") or {}).get("held")]
    rows.extend(linked["rows"])
    for i, r in enumerate(rows, 1):
        r["request_index"] = i
    held_reqs = [r for r in rows if r.get("held")]
    active = bool(role.our_label or flow.events or items or linked["privacy"].get("active") or linked["linkage"].get("active"))
    return {
        "active": active,
        "role": role.to_dict(),
        "flow": flow.to_dict(),
        "stages": stages(flow, role),
        "scenarios": scen,
        "figures": figs,
        "fact_corrections": corrections,
        "guidance_moved": moved,
        "revisions": [{"location": r["location"], "lines": r["lines"], "memo": r["memo"]} for r in revs],
        "request_contracts": [asdict(c) for c in contracts],
        "request_rows": [to_coverage_row(r) for r in rows],
        "held_requests": [r["original_user_text"] for r in held_reqs],
        "unresolved": unresolved,
        "history": history,
        "term_linkage": linked["linkage"],
        "privacy": linked["privacy"],
        "linked_revisions": [{"clause_id": f["clause_id"], "location": f["redline_instruction"]["edit_location"],
                              "lines": f["redline_instruction"]["replacement_text"].split("\n"), "topic": f.get("linked_topic")}
                             for f in linked["findings"]],
    }


def linked_review(*, text: str, clauses: list[Any] | None, clause_results: list[dict[str, Any]], role: "RoleResolution",
                  items: list[RequestItem], answers_text: str = "", request_text: str = "") -> dict[str, Any]:
    """해지·위약금 연결 검토 + 개인정보 처리 흐름 검토. 수정 문구는 clause_results 에 넣고, 같은 조의 다른 수정안은 하나로 합친다."""
    from runtime.review import privacy_flow as _pf
    from runtime.review import term_linkage as _tl

    ours = role.our_label if role.confirmed else ""
    theirs = role.counterparty_label if role.confirmed else ""
    lk = _tl.analyze(text, ours=ours or "우리", theirs=theirs or "상대방")
    term_items = [it for it in items if it.topic == "termination"]
    asks_exit = any("exit" in _tl.split_questions(it.text) for it in term_items)
    revs = _tl.revisions(lk, text, ours=ours, theirs=theirs, request_asks_exit=asks_exit) if ours and theirs else []
    findings = _tl.to_findings(revs, clauses)
    for f, r in zip(findings, revs):
        f["linked_topic"] = r["key"]
    pr = _pf.analyze(text, ours=ours or "우리", theirs=theirs or "상대방", answers_text=answers_text, request_text=request_text)
    prev = _pf.revision(pr, text, ours=ours, theirs=theirs) if ours and theirs else None
    if prev:
        pf_findings = _tl.to_findings([prev], clauses, prefix="privacy")
        for f in pf_findings:
            f["linked_topic"] = "privacy_flow"
            f["display_path"] = f["redline_instruction"]["edit_location"].replace(" 신설", "")
        findings.extend(pf_findings)
    superseded: list[dict[str, str]] = []
    # 같은 조에 다른 단계가 만든 수정안이 있으면 연결 수정안으로 합친다(두 수정안이 같은 조에 항 번호를 겹쳐 넣지 않게).
    # 다른 수정안의 지적 내용은 메모로 옮겨 남긴다.
    for f in findings:
        if f.get("linked_topic") == "privacy_flow":
            continue   # 새 조 신설 — 기존 조의 수정안과 겹치지 않는다
        art = _s(f.get("article_number"))
        for cr in list(clause_results):
            if not isinstance(cr, dict) or cr.get("is_deal_flow_revision") or not (cr.get("has_rewrite_change") or cr.get("has_addition")):
                continue
            ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
            if ri.get("held") or cr.get("keep_as_is") or cr.get("dedup_suppressed"):
                continue
            path = _s(cr.get("display_path"))
            m = re.match(r"제\s*(\d+)\s*조", path) or re.search(r"제\s*(\d+)\s*조", _s(ri.get("edit_location")))
            if not m or m.group(1) != art:
                continue
            clause_results.remove(cr)
            note = _ws(cr.get("problem") or cr.get("issue_title"))[:200]
            if note:
                f["drafting_memo"] = (_s(f.get("drafting_memo")) + f" 함께 검토한 다른 의견({path}): {note}").strip()
            superseded.append({"finding": _s(cr.get("clause_id")), "path": path, "claim": "같은 조의 개별 수정안",
                               "fact": f"연결 검토 수정안({f['redline_instruction']['edit_location']})으로 통합", "code": "SUPERSEDED",
                               "action": "통합"})
    # 홍보 조항 — 회사 승인과 개인 정보 이용을 나눈다
    if pr.active and pr.promo and ours and theirs:
        pm_art = re.sub(r"\D", "", pr.promo["path"].split("의")[0])
        live = [cr for cr in clause_results if isinstance(cr, dict) and cr.get("has_rewrite_change")
                and not (cr.get("redline_instruction") or {}).get("held") and not cr.get("dedup_suppressed")
                and _s(cr.get("risk_tier")).upper() in ("HIGH", "MEDIUM")
                and re.match(rf"제\s*{pm_art}\s*조", _s(cr.get("display_path")))]
        if live:
            cr = live[0]
            ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
            cur = _s(ri.get("final_clause_text") or ri.get("replacement_text") or cr.get("suggested_rewrite"))
            if not re.search(r"개인을\s*알아볼|개인\s*정보|개인의\s*별도\s*동의", cur):
                pr.promo["approval_in_contract"] = pr.promo.get("approval_in_contract") or bool(re.search(r"사전[^.]{0,10}(?:승인|동의)", cur))
                add = _pf.promo_sentence(pr, text, ours=ours, theirs=theirs)
                for k in ("replacement_text", "final_clause_text"):
                    if _s(ri.get(k)):
                        ri[k] = _s(ri[k]).rstrip() + " " + add
                if _s(cr.get("suggested_rewrite")):
                    cr["suggested_rewrite"] = _s(cr["suggested_rewrite"]).rstrip() + " " + add
                cr["drafting_memo"] = (_s(cr.get("drafting_memo")) + " 회사명·로고 사용 승인과 개인 정보의 홍보 이용(정보주체 동의)을 나눠 정합니다.").strip()
                cr["linked_privacy_promo"] = True
        else:
            add = _pf.promo_sentence(pr, text, ours=ours, theirs=theirs)
            pa = next((a for a in _tl.articles(text)[0] if a.path == pr.promo["path"]), None)
            if add and pa is not None:
                mark, _st = _tl.next_number(pa.body)
                pf2 = _tl.to_findings([{
                    "key": "privacy_promo", "article": pa, "lines": [f"{mark} {add}".strip()],
                    "location": f"{pa.path} {mark} 신설" if mark else f"{pa.path} 끝 문단 신설",
                    "issue_title": "홍보 이용 범위 — 회사 승인과 개인 정보 이용 구분",
                    "problem": (f"{pa.path}는 {ours}의 계약 체결 사실과 운영 사례를 {theirs}가 홍보에 쓸 수 있게 하면서 사전 승인 절차가 없고, "
                                f"운영 사례에 {pr.subject or '정보주체'}의 개인 정보가 들어갈 때의 동의도 정하지 않았습니다."),
                    "memo": "회사명·로고 사용은 회사 승인 사항이고, 개인 정보의 광고·홍보 이용은 정보주체 본인 동의 사항입니다.",
                    "tier": "MEDIUM"}], clauses, prefix="privacy")
                for f in pf2:
                    f["linked_topic"] = "privacy_promo"
                findings.extend(pf2)
    clause_results.extend(findings)
    # 요청별 답 — 중도해지 가능 여부와 위약금은 별개 질문
    rows: list[dict[str, Any]] = []
    fid = {f.get("linked_topic"): f["clause_id"] for f in findings}
    exit_items = [it for it in term_items if _tl._RX_ASK_EXIT.search(it.text)]
    for it in term_items:
        qs = _tl.split_questions(it.text)
        if len(qs) > 1 and exit_items and it not in exit_items:
            qs = [q for q in qs if q != "exit"]   # 다른 요청이 이미 중도해지 가능 여부를 묻는다 — 연결 질문을 반복하지 않는다
        for q in qs:
            ans = (_tl.answer_exit if q == "exit" else _tl.answer_cost)(lk, ours=ours or "우리", theirs=theirs or "상대방")
            label = ans["question"]
            linked_q = len(qs) > 1 and q == "exit" and not re.search(r"가능|할\s*수\s*있", it.text)
            fids = [fid[k] for k in (("convenience_termination",) if q == "exit" else ("penalty_scope",)) if k in fid]
            utext = (f"{it.text} — {'(연결 질문) ' if linked_q else ''}{label}") if len(qs) > 1 else it.text
            row = {"request_index": 0, "original_user_text": utext,
                   "topic": "termination", "contract": it.contract, "basis": ans["basis"], "judgment": ans["judgment"],
                   "required_action": ans["required_action"], "additional_checks": ans["additional_checks"],
                   "review_status": ans["review_status"] if ours else "사실관계 추가확인",
                   "needs_revision": ans["needs_revision"] and bool(fids), "answer_clause_paths": ans["answer_clause_paths"],
                   "matched_finding_ids": fids, "override": True,
                   "request_status": ("반영" if fids else "확인 필요" if ans["needs_revision"] else "현행 유지"),
                   "request_status_reason": (("수정안(" + ", ".join(f["redline_instruction"]["edit_location"] for f in findings
                                                             if f["clause_id"] in fids) + ") 반영") if fids else
                                             ("우리 역할 미확정 — 수정안 보류" if not ours else "")),
                   "brief_answer": f"{label}: " + (ans.get("short") or ans["judgment"].split(". ")[0].rstrip(".") + ".")}
            rows.append(row)
    # 포괄 요청("불리한 조항 등 기타 법률 검토") — 요청받지 않았어도 실제 업무에 수반되는 중요 위험(개인정보 처리 흐름 등)을
    # 실제 수정안과 함께 답한다. 다른 분석기가 이미 실질적으로 답했으면 그 답을 둔다(override 아님).
    general = [it for it in items if it.topic == "general" and re.search(r"불리|기타|전반|전체|그\s*밖|법률\s*검토|리스크", it.text)
               and not it.clause_refs]
    if general:
        live = [cr for cr in clause_results if isinstance(cr, dict) and (cr.get("has_rewrite_change") or cr.get("has_addition"))
                and not (cr.get("redline_instruction") or {}).get("held") and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
                and _s(cr.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]
        live.sort(key=lambda c: (0 if _s(c.get("risk_tier")).upper() == "HIGH" else 1))
        bits = []
        for cr in live[:8]:
            loc = _s((cr.get("redline_instruction") or {}).get("edit_location")) or _s(cr.get("display_path"))
            bits.append(f"[{_s(cr.get('risk_tier')).upper()}] {loc}: {_s(cr.get('issue_title')) or _ws(cr.get('problem'))[:60]}")
        if pr.active:
            bits.insert(0, f"개인정보 처리 흐름 {len(pr.activities)}건(활동별 정리는 개인정보 처리 흐름 절) — 처리 관계는 "
                           + ("운영 자료 확인 전이라 보류" if pr.held else "원문으로 확인"))
        for it in general:
            rows.append({"request_index": 0, "original_user_text": it.text, "topic": "general", "contract": it.contract,
                         "basis": ", ".join(dict.fromkeys(_s(c.get("display_path")) for c in live[:8])) or "—",
                         "judgment": ("수정이 필요한 조항: " + "; ".join(bits)) if bits else "수정이 필요한 불리한 조항을 찾지 못함",
                         "required_action": "수정 필요 — 각 수정 문구 참고" if live else "유지",
                         "additional_checks": list(pr.pre_launch[:3]) if pr.active else [],
                         "review_status": "수정 필요" if live else "적정", "needs_revision": bool(live),
                         "answer_clause_paths": list(dict.fromkeys(_s(c.get("display_path")).split(" ")[0] for c in live[:8])),
                         "matched_finding_ids": [_s(c.get("clause_id")) for c in live[:8]],
                         "request_status": "반영" if live else "현행 유지",
                         "request_status_reason": f"수정안 {len(live)}건" if live else "",
                         "brief_answer": (f"불리한 조항 {len(live)}건 수정 — " + "; ".join(b.split(': ')[0] for b in bits[:5])) if bits else
                                         "수정이 필요한 불리한 조항을 찾지 못했습니다."})
    return {"linkage": _trim_linkage(lk), "privacy": pr.to_dict(), "findings": findings, "rows": rows, "superseded": superseded}


def _trim_linkage(lk: Any) -> dict[str, Any]:
    d = lk.to_dict()
    (d.get("penalty") or {}).pop("body", None)
    return d


def ungrounded_labels(text: str, labels: list[str]) -> list[str]:
    """계약서가 당사자 호칭으로 쓰지 않는 갑·을·병·정 — 수정 문구에 나오면 다른 계약 문안이다."""
    out = []
    for lab in _PARTY_LABELS:
        if lab in labels:
            continue
        if re.search(rf"(?<![가-힣]){lab}\s*(?:[（(][^)）]{{0,20}}[)）])?\s*[:：]|[“\"']{lab}[”\"']|(?<![가-힣]){lab}(?:은|는|이|가|에게)\s", text or ""):
            continue
        out.append(lab)
    return out


_RX_EDIT_VERB = (r"(?:다음\s*(?:의\s*)?(?:문단|문장|항|호|목|내용|단서|조항)(?:을|를)?\s*(?P<add>추가|신설|삽입|덧붙이|덧붙인)(?:한다|하여야\s*한다|함)?"
                 r"|(?:을|를)?\s*다음과\s*같이\s*(?P<mod>수정|변경|교체|개정|대체)(?:한다|함)?)")
RX_EDIT_INSTRUCTION = re.compile(r"(?s)^(?P<lead>\s*(?:[①-⑳]|\(\d+\)|\d+(?:\.\d+)*\.?)?\s*)(?P<loc>[^\n'‘“\"]{0,60}?)\s*(?:중\s*|에\s*|의\s*)?"
                                 + _RX_EDIT_VERB + r"\s*[:：]?\s*(?P<body>.+)$")
RX_EDIT_INSTRUCTION_ANY = re.compile(_RX_EDIT_VERB)


def split_edit_instruction(cr: dict[str, Any]) -> str:
    """수정 문구가 "제15조 중 다음 문단을 추가한다: '…'" 같은 편집 지시면 따옴표 안 계약 문장만 본문에 두고 지시는 메모로 옮긴다.
    '추가' 지시는 항 신설(조 끝)로, '수정' 지시는 교체로 바꾼다. 옮긴 지시문을 돌려준다(없으면 "")."""
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else None
    if ri is None:
        ri = {}
        cr["redline_instruction"] = ri
    text = _s(ri.get("final_clause_text") or ri.get("replacement_text") or cr.get("suggested_rewrite"))
    m = RX_EDIT_INSTRUCTION.match(text)
    if not m:
        return ""
    body = m.group("body").strip()
    q = re.match(r"^['‘“\"](?P<in>.+?)['’”\"]\s*\.?\s*$", body, re.S)
    body = (q.group("in") if q else body).strip()
    if len(body) < 10:
        return ""
    lead = _s(m.group("lead"))
    instruction = _ws(text[:m.start("body")])
    new = (lead + " " + body).strip() if lead and not body.startswith(lead) else body
    path = _s(cr.get("display_path")).split(" ")[0] or _s(re.search(r"제\s*\d+\s*조(?:의\s*\d+)?", instruction).group(0)
                                                         if re.search(r"제\s*\d+\s*조", instruction) else "")
    for k in ("replacement_text", "final_clause_text"):
        ri[k] = new
    cr["suggested_rewrite"] = new
    for k in ("recommendation_text", "proposed_revision"):
        if _s(cr.get(k)):
            cr[k] = new
    if m.group("add"):
        ri["edit_type"] = "insert_after"
        ri["edit_mode"] = "new_paragraph"
        ri["target_text"] = ""
        loc = _s(ri.get("edit_location"))
        if "신설" not in loc:
            ri["edit_location"] = f"{path} 끝 문단 신설" if path else loc
    else:
        ri["edit_type"] = "replace"
    cr["has_rewrite_change"] = True
    cr["drafting_memo"] = (_s(cr.get("drafting_memo")) + f" 편집 지시(본문 아님): {instruction}").strip()
    cr["edit_instruction_split"] = instruction
    return instruction


def to_coverage_row(r: dict[str, Any]) -> dict[str, Any]:
    """user_review_coverage 행 — 거래 판단 행(source=deal_request)과 같은 자리에 싣는다."""
    return {
        "issue_id": f"flow_request_{r['request_index']}",
        "source": "deal_request",
        "answer_format": "flow",
        "request_index": r["request_index"],
        "original_user_text": r["original_user_text"],
        "normalized_issue": r["original_user_text"][:120],
        "topic": f"flow:{r.get('topic')}",
        "relevant_clause_paths": list(r.get("answer_clause_paths") or []),
        "answer_clause_paths": list(r.get("answer_clause_paths") or []),
        "review_status": r.get("review_status", ""),
        "needs_revision": bool(r.get("needs_revision")),
        "conclusion": r.get("judgment", ""),
        "direct_answer": r.get("judgment", ""),
        "judgment": r.get("judgment", ""),
        "basis": r.get("basis", ""),
        "existing_protection": "",
        "residual_risk": "",
        "required_action": r.get("required_action", ""),
        "additional_checks": list(r.get("additional_checks") or []),
        "needed_documents": [c for c in r.get("additional_checks") or [] if "원문" in str(c)] if r.get("held") else [],
        "matched_finding_ids": list(r.get("matched_finding_ids") or []),
        "request_status": r.get("request_status", ""),
        "request_status_reason": r.get("request_status_reason", ""),
        "brief_answer": r.get("brief_answer", ""),
        "substantive": True,
        "override": bool(r.get("override")),
        "held": bool(r.get("held")),
        "proposed_clauses": [],
    }


def overlay_rows(coverage: list[dict[str, Any]] | None, df: dict[str, Any] | None) -> list[dict[str, Any]]:
    """흐름 기반 요청 답을 맨 앞에 싣고, 같은 요청을 문장 조각으로 답한 기존 행은 걷어낸다."""
    rows = [dict(r) for r in (df or {}).get("request_rows") or [] if isinstance(r, dict)]
    old = [dict(r) for r in coverage or [] if isinstance(r, dict) and r.get("answer_format") != "flow"]
    if not rows:
        return old
    # 걷어내는 것은 (1) 같은 요청을 문장 조각으로 나눠 답한 행, (2) 같은 조항을 지목한 지정 조항 행뿐이다 — 다른 요청의
    # 답(다른 분석기가 주제별로 답한 행)은 그대로 둔다(2026-11-09: 와이어드·브랜디드 골든의 요청 답이 사라졌다).
    squash = lambda t: re.sub(r"[\s\-–·•●①-⑳()（）*]+", "", str(t or ""))  # noqa: E731
    def _matches(mine: dict[str, Any], r: dict[str, Any]) -> bool:
        a, t = squash(mine.get("original_user_text")), squash(r.get("original_user_text"))
        if t and len(t) >= 6 and (t in a or (len(a) >= 6 and a in t)):
            return True
        paths = {re.sub(r"\s", "", p) for p in re.findall(r"제\s*\d+\s*조", str(mine.get("original_user_text") or ""))}
        return r.get("source") == "user_focus_target" and any(re.sub(r"\s", "", str(x)) in paths
                                                               for x in r.get("relevant_clause_paths") or [])

    def _substantive(r: dict[str, Any]) -> bool:
        """다른 분석기가 이미 실질적으로 답한 행인가 — 비었거나 '현행 유지 —' 만 있으면 아니다."""
        if r.get("source") not in ("user_request", "user_focus_target", "deal_request"):
            return False
        c = str(r.get("conclusion") or r.get("direct_answer") or "")
        return len(re.sub(r"[\s—\-–:：.]|현행\s*유지", "", c)) >= 20 and not c.startswith("관련 조항이 계약에 존재")

    out_rows: list[dict[str, Any]] = []
    drop: set[int] = set()
    for mine in rows:
        hits = [i for i, r in enumerate(old) if _matches(mine, r)]
        if any(_substantive(old[i]) for i in hits) and not mine.get("held") and not mine.get("override"):
            continue   # 기존 답을 유지한다(같은 요청을 두 번 답하지 않는다)
        drop.update(hits)
        out_rows.append(mine)
    return out_rows + [r for i, r in enumerate(old) if i not in drop]


__all__ = ["DealFlow", "RoleResolution", "SECTION_TITLE", "answer_requests", "core_revisions", "extract_flow", "fact_errors",
           "figure_checks", "guidance_sentences", "linked_review", "overlay_rows", "split_edit_instruction", "ungrounded_labels", "parse_parties", "parse_request", "request_row_lines",
           "resolve_role", "run_deal_flow_stage", "scenarios", "section_lines", "stages", "strip_guidance"]
