"""Tests for the hybrid AI + rule-engine legal review architecture.

Goal (per user spec, 2026-08-28): when a real AI provider (OpenAI or
Anthropic) is configured, AI performs the actual per-clause legal reasoning
(원문 의미 -> 당사자 권리·의무 -> 우리 회사 리스크 -> 법적/실무적 이유 -> 최소
수정안), including discovering risks the rule DB never flagged. The rule
engine (common_legal_risk / testing_service_rules / hallucination_guard /
self_check) stays on as a guardrail: it validates AI output, rejects
ungrounded or out-of-scope suggestions, and guarantees a floor severity for
its own findings. When no AI provider is configured, the rule engine runs
alone and the result must say so plainly (no "looks like it worked" banner).

There is no live API key in this environment, so these tests exercise the
wiring with a stub AIProvider rather than a real OpenAI/Anthropic call.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from runtime.ai.provider import AIResponse, AIUsage
from runtime.ai.factory import is_ai_enabled
from runtime.ai.config import AIConfig
from runtime.rules.loader import RuleLoader
from runtime.services.query_service import RuleQueryService
from runtime.review.clause_level import build_clause_level_result

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "fiti_testing_service_agreement.txt"


class _StubAIProvider:
    """A minimal AIProvider that inspects the request and returns a
    hand-crafted response exercising the hybrid merge/guardrail paths."""

    def __init__(self, respond) -> None:
        self._respond = respond
        self.calls: list[dict[str, Any]] = []

    def complete(self, req):
        user_payload = json.loads(req.messages[-1].content)
        self.calls.append(user_payload)
        items_out = self._respond(user_payload)
        return AIResponse(content=json.dumps(items_out, ensure_ascii=False), usage=AIUsage(10, 10, 20), raw=None)


def _run_pipeline(*, ai_provider=None, ai_model=None):
    text = FIXTURE_PATH.read_text(encoding="utf-8")
    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)
    return build_clause_level_result(
        service=service,
        entity="시디즈",
        contract_type="",
        text=text,
        filename="x.pdf",
        answers=None,
        law_service=None,
        ai_provider=ai_provider,
        ai_model=ai_model or ("stub-model" if ai_provider else None),
        ai_timeout_sec=30.0 if ai_provider else None,
        ai_max_tokens=2000 if ai_provider else None,
        ai_temperature=0.2 if ai_provider else None,
    )


class ProviderGatingTest(unittest.TestCase):
    def test_is_ai_enabled_requires_real_provider_and_key(self) -> None:
        self.assertFalse(is_ai_enabled(AIConfig(provider="mock", model="x", api_key=None, endpoint=None, timeout_sec=1, max_tokens=1, temperature=0.1)))
        self.assertFalse(is_ai_enabled(AIConfig(provider="openai", model="x", api_key=None, endpoint=None, timeout_sec=1, max_tokens=1, temperature=0.1)))
        self.assertTrue(is_ai_enabled(AIConfig(provider="openai", model="x", api_key="sk-x", endpoint=None, timeout_sec=1, max_tokens=1, temperature=0.1)))
        # Anthropic must be treated as a real provider too — this was the bug:
        # every prior call site special-cased "openai" and silently ignored a
        # configured Anthropic key.
        self.assertTrue(is_ai_enabled(AIConfig(provider="anthropic", model="x", api_key="sk-ant-x", endpoint=None, timeout_sec=1, max_tokens=1, temperature=0.1)))


class RuleBasedFallbackBannerTest(unittest.TestCase):
    def test_no_provider_shows_fallback_banner(self) -> None:
        bundle = _run_pipeline(ai_provider=None)
        ai_meta = bundle.meta.get("ai")
        self.assertFalse(ai_meta.get("enabled"))
        self.assertEqual(ai_meta.get("mode"), "rule_based_fallback")
        self.assertIn("비활성화", ai_meta.get("banner", ""))
        # The rule engine must still have produced real findings (Layer 1/2).
        tier_counts = bundle.meta.get("tier_counts") or {}
        self.assertGreater(tier_counts.get("must", 0) + tier_counts.get("medium", 0), 0)


class HybridDiscoveryTest(unittest.TestCase):
    """AI escalates a clause the rule engine never flagged (is_exploration_only)."""

    def test_ai_discovers_new_risk_with_grounded_quote(self) -> None:
        def respond(payload: dict[str, Any]):
            out = []
            for item in payload["items"]:
                # Skip 제1-3조 (declarative/meta articles) — those are always
                # hard-blocked to LOW by design regardless of AI's severity
                # call, so they are not a useful target for this assertion.
                cid = str(item.get("clause_id") or "")
                if cid in ("KR-1", "KR-2", "KR-3") or cid.startswith("KR-1-") or cid.startswith("KR-2-") or cid.startswith("KR-3-"):
                    continue
                if item.get("is_exploration_only"):
                    ot = str(item["original_text"])
                    out.append({
                        "clause_id": item["clause_id"],
                        "original_text_quote": ot[:20],
                        "party_obligations": "당사자 의무 요약",
                        "our_company_risk": "우리 회사가 불리해지는 지점",
                        "rewrite_reason": "AI가 발견한 신규 리스크: " + ot[:15],
                        "suggested_rewrite": "수정 제안 문구",
                        "risk_tier": "HIGH",
                        "must_fix": True,
                    })
                    break  # escalate exactly one exploration-only clause
            return out

        stub = _StubAIProvider(respond)
        bundle = _run_pipeline(ai_provider=stub)
        ai_meta = bundle.meta.get("ai")
        self.assertEqual(ai_meta.get("mode"), "ai_legal_review")
        self.assertGreaterEqual(ai_meta.get("ai_discovered_count", 0), 1)
        discovered = [cr for cr in bundle.clause_results if isinstance(cr, dict) and cr.get("is_ai_discovered")]
        self.assertTrue(discovered, "expected at least one AI-discovered finding")
        for cr in discovered:
            # Not strictly HIGH: the pre-existing review-priority engine caps
            # total HIGH findings and may rank one of several HIGH claims
            # down to MEDIUM — that cap is a separate, legitimate feature.
            # What matters here is the finding was surfaced, not left at LOW.
            self.assertIn(cr["risk_tier"], ("HIGH", "MEDIUM"))
            self.assertTrue(cr.get("ai_deep_reviewed"))

    def test_ungrounded_severity_claim_is_rejected(self) -> None:
        def respond(payload: dict[str, Any]):
            out = []
            for item in payload["items"]:
                if item.get("is_exploration_only"):
                    out.append({
                        "clause_id": item["clause_id"],
                        # Quote does NOT appear anywhere in the actual clause text.
                        "original_text_quote": "이것은 원문에 전혀 없는 완전히 지어낸 문구입니다",
                        "rewrite_reason": "근거 없는 주장",
                        "suggested_rewrite": "근거 없는 수정안",
                        "risk_tier": "HIGH",
                        "must_fix": True,
                    })
                    break
            return out

        stub = _StubAIProvider(respond)
        bundle = _run_pipeline(ai_provider=stub)
        discovered = [cr for cr in bundle.clause_results if isinstance(cr, dict) and cr.get("is_ai_discovered")]
        self.assertEqual(discovered, [], "ungrounded AI finding must not be added to the result")
        ai_meta = bundle.meta.get("ai")
        self.assertGreaterEqual(ai_meta.get("ai_grounding_rejected_count", 0), 1)


class FloorProtectionTest(unittest.TestCase):
    """Rule-engine (Layer 1/2/mandatory) findings are a floor AI cannot lower
    without it being visible — AI may escalate them but not silently drop
    them below what the rule engine already guaranteed."""

    def test_ai_cannot_silently_downgrade_layer1_high_finding(self) -> None:
        def respond(payload: dict[str, Any]):
            out = []
            for item in payload["items"]:
                if str(item["clause_id"]).startswith("clr_") and item.get("risk_tier") == "HIGH":
                    ot = str(item["original_text"])
                    out.append({
                        "clause_id": item["clause_id"],
                        "original_text_quote": ot[:20],
                        "rewrite_reason": "AI가 이 조항이 실제로는 문제없다고(잘못) 판단",
                        "suggested_rewrite": None,
                        "risk_tier": "LOW",
                        "must_fix": False,
                    })
            return out

        stub = _StubAIProvider(respond)
        bundle = _run_pipeline(ai_provider=stub)
        clr_high = [
            cr for cr in bundle.clause_results
            if isinstance(cr, dict) and str(cr.get("clause_id") or "").startswith("clr_") and cr.get("is_common_legal_risk")
        ]
        self.assertTrue(clr_high)
        for cr in clr_high:
            self.assertNotEqual(cr.get("risk_tier"), "LOW", f"{cr.get('clause_id')} was silently downgraded below its rule-engine floor")


class OutOfScopeAIContentStillBlockedTest(unittest.TestCase):
    """Even if AI is enabled and "succeeds", an out-of-scope suggestion for
    this contract type must still be stripped by the existing guardrails —
    the rule engine is a backstop regardless of AI confidence."""

    def test_ai_proposed_ci_si_phrase_is_stripped_for_testing_service(self) -> None:
        def respond(payload: dict[str, Any]):
            out = []
            for item in payload["items"]:
                if item.get("clause_id") == "clr_fault_blind_exemption":
                    ot = str(item["original_text"])
                    out.append({
                        "clause_id": item["clause_id"],
                        "original_text_quote": ot[:20],
                        "rewrite_reason": "면책 범위 조정 필요",
                        "suggested_rewrite": "수탁자가 CI/SI 가이드라인을 위반한 경우 위약벌을 갑에게 지급한다.",
                        "risk_tier": "HIGH",
                        "must_fix": True,
                    })
            return out

        stub = _StubAIProvider(respond)
        bundle = _run_pipeline(ai_provider=stub)
        blob = str(bundle.clause_results)
        self.assertNotIn("CI/SI 가이드라인", blob)
        self.assertNotIn("위약벌을 갑에게 지급", blob)


if __name__ == "__main__":
    unittest.main()
