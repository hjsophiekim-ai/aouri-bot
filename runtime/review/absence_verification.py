"""부재 판정(“해당 조항 없음 / 신설 필요”) 전 계약 전문 강제 재검색.

2026-09-21 지시 6·7항 —
  "어떤 finding 을 '해당 조항 없음 / 신설 필요' 로 판단하기 전에 계약 전체에서
   관련 개념을 다시 검색하세요. 동의어까지 검색하고, 관련 조항이 하나라도
   있으면 '없음' 으로 판단 금지."
  "실제 존재하는 보호장치를 부재로 판단하면 전체 검토 실패
   (REVIEW_FAILED_SOURCE_CONTRADICTION)."

왜 개별 룰의 정규식을 고치는 것으로 끝내지 않는가
────────────────────────────────────────────
실측(인테리어 2차 본계약, 2026-09-21). 체크리스트 CWS-01 이
"재하도급의 허용 여부·범위와 발주자 승인 요건이 계약에 없음" 을 올렸다.
그런데 계약에는 제21조(하도급)가 실재하고 제2항이 바로 그 "사전 서면 승인"
을 정하고 있다. 원인은 그 체크의 `satisfied_when` 정규식이 "승인 → 서면"
어순만 상정하고 "서면 승인" 어순을 놓친 것이었다. 같은 사고가 CWC-*, eb_*,
counsel_* 등 서로 다른 생성기에서 각자의 정규식으로 반복된다.

판정은 두 갈래로 나눈다 — 넓게 잡으면 정당한 지적까지 지운다
──────────────────────────────────────────────────────
처음에 "부재를 말하는 항목 전부 × 개념 존재" 로 단순하게 걸었더니, 보증
조항(제16조)에 제대로 붙은 "보증금 **반환 시점**이 정해져 있지 않음" 같은
정당한 보완 지적까지 지워졌다. 조항 자체가 없다는 주장과, 있는 조항의 한
요소가 빠졌다는 주장은 다르다. 그래서:

  A. **보호장치 대조표**(지시 7항이 열거한 6가지) — 주장 문구와 계약 문언을
     각각 정밀 패턴으로 대조한다. 걸리면 제거하고 전체 검토 실패를 세운다.
  B. **일반 규칙**(지시 6항) — 부재를 말하는 항목 중
     · 어느 조항에도 붙어 있지 않은 것(신설 권고)은 개념이 계약 어딘가에
       있으면 제거한다.
     · 어떤 조항에 붙어 있는 것은, 그 개념이 **다른 조항**에 규정돼 있을
       때만 제거한다(엉뚱한 조항을 보고 없다고 한 경우). 같은 조항 안의
       보완 지적은 건드리지 않는다.

별도 문서를 대상으로 하는 항목(재하도급 계약서 등)은 애초에 이 계약의
부재를 말하는 것이 아니므로 검증 대상이 아니다.

제거·기록 후 전달
───────────────
근거 없는 부재 주장은 삭제하되 무엇을 왜 지웠는지 meta 에 남긴다. 다운로드는
막지 않는다 — 결함은 이미 제거됐고 담당자에게 결과는 가야 한다
(2026-09-10 지시 2항).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

REVIEW_FAILED_SOURCE_CONTRADICTION = "REVIEW_FAILED_SOURCE_CONTRADICTION"

#: 이 계약이 아니라 **다른 문서**에 들어갈 항목의 표지. 원도급 계약을 검토하며
#: "재하도급 계약서에 반영할 사항" 을 적는 경우가 여기 해당한다(지시 11항).
_OTHER_DOCUMENT_MARKERS: tuple[str, ...] = ("재하도급 계약서", "별도 체결", "별도 계약")

#: finding 이 "없다" 고 말하고 있는지 판별하는 표지.
_ABSENCE_MARKERS: tuple[str, ...] = (
    "해당 조항 없음",
    "계약에 없",
    "계약서에 없",
    "규정이 없",
    "조항이 없",
    "절차가 없",
    "기준이 없",
    "근거가 없",
    "정함이 없",
    "명시되어 있지 않",
    "규정되어 있지 않",
    "규정되지 않",
    "정하지 않",
    "정해져 있지 않",
    "마련되어 있지 않",
    "반영되어 있지 않",
    "반영되지 않",
    "대비가 없",
    "미규정",
    "신설 필요",
)

#: 부재 주장을 부정하는 문맥 — "없으면", "없는 경우" 처럼 조건절이면 주장이
#: 아니다.
_ABSENCE_FALSE_FRIENDS: tuple[str, ...] = ("없으면", "없는 경우", "없을 때", "없다면")

#: 조항에 붙어 있지 않다는 표지(신설 권고 / 위치 미상).
_UNANCHORED_MARKERS: tuple[str, ...] = (
    "해당 조항 없음", "신설", "조항 위치 확인 필요",
)


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════════
# A. 보호장치 대조표 — 지시 7항이 열거한 6가지 (hard fail)
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProtectiveDeviceCheck:
    key: str
    label: str
    #: finding 이 "이 보호장치가 없다" 고 말하고 있는지.
    claim_rx: re.Pattern[str]
    #: 계약 문언에 그 보호장치가 실재하는지.
    presence_rx: re.Pattern[str]


PROTECTIVE_DEVICES: tuple[ProtectiveDeviceCheck, ...] = (
    ProtectiveDeviceCheck(
        key="delay_penalty_cap",
        label="지체상금 상한(cap)",
        claim_rx=_rx(
            r"지체\s*상금[^.\n]{0,60}(?:상한|한도|cap|캡)[^.\n]{0,30}"
            r"(?:없|부재|미설정|정해져 있지 않|규정되어 있지 않)"
            r"|(?:상한|한도|cap|캡)[^.\n]{0,30}(?:없|부재)[^.\n]{0,40}지체\s*상금"
        ),
        presence_rx=_rx(
            r"지체\s*상금[^.\n]{0,160}(?:총액|상한|한도)[^.\n]{0,80}"
            r"(?:초과하지|넘지|\d+\s*%|100\s*분의\s*\d+)"
            r"|(?:지체\s*상금)[^.\n]{0,60}총액[^.\n]{0,80}초과하지"
        ),
    ),
    ProtectiveDeviceCheck(
        key="fault_exclusion",
        label="귀책 제외사유",
        claim_rx=_rx(
            r"(?:제외\s*사유|면책\s*사유|귀책[^.\n]{0,20}제외)[^.\n]{0,40}"
            r"(?:없|부재|규정되어 있지 않|정해져 있지 않)"
            r"|(?:수급인|우리)[^.\n]{0,20}귀책[^.\n]{0,20}아닌[^.\n]{0,40}"
            r"(?:제외되지 않|부과)"
        ),
        presence_rx=_rx(
            r"(?:다음 각 호|아래)[^.\n]{0,60}"
            r"(?:지체\s*일수|지체\s*상금|하자)[^.\n]{0,60}(?:제외|산입하지)"
            r"|(?:지체\s*일수|지체\s*상금)[^.\n]{0,80}(?:산정에서\s*)?제외"
            r"|(?:하자)[^.\n]{0,60}책임을\s*지지\s*아니한다"
        ),
    ),
    ProtectiveDeviceCheck(
        key="subcontract",
        label="하도급·재하도급 규정",
        claim_rx=_rx(
            r"(?:재?하도급|하수급|제3자[^.\n]{0,10}위탁)[^.\n]{0,80}"
            r"(?:없|부재|규정되어 있지 않|정해져 있지 않|마련되어 있지 않)"
        ),
        presence_rx=_rx(
            r"하도급[^.\n]{0,120}(?:승인|동의|통지|금지|할 수 없)"
            r"|(?:제\s*\d+\s*조\s*)?\(\s*하도급\s*\)"
        ),
    ),
    ProtectiveDeviceCheck(
        key="guarantee",
        label="보증 규정",
        claim_rx=_rx(
            r"(?:이행\s*보증|하자\s*보수\s*보증|보증\s*(?:서|금|보험))[^.\n]{0,60}"
            r"(?:없|부재|확보되어 있지 않|규정되어 있지 않)"
            r"|보증[^.\n]{0,30}규정[^.\n]{0,20}(?:없|부재)"
        ),
        presence_rx=_rx(
            r"(?:계약\s*이행|하자\s*보수)\s*보증(?:보험)?(?:증권|서|금)"
            r"|보증(?:보험)?\s*증권[^.\n]{0,60}제출"
        ),
    ),
    ProtectiveDeviceCheck(
        key="acceptance",
        label="준공검사·검수 기준",
        claim_rx=_rx(
            r"(?:준공\s*검사|검수|인수\s*검사|검사)[^.\n]{0,60}"
            r"(?:기준|절차|규정)?[^.\n]{0,20}"
            r"(?:없|부재|규정되어 있지 않|정해져 있지 않|마련되어 있지 않)"
            r"|(?:인수|검수)\s*기준[^.\n]{0,20}(?:없|부재)"
        ),
        presence_rx=_rx(
            r"준공\s*검사[^.\n]{0,120}(?:합격|실시|통지|\d+\s*일)"
            r"|검사[^.\n]{0,60}(?:합격|보완\s*요구)[^.\n]{0,60}통지"
        ),
    ),
    ProtectiveDeviceCheck(
        key="first_contract_relation",
        label="1차 계약과 본계약의 관계",
        claim_rx=_rx(
            r"(?:\(?1\s*차\)?\s*계약|선행\s*계약|기본\s*계약)[^.\n]{0,60}"
            r"(?:관계|효력|정산)?[^.\n]{0,20}"
            r"(?:없|부재|규정되어 있지 않|정해져 있지 않|해당 조항 없음)"
        ),
        presence_rx=_rx(
            r"\(\s*1\s*차\s*\)\s*계약[^.\n]{0,160}(?:효력|유지|적용|체결|따라)"
            r"|1\s*차\s*계약[^.\n]{0,120}(?:2\s*차|본\s*계약)"
        ),
    ),
)


# ══════════════════════════════════════════════════════════════════════════
# B. 일반 개념 재검색 — 지시 6항의 동의어 목록
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConceptSpec:
    key: str
    label: str
    #: finding 이 이 개념을 다루고 있는지 알아보는 낱말들.
    claim_terms: tuple[str, ...]
    #: 계약 전문에서 이 개념이 실재하는지 찾는 동의어들(지시 6항 목록).
    document_terms: tuple[str, ...]


CONCEPTS: tuple[ConceptSpec, ...] = (
    ConceptSpec(
        key="subcontract", label="하도급·재하도급",
        claim_terms=("하도급", "재하도급", "하수급", "제3자 위탁"),
        document_terms=("하도급", "재하도급", "하수급", "제3자 위탁"),
    ),
    ConceptSpec(
        key="delay_penalty", label="지체상금·지연배상",
        claim_terms=("지체상금", "지연배상", "지연손해금", "지체일수"),
        document_terms=("지체상금", "지연배상", "지연손해금", "지체일수"),
    ),
    ConceptSpec(
        key="payment_withholding", label="지급유보·지급보류",
        claim_terms=("지급유보", "지급 유보", "지급보류", "유보금"),
        document_terms=("지급을 유보", "지급 유보", "지급유보", "지급보류", "유보 금액"),
    ),
    ConceptSpec(
        key="lien_waiver", label="유치권 포기·불행사",
        claim_terms=("유치권", "포기각서", "불행사"),
        document_terms=("유치권", "포기각서", "불행사"),
    ),
    ConceptSpec(
        key="guarantee", label="보증·보험증권",
        claim_terms=("이행보증", "하자보수보증", "보증서", "보증보험", "보험증권"),
        document_terms=("보증보험", "보험증권", "이행보증", "하자보수보증", "보증서"),
    ),
    ConceptSpec(
        key="acceptance", label="준공·검수·검사·인수인계",
        claim_terms=("준공검사", "검수", "인수인계", "인수 기준", "검사 기준"),
        document_terms=("준공검사", "검수", "인수인계", "준공"),
    ),
    ConceptSpec(
        key="change_order", label="설계변경·Change Order",
        claim_terms=(
            "설계변경", "추가공사", "change order", "변경계약", "계약금액의 조정",
            "업무의 변경", "추가 업무", "범위 변경", "변경·추가",
        ),
        document_terms=("설계변경", "추가공사", "change order", "변경계약서", "계약금액을 조정"),
    ),
    ConceptSpec(
        key="setoff", label="상계·공제",
        claim_terms=("상계", "공제"),
        document_terms=("상계", "공제할 수 있", "직접 공제"),
    ),
    ConceptSpec(
        key="time_extension", label="공기연장",
        claim_terms=("공기연장", "공사기간의 연장", "공기 연장", "기간 연장", "공기만회"),
        document_terms=("공사기간의 연장", "공기연장", "연장을 신청", "연장 일수"),
    ),
    ConceptSpec(
        key="first_contract_relation", label="1차 계약과의 관계",
        claim_terms=("1차 계약", "(1차)", "2차 계약", "선행 계약"),
        document_terms=("(1차) 계약", "1차) 계약", "2차 계약"),
    ),
)


def _finding_text(cr: dict[str, Any]) -> str:
    parts = [
        cr.get("issue_title"),
        cr.get("clause_title"),
        # 지적 본문까지 본다 — issue_title 이 비어 있고 problem 에만 부재
        # 주장이 적힌 항목이 있다(실측: effect_baseline 경로).
        cr.get("problem"),
        cr.get("legal_business_reason"),
        cr.get("legal_risk"),
        cr.get("our_company_risk"),
        cr.get("rewrite_reason"),
        cr.get("suggested_direction"),
    ]
    dil = cr.get("detected_issue_list")
    if isinstance(dil, list):
        parts.extend(dil)
    return _norm(" ".join(str(p) for p in parts if p))


def targets_other_document(cr: dict[str, Any]) -> bool:
    """이 계약이 아니라 별도 문서에 들어갈 항목인가(지시 11항)."""
    if str(cr.get("target_contract") or "") not in ("", "this"):
        return True
    where = " ".join(
        str(cr.get(k) or "") for k in ("display_path", "clause_title", "clause_id")
    )
    return any(marker in where for marker in _OTHER_DOCUMENT_MARKERS)


def claims_absence(cr: dict[str, Any]) -> bool:
    """이 finding 이 '없다' 고 말하고 있는가."""
    text = _finding_text(cr)
    if not text:
        return False
    for friend in _ABSENCE_FALSE_FRIENDS:
        text = text.replace(friend, " ")
    return any(marker in text for marker in _ABSENCE_MARKERS)


def is_unanchored(cr: dict[str, Any]) -> bool:
    """어느 실재 조항에도 붙어 있지 않은가(= 신설 권고)."""
    if bool(cr.get("is_new_clause")) or bool(cr.get("clause_reference_unresolved")):
        return True
    path = str(cr.get("display_path") or "")
    if any(marker in path for marker in _UNANCHORED_MARKERS):
        return True
    return not str(cr.get("article_number") or "").strip() and not re.search(
        r"제\s*\d+\s*조", path
    )


def anchored_article_number(cr: dict[str, Any]) -> str:
    art = str(cr.get("article_number") or "").strip()
    if art:
        return art
    m = re.search(r"제\s*(\d+)\s*조", str(cr.get("display_path") or ""))
    return m.group(1) if m else ""


def _best_concept(text: str) -> ConceptSpec | None:
    best: ConceptSpec | None = None
    best_hits = 0
    low = (text or "").lower()
    for spec in CONCEPTS:
        hits = sum(1 for term in spec.claim_terms if term.lower() in low)
        if hits > best_hits:
            best, best_hits = spec, hits
    return best


def concept_of(cr: dict[str, Any]) -> ConceptSpec | None:
    """finding 이 다루는 개념.

    **제목이 먼저다.** 본문에는 배경 설명으로 다른 개념이 여러 번 나온다 —
    실측: "공기연장과 추가비를 받을 수 없음"(CWC-02) 의 본문이 지체상금을
    여러 번 언급해, 낱말 수로만 세면 개념이 '지체상금' 으로 뒤집혔다. 그
    계약에는 지체상금 조항이 실재하므로, 실제로는 공기연장 조항이 없는데도
    "근거 없는 부재 주장" 으로 지워졌다.
    """
    title = " ".join(
        str(cr.get(k) or "") for k in ("issue_title", "clause_title")
    )
    return _best_concept(title) or _best_concept(_finding_text(cr))


#: 정의 조항은 개념을 **규정**하지 않는다 — 이름을 붙일 뿐이다. 실측: 제2조
#: (용어의 정의)가 "변경(Change Order)" 를 정의한다는 이유로, 제2조에 잘못
#: 붙은 "변경 절차가 규정되지 않았다" 지적이 "같은 조항 안의 보완 지적" 으로
#: 분류되어 살아남았다. 실제 변경 절차는 제13조에 있다.
_RX_DEFINITIONS_TITLE = re.compile(r"용어(?:의)?\s*정의|^\s*정의\s*$|Definitions", re.IGNORECASE)


def _articles_containing(spec: ConceptSpec, clauses: list[Any] | None) -> set[str]:
    """이 개념을 규정한 조 번호들. 정의 조항은 세지 않는다."""
    found: set[str] = set()
    for c in clauses or []:
        article = str(getattr(c, "article_number", "") or "")
        if not article:
            continue
        title = str(getattr(c, "title", "") or "")
        if _RX_DEFINITIONS_TITLE.search(title):
            continue
        body = f"{title}\n{getattr(c, 'text', '') or ''}".lower()
        if any(term.lower() in body for term in spec.document_terms):
            found.add(article)
    return found


def concept_present(spec: ConceptSpec, contract_text: str) -> tuple[bool, str]:
    """계약 전문에 이 개념이 실재하는가. (존재여부, 근거 발췌)."""
    body = str(contract_text or "")
    if not body:
        return False, ""
    low = body.lower()
    for term in spec.document_terms:
        idx = low.find(term.lower())
        if idx >= 0:
            start = max(0, idx - 40)
            return True, _norm(body[start : idx + 120])
    return False, ""


@dataclass
class AbsenceVerificationReport:
    removed: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    checked: int = 0

    @property
    def status(self) -> str:
        return REVIEW_FAILED_SOURCE_CONTRADICTION if self.contradictions else ""

    @property
    def detail(self) -> str:
        if not self.contradictions:
            return ""
        names = ", ".join(
            f"{c['concept_label']}({c['display_path'] or c['clause_id']})"
            for c in self.contradictions[:3]
        )
        return (
            f"계약에 실재하는 보호조항을 '없음' 으로 판단한 항목 "
            f"{len(self.contradictions)}건을 제거했습니다 — {names}."
        )


def verify_absence_claims(
    clause_results: list[dict[str, Any]],
    *,
    contract_text: str,
    clauses: list[Any] | None = None,
) -> AbsenceVerificationReport:
    """부재를 주장하는 finding 을 계약 전문과 대조해 근거 없는 것을 제거한다.

    제자리에서 리스트를 수정하고 보고서를 돌려준다.
    """
    report = AbsenceVerificationReport()
    if not isinstance(clause_results, list) or not clause_results:
        return report

    body = str(contract_text or "")
    keep: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or targets_other_document(cr):
            keep.append(cr)
            continue
        if not claims_absence(cr):
            keep.append(cr)
            continue
        report.checked += 1
        text = _finding_text(cr)

        # A. 보호장치 대조표 — 실재하는데 없다고 하면 전체 검토 실패.
        device = next(
            (
                d
                for d in PROTECTIVE_DEVICES
                if d.claim_rx.search(text) and d.presence_rx.search(body)
            ),
            None,
        )
        if device is not None:
            m = device.presence_rx.search(body)
            record = {
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "issue_title": str(cr.get("issue_title") or cr.get("clause_title") or ""),
                "concept": device.key,
                "concept_label": device.label,
                "evidence": _norm(m.group(0))[:200] if m else "",
                "rule": "protective_device",
                "reason": (
                    f"'{device.label}' 가 계약에 실재하는데 부재로 판단한 항목이라 "
                    f"제거했습니다."
                ),
            }
            report.removed.append(record)
            report.contradictions.append(record)
            continue

        # B. 일반 규칙 — 개념이 계약 어딘가에 있으면 부재 주장은 성립하지 않는다.
        spec = concept_of(cr)
        if spec is None:
            keep.append(cr)
            continue
        present, excerpt = concept_present(spec, body)
        if not present:
            keep.append(cr)
            continue
        anchored = anchored_article_number(cr)
        if anchored and not is_unanchored(cr):
            # 어떤 조항에 붙어 있는 항목은, 그 개념이 **다른 조항**에 규정돼
            # 있을 때만 잘못된 부재 주장이다. 같은 조항 안에서 한 요소가
            # 빠졌다는 지적(예: 보증금 반환 시점)은 정당하다.
            where = _articles_containing(spec, clauses)
            if not where or anchored in where:
                keep.append(cr)
                continue
            excerpt = f"제{sorted(where, key=lambda x: int(x) if x.isdigit() else 0)[0]}조에 규정됨"
        record = {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "issue_title": str(cr.get("issue_title") or cr.get("clause_title") or ""),
            "concept": spec.key,
            "concept_label": spec.label,
            "evidence": excerpt,
            "rule": "concept_present",
            "reason": (
                f"'{spec.label}' 에 관한 규정이 계약에 실재하는데 부재로 판단한 "
                f"항목이라 제거했습니다."
            ),
        }
        report.removed.append(record)

    if report.removed:
        removed_ids = {id(r) for r in clause_results} - {id(k) for k in keep}
        if removed_ids:
            clause_results[:] = keep
    return report
