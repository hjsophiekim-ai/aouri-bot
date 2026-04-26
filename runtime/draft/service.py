from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from runtime.review.text_extract import extract_text_from_file
from runtime.services.query_service import RuleQueryService


ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATES_DIR = ROOT_DIR / "docs" / "Standard Contract"


@dataclass(frozen=True)
class TemplateInfo:
    template_id: str
    filename: str
    path: str
    supported: bool


def list_standard_templates() -> list[TemplateInfo]:
    out: list[TemplateInfo] = []
    if not TEMPLATES_DIR.exists():
        return out
    for p in sorted(TEMPLATES_DIR.iterdir()):
        if not p.is_file():
            continue
        template_id = p.name
        supported = p.suffix.lower() in (".docx", ".txt")
        out.append(
            TemplateInfo(
                template_id=template_id,
                filename=p.name,
                path=str(p),
                supported=supported,
            )
        )
    return out


DEFAULT_TEMPLATE_HINTS: list[dict[str, object]] = [
    {
        "contract_type_keywords": ["NDA", "비밀", "비밀유지"],
        "template_ids": ["비밀유지서약서_당사가 정보를 제공한 경우.docx"],
    },
    {
        "contract_type_keywords": ["대리점", "유통", "위탁"],
        "template_ids": ["사내표준 재판매대리점 약정서.docx"],
    },
    {
        "contract_type_keywords": ["물품공급", "구매", "매매", "공급"],
        "template_ids": ["영문 물품공급 계약서.docx", "표준 건설자재공급계약서.docx"],
    },
    {
        "contract_type_keywords": ["용역", "자문", "SOW", "디자인"],
        "template_ids": ["영문 디자인용역 계약서.docx"],
    },
    {
        "contract_type_keywords": ["개인정보", "DPA", "처리위탁", "privacy"],
        "template_ids": ["표준 개인정보처리위탁 계약서.docx"],
    },
    {
        "contract_type_keywords": ["광고", "마케팅", "협찬", "모델"],
        "template_ids": ["사내 표준 광고대행계약서.docx", "표준 모델 출연계약서.docx"],
    },
]


def suggest_template_ids(contract_type: str) -> list[str]:
    ct = contract_type or ""
    hits: list[str] = []
    for rule in DEFAULT_TEMPLATE_HINTS:
        kws = rule.get("contract_type_keywords")
        tids = rule.get("template_ids")
        if not isinstance(kws, list) or not isinstance(tids, list):
            continue
        if any(str(k) in ct for k in kws):
            for tid in tids:
                if isinstance(tid, str) and tid not in hits:
                    hits.append(tid)
    return hits


SUGGESTION_BY_RULE_ID = {
    "RISK-001": "무제한 책임 표현이 있으면 손해배상 상한(예: 계약금액/연간 총액)과 간접손해 제외를 제안한다.",
    "RISK-002": "일방 면책/일방 배상 구조면 상호주의(쌍방 면책/쌍방 배상) 또는 범위 제한을 제안한다.",
    "RISK-004": "기술자료 요구가 있으면 목적/범위/보관기간/반환·파기/제3자 제공 금지/보안 기준을 명시하도록 제안한다.",
    "RISK-005": "하도급 단가감액 위험이 있으면 단가 조정 요건·절차·근거자료·사전협의·서면합의 조건을 제안한다.",
    "RISK-006": "대리점 비용전가 위험이 있으면 비용 항목/정산 기준/상한/근거/사전 합의(서면) 조항을 제안한다.",
}


def generate_draft_text(
    service: RuleQueryService,
    template_id: str,
    entity: str,
    contract_type: str,
    party_a: str,
    party_b: str,
    purpose: str | None,
) -> dict[str, Any]:
    p = TEMPLATES_DIR / template_id
    if not p.exists():
        raise FileNotFoundError("template not found")

    extraction = extract_text_from_file(p)
    if not extraction.success:
        raise ValueError(f"template not supported for MVP: {extraction.error}")

    rules = service.list_rules(entity=entity, contract_type=contract_type, include_backlog=False)
    suggestions: list[str] = []
    for r in rules:
        rid = r.get("rule_id")
        if rid in SUGGESTION_BY_RULE_ID:
            suggestions.append(SUGGESTION_BY_RULE_ID[rid])

    header = [
        "### 계약서 초안(템플릿 기반, MVP)",
        f"- 템플릿: {p.name}",
        f"- 법인(entity): {entity}",
        f"- 계약유형(contract_type): {contract_type}",
        f"- 당사: {party_a}",
        f"- 상대방: {party_b}",
    ]
    if purpose:
        header.append(f"- 거래 목적: {purpose}")

    body = extraction.text
    draft_text = "\n".join(header) + "\n\n---\n\n" + body

    return {
        "template": {"template_id": template_id, "filename": p.name},
        "draft_text": draft_text,
        "suggestions": suggestions,
        "note": "MVP: LLM 없이 템플릿 텍스트 + 룰 기반 체크/제안만 제공한다. DOC(HWP/PDF) 템플릿은 제외.",
    }

