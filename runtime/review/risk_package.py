"""Risk Package — 같은 법률효과를 만드는 조항들을 하나로 묶어 **최대 exposure**를
산정한다 (2026-09-09 지시 4항).

조항별로 따로 나열하면 각 항목이 다 "받아들일 만한" 수준으로 보인다. 문제는
그것들이 동시에 발동한다는 데 있다. 예를 들어 해지 패키지:

    상대방의 일방적 해지권          그 자체로는 흔한 조항
    + 계약이행보증금 귀속           그 자체로는 흔한 조항
    + 추가 손해배상 청구            그 자체로는 흔한 조항
    + 기성금에서 상계               그 자체로는 흔한 조항
    ─────────────────────────────
    = 상대방이 언제든 해지하고, 보증금을 가져가고, 손해배상까지 청구하며,
      우리가 이미 한 일의 대금에서 그것을 공제한다. 우리 회사의 실제 최대
      노출은 "계약금액 + 보증금"이고, 받을 돈은 0 이 될 수 있다.

이 모듈은 계약 전체에서 패키지 구성요소의 존재 여부와, 그 위험이 누구에게
배분됐는지(위험배분 매트릭스 결과 재사용), 완충장치(cap·예외·귀책요건)가
있는지를 함께 본다.

설계 — **하드코딩 금지**. 특정 계약명·회사명·조항번호를 쓰지 않는다. 구성요소는
실무 계약이 쓰는 일반 문형으로만 찾고, 부담 주체 판정은 매트릭스에 위임한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


def _rx(*alts: str) -> re.Pattern[str]:
    return re.compile("|".join(alts), re.IGNORECASE | re.DOTALL)


#: 구성요소가 당사자를 검증해야 하는지. 문형만 보면 방향이 반대인 조항까지
#: 잡는다 — "공사 중지에 따른 추가 비용은 도급인이 부담한다"를 "추가비용
#: 자기부담"으로 보고했다(2026-09-09 실측). 부담·권리의 주체를 확인한다.
ACTOR_ANY = ""
ACTOR_OURS = "ours"          # 우리 쪽이 부담자로 지목돼야 성립
ACTOR_THEIRS = "theirs"      # 상대방이 권리자·수익자로 지목돼야 성립


@dataclass(frozen=True)
class PackageComponent:
    key: str
    label: str
    pattern: re.Pattern[str]
    actor: str = ACTOR_ANY


@dataclass(frozen=True)
class RiskPackage:
    key: str
    label: str
    #: 이 패키지가 걸쳐 있는 위험배분 축(risk_allocation_matrix 의 key)
    axes: tuple[str, ...]
    #: 노출을 키우는 구성요소 — 많이 모이면 그만큼 위험이 겹친다
    components: tuple[PackageComponent, ...]
    #: 노출을 줄이는 완충장치 — 하나라도 있으면 최대 노출이 내려간다
    mitigations: tuple[PackageComponent, ...]
    #: 왜 따로 보면 안 되는지
    why: str


#: 권리 주체가 명시되는 문형 — {P} 자리에 당사자 호칭이 들어간다.
#: 부담 문형(_BEAR)과 대칭으로 쓴다. **주격 조사만** 받는다: "{P}에게 청구"는
#: P 가 권리자라는 뜻이 아니라 P 를 **상대로** 청구한다는 뜻이다. 이걸
#: 구분하지 않아 "수급인은 도급인에게 배상을 청구할 수 있다"(우리 권리)가
#: "상대방의 손해배상 청구권"으로 잡혔다(2026-09-09 실측).
_RIGHT = (
    r"{P}(?:\s*[”\"'’])?\s*(?:은|는|이|가)[^.\n]{{0,60}}?"
    r"(?:할\s*수\s*있다|청구(?:한다|할)|요구할\s*수|해지|해제)",
)

#: 수익 주체가 명시되는 문형. 여기서는 "{P}에게 귀속"이 P 가 얻는다는 뜻이다.
_BENEFIT = (
    r"{P}(?:\s*[”\"'’])?\s*(?:에게|에|으로)[^.\n]{{0,20}}?"
    r"(?:귀속(?:된다|한다|하며)?|몰취|몰수)",
    r"{P}(?:\s*[”\"'’])?\s*(?:은|는|이|가)[^.\n]{{0,40}}?(?:몰취|몰수)",
)

_C = PackageComponent

RISK_PACKAGES: tuple[RiskPackage, ...] = (
    RiskPackage(
        key="termination_exit",
        label="해지 패키지 (해지권 + 보증금 몰취 + 손해배상 + 상계)",
        axes=("termination", "bond_forfeiture", "damages", "setoff"),
        components=(
            _C("unilateral_termination", "일방적 해지권",
               _rx(r"(?:언제(?:든지|라도)|사전\s*통(?:지|보)(?:만|로써)?|"
                   r"필요(?:하다고)?\s*(?:인정|판단))[^.\n]{0,40}?(?:해지|해제)",
                   r"(?:해지|해제)할\s*수\s*있다",
                   r"terminate[^.\n]{0,40}?(?:at\s+any\s+time|for\s+convenience)"),
               ACTOR_THEIRS),
            _C("bond_forfeiture", "보증금 귀속·몰취",
               _rx(r"보증금[^.\n]{0,40}?(?:귀속|몰취|몰수)", r"forfeit"),
               ACTOR_THEIRS),
            _C("extra_damages", "보증금과 별도의 손해배상",
               _rx(r"보증금[^.\n]{0,60}?(?:외에|불구하고|별도)[^.\n]{0,40}?손해",
                   r"손해[^.\n]{0,40}?(?:배상을\s*)?청구할\s*수\s*있다"),
               ACTOR_THEIRS),
            # "건설공제조합"·"산업재해보상보험 공제"의 공제를 상계로 읽으면
            # 지급보증 조항이 상계 조항으로 잡힌다(2026-09-09 실측).
            _C("setoff", "기성금·대금에서 공제·상계",
               _rx(r"(?:기성|대금|정산금|공사대금)[^.\n]{0,40}?"
                   r"(?:상계|(?<!건설)(?<!산업)공제(?!조합))",
                   r"(?:상계|(?<!건설)(?<!산업)공제(?!조합))[^.\n]{0,40}?"
                   r"(?:할\s*수\s*있다|한다)"),
               ACTOR_THEIRS),
        ),
        mitigations=(
            _C("fault_requirement", "귀책사유 요건",
               _rx(r"귀책\s*사유", r"(?:책임\s*있는|중대한)\s*(?:사유|과실)",
                   r"material\s+breach")),
            _C("cure_period", "시정기간 부여",
               _rx(r"(?:시정|보완|치유)[^.\n]{0,20}?(?:기간|기회)",
                   r"\d+\s*일\s*(?:이내|전)[^.\n]{0,20}?(?:시정|보완)",
                   r"cure\s+period")),
            _C("damages_cap", "손해배상 상한",
               _rx(r"손해\s*배상[^.\n]{0,40}?(?:한도|상한|초과하지)",
                   r"(?:한도|상한)[^.\n]{0,30}?손해\s*배상",
                   r"liability[^.\n]{0,40}?(?:cap|shall\s+not\s+exceed)")),
        ),
        why=("해지·몰취·손해배상·상계는 동시에 발동한다. 따로 보면 각각 흔한 "
             "조항이지만, 함께 걸리면 이미 수행한 일의 대금까지 회수하지 못한다."),
    ),
    RiskPackage(
        key="delay_penalty",
        label="지연 패키지 (지체상금 + 상한 + 공기연장 예외)",
        axes=("schedule_delay",),
        components=(
            _C("late_penalty", "지체상금",
               _rx(r"지체\s*상금", r"liquidated\s+damages"),
               ACTOR_OURS),
            # 요율 숫자만 보면 "계약이행보증 : 계약금액의 10%" 같은 무관한
            # 표기를 지체상금률로 읽는다(2026-09-09 실측). 지체 문맥을 요구한다.
            _C("penalty_rate", "지체상금률",
               _rx(r"지체\s*상금\s*률",
                   r"지체[^.\n]{0,40}?\d+\s*/\s*1[,.]?000",
                   r"지체[^.\n]{0,40}?\d+\s*천분\s*의\s*\d+",
                   r"지체[^.\n]{0,40}?\d+(?:\.\d+)?\s*%")),
            _C("delay_termination", "지연을 이유로 한 해지",
               _rx(r"지체[^.\n]{0,60}?(?:해지|해제)",
                   r"지체\s*상금[^.\n]{0,60}?(?:초과|달(?:하|한))[^.\n]{0,40}?(?:해지|해제)"),
               ACTOR_THEIRS),
        ),
        mitigations=(
            _C("penalty_cap", "지체상금 상한",
               _rx(r"지체\s*상금[^.\n]{0,60}?(?:한도|상한|까지로\s*한다|초과(?:할\s*수)?\s*없)",
                   r"(?:계약\s*금액|도급\s*금액)[^.\n]{0,20}?\d+\s*%\s*(?:까지|이내|한도)")),
            _C("time_extension", "공기연장 사유",
               _rx(r"공사\s*기간[^.\n]{0,20}?연장", r"준공\s*기한[^.\n]{0,20}?연장",
                   r"extension\s+of\s+time")),
            _C("delay_exception", "무귀책 지연 면제",
               _rx(r"(?:불가항력|천재\s*지변)[^.\n]{0,60}?(?:지체\s*상금|면(?:제|책))",
                   r"(?:도급인|발주자|발주처)[^.\n]{0,20}?(?:책임|귀책)[^.\n]{0,60}?"
                   r"(?:연장|면(?:제|책))")),
        ),
        why=("지체상금은 상한과 공기연장 예외가 함께 있어야 계산 가능한 위험이 된다. "
             "상한이 없거나 무귀책 지연이 면제되지 않으면 노출이 사실상 무한이다."),
    ),
    RiskPackage(
        key="defect_liability",
        label="하자 패키지 (하자기간 + 재하자 + 보증금 + 진단비)",
        axes=("defects", "bond_forfeiture"),
        components=(
            _C("defect_period", "하자담보 책임기간",
               _rx(r"하자\s*(?:담보|보수)[^.\n]{0,20}?(?:책임\s*)?기간",
                   r"defects?\s+liability\s+period")),
            _C("repeat_defect", "재하자 시 기간 재기산",
               _rx(r"재\s*하자", r"보수[^.\n]{0,30}?(?:다시|재)\s*(?:기산|시작)",
                   r"하자[^.\n]{0,30}?재발")),
            _C("defect_bond", "하자보수보증금",
               _rx(r"하자\s*보수\s*보증금", r"하자\s*보증금")),
            # 하자와 무관한 자재 검사비용까지 잡으면 안 된다(2026-09-09 실측).
            _C("diagnosis_cost", "정밀진단·검사 비용",
               _rx(r"하자[^.\n]{0,60}?(?:정밀\s*)?(?:안전\s*)?진단[^.\n]{0,20}?비용",
                   r"(?:정밀|안전)\s*진단[^.\n]{0,40}?비용",
                   r"하자[^.\n]{0,60}?(?:검사|시험)[^.\n]{0,20}?비용"),
               ACTOR_OURS),
        ),
        mitigations=(
            _C("defect_scope_limit", "하자 범위 한정",
               _rx(r"(?:수급인|시공사|공급자)[^.\n]{0,20}?귀책[^.\n]{0,40}?하자",
                   r"하자[^.\n]{0,40}?(?:제외|한정|국한)",
                   r"(?:통상|자연)\s*(?:마모|소모)")),
            _C("defect_period_cap", "기간 상한",
               _rx(r"하자[^.\n]{0,40}?(?:최장|최대)\s*\d+\s*(?:년|개월)",
                   r"\d+\s*년[^.\n]{0,20}?(?:초과하지|넘지)")),
        ),
        why=("하자기간·재하자·보증금·진단비는 하나의 사슬이다. 재하자로 기간이 "
             "재기산되고 보증금이 계속 묶이면 준공 후에도 자본이 회수되지 않는다."),
    ),
    RiskPackage(
        key="no_fault_loss",
        label="무귀책 손해 패키지 (보험 + 무귀책 손해부담 + 위험이전)",
        axes=("insurance", "force_majeure", "third_party_damage"),
        components=(
            _C("no_fault_bearing", "귀책 없는 손해의 부담",
               _rx(r"(?:귀책\s*사유가?\s*없|책임\s*없는|무귀책)[^.\n]{0,60}?"
                   r"(?:부담|책임)",
                   r"(?:천재\s*지변|불가항력)[^.\n]{0,60}?(?:부담|책임)"),
               ACTOR_OURS),
            _C("risk_until_acceptance", "검수·인도 전 위험 부담",
               _rx(r"(?:인도|준공\s*검사|검수)\s*(?:전|시)까지[^.\n]{0,40}?"
                   r"(?:위험|손해|멸실|훼손)",
                   r"(?:멸실|훼손)[^.\n]{0,40}?(?:부담|책임)"),
               ACTOR_OURS),
            _C("insurance_duty", "보험 가입 의무",
               _rx(r"보험[^.\n]{0,30}?(?:가입|부보|체결)"),
               ACTOR_OURS),
            _C("third_party_claim", "제3자 청구·민원 부담",
               _rx(r"제\s*3\s*자[^.\n]{0,40}?(?:청구|손해|민원)"),
               ACTOR_OURS),
        ),
        mitigations=(
            _C("insurance_covers", "보험으로 담보되는 범위",
               _rx(r"보험[^.\n]{0,40}?(?:담보|보상|보전)",
                   r"보험금[^.\n]{0,30}?(?:충당|지급)")),
            _C("fm_relief", "불가항력 면책",
               _rx(r"불가항력[^.\n]{0,60}?(?:면(?:제|책)|책임을\s*(?:지지|부담하지))")),
        ),
        why=("보험 의무만 지우고 무귀책 손해까지 떠안기면, 보험으로 담보되지 않는 "
             "구간이 그대로 우리 손실이 된다. 위험이전 시점과 함께 보아야 한다."),
    ),
    RiskPackage(
        key="scope_change",
        label="범위변경 패키지 (설계변경 + 추가업무 + 비용조정)",
        axes=("design_change", "extra_work"),
        components=(
            _C("change_right", "상대방의 변경 지시권",
               _rx(r"(?:변경|추가)[^.\n]{0,40}?(?:지시|요구)할\s*수\s*있다",
                   r"설계\s*변경[^.\n]{0,40}?(?:요구|지시)"),
               ACTOR_THEIRS),
            _C("extra_work_duty", "추가업무 수행 의무",
               _rx(r"추가\s*(?:공사|업무|작업)[^.\n]{0,40}?(?:수행|이행|시공)",
                   r"(?:요구|지시)[^.\n]{0,30}?(?:응하여야|따라야)")),
            _C("no_price_change", "계약금액 변경 요구 제한",
               _rx(r"계약\s*금액의?\s*변경을?\s*요구(?:하거나|할\s*수)[^.\n]{0,30}?"
                   r"(?:아니\s*된다|없다)",
                   r"(?:증액|추가\s*비용)[^.\n]{0,40}?(?:청구할\s*수\s*없|인정하지)")),
            # 방향을 확인하지 않으면 "공사 중지에 따른 추가 비용은 도급인이
            # 부담한다"를 자기부담으로 보고한다(2026-09-09 실측).
            _C("cost_on_us", "추가비용 자기부담",
               _rx(r"(?:추가|증가|돌관)[^.\n]{0,20}?비용[^.\n]{0,40}?부담",
                   r"비용[^.\n]{0,20}?(?:으로|은|는)\s*(?:시행|수행)"),
               ACTOR_OURS),
        ),
        mitigations=(
            _C("price_adjustment", "계약금액 조정 조항",
               _rx(r"계약\s*금액[^.\n]{0,20}?(?:조정|증감|증액)",
                   r"variation[^.\n]{0,30}?(?:price|adjust)")),
            _C("new_rate", "신규단가 적용",
               _rx(r"신규\s*단가", r"단가[^.\n]{0,20}?(?:적용|산정)")),
            _C("extension_with_change", "변경 시 공기연장",
               _rx(r"변경[^.\n]{0,60}?(?:공사\s*기간|공기)[^.\n]{0,20}?연장")),
        ),
        why=("변경 지시권과 추가업무 의무가 있는데 계약금액 조정이 막혀 있으면, "
             "범위가 늘어나는 만큼 무상 노동이 된다. 세 조항을 함께 보아야 한다."),
    ),
)


def _found(
    components: tuple[PackageComponent, ...],
    text: str,
    *,
    our_role_direction: str = "",
) -> list[dict[str, str]]:
    """구성요소별로 **당사자까지 확인해서** 존재 여부를 판정한다."""
    from runtime.review.risk_allocation_matrix import (
        _BEAR,
        _bearer_hit,
        _sentence_around,
        _side_aliases,
    )

    ours_aliases, their_aliases = _side_aliases(our_role_direction)
    out: list[dict[str, str]] = []
    for comp in components:
        for m in comp.pattern.finditer(text):
            sentence = _sentence_around(text, m.start(), m.end())
            # 당사자 확인은 문장보다 조금 넓게 본다. 한국어 계약은 주체를 항의
            # 첫머리에 한 번만 쓰고 이어지는 문장에서 생략하므로, 문장 안에만
            # 주체가 있다고 요구하면 정상 조항을 놓친다("… “도급인”은 …
            # 위반할 경우 계약을 해제 또는 해지할 수 있다").
            ctx = text[max(0, m.start() - 160): m.end() + 160]
            if comp.actor == ACTOR_OURS:
                # 우리 쪽이 부담자로 지목돼야 하고, 상대방이 더 가깝게
                # 부담자로 지목돼 있으면 방향이 반대인 조항이다.
                ours_hit, _, ours_d = _bearer_hit(sentence, _BEAR, ours_aliases)
                theirs_hit, _, theirs_d = _bearer_hit(sentence, _BEAR, their_aliases)
                if not ours_hit or (theirs_hit and theirs_d < ours_d):
                    continue
            elif comp.actor == ACTOR_THEIRS:
                # 상대방이 권리자·수익자로 지목돼야 한다. 두 당사자가 같은
                # 문장에 등장하는 경우가 많으므로("수급인은 … 도급인에게 배상을
                # 청구할 수 있다"), 어느 쪽이 문형에 더 가까운지로 가린다.
                theirs_hit, _, theirs_d = _bearer_hit(ctx, _RIGHT, their_aliases)
                ours_hit, _, ours_d = _bearer_hit(ctx, _RIGHT, ours_aliases)
                ben_theirs, _, ben_theirs_d = _bearer_hit(ctx, _BENEFIT, their_aliases)
                ben_ours, _, ben_ours_d = _bearer_hit(ctx, _BENEFIT, ours_aliases)
                theirs_best = min(theirs_d if theirs_hit else 1 << 30,
                                  ben_theirs_d if ben_theirs else 1 << 30)
                ours_best = min(ours_d if ours_hit else 1 << 30,
                                ben_ours_d if ben_ours else 1 << 30)
                if theirs_best >= (1 << 30) or ours_best < theirs_best:
                    continue
            out.append({
                "key": comp.key,
                "label": comp.label,
                "evidence": sentence,
            })
            break
    return out


def build_risk_packages(
    text: str,
    matrix: dict[str, Any] | None = None,
    *,
    our_role_direction: str = "",
    contract_type_code: str = "",
) -> list[dict[str, Any]]:
    """패키지별 최대 exposure 판정.

    `matrix` 는 `build_risk_allocation_matrix()` 결과. 넘기지 않으면 여기서
    만든다 — 부담 주체 판정을 두 곳에서 다르게 하지 않으려고 재사용한다.
    """
    from runtime.review.risk_allocation_matrix import (
        SIDE_OURS,
        build_risk_allocation_matrix,
    )

    hay = text or ""
    if matrix is None:
        matrix = build_risk_allocation_matrix(
            hay, our_role_direction=our_role_direction,
            contract_type_code=contract_type_code,
        )
    sides = {r["key"]: r for r in (matrix.get("rows") or [])}

    out: list[dict[str, Any]] = []
    for pkg in RISK_PACKAGES:
        present = _found(pkg.components, hay, our_role_direction=our_role_direction)
        if not present:
            continue  # 이 계약에 이 패키지 자체가 없다
        mitigations = _found(pkg.mitigations, hay,
                             our_role_direction=our_role_direction)
        missing_mitigations = [
            {"key": c.key, "label": c.label}
            for c in pkg.mitigations
            if c.key not in {m["key"] for m in mitigations}
        ]
        axis_rows = [sides[k] for k in pkg.axes if k in sides]
        ours_axes = [r for r in axis_rows if r.get("side") == SIDE_OURS]

        # 노출 강도: 구성요소가 많이 모이고, 그 부담이 우리 쪽이며, 완충장치가
        # 없을수록 크다. 구성요소 수만 세면 흔한 조항이 모여 있는 정상 계약도
        # 전부 걸리므로 "우리 쪽"이라는 조건을 함께 요구한다.
        #
        # 그 조건을 매트릭스 축(ours_axes)만으로 보면 안 된다. 해지 패키지는
        # 구성요소 4/4 가 다 있는데도 축 판정이 termination=미배분,
        # bond_forfeiture=상대방(귀속받는 쪽), damages·setoff=분담 으로 나와
        # LOW 가 됐다(2026-09-09 실측). 구성요소 자체가 이미 당사자를 검증하고
        # 있으므로(ACTOR_OURS / ACTOR_THEIRS) 그 결과도 함께 근거로 쓴다.
        directed = [
            p for p in present
            if _component_actor(pkg, str(p["key"])) in (ACTOR_OURS, ACTOR_THEIRS)
        ]
        on_us = bool(ours_axes) or bool(directed)
        stacked = len(present)
        exposure = "low"
        if stacked >= 3 and on_us and not mitigations:
            exposure = "critical"
        elif stacked >= 3 and on_us:
            exposure = "high"
        elif stacked >= 2 and on_us:
            exposure = "medium"
        elif on_us:
            exposure = "medium"

        out.append({
            "key": pkg.key,
            "label": pkg.label,
            "axes": list(pkg.axes),
            "why": pkg.why,
            "components_present": present,
            "components_present_count": stacked,
            "components_total": len(pkg.components),
            "mitigations_present": mitigations,
            "mitigations_missing": missing_mitigations,
            "axes_on_us": [r.get("label") for r in ours_axes],
            "exposure": exposure,
            "max_exposure_note": _exposure_note(pkg, present, mitigations, ours_axes),
        })
    return out


def _component_actor(pkg: RiskPackage, key: str) -> str:
    for comp in pkg.components:
        if comp.key == key:
            return comp.actor
    return ACTOR_ANY


def _exposure_note(
    pkg: RiskPackage,
    present: list[dict[str, str]],
    mitigations: list[dict[str, str]],
    ours_axes: list[dict[str, Any]],
) -> str:
    parts = [
        f"{pkg.label} — 구성요소 {len(present)}/{len(pkg.components)}개 확인"
        f"({', '.join(p['label'] for p in present)})."
    ]
    if ours_axes:
        parts.append(
            "이 중 " + ", ".join(str(r.get("label")) for r in ours_axes)
            + " 위험이 우리 회사 부담으로 배분되어 있습니다."
        )
    if mitigations:
        parts.append(
            "완충장치: " + ", ".join(m["label"] for m in mitigations) + "."
        )
    else:
        parts.append(
            "완충장치(상한·예외·귀책요건)가 확인되지 않아, 구성요소가 동시에 "
            "발동하면 노출을 계산할 수 없습니다."
        )
    return " ".join(parts)


def attach_packages_to_findings(
    clause_results: list[dict[str, Any]],
    packages: list[dict[str, Any]],
) -> dict[str, Any]:
    """finding 을 패키지에 연결한다.

    같은 법률효과를 조항별로 따로 나열하지 않으려면, 먼저 어느 finding 이
    어느 패키지에 속하는지 표시해 두어야 한다. finding 을 **지우지는 않는다** —
    조항별 수정문안은 그대로 필요하고, 리포트가 묶어서 보여줄 뿐이다.
    """
    by_key = {str(p["key"]): p for p in packages}
    axis_to_pkg: dict[str, str] = {}
    for p in packages:
        for axis in p.get("axes") or []:
            axis_to_pkg.setdefault(str(axis), str(p["key"]))

    grouped: dict[str, list[str]] = {k: [] for k in by_key}
    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        blob = " ".join(
            str(cr.get(f) or "")
            for f in ("title", "issue", "legal_business_reason", "risk_note",
                      "original_text")
        )
        hit: str | None = None
        for pkg in RISK_PACKAGES:
            if str(pkg.key) not in by_key:
                continue
            if any(c.pattern.search(blob) for c in pkg.components):
                hit = str(pkg.key)
                break
        if hit:
            cr["risk_package"] = hit
            cr["risk_package_label"] = str(by_key[hit].get("label") or "")
            grouped[hit].append(str(cr.get("clause_id") or ""))

    return {
        "assignments": {k: v for k, v in grouped.items() if v},
        "unassigned_count": sum(
            1 for cr in clause_results
            if isinstance(cr, dict) and not cr.get("risk_package")
        ),
        "axis_to_package": axis_to_pkg,
    }
