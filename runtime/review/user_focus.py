from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UserFocusObjective:
    code: str
    title: str
    keywords: list[str]

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "title": self.title, "keywords": list(self.keywords)}


_OBJECTIVES: list[UserFocusObjective] = [
    UserFocusObjective(code="dealer_unfair_disadvantage", title="대리점법상 불이익 제공/거래상 지위 남용", keywords=["불이익", "불이익제공", "거래상", "지위", "남용", "대리점법", "공정거래"]),
    UserFocusObjective(code="dealer_management_interference", title="경영간섭/영업자율 침해", keywords=["경영간섭", "영업간섭", "인사", "가격", "판매가격", "가격통제", "영업정책", "강제", "지시"]),
    UserFocusObjective(code="dealer_cost_shift", title="비용전가(판촉비/광고비/반품비/원상회복)", keywords=["비용전가", "비용 전가", "비용부담", "판촉", "판매장려금", "광고비", "반품", "원상회복"]),
    UserFocusObjective(code="termination_abuse", title="계약해지/물량축소/불이익 조치 남용", keywords=["해지", "종료", "물량", "축소", "중단", "불이익", "일방", "임의"]),
    UserFocusObjective(code="settlement_offset", title="정산/공제/상계/증빙(대금 리스크)", keywords=["정산", "상계", "공제", "차감", "증빙", "인보이스", "세금계산서"]),
    UserFocusObjective(code="delay_liquidated_damages", title="지체상금(지체상금율/공기지연 책임)", keywords=["지체상금", "공기", "공기지연", "지연", "지연손해금", "손해배상액의 예정", "지체"]),
    UserFocusObjective(code="penalty_clause", title="위약금/위약벌(과도한 페널티)", keywords=["위약금", "위약벌", "벌금", "패널티", "penalty"]),
    UserFocusObjective(code="unilateral_setoff", title="일방적 상계권(이의제기권 부재)", keywords=["일방", "상계권", "상계", "공제", "차감", "이의", "이의제기", "이의 제기"]),
    UserFocusObjective(code="unfair_unit_price_reduction", title="부당한 단가 인하(하도급/공사 단가 리스크)", keywords=["단가", "단가인하", "단가 인하", "감액", "대금감액", "부당", "하도급", "하도급법"]),
    UserFocusObjective(code="rpm_price_fixing", title="재판매가격 유지행위 강제(가격결정권 침해)", keywords=["재판매", "가격유지", "가격 유지", "판매가격", "가격결정", "가격 결정", "가격강제", "가격 강제", "가격 통제"]),
    UserFocusObjective(code="privacy", title="개인정보/처리위탁/재위탁/침해사고", keywords=["개인정보", "처리위탁", "수탁", "재위탁", "파기", "반환", "침해사고", "유출", "통지"]),
    UserFocusObjective(code="dispute", title="분쟁해결/재판관할/준거법", keywords=["분쟁", "관할", "전속관할", "합의관할", "준거법", "중재", "조정"]),
]

def _objective_by_code(code: str) -> UserFocusObjective | None:
    c = (code or "").strip()
    if not c:
        return None
    for o in _OBJECTIVES:
        if o.code == c:
            return o
    return None


def parse_user_focus_issues(text: str | None) -> list[UserFocusObjective]:
    s = (text or "").strip()
    if not s:
        return []
    low = s.lower()
    out: list[UserFocusObjective] = []

    for o in _OBJECTIVES:
        if any(k.lower() in low for k in o.keywords if k):
            out.append(o)

    parts = re.split(r"[\n\r,;/]+", s)
    for p in [x.strip() for x in parts if x.strip()]:
        if len(p) < 2:
            continue
        if any(o.title == p for o in out):
            continue
        if "대리점" in p and "불이익" in p:
            o = _objective_by_code("dealer_unfair_disadvantage")
            if o is not None:
                out.append(o)
            continue
        if "경영" in p and ("간섭" in p or "통제" in p):
            o = _objective_by_code("dealer_management_interference")
            if o is not None:
                out.append(o)
            continue

    uniq: dict[str, UserFocusObjective] = {}
    for o in out:
        uniq[o.code] = o
    return list(uniq.values())


def objective_codes_to_clause_topics(codes: list[str]) -> set[str]:
    out: set[str] = set()
    for c in codes:
        if c in ("dealer_unfair_disadvantage",):
            out.update({"dealer_unfair", "termination"})
        if c in ("dealer_management_interference",):
            out.update({"dealer_unfair"})
        if c in ("dealer_cost_shift", "settlement_offset"):
            out.update({"cost_burden", "payment_settlement", "dealer_unfair"})
        if c in ("termination_abuse",):
            out.update({"termination", "dealer_unfair"})
        if c in ("delay_liquidated_damages", "penalty_clause", "unfair_unit_price_reduction"):
            out.add("payment_settlement")
        if c in ("unilateral_setoff",):
            out.update({"payment_settlement", "dealer_unfair"})
        if c in ("rpm_price_fixing",):
            out.add("dealer_unfair")
        if c in ("privacy",):
            out.add("personal_data")
        if c in ("dispute",):
            out.add("dispute")
    return out


def derive_focus_objectives_from_answers(answers: dict[str, object] | None) -> list[UserFocusObjective]:
    ans = dict(answers or {})
    out: list[UserFocusObjective] = []

    def _is_yes(v: object) -> bool:
        if isinstance(v, bool):
            return bool(v)
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            s = v.strip().lower()
            return s in ("yes", "y", "true", "t", "1") or ("있" in s) or ("해당" in s)
        return False

    def _has_text(v: object) -> bool:
        return isinstance(v, str) and v.strip() != ""

    if _is_yes(ans.get("Q-DL-002-cost-shift")) or _is_yes(ans.get("Q-CA-001-dealer-cost")) or _is_yes(ans.get("Q-007-dealer")):
        out.append(_OBJECTIVES[2])
    if _is_yes(ans.get("Q-DL-003-settlement")):
        out.append(_OBJECTIVES[4])
    if _is_yes(ans.get("Q-DL-004-termination")):
        out.append(_OBJECTIVES[3])
    if _is_yes(ans.get("Q-DL-006-unfair-interference")):
        out.append(_OBJECTIVES[0])
        out.append(_OBJECTIVES[1])
    if _is_yes(ans.get("Q-DL-005-privacy")) or _is_yes(ans.get("Q-003-personal-data")):
        out.append(_OBJECTIVES[5])
    if _has_text(ans.get("Q-DL-007-dispute-special")):
        out.append(_OBJECTIVES[6])

    uniq: dict[str, UserFocusObjective] = {}
    for o in out:
        uniq[o.code] = o
    return list(uniq.values())
