"""Tests for wiring Layer 0 (Contract Legal Map) as the priority source of
truth over rule-based classifier/party_role for the provider/recipient
direction axis (변호사형 전체계약 판단 지시 후속, 2026-09-01 — 8건 hold-out
검증에서 라이선스 계약처럼 처음 보는 유형에 대해 rule classifier가 당사자
방향을 반대로("ordering_party"/buyer_favorable) 판정하는 문제가 발견된 후
요청됨).

license_1 fixture(실제 Fursys-Teknion License Agreement)는 이 문제가 실제로
발생한 사례 그대로다 — rule classifier는 이를 purchase_supply/ordering_party
(buyer_favorable)로 오분류하지만, 퍼시스는 실제로 Licensor/제조자(provider)
쪽이다. 실제 AI 호출 없이(비용 없이) 같은 결과를 재현하기 위해 stub
AIProvider로 Contract Legal Map의 our_role_direction/confidence 응답만
가짜로 주입한다.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from runtime.ai.provider import AIResponse, AIUsage
from runtime.review.clause_level import build_clause_level_result
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "_lm_license_1.txt"


class _StubAIProvider:
    """Contract Legal Map 호출({"contract_text": ...} payload)에만 지정된
    our_role_direction/confidence를 얹어 응답하고, 그 외 호출(조항별 리뷰,
    meta-extraction)은 전부 무해한 빈 응답으로 처리한다."""

    def __init__(self, *, our_role_direction: str | None, confidence: str | None) -> None:
        self._our_role_direction = our_role_direction
        self._confidence = confidence
        self.legal_map_calls: list[dict[str, Any]] = []

    def complete(self, req):
        payload = json.loads(req.messages[-1].content)
        if "contract_text" in payload:
            self.legal_map_calls.append(payload)
            resp = {
                "our_party": payload.get("entity"),
                "our_role_direction": self._our_role_direction,
                "our_role_direction_confidence": self._confidence,
            }
            return AIResponse(content=json.dumps(resp, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)
        if "items" in payload:
            return AIResponse(content="[]", usage=AIUsage(5, 5, 10), raw=None)
        return AIResponse(content="{}", usage=AIUsage(5, 5, 10), raw=None)


def _run(*, ai_provider) -> Any:
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)
    return build_clause_level_result(
        service=service,
        entity="퍼시스",
        contract_type="",
        text=text,
        filename="license_1.docx",
        answers=None,
        review_focus=None,
        law_service=None,
        ai_provider=ai_provider,
        ai_model="stub-model",
        ai_timeout_sec=30.0,
        ai_max_tokens=2000,
        ai_temperature=0.2,
    )


class LegalMapRoleOverrideTest(unittest.TestCase):
    def test_high_confidence_provider_direction_overrides_wrong_recipient_default(self) -> None:
        bundle = _run(ai_provider=_StubAIProvider(our_role_direction="provider", confidence="high"))
        audit = bundle.meta.get("legal_map_role_override")
        self.assertIsNotNone(audit, "rule classifier가 ordering_party(recipient)로 잘못 판정한 것을 override해야 한다")
        self.assertEqual(audit["previous_polarity"], "recipient")
        self.assertEqual(audit["overridden_our_role"], "supplier")
        self.assertEqual(audit["overridden_counterparty_role"], "buyer")

    def test_low_confidence_does_not_override(self) -> None:
        bundle = _run(ai_provider=_StubAIProvider(our_role_direction="provider", confidence="low"))
        self.assertIsNone(bundle.meta.get("legal_map_role_override"))

    def test_missing_direction_does_not_override(self) -> None:
        bundle = _run(ai_provider=_StubAIProvider(our_role_direction=None, confidence="high"))
        self.assertIsNone(bundle.meta.get("legal_map_role_override"))

    def test_no_ai_provider_never_overrides(self) -> None:
        bundle = _run(ai_provider=None)
        self.assertIsNone(bundle.meta.get("legal_map_role_override"))
        # AI 없이도 Layer 0는 축소판으로 항상 채워져야 한다.
        self.assertEqual(bundle.meta.get("contract_legal_map", {}).get("_legal_map_source"), "regex_fallback_no_ai")

    def test_agreeing_direction_does_not_override(self) -> None:
        # rule classifier가 이미 recipient로 판단했는데 AI도 recipient라고
        # 확인해주는 경우 — 덮어쓸 대상이 없으므로 audit는 None이어야 한다.
        bundle = _run(ai_provider=_StubAIProvider(our_role_direction="recipient", confidence="high"))
        self.assertIsNone(bundle.meta.get("legal_map_role_override"))


if __name__ == "__main__":
    unittest.main()
