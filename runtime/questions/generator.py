from __future__ import annotations

import re

from runtime.questions.model import Question, QuestionOption


YES_NO = [
    QuestionOption("yes", "예"),
    QuestionOption("no", "아니오"),
    QuestionOption("unknown", "미상"),
]


def _has_any(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def _extract_rule_ids(clause_results: list[dict] | None) -> set[str]:
    out: set[str] = set()
    for cr in clause_results or []:
        if not isinstance(cr, dict):
            continue
        rr = cr.get("related_rules")
        if isinstance(rr, list):
            for r in rr:
                if isinstance(r, dict) and isinstance(r.get("rule_id"), str):
                    out.add(str(r.get("rule_id")))
    return out


def _top_keywords(text: str, keywords: list[str], *, limit: int = 3) -> list[str]:
    out: list[str] = []
    t = text.lower()
    for k in keywords:
        if k.lower() in t and k not in out:
            out.append(k)
        if len(out) >= limit:
            break
    return out


def generate_questions(
    entity: str,
    contract_type: str,
    detected_rule_ids: list[str] | None,
    law_topics: list[str] | None = None,
    contract_text: str | None = None,
    clause_results: list[dict] | None = None,
    max_questions: int = 5,
) -> list[Question]:
    detected = set(detected_rule_ids or [])
    ctype = contract_type or ""
    ent = entity or ""
    topics = set([t.strip() for t in (law_topics or []) if isinstance(t, str) and t.strip()])
    text = contract_text or ""
    clause_rule_ids = _extract_rule_ids(clause_results)

    questions: list[Question] = []

    candidates: list[tuple[int, Question]] = []
    cap_present = _has_any(text, ["책임 상한", "책임상한", "limit of liability", "liability cap", "총 책임은", "총책임은"])
    privacy_present = _has_any(text, ["개인정보", "privacy", "dpa", "처리위탁", "수탁"])
    privacy_controls_present = _has_any(text, ["재위탁", "파기", "보관기간", "침해", "사고 통지", "보안조치"])
    dealer_present = _has_any(text, ["대리점", "유통", "위탁", "위탁판매", "위수탁"])
    dealer_cost_present = _has_any(text, ["판촉", "판매장려금", "광고비", "반품", "리베이트", "수수료", "비용 전가", "비용전가"])
    onsite_present = _has_any(text, ["설치", "시공", "현장", "작업", "공사", "물류센터"])
    safety_present = _has_any(text, ["산업안전", "중대재해", "안전관리", "보호구", "작업중지"])

    if max_questions < 1:
        max_questions = 1
    max_questions = min(int(max_questions), 8)

    if dealer_present and ("RISK-006" in detected or "RISK-006" in clause_rule_ids or dealer_cost_present):
        kws = _top_keywords(text, ["판촉비", "판매장려금", "광고비", "반품", "리베이트", "수수료", "위탁판매", "비용전가"], limit=3)
        suffix = f" (근거 키워드: {', '.join(kws)})" if kws else ""
        candidates.append(
            (
                95,
                Question(
                    question_id="Q-CA-001-dealer-cost",
                    title="대리점/위탁 거래에서 비용 부담(판촉비/광고비/반품 등) 항목·상한·정산 기준이 계약서에 명확히 적혀 있나요?",
                    description="비용 전가/판매장려금 조항은 분쟁 빈도가 높아, 항목별 상한·사전 서면합의·정산/증빙이 빠져 있으면 고위험이 된다." + suffix,
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:dealer", "priority:high", "reason_code:dealer_cost_terms"],
                    related_rule_ids=["RISK-006"],
                ),
            )
        )

    if ("RISK-001" in detected or "RISK-001" in clause_rule_ids) and not cap_present:
        kws = _top_keywords(text, ["무제한", "without limitation", "unlimited", "모든 손해", "간접손해"], limit=2)
        suffix = f" (문구 근거: {', '.join(kws)})" if kws else ""
        candidates.append(
            (
                90,
                Question(
                    question_id="Q-CA-002-liability-cap",
                    title="손해배상/책임 조항에 책임 상한(캡)과 간접손해 제외가 필요해 보입니다. 당사 기준 상한을 무엇으로 둘까요?",
                    description="무제한 책임 또는 간접손해 포함은 과도한 리스크로 이어질 수 있어, 상한 기준(계약금액/연간 총대금 등)과 예외(고의·중과실/강행법규)를 정해야 한다." + suffix,
                    answer_type="single_choice",
                    required=True,
                    options=[
                        QuestionOption("cap_contract_value", "계약금액(총 대금)"),
                        QuestionOption("cap_annual_value", "연간 총대금"),
                        QuestionOption("cap_other", "기타/협의 필요"),
                        QuestionOption("unknown", "미상"),
                    ],
                    tags=["topic:liability", "priority:high", "reason_code:missing_liability_cap"],
                    related_rule_ids=["RISK-001"],
                ),
            )
        )

    if ("RISK-002" in detected or "RISK-002" in clause_rule_ids) and _has_any(text, ["면책", "indemnif", "hold harmless"]):
        candidates.append(
            (
                85,
                Question(
                    question_id="Q-CA-003-indemnity-procedure",
                    title="면책/배상(특히 제3자 청구) 조항에 통지·방어권·승인 절차와 범위/한도를 명시할 필요가 있나요?",
                    description="제3자 청구 배상은 통지·방어권·합의/변제 승인 절차가 없으면 일방 부담으로 확대될 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:indemnity", "priority:high", "reason_code:indemnity_missing_procedure"],
                    related_rule_ids=["RISK-002"],
                ),
            )
        )

    if privacy_present and not privacy_controls_present:
        candidates.append(
            (
                80,
                Question(
                    question_id="Q-CA-004-privacy-delegation",
                    title="개인정보 처리/위탁 정황이 있는데, 재위탁·보안조치·보관/파기·침해사고 통지 기준이 계약서에 충분히 포함돼 있나요?",
                    description="개인정보 처리위탁이 있는 경우, 핵심 통제(재위탁/보안/파기/통지)가 빠져 있으면 보완이 필요하다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:privacy", "priority:high", "reason_code:privacy_controls_missing"],
                    related_rule_ids=[],
                ),
            )
        )

    if onsite_present and not safety_present:
        candidates.append(
            (
                75,
                Question(
                    question_id="Q-CA-005-onsite-safety",
                    title="설치/현장 작업 정황이 있는데, 안전관리 책임·교육·보호구·사고 통지·작업중지권 등이 계약서에 포함돼 있나요?",
                    description="현장 작업이 포함되면 안전 책임 공백이 발생하기 쉬워, 안전 관련 의무 배분과 절차를 명확히 해야 한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:safety", "priority:high", "reason_code:onsite_safety_missing"],
                    related_rule_ids=[],
                ),
            )
        )

    candidates.append(
        (
            10,
            Question(
                question_id="Q-CA-999-template-owner",
                title="상대방 양식인지, 당사 양식인지 확인",
                description="상대방 양식이면 면책/책임/관할 등 불리 조항이 포함될 가능성이 높아 검토 강도가 올라간다.",
                answer_type="single_choice",
                required=False,
                options=[
                    QuestionOption("counterparty", "상대방 양식"),
                    QuestionOption("ours", "당사 양식"),
                    QuestionOption("unknown", "미상"),
                ],
                tags=["source:template", "reason_code:template_owner"],
                related_rule_ids=[],
            ),
        )
    )

    candidates.sort(key=lambda x: x[0], reverse=True)
    picked: list[Question] = []
    used_ids: set[str] = set()
    for _, q in candidates:
        if q.question_id in used_ids:
            continue
        picked.append(q)
        used_ids.add(q.question_id)
        if len(picked) >= max_questions:
            break

    if picked:
        min_needed = min(3, max_questions)
        if len(picked) < min_needed:
            baselines: list[Question] = [
                Question(
                    question_id="Q-CA-999-template-owner",
                    title="상대방 양식인지, 당사 양식인지 확인",
                    description="상대방 양식이면 면책/책임/관할 등 불리 조항이 포함될 가능성이 높아 검토 강도가 올라간다.",
                    answer_type="single_choice",
                    required=False,
                    options=[
                        QuestionOption("counterparty", "상대방 양식"),
                        QuestionOption("ours", "당사 양식"),
                        QuestionOption("unknown", "미상"),
                    ],
                    tags=["source:template", "reason_code:template_owner"],
                    related_rule_ids=[],
                ),
                Question(
                    question_id="Q-CA-998-overseas",
                    title="해외법인/해외거래 관련 여부",
                    description="해외거래이면 준거법/관할/언어/수출통제/개인정보 국외이전 이슈를 추가로 확인한다.",
                    answer_type="single_choice",
                    required=False,
                    options=YES_NO,
                    tags=["topic:overseas", "reason_code:overseas_possible"],
                    related_rule_ids=["ACT-004"],
                ),
                Question(
                    question_id="Q-CA-997-personal-data",
                    title="개인정보 처리(수집/이용/제공/위탁) 여부",
                    description="개인정보 처리/위탁이 있으면 DPA 및 보안/재위탁/보관기간/파기/침해사고 통지 기준이 필요하다.",
                    answer_type="single_choice",
                    required=False,
                    options=YES_NO,
                    tags=["topic:privacy", "reason_code:privacy_possible"],
                    related_rule_ids=[],
                ),
            ]
            for bq in baselines:
                if bq.question_id in used_ids:
                    continue
                picked.append(bq)
                used_ids.add(bq.question_id)
                if len(picked) >= min_needed:
                    break
        return picked[:max_questions]

    if "해외법인" in ent:
        overseas_default = True
    else:
        overseas_default = False

    if overseas_default or any(r in detected for r in {"ACT-004"}):
        questions.append(
            Question(
                question_id="Q-002-overseas",
                title="해외법인/해외거래 관련 여부",
                description="해외거래이면 준거법/관할/언어/수출통제/개인정보 국외이전 이슈를 추가로 확인한다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:overseas", "priority:high"],
                related_rule_ids=["ACT-004"],
            )
        )
    else:
        questions.append(
            Question(
                question_id="Q-002-overseas",
                title="해외법인/해외거래 관련 여부",
                description="해외거래이면 준거법/관할/언어/수출통제/개인정보 국외이전 이슈를 추가로 확인한다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:overseas"],
                related_rule_ids=["ACT-004"],
            )
        )

    if any(k in ctype for k in ("개인정보", "DPA")):
        questions.append(
            Question(
                question_id="Q-003-personal-data",
                title="개인정보 처리(수집/이용/제공/위탁) 여부",
                description="개인정보 처리/위탁이 있으면 DPA 및 보안/재위탁/보관기간/파기/침해사고 통지 기준이 필요하다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:privacy", "priority:high"],
                related_rule_ids=[],
            )
        )
    else:
        questions.append(
            Question(
                question_id="Q-003-personal-data",
                title="개인정보 처리(수집/이용/제공/위탁) 여부",
                description="개인정보 처리/위탁이 있으면 DPA 및 보안/재위탁/보관기간/파기/침해사고 통지 기준이 필요하다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:privacy"],
                related_rule_ids=[],
            )
        )

    if any(k in ctype for k in ("용역", "자문", "SOW", "광고", "마케팅", "라이선스")) or any(
        r in detected for r in {"ACT-007", "RISK-004"}
    ):
        questions.append(
            Question(
                question_id="Q-004-deliverable-ip",
                title="산출물(저작권/디자인/소스코드/콘텐츠) 귀속/이전이 필요한지",
                description="산출물 귀속 방식에 따라 IP 귀속·사용허락·2차저작물·포트폴리오·대가·반환 의무 검토가 달라진다.",
                answer_type="single_choice",
                required=True,
                options=[
                    QuestionOption("assign_to_ours", "당사 귀속/이전 필요"),
                    QuestionOption("license_only", "사용허락(라이선스) 형태"),
                    QuestionOption("counterparty", "상대방 귀속"),
                    QuestionOption("unknown", "미상"),
                ],
                tags=["topic:ip", "priority:high"],
                related_rule_ids=["ACT-007", "RISK-004"],
            )
        )

    if any(r in detected for r in {"ACT-007", "RISK-004"}):
        questions.append(
            Question(
                question_id="Q-005-tech-material",
                title="기술자료/원가자료/소스코드 제공 요구가 있는지",
                description="기술자료 요구가 있으면 제공 범위·목적 제한·반환/파기·제3자 제공 금지·보안 수준을 별도로 확정해야 한다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:tech_material", "priority:high"],
                related_rule_ids=["ACT-007", "RISK-004"],
            )
        )

    if any(k in ctype for k in ("하도급", "도급", "공사")) or any(r in detected for r in {"RISK-005", "ACT-008"}):
        questions.append(
            Question(
                question_id="Q-006-subcontract",
                title="하도급/도급/단가 감액(인하) 이슈 여부",
                description="하도급 단가 감액/비용전가/검수-대금 연계 등은 고위험으로 별도 승인/가이드 적용이 필요하다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:subcontract", "priority:high"],
                related_rule_ids=["RISK-005", "ACT-008"],
            )
        )
    else:
        questions.append(
            Question(
                question_id="Q-006-subcontract",
                title="하도급/도급/단가 감액(인하) 이슈 여부",
                description="하도급 단가 감액/비용전가/검수-대금 연계 등은 고위험으로 별도 승인/가이드 적용이 필요하다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:subcontract"],
                related_rule_ids=["RISK-005", "ACT-008"],
            )
        )

    if any(k in ctype for k in ("대리점", "유통", "위탁")) or any(r in detected for r in {"RISK-006", "ACT-009"}):
        questions.append(
            Question(
                question_id="Q-007-dealer",
                title="대리점/유통/위탁 거래에서 비용 전가(판촉비/반품/광고비 등) 이슈 여부",
                description="대리점 비용전가는 고위험 후보로 별도 승인/가이드 적용이 필요하다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:dealer", "priority:high"],
                related_rule_ids=["RISK-006", "ACT-009"],
            )
        )

    if "대리점법" in topics:
        questions.append(
            Question(
                question_id="Q-LAW-001-dealer-consignment",
                title="위탁판매/위수탁(위탁매매) 구조인가요?",
                description="대리점/위탁 구조에 따라 비용 분담·판매장려금·판촉비 부담 조항의 위험도가 달라질 수 있다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:law_dealer_act"],
                related_rule_ids=[],
            )
        )
        questions.append(
            Question(
                question_id="Q-LAW-002-dealer-promo",
                title="판매장려금/판촉비/광고비/반품 비용 부담 조항이 있나요?",
                description="대리점/유통 계약에서 비용 전가 조항은 고위험 후보가 될 수 있어 확인이 필요하다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:law_dealer_act"],
                related_rule_ids=[],
            )
        )
    else:
        questions.append(
            Question(
                question_id="Q-007-dealer",
                title="대리점/유통/위탁 거래에서 비용 전가(판촉비/반품/광고비 등) 이슈 여부",
                description="대리점 비용전가는 고위험 후보로 별도 승인/가이드 적용이 필요하다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:dealer"],
                related_rule_ids=["RISK-006", "ACT-009"],
            )
        )

    if any(k in ctype for k in ("공사", "도급")) or any(r in detected for r in {"ACT-010"}):
        questions.append(
            Question(
                question_id="Q-008-onsite-work",
                title="공장/설치/현장 작업(안전/산업안전/중대재해) 여부",
                description="현장 작업이 있으면 안전책임 공백, 안전관리/교육/보호구/사고 통지/작업중지권 등 확인이 필요하다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:safety", "priority:high"],
                related_rule_ids=["ACT-010"],
            )
        )

    if any(k in ctype for k in ("광고", "마케팅", "협찬")):
        questions.append(
            Question(
                question_id="Q-009-ad-model",
                title="광고/모델(초상권/퍼블리시티권) 계약 여부",
                description="모델/초상권 계약이면 사용범위(매체/기간/지역), 2차사용, 철회, 위약금, 분쟁 대응을 확인한다.",
                answer_type="single_choice",
                required=True,
                options=YES_NO,
                tags=["topic:ad_model", "priority:high"],
                related_rule_ids=[],
            )
        )
    else:
        questions.append(
            Question(
                question_id="Q-009-ad-model",
                title="광고/모델(초상권/퍼블리시티권) 계약 여부",
                description="모델/초상권 계약이면 사용범위(매체/기간/지역), 2차사용, 철회, 위약금, 분쟁 대응을 확인한다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:ad_model"],
                related_rule_ids=[],
            )
        )

    if "하도급법" in topics:
        questions.append(
            Question(
                question_id="Q-LAW-003-subcontract-tech",
                title="기술자료(설계/도면/원가/소스 등) 요구 또는 제공 조항이 있나요?",
                description="기술자료 관련 조항은 별도 보호조치(목적 제한·반환/파기·제3자 제공 금지)가 필요할 수 있다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:law_subcontract_act"],
                related_rule_ids=[],
            )
        )
        questions.append(
            Question(
                question_id="Q-LAW-004-subcontract-price",
                title="단가 조정(감액/인하) 또는 재작업·재시공 비용 부담 조항이 있나요?",
                description="단가·재작업 비용 부담 조항은 하도급/도급 거래에서 고위험 후보가 될 수 있다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:law_subcontract_act"],
                related_rule_ids=[],
            )
        )

    if "개인정보보호법" in topics:
        questions.append(
            Question(
                question_id="Q-LAW-005-privacy-transfer",
                title="개인정보 국외이전(해외 서버/해외 법인 제공) 가능성이 있나요?",
                description="해외 이전이 있으면 별도 고지/동의/보호조치 조건을 확인해야 한다.",
                answer_type="single_choice",
                required=False,
                options=YES_NO,
                tags=["topic:law_privacy"],
                related_rule_ids=[],
            )
        )

    if any(r in detected for r in {"RISK-001", "RISK-002"}):
        questions.append(
            Question(
                question_id="Q-010-liability-cap",
                title="책임제한(상한) 합의가 필요한지",
                description="무제한 책임/일방 면책 후보가 탐지되면 책임 상한, 간접손해 제외, 손해배상 범위를 별도 협의해야 한다.",
                answer_type="single_choice",
                required=True,
                options=[
                    QuestionOption("need_cap", "상한 설정 필요"),
                    QuestionOption("ok_no_cap", "상한 없이 진행 가능"),
                    QuestionOption("unknown", "미상"),
                ],
                tags=["topic:liability", "priority:high"],
                related_rule_ids=["RISK-001", "RISK-002"],
            )
        )

    return questions

