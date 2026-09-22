"""영문 계약 조항 추출·연결 골든 회귀 (2026-09-21 5차 지시).

지시 14항이 요구한 골든 매핑을 그대로 옮긴다.

    Request 1 → Article 5.3 + 7.1~7.3      Request 5 → Article 12 + 13
    Request 2 → Article 5.3 + 7.1          Request 6 → Article 14
    Request 3 → Article 7.4 + 9.2~9.3      Request 7 → Article 15
    Request 4 → Article 5.5 + 9.4          Request 8 → Article 16.4~16.5

    "하나라도 '해당 조항 없음'이면 테스트 실패."

무엇이 깨졌었나
────────────
영문 파서는 줄머리의 `N.` 을 전부 Article 로 올렸다. 그래서 Article 5 의
제3항("3. The Receiving Party may disclose …")이 **Article 3** 이 되고,
Article 5.3 은 색인에 아예 없었다. 색인에 없으니 담당자 질문 1·2 는
"해당 조항 없음" 으로 나갔다 — 계약서에는 버젓이 있는 조항인데도.

픽스처는 실제 검토 대상(중국 액추에이터 업체와의 상호 NDA)과 같은 구조를
가지되 당사자·제품명을 바꾼 익명본이다. 16개 조, 조마다 항이 있고 항이 줄
폭에서 끊겨 있다 — 원문에서 오판을 일으킨 조건을 그대로 남겼다.
"""
from __future__ import annotations

import pathlib

import pytest

from runtime.review.clause_extraction import extract_clauses
from runtime.review.english_clause_grounding import (
    REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING,
    STATUS_ABSENT,
    STATUS_PRESENT,
    check_english_clause_grounding,
)
from runtime.review.user_request_answers import (
    REQUEST_TOPICS,
    _find_clauses,
    answer_requests,
    parse_numbered_requests,
)

FIXTURE = (
    pathlib.Path(__file__).parent / "fixtures" / "mutual_nda_en_16_articles.txt"
)

#: 지시 14항의 매핑. 값은 **반드시 나와야 하는** 조항이다(추가 조항은 허용).
GOLDEN: dict[str, tuple[str, ...]] = {
    "third_party_sharing": ("Article 5.3", "Article 7.1", "Article 7.3"),
    "core_tech_approval": ("Article 5.3", "Article 7.1"),
    "ip_ownership_split": ("Article 7.4", "Article 9.2", "Article 9.3"),
    "independent_development": ("Article 5.5", "Article 9.4"),
    "term_and_damages": ("Article 12.2", "Article 13.2"),
    "personal_data": ("Article 14.1",),
    "governing_law_arbitration": ("Article 15.1", "Article 15.2"),
    "prevailing_language": ("Article 16.4", "Article 16.5"),
}

REVIEW_FOCUS = """아래 사항을 검토해 주세요.
1. 국내 개발사·시험기관 등 제3자와 상대방 기술자료를 공유해도 되는지 확인 부탁드립니다.
2. 상대방 핵심기술을 쓰려면 사전 승인이 필요한 구조인지 확인 부탁드립니다.
3. 우리가 기존부터 보유한 기술과 이번에 나올 개발성과의 권리 구분이 되어 있는지요.
4. 우리가 다른 업체와 독자 개발을 하는 것이 제한되지 않는지 확인 부탁드립니다.
5. 비밀유지 기간과 손해배상 범위가 우리에게 과도하지 않은지 봐주세요.
6. 수면 데이터 등 개인정보 처리 경계가 정리되어 있는지 확인 부탁드립니다.
7. 준거법과 중재 조항의 집행 가능성을 알려주세요.
8. 국문·영문·중문 중 어느 본이 우선하는지 확인 부탁드립니다.
"""


@pytest.fixture(scope="module")
def clauses():
    text = FIXTURE.read_text(encoding="utf-8")
    chunks, _report = extract_clauses(text)
    return chunks


@pytest.fixture(scope="module")
def contract_text():
    return FIXTURE.read_text(encoding="utf-8")


def _paths(clauses) -> list[str]:
    return [c.display_path for c in clauses]


# ── 파서 ────────────────────────────────────────────────────────────────


def test_every_article_and_subsection_is_indexed(clauses):
    paths = _paths(clauses)
    # 조는 1~16, 항은 조마다 실제 있는 만큼.
    for article in range(2, 17):
        assert any(
            p.startswith(f"Article {article}.") for p in paths
        ), f"Article {article} 의 항이 하나도 색인되지 않았다"


def test_subsection_is_not_promoted_to_article(clauses):
    """Article 5 의 제3항이 'Article 3' 이 되면 안 된다."""
    by_path = {c.display_path: c for c in clauses}
    assert "Article 5.3" in by_path
    # 항만 있는 문서이므로 조 단독 항목(Article 3)은 만들어지지 않는다.
    assert "Article 3" not in by_path
    assert "need-to-know" in by_path["Article 5.3"].text


def test_subsection_text_joins_wrapped_lines(clauses):
    """줄 폭에서 끊긴 한 항은 하나의 조각으로 이어져야 한다."""
    by_path = {c.display_path: c for c in clauses}
    body = " ".join(by_path["Article 5.3"].text.split())
    assert body.startswith("The Receiving Party may disclose")
    assert body.rstrip().endswith("disclosure.")
    assert "prior written consent" in body


def test_article_numbers_are_ascending_and_unique(clauses):
    pairs = [
        (c.article_number, c.paragraph_number)
        for c in clauses
        if c.article_number
    ]
    assert len(pairs) == len(set(pairs)), "같은 조·항이 두 번 나왔다"
    roots = [int(a) for a, _ in pairs]
    assert roots == sorted(roots)
    assert max(roots) == 16


def test_clause_index_sees_sixteen_articles_not_fake_ones(clauses, contract_text):
    """조 번호에 항을 붙여 넣으면 제53조 같은 없는 조가 생긴다."""
    from runtime.review.clause_index import build_clause_index

    index = build_clause_index(contract_text, clauses)
    assert sorted(int(n) for n in index.articles) == list(range(1, 17))
    assert index.uncertainty_reasons == []
    assert not index.structure_uncertain
    assert index.has_paragraph(5, 3)
    assert index.has_paragraph(16, 5)
    assert not index.has_article(53)


# ── 골든 매핑 (지시 14항) ────────────────────────────────────────────────


@pytest.mark.parametrize("topic_key,required", sorted(GOLDEN.items()))
def test_golden_request_to_clause_mapping(clauses, topic_key, required):
    topic = next(t for t in REQUEST_TOPICS if t.key == topic_key)
    found = _find_clauses(topic, clauses)
    assert found, f"{topic_key}: 해당 조항 없음 — 골든 매핑 실패"
    missing = [r for r in required if r not in found]
    assert not missing, f"{topic_key}: {missing} 를 찾지 못했다 (찾은 것: {found})"


def test_no_request_is_answered_as_clause_absent(clauses):
    requests = parse_numbered_requests(REVIEW_FOCUS)
    assert len(requests) == 8

    answers = answer_requests(
        review_focus=REVIEW_FOCUS,
        clauses=clauses,
        clause_results=[],
        contract_type_code="nda_confidentiality",
    )
    assert len(answers) == 8
    for a in answers:
        assert a.clauses, f"요청 {a.index}: 연결된 조항이 없다 — {a.question[:40]}"
        assert "해당 조항 없음" not in a.reason


def test_language_question_is_answered_from_both_language_clauses(clauses):
    answers = answer_requests(
        review_focus=REVIEW_FOCUS,
        clauses=clauses,
        clause_results=[],
        contract_type_code="nda_confidentiality",
    )
    last = answers[-1]
    assert last.index == 8
    assert "Article 16.4" in last.clauses
    assert "Article 16.5" in last.clauses


# ── 영문 grounding 게이트 (지시 9·10·11·18항) ───────────────────────────


def test_grounding_recognises_existing_protections(clauses, contract_text):
    report = check_english_clause_grounding(clauses, [], contract_text=contract_text)
    assert report.applied
    by_key = {p["key"]: p for p in report.protections}
    for key in (
        "mutual_nda",
        "third_party_disclosure",
        "background_ip",
        "foreground_ip",
        "independent_development",
        "return_destruction",
        "confidentiality_term",
        "data_processing_boundary",
        "governing_law",
        "arbitration",
        "language_precedence",
    ):
        assert by_key[key]["status"] == STATUS_PRESENT, f"{key} 를 없다고 보았다"
        # 지시 11항 — 근거 조항 없이 존재한다고 말하지 않는다.
        assert by_key[key]["supporting_clause_ids"]


def test_grounding_reports_absent_protection_without_evidence(clauses, contract_text):
    """계약에 없는 것은 없다고 한다 — 있는 척하지 않는다."""
    report = check_english_clause_grounding(clauses, [], contract_text=contract_text)
    by_key = {p["key"]: p for p in report.protections}
    ai = by_key["ai_training_restriction"]
    # 픽스처 6.6 은 업로드 금지일 뿐 학습 목적 사용 동의를 정하지 않는다.
    assert ai["status"] == STATUS_ABSENT
    assert ai["supporting_clause_ids"] == []


def test_grounding_flags_false_absence_claim(clauses, contract_text):
    clause_results = [
        {
            "clause_id": "fnd_1",
            "issue_title": "제3자 제공 조항 없음",
            "problem": "제3자에 대한 제공 범위가 규정되어 있지 않습니다.",
        },
        {
            "clause_id": "fnd_2",
            "issue_title": "준거법 미기재",
            "problem": "준거법이 없어 분쟁 시 기준이 불명확합니다.",
        },
    ]
    report = check_english_clause_grounding(
        clauses, clause_results, contract_text=contract_text
    )
    assert report.status == REVIEW_FAILED_ENGLISH_CLAUSE_GROUNDING
    keys = {v["key"] for v in report.violations}
    assert {"third_party_disclosure", "governing_law"} <= keys
    # 지적을 지우지 않고, 어디에 있는지를 붙여 둔다.
    assert clause_results[0]["english_grounding_contradiction"]["supporting_clause_ids"]
    assert "Article 15.1" in (
        clause_results[1]["english_grounding_contradiction"]["supporting_clause_ids"]
    )
    assert "Article" in report.detail


def test_grounding_leaves_sound_findings_alone(clauses, contract_text):
    clause_results = [
        {
            "clause_id": "fnd_3",
            "issue_title": "손해배상 상한 부재",
            "problem": "배상액의 총액 상한이 정해져 있지 않습니다.",
        },
    ]
    report = check_english_clause_grounding(
        clauses, clause_results, contract_text=contract_text
    )
    assert report.violations == []
    assert report.status == ""
    assert "english_grounding_contradiction" not in clause_results[0]


def test_grounding_skips_korean_contracts():
    text = (
        pathlib.Path(__file__).parent / "fixtures" / "nda_basic.txt"
    ).read_text(encoding="utf-8")
    chunks, _ = extract_clauses(text)
    report = check_english_clause_grounding(chunks, [], contract_text=text)
    assert not report.applied
    assert report.status == ""
