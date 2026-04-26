from __future__ import annotations

import re
from dataclasses import dataclass

from runtime.review.infer import merge_inference

@dataclass
class ClassificationResult:
    entity: str
    contract_type: str
    entity_source: str
    contract_type_source: str
    is_inferred: bool


ENTITY_RULES = [
    ("퍼시스홀딩스", [r"퍼시스홀딩스", r"fursys holdings"]),
    ("퍼시스", [r"(주\.)?\s*퍼시스", r"\bfursys\b"]),
    ("시디즈", [r"시디즈", r"\bsidiz\b"]),
    ("일룸/데스커", [r"일룸", r"데스커", r"\biloom\b", r"\bdesker\b"]),
    ("바로스", [r"바로스", r"\bbaros\b"]),
    ("해외법인", [r"\bLLC\b", r"\bInc\.\b", r"\bVietnam\b", r"\bTaiwan\b", r"\bSingapore\b", r"아메리카"]),
]

CONTRACT_TYPE_RULES = [
    ("NDA/비밀유지", [r"\bNDA\b", r"Non[- ]Disclosure", r"비밀유지", r"confidentiality"]),
    ("개인정보/처리위탁(DPA)", [r"개인정보", r"처리위탁", r"privacy", r"data processing", r"\bDPA\b"]),
    ("임대차/전대차", [r"임대차", r"전대차", r"\blease\b", r"\bsublease\b"]),
    (
        "장비공급/설치/시운전",
        [
            r"장비\s*(공급|구매|납품)",
            r"설치",
            r"시운전",
            r"검수",
            r"\bequipment\b",
            r"\binstallation\b",
            r"\bcommissioning\b",
        ],
    ),
    ("물품공급/구매/매매", [r"물품공급", r"구매", r"매매", r"\bsupply\b", r"\bpurchase\b", r"\bsales contract\b"]),
    ("대리점/위탁/유통", [r"대리점", r"위탁", r"위탁거래", r"\bdealer\b", r"\bdistributor\b", r"\bconsignment\b"]),
    ("용역/자문/SOW", [r"용역", r"자문", r"컨설팅", r"\bSOW\b", r"Statement of Work", r"\bengagement\b", r"\bservice agreement\b"]),
    ("광고/마케팅/협찬", [r"광고", r"마케팅", r"대행", r"협찬", r"sponsorship", r"advertising", r"marketing"]),
    ("라이선스/로열티", [r"라이선스", r"\blicense\b", r"로열티", r"\broyalt"]),
    ("공사/도급/하도급", [r"공사", r"시공", r"도급", r"하도급", r"\bconstruction\b", r"\bsubcontract"]),
    ("근로/고용", [r"근로계약", r"고용", r"\bemployment\b", r"\blabor\b"]),
    ("합의/정산/해지", [r"합의서", r"정산", r"해지", r"종료 합의", r"\bsettlement\b", r"\btermination\b"]),
    ("공문/의견/확인", [r"공문", r"의견", r"검토의견", r"확인서", r"notice", r"letter"]),
]


def classify(
    entity: str | None,
    contract_type: str | None,
    text: str,
    filename: str | None,
    file_path: str | None = None,
) -> ClassificationResult:
    text_entity = _classify_entity(text, filename)
    text_contract_type = _classify_contract_type(text, filename)
    inferred = merge_inference(
        user_entity=entity,
        user_contract_type=contract_type,
        text_entity=text_entity,
        text_contract_type=text_contract_type,
        filename=filename,
        file_path=file_path,
    )
    return ClassificationResult(
        inferred.entity,
        inferred.contract_type,
        inferred.entity_source,
        inferred.contract_type_source,
        inferred.is_inferred,
    )


def _classify_entity(text: str, filename: str | None) -> str:
    s = (text or "") + "\n" + (filename or "")
    for name, pats in ENTITY_RULES:
        for p in pats:
            if re.search(p, s, re.IGNORECASE):
                return name
    return "미상"


def _classify_contract_type(text: str, filename: str | None) -> str:
    s = (text or "") + "\n" + (filename or "")
    for name, pats in CONTRACT_TYPE_RULES:
        for p in pats:
            if re.search(p, s, re.IGNORECASE):
                return name
    return "기타/미분류"

