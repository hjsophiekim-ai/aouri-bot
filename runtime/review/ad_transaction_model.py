"""광고계약의 **거래구조**를 먼저 가른다 — 누가 콘텐츠를 만들고 누가 송출만 하는가.

2026-09-15 지시 —
  "광고계약이라는 큰 분류만 보고 질문하지 말고, 실제로 누가 콘텐츠를 만들고
   누가 송출만 하는지를 먼저 구분한 뒤 사전질문과 검토항목을 생성할 것."

실측 (타운보드 광고 계약, 일룸–매체사)
──────────────────────────────────
사용자는 검토 요청에 이렇게 적었다.

    "엘레베이터 내 미디어 광고 집행을 위탁하기 위한 계약서입니다."

계약서도 같은 말을 한다 — 매체사는 "고객이 전달한 컨텐츠를 송출" 하고, 콘텐츠
제작비용은 **고객이** 부담한다. 그런데 사전질문에 이것이 나갔다.

    Q-EFF-ip-scope
    "이 계약으로 취득하는 지식재산을 앞으로 어디까지 활용할 계획인가요?
     (매체·기간·지역·**재가공** 포함 여부)"

취득하는 지식재산이 없다. 상대방은 아무것도 만들지 않는다. 2차적저작물작성권·
저작인격권·chain of title 은 **콘텐츠 제작계약**의 논점이지 매체 집행계약의
논점이 아니다. 담당자는 계약과 무관한 질문에 답을 지어내야 했다.

세 가지 거래구조
───────────────
    광고매체 집행형  광고주가 완성된 광고물을 주고, 상대방은 송출·게재만 한다.
                     (엘리베이터·옥외·디지털 사이니지·지면)
    콘텐츠 제작형    상대방 또는 크리에이터가 광고 콘텐츠를 직접 만든다.
    혼합형           제작과 집행을 모두 한다.

판단의 축은 **누가 콘텐츠를 만드는가** 하나다. 매체 어휘가 많다고 집행형이
되는 것이 아니라(제작형 계약도 매체를 말한다), 제작 주체가 상대방이 아닐 때
집행형이다.

설계 원칙
────────
· 사용자 설명과 계약 원문을 **함께** 본다. 둘이 같은 방향이면 확신(`confident`),
  엇갈리면 확신하지 않고 아무것도 끄지 않는다 — 모르는 상태에서 질문을 지우면
  물어야 할 것을 못 묻는다.
· 회사명·계약명을 하드코딩하지 않는다. "타운보드" 는 매체 이름의 한 예일 뿐이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

AD_MEDIA_PLACEMENT = "ad_media_placement"
AD_CONTENT_PRODUCTION = "ad_content_production"
AD_HYBRID = "ad_hybrid"
AD_NOT_ADVERTISING = "not_advertising"
AD_UNCERTAIN = "ad_uncertain"

MODEL_LABELS: dict[str, str] = {
    AD_MEDIA_PLACEMENT: "광고매체 집행형 (상대방은 송출·게재만 수행)",
    AD_CONTENT_PRODUCTION: "콘텐츠 제작형 (상대방·크리에이터가 콘텐츠 제작)",
    AD_HYBRID: "혼합형 (콘텐츠 제작 + 매체 집행)",
    AD_NOT_ADVERTISING: "광고계약 아님",
    AD_UNCERTAIN: "광고계약이나 거래구조 미확정",
}

REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH = "REVIEW_FAILED_TRANSACTION_MODEL_MISMATCH"

#: 거래모델 → **canonical contract_type 코드**.
#:
#: 2026-09-16 지시 1항 — "canonical transaction model 을 하나만 확정하고, 이후
#: 사전질문·finding·rewrite·UI·DOCX 모두 그 값을 사용하세요."
#:
#: 실측(v11 이후에도 남아 있던 자기모순): 거래모델은 `ad_media_placement`
#: (confident) 로 확정됐는데 canonical 계약유형은 여전히
#: `advertising_content_production`("제품 광고 콘텐츠 제작 대행 계약")이었다.
#: 리포트 상단은 "제작 대행", 본문 검토는 "송출만 한다" 였고, 최종 자가점검은
#: 룰 분류기의 `contract_type_resolution`(미확정)을 보고 blocking 실패했다.
#: 거래모델이 확정됐으면 **그것이 계약유형이다**. 한 곳에서만 정한다.
#:
#: 혼합형·제작형은 제작계약 코드를 그대로 쓴다 — 아무것도 끄지 않기 위함이다.
MODEL_TO_CONTRACT_TYPE: dict[str, str] = {
    AD_MEDIA_PLACEMENT: "advertising_media_placement",
    AD_CONTENT_PRODUCTION: "advertising_content_production",
    AD_HYBRID: "advertising_content_production",
}

#: 집행형 canonical 코드. 이 문자열을 다른 모듈이 직접 쓰지 않게 여기서 내보낸다.
AD_MEDIA_PLACEMENT_TYPE_CODE = MODEL_TO_CONTRACT_TYPE[AD_MEDIA_PLACEMENT]


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: 이 계약이 광고 거래인가.
_RX_ADVERTISING = _rx(
    r"광고|advertis|캠페인\s*집행|매체\s*집행|홍보\s*콘텐츠"
)

#: 매체에 **싣는** 행위. 집행형의 핵심 급부다.
_RX_MEDIA_ACT = _rx(
    r"송출|표출|게재|게첩|노출|방영|상영|게시|디스플레이|전광판|사이니지"
    r"|옥외\s*광고|지면\s*광고|매체\s*(?:위치|수량|운영|사)|광고\s*매체"
    r"|엘리베이터|타운보드|스크린\s*도어"
)

#: 매체 집행 계약에서만 나오는 운영 어휘.
_RX_MEDIA_OPS = _rx(
    r"송출\s*(?:횟수|시간|실적|스케줄)|광고\s*기간|광고료|매체\s*사|심의"
    r"|민원|장애|중단|표출\s*불가"
)

#: **광고주가** 광고물을 준다 — 집행형의 결정적 신호.
_RX_ADVERTISER_SUPPLIES = _rx(
    r"(?:고객|광고주|갑|제휴사|위탁자)[^.\n]{0,60}"
    r"(?:컨텐츠|콘텐츠|광고물|광고\s*소재|시안|소재)[^.\n]{0,30}"
    r"(?:전달|제공|입고|송부|제출)"
    r"|(?:컨텐츠|콘텐츠|광고물|광고\s*소재|시안)[^.\n]{0,40}"
    r"(?:고객|광고주|갑|제휴사)[^.\n]{0,20}(?:전달|제공|입고|제작)"
    r"|고객이\s*전달한\s*(?:컨텐츠|콘텐츠)"
)

#: **상대방이** 콘텐츠를 만든다 — 제작형의 결정적 신호.
_RX_COUNTERPARTY_PRODUCES = _rx(
    r"크리에이터|인플루언서|제작사|촬영\s*원본|편집\s*파일|편집본"
    r"|(?:콘텐츠|영상|광고물|시안)[^.\n]{0,20}(?:제작|기획|촬영|편집)"
    r"[^.\n]{0,20}(?:위탁|의뢰|수행|담당|납품|납품물)"
    r"|(?:을|수급인|수탁자|대행사)[^.\n]{0,40}(?:콘텐츠|영상)[^.\n]{0,10}제작"
    r"|제작\s*(?:대금|용역|일정|단계)|산출물\s*(?:인도|납품)"
)

#: 제작형에서만 성립하는 권리 어휘(상대방이 만든 것을 우리가 가져오는 구조).
_RX_PRODUCTION_RIGHTS = _rx(
    r"2차적저작물|저작인격권|저작재산권[^.\n]{0,20}(?:양도|이전|귀속)"
    r"|결과물[^.\n]{0,15}(?:권리|귀속)|산출물[^.\n]{0,15}(?:권리|귀속)"
)

#: 사용자 설명에서 읽는 신호.
_RX_USER_MEDIA = _rx(
    r"광고\s*집행|매체\s*집행|송출|게재|노출|옥외|엘리베이터|타운보드"
    r"|사이니지|전광판|지면\s*광고|광고를?\s*(?:싣|실어|건다|게시)"
)
_RX_USER_PRODUCTION = _rx(
    r"콘텐츠\s*제작|영상\s*제작|광고\s*제작|크리에이터|인플루언서|촬영|편집"
    r"|제작\s*대행|시안"
)


@dataclass
class AdTransactionModel:
    """광고계약 거래구조 판정 하나."""

    model: str = AD_NOT_ADVERTISING
    confident: bool = False
    basis: str = ""
    text_signals: dict[str, int] = field(default_factory=dict)
    user_signal: str = ""

    @property
    def is_media_placement(self) -> bool:
        return self.model == AD_MEDIA_PLACEMENT

    @property
    def counterparty_produces_content(self) -> bool:
        """상대방이 콘텐츠를 만드는 구조인가 — 제작계약용 논점의 성립 요건."""
        return self.model in (AD_CONTENT_PRODUCTION, AD_HYBRID)

    @property
    def label(self) -> str:
        return MODEL_LABELS.get(self.model, self.model)

    @property
    def canonical_contract_type(self) -> str:
        """이 거래모델이 확정하는 canonical 계약유형 코드.

        확신하지 못하면 빈 문자열이다 — 모르는 상태에서 유형을 덮어쓰면
        틀린 유형의 체크리스트를 주입하게 된다. 아무것도 확정하지 않는 편이
        안전하다는 원칙(v10)을 여기서도 그대로 지킨다.
        """
        if not self.confident:
            return ""
        return MODEL_TO_CONTRACT_TYPE.get(self.model, "")

    @property
    def is_settled(self) -> bool:
        """거래모델이 하나로 확정됐는가 — "유형 미확정" 과 양립할 수 없는 상태."""
        return bool(self.canonical_contract_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "label": self.label,
            "confident": self.confident,
            "basis": self.basis,
            "text_signals": dict(self.text_signals),
            "user_signal": self.user_signal,
            "counterparty_produces_content": self.counterparty_produces_content,
            "canonical_contract_type": self.canonical_contract_type,
            "settled": self.is_settled,
        }


def _count(pattern: re.Pattern[str], text: str) -> int:
    return len(pattern.findall(text or ""))


def classify_ad_transaction_model(
    *,
    contract_text: str,
    user_description: str = "",
    contract_type_code: str = "",
) -> AdTransactionModel:
    """광고계약의 거래구조를 가른다.

    광고 거래가 아니면 `AD_NOT_ADVERTISING` 을 돌려주고 이후 게이트는 아무것도
    하지 않는다 — 광고가 아닌 계약에 이 판단을 적용할 이유가 없다.
    """
    body = str(contract_text or "")
    desc = str(user_description or "")

    if not (_RX_ADVERTISING.search(body) or _RX_ADVERTISING.search(desc)
            or "advertis" in str(contract_type_code or "").lower()):
        return AdTransactionModel(model=AD_NOT_ADVERTISING, basis="광고 거래 신호 없음")

    signals = {
        "media_act": _count(_RX_MEDIA_ACT, body),
        "media_ops": _count(_RX_MEDIA_OPS, body),
        "advertiser_supplies": _count(_RX_ADVERTISER_SUPPLIES, body),
        "counterparty_produces": _count(_RX_COUNTERPARTY_PRODUCES, body),
        "production_rights": _count(_RX_PRODUCTION_RIGHTS, body),
    }

    user_media = bool(_RX_USER_MEDIA.search(desc))
    user_production = bool(_RX_USER_PRODUCTION.search(desc))
    if user_media and not user_production:
        user_signal = AD_MEDIA_PLACEMENT
    elif user_production and not user_media:
        user_signal = AD_CONTENT_PRODUCTION
    elif user_media and user_production:
        user_signal = AD_HYBRID
    else:
        user_signal = ""

    # 계약 원문의 판정 — 축은 "상대방이 만드는가" 하나다.
    produces = signals["counterparty_produces"] + signals["production_rights"]
    places = signals["media_act"] + signals["media_ops"]
    supplies = signals["advertiser_supplies"]

    # 혼합형은 **양쪽 다 뚜렷할 때만**. 매체 어휘 한두 개는 제작형 계약에도
    # 흔히 나오므로(콘텐츠를 어디에 올릴지 적는다) 그것만으로 혼합형이라고
    # 하면 제작형이 전부 혼합형으로 흘러 아무 게이트도 못 건다.
    if produces >= 2 and places >= 3:
        text_model = AD_HYBRID
    elif produces >= 2 and produces > places:
        text_model = AD_CONTENT_PRODUCTION
    elif places >= 2 and (supplies or produces == 0):
        text_model = AD_MEDIA_PLACEMENT
    elif produces:
        text_model = AD_CONTENT_PRODUCTION
    else:
        text_model = AD_UNCERTAIN

    # 광고주가 소재를 준다는 문언이 있으면 제작형일 수 없다 — 그것이 집행형의
    # 정의다. 제작 어휘가 섞여 있어도(제작비용 부담 조항 등) 이쪽이 우선한다.
    if supplies and text_model == AD_CONTENT_PRODUCTION and produces < 3:
        text_model = AD_MEDIA_PLACEMENT

    if not user_signal:
        model = text_model
        confident = text_model in (AD_MEDIA_PLACEMENT, AD_CONTENT_PRODUCTION, AD_HYBRID) and (
            places >= 3 or produces >= 3
        )
        basis = f"계약 원문 신호만으로 판정({text_model})."
    elif text_model in (AD_UNCERTAIN, user_signal):
        model = user_signal
        confident = True
        basis = "사용자 설명과 계약 원문이 같은 거래구조를 가리킵니다."
    else:
        # 엇갈리면 확신하지 않는다. 더 넓은 쪽(혼합형)으로 두어 아무것도 끄지 않는다.
        model = AD_HYBRID
        confident = False
        basis = (
            f"사용자 설명({MODEL_LABELS.get(user_signal, user_signal)})과 계약 원문"
            f"({MODEL_LABELS.get(text_model, text_model)}) 판정이 달라 혼합형으로 보수적으로 둡니다."
        )

    return AdTransactionModel(
        model=model, confident=confident, basis=basis,
        text_signals=signals, user_signal=user_signal,
    )


# ── canonical 해석: 거래모델을 한 번만 정한다 ────────────────────────────────

def _answers_to_text(answers: Any) -> str:
    """사용자 답변에서 거래구조 신호가 될 수 있는 **값만** 모은다.

    답변은 `{question_id: value}` 또는 `[{"question_id": …, "answer": …}]` 로
    들어온다. 어느 쪽이든 값만 이어 붙이고 **질문 문구는 넣지 않는다** —
    질문 템플릿이 만든 낱말("2차 활용", "결과물 저작권", "성적서")이 사용자
    설명으로 둔갑해 거래구조 판정을 뒤집는 일을 막기 위함이다(지시 4항).
    """
    if not answers:
        return ""
    vals: list[str] = []
    if isinstance(answers, dict):
        vals = [str(v) for v in answers.values() if isinstance(v, (str, int, float))]
    elif isinstance(answers, list):
        for row in answers:
            if isinstance(row, dict):
                for key in ("answer", "value", "text", "answer_text"):
                    v = row.get(key)
                    if isinstance(v, (str, int, float)) and str(v).strip():
                        vals.append(str(v))
                        break
            elif isinstance(row, str):
                vals.append(row)
    return "\n".join(vals)


def resolve_ad_transaction_model(
    *,
    contract_text: str,
    user_description: str = "",
    contract_type_code: str = "",
    answers: Any = None,
) -> AdTransactionModel:
    """거래모델의 **단일 확정 지점**.

    2026-09-16 지시 1항 — "사용자 설명과 계약 원문을 모두 반영해 canonical
    transaction model 을 하나만 확정하고, 이후 사전질문·finding·rewrite·UI·
    DOCX 모두 그 값을 사용하세요."

    사전질문 생성기와 검토 파이프라인이 각자 `classify_…()` 를 부르면 입력이
    조금만 달라도 서로 다른 모델을 들고 일하게 된다 — 질문은 집행형으로
    나가고 finding 은 제작형으로 생성되는 상태다. 두 경로 모두 이 함수만
    부른다.

    답변까지 받은 뒤 다시 부르면 그 답변이 사용자 설명에 더해진 채로
    재확정된다. 검토 시점의 판정이 질문 시점의 판정을 덮어쓰는 것이 맞다 —
    담당자가 "상대방이 영상도 만든다" 고 답했으면 그때부터 혼합형이다.
    """
    desc = "\n".join(
        x for x in (str(user_description or ""), _answers_to_text(answers)) if x.strip()
    )
    return classify_ad_transaction_model(
        contract_text=contract_text,
        user_description=desc,
        contract_type_code=contract_type_code,
    )


# ── 제작계약용 finding 비활성화 ──────────────────────────────────────────────

#: 상대방이 콘텐츠를 만들 때만 성립하는 논점. 집행형에서는 근거 자체가 없다.
_RX_PRODUCTION_ONLY_FINDING = _rx(
    r"2차적저작물|2차\s*활용|2차\s*저작물|저작인격권|chain\s*of\s*title"
    r"|저작(?:재산)?권[^.\n]{0,20}(?:양도|이전|귀속|확보)"
    r"|창작자[^.\n]{0,20}(?:권리|확약|동의)"
    r"|결과물[^.\n]{0,15}(?:권리|저작권|이전|귀속)"
    r"|산출물[^.\n]{0,15}(?:인도|권리|귀속)"
    # [2026-09-16 지시 4항] 집행형 계약에 없는 산출물·의무를 만들어 내던 말들.
    # "제3자 소재 라이선스 확보 의무" 는 상대방이 소재를 조달해 만들 때만
    # 성립한다. 우리가 완성된 광고물을 주는 구조에서는 상대방에게 지울 의무가
    # 아니다 — 우리 쪽 책임 문제는 `_RX_SUPPLIED_CONTENT_LIABILITY` 가 남긴다.
    r"|(?:제3자|타인)\s*(?:소재|저작물|콘텐츠|권리)[^.\n]{0,25}"
    r"(?:라이선스|이용허락|사용권|권리처리)[^.\n]{0,20}(?:확보|취득|입수|처리)"
    r"|(?:폰트|음원|스톡\s*이미지|BGM)[^.\n]{0,20}(?:라이선스|이용허락)[^.\n]{0,20}(?:확보|취득)"
    r"|초상권[^.\n]{0,20}(?:이용허락(?:서)?|동의서)[^.\n]{0,20}(?:확보|징구|제출)"
    r"|모델\s*(?:계약|섭외|출연\s*동의)"
    r"|시안[^.\n]{0,15}(?:검수|확정|승인)|수정\s*요청\s*횟수"
    r"|포트폴리오[^.\n]{0,15}(?:활용|게재)"
)

#: 다만 **광고주가 제공한 콘텐츠에 대한 책임** 은 집행형의 진짜 논점이다.
#: 지식재산 어휘가 들어 있어도 이쪽이면 끄지 않는다.
#: 종전에는 `면책` 한 낱말만 있어도 예외로 빠져나갔다. 제작계약용 리스크 사슬
#: finding 이 설명 중에 "면책" 을 쓰는 것만으로 살아남아, 집행형 계약에서
#: "창작자 → 2차적저작물작성권 → 저작인격권" 논점이 유일한 HIGH 로 남았다.
#: 이 예외는 **광고주가 제공한 콘텐츠의 책임** 을 다루는 항목만을 위한 것이다.
_RX_SUPPLIED_CONTENT_LIABILITY = _rx(
    r"(?:고객|광고주|갑|제휴사)[^.\n]{0,40}(?:제공|전달)[^.\n]{0,30}"
    r"(?:컨텐츠|콘텐츠|광고물|소재)"
    r"|제공한?\s*(?:광고\s*)?(?:컨텐츠|콘텐츠|광고물|소재)[^.\n]{0,40}(?:책임|적법|위법|침해)"
)


#: 이 필드들이 finding 의 "말" 이다. 여러 곳에서 같은 목록을 쓰므로 한 번만 적는다.
FINDING_TEXT_FIELDS: tuple[str, ...] = (
    "issue_title", "clause_title", "problem", "rewrite_reason",
    "legal_business_reason", "suggested_rewrite", "recommendation_text",
)


def finding_blob(cr: dict[str, Any]) -> str:
    """finding 이 담당자에게 실제로 말하는 내용 전부."""
    return "\n".join(str(cr.get(k) or "") for k in FINDING_TEXT_FIELDS)


def is_production_only_finding(blob: str) -> bool:
    """이 문장이 **상대방이 콘텐츠를 만들 때만** 성립하는 논점인가.

    광고주가 제공한 콘텐츠의 책임 범위를 다루는 항목은 제외한다 — 그것은
    집행형의 진짜 논점이다(지시 5항).
    """
    body = str(blob or "")
    if not _RX_PRODUCTION_ONLY_FINDING.search(body):
        return False
    return not _RX_SUPPLIED_CONTENT_LIABILITY.search(body)


def deactivate_production_only_findings(
    clause_results: list[dict[str, Any]],
    model: AdTransactionModel,
) -> list[dict[str, Any]]:
    """집행형 계약에서 콘텐츠 제작계약용 finding 을 끈다.

    상대방이 아무것도 만들지 않는 계약에서 "2차적저작물작성권을 확보하라",
    "창작자 저작인격권 불행사 확약을 받아라" 는 성립하지 않는다. 확신할 수
    있을 때만 끈다(`confident`) — 구조를 확신하지 못한 상태에서 지우면 물어야
    할 것을 못 묻는 것과 같은 실패다.
    """
    if not (model.is_media_placement and model.confident):
        return []

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for cr in clause_results:
        if not isinstance(cr, dict):
            kept.append(cr)
            continue
        # 집행형 체크리스트가 스스로 만든 항목은 대상이 아니다 — 그 항목들이
        # 바로 "이 거래구조에서 무엇을 볼 것인가" 의 답이다(제공 콘텐츠 책임
        # carve-out 문안이 "초상권" 한 낱말로 지워지던 v11 실측).
        if bool(cr.get("is_ad_media_checklist")):
            kept.append(cr)
            continue
        if not is_production_only_finding(finding_blob(cr)):
            kept.append(cr)
            continue
        removed.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "issue_title": str(cr.get("issue_title") or "")[:90],
            "reason": "광고매체 집행형 계약이라 상대방이 콘텐츠를 제작하지 않습니다 — "
                      "제작계약용 권리 논점은 성립하지 않습니다.",
        })
    clause_results[:] = kept
    return removed
