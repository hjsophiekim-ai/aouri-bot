"""임직원 비밀유지계약(Employee NDA) — 기존 보호조항 KEEP + 실질 공백만 최소수정.

2026-09-28 2차 지시. 실측(신규 입사자 비밀유지계약, California, AI 사용):

    HIGH  Article 5  "임금·근로조건 논의 권리 명확화 필요"
                     → 제안 문구가 원문 (c) 와 **같은 문장**이었다(no-op redline)
    HIGH  counsel    "경업금지로 해석될 위험 차단 필요"
                     → 제8조·제11조에 이미 "다른 사용자 취업을 제한하지 않는다" 가 있다
    HIGH  Article 6  DTSA 고지 → 이미 §1833(b) 네 요소를 모두 갖췄다
    HIGH  counsel    가처분 문구 반복 → 제10조에 이미 있다
    MED   Article 8  "영구 비밀유지는 무효 위험" → 정보가 비밀인 동안만 존속 +
                     일반 지식·경험 사용 허용이 이미 있다
    지위  supplier / buyer (AI Legal Map override)

반대로 실제 공백 — 계열사(SIDIZ America) 정보의 보호 주체·범위, 캘리포니아
Gov. Code §12964.5 법정 문구 — 는 finding 으로 하나도 나오지 않았다.

많이 고치는 것이 아니라, 이미 잘 막은 것은 KEEP 하고 강행법·계열사·직원
개인정보의 **실질 공백만** 최소 추가문안으로 잡는다.

이 모듈이 하는 일
──────────────
1. `employee_nda_protections()` — 계약이 이미 갖춘 보호 축과 그 근거 조항.
2. `apply_employee_nda_final_gate()` — 최종 출력 직전에 모든 finding 을 감사:
     · 다른 계약유형 축(단가·세금·하도급·대리점·공사·광고·공급) → 제거
     · 공급업자/수탁자/도급인 등 다른 지위로 부른 finding → 제거
     · 이미 보호된 축을 다시 고치자는 finding → KEEP_EXISTING_CLAUSE
     · 원문과 실질적으로 같은 제안 → REVIEW_FAILED_NO_OP_REDLINE 기록 후 KEEP
3. `run_employee_nda_checklist()` — 공백에만 최소 추가문안(기존 조항 뒤에 한
   문장씩 덧붙인다 — 기존 carve-out·직업선택 자유 문구·DTSA·가처분은 건드리지
   않는다).

**하드코딩 금지** — 조항번호·회사명을 쓰지 않는다. 조항은 문형으로 찾고, 계열사는
거래모델(담당자 요청 + `group_entities`)에서, 관할은 준거법 조항에서 읽는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable

from runtime.review.employee_nda_model import EmployeeNdaModel

KEEP_EXISTING_CLAUSE = "KEEP_EXISTING_CLAUSE"
REVIEW_FAILED_NO_OP_REDLINE = "REVIEW_FAILED_NO_OP_REDLINE"
REVIEW_FAILED_PARTY_ROLE_MISMATCH = "REVIEW_FAILED_PARTY_ROLE_MISMATCH"
FINDING_REJECTED_OUT_OF_SCOPE = "FINDING_REJECTED_OUT_OF_SCOPE"


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


def _attr(c: Any, key: str) -> str:
    if isinstance(c, dict):
        return str(c.get(key) or "")
    return str(getattr(c, key, "") or "")


def _find(clauses: list[Any], rx: re.Pattern[str]) -> list[Any]:
    return [c for c in clauses or [] if rx.search(_attr(c, "text"))]


def _path(c: Any) -> str:
    p = _attr(c, "display_path") or _attr(c, "clause_id")
    t = re.sub(r"^[0-9.]+\s*", "", _attr(c, "title") or _attr(c, "clause_title")).strip()
    return f"{p}({t})" if t else p


# ══════════════════════════════════════════════════════════════════════════
# 1. 이미 갖춘 보호 축
# ══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ProtectionAxis:
    key: str
    label: str
    #: 이 축을 다루는 finding 인지(제목·사유·제안문구) — KEEP 대상 판별.
    topic: re.Pattern[str]
    #: 계약이 이 축을 이미 충분히 갖췄는지.
    satisfied: Callable[[EmployeeNdaModel, str, list[Any]], list[Any]]


_RX_DTSA_ELEMENTS = (
    _rx(r"government\s+official|federal,\s*state,\s*or\s*local\s+government"),
    _rx(r"attorney"),
    _rx(r"under\s+seal"),
    _rx(r"retaliation"),
)


def dtsa_elements(text: str) -> dict[str, bool]:
    """18 U.S.C. §1833(b) 고지의 네 요소 — 존재가 아니라 **충족**을 본다."""
    body = str(text or "")
    dtsa = re.search(r"Defend\s+Trade\s+Secrets\s+Act|1833\s*\(b\)", body, re.IGNORECASE)
    if not dtsa:
        return {"present": False, "government_official": False, "attorney": False,
                "sealed_filing": False, "retaliation_lawsuit": False}
    window = body[dtsa.start(): dtsa.start() + 2000]
    keys = ("government_official", "attorney", "sealed_filing", "retaliation_lawsuit")
    out = {"present": True}
    for k, rx in zip(keys, _RX_DTSA_ELEMENTS):
        out[k] = bool(rx.search(window))
    return out


def _sat_noncompete(m: EmployeeNdaModel, t: str, cl: list[Any]) -> list[Any]:
    if m.noncompete_present or m.customer_nonsolicit_present:
        return []
    return _find(cl, _rx(r"does\s+not\s+restrict[^.]{0,80}(?:employment|services)|16600|general\s+knowledge,\s*skill"))


def _sat_dtsa(m: EmployeeNdaModel, t: str, cl: list[Any]) -> list[Any]:
    el = dtsa_elements(t)
    if el["present"] and all(el[k] for k in ("government_official", "attorney", "sealed_filing", "retaliation_lawsuit")):
        return _find(cl, _rx(r"Defend\s+Trade\s+Secrets\s+Act|1833"))
    return []


def _sat_by(rx: re.Pattern[str]) -> Callable[[EmployeeNdaModel, str, list[Any]], list[Any]]:
    return lambda m, t, cl: _find(cl, rx)


def _sat_duration(m: EmployeeNdaModel, t: str, cl: list[Any]) -> list[Any]:
    # 무기한이라도 "정보가 비밀인 동안" 으로 묶여 있고 일반 지식·경험 사용이
    # 허용되면 경업금지로 기능하지 않는다(지시 11항 — 세 범주 구분).
    tied = _find(cl, _rx(r"for\s+as\s+long\s+as[^.]{0,80}(?:confidential|trade\s+secret)|비밀로\s*유지되는\s*동안|영업비밀[^.\n]{0,20}(?:존속|동안)"))
    skill = _rx(r"general\s+knowledge,\s*skill|일반적인?\s*지식|숙련").search(t)
    return tied if (tied and skill) else []


PROTECTION_AXES: tuple[ProtectionAxis, ...] = (
    ProtectionAxis(
        "employee_freedom", "퇴직 후 직업선택 자유(경업금지 없음)",
        _rx(r"경업|non[- ]?compet|직업\s*선택|16600|restrain|전직|취업\s*제한|accept\s+employment"),
        _sat_noncompete,
    ),
    ProtectionAxis(
        "dtsa_notice", "DTSA 면책 고지(§1833(b) 네 요소 충족)",
        _rx(r"DTSA|Defend\s+Trade\s+Secrets|1833|영업비밀\s*(?:면책|고지)"),
        _sat_dtsa,
    ),
    ProtectionAxis(
        "wage_discussion", "임금·근로조건 논의권(Labor Code §232·§232.5, NLRA §7)",
        _rx(r"임금|근로\s*조건|wage|232|NLRA|National\s+Labor|Section\s+7|concerted"),
        _sat_by(_rx(r"Labor\s+Code\s+Sections?\s+232|discuss[^.]{0,40}wages|National\s+Labor\s+Relations\s+Act")),
    ),
    ProtectionAxis(
        "whistleblower", "내부고발·정부기관 신고(Labor Code §1102.5 등)",
        _rx(r"내부\s*고발|공익\s*신고|whistle|1102\.5|정부\s*기관|government\s+agency|신고"),
        _sat_by(_rx(r"1102\.5|whistleblower")),
    ),
    ProtectionAxis(
        "required_disclosure", "법령·법원 명령에 따른 공개",
        _rx(r"법원\s*명령|subpoena|court\s+order|required\s+by\s+law|법령상\s*공개"),
        _sat_by(_rx(r"required\s+by\s+law|court\s+order|subpoena")),
    ),
    ProtectionAxis(
        "injunctive_relief", "금지명령 등 형평법상 구제",
        _rx(r"injunct|금지\s*명령|가처분|irreparable|equitable|형평법"),
        _sat_by(_rx(r"injunctive\s+(?:or\s+other\s+equitable\s+)?relief|가처분")),
    ),
    ProtectionAxis(
        "return_deletion", "퇴직 시 반환·삭제",
        _rx(r"반환|삭제|파기|return|delet|destroy"),
        _sat_by(_rx(r"return\s+all|permanently\s+delete|반환|파기")),
    ),
    ProtectionAxis(
        "duration", "존속기간(정보가 비밀인 동안 + 일반 지식·경험 사용 허용)",
        _rx(r"존속|영구|무기한|indefinite|perpetual|surviv|duration|비밀유지\s*기간"),
        _sat_duration,
    ),
    ProtectionAxis(
        "exclusions", "비밀정보 예외(공지·기보유·독자개발)",
        _rx(r"예외|exclusion|independently\s+developed|공지|기보유"),
        _sat_by(_rx(r"does\s+not\s+include|independently\s+developed")),
    ),
)


def employee_nda_protections(
    model: EmployeeNdaModel, *, contract_text: str, clauses: list[Any],
) -> dict[str, dict[str, Any]]:
    """계약이 이미 갖춘 보호 축 → 근거 조항."""
    out: dict[str, dict[str, Any]] = {}
    for ax in PROTECTION_AXES:
        hits = ax.satisfied(model, str(contract_text or ""), clauses)
        if hits:
            out[ax.key] = {
                "label": ax.label,
                "clause_ids": [_attr(c, "clause_id") for c in hits],
                "clause_paths": [_path(c) for c in hits],
            }
    return out


# ══════════════════════════════════════════════════════════════════════════
# 2. 최종 감사 게이트
# ══════════════════════════════════════════════════════════════════════════

#: 다른 계약유형 축 — (finding 문형, 원문 근거 문형).
_FOREIGN_DOMAIN_AXES: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    ("price", _rx(r"계약\s*단가|납품\s*단가|단가\s*(?:산정|인하)|대금\s*지급|지급\s*기한|지연\s*이자|late\s+(?:payment|interest)"),
     _rx(r"단가|대금|용역비|계약금액|\bfees?\s+(?:of|payable|shall)|\$\s?\d")),
    ("tax", _rx(r"부가가치세|세금계산서|원천\s*징수|특수\s*관계|부당행위"),
     _rx(r"부가가치세|\bVAT\b|세금계산서|withholding\s+tax|related\s+part")),
    ("subcontract", _rx(r"하도급|재하도급|수급사업자|원사업자"),
     _rx(r"하도급|subcontract")),
    ("dealer", _rx(r"대리점|재판매|경영\s*간섭|판매\s*정책|판매\s*목표"),
     _rx(r"대리점|\bdealers?\b|resale|재판매")),
    ("construction", _rx(r"공사\s*대금|준공|기성|착공|하자\s*보수|건설"),
     _rx(r"공사|construction|준공")),
    ("advertising", _rx(r"광고\s*(?:비|매체|집행)|매체\s*(?:집행|송출)|표시\s*광고"),
     _rx(r"광고|advertis")),
    ("supply", _rx(r"납품|검수|인수\s*검사|하자\s*담보|물품\s*공급|공급\s*계약"),
     _rx(r"납품|검수|deliver(?:y|ables)|goods|supply\s+of")),
)
#: 이 계약에 존재할 수 없는 지위로 당사자를 부르는 finding.
#: 판단 문장(제목·문제·사유)에서만 본다 — 원문 인용·제안문구에는 계약 자체의
#: 낱말("contractor", "vendor")이 정상적으로 들어간다.
_RX_FOREIGN_ROLE = _rx(r"공급업자|수탁자|수급인|도급인|대리점주|판매대리인")

#: 체크리스트가 이미 다루는 공백 — 같은 공백을 AI 가 따로 지적하면 중복이다.
_GAP_TOPICS: dict[str, re.Pattern[str]] = {
    "affiliate_protection": _rx(r"계열사|affiliat|SIDIZ|시디즈|third[- ]party\s+beneficiar|제3자\s*수익자"),
    "employment_rights": _rx(r"12964\.5|SB\s*331|unlawful\s+acts|harass|불법\s*행위|괴롭힘|차별"),
    "employee_data": _rx(r"사고\s*(?:통지|보고)|incident|breach\s+notif|보안\s*정책|개인정보\s*(?:처리)?\s*방침|privacy\s+polic"),
}


def _finding_blob(cr: dict[str, Any]) -> str:
    return "\n".join(
        str(cr.get(k) or "") for k in (
            "issue_title", "clause_title", "problem", "rewrite_reason",
            "legal_business_reason", "suggested_rewrite",
        )
    )


def _norm_for_noop(s: str) -> str:
    s = re.sub(r"\.\.\.|…", " ", str(s or ""))
    s = re.sub(r"^\s*\d+\.\s*[A-Z][^\n]{0,60}\n", " ", s)  # 조 제목 줄
    s = re.sub(r"[^\w가-힣]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def is_no_op_redline(original: str, rewrite: str) -> bool:
    """제안 문구가 원문과 실질적으로 같은가(지시 4항).

    제안이 원문 일부를 그대로 옮긴 것이거나(생략부호로 앞뒤를 줄인 경우 포함),
    글자 단위로 거의 같으면 수정이 아니다.
    """
    o = _norm_for_noop(original)
    r = _norm_for_noop(rewrite)
    if not r or not o:
        return False
    if r in o:
        return True
    # 생략부호로 나뉜 조각이 전부 원문에 있으면 새로 더한 것이 없다.
    pieces = [_norm_for_noop(p) for p in re.split(r"\.\.\.|…", str(rewrite or ""))]
    pieces = [p for p in pieces if len(p) >= 12]
    if pieces and all(p in o for p in pieces):
        return True
    return SequenceMatcher(None, o, r).ratio() >= 0.95


def _to_keep(cr: dict[str, Any], *, code: str, reason: str) -> None:
    cr["keep_as_is"] = True
    cr["display_kind"] = "keep"
    cr["risk_tier"] = "LOW"
    cr["severity"] = "LOW"
    cr["high_risk"] = False
    cr["must_fix"] = False
    cr["approval_required"] = False
    cr["review_tier"] = "KEEP"
    cr["has_rewrite_change"] = False
    cr["suggested_rewrite"] = ""
    cr["redline_instruction"] = None
    cr["keep_code"] = code
    cr["keep_reason"] = reason
    cr["rewrite_reason"] = reason


def apply_employee_nda_final_gate(
    clause_results: list[dict[str, Any]],
    *,
    model: EmployeeNdaModel | None,
    contract_text: str,
    clauses: list[Any],
) -> dict[str, Any]:
    """최종 출력 직전 감사(지시 17항). clause_results 를 제자리에서 고친다."""
    report: dict[str, Any] = {
        "applied": False, "removed": [], "kept_existing": [], "no_op": [], "protections": {},
    }
    if model is None or not (model.is_employee_nda and model.confident):
        return report
    body = str(contract_text or "")
    protections = employee_nda_protections(model, contract_text=body, clauses=clauses)
    report["applied"] = True
    report["protections"] = protections

    checklist_tags = {
        t for cr in (clause_results or []) if isinstance(cr, dict) and cr.get("is_employee_nda_checklist")
        for t in (cr.get("employee_nda_tags") or [])
    }
    keep: list[dict[str, Any]] = []
    for cr in clause_results or []:
        if not isinstance(cr, dict):
            continue
        if bool(cr.get("is_employee_nda_checklist")):
            keep.append(cr)
            continue
        if bool(cr.get("keep_as_is")) or str(cr.get("display_kind") or "") == "keep":
            keep.append(cr)
            continue
        blob = _finding_blob(cr)
        cid = str(cr.get("clause_id") or "")

        reasoning = "\n".join(
            str(cr.get(k) or "") for k in ("issue_title", "problem", "rewrite_reason", "legal_business_reason")
        )
        foreign = [k for k, q, basis in _FOREIGN_DOMAIN_AXES if q.search(blob) and not basis.search(body)]
        if foreign or _RX_FOREIGN_ROLE.search(reasoning):
            report["removed"].append({
                "clause_id": cid, "code": FINDING_REJECTED_OUT_OF_SCOPE,
                "reason": ("다른 계약유형의 축: " + ", ".join(foreign)) if foreign
                else "임직원 비밀유지계약에 존재하지 않는 지위(공급업자·수탁자 등)로 당사자를 불렀습니다.",
            })
            continue

        rewrite = str(cr.get("suggested_rewrite") or "")
        original = str(cr.get("original_text") or "")
        if rewrite.strip() and is_no_op_redline(original, rewrite):
            reason = "제안 문구가 현재 원문과 실질적으로 같아 수정이 아닙니다 — 현행 유지."
            _to_keep(cr, code=REVIEW_FAILED_NO_OP_REDLINE, reason=reason)
            report["no_op"].append({"clause_id": cid, "code": REVIEW_FAILED_NO_OP_REDLINE})
            keep.append(cr)
            continue

        dup = next((tag for tag, rx in _GAP_TOPICS.items() if tag in checklist_tags and rx.search(blob)), "")
        if dup:
            report["removed"].append({
                "clause_id": cid, "code": "DUPLICATE_OF_EMPLOYEE_NDA_CHECKLIST",
                "reason": f"같은 공백({dup})을 최소 추가문안 항목이 이미 다룹니다.",
            })
            continue

        hit_axis = None
        for ax in PROTECTION_AXES:
            if ax.key in protections and ax.topic.search(blob):
                hit_axis = ax
                break
        if hit_axis is not None and str(cr.get("risk_tier") or cr.get("severity") or "").upper() in ("HIGH", "MEDIUM", "LOW"):
            prot = protections[hit_axis.key]
            reason = (
                f"{hit_axis.label} — {', '.join(prot['clause_paths'][:2])}에 이미 충분한 보호문구가 있어 "
                "현행 유지합니다(중복 수정 금지)."
            )
            _to_keep(cr, code=KEEP_EXISTING_CLAUSE, reason=reason)
            report["kept_existing"].append({"clause_id": cid, "axis": hit_axis.key, "code": KEEP_EXISTING_CLAUSE})
            keep.append(cr)
            continue
        keep.append(cr)

    clause_results[:] = keep
    return report


def build_employee_nda_legal_map(
    model: EmployeeNdaModel, *, contract_text: str, clauses: list[Any],
) -> dict[str, Any]:
    """Employee NDA 전용 Legal Map(지시 13항) — 대가·검수·준공·세금 축은 없다.

    각 축에 값과 근거 조항을 채운다. 비어 있는 축은 '미기재' 로 두되, 그것이
    곧 결함인지는 체크리스트가 판단한다(Map 은 사실의 기록이다).
    """
    from runtime.review.employee_nda_model import INFO_TYPE_LABELS, PD_LABELS

    body = str(contract_text or "")
    prot = employee_nda_protections(model, contract_text=body, clauses=clauses)

    def cite(rx: str) -> list[str]:
        return [_path(c) for c in _find(clauses, _rx(rx))][:3]

    def axis(value: str, paths: list[str]) -> dict[str, Any]:
        return {"value": value or "미기재", "clause_paths": paths}

    dt = dtsa_elements(body)
    return {
        "schema": "employee_nda",
        "axes": {
            "employer_employee": axis(
                f"{model.employer_label} (employer) / {model.employee_label} (employee)"
                + (f" — {model.position}" if model.position else ""), []),
            "confidential_information": axis(
                ", ".join(INFO_TYPE_LABELS.get(t, t) for t in model.information_types),
                cite(r"[\"“]Confidential\s+Information[\"”]\s+means|비밀정보[^.\n]{0,20}(?:말한다|의미한다)")),
            "trade_secrets": axis(
                "DTSA 고지 포함" if dt["present"] else ("영업비밀 언급" if "trade_secret" in model.information_types else ""),
                cite(r"trade\s+secret|영업\s*비밀")),
            "affiliate_information": axis(
                ("정의 조항에 계열사 정보 포함" if model.contract_mentions_affiliates else "")
                + (f" / 보호 요청: {', '.join(model.requested_affiliates)}" if model.requested_affiliates else ""),
                cite(r"affiliat|계열사")),
            "employee_personal_data": axis(
                PD_LABELS.get(model.personal_data_structure, ""), cite(r"payroll|employee\s+compensation|급여|인사")),
            "post_employment_obligations": axis(
                (prot.get("duration") or {}).get("label", ""), (prot.get("duration") or {}).get("clause_paths", [])),
            "dtsa_notice": axis(
                "§1833(b) 네 요소 충족" if "dtsa_notice" in prot else ("일부 누락" if dt["present"] else ""),
                (prot.get("dtsa_notice") or {}).get("clause_paths", [])),
            "protected_disclosures": axis(
                ", ".join(prot[k]["label"] for k in ("required_disclosure", "whistleblower", "wage_discussion") if k in prot),
                sorted({p for k in ("required_disclosure", "whistleblower", "wage_discussion") if k in prot
                        for p in prot[k]["clause_paths"]})),
            "noncompete_restriction": axis(
                "경업금지 있음" if model.noncompete_present else (
                    "없음 — 직업선택 자유 명시" if "employee_freedom" in prot else "없음"),
                (prot.get("employee_freedom") or {}).get("clause_paths", [])),
            "return_deletion": axis(
                "퇴직·요청 시 반환·삭제" if "return_deletion" in prot else "",
                (prot.get("return_deletion") or {}).get("clause_paths", [])),
            "governing_law": axis(model.governing_law, cite(r"governed\s+by|준거법")),
        },
        "not_applicable_axes": [
            "payment_flow", "acceptance_and_completion", "risk_transfer_point", "tax",
        ],
    }


def check_party_roles(canonical_state: dict[str, Any] | None, model: EmployeeNdaModel | None) -> dict[str, Any]:
    """확정된 사용자/직원 지위가 최종 출력까지 유지됐는가(지시 1항)."""
    if model is None or not (model.is_employee_nda and model.confident):
        return {"checked": False, "status": ""}
    cs = canonical_state or {}
    ok = str(cs.get("party_role") or "") == "employer" and str(cs.get("counterparty_role") or "") == "employee"
    return {
        "checked": True,
        "status": "" if ok else REVIEW_FAILED_PARTY_ROLE_MISMATCH,
        "detail": "" if ok else (
            f"임직원 비밀유지계약인데 최종 지위가 {cs.get('party_role')}/{cs.get('counterparty_role')} 입니다."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════
# 3. 실질 공백 — 최소 추가문안
# ══════════════════════════════════════════════════════════════════════════

_RX_ANCHOR_DEFINITION = _rx(r"[\"“]Confidential\s+Information[\"”]\s+means|비밀정보[^.\n]{0,20}(?:말한다|의미한다)")
_RX_ANCHOR_NONDISCLOSURE = _rx(r"(?:person|entity)\s+outside\s+the\s+Company|제\s*3\s*자에게\s*(?:누설|공개|제공)")
#: 법정 공개 예외 조항 — 비공개 의무 조항 안의 "as required by law" 가 먼저
#: 걸리지 않도록 예외를 **정하는** 문형을 앞세운다.
_RX_ANCHOR_CARVE = _rx(r"Nothing\s+in\s+this\s+Agreement\s+(?:prevents|prohibits|restricts)|공개할\s*수\s*있는\s*경우|예외적으로\s*공개")
_RX_ANCHOR_CARVE_FALLBACK = _rx(r"required\s+by\s+law|법령에\s*따라")
_RX_ANCHOR_CARE = _rx(r"degree\s+of\s+care|reasonable\s+degree|security|주의\s*의무|보안")
_RX_ANCHOR_NONCOMPETE = _rx(r"non[- ]?compet|shall\s+not\s+(?:engage|compete)|경업|경쟁\s*업체")


def _excerpt(text: str, rx: re.Pattern[str]) -> str:
    body = str(text or "")
    m = rx.search(body)
    if not m:
        return ""
    start = body.rfind("\n", 0, m.start()) + 1
    end = body.find("\n", m.end())
    return body[start: end if end != -1 else len(body)].strip()[:400]


def _anchor(clauses: list[Any], rx: re.Pattern[str]) -> Any | None:
    hits = _find(clauses, rx)
    return hits[0] if hits else None


def _finding(
    *, check_id: str, severity: str, anchor: Any | None, quote: str, title: str,
    problem: str, legal: str, addition: str, basis: str, tags: list[str],
) -> dict[str, Any]:
    from runtime.review.redline_instruction import build_redline_instruction

    art = _attr(anchor, "article_number") if anchor is not None else ""
    path = _attr(anchor, "display_path") if anchor is not None else "신설 조항"
    title_a = re.sub(r"^[0-9.]+\s*", "", _attr(anchor, "title")).strip() if anchor is not None else ""
    loc = f"{path}({title_a}) 말미에 추가" if anchor is not None else "본 계약 말미에 신설 (특정 조항 아님 — 계약 전반 사항)"
    redline = build_redline_instruction(
        clause_id=check_id, severity=severity, edit_location=loc,
        edit_type="insert_after" if anchor is not None else "new_clause",
        replacement_text=addition, reason=problem,
    )
    return {
        "clause_id": check_id,
        "article_number": art or None,
        "display_path": path,
        "clause_title": title[:60],
        "clause_topic": "confidentiality",
        "risk_tier": severity,
        "severity": severity,
        "high_risk": severity == "HIGH",
        "must_fix": severity == "HIGH",
        "approval_required": severity == "HIGH",
        "review_tier": "MUST" if severity == "HIGH" else "SUGGEST",
        "high_severity_basis": basis,
        "issue_title": title,
        "original_text": quote,
        "problem": problem,
        "legal_business_reason": legal,
        "suggested_rewrite": addition,
        "rewrite_reason": problem,
        "redline_instruction": redline,
        "has_rewrite_change": True,
        "display_kind": "redline" if severity == "HIGH" else "guidance",
        "confidence": 0.9,
        "is_mandatory": True,
        "is_employee_nda_checklist": True,
        "employee_nda_tags": list(tags),
    }


def run_employee_nda_checklist(
    model: EmployeeNdaModel | None,
    *,
    contract_text: str,
    clauses: list[Any],
    review_focus: str = "",
) -> list[dict[str, Any]]:
    """실질 공백에만 최소 추가문안을 낸다. 이미 갖춘 축은 건드리지 않는다."""
    if model is None or not (model.is_employee_nda and model.confident):
        return []
    from runtime.review.employee_nda_review import (
        evaluate_affiliate_protection,
        evaluate_employment_law,
    )

    body = str(contract_text or "")
    english = model.employee_label == "Employee"
    out: list[dict[str, Any]] = []

    # ── [Affiliate Protection Package] 회사 정의 → 계열사 정의 → 비밀정보 → 집행
    if model.requested_affiliates or model.named_affiliates_in_contract:
        aff = evaluate_affiliate_protection(model, contract_text=body, clauses=clauses)
        if aff["missing"] and aff["fix_clauses"] and english:
            anchor = _anchor(clauses, _RX_ANCHOR_DEFINITION)
            names = ", ".join(aff["targets_en"])
            out.append(_finding(
                check_id="ENDA-AFFILIATE",
                severity="HIGH" if model.requested_affiliates else "MEDIUM",
                anchor=anchor,
                quote=_excerpt(body, _RX_ANCHOR_DEFINITION),
                title=f"계열사({names}) 기밀정보 보호 주체·범위 불명확",
                problem=" ".join(p["finding"] for p in aff["missing"]),
                legal=(
                    "'Company' 는 계약 당사자 법인 하나만 가리키고 'affiliates' 는 정의되지 않았습니다. 계열사 정보는 "
                    "정의 조항의 포괄 문언에 기대어 간접적으로만 보호되며, 계열사는 계약 당사자가 아니어서 직접 "
                    "집행할 수 없습니다. 계열사 업무를 함께 수행하는 직원이면 업무상 공유 자체가 문언상 위반이 됩니다."
                ),
                addition=" ".join(aff["fix_clauses"]),
                basis="계열사 기밀정보 보호 실패",
                tags=["affiliate_protection"],
            ))

    # ── [Employment Rights Package] 관할 강행규정의 누락 carve-out 만
    ev = evaluate_employment_law(model, contract_text=body, clauses=clauses)
    carve_keys = {"required_by_law", "government_reporting", "whistleblower_ca", "dtsa_notice",
                  "nlra_section7", "wage_discussion", "unlawful_acts_workplace"}
    missing = [r for r in ev["missing"] if r["key"] in carve_keys and r["fix_clause"]]
    dtsa = dtsa_elements(body)
    if dtsa["present"] and not all(dtsa[k] for k in ("government_official", "attorney", "sealed_filing", "retaliation_lawsuit")):
        missing.append({
            "key": "dtsa_incomplete",
            "rule": "18 U.S.C. §1833(b) — 고지 요소 일부 누락(" + ", ".join(
                k for k in ("government_official", "attorney", "sealed_filing", "retaliation_lawsuit") if not dtsa[k]
            ) + ")",
            "fix_clause": (
                "An individual who files a lawsuit for retaliation by an employer for reporting a suspected violation "
                "of law may disclose the trade secret to the individual's attorney and use the trade secret "
                "information in the court proceeding, if the individual files any document containing the trade "
                "secret under seal and does not disclose the trade secret except pursuant to court order."
            ),
        })
    if missing:
        high_keys = {"whistleblower_ca", "government_reporting", "dtsa_notice", "unlawful_acts_workplace", "wage_discussion"}
        severity = "HIGH" if any(r["key"] in high_keys for r in missing) else "MEDIUM"
        _carve_rx = _RX_ANCHOR_CARVE if _anchor(clauses, _RX_ANCHOR_CARVE) is not None else _RX_ANCHOR_CARVE_FALLBACK
        anchor = _anchor(clauses, _carve_rx)
        out.append(_finding(
            check_id="ENDA-CARVEOUT",
            severity=severity,
            anchor=anchor,
            quote=_excerpt(body, _carve_rx),
            title=f"{model.governing_law or '관할'} 고용법상 필수 공개 예외 누락: " + ", ".join(
                r["rule"].split(" — ")[0] for r in missing
            ),
            problem="누락된 법정 공개 예외: " + "; ".join(r["rule"] for r in missing),
            legal=(
                "고용 조건으로 받는 비밀유지 서약이 법정 공개 예외를 갖추지 않으면 그 제한 부분이 무효가 되거나 "
                "사용자에게 제재가 따릅니다. 기존 예외 문구는 그대로 두고 빠진 문장만 추가합니다."
            ),
            addition=" ".join(r["fix_clause"] for r in missing),
            basis="캘리포니아 강행법 위반 가능성" if model.is_california else "법정 공개 예외 누락",
            tags=["employment_rights"],
        ))

    # ── [Employee Data Package] HR·급여·재무 → 접근통제 → 보안 → 사고 → 반환
    if "payroll_hr_personal" in model.information_types or model.personal_data_internal:
        need = bool(_rx(r"need\s+to\s+know|업무상\s*필요한\s*범위").search(body))
        care = bool(_rx(r"degree\s+of\s+care|security|보안|주의\s*의무").search(body))
        incident = bool(_rx(r"(?:notify|report)[^.]{0,80}(?:unauthori[sz]ed|breach|incident|loss)|유출\s*사실[^.\n]{0,20}(?:통지|보고)").search(body))
        policy = bool(_rx(r"(?:comply|compliance)[^.]{0,60}polic|보안\s*정책|개인정보\s*(?:처리)?\s*방침").search(body))
        adds: list[str] = []
        gaps: list[str] = []
        if not need:
            gaps.append("업무상 필요 범위(need-to-know) 내 접근 제한")
            adds.append("Employee will access personal information of Company personnel, customers, or vendors only to the extent necessary to perform Employee's job duties.")
        if not care:
            gaps.append("보안·주의의무")
            adds.append("Employee will maintain the security of all such information in accordance with reasonable administrative, technical, and physical safeguards.")
        if not incident:
            gaps.append("무단 접근·유출 사고 통지")
            adds.append("Employee will promptly notify the Company of any actual or suspected unauthorized access to, use, or disclosure of Confidential Information, including personal information of Company personnel.")
        if not policy:
            gaps.append("회사 개인정보·정보보안 정책 준수")
            adds.append("Employee will comply with the Company's information security and privacy policies as in effect from time to time.")
        if adds and english:
            severity = "HIGH" if (not need and not care) else "MEDIUM"
            anchor = _anchor(clauses, _RX_ANCHOR_CARE)
            out.append(_finding(
                check_id="ENDA-EMPLOYEE-DATA",
                severity=severity,
                anchor=anchor,
                quote=_excerpt(body, _RX_ANCHOR_CARE),
                title="직원 개인정보(HR·급여·재무) 내부 접근 보호 공백: " + ", ".join(gaps),
                problem=(
                    "직원이 업무상 다른 직원의 급여·인사·금융 정보에 접근하는 구조(내부 접근 — 처리위탁·제3자 제공 "
                    "아님)인데, 다음 보호가 없습니다: " + ", ".join(gaps) + "."
                ),
                legal=(
                    "비밀유지 의무만으로는 사고 발생 시 회사가 알 수 있는 통로가 없고, 합리적 보안조치 의무"
                    "(예: Cal. Civ. Code §1798.81.5)를 회사가 이행했다는 근거도 약해집니다. 기존 주의의무 조항 뒤에 "
                    "빠진 의무만 추가합니다."
                ),
                addition=" ".join(adds),
                basis="직원 민감정보 보호 공백" if severity == "HIGH" else "직원 개인정보 보호 보완",
                tags=["employee_data"],
            ))

    # ── [정보유형 대조] 담당자가 설명한 HR·재무 정보가 정의에 들어 있는가(지시 14항)
    user = str(review_focus or "")
    wants_hr = bool(_rx(r"급여|인사|HR|payroll|personnel").search(user))
    wants_fin = bool(_rx(r"재무|회계|financial|accounting|세무|tax").search(user))
    lacks = []
    if wants_hr and "payroll_hr_personal" not in model.information_types:
        lacks.append("employee personnel, payroll, compensation, and benefits information")
    if wants_fin and "financial" not in model.information_types:
        lacks.append("financial, accounting, tax, and banking information")
    if lacks and english:
        anchor = _anchor(clauses, _RX_ANCHOR_DEFINITION)
        out.append(_finding(
            check_id="ENDA-INFO-TYPES",
            severity="MEDIUM",
            anchor=anchor,
            quote=_excerpt(body, _RX_ANCHOR_DEFINITION),
            title="담당자가 설명한 접근 정보 유형이 비밀정보 정의에 없음",
            problem="담당자 설명상 직원이 접근하는 정보 유형이 정의 조항에 열거되지 않았습니다: " + "; ".join(lacks),
            legal="보호 대상 정보를 구체적으로 열거해야 합리적 비밀관리 노력이 인정되고 분쟁 시 범위 다툼이 줄어듭니다.",
            addition="Confidential Information includes " + " and ".join(lacks) + ".",
            basis="보호대상 정의 보완",
            tags=["information_types"],
        ))

    # ── 퇴직 후 경업금지 — 캘리포니아는 무효(삭제), 그 외는 범위 축소
    if model.noncompete_present:
        anchor = _anchor(clauses, _RX_ANCHOR_NONCOMPETE)
        if model.is_california and english:
            out.append(_finding(
                check_id="ENDA-NONCOMPETE",
                severity="HIGH",
                anchor=anchor,
                quote=_excerpt(body, _RX_ANCHOR_NONCOMPETE),
                title="캘리포니아에서 무효인 퇴직 후 경업금지",
                problem="Cal. Bus. & Prof. Code §16600·§16600.5에 따라 퇴직 후 경업금지는 무효이며, 사용자는 무효 고지 의무(§16600.1)와 손해배상 책임을 질 수 있습니다.",
                legal="영업비밀 보호는 비밀유지·영업비밀 이용 금지로 충분히 달성되므로 경업금지는 삭제합니다.",
                addition="Nothing in this Agreement restricts Employee from engaging in any lawful profession, trade, or business following separation from the Company.",
                basis="unlawful noncompete",
                tags=["noncompete"],
            ))

    # ── 존속기간 — 영업비밀/일반 비밀정보/일반 지식·경험 세 범주(지시 11항)
    if english and not _sat_duration(model, body, clauses):
        perpetual = bool(_rx(r"indefinite|perpetual|in\s+perpetuity|at\s+any\s+time\s+after").search(body))
        skill = bool(_rx(r"general\s+knowledge,\s*skill").search(body))
        if perpetual or not skill:
            anchor = _anchor(clauses, _rx(r"surviv|continue\s+during\s+employment|after\s+employment"))
            adds = []
            if perpetual:
                adds.append(
                    "Employee's obligations with respect to trade secrets continue for so long as the information "
                    "remains a trade secret under applicable law, and with respect to other Confidential Information "
                    "for so long as it remains confidential."
                )
            if not skill:
                adds.append(
                    "Nothing in this Agreement restricts Employee's use of general knowledge, skill, and experience "
                    "acquired during employment."
                )
            out.append(_finding(
                check_id="ENDA-DURATION",
                severity="MEDIUM",
                anchor=anchor,
                quote=_excerpt(body, _rx(r"surviv|continue\s+during\s+employment|after\s+employment")),
                title="퇴직 후 비밀유지 존속기간의 범주 구분",
                problem="영업비밀·일반 비밀정보·직원의 일반 지식과 경험이 구분되지 않아, 존속기간이 경업금지처럼 작동한다고 다툴 여지가 있습니다.",
                legal="영업비밀은 비밀성이 유지되는 한 보호하고, 일반 비밀정보는 비밀인 동안으로 묶으며, 일반 지식·경험은 제한하지 않는 것이 표준입니다.",
                addition=" ".join(adds),
                basis="존속기간 보완",
                tags=["duration"],
            ))
    return out
