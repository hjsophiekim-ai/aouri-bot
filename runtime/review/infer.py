from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Inference:
    entity: str
    contract_type: str
    entity_source: str
    contract_type_source: str
    is_inferred: bool


CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "classification_cache.json"
VERIFIED_META_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "review_output"
    / "02_verified_meta.json"
)


ENTITY_KEYWORDS = [
    ("퍼시스홀딩스", ["퍼시스홀딩스", "fursys_holdings"]),
    ("퍼시스", ["퍼시스", "fursys"]),
    ("시디즈", ["시디즈", "sidiz"]),
    ("일룸", ["일룸", "iloom"]),
    ("데스커", ["데스커", "desker"]),
    ("바로스", ["바로스", "baros"]),
    ("해외법인", ["overseas", "global", "usa", "america", "vietnam", "taiwan", "singapore", "hk", "hongkong"]),
]


CONTRACT_TYPE_KEYWORDS = [
    ("NDA/비밀유지", ["nda", "비밀유지", "confidential"]),
    ("앱개발/소프트웨어개발/SI/유지보수/SaaS", ["앱 개발", "소프트웨어 개발", "시스템 개발", "개발용역", "it 용역", "si", "유지보수", "saas", "api 연동", "source code", "산출물", "sla"]),
    ("운영대행/위탁운영/공간운영/서비스위탁", ["운영대행", "위탁운영", "운영위탁", "공간운영", "매장운영", "라운지 운영", "시설운영", "시설관리", "관리용역", "운영용역", "서비스위탁"]),
    ("개인정보/처리위탁(DPA)", ["처리위탁", "dpa", "data processing", "personal data processing", "수탁자", "위탁자"]),
    ("임대차/전대차", ["임대차", "전대차", "lease", "rental"]),
    ("물품공급/구매/매매", ["공급", "구매", "매매", "purchase", "supply", "sales"]),
    ("대리점/위탁/유통", ["대리점", "유통", "위탁판매", "위탁거래", "dealer", "distributor", "consignment"]),
    ("용역/자문/SOW", ["용역", "자문", "sow", "service", "consulting"]),
    ("공사/도급/하도급", ["공사", "도급", "하도급", "construction", "subcontract"]),
    ("광고/마케팅/협찬", ["광고", "마케팅", "협찬", "ad", "marketing", "sponsor"]),
    ("라이선스/로열티", ["라이선스", "로열티", "license", "royalt"]),
    ("합의/정산/해지", ["합의", "정산", "해지", "settlement", "termination"]),
]


def infer_from_path(file_path: str | None) -> Inference | None:
    if not file_path:
        return None
    p = Path(file_path)
    hay = " / ".join([*p.parts, p.name]).lower()

    entity = None
    for ent, keys in ENTITY_KEYWORDS:
        if any(k.lower() in hay for k in keys):
            entity = ent
            break

    contract_type = None
    for ct, keys in CONTRACT_TYPE_KEYWORDS:
        if any(k.lower() in hay for k in keys):
            contract_type = ct
            break

    if not entity and not contract_type:
        return None

    return Inference(
        entity=entity or "미상",
        contract_type=contract_type or "기타/미분류",
        entity_source="inferred_path",
        contract_type_source="inferred_path",
        is_inferred=True,
    )


def _safe_load_json(path: Path) -> dict | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def infer_from_cache(filename: str | None, file_path: str | None) -> Inference | None:
    if not filename and not file_path:
        return None

    cache = _safe_load_json(CACHE_PATH) or {}
    key = filename or (Path(file_path).name if file_path else None)
    if key and key in cache and isinstance(cache[key], dict):
        it = cache[key]
        ent = str(it.get("entity", "미상"))
        ct = str(it.get("contract_type", "기타/미분류"))
        return Inference(
            entity=ent,
            contract_type=ct,
            entity_source="cache",
            contract_type_source="cache",
            is_inferred=True,
        )
    return None


def infer_from_verified_meta(filename: str | None) -> Inference | None:
    if not filename:
        return None
    meta = _safe_load_json(VERIFIED_META_PATH)
    if not meta or not isinstance(meta.get("items"), list):
        return None
    for it in meta["items"]:
        if not isinstance(it, dict):
            continue
        if str(it.get("filename", "")) == filename:
            ent = str(it.get("entity", "미상"))
            ct = str(it.get("contract_type", "기타/미분류"))
            return Inference(
                entity=ent,
                contract_type=ct,
                entity_source="verified_meta",
                contract_type_source="verified_meta",
                is_inferred=True,
            )
    return None


def merge_inference(
    user_entity: str | None,
    user_contract_type: str | None,
    text_entity: str,
    text_contract_type: str,
    filename: str | None,
    file_path: str | None,
) -> Inference:
    if user_entity or user_contract_type:
        return Inference(
            entity=user_entity or text_entity,
            contract_type=user_contract_type or text_contract_type,
            entity_source="user_input" if user_entity else "heuristic_text",
            contract_type_source="user_input" if user_contract_type else "heuristic_text",
            is_inferred=not (user_entity and user_contract_type),
        )

    inferred = (
        infer_from_cache(filename, file_path)
        or infer_from_verified_meta(filename)
        or infer_from_path(file_path or filename)
    )

    if inferred:
        ent = inferred.entity if inferred.entity != "미상" else text_entity
        ct = inferred.contract_type if inferred.contract_type != "기타/미분류" else text_contract_type
        return Inference(
            entity=ent,
            contract_type=ct,
            entity_source=inferred.entity_source if ent == inferred.entity else "heuristic_text",
            contract_type_source=inferred.contract_type_source if ct == inferred.contract_type else "heuristic_text",
            is_inferred=True,
        )

    return Inference(
        entity=text_entity,
        contract_type=text_contract_type,
        entity_source="heuristic_text",
        contract_type_source="heuristic_text",
        is_inferred=True,
    )


def update_cache(filename: str, entity: str, contract_type: str) -> None:
    if not filename:
        return
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = _safe_load_json(CACHE_PATH) or {}
    cache[filename] = {"entity": entity, "contract_type": contract_type}
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

