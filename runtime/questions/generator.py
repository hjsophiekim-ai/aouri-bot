from __future__ import annotations

import re

from runtime.questions.model import Question, QuestionOption
from runtime.review.jurisdiction import classify_jurisdiction_profile
from runtime.review.priority_map import infer_contract_profile
from runtime.review.user_focus import parse_user_focus_issues


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


def _topic_risk(clause_results: list[dict] | None, keywords: list[str]) -> str:
    best = "none"
    for cr in clause_results or []:
        if not isinstance(cr, dict):
            continue
        txt = " ".join([str(cr.get("clause_title") or ""), str(cr.get("display_path") or ""), str(cr.get("original_text") or "")])
        if not _has_any(txt, keywords):
            continue
        tier = str(cr.get("risk_tier") or "").strip().upper()
        if bool(cr.get("must_fix")) or tier == "HIGH":
            return "high"
        if tier == "MEDIUM":
            best = "medium"
    return best


def _top_keywords(text: str, keywords: list[str], *, limit: int = 3) -> list[str]:
    out: list[str] = []
    t = text.lower()
    for k in keywords:
        if k.lower() in t and k not in out:
            out.append(k)
        if len(out) >= limit:
            break
    return out


def _find_any(text: str, keywords: list[str]) -> list[int]:
    t = (text or "").lower()
    idxs: list[int] = []
    for k in keywords:
        kk = (k or "").lower()
        if not kk:
            continue
        start = 0
        while True:
            i = t.find(kk, start)
            if i < 0:
                break
            idxs.append(i)
            start = i + max(1, len(kk))
            if len(idxs) >= 30:
                return idxs
    return idxs


def _topic_state(
    text: str,
    *,
    anchors: list[str],
    clear_terms: list[str],
    ambiguity_terms: list[str],
    window: int = 140,
) -> str:
    t = text or ""
    if not _has_any(t, anchors):
        return "missing"
    idxs = _find_any(t, anchors)
    amb = False
    clr = False
    low = t.lower()
    for i in idxs[:12]:
        s = low[max(0, i - window) : min(len(low), i + window)]
        if any(a.lower() in s for a in ambiguity_terms):
            amb = True
        if any(c.lower() in s for c in clear_terms):
            clr = True
    if amb:
        return "ambiguous"
    if clr:
        return "clear"
    return "ambiguous"


def generate_questions(
    entity: str,
    contract_type: str,
    detected_rule_ids: list[str] | None,
    law_topics: list[str] | None = None,
    contract_text: str | None = None,
    clause_results: list[dict] | None = None,
    max_questions: int = 7,
    review_focus: str | None = None,
) -> list[Question]:
    detected = set(detected_rule_ids or [])
    ctype = contract_type or ""
    ent = entity or ""
    topics = set([t.strip() for t in (law_topics or []) if isinstance(t, str) and t.strip()])
    text = contract_text or ""
    clause_rule_ids = _extract_rule_ids(clause_results)
    jur = classify_jurisdiction_profile(text=text, entity=ent, contract_type=ctype, filename=None)
    prof = infer_contract_profile(contract_type=ctype, text=text)
    focus = parse_user_focus_issues(review_focus)
    focus_codes = {x.code for x in focus if hasattr(x, "code")}

    questions: list[Question] = []

    candidates: list[tuple[int, Question]] = []
    cap_present = _has_any(text, ["책임 상한", "책임상한", "limit of liability", "liability cap", "총 책임은", "총책임은"])
    privacy_present = _has_any(text, ["개인정보", "privacy", "dpa", "처리위탁", "수탁"])
    privacy_controls_present = _has_any(text, ["재위탁", "파기", "보관기간", "침해", "사고 통지", "보안조치"])
    dealer_present = _has_any(text, ["대리점", "유통", "위탁", "위탁판매", "위수탁"])
    dealer_cost_present = _has_any(text, ["판촉", "판매장려금", "광고비", "반품", "리베이트", "수수료", "비용 전가", "비용전가"])
    if dealer_cost_present:
        dealer_present = True
    dealer_cost_details_present = _has_any(text, ["상한", "정산", "증빙", "사전 서면", "서면 합의", "서면합의"])
    onsite_present = _has_any(text, ["설치", "시공", "현장", "작업", "공사", "물류센터"])
    safety_present = _has_any(text, ["산업안전", "중대재해", "안전관리", "보호구", "작업중지"])
    inspection_present = _has_any(text, ["검수", "검사", "시운전", "성능시험", "인수", "재검수"])
    subcontract_present = _has_any(text, ["재위탁", "하도급", "협력업체", "외주"])
    subcontract_approval_present = _has_any(text, ["사전 승인", "사전승인", "서면 승인", "서면승인", "승인"])
    app_dev_present = (
        _has_any(
            ctype,
            ["앱개발", "소프트웨어개발", "SI", "유지보수", "SaaS", "API"],
        )
        or _has_any(
            text,
            ["앱 개발", "소프트웨어 개발", "시스템 개발", "개발 용역", "SaaS", "API 연동", "소스코드", "산출물", "SLA"],
        )
    )
    ambiguity_markers = [
        "별도 협의",
        "추후 협의",
        "상호 협의",
        "협의한다",
        "협의하여",
        "별도로 정한다",
        "추후 정한다",
        "to be agreed",
        "tbd",
        "to be determined",
        "mutual agreement",
    ]
    ip_state = _topic_state(
        text,
        anchors=["산출물", "저작권", "지식재산", "ip", "프로그램", "source code", "소스코드"],
        clear_terms=["귀속", "양도", "이전", "소유", "ownership", "assign", "license", "이용허락", "사용권"],
        ambiguity_terms=ambiguity_markers,
    )
    source_delivery_state = _topic_state(
        text,
        anchors=["소스코드", "source code", "repository", "git"],
        clear_terms=["인도", "제공", "납품", "전달", "이관", "에스크로", "escrow", "저장소"],
        ambiguity_terms=ambiguity_markers,
    )
    maintenance_state = _topic_state(
        text,
        anchors=["유지보수", "maintenance", "운영", "하자보수"],
        clear_terms=["기간", "개월", "년", "범위", "무상", "유상", "요율", "응답", "복구", "지원시간", "SLA"],
        ambiguity_terms=ambiguity_markers,
    )
    acceptance_state = _topic_state(
        text,
        anchors=["검수", "인수", "acceptance", "테스트", "간주검수", "재검수"],
        clear_terms=["기준", "기간", "영업일", "재검수", "테스트 시나리오", "결함", "합격"],
        ambiguity_terms=ambiguity_markers,
    )
    sla_state = _topic_state(
        text,
        anchors=["SLA", "가용성", "uptime", "응답시간", "복구시간", "장애", "서비스 수준"],
        clear_terms=["%", "시간", "분", "rto", "rpo", "등급", "레벨", "크레딧", "감액"],
        ambiguity_terms=ambiguity_markers,
    )
    privacy_state = _topic_state(
        text,
        anchors=["개인정보", "privacy", "dpa", "처리위탁", "수탁", "위탁", "국외이전", "재위탁"],
        clear_terms=["재위탁", "파기", "보관", "국외", "암호화", "접근통제", "침해사고", "통지", "대응"],
        ambiguity_terms=ambiguity_markers,
    )
    oss_state = _topic_state(
        text,
        anchors=["오픈소스", "open source", "gpl", "mit", "apache", "라이선스", "license", "third party", "서드파티"],
        clear_terms=["목록", "sbom", "고지", "준수", "위반", "카피레프트", "공개", "copyleft"],
        ambiguity_terms=ambiguity_markers,
    )
    subcontract_state = _topic_state(
        text,
        anchors=["재위탁", "하도급", "외주", "협력업체", "subcontract"],
        clear_terms=["사전", "서면", "승인", "책임", "연대", "관리", "동일한 의무"],
        ambiguity_terms=ambiguity_markers,
    )
    security_state = _topic_state(
        text,
        anchors=["보안", "침해", "유출", "사고", "취약점", "암호화", "로그", "incident"],
        clear_terms=["통지", "조사", "시정", "재발방지", "손해배상", "비용", "협력"],
        ambiguity_terms=ambiguity_markers,
    )
    exit_state = _topic_state(
        text,
        anchors=["종료", "해지", "인수인계", "전환", "migration", "데이터", "반환", "삭제", "파기", "소스코드"],
        clear_terms=["반환", "삭제", "파기", "포맷", "기한", "확인", "증적", "지원", "이관"],
        ambiguity_terms=ambiguity_markers,
    )
    security_hint = _has_any(text, ["보안", "침해", "유출", "사고", "취약점", "암호화", "로그", "incident"])
    data_subject_hint = _has_any(text, ["회원", "이용자", "고객", "로그인", "계정", "배송", "결제", "주문", "사용자"])

    if max_questions < 1:
        max_questions = 1
    max_questions = min(int(max_questions), 7)

    if prof.profile == "dealer_consignment":
        if max_questions > 5:
            max_questions = 5

        cost_state = _topic_state(
            text,
            anchors=["판촉", "광고비", "반품", "판매장려금", "리베이트", "원상회복", "비용부담", "비용 전가", "비용전가"],
            clear_terms=["상한", "정산", "증빙", "사전", "서면", "합의", "산식", "기준"],
            ambiguity_terms=ambiguity_markers,
        )
        settle_state = _topic_state(
            text,
            anchors=["정산", "상계", "공제", "차감", "매출", "인보이스", "세금계산서"],
            clear_terms=["산식", "기준", "정산주기", "기한", "증빙", "정산서", "상계사유"],
            ambiguity_terms=ambiguity_markers,
        )
        term_state = _topic_state(
            text,
            anchors=["해지", "종료", "물량", "취소", "중단", "불이익"],
            clear_terms=["사유", "통지", "기간", "정산", "반환", "손해배상"],
            ambiguity_terms=ambiguity_markers,
        )
        privacy_state2 = _topic_state(
            text,
            anchors=["개인정보", "고객정보", "회원", "privacy", "dpa", "처리위탁", "수탁", "위탁"],
            clear_terms=["재위탁", "파기", "보관", "암호화", "접근통제", "침해사고", "통지", "대응"],
            ambiguity_terms=ambiguity_markers,
        )

        candidates.append(
            (
                96,
                Question(
                    question_id="Q-DL-001-form",
                    title="이 계약서는 상대방(대리점/위탁자) 양식인가요?",
                    description="상대방 양식이면 비용전가·정산·해지 등 핵심 조항이 상대방 유리하게 설계되는 경우가 많아, 검토 우선순위를 조정한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:dealer", "priority:high", "reason_code:deal_form"],
                    related_rule_ids=["ACT-009", "RISK-006"],
                ),
            )
        )
        candidates.append(
            (
                95 if cost_state == "missing" else (92 if cost_state == "ambiguous" else 86),
                Question(
                    question_id="Q-DL-002-cost-shift",
                    title="판촉비/광고비/반품비/원상회복 비용을 누가 어떤 기준(상한·증빙·정산)으로 부담하나요?",
                    description="대리점/위탁거래의 핵심 쟁점으로, 비용 부담 주체·상한·증빙·사전 서면합의가 불명확하면 분쟁 및 공정거래 리스크가 커질 수 있다.",
                    answer_type="single_choice",
                    required=(cost_state != "clear"),
                    options=YES_NO,
                    tags=["topic:dealer", "priority:high", ("reason_code:dealer_cost_shift_ambiguity" if cost_state != "clear" else "reason_code:confirm_dealer_cost_shift")],
                    related_rule_ids=["RISK-006", "ACT-009"],
                ),
            )
        )
        if cost_state != "clear":
            candidates.append(
                (
                    91 if cost_state == "missing" else 89,
                    Question(
                        question_id="Q-CA-001-dealer-cost",
                        title="대리점/위탁 거래에서 비용 부담(판촉비/광고비/반품 등) 항목·상한·정산 기준이 계약서에 명확히 적혀 있나요?",
                        description="대리점 비용전가 조항은 고위험 후보가 될 수 있어, 항목·상한·정산·증빙·사전 서면합의 요건을 명확히 해야 한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:dealer", "priority:medium", "reason_code:dealer_cost_terms"],
                        related_rule_ids=["RISK-006", "ACT-009"],
                    ),
                )
            )
        candidates.append(
            (
                92 if settle_state == "missing" else (90 if settle_state == "ambiguous" else 86),
                Question(
                    question_id="Q-DL-003-settlement",
                    title="정산식/상계/공제(차감) 기준과 정산 주기·증빙·이의제기 절차가 명확한가요?",
                    description="정산/상계/공제는 대금 분쟁의 핵심이라 산식·기준·증빙과 이의제기 기간이 모호하면 리스크가 커진다.",
                    answer_type="single_choice",
                    required=(settle_state != "clear"),
                    options=YES_NO,
                    tags=["topic:dealer", "priority:high", ("reason_code:settlement_offset_ambiguity" if settle_state != "clear" else "reason_code:confirm_settlement_controls")],
                    related_rule_ids=["C-001"],
                ),
            )
        )
        candidates.append(
            (
                91 if term_state == "missing" else (89 if term_state == "ambiguous" else 86),
                Question(
                    question_id="Q-DL-004-termination",
                    title="계약 해지/물량 축소/불이익 조치가 가능한 조건과 절차(통지·유예·정산)가 명확한가요?",
                    description="해지/불이익 조치는 거래상 지위 남용 리스크와 직결되므로, 요건·절차·정산을 명확히 해야 한다.",
                    answer_type="single_choice",
                    required=(term_state != "clear"),
                    options=YES_NO,
                    tags=["topic:dealer", "priority:high", ("reason_code:termination_disadvantage_risk" if term_state != "clear" else "reason_code:confirm_termination_controls")],
                    related_rule_ids=["RISK-006"],
                ),
            )
        )
        if ("dealer_management_interference" in focus_codes) or ("dealer_unfair_disadvantage" in focus_codes):
            candidates.append(
                (
                    94,
                    Question(
                        question_id="Q-DL-006-unfair-interference",
                        title="불이익 제공/경영간섭(가격·인사·영업정책 강제 등) 위험이 있는 조항이 있나요?",
                        description="대리점법상 불이익 제공·경영간섭은 핵심 쟁점이다. 해당 정황이 있으면 관련 조항을 최우선으로 집중 검토한다.",
                        answer_type="single_choice",
                        required=True,
                        options=YES_NO,
                        tags=["topic:dealer", "priority:high", "reason_code:user_focus_dealer_unfair"],
                        related_rule_ids=["ACT-009", "RISK-006"],
                    ),
                )
            )
        if ("dispute" in focus_codes) or ("dealer_unfair_disadvantage" in focus_codes):
            candidates.append(
                (
                    87,
                    Question(
                        question_id="Q-DL-007-dispute-special",
                        title="대리점법상 분쟁조정/관할/준거법에 관해 특별히 요구하는 방향이 있나요?",
                        description="국내 대리점 거래는 해외 집행 논리보다 관할·분쟁해결 절차(조정 포함)가 실무적으로 중요할 수 있어, 원하는 방향을 확인한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:dispute", "priority:medium", "reason_code:user_focus_dispute"],
                        related_rule_ids=["ACT-004"],
                    ),
                )
            )
        if ("personal_data" in text.lower()) or (privacy_state2 != "missing" and privacy_state2 != "clear"):
            candidates.append(
                (
                    88 if privacy_state2 == "missing" else 86,
                    Question(
                        question_id="Q-DL-005-privacy",
                        title="고객/회원정보 등 개인정보를 처리(제공/위탁/재위탁)하는 경우, 재위탁·파기/반환·침해사고 통지 기준이 명확한가요?",
                        description="대리점/위탁거래에서도 고객정보 처리가 있으면 개인정보보호법상 책임이 발생할 수 있어, 재위탁·안전조치·파기/반환·침해사고 통지를 점검해야 한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:privacy", "priority:medium", "reason_code:privacy_controls_missing"],
                    related_rule_ids=[],
                    ),
                )
            )

        if jur.kind != "domestic_korea":
            candidates.append(
                (
                    87,
                    Question(
                        question_id="Q-DL-006-crossborder",
                        title="해외 당사자/해외 지급/해외 수행 등 해외 거래 정황이 있나요?",
                        description="해외 거래 정황이 있으면 준거법/관할(또는 중재)과 집행 가능성까지 고려해야 한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:dispute", "priority:medium", "reason_code:cross_border_classifier"],
                        related_rule_ids=["ACT-004"],
                    ),
                )
            )

        candidates.sort(key=lambda x: int(x[0]), reverse=True)
        return [q for _, q in candidates[:max_questions]]

    if prof.profile == "ops_outsourcing":
        if max_questions > 5:
            max_questions = 5

        scope_state = _topic_state(
            text,
            anchors=["운영", "대행", "위탁운영", "운영위탁", "업무범위", "서비스", "관리", "대상 공간", "매장", "라운지"],
            clear_terms=["별지", "KPI", "성과", "보고", "점검", "검수", "인수", "기준", "주기"],
            ambiguity_terms=ambiguity_markers,
        )
        staffing_state = _topic_state(
            text,
            anchors=["인력", "직원", "근무", "교대", "배치", "교육", "관리자", "책임자"],
            clear_terms=["인원", "자격", "요건", "교체", "승인", "근무시간", "휴게", "업무지시"],
            ambiguity_terms=ambiguity_markers,
        )
        reporting_state = _topic_state(
            text,
            anchors=["보고", "보고서", "자료제출", "실적", "월간", "주간", "정기"],
            clear_terms=["주기", "양식", "기한", "전자", "서면"],
            ambiguity_terms=ambiguity_markers,
        )
        settle_state = _topic_state(
            text,
            anchors=["정산", "지급", "대금", "용역비", "수수료", "운영수수료", "상계", "공제", "증빙"],
            clear_terms=["산식", "기준", "정산주기", "기한", "증빙", "정산서", "이의제기"],
            ambiguity_terms=ambiguity_markers,
        )
        term_state = _topic_state(
            text,
            anchors=["해지", "종료", "갱신", "중도해지", "위약", "손해배상", "제재", "패널티"],
            clear_terms=["사유", "통지", "기간", "유예", "정산", "인수인계"],
            ambiguity_terms=ambiguity_markers,
        )

        candidates.append(
            (
                96,
                Question(
                    question_id="Q-OPS-001-form",
                    title="이 운영대행/위탁운영 계약서는 상대방 양식인가요?",
                    description="상대방 양식이면 운영범위·정산·해지·책임 배분이 상대방 유리하게 설계되는 경우가 많아, 검토 우선순위를 조정한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:ops", "priority:high", "reason_code:ops_form"],
                    related_rule_ids=[],
                ),
            )
        )
        candidates.append(
            (
                95 if scope_state != "clear" else 88,
                Question(
                    question_id="Q-OPS-002-scope-kpi",
                    title="운영 범위(업무범위), 성과/KPI, 보고·검수 기준이 계약서에 명확히 적혀 있나요?",
                    description="운영대행 계약의 핵심은 범위·성과·보고·검수의 명확성이다. 모호하면 인력·비용·책임 분쟁이 커질 수 있다.",
                    answer_type="single_choice",
                    required=(scope_state != "clear"),
                    options=YES_NO,
                    tags=["topic:ops", "priority:high", "reason_code:ops_scope_kpi"],
                    related_rule_ids=[],
                ),
            )
        )
        candidates.append(
            (
                93 if staffing_state != "clear" else 86,
                Question(
                    question_id="Q-OPS-003-staffing",
                    title="운영 인력 배치(인원/자격/교체/교육)와 지휘·감독 범위가 명확한가요?",
                    description="인력 배치/교체/교육과 지휘·감독 구조가 불명확하면 품질·안전·노무 리스크로 이어질 수 있다.",
                    answer_type="single_choice",
                    required=(staffing_state != "clear"),
                    options=YES_NO,
                    tags=["topic:ops", "priority:high", "reason_code:ops_staffing_controls"],
                    related_rule_ids=[],
                ),
            )
        )
        candidates.append(
            (
                92 if settle_state != "clear" else 86,
                Question(
                    question_id="Q-OPS-004-settlement",
                    title="정산(용역비/수수료) 산식·정산주기·증빙·이의제기 절차가 명확한가요?",
                    description="정산/상계/증빙이 모호하면 운영대행 계약에서 가장 큰 분쟁(대금)으로 번질 수 있다.",
                    answer_type="single_choice",
                    required=(settle_state != "clear"),
                    options=YES_NO,
                    tags=["topic:payment", "priority:high", "reason_code:ops_settlement_controls"],
                    related_rule_ids=["C-001"],
                ),
            )
        )
        candidates.append(
            (
                90 if subcontract_state != "clear" else 84,
                Question(
                    question_id="Q-OPS-005-subcontract",
                    title="하도급/재위탁(협력업체 사용) 가능 여부와 사전 서면 승인·책임 귀속이 명확한가요?",
                    description="운영 품질·안전·개인정보가 협력업체로 넘어갈 수 있어, 재위탁 통제(사전 승인/동일 의무/책임)를 확인해야 한다.",
                    answer_type="single_choice",
                    required=(subcontract_state != "clear") and subcontract_present,
                    options=YES_NO,
                    tags=["topic:subcontract", "priority:high", "reason_code:ops_subcontract_control"],
                    related_rule_ids=["ACT-010"],
                ),
            )
        )

        if ("termination_abuse" in focus_codes) or ("dealer_unfair_disadvantage" in focus_codes) or ("dealer_management_interference" in focus_codes):
            candidates.append(
                (
                    94,
                    Question(
                        question_id="Q-OPS-006-unfair-termination",
                        title="운영지침/평가/제재/일방 해지 등으로 과도한 불이익(거래상 지위 남용/경영간섭)이 발생할 위험이 있나요?",
                        description="운영대행에서도 지침 강제, 평가·패널티, 일방 해지/계약조건 변경이 누적되면 거래상 지위 남용 리스크가 될 수 있어 우선 확인한다.",
                        answer_type="single_choice",
                        required=True,
                        options=YES_NO,
                        tags=["topic:dealer", "priority:high", "reason_code:user_focus_unfair_ops"],
                        related_rule_ids=["ACT-009"],
                    ),
                )
            )

        if onsite_present or safety_present or _has_any(text, ["안전관리", "산업안전", "중대재해"]):
            candidates.append(
                (
                    88,
                    Question(
                        question_id="Q-OPS-007-safety",
                        title="현장/공간 운영 중 안전관리 책임(교육·보호구·사고 보고·작업중지 등)이 계약서에 포함돼 있나요?",
                        description="현장 운영 정황이 있으면 산안법/중대재해 리스크가 핵심이므로 안전관리 책임과 협력 체계를 확인한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:safety", "priority:medium", "reason_code:ops_safety_presence"],
                        related_rule_ids=["ACT-010"],
                    ),
                )
            )

        if privacy_present or data_subject_hint:
            candidates.append(
                (
                    87,
                    Question(
                        question_id="Q-OPS-008-privacy",
                        title="고객/이용자 정보 등 개인정보를 처리(접근/제공/재위탁)하나요? 그렇다면 재위탁·파기/반환·침해사고 통지가 명확한가요?",
                        description="운영대행에서 고객 접점이 있으면 개인정보보호법상 책임이 발생할 수 있어, 처리 범위와 통제(재위탁/파기/침해사고)를 확인한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:privacy", "priority:medium", "reason_code:ops_privacy_presence"],
                        related_rule_ids=[],
                    ),
                )
            )

        if term_state != "clear":
            candidates.append(
                (
                    89,
                    Question(
                        question_id="Q-OPS-009-termination",
                        title="계약 해지/갱신 조건과 해지 시 인수인계·정산·자료 반환 의무가 명확한가요?",
                        description="운영대행 계약은 해지 시점의 인수인계·자료 반환·정산이 핵심 분쟁 포인트가 될 수 있어 확인한다.",
                        answer_type="single_choice",
                        required=False,
                        options=YES_NO,
                        tags=["topic:termination", "priority:medium", "reason_code:ops_termination_exit"],
                        related_rule_ids=["ACT-004"],
                    ),
                )
            )

        candidates.sort(key=lambda x: int(x[0]), reverse=True)
        return [q for _, q in candidates[:max_questions]]

    ip_risk = _topic_risk(clause_results, ["산출물", "저작권", "지식재산", "ip", "소스코드", "프로그램"])
    oss_risk = _topic_risk(clause_results, ["오픈소스", "open source", "gpl", "mit", "apache", "라이선스", "license", "서드파티"])
    maintenance_risk = _topic_risk(clause_results, ["유지보수", "운영", "하자보수", "SLA", "장애"])
    acceptance_risk = _topic_risk(clause_results, ["검수", "인수", "간주검수", "재검수", "테스트", "시운전"])
    sla_risk = _topic_risk(clause_results, ["SLA", "가용성", "uptime", "응답시간", "복구시간", "장애", "서비스 수준"])
    privacy_risk = _topic_risk(clause_results, ["개인정보", "처리위탁", "수탁", "국외이전", "재위탁", "파기", "유출"])
    subcontract_risk = _topic_risk(clause_results, ["재위탁", "하도급", "외주", "협력업체"])
    security_risk = _topic_risk(clause_results, ["보안", "침해", "유출", "사고", "취약점", "암호화"])
    exit_risk = _topic_risk(clause_results, ["종료", "해지", "인수인계", "데이터", "반환", "삭제", "파기"])

    if app_dev_present and ip_state != "clear":
        candidates.append(
            (
                (96 if ip_state == "missing" else 94)
                + (4 if ip_risk == "high" else (2 if ip_risk == "medium" else 0)),
                Question(
                    question_id="Q-AD-001-ip-ownership",
                    title="개발 산출물/소스코드/저작권(IP) 귀속(양도/이용허락) 구조가 계약서에 명확히 적혀 있나요?",
                    description="앱/소프트웨어 개발계약의 핵심 쟁점으로, 산출물·소스코드 귀속 및 이용범위(수정/배포/재사용)와 제3자 권리침해 보증·시정 구조가 빠지면 분쟁이 커질 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_ip_ownership_terms"],
                    related_rule_ids=["APP-001"],
                ),
            )
        )

    if app_dev_present and oss_state != "clear":
        candidates.append(
            (
                (93 if oss_state == "missing" else 92)
                + (4 if oss_risk == "high" else (2 if oss_risk == "medium" else 0)),
                Question(
                    question_id="Q-AD-002-oss",
                    title="오픈소스/서드파티 라이브러리 사용 고지(SBOM)와 라이선스 준수/위반 시 시정·배상 구조가 계약서에 포함돼 있나요?",
                    description="오픈소스 라이선스 위반은 소스 공개 의무 등 치명적 리스크로 이어질 수 있어, 사용 제한/고지/준수/치료책(대체·제거) 구조를 명확히 해야 한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_oss_controls"],
                    related_rule_ids=["APP-002"],
                ),
            )
        )

    if app_dev_present and _has_any(text, ["개발", "요구사항", "사양", "SOW", "범위"]) and _topic_state(
        text,
        anchors=["요구사항", "사양", "SOW", "범위", "기능명세", "변경요청", "change request"],
        clear_terms=["별지", "요청서", "승인", "견적", "영향분석", "일정", "비용"],
        ambiguity_terms=ambiguity_markers,
    ) != "clear":
        candidates.append(
            (
                92,
                Question(
                    question_id="Q-AD-003-sow",
                    title="개발 범위/요구사항/사양(SOW)과 변경관리(추가비용·일정 반영) 절차가 계약서에 명확히 정의돼 있나요?",
                    description="범위·사양이 모호하면 일정 지연/추가비용/검수 분쟁으로 확대될 수 있어, 별지 SOW와 변경요청 승인 프로세스를 명확히 해야 한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_sow_change_control"],
                    related_rule_ids=["APP-003"],
                ),
            )
        )

    if app_dev_present and acceptance_state != "clear":
        candidates.append(
            (
                (92 if acceptance_state == "missing" else 90)
                + (4 if acceptance_risk == "high" else (2 if acceptance_risk == "medium" else 0)),
                Question(
                    question_id="Q-AD-004-acceptance",
                    title="검수 기준과 검수 기간(재검수/간주검수 포함)이 계약서에 명확히 정해져 있나요?",
                    description="검수 기준/기간/재검수/간주검수는 대금지급·책임전환의 핵심이라, 요건이 약하면 분쟁이 커질 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_acceptance_terms"],
                    related_rule_ids=["APP-004"],
                ),
            )
        )

    if app_dev_present and sla_state != "clear" and _has_any(text, ["SLA", "가용성", "응답시간", "복구시간", "장애", "서비스 수준", "uptime", "유지보수"]):
        candidates.append(
            (
                89 + (4 if sla_risk == "high" else (2 if sla_risk == "medium" else 0)),
                Question(
                    question_id="Q-AD-005-sla",
                    title="장애 대응 시간/가용성 등 SLA(서비스 수준)를 계약서에 명시할 필요가 있나요?",
                    description="SLA가 모호하면 장애 대응 및 대금 감액/크레딧/해지 등 구제수단이 작동하지 않아 운영 리스크가 커질 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_sla_terms"],
                    related_rule_ids=["APP-006", "APP-012"],
                ),
            )
        )

    if app_dev_present and privacy_state != "clear" and (data_subject_hint or _has_any(text, ["개인정보", "privacy", "dpa", "처리위탁", "수탁", "위탁"])):
        candidates.append(
            (
                88 + (4 if privacy_risk == "high" else (2 if privacy_risk == "medium" else 0)),
                Question(
                    question_id="Q-AD-006-privacy-processing",
                    title="개인정보 처리/위탁(DPA) 여부와 재위탁·파기·사고 통지 등 통제조항이 계약서에 충분히 포함돼 있나요?",
                    description="앱/서비스 운영은 개인정보 이슈로 연결될 수 있어, 처리위탁 여부와 통제(재위탁/파기/통지/보안조치)를 계약서 또는 부속합의로 확정해야 한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:privacy", "priority:high", "reason_code:missing_privacy_processing_terms"],
                    related_rule_ids=["APP-007", "APP-010"],
                ),
            )
        )

    if app_dev_present and source_delivery_state != "clear":
        candidates.append(
            (
                (87 if source_delivery_state == "missing" else 86)
                + (4 if ip_risk == "high" else (2 if ip_risk == "medium" else 0)),
                Question(
                    question_id="Q-AD-007-source-delivery",
                    title="소스코드 인도(저장소 이전/접근권 포함)가 계약 범위에 포함되어야 하나요?",
                    description="소스코드 인도 여부는 종료·전환 리스크와 직결되므로, 인도 범위(저장소/빌드스크립트/환경설정)와 시점을 명확히 해야 한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_source_code_delivery_terms"],
                    related_rule_ids=["APP-001", "APP-011"],
                ),
            )
        )

    if app_dev_present and maintenance_state != "clear":
        candidates.append(
            (
                86 if maintenance_state == "missing" else 84,
                Question(
                    question_id="Q-AD-008-maintenance-scope",
                    title="유지보수 범위와 기간(무상/유상, 지원시간, 업데이트 정책)이 계약서에 명확히 정해져 있나요?",
                    description="유지보수 조항이 포괄적이거나 기간/범위가 불명확하면 운영 단계에서 추가비용/책임 분쟁이 발생할 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_maintenance_terms"],
                    related_rule_ids=["APP-006"],
                ),
            )
        )

    if app_dev_present and subcontract_present and not subcontract_approval_present:
        candidates.append(
            (
                85,
                Question(
                    question_id="Q-AD-009-subcontract",
                    title="재위탁(외주/하도급) 개발을 허용한다면 사전 서면 승인과 책임 귀속(보안/IP 포함)이 명확한가요?",
                    description="재위탁은 품질·보안·IP 리스크를 증폭시키므로, 사전 승인과 하위수탁자 관리/연대책임 구조가 필요하다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_subcontract_controls"],
                    related_rule_ids=["APP-009"],
                ),
            )
        )

    if app_dev_present and security_state != "clear" and (privacy_state != "missing" or security_hint):
        candidates.append(
            (
                84,
                Question(
                    question_id="Q-AD-010-security-incident",
                    title="보안사고/개인정보 유출 발생 시 통지·조사·시정·재발방지 및 비용/손해배상 책임 구조가 계약서에 명확히 있나요?",
                    description="침해사고는 통지·협력·비용 부담·재위탁 통제까지 계약에 담겨야 실제 대응이 가능하다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:security", "priority:high", "reason_code:missing_security_incident_procedure"],
                    related_rule_ids=["APP-007"],
                ),
            )
        )

    if app_dev_present and exit_state != "clear":
        candidates.append(
            (
                83 if exit_state == "missing" else 82,
                Question(
                    question_id="Q-AD-011-exit-handover",
                    title="계약 종료 시 데이터/소스코드 반환·삭제 및 인수인계/전환 지원이 계약서에 명확히 포함되어야 하나요?",
                    description="종료/전환 조항이 약하면 서비스 중단과 개인정보 리스크가 커질 수 있어, 반환 포맷/기한/삭제 확인 및 전환 지원 범위를 명확히 해야 한다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:appdev", "priority:high", "reason_code:missing_exit_handover_terms"],
                    related_rule_ids=["APP-010", "APP-011"],
                ),
            )
        )

    if (
        dealer_present
        and ("RISK-006" in detected or "RISK-006" in clause_rule_ids or dealer_cost_present)
        and not dealer_cost_details_present
    ):
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
                85,
                Question(
                    question_id="Q-CA-006-privacy-controls",
                    title="개인정보 처리/위탁이 있다면 재위탁, 보관기간, 파기, 침해사고 통지, 보안조치 기준이 계약서에 명확히 포함되어 있나요?",
                    description="개인정보 관련 통제 조항이 빠져 있으면 DPA/보안 부속 합의가 필요할 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:privacy", "priority:high", "reason_code:missing_privacy_controls"],
                    related_rule_ids=[],
                ),
            )
        )

    if onsite_present and not inspection_present:
        candidates.append(
            (
                84,
                Question(
                    question_id="Q-CA-007-inspection-acceptance",
                    title="납품/설치/시운전의 검수 기준(재검수 포함)과 인수 시점이 계약서에 명확히 적혀 있나요?",
                    description="검수 기준/절차/재검수/인수 시점이 불명확하면 성능 미달·지연·대금 지급과 연계되어 분쟁이 커질 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:inspection", "priority:high", "reason_code:missing_inspection_terms"],
                    related_rule_ids=[],
                ),
            )
        )

    if onsite_present and (not subcontract_present or (subcontract_present and not subcontract_approval_present)):
        candidates.append(
            (
                83,
                Question(
                    question_id="Q-CA-008-subcontract-approval",
                    title="설치/시공/시운전을 협력업체에 재위탁(하도급)할 수 있다면, 사전 서면 승인과 안전·품질 책임 귀속이 명확한가요?",
                    description="현장 작업은 재위탁 관리가 핵심이며, 승인/책임/보험/사고 통지 체계가 없으면 당사 리스크가 커질 수 있다.",
                    answer_type="single_choice",
                    required=True,
                    options=YES_NO,
                    tags=["topic:safety", "priority:high", "reason_code:missing_subcontract_controls"],
                    related_rule_ids=["ACT-010"],
                ),
            )
        )

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

