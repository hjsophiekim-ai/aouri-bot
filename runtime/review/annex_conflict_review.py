"""본계약 ↔ 별첨 구조 비교 + 별첨의 가맹사업 실질 판단 (2026-10-13 긴급 보정 4·5·7·8·9항).

실측(일룸 ↔ ㈜아트앤라이프 물품거래계약서 + [별첨] 그림닷컴 큐레이션 샵 프랜차이즈 가맹)
──────────────────────────────────────────────────────────────────────────
사업부 요청: "[별첨] 프랜차이즈 가맹 내용 검토 : 물품공급계약과 프랜차이즈 가맹 내용 상충 여부".

수정 전 결과: 별첨이 제27조(유효기간) 원문에 묶여 요청이 제27조로 매핑됐고 "적정 — 수정 불필요" 로
끝났다. 실제로는 본문 제13조 제3항(종료 시 "갑" 반환 → "을" 공급가격 상환)과 별첨 12. 2)(가맹본부가
판화·원화만 "매입할 수 있다")가 정면으로 다르고, 본문 제15조(월합계 60일 후불)와 별첨 4. 4)(초도물량
영업 개시 전 선납)가 다르며, 우선순위 조항도 없다. 별첨의 AI 서술은 일룸을 가맹본부로 적었다.

이 모듈의 계약
    1. 별첨 구간을 항목(1. 2. …)·세목(1) 2) …)으로 나누고, 본문 조·항과 **축별로** 짝지어 비교한다.
       판단은 원문 문언으로만 한다 — 원문에 없는 축은 "해당 없음" 이고 finding 을 만들지 않는다.
    2. 충돌·불일치 축은 CONTRACT_APPENDIX_CONFLICT finding 으로, 양쪽 조항을 정확히 인용하고
       수정문구를 붙인다(별첨 쪽 수정 + 본문 쪽 연계 수정).
    3. 별첨이 영업표지 사용허락·영업방식 통제·지원·가맹금·계속거래를 정하면 가맹사업법 적용 가능성을
       **요건별로** 본다. 가맹금(차액가맹금 포함)·소규모 가맹본부 적용배제는 원문만으로 알 수 없으므로
       "적용 확정" 이라고 쓰지 않는다.
    4. 별첨의 역할(가맹본부/가맹점사업자)을 본문 당사자(갑/을)에 연결한다 — 별첨이 법인명이 아니라
       영업표지("그림닷컴")로 당사자를 부르면 그 표지의 주인은 우리 회사가 아닌 쪽이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

STATUS_APPENDIX_CONFLICT = "CONTRACT_APPENDIX_CONFLICT"

CONFLICT = "충돌"
MISMATCH = "불일치"
SUPPLEMENT = "보완 관계(충돌 없음)"
ANNEX_ONLY = "별첨만 규정(충돌 없음)"
MAIN_ONLY = "본문만 규정(충돌 없음)"
NOT_PRESENT = "해당 없음"

_RX_ANNEX_PATH = re.compile(r"^\[\s*(?:별첨|부속서|첨부)")
_RX_PAGE_NOISE = re.compile(r"^\s*(?:-\s*\d+\s*/\s*\d+\s*-|\[페이지\s*\d+\])\s*$")
_RX_ITEM = re.compile(r"^(\d{1,2})\.\s*(\S.*)$")
_RX_SUB = re.compile(r"^(\d{1,2})\)\s*(.*)$")
_Q = "[“”\"]"


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _lines(text: str) -> list[str]:
    return [ln for ln in str(text or "").splitlines() if ln.strip() and not _RX_PAGE_NOISE.match(ln)]


# ── 구조 파싱 ────────────────────────────────────────────────────────────────

@dataclass
class Part:
    """본문 조의 항(1. 2. …) 또는 별첨 항목/세목 하나. text 는 원문 그대로(줄바꿈 보존)."""

    path: str
    text: str
    title: str = ""
    subs: dict[str, "Part"] = field(default_factory=dict)


def _numbered(lines: list[str], rx: re.Pattern[str]) -> list[tuple[str, list[str]]]:
    """번호가 1부터 차례로 올라가는 줄만 경계로 삼는다(본문 속 "1." 인용을 경계로 오인하지 않게)."""
    out: list[tuple[str, list[str]]] = []
    expect = 1
    for ln in lines:
        m = rx.match(ln.strip())
        if m and int(m.group(1)) == expect:
            out.append((m.group(1), [ln]))
            expect += 1
        elif out:
            out[-1][1].append(ln)
    return out


def parse_annex(chunk: Any) -> list[Part]:
    """별첨 구간 → 항목 목록. 항목 안의 세목 "1) 2)" 도 나눈다(같은 번호가 다시 나오면 앞 세목에 붙인다)."""
    body = _lines(_attr(chunk, "text"))
    items: list[Part] = []
    for num, block in _numbered(body, _RX_ITEM):
        title = _RX_ITEM.match(block[0].strip()).group(2).strip()
        part = Part(path=f"[별첨] {num}.", title=title, text="\n".join(block))
        for snum, sblock in _numbered(block[1:], _RX_SUB):
            part.subs[snum] = Part(path=f"[별첨] {num}. {snum})", text="\n".join(sblock), title=title)
        items.append(part)
    return items


def _article(clauses: list[Any], num: str) -> Any | None:
    return next((c for c in clauses if _attr(c, "article_number") == num and not _attr(c, "paragraph_number")), None) \
        or next((c for c in clauses if _attr(c, "article_number") == num), None)


def article_paragraphs(chunk: Any) -> dict[str, Part]:
    """본문 조 하나 → {항 번호: Part}. "1." 형식 항을 쓰는 계약용(원문자 항은 clause 가 이미 나뉘어 있다)."""
    art = _attr(chunk, "article_number")
    lines = _lines(_attr(chunk, "text"))[1:]
    return {n: Part(path=f"제{art}조 제{n}항", text="\n".join(b)) for n, b in _numbered(lines, _RX_ITEM)}


def _find(parts: dict[str, Part] | list[Part], rx: str) -> Part | None:
    seq = parts.values() if isinstance(parts, dict) else parts
    return next((p for p in seq if re.search(rx, _flat(p.text))), None)


def _find_sub(items: list[Part], rx: str) -> Part | None:
    for it in items:
        for sp in it.subs.values():
            if re.search(rx, _flat(sp.text)):
                return sp
    return None


# ── 당사자 역할 ──────────────────────────────────────────────────────────────

@dataclass
class AnnexRoles:
    franchisor_label: str = ""
    franchisor_name: str = ""
    franchisor_annex_name: str = ""
    franchisee_label: str = ""
    franchisee_name: str = ""
    linked_in_text: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "가맹본부": {"label": self.franchisor_label, "name": self.franchisor_name,
                      "annex_name": self.franchisor_annex_name},
            "가맹점사업자": {"label": self.franchisee_label, "name": self.franchisee_name},
            "linked_in_text": self.linked_in_text,
        }

    def sentence(self) -> str:
        if not self.franchisor_label:
            return ""
        fe = self.franchisee_name or "우리 회사"
        return (f"본문에서는 {_p(fe, '이', '가')} “{self.franchisee_label}”, "
                f"{_p(self.franchisor_name, '이', '가')} “{self.franchisor_label}”이고, 별첨에서는 "
                f"{self.franchisor_name}({self.franchisor_annex_name or '영업표지 보유자'})가 가맹본부, "
                f"{_p(fe, '이', '가')} 가맹점사업자입니다.")


def resolve_annex_roles(full_text: str, parties: list[Any]) -> AnnexRoles:
    """별첨의 "X(가맹본부)" 를 본문 당사자에 연결한다.

    X 가 우리 회사 이름이 아니면 상대방이다 — 영업표지(브랜드)로 적혀 있어도 마찬가지다.
    """
    m = re.search(r"([가-힣A-Za-z0-9·]+)\s*\(\s*가맹본부\s*\)", full_text or "")
    if not m:
        return AnnexRoles()
    name = m.group(1)
    ours = [p for p in parties if getattr(p, "is_our_company", False) and getattr(p, "label", "")]
    theirs = [p for p in parties if not getattr(p, "is_our_company", False) and getattr(p, "label", "")
              and not getattr(p, "alias_of", "")]

    def names(p: Any) -> list[str]:
        return [str(getattr(p, k, "") or "") for k in ("written_name", "legal_entity_name", "brand_name")]

    we_are_franchisor = any(name and any(name in n or n.replace("㈜", "").replace("주식회사", "").strip() in name
                                         for n in names(p) if n) for p in ours)
    fr, fe = (ours, theirs) if we_are_franchisor else (theirs, ours)
    if not fr or not fe:
        return AnnexRoles(franchisor_annex_name=name)
    linked = bool(re.search(r"가맹본부[^.\n]{0,20}" + _Q + r"?(?:을|갑)" + _Q, full_text or ""))
    return AnnexRoles(
        franchisor_label=str(fr[0].label), franchisor_name=str(fr[0].legal_entity_name or fr[0].written_name),
        franchisor_annex_name=name,
        franchisee_label=str(fe[0].label), franchisee_name=str(fe[0].legal_entity_name or fe[0].written_name),
        linked_in_text=linked,
    )


# ── 가맹사업 실질 판단 ──────────────────────────────────────────────────────

_FRANCHISE_SIGNALS: tuple[tuple[str, str], ...] = (
    ("영업표지 사용허락", r"영업표지[^.]{0,30}사용권|영업표지[^.]{0,20}사용(?:을)?\s*허"),
    ("영업방식·품질기준 통제", r"영업시스템|영업표준화|영업규정|통일성"),
    ("경영·영업 지원(교육·노하우)", r"노하우|교육|경영지원|지도"),
    ("상품 구입강제", r"반드시[^.]{0,30}(?:로부터|에서)\s*공급받"),
    ("초도물량·상품 공급대가 지급", r"초도\s*물량|공급가격|계속가맹금"),
    ("가맹본부·가맹점사업자 호칭", r"가맹본부|가맹점사업자"),
    ("광고·판촉 비용 분담", r"(?:광고|판촉)[^.]{0,60}비용"),
)


def franchise_signals(annex_text: str) -> list[str]:
    flat = _flat(annex_text)
    return [label for label, rx in _FRANCHISE_SIGNALS if re.search(rx, flat)]


def franchise_assessment(items: list[Part], roles: AnnexRoles) -> dict[str, Any]:
    """가맹사업법 제2조 제1호 요건별 판단. 원문으로 확인되지 않는 요건은 '확인 필요' 로 둔다."""
    def ref(rx: str) -> str:
        sp = _find_sub(items, rx)
        if sp is not None:
            return sp.path
        it = _find(items, rx)
        return it.path if it is not None else ""

    reqs = []
    for label, rx, unknown_note in (
        ("영업표지 사용 허락", r"영업표지[^.]{0,30}사용권", ""),
        ("가맹본부가 정한 품질기준·영업방식에 따른 판매", r"영업규정|영업표준화|통일성", ""),
        ("경영·영업활동에 대한 지원·교육·통제", r"노하우|교육|경영지원", ""),
        ("계속적 거래관계", r"계약기간\s*중|초도\s*물량|공급받", ""),
    ):
        r = ref(rx)
        reqs.append({"requirement": label, "status": "충족" if r else "확인 필요", "basis": r or unknown_note})
    no_initial_fee = ref(r"최초가맹금을\s*수령하지\s*아니")
    price_ref = ref(r"공급받는\s*가격|공급가격")
    reqs.append({
        "requirement": "가맹금 지급(가맹사업법 제2조 제6호 — 가입비뿐 아니라 상품 공급대가 중 적정 도매가격을 넘는 부분 포함)",
        "status": "확인 필요",
        "basis": (f"{no_initial_fee}는 최초가맹금을 받지 않는다고 정하지만, {price_ref}의 상품 공급대가에 적정 "
                  "도매가격을 넘는 부분(차액가맹금)이 있으면 가맹금 지급 요건을 충족합니다."
                  if no_initial_fee else "가맹금 지급 구조를 원문으로 확인하지 못했습니다."),
    })
    met = sum(1 for r in reqs if r["status"] == "충족")
    likely = met >= 3
    who = (f"{roles.franchisor_name}(별첨상 가맹본부)" if roles.franchisor_name else "가맹본부")
    them = roles.franchisee_name or "우리 회사"
    return {
        "law": "가맹사업거래의 공정화에 관한 법률",
        "likelihood": "높음(확정 아님)" if likely else "확인 필요",
        "requirements": reqs,
        "open_facts": [
            "상품 공급가격에 적정 도매가격을 넘는 부분(차액가맹금)이 있는지 — 가맹금 지급 요건",
            "가맹사업법 제3조 소규모 가맹본부 적용배제 해당 여부(가맹금 총액·가맹본부 연간 매출액 기준)",
            f"{who}의 정보공개서 등록 여부와 계약 체결 전 정보공개서·가맹계약서 사전 제공 여부(가맹사업법 제7조·제11조)",
        ],
        "conclusion": (
            f"형식은 물품공급계약이지만, 별첨은 영업표지 사용허락·영업표준화·교육 지원·구입강제·초도물량 구매를 "
            f"정하고 있어 실질은 가맹사업 구조에 가깝습니다. 가맹금(차액가맹금 포함) 지급과 소규모 가맹본부 "
            f"적용배제 여부를 확인하기 전에는 적용을 확정할 수 없으나, 적용된다면 {_p(them, "은", "는")} 가맹점사업자로서 "
            f"정보공개서 사전 제공(가맹사업법 제7조), 계약갱신요구권(가맹사업법 제13조), 부당한 계약해지 제한(가맹사업법 제14조: "
            f"2개월 이상의 유예기간을 두고 2회 이상 서면 시정요구) 등의 보호를 받고, 의무 이행 주체는 {who}입니다."
            if likely else
            "별첨에 가맹사업 요소가 일부 있으나 요건 대부분을 원문으로 확인하지 못해 적용 가능성을 판단하려면 "
            "사실관계 확인이 필요합니다."
        ),
        "franchisor": roles.franchisor_label, "franchisee": roles.franchisee_label,
    }


# ── 축별 비교 ───────────────────────────────────────────────────────────────

@dataclass
class AxisRow:
    axis: str
    main_refs: list[str]
    annex_refs: list[str]
    status: str
    note: str
    finding_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"axis": self.axis, "main_refs": self.main_refs, "annex_refs": self.annex_refs,
                "status": self.status, "note": self.note, "finding_key": self.finding_key,
                "code": STATUS_APPENDIX_CONFLICT if self.status in (CONFLICT, MISMATCH) else ""}


@dataclass
class AnnexReview:
    applies: bool = False
    annex_path: str = ""
    roles: AnnexRoles = field(default_factory=AnnexRoles)
    franchise: dict[str, Any] = field(default_factory=dict)
    rows: list[AxisRow] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)

    @property
    def conflicts(self) -> list[AxisRow]:
        return [r for r in self.rows if r.status in (CONFLICT, MISMATCH)]

    def summary_lines(self) -> list[str]:
        return [f"{r.axis}: {' · '.join(r.main_refs) or '본문 없음'} ↔ {' · '.join(r.annex_refs) or '별첨 없음'} "
                f"— {r.status}" + (f" ({r.note})" if r.note else "") for r in self.rows if r.status != NOT_PRESENT]

    def to_dict(self) -> dict[str, Any]:
        return {
            "applies": self.applies, "annex_path": self.annex_path, "roles": self.roles.to_dict(),
            "franchise_assessment": self.franchise, "rows": [r.to_dict() for r in self.rows],
            "conflict_count": len(self.conflicts),
            "finding_ids": [str(f.get("clause_id")) for f in self.findings],
        }


#: finding 제목 — 보고서 목록·요약에 그대로 나가는 한 줄.
_ISSUE_TITLES: dict[str, str] = {
    "annex_precedence": "[본계약↔별첨] 우선순위·당사자 연결 조항 부재 (CONTRACT_APPENDIX_CONFLICT)",
    "annex_exit_inventory": "[본계약↔별첨 충돌] 계약 종료 시 미판매 작품 처리 — 본문 반품·상환 vs 별첨 재량 매입",
    "annex_payment_timing": "[본계약↔별첨 충돌] 초도물량 대금 — 본문 후불 vs 별첨 영업 개시 전 선납",
    "annex_price_change": "[본계약↔별첨 불일치] 공급가격 결정·변경 기준 이원화, 존재하지 않는 변경 절차 인용",
    "annex_tying_scope": "[별첨] 구입강제 범위 불특정 — 매장 전체 미술품 판매로 확대 해석 위험",
    "annex_termination": "[본계약↔별첨 충돌] 구입강제 위반 해지 — 본문에 없는 해지사유·절차 부재",
    "annex_term_link": "[본계약↔별첨 불일치] 기본계약 1년 vs 별첨 운영기간 미정 — 종료 연동 없음",
}


def _q(label: str) -> str:
    return f"“{label}”"


def _p(word: str, with_b: str, without_b: str) -> str:
    core = re.sub(r"[\s“”\"'()「」]+$", "", word or "")
    last = core[-1:] if core else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _base(anchor: Part, chunk: Any, *, key: str, tier: str, **kw: Any) -> dict[str, Any]:
    base = {
        "clause_id": f"ax_{key}__{_attr(chunk, 'clause_id')}",
        "clause_title": anchor.title or _attr(chunk, "title"),
        "display_path": anchor.path,
        "article_number": _attr(chunk, "article_number"),
        "paragraph_number": "",
        "original_text": anchor.text,
        "risk_tier": tier, "severity": tier, "review_tier": "MUST" if tier == "HIGH" else "SUGGEST",
        "must_fix": tier == "HIGH", "confidence": 0.95,
        "is_common_legal_risk": True, "legal_core": True, "is_annex_conflict": True,
        "legal_effect_code": STATUS_APPENDIX_CONFLICT,
    }
    base.update(kw)
    base.setdefault("issue_title", _ISSUE_TITLES.get(key, ""))
    base.setdefault("detected_issue_list", [{"issue_title": base["issue_title"]}] if base.get("issue_title") else [])
    base.setdefault("rewrite_reason", base.get("problem", ""))
    base.setdefault("recommendation_text", base.get("suggested_rewrite", ""))
    base.setdefault("proposed_revision", base.get("suggested_rewrite", ""))
    base.setdefault("negotiation_strategy", base.get("negotiation_position", ""))
    base.setdefault("location_instruction", f"{anchor.path} 교체")
    base["has_rewrite_change"] = True
    linked = base.get("package_linked_edits") or []
    base["related_clause_paths"] = list(dict.fromkeys(
        [anchor.path] + [str(p) for p in base.get("related_clause_paths") or []]
        + [str(e.get("display_path") or "") for e in linked]))
    if linked:
        base["problem"] = str(base["problem"]) + " [연계 수정] " + " / ".join(
            f"{e['display_path']}: {e['text']}" for e in linked)
    return base


def review_annex(
    *, clauses: list[Any] | None, full_text: str, parties: list[Any],
) -> AnnexReview:
    clauses = list(clauses or [])
    chunk = next((c for c in clauses if _RX_ANNEX_PATH.match(_attr(c, "display_path"))), None)
    if chunk is None:
        return AnnexReview()
    items = parse_annex(chunk)
    if not items:
        return AnnexReview()
    roles = resolve_annex_roles(full_text, parties)
    annex_text = _attr(chunk, "text")
    signals = franchise_signals(annex_text)
    rv = AnnexReview(applies=True, annex_path=_attr(chunk, "display_path"), roles=roles)
    if len(signals) >= 4 and "가맹본부·가맹점사업자 호칭" in signals:
        rv.franchise = franchise_assessment(items, roles)
        rv.franchise["signals"] = signals

    fr_q = _q(roles.franchisor_label) if roles.franchisor_label else "가맹본부"
    fe_q = _q(roles.franchisee_label) if roles.franchisee_label else "가맹점사업자"
    arts = {_attr(c, "article_number"): c for c in clauses if _attr(c, "article_number") and not _attr(c, "paragraph_number")}
    paras = {n: article_paragraphs(c) for n, c in arts.items()}
    max_art = max((int(n) for n in arts if n.isdigit()), default=0)
    addendum = next((c for c in clauses if _attr(c, "display_path").startswith("[부칙")), None)
    add_parts = {n: Part(path=f"[부칙] 제{n}항", text="\n".join(b),
                         title=_RX_ITEM.match(b[0].strip()).group(2).strip()) for n, b in
                 _numbered(_lines(_attr(addendum, "text"))[1:], _RX_ITEM)} if addendum is not None else {}

    def main_para(rx: str) -> Part | None:
        for n in sorted(paras, key=lambda x: int(x) if x.isdigit() else 999):
            p = _find(paras[n], rx)
            if p is not None:
                return p
        for n, c in arts.items():
            if not paras.get(n) and re.search(rx, _flat(_attr(c, "text"))):
                return Part(path=f"제{n}조", text=_attr(c, "text"))
        return None

    rows: list[AxisRow] = []
    findings: list[dict[str, Any]] = []

    # 1. 우선순위 + 당사자 역할 연결 ────────────────────────────────────────
    ref_clause = _find(add_parts, r"별첨") if add_parts else None
    precedence = re.search(r"(?:별첨|부속서)[^.\n]{0,40}(?:우선|우선하여|우선한다)|본문[^.\n]{0,30}우선", full_text or "")
    ind_priority = main_para(r"개별계약[^.]{0,40}우선적\s*효력")
    rows.append(AxisRow(
        "당사자 역할", [], [items[0].path] if roles.franchisor_annex_name else [],
        MISMATCH if roles.franchisor_label and not roles.linked_in_text else (SUPPLEMENT if roles.franchisor_label else NOT_PRESENT),
        (roles.sentence() + " 별첨에는 ‘가맹본부 = " + fr_q + ", 가맹점사업자 = " + fe_q + "’라는 연결 정의가 없고 "
         f"법인명이 아닌 영업표지({roles.franchisor_annex_name})로 당사자를 적었습니다.")
        if roles.franchisor_label and not roles.linked_in_text else roles.sentence(),
        "annex_precedence" if roles.franchisor_label and not roles.linked_in_text else "",
    ))
    rows.append(AxisRow(
        "우선순위 조항", [p.path for p in (ref_clause, ind_priority) if p is not None], [],
        NOT_PRESENT if precedence else MISMATCH,
        "" if precedence else (
            (f"{_p(ref_clause.path, '은', '는')} 별첨을 끌어오기만 하고" if ref_clause is not None else "별첨을 끌어오는 조항은 있으나")
            + (f", {ind_priority.path}의 우선 규정은 개별계약에 관한 것이라" if ind_priority is not None else "")
            + " 본문과 별첨이 다를 때 어느 쪽이 우선하는지 정한 조항이 없습니다."),
        "annex_precedence" if not precedence else "",
    ))

    # 2. 종료 후 재고 처리·반품/매입 ───────────────────────────────────────────
    m_return = main_para(r"종료된?\s*때[^.]{0,60}반환[^.]{0,60}상환")
    exit_item = next((it for it in items if re.search(r"종료", it.title)), None)
    a_buyback = _find(exit_item.subs, r"매입할\s*수\s*있") if exit_item is not None else None
    a_fault_buyback = _find_sub(items, r"귀책사유로[^.]{0,80}(?:해지|불가능)[^.]{0,80}전부\s*매입")
    if m_return is not None and a_buyback is not None:
        rows.append(AxisRow("반품/매입 · 계약종료 후 재고처리", [m_return.path],
                            [a_buyback.path] + ([a_fault_buyback.path] if a_fault_buyback else []), CONFLICT,
                            "본문은 종료 시 완전물 전부를 반환하고 공급가격으로 상환받게 하나, 별첨은 가맹본부가 판화·원화만 "
                            "재량으로 매입할 수 있고 대상·수량도 협의로 정합니다.", "annex_exit_inventory"))
        art13 = m_return.path.split(" ")[0]
        findings.append(_base(
            a_buyback, chunk, key="annex_exit_inventory", tier="HIGH",
            problem=(f"계약 종료 후 미판매 작품의 처리가 본문과 별첨에서 서로 다릅니다. {m_return.path}은 종료 시 "
                     f"{_p(fe_q, '이', '가')} 완전물을 {fr_q}에게 반환하고 {_p(fr_q, '은', '는')} 공급가격으로 상환하도록 하여 재고 위험을 "
                     f"{fr_q}에게 두지만, {a_buyback.path}는 가맹본부가 판화·원화에 한하여 공급가격 기준으로 "
                     "‘매입할 수 있다’고만 하고 매입 대상·수량을 종료 시 협의로 정합니다. 프린트·사진·액자 상품은 매입 "
                     "대상에서 빠지고, 판화·원화도 매입 여부가 상대방 재량입니다."),
            legal_business_reason=(
                "같은 사항을 두 규정이 다르게 정하고 우선순위 조항이 없으면, 분쟁 시 상대방은 특별 규정인 별첨을 "
                "근거로 매입을 거절할 수 있습니다. 미술품은 다른 판매처로 돌리기 어려운 재고라 종료 시점의 반품권이 "
                "곧 재고 위험의 배분입니다."),
            suggested_rewrite=(
                f"2) 제1항의 경우 가맹점사업자가 보유한 미판매 작품(액자 등 부속품을 포함한다)의 처리는 본문 {art13} "
                f"제3항에 따른다. 가맹본부는 가맹점사업자가 반환을 요청한 작품을 반환받고 그 공급가격(납품가)을 "
                f"반환일부터 30일 이내에 지급하여야 한다."),
            location_instruction=f"{a_buyback.path} 교체",
            related_clause_paths=[m_return.path] + ([a_fault_buyback.path] if a_fault_buyback else []),
            negotiation_position=("본문 제13조 제3항은 상대방이 이미 서명한 기준이므로 '본문과 맞추자'는 요구는 거절 명분이 "
                                  "약합니다. 전 품목 매입이 어렵다고 하면 원화·판화는 전량, 프린트·액자는 미개봉 완전물로 "
                                  "범위를 나누는 안을 2차로 제시하십시오."),
            high_severity_basis="종료 시 재고 반품권(본문)과 가맹본부 재량 매입(별첨) 충돌 — 재고 위험 배분이 뒤바뀜",
        ))

    # 3. 대금 지급 시기 ───────────────────────────────────────────────────────
    m_pay = main_para(r"대금[^.]{0,80}지급[^.]{0,200}\d+\s*일\s*이내")
    a_prepay = _find_sub(items, r"(?:개시일?|영업\s*개시)\s*전까지\s*납부|선급|선납")
    if m_pay is not None and a_prepay is not None:
        days = re.search(r"(\d+)\s*일\s*이내", _flat(m_pay.text))
        rows.append(AxisRow("대금 지급", [m_pay.path], [a_prepay.path], CONFLICT,
                            f"본문은 월합계 후 {days.group(1) if days else '일정 기간'}일 이내 지급, 별첨은 초도물량 대금을 "
                            "영업 개시 전 선납.", "annex_payment_timing"))
        findings.append(_base(
            a_prepay, chunk, key="annex_payment_timing", tier="MEDIUM",
            problem=(f"{m_pay.path}은 거래 대금을 월 단위로 합산해 정산일부터 "
                     f"{days.group(1) if days else '일정 기간'}일 이내에 지급하도록 하지만, {a_prepay.path}는 초도물량 "
                     "구매대금을 영업 개시일 전까지 납부하도록 합니다. 초도물량도 이 계약의 물품 거래인데 지급 시기가 "
                     f"두 가지로 정해져 있고, 별첨대로면 {_p(fe_q, '이', '가')} 검사(제13조) 전에 대금을 먼저 내게 됩니다."),
            legal_business_reason=("선납하면 하자·수량 부족이 있어도 대금 지급을 미뤄 다툴 수단(동시이행)이 없어집니다. "
                                   "초도물량은 금액이 가장 큰 1회 거래라 지급 조건 차이가 그대로 노출 규모입니다."),
            suggested_rewrite=(f"4) 가맹점사업자는 초도물량 구매대금을 본문 {m_pay.path}에 따라 지급한다. 다만 당사자가 "
                               "서면으로 달리 합의한 경우에는 그에 따른다."),
            location_instruction=f"{a_prepay.path} 교체",
            related_clause_paths=[m_pay.path],
            negotiation_position="본문 지급조건으로 통일하자는 요구입니다. 선납을 고집하면 검수 완료 후 지급으로 절충하십시오.",
        ))

    # 4. 공급가격 + 존재하지 않는 조항 인용 ───────────────────────────────────
    m_price = main_para(r"단가는[^.]{0,120}협의")
    a_price = _find(items, r"공급받는\s*가격|할인율")
    a_change = _find_sub(items, r"(?:공급가격|할인율)[^.]{0,80}변경")
    dangling = []
    if a_change is not None:
        dangling = [n for n in re.findall(r"제\s*(\d{1,3})\s*조", _flat(a_change.text)) if int(n) > max_art]
    if a_price is not None and m_price is not None:
        rows.append(AxisRow("대금/공급가격", [m_price.path], [a_price.path] + ([a_change.path] if a_change else []),
                            MISMATCH,
                            "본문은 단가를 개별 협의로 정하고, 별첨은 소비자 판매가 기준 할인율 표로 정합니다"
                            + (f"; 별첨이 인용한 {dangling[0]}조(거래조건 변경 협의 절차)는 이 계약에 없습니다." if dangling else "."),
                            "annex_price_change" if (a_change is not None) else ""))
        if a_change is not None:
            missing_ref = (f" 또한 변경 절차로 인용한 ‘{dangling[0]}조의 거래조건 변경 협의 절차’는 이 계약(제{max_art}조까지)에 "
                           "없는 조항이어서, 변경 절차가 사실상 정해져 있지 않습니다." if dangling else "")
            findings.append(_base(
                a_change, chunk, key="annex_price_change", tier="MEDIUM",
                problem=(f"공급가격의 결정·변경 기준이 이원화되어 있습니다. {m_price.path}은 단가를 “갑”과 “을”의 협의로 "
                         f"정하고 변경도 협의하도록 하지만, {a_price.path}는 미술품 공급가격을 소비자 판매가 기준 할인율로 "
                         f"정하고 {a_change.path}는 시장 환경·원가율 변동을 이유로 협의를 거쳐 변경할 수 있다고 합니다."
                         + missing_ref),
                legal_business_reason=("소비자 판매가는 가맹본부가 정하므로, 할인율이 같아도 판매가를 올리면 공급가격이 오릅니다. "
                                       "변경 절차와 효력 발생 시점이 없으면 이미 발주한 물량에도 변경 가격을 주장할 여지가 생깁니다."),
                suggested_rewrite=("4) 공급가격 및 할인율은 시장 환경 변화, 원가율 변동 등을 고려하여 가맹본부와 가맹점사업자의 "
                                   "협의를 거쳐 변경할 수 있다. 단, 변경은 당사자가 서면으로 합의한 경우에만 효력이 있고, "
                                   "변경된 공급가격은 합의일 이후 발주분부터 적용하며, 소비자 판매가격의 변경으로 공급가격이 "
                                   "오르는 경우에도 같다."),
                location_instruction=f"{a_change.path} 교체",
                related_clause_paths=[m_price.path, a_price.path],
                negotiation_position="서면 합의·장래 발주분 적용은 통상적 요구라 수용 가능성이 높습니다.",
            ))

    # 5. 재고/초도물량 ─────────────────────────────────────────────────────────
    a_initial = _find_sub(items, r"초도\s*물량에\s*대해\s*구매하여야|초도\s*물량[^.]{0,30}구매하여야")
    m_order = main_para(r"발주할\s*때") or main_para(r"발주")
    if a_initial is not None:
        rows.append(AxisRow("재고/초도물량", [m_order.path] if m_order else [], [a_initial.path], SUPPLEMENT,
                            "본문은 개별 발주로 거래하고, 별첨은 영업 개시 전 초도물량 구매의무를 더합니다(수량·금액은 협의)."))

    # 6. 하자/품질 ─────────────────────────────────────────────────────────────
    m_def = main_para(r"하자\s*보증|하자를\s*발견")
    a_direct = _find_sub(items, r"본사\s*직접\s*배송\s*판매\s*건\W{0,3}이라") or _find_sub(items, r"본사\s*직접\s*배송")
    m_warranty = main_para(r"하자\s*보증\s*책임을\s*지")
    if m_def is not None:
        rows.append(AxisRow("하자/품질책임", list(dict.fromkeys([m_def.path] + ([m_warranty.path] if m_warranty else []))), [a_direct.path] if a_direct else [], MAIN_ONLY,
                            "하자 책임은 본문만 정합니다" + ("; 별첨의 ‘본사 직접 배송 판매 건’은 일룸의 검사 없이 고객에게 "
                                                    "바로 인도되므로 하자·파손 처리 주체를 본문 제16조에서 정해야 합니다." if a_direct else ".")))

    # 7. 지식재산권 · 브랜드 사용 ─────────────────────────────────────────────
    m_ip = main_para(r"지적재산권|지식재산권")
    a_ip = _find(items, r"지식재산권의\s*확보|영업표지에\s*대한\s*배타적")
    if m_ip is not None or a_ip is not None:
        rows.append(AxisRow("지식재산권", [m_ip.path] if m_ip else [], [a_ip.path] if a_ip else [], SUPPLEMENT,
                            "본문은 계약물품의 권리 비침해를, 별첨은 영업표지 권리 확보를 각각 상대방이 보증합니다."))
    m_mark = main_para(r"상표를\s*도용")
    m_label = main_para(r"상표의\s*표시")
    a_brand = _find(items, r"가맹점운영권|영업표지[^.]{0,20}사용권")
    if a_brand is not None:
        rows.append(AxisRow("브랜드 사용", [p.path for p in (m_label, m_mark) if p is not None], [a_brand.path],
                            MISMATCH if m_mark is not None else SUPPLEMENT,
                            ("본문 해지사유는 ‘“을”이 “갑”의 상표를 도용한 경우’만 두지만, 별첨에서 영업표지를 쓰는 쪽은 "
                             f"{fe_q}이고 표지의 주인은 {fr_q}입니다 — 방향이 반대입니다.") if m_mark is not None else
                            "본문은 계약물품의 상표 표시를, 별첨은 가맹점 영업표지 사용을 정합니다.",
                            "annex_termination" if m_mark is not None else ""))

    # 8. 광고/판촉 · 권장가격 ──────────────────────────────────────────────────
    a_ad = _find(items, r"광고를\s*시행")
    a_promo = _find(items, r"판촉")
    if a_ad or a_promo:
        rows.append(AxisRow("광고/판촉", [], [p.path for p in (a_ad, a_promo) if p], ANNEX_ONLY,
                            "가맹점사업자 비용 부담 광고·판촉은 사전 동의와 개별 거부권이 있습니다."))
    a_rrp = _find(items, r"소비자가격을\s*권장")
    if a_rrp is not None:
        rows.append(AxisRow("권장가격", [], [a_rrp.path], ANNEX_ONLY,
                            "권장가격은 구속력이 없어야 합니다 — 판매가 변경 시 ‘협의’ 의무가 사실상 가격 구속이 되지 않게 운영해야 합니다."))

    # 9. 독점/구입강제 ─────────────────────────────────────────────────────────
    a_tying = _find_sub(items, r"반드시\s*가맹본부로부터\s*공급받")
    if a_tying is not None:
        rows.append(AxisRow("독점/구입강제", [], [a_tying.path], ANNEX_ONLY,
                            "‘가맹점에서 판매하는 모든 미술품 관련 상품’을 가맹본부로부터만 공급받아야 합니다 — 가맹점이 "
                            "데스커 매장 안에 있으면 매장 전체의 미술품 판매로 읽힐 수 있습니다.", "annex_tying_scope"))
        point = items[0].text if items else ""
        findings.append(_base(
            a_tying, chunk, key="annex_tying_scope", tier="MEDIUM",
            problem=(f"{a_tying.path}는 ‘가맹점에서 판매하는 모든 미술품 관련 상품’을 가맹본부로부터만 공급받도록 하고 "
                     "위반 시 해지 절차까지 둡니다. 가맹점의 범위가 점포명·소재지로만 표시되어"
                     f"({items[0].path}) 우리 매장 안의 큐레이션 구역인지 매장 전체인지 특정되지 않아, 우리 회사가 다른 "
                     "공급처에서 매입한 미술품·소품을 같은 매장에서 파는 것까지 위반으로 다툴 여지가 있습니다."),
            legal_business_reason=("구입강제는 영업표지의 동일성 유지에 필요한 범위에서만 허용되는 것이 원칙입니다"
                                   "(가맹사업법상 불공정거래행위 금지 — 구입강제). 범위를 특정하지 않으면 우리 매장의 상품 구성권을 상대방이 "
                                   "통제하게 됩니다."),
            suggested_rewrite=("1) 가맹점사업자가 가맹점에서 「그림닷컴 큐레이션 샵」 영업표지를 사용하여 판매하는 미술품 관련 "
                               "상품은 가맹본부로부터 공급받아야 하며, 가맹본부의 사전 승인 없이 타 사업자로부터 소싱한 상품을 "
                               "그 영업표지를 사용하여 판매할 수 없다. 가맹점사업자가 가맹점이 위치한 매장의 다른 구역에서 "
                               "자기의 상호 또는 영업표지로 판매하는 상품에는 본항을 적용하지 아니한다."),
            location_instruction=f"{a_tying.path} 교체",
            related_clause_paths=[items[0].path],
            negotiation_position=("상대방의 정당한 관심은 '그림닷컴' 간판 아래에서 파는 상품의 동일성입니다. 그 범위로 좁히자는 "
                                  "요구는 거절 명분이 약합니다."),
        ) if point else {})

    # 10. 해지 ─────────────────────────────────────────────────────────────────
    m_term = main_para(r"상당한\s*기간을\s*정하여[^.]{0,40}최고")
    a_term = _find_sub(items, r"(?:위반|판매)[^.]{0,120}계약\s*해지\s*절차")
    if a_term is not None:
        rows.append(AxisRow("해지", [m_term.path] if m_term else [], [a_term.path], CONFLICT,
                            "별첨이 본문 해지사유에 없는 해지사유(구입강제 위반)를 더하면서 시정기간·절차를 정하지 않았습니다.",
                            "annex_termination"))
        linked = []
        if m_mark is not None:
            linked.append({"display_path": f"{m_mark.path} 5호" if re.search(r"(?m)^\s*5\)", m_mark.text) else m_mark.path,
                           "text": "5) “갑” 또는 “을”이 상대방의 상표 또는 영업표지를 도용했을 경우",
                           "source": "EXISTING_CLAUSE_EDIT"})
        cure = f"본문 {m_term.path}" if m_term is not None else "본문의 해지 조항"
        findings.append(_base(
            a_term, chunk, key="annex_termination", tier="MEDIUM",
            problem=(f"{a_term.path}는 구입강제 위반을 이유로 가맹본부가 ‘계약 해지 절차를 진행할 수 있다’고 하지만, 본문 "
                     f"해지 조항({m_term.path if m_term else '해지 조항'})에는 이 사유가 없고 별첨에는 시정 기회·통지 절차도 "
                     "없습니다. 어느 계약(별첨만인지, 물품거래 기본계약 전체인지)을 해지하는지도 불명확합니다."
                     + (f" 또한 {m_mark.path}의 ‘“을”이 “갑”의 상표를 도용한 경우’는 별첨 구조(영업표지 = {fr_q} 소유, "
                        f"사용자 = {fe_q})와 방향이 반대입니다." if m_mark is not None else "")),
            legal_business_reason=("가맹사업법이 적용되면 가맹본부는 2개월 이상의 유예기간을 두고 위반 사실과 해지 사유를 2회 이상 "
                                   "서면으로 통지해야 해지할 수 있습니다(가맹사업법상 가맹계약 해지 제한). 절차 없는 해지 문구는 우리에게 불리하게 "
                                   "운용될 수 있고, 기본계약까지 함께 해지되면 공급이 끊깁니다."),
            suggested_rewrite=(f"2) 가맹점사업자가 제1항을 위반하여 가맹본부 외의 사업자로부터 소싱한 미술품 관련 상품을 판매한 "
                               f"경우, 가맹본부는 해당 상품의 판매 중지를 서면으로 요구할 수 있으며, 가맹점사업자가 그 요구를 받은 "
                               f"날부터 30일 이내에 이를 시정하지 아니한 경우에 한하여 {cure}에 따라 별첨에 따른 가맹점 운영에 "
                               "관한 약정을 해지할 수 있다. 관계 법령이 더 긴 유예기간이나 통지 절차를 정한 경우에는 그에 따른다."),
            location_instruction=f"{a_term.path} 교체",
            related_clause_paths=[p for p in ([m_term.path] if m_term else [])],
            package_linked_edits=linked,
            negotiation_position="시정기간·서면요구는 법이 요구하는 수준이라 상대방이 거부하기 어렵습니다.",
        ))

    # 11. 유효기간 ─────────────────────────────────────────────────────────────
    m_term_len = main_para(r"유효기간[^.]{0,40}(?:\d+\s*년|만\s*\d)")
    a_period = re.search(r"가맹\s*(?:계약)?\s*기간|운영\s*기간|계약기간은", _flat(annex_text))
    if m_term_len is not None and not a_period:
        rows.append(AxisRow("유효기간", [m_term_len.path], [], MISMATCH,
                            "본문 기본계약은 1년이고 별첨에는 가맹점 운영기간·갱신·종료 연동 규정이 없습니다.", "annex_term_link"))
        art = m_term_len.path.split(" ")[0]
        chunk_art = arts.get(re.sub(r"\D", "", art))
        n_next = len(paras.get(re.sub(r"\D", "", art), {})) + 1
        findings.append(_base(
            Part(path=art, text=_attr(chunk_art, "text"), title=_attr(chunk_art, "title")) if chunk_art is not None else m_term_len,
            chunk_art if chunk_art is not None else chunk, key="annex_term_link", tier="MEDIUM",
            problem=(f"{m_term_len.path}은 기본계약의 유효기간을 체결일부터 1년으로 정하지만, 별첨에는 가맹점 운영기간이나 "
                     "갱신·종료 연동 규정이 없습니다. 기본계약이 만료돼도 별첨(영업표지 사용·구입강제·종료 후 철거 의무)이 "
                     "따로 남는지, 함께 끝나는지 알 수 없습니다."),
            legal_business_reason=("가맹사업법이 적용되면 가맹점사업자는 전체 가맹계약기간 10년 범위에서 갱신을 요구할 수 있습니다"
                                   "(가맹사업법상 계약갱신요구권). 기간 연동을 정하지 않으면 1년 뒤 공급 기본계약만 끝나고 구입강제·철거 의무가 "
                                   "남는 상태가 생길 수 있습니다."),
            suggested_rewrite=((_attr(chunk_art, "text").rstrip() + "\n") if chunk_art is not None else "")
            + (f"{n_next}. 별첨에 따른 가맹점 운영에 관한 약정의 기간은 이 기본계약의 유효기간과 같으며, 이 "
               "기본계약이 만료되거나 해지되면 별첨에 따른 약정도 함께 종료된다. 이 경우 미판매 작품의 처리는 "
               "제13조 제3항에 따른다."),
            location_instruction=f"{art} 말미에 다음 항 추가",
            negotiation_position="기간 연동은 양측 모두의 불확실성을 줄이는 조항이라 수용 가능성이 높습니다.",
        ))

    # 우선순위 finding — 역할 연결과 우선 규정을 한 번에 고친다(부칙의 별첨 연결 문구가 앵커).
    if any(r.finding_key == "annex_precedence" for r in rows) and ref_clause is not None and addendum is not None:
        conflicts = [r for r in rows if r.status in (CONFLICT, MISMATCH) and r.axis not in ("당사자 역할", "우선순위 조항")]
        listing = "; ".join(f"{r.axis}({' · '.join(r.main_refs) or '본문 규정 없음'} ↔ "
                            f"{' · '.join(r.annex_refs) or '별첨 규정 없음'})" for r in conflicts)
        fr_word = roles.franchisor_annex_name or "가맹본부"
        findings.insert(0, _base(
            ref_clause, addendum, key="annex_precedence", tier="HIGH",
            problem=(f"{_p(ref_clause.path, '은', '는')} 가맹 관련 사항을 ‘별첨의 내용으로 한다’고만 정하고, 본문과 별첨이 다를 때 무엇이 "
                     "우선하는지, 별첨의 가맹본부·가맹점사업자가 본문의 누구인지를 정하지 않았습니다. "
                     + (roles.sentence() + " ") + (f"본문과 별첨이 실제로 다르게 정한 항목: {listing}." if listing else "")),
            legal_business_reason=(
                "우선순위가 없으면 같은 사항에 두 규정이 경합하고, 상대방은 자기에게 유리한 쪽(대개 특별 규정인 별첨)을 "
                "주장합니다. 별첨이 영업표지로 당사자를 적으면 계약 주체 다툼의 빌미도 됩니다."
                + (" 또한 별첨은 가맹사업 요소(영업표지 사용허락·영업표준화·구입강제·초도물량)를 담고 있어, 물품공급계약으로 "
                   "체결하더라도 실질은 가맹계약으로 평가될 수 있습니다." if rv.franchise else "")),
            suggested_rewrite=(
                f"3. 프랜차이즈 가맹\n① {fr_word}(가맹본부) 큐레이션 샵 프랜차이즈 가맹과 관련한 사항은 별첨의 내용으로 한다. "
                f"별첨에서 “가맹본부”는 {_p(fr_q, '을', '를')}, “가맹점사업자”는 {_p(fe_q, '을', '를')}, “가맹점”은 별첨 제1항에 표시된 점포를 말하며, "
                f"{_p('「' + fr_word + '」', '은', '는')} {_p(fr_q, '이', '가')} 사용하는 영업표지를 말한다.\n"
                "② 별첨은 가맹점 운영(영업표지 사용, 영업표준화, 광고·판촉, 권장가격)에 관한 사항에 한하여 적용하며, 계약물품의 "
                "발주·납품·검사·대금 지급·반품·하자보증, 계약의 해제·해지 및 유효기간에 관하여는 본문이 별첨에 우선한다.\n"
                "③ 제2항에 따라 우선순위가 정해지지 아니한 사항에 관하여 본문과 별첨이 서로 다르게 정한 경우에는 “갑”과 “을”이 "
                "서면으로 합의하여 정한다."),
            location_instruction=f"{ref_clause.path} 교체",
            related_clause_paths=[rv.annex_path] + ([ind_priority.path] if ind_priority else []),
            negotiation_position=("'본문 우선' 범위는 물품 거래의 핵심 조건(대금·반품·하자·해지)으로 한정해 제시하면, 가맹 운영 "
                                  "사항은 상대방 별첨을 존중하는 모양이 되어 수용 가능성이 높습니다."),
            high_severity_basis="본문·별첨 충돌 다수 + 우선순위·역할 연결 조항 부재",
        ))

    rv.rows = rows
    rv.findings = [f for f in findings if f]
    return rv


def corrected_role_text(text: str, roles: AnnexRoles) -> tuple[str, int]:
    """'우리 회사(가맹본부)' 처럼 별첨 역할을 뒤집은 서술을 바로잡는다. (고친 문장, 고친 수)."""
    if not roles.franchisor_name or not roles.franchisee_name:
        return text, 0
    body = str(text or "")
    n = 0

    def short(name: str) -> str:
        return re.sub(r"주식회사|㈜|\(주\)", "", name).strip()

    fe, fr = short(roles.franchisee_name), short(roles.franchisor_name)
    for wrong, right in (
        (rf"((?:㈜|\(주\)|주식회사\s*)?{re.escape(fe)})\s*\(\s*가맹본부\s*\)", r"\1(가맹점사업자)"),
        (rf"((?:㈜|\(주\)|주식회사\s*)?{re.escape(fr)})\s*\(\s*가맹점사업자\s*\)", r"\1(가맹본부)"),
        (rf"{re.escape(fe)}[^.\n]{{0,6}}(?:이|가|은|는)\s*가맹본부(?=이|로|에|입|\s|\.|,)", None),
    ):
        if right is None:
            def _fix(m: "re.Match[str]") -> str:
                return m.group(0).replace("가맹본부", "가맹점사업자")
            body, k = re.subn(wrong, _fix, body)
        else:
            body, k = re.subn(wrong, right, body)
        n += k
    return body, n
