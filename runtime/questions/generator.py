from __future__ import annotations

from runtime.questions.model import Question, QuestionOption


YES_NO = [
    QuestionOption("yes", "예"),
    QuestionOption("no", "아니오"),
    QuestionOption("unknown", "미상"),
]


def generate_questions(
    entity: str,
    contract_type: str,
    detected_rule_ids: list[str] | None,
    law_topics: list[str] | None = None,
) -> list[Question]:
    detected = set(detected_rule_ids or [])
    ctype = contract_type or ""
    ent = entity or ""
    topics = set([t.strip() for t in (law_topics or []) if isinstance(t, str) and t.strip()])

    questions: list[Question] = []

    questions.append(
        Question(
            question_id="Q-001-template-owner",
            title="상대방 양식인지, 당사(아우리봇) 양식인지 확인",
            description="상대방 양식이면 면책/책임/관할 등 불리 조항이 포함될 가능성이 높아 검토 강도가 올라간다.",
            answer_type="single_choice",
            required=True,
            options=[
                QuestionOption("counterparty", "상대방 양식"),
                QuestionOption("ours", "당사 양식"),
                QuestionOption("unknown", "미상"),
            ],
            tags=["source:template", "priority:high"],
            related_rule_ids=[],
        )
    )

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

