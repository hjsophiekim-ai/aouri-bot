"""판매/위탁판매/대리판매/중개/판매지원 계약의 거래구조 모호성 탐지.

범용 사내변호사형 검토 엔진 전면 보정(2026-09-04 지시, 그림닷컴 판매지원
용역계약 실사례) — 계약 제목이나 contract_type/contract_class 분류 결과에
의존하지 않고, 계약 본문 자체에서 "판매·위탁판매·대리판매·중개·판매지원"
성격의 거래 신호가 있는지, 있다면 판매자·소유권 같은 핵심 사실관계가 계약
문언 자체에서 이미 확정되어 있는지를 독립적으로 판단한다.

이 신호는 contract_class 분류가 틀려도(예: 그림닷컴 사례처럼 "advisory"로
오분류) 그와 무관하게 동작해야 한다 — 분류 오류를 자동으로 보완하는
안전망이기 때문이다.

── 2026-09-10 보정 (대물교환 계약 오탐) ────────────────────────────────────
종전 구현은 본문 어디든 `판매|매매|중개|…` 가 한 번, `고객|소비자|구매자` 가
한 번 나오면 곧바로 True 를 돌려주었다. 그 결과 "콘텐츠 제작 대가로 가구를
공급하는 대물교환(바터) 계약"에서

  · 제9조 제5항 "제3자에게 **판매**, 양도, 대여, 담보제공하거나" (금지 문언)
  · 표지 "**소비자가** 기준 일금 [ ]원"                          (가격 기준 표현)

두 군데가 걸려 위탁매매 사전질문 9개가 통째로 주입됐다. 매매도 고객도 재고도
없는 계약이었다. 그래서 판정을 세 가지로 조인다.

1. **금지·제한 열거 안의 "판매"는 거래구조 신호가 아니다.** "판매·양도·대여·
   담보제공" 처럼 처분행위를 나열해 금지하는 문맥은 제외한다.
2. **"소비자가(消費者價)"는 고객 신호가 아니다.** 가격 기준을 가리키는
   표현이므로 거래 상대방으로 세지 않는다.
3. **신호 하나로는 부족하다.** 이 계약의 급부 구조가 실제로 판매인지를
   보여주는 **운영 신호**(판매수수료·판매대금·매출 귀속·재고·반품·POS·
   위탁판매 등)가 최소 하나는 있어야 한다. 단순히 "판매"라는 단어가 스치는
   것만으로는 묻지 않는다.

추가로 대물교환·바터처럼 **금전 대가 자체가 없는** 구조가 명시된 계약은
매매 거래구조 질문의 대상이 아니므로 즉시 False 를 돌려준다.
"""
from __future__ import annotations

import re

# ── 거래구조가 "판매"임을 드러내는 운영 신호 ────────────────────────────────
# 단어가 스치는 것이 아니라, 판매 거래를 실제로 굴리는 장치들이다.
_RX_OPERATIVE_SALES_SIGNAL = re.compile(
    r"위탁판매|수탁판매|대리판매|판매대리|판매지원|영업지원|판매위탁"
    r"|판매수수료|판매장려금|판매대금|판매가격|판매단가|판매실적|판매목표"
    r"|재판매|매입.{0,10}판매|사입|반품|재고|진열|POS|포스\s*단말"
    r"|매출\s*(?:귀속|인식|정산)|정산\s*(?:주기|방식|대금)"
    r"|고객에게\s*판매|소비자에게\s*판매|최종\s*판매",
    re.IGNORECASE,
)

# ── 약한 신호(단어만) ──────────────────────────────────────────────────────
_RX_WEAK_SALES_SIGNAL = re.compile(r"판매|매매|중개|매도인|매수인", re.IGNORECASE)

# "판매"가 처분행위 금지 열거 안에 있는 경우 — 거래구조가 아니라 제한 문언이다.
# 예: "제3자에게 판매, 양도, 대여, 담보제공하거나", "매도, 양도, 담보제공, 임대"
_RX_DISPOSAL_PROHIBITION = re.compile(
    r"(?:판매|매도)\s*[,·]\s*(?:양도|대여|임대|담보|처분|이전)"
    r"|(?:양도|대여|임대|담보제공|처분)\s*[,·]\s*(?:판매|매도)",
)

# 고객 신호. "소비자가"(가격 기준)는 제외한다.
_RX_CUSTOMER_SIGNAL = re.compile(r"고객|구매자|소비자(?!가\s*(?:기준|격))", re.IGNORECASE)
_RX_PAYMENT_CHANNEL_SIGNAL = re.compile(
    r"결제|POS|포스|판매수수료|용역수수료|대금\s*수령",
    re.IGNORECASE,
)

# 금전 대가가 없는 교환 구조 — 매매 거래구조 질문의 대상이 아니다.
_RX_NON_MONETARY_EXCHANGE = re.compile(
    r"대물교환|물물교환|바터|barter|현물\s*교환"
    r"|현금\s*(?:지급|대가)(?:가|이)?\s*없[는다]"
    r"|별도의\s*현금\s*대가를\s*지급하지\s*아니",
    re.IGNORECASE,
)

# 계약 문언 자체가 이미 판매자·소유권을 명시적으로 확정하고 있다는 신호 —
# 이런 문장이 있으면 더 이상 물을 필요가 없다.
_RX_SELLER_ALREADY_RESOLVED = re.compile(
    r"판매자는\s*[\S ]{0,20}(?:이다|로\s*한다)"
    r"|매도인은\s*[\S ]{0,20}(?:이다|로\s*한다)"
    r"|(?:갑|을)(?:이|가)\s*(?:매입|구매)하여?\s*(?:재판매|다시\s*판매)"
    r"|고객과의?\s*매매계약(?:상)?\s*당사자는\s*[\S ]{0,20}(?:이다|로\s*한다)",
    re.IGNORECASE,
)
_RX_OWNERSHIP_ALREADY_RESOLVED = re.compile(
    r"소유권은\s*[\S ]{0,20}(?:에게\s*있다|에\s*귀속)"
    r"|소유권(?:은|이)\s*[\S ]{0,20}(?:이전|귀속)",
    re.IGNORECASE,
)


def _strip_disposal_prohibitions(text: str) -> str:
    """처분행위 금지 열거를 지운 본문. 거래구조 판정에서만 쓴다."""
    return _RX_DISPOSAL_PROHIBITION.sub(" ", text or "")


def detect_sales_transaction_ambiguity(text: str) -> bool:
    """판매/위탁판매/대리판매/중개/판매지원 성격의 **거래구조**가 실재하는데
    판매자·소유권이 계약 문언 자체에서 확정되어 있지 않으면 True.

    contract_type_code/contract_class 와 무관하게 순수 텍스트 신호로만
    판단한다(분류 오류에 대한 안전망 역할).
    """
    t = text or ""
    if not t.strip():
        return False

    # 금전 대가가 오가지 않는 교환 구조는 매매 거래구조 질문의 대상이 아니다.
    if _RX_NON_MONETARY_EXCHANGE.search(t):
        return False

    scan = _strip_disposal_prohibitions(t)

    has_operative_signal = bool(_RX_OPERATIVE_SALES_SIGNAL.search(scan))
    if not has_operative_signal:
        # 운영 신호가 하나도 없으면, "판매"라는 단어가 몇 번 스쳐도 이 계약의
        # 급부 구조가 판매라고 볼 근거가 없다.
        return False

    has_weak_signal = bool(_RX_WEAK_SALES_SIGNAL.search(scan))
    has_customer_signal = bool(_RX_CUSTOMER_SIGNAL.search(scan))
    has_payment_channel_signal = bool(_RX_PAYMENT_CHANNEL_SIGNAL.search(scan))
    if not (has_weak_signal and (has_customer_signal or has_payment_channel_signal)):
        return False

    already_resolved = bool(_RX_SELLER_ALREADY_RESOLVED.search(t)) and bool(_RX_OWNERSHIP_ALREADY_RESOLVED.search(t))
    return not already_resolved
