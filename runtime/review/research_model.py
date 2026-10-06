"""Transaction Reconstruction — 산학협력 연구용역·공동연구 계약.

2026-10-06 지시 (범용 보정 — 조항 정확성 / 불필요 이슈 제거 / Senior Counsel Filter)
──────────────────────────────────────────────────────────────────────────
실측(서울대 산학협력단 연구계약): 같은 계약이 legal_state 에서는 "지식재산권 실시허락(라이선스)",
구조 판정에서는 "비밀유지계약(NDA)", 범위 정책에서는 "자문/용역" 으로 동시에 불렸다. 정의 조항의
지식재산권 어휘(2개)가 인도 어휘보다 많다는 이유만으로 라이선스가 됐고, 그 위에서 2차적저작물·
제3자 소재 라이선스 같은 라이선스 계약의 논점이 돌았다. 정작 연구비 전액을 대는 우리 회사가
성과를 쓰려면 다시 실시계약을 맺어야 하는 문제, 연구보고서 제출 전에 잔금 지급일이 오는 문제는
하나의 쟁점으로 정리되지 않았다.

이 모듈은 분류기보다 먼저 **거래 실질**을 세운다.

    연구 의뢰자(sponsor)   연구비를 지급하고 연구결과를 받는다
    연구 수행기관           연구책임자를 두고 연구를 수행해 보고서를 낸다
    급부                   연구 수행 + 연구보고서(주된 성과물)
    대가                   연구비(착수금·중도금·잔금)
    핵심 권리               성과물·지식재산권 귀속, 실시 조건, 발표(공개) 통제

연구비·연구책임자·연구기간·보고서 신호가 함께 서야 확정한다. 확신하지 못하면 아무것도 바꾸지 않는다.

여기서 만드는 finding 은 셋뿐이다(지시 5·6·8항 — 사내변호사가 실제로 넣으라고 할 것만).
    1. 성과물 제출·대금 연계 package   잔금·해지 정산이 연구보고서 제출과 끊겨 있다
    2. 연구성과 귀속·활용 package     우리가 연구비를 다 내는데 성과를 쓰려면 다시 실시계약
    3. (사업부 확인) 금액 미확정 별도 용역비
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

CANONICAL_TYPE = "research_collaboration"
LABEL = "산학협력 연구용역 계약(지식재산권 조항 포함)"
SPONSOR_ROLE_LABEL = "연구 의뢰자(연구비 지급·연구결과 수령)"
PERFORMER_ROLE_LABEL = "연구 수행기관(연구 수행·연구보고서 제출)"

_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("연구비", re.compile(r"연\s*구\s*비")),
    ("연구책임자", re.compile(r"연\s*구\s*책\s*임\s*자|principal\s+investigator", re.IGNORECASE)),
    ("연구기간", re.compile(r"연\s*구\s*기\s*간")),
    ("연구보고서", re.compile(r"연구\s*(?:결과\s*)?보고서|연구결과(?:물)?를?\s*(?:제출|제공)")),
    ("연구기관", re.compile(r"산학협력단|대학교|연구원|연구소|연구기관|university", re.IGNORECASE)),
    ("연구계획서", re.compile(r"연구\s*계획서|연구\s*과제")),
)

_RX_ALIAS = re.compile(r"(\S{2,30}?)\s*\(\s*이하\s*[“\"']\s*([^”\"']{1,12})\s*[”\"']")
#: "“A”가 “B”에 지급하는 연구비" — 연구비를 내는 쪽이 연구 의뢰자다.
_RX_PAYER = re.compile(
    r"[“\"']([^”\"']{1,12})[”\"']\s*(?:가|이)\s*[“\"']?([^”\"'\s]{1,12})[”\"']?\s*에(?:게)?\s*지급하는\s*연구비"
)

_RX_REPORT_DUTY = re.compile(r"연구\s*(?:결과\s*)?보고서를?\s*제출")
_RX_REPORT_WAIVER = re.compile(r"제출하지\s*(?:아니|않)")
_RX_PAY_SCHEDULE = re.compile(r"잔\s*금|중\s*도\s*금|착\s*수\s*금")
_RX_PAY_LINKED = re.compile(
    r"(?:보고서|성과물|결과물|연구결과)[^.]{0,40}(?:제출|검수|확인|승인|인수)[^.]{0,40}(?:후|때|경우|한\s*날)[^.]{0,60}지급"
)
_RX_TERM_SETTLE = re.compile(r"해지[^.]{0,200}정산|정산[^.]{0,200}해지")
_RX_REFUND = re.compile(r"(?:초과|잔액|차액|미사용)[^.]{0,40}반환|반환하여야|환급")
_RX_IP_JOINT = re.compile(r"공동\s*소유|공유로\s*한다|공동\s*명의")
_RX_IP_THEIRS = re.compile(r"지식재산권[^.]{0,60}[“\"']?(?:학교|수행기관|연구기관)[”\"']?(?:의|에)\s*(?:소유|귀속)")
_RX_SEPARATE_LICENSE = re.compile(r"별도의?\s*(?:실시|이용|사용)\s*(?:계약|허락|협약)")
_RX_IP_CLAUSE = re.compile(r"무형적\s*(?:성과물|재산)|지식재산권[^.]{0,40}(?:귀속|소유)|(?:귀속|소유)[^.]{0,40}지식재산권")
_RX_PUBLICATION = re.compile(r"발표할\s*수\s*있")
_RX_PUB_CONTROL = re.compile(r"(?:동의|승인)(?:를|을)?\s*(?:받|얻)|연기|삭제를?\s*요청|특허\s*출원")
#: 상대방 문서·명칭을 광고·판촉에 쓰려면 사전 승인을 받게 하는 조항.
_RX_NAME_USE = re.compile(r"(?:승인|동의)\s*없이[^.]{0,80}(?:광고|판매\s*촉진|선전|홍보)[^.]{0,80}(?:사용할\s*수\s*없|금지)")
_RX_OPEN_COST = re.compile(
    r"(?:비용|용역비)[^.]{0,80}(?:부속\s*합의서|별도\s*합의|협의)[^.]{0,60}(?:확정|정한)"
    r"|(?:부속\s*합의서|별도\s*합의)[^.]{0,40}(?:비용|용역비)[^.]{0,20}(?:확정|정한)"
)
_RX_DATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_RX_TERM_END = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*까지")
_RX_REPORT_LAG = re.compile(r"종료일?\s*후\s*(\d{1,2})\s*(개월|일)\s*이내")


@dataclass
class ResearchModel:
    confident: bool = False
    basis: str = ""
    sponsor_label: str = ""
    performer_label: str = ""
    our_side: str = ""                  # "sponsor" | "performer" | ""
    signals: list[str] = field(default_factory=list)
    ip_regime: str = ""                 # "joint" | "performer" | "sponsor" | ""
    separate_license_required: bool = False
    report_waivable: bool = False
    final_payment_date: str = ""
    report_due: str = ""
    payment_linked_to_report: bool = False

    @property
    def canonical_contract_type(self) -> str:
        return CANONICAL_TYPE if self.confident else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "confident": self.confident, "basis": self.basis,
            "canonical_contract_type": self.canonical_contract_type,
            "label": LABEL if self.confident else "",
            "sponsor_label": self.sponsor_label, "performer_label": self.performer_label,
            "our_side": self.our_side, "signals": list(self.signals),
            "ip_regime": self.ip_regime, "separate_license_required": self.separate_license_required,
            "report_waivable": self.report_waivable, "final_payment_date": self.final_payment_date,
            "report_due": self.report_due, "payment_linked_to_report": self.payment_linked_to_report,
        }


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _norm(label: str) -> str:
    return re.sub(r"[\s“”\"'()]|㈜|주식회사", "", str(label or "").replace("(주)", "").replace("㈜", ""))


def _quoted(label: str, body: str) -> str:
    """본문에서 그 당사자를 실제로 부르는 표기(따옴표 포함) — "(주)퍼시스" 와 "㈜퍼시스" 를 가린다."""
    m = re.search(r"[“\"]" + re.escape(label) + r"[”\"]", body)
    return m.group(0).replace('"', "“", 1).replace('"', "”", 1) if m else f"“{label}”"


def resolve_research_model(*, contract_text: str, entity: str = "") -> ResearchModel:
    body = str(contract_text or "")
    flat = _flat(body)
    model = ResearchModel()
    hits = [name for name, rx in _SIGNALS if rx.search(body)]
    if not ({"연구비", "연구책임자", "연구보고서"} <= set(hits) and len(hits) >= 4):
        return model
    m_pay = _RX_PAYER.search(flat)
    if not m_pay:
        return model
    sponsor, performer = m_pay.group(1).strip(), m_pay.group(2).strip()
    if _norm(sponsor) == _norm(performer):
        return model

    model.confident = True
    model.signals = hits
    model.sponsor_label = sponsor
    model.performer_label = performer
    model.basis = f"연구 신호 {len(hits)}개({', '.join(hits)}), '{sponsor}'가 '{performer}'에 연구비 지급"

    ent = _norm(entity)
    our_aliases: list[str] = []
    try:
        from runtime.review.group_entities import resolve_entity

        for name, alias in _RX_ALIAS.findall(body[:1500]):
            if resolve_entity(name) is not None or resolve_entity(alias) is not None:
                our_aliases.append(_norm(alias))
    except Exception:  # noqa: BLE001 - 판정 실패 시 entity 이름으로만 본다
        pass
    if ent and ent in _norm(sponsor) or _norm(sponsor) in our_aliases:
        model.our_side = "sponsor"
    elif ent and ent in _norm(performer) or _norm(performer) in our_aliases:
        model.our_side = "performer"

    ip_text = " ".join(_flat(s) for s in re.split(r"(?=제\s*\d+\s*조)", body) if _RX_IP_CLAUSE.search(_flat(s)))
    if _RX_IP_JOINT.search(ip_text):
        model.ip_regime = "joint"
    elif _RX_IP_THEIRS.search(ip_text):
        model.ip_regime = "performer"
    elif ip_text:
        model.ip_regime = "sponsor"
    model.separate_license_required = bool(_RX_SEPARATE_LICENSE.search(ip_text))
    model.payment_linked_to_report = bool(_RX_PAY_LINKED.search(flat))
    m_final = re.search(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*(?:에|까지)?\s*잔\s*금", flat)
    if m_final:
        model.final_payment_date = "-".join(f"{int(g):02d}" for g in m_final.groups())
    m_end = _RX_TERM_END.search(flat[flat.find("연구기간"):] if "연구기간" in flat else "")
    m_lag = _RX_REPORT_LAG.search(flat)
    if m_end and m_lag:
        y, mo, d = (int(g) for g in m_end.groups())
        n = int(m_lag.group(1))
        if m_lag.group(2) == "개월":
            mo2, y2 = mo + n, y
            while mo2 > 12:
                mo2, y2 = mo2 - 12, y2 + 1
            last = [31, 29 if y2 % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo2 - 1]
            model.report_due = date(y2, mo2, min(d if d < 28 else last, last)).isoformat()
        else:
            model.report_due = date.fromordinal(date(y, mo, d).toordinal() + n).isoformat()
    report = next((s for s in re.split(r"(?=제\s*\d+\s*조)", body) if _RX_REPORT_DUTY.search(_flat(s))), "")
    model.report_waivable = bool(_RX_REPORT_WAIVER.search(_flat(report)))
    return model


# ── finding ─────────────────────────────────────────────────────────────────

def _clause(clauses: list[Any] | None, rx: re.Pattern[str], *, need: re.Pattern[str] | None = None) -> Any:
    for c in clauses or []:
        if not _attr(c, "article_number"):
            continue
        t = _flat(_attr(c, "text"))
        if rx.search(t) and (need is None or need.search(t)):
            return c
    return None


def _article_ref(c: Any) -> str:
    return f"제{_attr(c, 'article_number')}조" if c is not None else ""


def _p(word: str, with_b: str, without_b: str) -> str:
    """조사를 받침에 맞춘다. 따옴표·괄호는 건너뛰고 마지막 한글 음절을 본다("“연구원”과")."""
    core = re.sub(r"[\s“”\"'()]+$", "", word or "")
    last = core[-1:] if core else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _eun(word: str) -> str:
    """받침에 맞는 보조사 — "제10조는", "제9조 제2항은"."""
    last = word.rstrip()[-1:] if word else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + ("은" if has else "는")


def _ko(d: str) -> str:
    if not d:
        return ""
    y, m, dd = d.split("-")
    return f"{int(y)}. {int(m)}. {int(dd)}."


def _finding(anchor: Any, **kw: Any) -> dict[str, Any]:
    base = {
        "clause_title": _attr(anchor, "title"),
        "display_path": _attr(anchor, "display_path"),
        "article_number": _attr(anchor, "article_number"),
        "paragraph_number": _attr(anchor, "paragraph_number"),
        "original_text": _attr(anchor, "text"),
        "risk_tier": "HIGH", "severity": "HIGH", "confidence": 0.97,
        "is_effect_baseline": True, "is_common_legal_risk": True,
        # 같은 손실 시나리오의 다른 조항 지적을 흡수하는 대표 finding 이다(지시 8항).
        "is_transaction_package": True,
    }
    base.update(kw)
    base.setdefault("rewrite_reason", base.get("problem", ""))
    base.setdefault("recommendation_text", base.get("suggested_rewrite", ""))
    base.setdefault("negotiation_strategy", base.get("negotiation_position", ""))
    return base


def research_findings(model: ResearchModel, clauses: list[Any] | None, contract_text: str) -> list[dict[str, Any]]:
    """연구 의뢰자(우리) 관점의 핵심 package. 우리가 수행기관이면 만들지 않는다."""
    if not model.confident or model.our_side != "sponsor":
        return []
    body = str(contract_text or "")
    us = _quoted(model.sponsor_label, body)
    them = _quoted(model.performer_label, body)
    out: list[dict[str, Any]] = []

    # 1. 성과물 제출·대금 연계 package ─────────────────────────────────────
    pay = _clause(clauses, re.compile(r"연\s*구\s*비"), need=_RX_PAY_SCHEDULE)
    report = _clause(clauses, _RX_REPORT_DUTY)
    settle = _clause(clauses, _RX_TERM_SETTLE)
    if pay is not None and report is not None and not model.payment_linked_to_report:
        gaps: list[str] = []
        timing = ""
        if model.final_payment_date and model.report_due and model.final_payment_date <= model.report_due:
            timing = (f"잔금 지급일({_ko(model.final_payment_date)})이 연구보고서 제출기한"
                      f"({_ko(model.report_due)})보다 먼저 와서, 보고서를 받기 전에 연구비 전액이 지급된다")
            gaps.append(timing)
        else:
            gaps.append("잔금이 확정 일자에 지급되도록 되어 있고 연구보고서 제출과 연결되어 있지 않다")
        if model.report_waivable:
            gaps.append(f"{_article_ref(report)} 단서에 따라 연구보고서를 제출하지 않을 수도 있어 대가와 맞바꿀 성과물이 남지 않는다")
        refund_missing = settle is not None and not _RX_REFUND.search(_flat(_attr(settle, "text")))
        if refund_missing:
            gaps.append(f"중도 해지 시 정산({_attr(settle, 'display_path')})에는 이미 지급한 연구비가 정산액을 넘을 때 "
                        "돌려받는다는 문언이 없다")
        report_ref = _article_ref(report)
        addition = (
            f"다만, 잔금은 {_p(them, '이', '가')} {report_ref}에 따른 연구보고서를 제출하고 {_p(us, '이', '가')} 그 수령을 서면으로 확인한 후 "
            f"지급하며, 연구보고서가 제출되지 아니한 경우 {_p(us, '은', '는')} 잔금의 지급을 거절할 수 있다."
        )
        linked: list[dict[str, str]] = []
        if refund_missing:
            linked.append({
                "display_path": _attr(settle, "display_path"),
                "text": (f"정산 결과 {_p(us, '이', '가')} 이미 지급한 연구비가 정산비용을 초과하는 경우, {_p(them, '은', '는')} 그 차액을 "
                         f"정산서 제출일로부터 30일 이내에 {us}에 반환한다."),
            })
        if model.report_waivable:
            linked.append({
                "display_path": _attr(report, "display_path"),
                "text": (f"단서에 따라 연구보고서를 제출하지 아니하는 경우에도 {_p(them, '은', '는')} 연구결과를 {us}에 "
                         "비공개 방식으로 제공하여야 한다."),
            })
        original = _attr(pay, "text").rstrip()
        proposal = f"{original} {addition}"
        paths = [_attr(pay, "display_path"), _attr(report, "display_path")] + (
            [_attr(settle, "display_path")] if settle is not None else [])
        problem = "; ".join(gaps) + "."
        if linked:
            problem += " [연계 수정] " + " / ".join(f"{e['display_path']} 말미: {e['text']}" for e in linked)
        out.append(_finding(
            pay,
            clause_id=f"tx_deliverable_payment_package__{_attr(pay, 'clause_id')}",
            problem=problem,
            rewrite_reason="; ".join(gaps) + ".",
            legal_business_reason=(
                f"연구용역의 대가는 연구결과(보고서)와 맞바꾸는 것인데, 지금 구조에서는 {_p(us, '이', '가')} 연구비를 모두 낸 뒤에야 "
                "보고서가 오고, 보고서가 오지 않아도 잔금 지급을 거절할 계약상 근거가 없다. 보고서 미제출을 이유로 "
                "해지하더라도 이미 지급한 착수금·중도금을 돌려받는 근거가 약하다."
            ),
            high_severity_basis=f"연구비 잔금 및 해지 시 기지급 연구비 회수 — 성과물 없이 대가가 지급되는 구조",
            suggested_rewrite=proposal,
            location_instruction=f"{_attr(pay, 'display_path')} 말미에 다음 문구 추가",
            package_linked_edits=linked,
            related_clause_paths=[p for p in dict.fromkeys(paths) if p],
            package_articles=sorted({_attr(c, "article_number") for c in (pay, report, settle) if c is not None}),
            package_pattern=r"잔금|연구비|대금|지급|보고서|성과물|결과물|제출|정산|검수",
            negotiation_position=(
                "잔금을 연구보고서 제출·확인과 연결하는 것이 1순위입니다. 수행기관 표준양식상 확정일 지급을 고수하면, "
                "최소한 잔금 지급일을 보고서 제출기한 이후로 옮기도록 요청합니다."
            ),
            detected_issue_list=[{"issue_title": "[성과물 제출·대금 연계] 연구보고서 제출 전 잔금 지급·해지 시 연구비 반환 근거 부재"}],
        ))

    # 2. 연구성과 귀속·활용 package ───────────────────────────────────────
    ip = _clause(clauses, _RX_IP_CLAUSE, need=re.compile(r"무형|지식재산권"))
    if ip is not None and model.ip_regime in ("joint", "performer"):
        ip_text = _flat(_attr(ip, "text"))
        # 수행기관 자신의 발표권(통지 후 발표)을 고른다 — 연구책임자 개인의 학술발표 조항보다 앞선다.
        pub = (_clause(clauses, _RX_PUBLICATION, need=re.compile(r"(?:성과물|연구결과)[^.]*(?:전에|통지|제공하며)"))
               or _clause(clauses, _RX_PUBLICATION, need=re.compile(r"성과물|연구결과")))
        pub_open = pub is not None and not _RX_PUB_CONTROL.search(_flat(_attr(pub, "text")))
        name_use = _clause(clauses, _RX_NAME_USE)
        gaps = []
        if model.ip_regime == "joint":
            gaps.append(f"{_p(us, '이', '가')} 연구비 전액을 부담하는데 무형 성과물과 지식재산권은 {_p(them, '과', '와')} 공동소유다")
        else:
            gaps.append(f"{_p(us, '이', '가')} 연구비 전액을 부담하는데 무형 성과물과 지식재산권이 {them}에 귀속된다")
        if model.separate_license_required:
            gaps.append(f"{_p(us, '이', '가')} 그 성과를 실시하려면 별도의 실시계약을 맺어야 해, 이미 대가를 낸 연구결과를 쓰기 위해 "
                        "실시료를 다시 협상해야 한다")
        gaps.append("연구보고서도 공동저작물이 되어 대외 활용(홍보·보도자료 등)에 상대방 동의가 필요하다")
        if name_use is not None:
            gaps.append(f"{_eun(_attr(name_use, 'display_path'))} 상대방이 제출한 문서(연구보고서 포함)의 내용과 상대방 명칭을 "
                        "광고·판매촉진에 쓰려면 사전 서면 승인을 받도록 하고 있어, 승인 없이 연구결과를 홍보에 쓸 수 없다")
        if pub_open:
            m_days = re.search(r"\(?\s*(\d{1,3})\s*\)?\s*일\s*전", _flat(_attr(pub, "text")))
            notice = f"{m_days.group(1)}일 전 통지만으로" if m_days else "사전 통지만으로"
            gaps.append(f"{_p(them, '은', '는')} {notice} 연구결과를 발표할 수 있어({_attr(pub, 'display_path')}) "
                        "특허출원 전 공개로 신규성을 잃거나 우리 비밀정보가 공개될 수 있다")
        proviso = (f"다만, {_p(us, '은', '는')} 별도의 실시계약이나 실시료 없이 위 지식재산권을 무상으로 실시할 수 있고, "
                   f"연구보고서 등 저작물을 내부 활용 및 대외 홍보 목적으로 이용할 수 있다.")
        original = _attr(ip, "text").rstrip()
        if re.search(r"다만,[^.]*별도의?\s*(?:실시|이용|사용)\s*계약[^.]*\.", original):
            proposal = re.sub(r"다만,[^.]*별도의?\s*(?:실시|이용|사용)\s*계약[^.]*\.", proviso, original, count=1)
        else:
            proposal = f"{original} {proviso}"
        linked = []
        if pub_open:
            linked.append({
                "display_path": _attr(pub, "display_path"),
                "text": (f"다만, {_p(us, '이', '가')} 위 기간 내에 발표 내용에 {us}의 비밀정보가 포함되어 있거나 특허출원이 필요하다고 "
                         f"서면으로 요청하는 경우, {_p(them, '은', '는')} 해당 정보를 삭제하거나 특허출원 시까지(최대 60일) 발표를 연기한다."),
            })
        if name_use is not None:
            linked.append({
                "display_path": _attr(name_use, "display_path"),
                "text": (f"다만, {_p(us, '은', '는')} 본 연구의 결과 및 연구보고서의 내용을 {us}의 제품·서비스 홍보에 인용할 수 있으며, "
                         f"{them}의 명칭은 {_p(them, '과', '와')} 사전에 협의한 표현으로 표시한다."),
            })
        problem = "; ".join(gaps) + "."
        if linked:
            problem += " [연계 수정] " + " / ".join(f"{e['display_path']} 말미: {e['text']}" for e in linked)
        paths = [_attr(ip, "display_path")] + [_attr(c, "display_path") for c in (pub, name_use) if c is not None]
        out.append(_finding(
            ip,
            clause_id=f"tx_research_ip_package__{_attr(ip, 'clause_id')}",
            problem=problem,
            rewrite_reason="; ".join(gaps) + ".",
            legal_business_reason=(
                "공동저작물인 연구보고서는 저작재산권 공유자 전원의 합의 없이 행사할 수 없고(저작권법 제48조 제1항), "
                "공유 특허는 계약으로 달리 정하면 각 공유자가 자유롭게 실시할 수 없다(특허법 제99조 제3항). 이 계약의 "
                "'별도 실시계약' 단서가 바로 그 '달리 정한 약정'이다. 연구비를 전액 낸 쪽이 성과를 쓰지 못하면 계약 목적이 "
                "달성되지 않는다."
            ),
            high_severity_basis="연구비를 전액 부담한 연구성과를 실시·활용하려면 추가 실시료가 필요한 구조",
            suggested_rewrite=proposal,
            package_linked_edits=linked,
            related_clause_paths=[p for p in dict.fromkeys(paths) if p],
            package_articles=sorted({_attr(c, "article_number") for c in (ip, pub) if c is not None}
                                    | {_attr(c, "article_number") for c in clauses or []
                                       if re.search(r"지식재산권|명칭\s*사용|발표", _attr(c, "title") + _flat(_attr(c, "text"))[:80])
                                       and _attr(c, "article_number")}),
            package_pattern=r"지식재산|저작|실시|귀속|소유|2차적|발표|공개|명칭|활용|IP\b",
            negotiation_position=(
                f"{_p(them, '이', '가')} 공동소유를 고수하면 '{us}의 무상 실시권 + 연구보고서 자유 이용'을 최소선으로 둡니다. "
                f"가능하면 {us} 단독 귀속에 {them}의 교육·비영리 학술 이용권을 주는 안을 먼저 제시합니다."
            ),
            negotiation_ladder=[
                {"priority": 1, "label": "최선안", "action": f"무형 성과물·지식재산권 {us} 단독 귀속",
                 "rewrite_text": (f"본 연구결과로 발생되는 무형적 성과물 및 그에 대한 지식재산권은 {us}에 귀속한다. 다만, "
                                  f"{_p(them, '과', '와')} 연구책임자는 이를 교육 및 비영리 학술연구 목적으로 무상 이용할 수 있다.")},
                {"priority": 2, "label": "차선안", "action": f"공동소유 유지 + {us} 무상 실시·보고서 자유 이용",
                 "rewrite_text": proviso},
            ],
            detected_issue_list=[{"issue_title": "[연구성과 귀속·활용] 연구비 전액 부담에도 성과 실시에 별도 실시계약 필요"}],
        ))

    # 3. 금액이 정해지지 않은 별도 용역비 — 법무 수정이 아니라 사업부 확인 ─────────────
    extra = _clause(clauses, _RX_OPEN_COST)
    if extra is not None:
        out.append({
            "clause_id": f"tx_open_cost_business_check__{_attr(extra, 'clause_id')}",
            "clause_title": _attr(extra, "title"),
            "display_path": _attr(extra, "display_path"),
            "article_number": _attr(extra, "article_number"),
            "paragraph_number": _attr(extra, "paragraph_number"),
            "original_text": _attr(extra, "text"),
            "risk_tier": "LOW", "severity": "LOW", "confidence": 0.9,
            "is_effect_baseline": True, "is_common_legal_risk": True,
            "business_check": True, "finance_check": True, "triage": "FINANCE_CHECK",
            "problem": ("연구비와 별도로 발생하는 용역비의 금액이 정해져 있지 않고 부속합의서로 정하도록 되어 있다. "
                        "예산 상한과 재위탁 여부(외부 전문가 활용 시 수행기관 책임 유지)를 사업부가 미리 확인해야 한다."),
            "detected_issue_list": [{"issue_title": "[사업부 확인] 금액 미확정 별도 용역비의 예산 상한"}],
        })
    return out


__all__ = [
    "CANONICAL_TYPE", "LABEL", "PERFORMER_ROLE_LABEL", "ResearchModel", "SPONSOR_ROLE_LABEL",
    "research_findings", "resolve_research_model",
]
