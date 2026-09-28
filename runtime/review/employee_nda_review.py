"""임직원 비밀유지계약(Employee NDA) 필수 검토항목과 사용자 요청 직접 답변.

2026-09-28 지시 5항 — "사용자가 명시한 California law / labor law 적법성, SIDIZ
America 와 Fursys America 양사의 기밀정보 보호 가능 여부를
mandatory_review_issues 로 저장하고 반드시 최종 검토에서 직접 답하라. 다른
generic finding 으로 대체하지 마라."

실측(AI 미사용 경로) — 두 요청 모두 "해당 조항 없음 / 사실관계 추가확인" 으로
답변됐다. 요청을 조항 검색어로만 다뤘기 때문이다("캘리포니아 노동법상 적법한지"
라는 낱말을 담은 조항은 없다). 이 두 요청은 검색이 아니라 **판단**이다 —
적용되는 강행규정 목록을 원문과 대조하고, 보호 대상 법인이 계약상 권리를
가지는지를 당사자 구조에서 읽어야 한다.

같은 자리에서 필수 검토항목(0-2절)도 바꾼다. 종전 NDA 기본 이슈맵은 기술협업
NDA 의 사용자 요청(Background IP, 범용 AI 학습 제한, 음성·수면·건강 정보)을
그대로 담고 있어, 직원 서약서의 리포트에 **다른 계약의 요청사항**이 '사용자
검토항목 답변' 으로 나갔다. 직원 비밀유지계약에는 이 모듈의 이슈맵을 쓴다.

**하드코딩 금지** — 회사명·조항번호를 쓰지 않는다. 조항은 문형으로 찾고, 보호
대상 계열사는 담당자 요청과 `group_entities` 표에서, 관할은 거래모델에서 읽는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from runtime.review.employee_nda_model import (
    PD_LABELS,
    EmployeeNdaModel,
)
from runtime.review.mandatory_review_issues import (
    SOURCE_CONTRACT_TYPE_DEFAULT,
    SOURCE_LABELS,
    SOURCE_USER_REQUEST,
    VERDICT_NEEDS_FIX,
    VERDICT_OK,
    VERDICT_SEPARATE_AGREEMENT,
)


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════════
# 조항 찾기 — 문형으로, 번호로가 아니라
# ══════════════════════════════════════════════════════════════════════════

def _clause_attr(c: Any, key: str) -> str:
    if isinstance(c, dict):
        return str(c.get(key) or "")
    return str(getattr(c, key, "") or "")


def _find_clauses(clauses: list[Any], rx: re.Pattern[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for c in clauses or []:
        body = _clause_attr(c, "text")
        if body and rx.search(body):
            cid = _clause_attr(c, "clause_id")
            path = _clause_attr(c, "display_path") or cid
            title = _clause_attr(c, "title") or _clause_attr(c, "clause_title")
            name = re.sub(r"^[0-9.]+\s*", "", title).strip()
            label = f"{path}({name})" if name else path
            out.append((cid, label))
    return out


def _paths(hits: list[tuple[str, str]]) -> list[str]:
    return [p for _, p in hits]


def _ids(hits: list[tuple[str, str]]) -> list[str]:
    return [i for i, _ in hits]


# ══════════════════════════════════════════════════════════════════════════
# 1. 관할 고용법 점검표
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EmploymentLawCheck:
    key: str
    rule: str
    #: 이 점검이 적용되는 관할 — "us"(연방, 모든 주), "us_california" 등.
    applies_to: tuple[str, ...]
    #: 원문이 이 요구를 충족하는가(충족 문언의 문형).
    satisfied: re.Pattern[str] | None
    #: 이 점검이 **위반 문언**을 찾는 것이면 True — 매치되면 위반이다.
    violation_if_match: bool = False
    #: 미충족 시 넣을 완성 문안(영문 계약이므로 영문).
    fix_clause: str = ""
    note: str = ""


EMPLOYMENT_LAW_CHECKS: tuple[EmploymentLawCheck, ...] = (
    EmploymentLawCheck(
        key="noncompete_void",
        rule="Cal. Bus. & Prof. Code §16600·§16600.5 — 퇴직 후 경업금지 무효(체결지·서명지 불문)",
        applies_to=("us_california",),
        satisfied=_rx(r"non[- ]?compet|shall\s+not\s+(?:engage|compete|work\s+for)[^.]{0,80}(?:competitor|business)"),
        violation_if_match=True,
        fix_clause="Delete the post-employment non-competition covenant in its entirety.",
    ),
    EmploymentLawCheck(
        key="customer_nonsolicit_void",
        rule="Cal. Bus. & Prof. Code §16600 — 퇴직 후 고객유인 금지도 원칙적 무효(영업비밀 이용 금지로만 제한 가능)",
        applies_to=("us_california",),
        satisfied=_rx(r"(?:solicit|induce|divert)[^.]{0,60}(?:customers?|clients?)"),
        violation_if_match=True,
        fix_clause=(
            "Replace any customer non-solicitation covenant with: \"Employee will not use or disclose the "
            "Company's trade secrets to solicit any customer of the Company.\""
        ),
    ),
    EmploymentLawCheck(
        key="restraint_disclaimer",
        rule="Cal. Bus. & Prof. Code §16600 — 퇴직 후 직업선택의 자유를 제한하지 않는다는 해석 기준",
        applies_to=("us_california",),
        satisfied=_rx(r"16600|does\s+not\s+restrict[^.]{0,80}(?:employment|services)|nothing\s+in\s+this\s+agreement[^.]{0,80}restrain"),
    ),
    EmploymentLawCheck(
        key="required_by_law",
        rule="법원 명령·법령상 공개 의무 예외",
        applies_to=("us",),
        satisfied=_rx(r"required\s+by\s+law|court\s+order|subpoena"),
        fix_clause=(
            "Nothing in this Agreement prevents Employee from making a disclosure required by law, court order, "
            "or valid subpoena."
        ),
    ),
    EmploymentLawCheck(
        key="government_reporting",
        rule="정부기관 신고 보호(SEC Rule 21F-17, EEOC, NLRB 등) — 사전 통지·승인 요구 금지",
        applies_to=("us",),
        satisfied=_rx(r"government\s+agency|Securities\s+and\s+Exchange\s+Commission|\bSEC\b|Equal\s+Employment|EEOC"),
        fix_clause=(
            "Nothing in this Agreement prohibits Employee from reporting possible violations of law to any "
            "government agency, or from making other disclosures protected under whistleblower laws, without "
            "notice to or approval from the Company."
        ),
    ),
    EmploymentLawCheck(
        key="whistleblower_ca",
        rule="Cal. Labor Code §1102.5 — 내부고발 보호",
        applies_to=("us_california",),
        satisfied=_rx(r"1102\.5|whistleblower"),
        fix_clause=(
            "Nothing in this Agreement prevents Employee from making any disclosure protected under California "
            "Labor Code Section 1102.5."
        ),
    ),
    EmploymentLawCheck(
        key="dtsa_notice",
        rule="18 U.S.C. §1833(b) — 영업비밀 면책 고지(누락 시 징벌적 배상·변호사비용 청구 불가)",
        applies_to=("us",),
        satisfied=_rx(r"Defend\s+Trade\s+Secrets\s+Act|1833\s*\(b\)"),
        fix_clause=(
            "Pursuant to the Defend Trade Secrets Act of 2016, 18 U.S.C. §1833(b), Employee will not be held "
            "criminally or civilly liable under any federal or state trade secret law for the disclosure of a "
            "trade secret that is made in confidence to a government official or to an attorney solely for the "
            "purpose of reporting or investigating a suspected violation of law, or in a complaint or other "
            "document filed under seal in a lawsuit or other proceeding."
        ),
    ),
    EmploymentLawCheck(
        key="nlra_section7",
        rule="NLRA §7 — 근로조건에 관한 집단적 논의 보호(McLaren Macomb 기준)",
        applies_to=("us",),
        satisfied=_rx(r"National\s+Labor\s+Relations\s+Act|\bNLRA\b"),
        fix_clause=(
            "Nothing in this Agreement restricts Employee's rights under Section 7 of the National Labor "
            "Relations Act, including the right to discuss wages, hours, and other terms and conditions of "
            "employment."
        ),
    ),
    EmploymentLawCheck(
        key="wage_discussion",
        rule="Cal. Labor Code §232·§232.5 — 임금·근로조건 공개·논의 보호",
        applies_to=("us_california",),
        satisfied=_rx(r"Labor\s+Code\s+Sections?\s+232|discuss[^.]{0,40}(?:own\s+)?wages"),
        fix_clause=(
            "Nothing in this Agreement prevents Employee from disclosing or discussing Employee's own wages or "
            "working conditions as permitted by California Labor Code Sections 232 and 232.5."
        ),
    ),
    EmploymentLawCheck(
        key="unlawful_acts_workplace",
        rule=(
            "Cal. Gov. Code §12964.5(SB 331) — 고용 조건으로 체결하는 비공개 약정에는 직장 내 불법행위 "
            "공개권을 보장하는 법정 문구가 필요(없으면 해당 제한은 무효, 공정고용주택법 위반)"
        ),
        applies_to=("us_california",),
        satisfied=_rx(r"unlawful\s+acts?\s+in\s+the\s+workplace|12964\.5"),
        fix_clause=(
            "Nothing in this Agreement prevents Employee from discussing or disclosing information about unlawful "
            "acts in the workplace, such as harassment or discrimination or any other conduct that Employee has "
            "reason to believe is unlawful."
        ),
        note="캘리포니아 법정 문구는 원문 그대로 넣는 것이 안전합니다(§12964.5(a)(1)(B)(i)).",
    ),
    EmploymentLawCheck(
        key="choice_of_law_ca",
        rule="Cal. Labor Code §925 — 캘리포니아 근무자에게 타주 준거법·관할 강제 금지",
        applies_to=("us_california",),
        satisfied=_rx(r"laws?\s+of\s+(?:the\s+)?State\s+of\s+California|California\s+law"),
        fix_clause="This Agreement is governed by the laws of the State of California.",
    ),
)


def _applicable_checks(model: EmployeeNdaModel) -> list[EmploymentLawCheck]:
    key = model.jurisdiction_key
    if not key.startswith("us"):
        return []
    return [c for c in EMPLOYMENT_LAW_CHECKS if "us" in c.applies_to or key in c.applies_to]


def evaluate_employment_law(
    model: EmployeeNdaModel, *, contract_text: str, clauses: list[Any],
) -> dict[str, Any]:
    """관할 고용법 강행규정을 원문과 하나씩 대조한다."""
    checks = _applicable_checks(model)
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for ck in checks:
        hits = _find_clauses(clauses, ck.satisfied) if ck.satisfied is not None else []
        found = bool(hits) or bool(ck.satisfied and ck.satisfied.search(contract_text))
        ok = (not found) if ck.violation_if_match else found
        row = {
            "key": ck.key,
            "rule": ck.rule,
            "status": "충족" if ok else ("위반 문언 있음" if ck.violation_if_match else "누락"),
            "ok": ok,
            "clause_paths": _paths(hits),
            "clause_ids": _ids(hits),
            "fix_clause": "" if ok else ck.fix_clause,
            "note": ck.note,
        }
        # 경업금지·고객유인 금지는 '없음' 이 충족이므로 조항 인용이 없다. 대신
        # 무효 해석 기준 조항이 있으면 그 위치를 근거로 남긴다.
        rows.append(row)
        if not ok:
            missing.append(row)
    return {"jurisdiction": model.governing_law, "rows": rows, "missing": missing}


# ══════════════════════════════════════════════════════════════════════════
# 2. 계열사 기밀정보 보호
# ══════════════════════════════════════════════════════════════════════════

_RX_COMPANY_INCLUDES_AFFILIATES = _rx(
    r"[\"“]Company[\"”]\s*\)?[^.]{0,120}(?:and\s+its|together\s+with\s+its|including\s+its)\s+(?:subsidiaries\s+and\s+)?affiliat"
    r"|[\"“]Company[\"”]\s+(?:means|includes)[^.]{0,120}affiliat|회사[^.\n]{0,20}(?:및|와)\s*(?:그\s*)?계열사"
)
_RX_AFFILIATE_DEF = _rx(r"[\"“]Affiliates?[\"”]\s+(?:means|shall\s+mean)|affiliates?\s+(?:means|shall\s+mean)")
_RX_AFFILIATE_MENTION = _rx(r"affiliat|계열사|관계\s*회사")
_RX_THIRD_PARTY_BENEFICIARY = _rx(r"third[- ]party\s+beneficiar|제\s*3\s*자\s*(?:를\s*위한|수익자)|직접\s*(?:청구|권리를?\s*행사)")
_RX_OUTSIDE_COMPANY_BAN = _rx(r"(?:person|entity|persons|entities)\s+outside\s+the\s+Company|회사\s*외부|제\s*3\s*자에게\s*(?:공개|누설|제공)")
_RX_AFFILIATE_SHARING_OK = _rx(r"(?:disclos|shar)[^.]{0,60}(?:to|with)\s+(?:the\s+Company['’]?s\s+)?affiliates?|계열사[^.\n]{0,20}(?:공유|제공)[^.\n]{0,10}(?:할\s*수|허용)")


def _english_name(group_name: str) -> str:
    try:
        from runtime.review.group_entities import resolve_entity
    except Exception:  # noqa: BLE001
        return group_name
    ent = resolve_entity(group_name)
    if ent is None:
        return group_name
    for nm in (ent.name,) + tuple(ent.aliases):
        if re.fullmatch(r"[A-Za-z][A-Za-z .,&-]+", nm):
            return nm
    return group_name


def evaluate_affiliate_protection(
    model: EmployeeNdaModel, *, contract_text: str, clauses: list[Any],
) -> dict[str, Any]:
    """보호를 원하는 계열사가 이 계약으로 실제 보호되는지 당사자 구조에서 읽는다."""
    targets = list(model.requested_affiliates) or list(model.named_affiliates_in_contract)
    targets_en = [_english_name(t) for t in targets]
    mention_hits = _find_clauses(clauses, _RX_AFFILIATE_MENTION)
    named_hits: list[tuple[str, str]] = []
    for t_en in targets_en:
        named_hits += _find_clauses(clauses, re.compile(re.escape(t_en), re.IGNORECASE))
    defined = bool(_RX_AFFILIATE_DEF.search(contract_text))
    beneficiary = bool(_RX_THIRD_PARTY_BENEFICIARY.search(contract_text))
    outside_ban = _find_clauses(clauses, _RX_OUTSIDE_COMPANY_BAN)
    sharing_ok = bool(_RX_AFFILIATE_SHARING_OK.search(contract_text))

    company_def = _find_clauses(clauses, _RX_COMPANY_INCLUDES_AFFILIATES)
    points = [
        {
            "key": "company_definition",
            "label": "'Company' 정의에 계열사가 포함되는가",
            "ok": bool(company_def),
            "clause_paths": _paths(company_def),
            "finding": (
                "'Company' 정의가 계열사를 포함합니다." if company_def else
                f"'Company' 는 {model.employer_label or '계약 당사자 법인'} 하나로만 정의되어 있어, 계약상 의무·권리가 "
                "그 법인에만 귀속됩니다."
            ),
        },
        {
            "key": "information_covered",
            "label": "계열사 정보가 비밀정보 정의에 포함되는가",
            "ok": bool(mention_hits),
            "clause_paths": _paths(mention_hits),
            "finding": (
                "정의 조항이 '계열사(affiliates)'의 정보를 포함한다고 적고 있습니다."
                if mention_hits else "비밀정보 정의에 계열사 정보가 없습니다."
            ),
        },
        {
            "key": "affiliate_identified",
            "label": "보호 대상 계열사가 특정되는가",
            "ok": bool(named_hits) or defined,
            "clause_paths": _paths(named_hits),
            "finding": (
                "보호 대상 계열사가 이름 또는 정의로 특정됩니다."
                if (named_hits or defined) else
                f"'affiliates' 가 정의되지 않았고 {', '.join(targets_en) or '보호 대상 계열사'}가 계약 어디에도 "
                "명시되지 않아, 어느 법인이 포함되는지 다툼이 생길 수 있습니다."
            ),
        },
        {
            "key": "enforcement_right",
            "label": "계열사가 직접 권리를 행사할 수 있는가",
            "ok": beneficiary,
            "clause_paths": [],
            "finding": (
                "계열사를 제3자 수익자로 지정해 직접 집행할 수 있습니다." if beneficiary else
                f"계약 당사자는 {model.employer_label or '회사'}와 직원뿐입니다. 제3자 수익자 조항이 없어 "
                f"{', '.join(targets_en) or '계열사'}는 위반 시 직접 금지청구·손해배상을 청구하기 어렵고, "
                "회사가 대신 청구할 때도 계열사 손해를 회사 손해로 입증해야 합니다."
            ),
        },
        {
            "key": "internal_sharing",
            "label": "업무상 계열사 담당자에게 전달하는 것이 허용되는가",
            "ok": sharing_ok or not outside_ban,
            "clause_paths": _paths(outside_ban),
            "finding": (
                "계열사와의 업무상 공유가 허용됩니다." if (sharing_ok or not outside_ban) else
                "비공개 의무가 '회사 외부의 모든 사람·법인' 에 대한 공개를 금지하므로, 공동 회계·ERP 업무로 "
                "계열사 담당자에게 자료를 넘기는 것 자체가 문언상 위반이 됩니다."
            ),
        },
    ]
    missing = [p for p in points if not p["ok"]]
    names_en = " and ".join(targets_en) if targets_en else "[AFFILIATE NAME]"
    fix_clauses: list[str] = []
    if any(p["key"] in ("affiliate_identified", "company_definition") for p in missing):
        fix_clauses.append(
            f"\"Affiliate\" means any entity that directly or indirectly controls, is controlled by, or is under "
            f"common control with the Company, including {names_en}. References to the Company's Confidential "
            f"Information include the Confidential Information of each Affiliate."
        )
    if any(p["key"] == "enforcement_right" for p in missing):
        fix_clauses.append(
            f"Each Affiliate, including {names_en}, is an intended third-party beneficiary of this Agreement with "
            "respect to its Confidential Information and may enforce this Agreement directly."
        )
    if any(p["key"] == "internal_sharing" for p in missing):
        fix_clauses.append(
            "Employee may disclose Confidential Information to employees of the Company or its Affiliates who "
            "have a legitimate business need to know it in order to perform their job duties."
        )
    return {
        "targets": targets,
        "targets_en": targets_en,
        "points": points,
        "missing": missing,
        "fix_clauses": fix_clauses,
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. 직원 비밀유지계약 기본 이슈맵
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class EmployeeNdaIssue:
    code: str
    title: str
    evaluate: Callable[[EmployeeNdaModel, str, list[Any]], tuple[str, str, list[tuple[str, str]]]]
    #: 이 항목이 기본 이슈맵에 들어가는 조건. 없으면 항상.
    applies: Callable[[EmployeeNdaModel], bool] | None = None


def _eval_scope(m: EmployeeNdaModel, t: str, cl: list[Any]):
    hits = _find_clauses(cl, _rx(r"[\"“]Confidential\s+Information[\"”]\s+means|비밀정보[^.\n]{0,20}(?:말한다|의미한다)"))
    if hits and len(m.information_types) >= 3:
        return VERDICT_OK, "직무상 접근하는 정보 유형이 정의에 구체적으로 열거되어 있습니다.", hits
    return VERDICT_NEEDS_FIX, "정의가 직무상 실제 접근 정보를 구체적으로 열거하지 않습니다.", hits


def _eval_exclusions(m: EmployeeNdaModel, t: str, cl: list[Any]):
    hits = _find_clauses(cl, _rx(r"does\s+not\s+include|independently\s+developed|비밀정보에서\s*제외|포함하지\s*아니"))
    if hits:
        return VERDICT_OK, "공지·기보유·적법 수령·독자개발 정보가 예외로 규정되어 있습니다.", hits
    return VERDICT_NEEDS_FIX, "비밀정보 예외(공지·기보유·독자개발) 규정이 없습니다.", hits


def _eval_lawful_disclosure(m: EmployeeNdaModel, t: str, cl: list[Any]):
    ev = evaluate_employment_law(m, contract_text=t, clauses=cl)
    keys = {"required_by_law", "government_reporting", "whistleblower_ca", "dtsa_notice",
            "nlra_section7", "wage_discussion", "unlawful_acts_workplace"}
    rows = [r for r in ev["rows"] if r["key"] in keys]
    miss = [r for r in rows if not r["ok"]]
    hits = list(dict.fromkeys(
        (i, p) for r in rows for i, p in zip(r["clause_ids"], r["clause_paths"])
    ))
    if not rows:
        found = _find_clauses(cl, _rx(r"required\s+by\s+law|whistleblower|government\s+agency|법령에\s*따라|공익\s*신고"))
        return (VERDICT_OK if found else VERDICT_NEEDS_FIX,
                "법정 공개 예외가 있습니다." if found else "법정 공개 예외 규정이 없습니다.", found)
    if miss:
        return VERDICT_NEEDS_FIX, "누락: " + "; ".join(r["rule"] for r in miss), hits
    return VERDICT_OK, "관할이 요구하는 법정 공개 예외가 모두 있습니다.", hits


def _eval_restraint(m: EmployeeNdaModel, t: str, cl: list[Any]):
    present = m.noncompete_present or m.customer_nonsolicit_present or m.employee_nonsolicit_present
    disclaim = _find_clauses(cl, _rx(r"16600|does\s+not\s+restrict[^.]{0,80}(?:employment|services)"))
    if present and m.is_california:
        return VERDICT_NEEDS_FIX, "캘리포니아에서 무효인 퇴직 후 제한 문언이 있습니다.", disclaim
    if present:
        return VERDICT_NEEDS_FIX, "퇴직 후 제한이 있어 관할별 허용 범위(기간·지역·대상) 확인이 필요합니다.", disclaim
    return VERDICT_OK, "퇴직 후 경업금지·유인금지가 없고" + (" 제한하지 않는다는 해석 기준이 명시되어 있습니다." if disclaim else " 추가 제한도 없습니다."), disclaim


def _eval_personal_data(m: EmployeeNdaModel, t: str, cl: list[Any]):
    need = _find_clauses(cl, _rx(r"need\s+to\s+know|업무상\s*필요한\s*범위"))
    care = _find_clauses(cl, _rx(r"degree\s+of\s+care|security|보안|주의의무"))
    ret = _find_clauses(cl, _rx(r"return\s+all|permanently\s+delete|반환|삭제|파기"))
    hits = need + care + ret
    structure = PD_LABELS.get(m.personal_data_structure, "미확정")
    base = f"개인정보 취급 구조: {structure}."
    if m.personal_data_structure and m.personal_data_structure != "employee_internal_access":
        return VERDICT_SEPARATE_AGREEMENT, base + " 외부 위탁·제3자 제공은 별도 처리위탁·제공 계약으로 정합니다.", hits
    lacking = [n for n, h in (("업무상 필요 범위의 내부 접근 제한", need), ("보안·주의의무", care), ("퇴직 시 반환·삭제", ret)) if not h]
    if lacking:
        return VERDICT_NEEDS_FIX, base + " 누락: " + ", ".join(lacking), hits
    return VERDICT_OK, base + " 내부 접근 제한(need-to-know)·보안의무·퇴직 시 반환·삭제가 모두 있습니다.", hits


def _eval_return(m: EmployeeNdaModel, t: str, cl: list[Any]):
    hits = _find_clauses(cl, _rx(r"return\s+(?:all|of\s+Company)|permanently\s+delete|반환|파기"))
    if hits:
        return VERDICT_OK, "퇴직 시·요청 시 반환과 개인 기기 내 사본 삭제 의무가 있습니다.", hits
    return VERDICT_NEEDS_FIX, "퇴직 시 반환·삭제 의무가 없습니다.", hits


def _eval_duration(m: EmployeeNdaModel, t: str, cl: list[Any]):
    hits = _find_clauses(cl, _rx(r"surviv|continue\s+during\s+employment|퇴직\s*후에도|존속"))
    if hits:
        return VERDICT_OK, "재직 중과 퇴직 후(정보가 비밀인 동안) 의무가 존속합니다.", hits
    return VERDICT_NEEDS_FIX, "퇴직 후 비밀유지의무의 존속이 정해지지 않았습니다.", hits


def _eval_governing_law(m: EmployeeNdaModel, t: str, cl: list[Any]):
    hits = _find_clauses(cl, _rx(r"governed\s+by|준거법|governing\s+law"))
    if not m.governing_law:
        return VERDICT_NEEDS_FIX, "준거법이 정해지지 않았습니다.", hits
    return VERDICT_OK, f"준거법은 {m.governing_law}입니다. 근무지가 같은 관할이면 강행규정과 충돌하지 않습니다.", hits


def _eval_ip(m: EmployeeNdaModel, t: str, cl: list[Any]):
    return VERDICT_SEPARATE_AGREEMENT, "창작 직무인데 업무 성과물 귀속 조항이 없습니다 — 발명양도 약정(캘리포니아는 Labor Code §2870 고지 포함)을 별도로 둡니다.", []


EMPLOYEE_NDA_ISSUES: tuple[EmployeeNdaIssue, ...] = (
    EmployeeNdaIssue("enda_confidentiality_scope", "비밀정보 정의가 직무상 접근 정보를 포괄하는지", _eval_scope),
    EmployeeNdaIssue("enda_exclusions", "비밀정보 예외(공지·기보유·독자개발)", _eval_exclusions),
    EmployeeNdaIssue("enda_lawful_disclosure", "법정 공개 예외(법원명령·정부신고·내부고발·임금논의·영업비밀 면책 고지)", _eval_lawful_disclosure),
    EmployeeNdaIssue("enda_post_employment_restraint", "퇴직 후 제한(경업금지·고객/직원 유인금지)의 효력", _eval_restraint),
    EmployeeNdaIssue("enda_personal_data_internal", "직원 개인정보의 내부 접근 통제·보안·목적 외 이용 금지", _eval_personal_data),
    EmployeeNdaIssue("enda_return_deletion", "퇴직 시 자료 반환·삭제", _eval_return),
    EmployeeNdaIssue("enda_duration_survival", "비밀유지의무의 존속기간", _eval_duration),
    EmployeeNdaIssue("enda_governing_law", "준거법·관할", _eval_governing_law),
    EmployeeNdaIssue(
        "enda_ip_assignment", "업무 성과물·직무발명 귀속", _eval_ip,
        applies=lambda m: (not m.ip_assignment_present)
        and bool(re.search(r"engineer|developer|designer|R\s*&\s*D|research|개발|디자인|설계|연구", m.position or "", re.IGNORECASE)),
    ),
)


# ══════════════════════════════════════════════════════════════════════════
# 4. 사용자 요청 인식 — 판단형 요청 두 가지
# ══════════════════════════════════════════════════════════════════════════

_RX_REQ_EMPLOYMENT_LAW = _rx(
    r"노동법|고용법|근로기준|근로\s*관계\s*법|employment\s+law|labor\s+law|labour\s+law"
    r"|(?:캘리포니아|California|주)\s*(?:법|law)[^.\n]{0,30}(?:적법|위반|유효|검토|문제)"
    r"|적법(?:한지|성)|강행\s*규정"
)
_RX_REQ_AFFILIATE = _rx(r"계열사|양사|두\s*회사|관계\s*회사|affiliat|both\s+(?:companies|entities)")

_RX_REQ_PRIVACY = _rx(r"개인정보|급여|인사\s*정보|privacy|personal\s+(?:data|information)|\bPII\b")
_RX_REQ_PRIVACY_ANSWER = _rx(
    r"(?:내부|사내|회사\s*직원)[^\n]{0,40}개인정보[^\n]{0,20}취급|개인정보[^\n]{0,40}(?:내부|직원이)[^\n]{0,20}(?:취급|처리)"
)

USER_ISSUE_EMPLOYMENT_LAW = "enda_user_employment_law"
USER_ISSUE_AFFILIATE = "enda_user_affiliate_protection"
USER_ISSUE_PRIVACY = "enda_user_employee_privacy"
NEEDS_FACT_CHECK = "NEEDS_FACT_CHECK"


#: 요청 문장의 표지 — 배경 설명(대상자·담당업무·신청 배경)과 요청을 가른다.
RX_REQUEST_VERB = _rx(
    r"검토|확인|여부|해\s*주|알려|가능한지|가능\s*여부|문제|적법|보호할\s*수|\?|review|confirm|whether|advise"
)
_RX_BULLET_SPLIT = re.compile(r"\n|(?:^|\s)(?:[●•◦▪■□◆◇▶►※*]|\d+[.)])\s*")


def _split_requests(review_focus: str) -> list[str]:
    """담당자 서술을 줄·글머리표 단위로 나눈다. 답변 블록은 요청이 아니다."""
    body = str(review_focus or "").split("[사용자 확인 답변]")[0]
    parts = _RX_BULLET_SPLIT.split(body)
    # 공백을 정규화하지 않는다 — 요청 문장은 담당자 원문의 **부분 문자열**이어야
    # 자가점검(사용자 요청 날조 금지)을 통과한다.
    out = [p.strip(" -\t\r") for p in parts]
    return [p for p in out if len(p) >= 4]


def _pick(segments: list[str], rx: re.Pattern[str], extra: Callable[[str], bool] | None = None) -> str:
    """주제에 맞는 조각 중 **요청 문장**을 우선 고른다(배경 설명보다)."""
    cands = [s for s in segments if rx.search(s) or (extra is not None and extra(s))]
    asks = [s for s in cands if RX_REQUEST_VERB.search(s)]
    return (asks or cands or [""])[0]


def detect_user_requests(model: EmployeeNdaModel, review_focus: str) -> list[dict[str, str]]:
    """담당자 요청 중 이 모듈이 판단으로 답해야 할 것을 찾는다."""
    segs = _split_requests(review_focus)
    out: list[dict[str, str]] = []
    law = _pick(segs, _RX_REQ_EMPLOYMENT_LAW)
    if law:
        out.append({"code": USER_ISSUE_EMPLOYMENT_LAW, "text": law})
    aff_names: list[str] = []
    try:
        from runtime.review.group_entities import resolve_entity

        for n in model.requested_affiliates:
            ent = resolve_entity(n)
            aff_names += list(ent.all_names()) if ent is not None else [n]
    except Exception:  # noqa: BLE001
        aff_names = list(model.requested_affiliates)
    # 한 문장에 두 요청이 함께 있을 수 있다("…적법한지, 계열사 정보도 보호되는지")
    # — 다른 문장을 먼저 보되, 없으면 같은 문장을 쓴다.
    aff = _pick(
        [s for s in segs if s != law] + ([law] if law else []), _RX_REQ_AFFILIATE,
        extra=lambda s: any(n.lower() in s.lower() for n in aff_names),
    )
    if aff and (RX_REQUEST_VERB.search(aff) or model.requested_affiliates):
        out.append({"code": USER_ISSUE_AFFILIATE, "text": aff})
    priv = _pick([s for s in segs if s not in (law, aff)], _RX_REQ_PRIVACY)
    if priv and RX_REQUEST_VERB.search(priv):
        out.append({"code": USER_ISSUE_PRIVACY, "text": priv})
    else:
        # 사전질문 답변으로 "직원이 내부적으로 개인정보를 취급" 한다고 알려 왔으면
        # 그 자체가 판단을 요구하는 사실이다(지시 7·8항 — 직접 답한다). 요청
        # 문장은 담당자가 **실제로 쓴 문장**을 그대로 쓴다 — 지어낸 문장을 요청으로
        # 기록하면 자가점검이 정당하게 막는다.
        for line in str(review_focus or "").splitlines():
            if _RX_REQ_PRIVACY_ANSWER.search(line):
                said = re.sub(r"^\s*-\s*[^:\n]{0,80}:\s*", "", line).strip()
                out.append({"code": USER_ISSUE_PRIVACY, "text": said or line.strip()})
                break
    return out


# ══════════════════════════════════════════════════════════════════════════
# 5. 답변 조립
# ══════════════════════════════════════════════════════════════════════════

def _employment_law_answer(model: EmployeeNdaModel, text: str, clauses: list[Any]) -> dict[str, Any]:
    ev = evaluate_employment_law(model, contract_text=text, clauses=clauses)
    rows = ev["rows"]
    if not rows:
        return {
            "verdict": VERDICT_NEEDS_FIX,
            "direct_answer": (
                f"준거법({model.governing_law or '미기재'})에 대한 고용법 점검표가 없어 결론을 내리지 않았습니다. "
                "근무지 관할의 강행규정(경업금지·내부고발 보호·영업비밀 면책 고지)을 확인해야 합니다."
            ),
            "rows": [], "clause_ids": [], "clause_paths": [], "fix_clauses": [],
        }
    from runtime.review.checklists.employee_nda import dtsa_elements

    ok_rows = [r for r in rows if r["ok"]]
    miss = ev["missing"]
    paths: list[str] = []
    ids: list[str] = []
    for r in rows:
        for i, p in zip(r["clause_ids"], r["clause_paths"]):
            if p not in paths:
                paths.append(p)
                ids.append(i)
    # 한 조항만 보지 않는다 — 비밀유지·DTSA·임금논의·내부고발·경업금지·존속기간·
    # 직원 개인정보를 묶어 판단한다(지시 5항).
    dt = dtsa_elements(text)
    dtsa_line = (
        "DTSA 고지는 §1833(b) 네 요소(정부·변호사 공개, 봉인 제출, 보복소송 시 사용)를 모두 갖췄습니다"
        if dt["present"] and all(dt[k] for k in ("government_official", "attorney", "sealed_filing", "retaliation_lawsuit"))
        else ("DTSA 고지가 일부 요소를 빠뜨렸습니다" if dt["present"] else "DTSA 고지가 없습니다")
    )
    restraint_line = (
        "퇴직 후 경업금지·고객유인 금지가 없고 직업선택 자유를 제한하지 않는다는 문언이 있습니다"
        if not (model.noncompete_present or model.customer_nonsolicit_present)
        else "캘리포니아에서 무효인 퇴직 후 제한 문언이 있습니다"
    )
    duration_line = (
        "존속기간은 '정보가 비밀인 동안' 으로 묶이고 일반 지식·경험 사용이 허용되어 경업금지로 기능하지 않습니다"
        if re.search(r"for\s+as\s+long\s+as[^.]{0,80}confidential", text, re.IGNORECASE)
        and re.search(r"general\s+knowledge,\s*skill", text, re.IGNORECASE)
        else "존속기간이 영업비밀·일반 비밀정보·일반 지식을 구분하지 않습니다"
    )
    effect = "; ".join([
        f"강행규정 {len(ok_rows)}개 충족("
        + ", ".join(r["rule"].split(" — ")[0] for r in ok_rows if r["clause_paths"]) + ")",
        dtsa_line, restraint_line, duration_line,
    ]) + "."
    judgment = (
        f"{model.governing_law} 고용법 강행규정 {len(rows)}개 중 {len(ok_rows)}개 충족. "
        + ("미충족: " + "; ".join(r["rule"] for r in miss) + "." if miss else "미충족 없음.")
    )
    if miss:
        verdict = VERDICT_NEEDS_FIX
        conclusion = (
            "기존 공개 예외·직업선택 자유·DTSA 문구는 그대로 두고, 빠진 문장만 법정 공개 예외 조항에 추가하면 "
            "적법합니다."
        )
    else:
        verdict = VERDICT_OK
        conclusion = "현재 문언은 적법합니다 — 수정할 필요가 없습니다."
    parts = {
        "relevant_clauses": ", ".join(paths) or "해당 조항 없음",
        "current_effect": effect,
        "legal_judgment": judgment,
        "conclusion": conclusion,
    }
    return {
        "verdict": verdict,
        "direct_answer": _compose(parts),
        "parts": parts,
        "rows": rows,
        "clause_ids": ids,
        "clause_paths": paths,
        "fix_clauses": [r["fix_clause"] for r in miss if r["fix_clause"]],
    }


def _compose(parts: dict[str, str]) -> str:
    return (
        f"[관련 조항] {parts['relevant_clauses']} "
        f"[현재 문구의 효과] {parts['current_effect']} "
        f"[법률 판단] {parts['legal_judgment']} "
        f"[결론] {parts['conclusion']}"
    )


def _affiliate_answer(model: EmployeeNdaModel, text: str, clauses: list[Any]) -> dict[str, Any]:
    ev = evaluate_affiliate_protection(model, contract_text=text, clauses=clauses)
    names = ", ".join(ev["targets_en"]) or "계열사"
    own = model.employer_label or "회사"
    paths: list[str] = []
    for p in ev["points"]:
        for x in p["clause_paths"]:
            if x not in paths:
                paths.append(x)
    ids = [i for i, _ in _find_clauses(clauses, _RX_AFFILIATE_MENTION) + _find_clauses(clauses, _RX_OUTSIDE_COMPANY_BAN)]
    effect = " ".join(p["finding"] for p in ev["points"])
    if not ev["missing"]:
        parts = {
            "relevant_clauses": ", ".join(paths) or "해당 조항 없음",
            "current_effect": effect,
            "legal_judgment": f"{own}와 {names}가 모두 보호 주체로 특정되고 집행 수단도 있습니다.",
            "conclusion": "양사 기밀정보가 모두 보호됩니다 — 수정할 필요가 없습니다.",
        }
        return {
            "verdict": VERDICT_OK, "direct_answer": _compose(parts), "parts": parts,
            "points": ev["points"], "clause_ids": ids, "clause_paths": paths, "fix_clauses": [],
        }
    parts = {
        "relevant_clauses": ", ".join(paths) or "해당 조항 없음",
        "current_effect": effect,
        "legal_judgment": (
            f"현재 문언으로는 {own}의 기밀정보만 온전히 보호되고, {names}의 기밀정보는 정의 조항의 포괄 문언에 기대 "
            "간접적으로만 보호됩니다. 미흡: " + ", ".join(p["label"] for p in ev["missing"]) + "."
        ),
        "conclusion": (
            f"정의 조항에 계열사 정의({names} 명시)를 넣고, 계열사를 제3자 수익자로 지정하며, 계열사 담당자와의 "
            "업무상 공유를 허용하는 문장을 추가하면 양사 모두 보호됩니다."
        ),
    }
    return {
        "verdict": VERDICT_NEEDS_FIX,
        "direct_answer": _compose(parts),
        "parts": parts,
        "points": ev["points"],
        "clause_ids": ids,
        "clause_paths": paths,
        "fix_clauses": ev["fix_clauses"],
    }


def _privacy_answer(model: EmployeeNdaModel, text: str, clauses: list[Any]) -> dict[str, Any]:
    """직원 개인정보 — 계약 층위와 법률 층위를 나눠 답한다(지시 7·8항).

    NDA 가 정보유출을 막는지(계약)와, 회사의 개인정보 컴플라이언스(법률·내부
    정책)는 다른 층위다. NDA 만으로 컴플라이언스가 끝났다고도, 개인정보 접근이
    있다는 이유만으로 모든 개인정보법이 적용된다고도 판단하지 않는다.
    """
    from runtime.review.employee_nda_model import INFO_TYPE_LABELS

    structure = PD_LABELS.get(model.personal_data_structure, "미확정")
    basis = {"user_answer": "담당자 답변", "contract": "계약 구조"}.get(model.personal_data_basis, "")
    covered = [INFO_TYPE_LABELS[t] for t in ("payroll_hr_personal", "banking_credentials", "tax", "financial") if t in model.information_types]
    need = _find_clauses(clauses, _rx(r"need\s+to\s+know|업무상\s*필요한\s*범위"))
    care = _find_clauses(clauses, _rx(r"degree\s+of\s+care|security|보안|주의\s*의무"))
    ret = _find_clauses(clauses, _rx(r"return\s+all|permanently\s+delete|반환|파기"))
    incident = bool(_rx(r"(?:notify|report)[^.]{0,80}(?:unauthori[sz]ed|breach|incident|loss)|유출\s*사실[^.\n]{0,20}(?:통지|보고)").search(text))
    policy = bool(_rx(r"(?:comply|compliance)[^.]{0,60}polic|보안\s*정책|개인정보\s*(?:처리)?\s*방침").search(text))
    have = [n for n, h in (("업무상 필요 범위 접근 제한", need), ("보안·주의의무", care), ("퇴직 시 반환·삭제", ret)) if h]
    lack = [n for n, ok in (
        ("업무상 필요 범위 접근 제한", bool(need)), ("보안·주의의무", bool(care)),
        ("무단 접근·유출 사고 통지", incident), ("회사 개인정보·정보보안 정책 준수", policy),
        ("퇴직 시 반환·삭제", bool(ret)),
    ) if not ok]
    paths = list(dict.fromkeys(_paths(need + care + ret)))
    ids = list(dict.fromkeys(_ids(need + care + ret)))
    fact_checks: list[str] = []
    law_layer = ""
    if model.is_california:
        fact_checks.append(
            "CCPA/CPRA 적용요건 — 회사가 캘리포니아에서 사업을 하며 연 매출이 기준액(물가연동, 2025년 약 2,660만 달러) "
            "을 넘거나, 연 10만 명 이상 소비자·가구의 개인정보를 매매·공유하거나, 매출의 50% 이상을 개인정보 판매·공유에서 "
            "얻는지. 해당하면 2023년부터 직원 개인정보에도 수집 고지·열람·삭제 요구권이 적용됩니다."
        )
        law_layer = (
            " 법률 층위: 이 서약서는 직원의 유출을 막는 계약일 뿐, 회사 자신의 개인정보 컴플라이언스(수집 고지·보유기간·"
            "직원의 열람·삭제권)를 해결하지 않습니다. Cal. Civ. Code §1798.81.5의 합리적 보안조치 의무는 캘리포니아 "
            "주민 개인정보를 보유하는 사업자에게 일반적으로 적용되고, CCPA/CPRA 적용 여부는 아래 요건 확인이 필요합니다"
            f"({NEEDS_FACT_CHECK})."
        )
    verdict = VERDICT_NEEDS_FIX if lack else VERDICT_OK
    parts = {
        "relevant_clauses": ", ".join(paths) or "해당 조항 없음",
        "current_effect": (
            f"개인정보 취급 구조는 {structure}입니다{f'({basis})' if basis else ''} — 외부 처리위탁·제3자 제공 계약이 "
            "필요한 구조가 아닙니다. "
            + (f"정의 조항이 {', '.join(covered)}를 보호대상으로 열거합니다. " if covered else "정의 조항에 직원 개인정보 유형이 열거되지 않았습니다. ")
            + (f"이미 있는 보호: {', '.join(have)}." if have else "")
        ),
        "legal_judgment": (
            (f"계약 층위 — 빠진 보호: {', '.join(lack)}." if lack else "계약 층위 — 필요한 보호가 모두 있습니다.")
            + law_layer
        ),
        "conclusion": (
            ("기존 주의의무 조항 뒤에 빠진 의무를 한 문장씩 추가합니다. " if lack else "")
            + "NDA 는 유출 방지 수단이므로, 회사의 직원 개인정보 처리 고지·보안 정책은 별도로 갖춰야 합니다."
        ),
    }
    return {
        "verdict": verdict,
        "direct_answer": _compose(parts),
        "parts": parts,
        "clause_ids": ids,
        "clause_paths": paths,
        "fix_clauses": [],
        "fact_checks": fact_checks,
    }


def build_employee_nda_review(
    model: EmployeeNdaModel,
    *,
    contract_text: str,
    clauses: list[Any],
    review_focus: str = "",
) -> dict[str, Any]:
    """mandatory_review_issues 답변(사용자 요청 우선)과 요청별 직접 답변을 만든다."""
    text = str(contract_text or "")
    answers: list[dict[str, Any]] = []
    user_answers: list[dict[str, Any]] = []

    for req in detect_user_requests(model, review_focus):
        if req["code"] == USER_ISSUE_EMPLOYMENT_LAW:
            a = _employment_law_answer(model, text, clauses)
            title = f"{model.governing_law or '관할'} 고용법(노동법)상 적법성"
        elif req["code"] == USER_ISSUE_PRIVACY:
            a = _privacy_answer(model, text, clauses)
            title = "직원 개인정보(HR·급여·재무) 내부 취급의 보호 충분성"
        else:
            a = _affiliate_answer(model, text, clauses)
            title = f"{model.employer_label or '회사'} + {', '.join(_english_name(t) for t in model.requested_affiliates) or '계열사'} 기밀정보 보호 가능 여부"
        row = {
            "code": req["code"],
            "title": title,
            "source": SOURCE_USER_REQUEST,
            "source_label": SOURCE_LABELS[SOURCE_USER_REQUEST],
            "original_user_text": req["text"],
            "verdict": a["verdict"],
            "basis": "employee_nda_review",
            "direct_answer": a["direct_answer"],
            "evidence_clause_ids": a["clause_ids"][:8],
            "evidence_clause_paths": a["clause_paths"][:8],
            "fix_clauses": a["fix_clauses"],
        }
        for k in ("rows", "points", "fact_checks", "parts"):
            if k in a:
                row[k] = a[k]
        answers.append(row)
        user_answers.append(row)

    for issue in EMPLOYEE_NDA_ISSUES:
        if issue.applies is not None and not issue.applies(model):
            continue
        verdict, why, hits = issue.evaluate(model, text, clauses)
        answers.append({
            "code": issue.code,
            "title": issue.title,
            "source": SOURCE_CONTRACT_TYPE_DEFAULT,
            "source_label": SOURCE_LABELS[SOURCE_CONTRACT_TYPE_DEFAULT],
            "verdict": verdict,
            "basis": "employee_nda_review",
            "direct_answer": why,
            "evidence_clause_ids": _ids(hits)[:5],
            "evidence_clause_paths": _paths(hits)[:5],
        })
    return {"mandatory_review_issues": answers, "user_requests": user_answers}


def compute_mandatory_review_answers(
    *,
    contract_type_code: str,
    review_focus: str | None,
    contract_text: str,
    clauses: list[Any],
    clause_results: list[dict[str, Any]],
    entity: str = "",
    model: EmployeeNdaModel | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """필수 검토항목 답변을 **한 곳에서만** 만든다.

    검토 파이프라인과 DOCX/PDF 다운로드 경로가 각자 이슈맵을 다시 만들면서
    어긋났다 — 다운로드 경로는 원문도 거래모델도 넘기지 않아, 검토에서 걸러낸
    기술협업 NDA 항목이 수정본 워드파일의 '사용자 검토항목 답변' 에 다시
    나갔다(2026-09-28 실측). 두 경로 모두 이 함수를 부른다.

    반환: (mandatory_review_issues 답변, 직원 비밀유지계약 검토 결과 또는 None)
    """
    from runtime.review.employee_nda_model import resolve_employee_nda_model
    from runtime.review.mandatory_review_issues import (
        answer_mandatory_review_issues,
        derive_mandatory_review_issues,
    )

    if model is None:
        model = resolve_employee_nda_model(
            contract_text=str(contract_text or ""),
            user_description=str(review_focus or ""),
            entity=str(entity or ""),
            contract_type_code=str(contract_type_code or ""),
        )
    if model.is_employee_nda and model.confident:
        review = build_employee_nda_review(
            model, contract_text=str(contract_text or ""), clauses=clauses,
            review_focus=str(review_focus or ""),
        )
        return list(review["mandatory_review_issues"]), review
    issues = derive_mandatory_review_issues(
        contract_type_code=str(contract_type_code or ""),
        review_focus=review_focus,
        contract_text=str(contract_text or ""),
    )
    return answer_mandatory_review_issues(
        issues, clause_results=clause_results, full_text=str(contract_text or ""),
    ), None


def all_requests_answered_by_review(coverage: list[dict[str, Any]] | None) -> bool:
    """사용자 요청이 전부 판단형 답변으로 채워졌는가 — 그러면 '의미 분석 실패'
    안내는 사실이 아니다(요청마다 직접 답을 냈다)."""
    rows = [r for r in (coverage or []) if isinstance(r, dict)]
    return bool(rows) and all(str(r.get("answered_by") or "") == "employee_nda_review" for r in rows)


def apply_to_user_review_coverage(
    coverage: list[dict[str, Any]] | None,
    user_answers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """사용자 요청 커버리지 행을 판단형 답변으로 채운다.

    같은 요청을 조항 검색으로 답한 행("해당 조항 없음 / 사실관계 추가확인")이
    있으면 그 행을 **대체**한다 — generic 결과로 요청을 답하지 않는다(지시 5항).
    """
    from difflib import SequenceMatcher

    def _n(s: str) -> str:
        return re.sub(r"[\s●•◦▪■□◆◇▶►※*:\-]+", " ", str(s or "")).strip().lower()

    rows = [dict(r) for r in (coverage or []) if isinstance(r, dict)]
    for ua in user_answers:
        text = str(ua.get("original_user_text") or "")
        nt = _n(text)
        target = None
        best = 0.0
        for r in rows:
            if str(r.get("answered_by") or ""):
                continue
            ot = _n(str(r.get("original_user_text") or ""))
            if not ot or not nt:
                continue
            if ot == nt:
                score = 1.0
            elif len(ot) >= 8 and (ot in nt or nt in ot):
                score = 0.9 * min(len(ot), len(nt)) / max(len(ot), len(nt)) + 0.1
            else:
                score = SequenceMatcher(None, ot, nt).ratio()
            if score > best:
                best, target = score, r
        if best < 0.6:
            target = None
        needs = ua["verdict"] != VERDICT_OK
        payload = {
            "normalized_issue": ua["title"],
            "relevant_clause": ", ".join(ua.get("evidence_clause_paths") or []) or "해당 조항 없음",
            "relevant_clause_ids": list(ua.get("evidence_clause_ids") or []),
            "relevant_clause_paths": list(ua.get("evidence_clause_paths") or []),
            "answer_clause_paths": list(ua.get("evidence_clause_paths") or []),
            "direct_answer": ua["direct_answer"],
            "review_status": ua["verdict"],
            "needs_revision": needs,
            "conclusion": ua["direct_answer"],
            "proposed_clauses": list(ua.get("fix_clauses") or []),
            "catalog_code": ua["code"],
            "answered_by": "employee_nda_review",
        }
        if target is not None:
            target.update(payload)
        else:
            rows.append({
                "issue_id": ua["code"],
                "source": "explicit_user_request",
                "original_user_text": text,
                "issue_topic": ua["code"],
                "custom_user_issue": True,
                "matched_finding_ids": [],
                **payload,
            })
    # 검토 요청이 아닌 배경 서술(대상자·담당업무·신청 배경 등)은 요청 행으로
    # 두지 않는다 — 키워드 fallback 이 담당자 메모를 줄마다 요청으로 세어
    # '사실관계 추가확인' 행이 줄줄이 생겼다. 배경 사실은 거래모델이 읽는다.
    kept: list[dict[str, Any]] = []
    for r in rows:
        ot = str(r.get("original_user_text") or "")
        if str(r.get("answered_by") or ""):
            kept.append(r)
        elif RX_REQUEST_VERB.search(ot) and not _RX_PROCESS_NOTE.search(ot):
            kept.append(r)
    return kept


#: 진행 절차 메모 — "검토 의견 반영 후 서명 진행" 은 검토 요청이 아니다.
_RX_PROCESS_NOTE = _rx(r"반영\s*후|서명\s*(?:진행|예정)|완료\s*기한|진행\s*예정|일정")
