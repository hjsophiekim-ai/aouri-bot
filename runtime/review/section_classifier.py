"""Section classifier for dealer_rental_service_contract.

Classifies contract text regions as:
  main_contract          — 대리점계약서 본문 (대리점↔공급업자 조항)
  customer_contract_form — 고객용 렌탈계약서 양식 (별첨/첨부)
  appendix               — 별첨/부속서류
  unknown                — 판단 불가
"""
from __future__ import annotations

import re

_MAIN_SIGNALS = re.compile(
    r"공급업자와\s*대리점|대리점은\s+공급업자로부터|용역수수료|케어운영\s*수수료|"
    r"안정운영\s*수수료|거래보증금|오피스케어|위탁판매\s*대리점|위탁\s*수수료|"
    r"대리점\s+계약|대리점이\s+공급업자에게|위탁\s*대리점\s*계약|공급업자와\s*최종\s*소비자",
    re.IGNORECASE,
)

_CUSTOMER_FORM_SIGNALS = re.compile(
    r"퍼시스와\s*고객|고객은\s*퍼시스와|계약물품\s*및\s*금액|렌탈료\s*산정|"
    r"설치장소|고객용\s*렌탈|별도\s*작성|첨부\s*양식|별첨\s*[1-9]|"
    r"부속서|[Aa]ppendix|[Ee]xhibit|고객과\s+퍼시스|임차인|임대인",
    re.IGNORECASE,
)

_APPENDIX_SIGNALS = re.compile(
    r"별첨\s*\d|부속\s*서류|첨부\s*\d|[Aa]ppendix\s*\d|[Ee]xhibit\s*\d|"
    r"별지\s*\d|붙임\s*\d",
    re.IGNORECASE,
)

# Section boundary markers — when these appear in text, everything after may be customer form
_FORM_BOUNDARY_MARKERS = re.compile(
    r"(별첨\s*\d|첨부\s*\d|부속서\s*\d|고객\s*렌탈계약서|"
    r"임차인\s*서명|임대인\s*서명|고객용\s*계약서)",
    re.IGNORECASE,
)


def detect_section_type(text_window: str) -> str:
    t = str(text_window or "")
    if _APPENDIX_SIGNALS.search(t):
        return "appendix"
    if _CUSTOMER_FORM_SIGNALS.search(t):
        return "customer_contract_form"
    if _MAIN_SIGNALS.search(t):
        return "main_contract"
    return "unknown"


def split_main_and_customer_form(full_text: str) -> dict:
    """Split contract text into main_contract and customer_contract_form regions.

    Returns:
        {
          'main_contract': str,       # 대리점계약서 본문
          'customer_form': str,       # 고객용 렌탈계약서 양식
          'appendix': str,            # 기타 별첨
          'boundary_pos': int,        # 분리 시작 위치 (-1 = no split)
          'has_customer_form': bool,
        }
    """
    text = full_text or ""
    boundary = _FORM_BOUNDARY_MARKERS.search(text)
    if boundary:
        split_pos = boundary.start()
        main_part = text[:split_pos].strip()
        rest = text[split_pos:].strip()

        # Check rest for customer form signals
        if _CUSTOMER_FORM_SIGNALS.search(rest):
            return {
                "main_contract": main_part,
                "customer_form": rest,
                "appendix": "",
                "boundary_pos": split_pos,
                "has_customer_form": True,
            }
        if _APPENDIX_SIGNALS.search(rest):
            return {
                "main_contract": main_part,
                "customer_form": "",
                "appendix": rest,
                "boundary_pos": split_pos,
                "has_customer_form": False,
            }

    # No split found — entire text is main contract
    return {
        "main_contract": text,
        "customer_form": "",
        "appendix": "",
        "boundary_pos": -1,
        "has_customer_form": False,
    }


def is_main_contract_text(text: str) -> bool:
    return _MAIN_SIGNALS.search(text or "") is not None


def classify_article_section(article_text: str, context_before: str = "") -> str:
    """Classify a single article as main_contract / customer_contract_form / appendix."""
    combined = (context_before or "") + "\n" + (article_text or "")
    return detect_section_type(combined)
