"""Final Senior Counsel Audit — 출력 직전에 결과 전체를 사내변호사 눈으로 다시 본다.

2026-09-30 지시 (범용 계약검토 최종보정)
────────────────────────────────────
"법률 이슈를 많이 찾는 AI 가 아니라, 정확한 조항번호와 실제 계약문언에 근거해
우리 회사에 실질적으로 중요한 위험만 골라내는 엔진."

실측(한글날 3자 아트상품 협업계약, 실제 AI 검토) — 출력 40건(HIGH 5·MEDIUM 6·LOW 29):
  · "제31조 신설 — 지연 시 연 6% 이자" : 우리가 지급자인데 지연이자 의무를 새로
    만들고, 지급 조항(제12조)이 있는데도 "신설"로 냈다.
  · 제24조 제2항(책임 조항)에 "해지권 과도 제한" finding, 수정문은 이 계약에
    없는 "위탁자"를 주어로 썼다.
  · 세금계산서 발행 시기(정산 실무)가 HIGH, 같은 VAT 쟁점이 제8조·제12조에 둘.
  · IP 이용권 쟁점이 제9조 제3항·제10조 제4항·제10조 제8항으로 쪼개짐.
  · 조항 없는 "[권고] 선급금 보증 구조" 등 체크리스트 5건, 같은 제목 LOW 4건.

각 단계는 앞 게이트들이 이미 한 일을 되풀이하지 않는다 — 존재 검증(v10)·인용
위치(v15)·중복 통합(v15)·KEEP(v16)이 끝난 결과를 받아, 거기서 빠지는 것만 본다.

  1. grounding       조·항이 없는 finding 을 실제 조항에 붙이거나, 못 붙이면 내보내지 않는다
  2. semantic        finding 주제가 붙은 조항의 문언에 전혀 없으면 내보내지 않는다
  3. redline         우리에게 불리한 수정안·계약에 없는 당사자 명사·깨진 문구·no-op
  4. materiality     관할·준거법 boilerplate 강등, 선급금 보증 자동요구 금지, HIGH 문턱
  5. package         같은 주제의 HIGH/MEDIUM 은 대표 하나 + 하위 쟁점으로 통합
  6. count           HIGH·MEDIUM 각 5건 상한, 같은 제목 LOW 통합

모든 조치는 `meta["senior_counsel_audit"]["actions"]` 에 남긴다(제거·기록 후 전달).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

STATUS_CLAUSE_GROUNDING = "REVIEW_FAILED_CLAUSE_GROUNDING"
STATUS_SEMANTIC_MISMATCH = "REVIEW_FAILED_SEMANTIC_MISMATCH"
STATUS_REDLINE_QUALITY = "REVIEW_FAILED_REDLINE_QUALITY"
STATUS_ADVERSE_TO_CLIENT = "REJECT_REDLINE_ADVERSE_TO_CLIENT"
STATUS_BOILERPLATE_LOW = "BOILERPLATE_LOW_PRIORITY"

MAX_HIGH = 5
MAX_MEDIUM = 5

_TIER_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


# ── 주제 ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    #: finding(제목·문제)이 이 주제를 다루는지.
    finding: re.Pattern[str]
    #: 계약 조항이 이 주제를 규정하는지 — 동의어·유사 법률효과까지(지시 4항).
    clause: re.Pattern[str]
    #: HIGH 를 허용하는가(지시 7항).
    high_allowed: bool = True
    #: 같은 주제면 조항이 달라도 하나의 package 로 통합하는가(지시 6항).
    #: 대금은 지급구조가 여럿이면 뭉뚱그리지 않는다(지시 12항) — 같은 조에서만.
    merge_across_articles: bool = False


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE)


#: 순서가 우선순위다(지시 17항). 앞의 주제가 먼저 잡힌다.
TOPICS: tuple[Topic, ...] = (
    Topic("tax", "세무(부가가치세·세금계산서)",
          _rx(r"세금계산서|부가가치세|\bVAT\b|원천징수|\[세무\]"),
          _rx(r"세금계산서|부가가치세|VAT|원천징수"),
          high_allowed=False, merge_across_articles=True),
    Topic("jurisdiction", "관할·준거법",
          _rx(r"관할\s*(?:법원|조항)?|준거법|중재|분쟁\s*(?:해결\s*)?조항|jurisdiction|governing\s+law"),
          _rx(r"관할|준거법|중재|분쟁"),
          high_allowed=False),
    Topic("prepayment_security", "선급금 보증·담보",
          _rx(r"선급금\s*보증|보증\s*보험|이행\s*보증|보증\s*증권"),
          _rx(r"선급금|선금|착수금|보증"),
          high_allowed=False),
    Topic("ip", "지식재산·이용권",
          _rx(r"지식재산|저작권|저작물|이용권|이용\s*허락|2차적|복제|초상|퍼블리시티|IP\b"),
          _rx(r"저작권|지식재산|이용권|이용을?\s*허락|복제|2차적|전시|홍보|출판"),
          merge_across_articles=True),
    Topic("authority", "권한·보증(대리권)",
          _rx(r"권한|대리권|위임|권리\s*보증|진술\s*및\s*보장"),
          _rx(r"권한|대리권|위임|보증")),
    Topic("termination", "해지·종료",
          _rx(r"해지|해제|계약\s*종료|중도\s*종료"),
          _rx(r"해지|해제|종료|시정")),
    Topic("payment", "대금·정산",
          _rx(r"대금|계약금액|지급|정산|로열티|제작비|실비|상계|공제|지연\s*(?:이자|손해)"),
          _rx(r"지급|정산|로열티|대금|제작비|실비|공제|상계|계약금액|수금|청구|입금|결제|수수료|금액")),
    Topic("acceptance", "검수·납품·품질",
          _rx(r"검수|납품|인수|품질|하자|A/S"),
          _rx(r"검수|승인|납품|인수|품질|하자")),
    Topic("confidentiality", "비밀유지·공개",
          _rx(r"비밀|기밀|공개|SNS|유출"),
          _rx(r"비밀|기밀|공개|SNS|게시")),
    Topic("exclusivity", "독점·판매기간",
          _rx(r"독점|판매\s*기간|경업"),
          _rx(r"독점|판매\s*기간|경업")),
    Topic("liability", "손해배상·책임",
          _rx(r"손해\s*배상|책임\s*(?:제한|한도|범위)|면책|배상\s*책임"),
          _rx(r"손해|배상|책임|면책")),
    Topic("notice", "통지",
          _rx(r"^통지|통지\s*(?:절차|방법)"),
          _rx(r"통지"),
          high_allowed=False),
)
_TOPIC_BY_KEY = {t.key: t for t in TOPICS}


def _visible(cr: Any) -> bool:
    return (
        isinstance(cr, dict)
        and not cr.get("dedup_suppressed")
        and not cr.get("keep_as_is")
        and str(cr.get("risk_tier") or "").upper() in _TIER_RANK
    )


def _title(cr: dict[str, Any]) -> str:
    for d in cr.get("detected_issue_list") or []:
        if isinstance(d, dict) and str(d.get("issue_title") or "").strip():
            return str(d["issue_title"]).strip()
    return str(cr.get("issue_title") or cr.get("clause_title") or "").strip()


def _title_topics(cr: dict[str, Any]) -> list[Topic]:
    """이슈 제목만으로 정한 주제들 — 문제 서술에 스친 낱말은 쓰지 않는다."""
    title = re.sub(r"^제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?\s*", "", _title(cr))
    return [t for t in TOPICS if t.finding.search(title)]


def topic_of(cr: dict[str, Any]) -> Topic | None:
    """finding 이 다루는 주제. **이슈 제목**을 먼저 본다 — 조항 제목은 그 조항의
    이름일 뿐 finding 이 무엇을 문제삼는지가 아니다."""
    title = re.sub(r"^제\s*\d+\s*조(?:\s*제\s*\d+\s*항)?\s*", "", _title(cr))
    for t in TOPICS:
        if t.finding.search(title):
            return t
    problem = str(cr.get("problem") or "")[:160]
    for t in TOPICS:
        if t.finding.search(problem):
            return t
    return None


# ── 조항 색인 ───────────────────────────────────────────────────────────────

@dataclass
class ClauseRef:
    clause_id: str
    article: str
    paragraph: str
    display_path: str
    title: str
    text: str


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _index(clauses: list[Any] | None) -> list[ClauseRef]:
    out: list[ClauseRef] = []
    for c in clauses or []:
        text = _attr(c, "text")
        art = _attr(c, "article_number").strip()
        if not text.strip() or not art:
            continue
        out.append(ClauseRef(
            clause_id=_attr(c, "clause_id"),
            article=art,
            paragraph=_attr(c, "paragraph_number").strip(),
            display_path=_attr(c, "display_path") or (
                f"제{art}조" + (f" 제{_attr(c, 'paragraph_number')}항" if _attr(c, "paragraph_number") else "")
            ),
            title=_attr(c, "title") or _attr(c, "clause_title"),
            text=text,
        ))
    return out


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _clause_containing(quote: str, index: list[ClauseRef]) -> ClauseRef | None:
    # 앞 30자만 — 인용이 항을 넘어 이어지면("… VAT 별도 ② 위 계약금액은") 60자로는
    # 어느 항에도 통째로 들어 있지 않다.
    q = _squash(quote)[:30]
    if len(q) >= 8:
        for ref in index:
            if q in _squash(ref.text):
                return ref
    # 인용이 여러 항을 이어 붙인 것이면 줄 단위로 찾아 가장 많이 담은 조항을 쓴다.
    lines = [_squash(ln) for ln in str(quote or "").splitlines()]
    lines = [ln for ln in lines if len(ln) >= 8]
    best, best_hits = None, 0
    for ref in index:
        body = _squash(ref.text)
        hits = sum(1 for ln in lines if ln[:40] in body)
        if hits > best_hits:
            best, best_hits = ref, hits
    return best


_RX_WORD = re.compile(r"[가-힣]{2,}")
_STOP = frozenset({"계약", "조항", "규정", "경우", "관련", "사항", "책임", "당사자", "상대방", "우리",
                   "회사", "본계약", "계약서", "없음", "부재", "누락", "공통", "법률리스크", "구조인데"})


def _clause_by_overlap(cr: dict[str, Any], index: list[ClauseRef]) -> ClauseRef | None:
    """주제로도 못 찾으면 finding 의 낱말과 가장 많이 겹치는 조항 — 2개 이상 겹칠 때만."""
    words = {w for w in _RX_WORD.findall(_title(cr) + " " + str(cr.get("problem") or "")[:300])
             if w not in _STOP}
    best, best_hits = None, 1
    for ref in index:
        hits = sum(1 for w in words if w in ref.text)
        if hits > best_hits:
            best, best_hits = ref, hits
    return best


def _best_clause_for(topic: Topic, index: list[ClauseRef]) -> ClauseRef | None:
    best, best_hits = None, 0
    for ref in index:
        hits = len(topic.clause.findall(ref.title + " " + ref.text))
        # 조 제목에 주제어가 있으면 그 조가 이 주제를 규정하는 조항이다.
        if topic.clause.search(ref.title):
            hits += 3
        if hits > best_hits:
            best, best_hits = ref, hits
    return best


_RX_ABSENT_ORIGINAL = re.compile(r"해당\s*조항\s*없음|신설\s*필요")
_RX_NEW_ARTICLE = re.compile(r"신설|해당\s*조항\s*없음|말미에\s*신설|적절한\s*위치|관련\s*조항")


# ── 수정안 품질 ─────────────────────────────────────────────────────────────

_RX_APPENDIX_MARK = re.compile(r"\[추가\s*권고\]|\[수정\s*제안[^\]]*\]")


def _proposal(cr: dict[str, Any]) -> str:
    """제안 부분만 — "[추가 권고]" 앞의 원문 보존부는 뺀다."""
    sr = str(cr.get("suggested_rewrite") or cr.get("recommendation_text") or "")
    parts = _RX_APPENDIX_MARK.split(sr)
    return parts[-1].strip() if len(parts) > 1 else sr.strip()


#: 금전 부담을 **새로** 지우는 문형(지시 11항 — 지연이자 신설·위약금 등).
_RX_MONEY_BURDEN = _rx(
    r"연\s*\d+(?:\.\d+)?\s*%|지연\s*(?:이자|손해금)|이자를\s*가산|위약금|지체\s*상금|가산금"
)

#: 그 문장이 실제로 지급 의무를 지우는가. "지체상금 산정의 기준이 되는 잠정금액을
#: 명시한다"(언급)나 "위약금 등 추가 부담을 지지 아니한다"(부정)는 부담이 아니다.
_RX_PAY_VERB = _rx(r"지급(?:한다|하여야|해야|할\s*의무)|가산하여\s*지급|배상(?:한다|하여야)|부담한다")
_RX_NEGATED = _rx(r"아니한다|않는다|없다|지지\s*아니|면제")


def _added_money_burden(proposal: str, original: str) -> list[str]:
    out: list[str] = []
    for sent in re.split(r"(?<=[.。])\s+|\n", proposal):
        if not _RX_PAY_VERB.search(sent) or _RX_NEGATED.search(sent):
            continue
        for m in _RX_MONEY_BURDEN.finditer(sent):
            if m.group(0) not in original and m.group(0) not in out:
                out.append(m.group(0))
    return out


#: 당사자 역할 명사 — 계약에 없는 것이 수정문에 나오면 다른 계약의 템플릿이다.
_ROLE_NOUNS = (
    "위탁자", "수탁자", "발주자", "수급인", "도급인", "하수급인", "공급자", "매수인", "매도인",
    "용역사", "수행사", "라이선서", "라이선시", "임대인", "임차인", "광고주", "대행사",
)
#: 계약 당사자 지위 쌍으로만 쓰이는 명사 — 이 계약에 없고 바꿀 용어도 없으면 다른
#: 계약 템플릿이 섞인 것이다.
_STRICT_ROLE_NOUNS = frozenset({
    "위탁자", "수탁자", "도급인", "수급인", "하수급인", "발주자", "매도인", "매수인",
    "라이선서", "라이선시", "임대인", "임차인",
})

#: 역할 명사가 서는 쪽 — 대가를 주고 급부를 받는 쪽(client) / 급부를 제공하는 쪽(provider).
_CLIENT_SIDE = frozenset({"위탁자", "발주자", "도급인", "매수인", "광고주", "라이선시", "임차인",
                          "고객", "발주처", "구매자", "주문자"})
_PROVIDER_SIDE = frozenset({"수탁자", "수급인", "하수급인", "공급자", "매도인", "용역사", "수행사",
                            "라이선서", "임대인", "대행사", "매체사", "판매자", "공급사"})
_RX_QUOTED_TERM = re.compile(r"[“\"]([가-힣A-Za-z·]{1,10})[”\"]")


def _defined_terms(text: str) -> set[str]:
    """계약이 따옴표로 정의해 쓰는 당사자 용어("고객", "매체사")."""
    counts: dict[str, int] = {}
    for m in _RX_QUOTED_TERM.finditer(text):
        counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    return {t for t, n in counts.items() if n >= 2}


def _map_role_noun(noun: str, terms: set[str]) -> str:
    """템플릿 역할 명사를 이 계약의 같은 쪽 당사자 용어로. 하나로 정해지지 않으면 ""."""
    side = _CLIENT_SIDE if noun in _CLIENT_SIDE else _PROVIDER_SIDE if noun in _PROVIDER_SIDE else None
    if side is None:
        return ""
    cands = [t for t in terms if t in side]
    return cands[0] if len(cands) == 1 else ""


def _has_batchim(word: str) -> bool:
    last = word[-1:] if word else ""
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0


def _replace_role_noun(s: str, noun: str, term: str) -> str:
    pairs = {"은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"), "가": ("이", "가"),
             "을": ("을", "를"), "를": ("을", "를"), "과": ("과", "와"), "와": ("과", "와")}

    def _sub(m: re.Match[str]) -> str:
        p = m.group(1) or ""
        if p in pairs:
            p = pairs[p][0] if _has_batchim(term) else pairs[p][1]
        return term + p

    return re.sub(rf"{re.escape(noun)}(은|는|이|가|을|를|과|와)?", _sub, s)


#: 깨진 문구 — 빈 열거 고리, 짝 없는 괄호, 문장 끝이 접속어.
_RX_BROKEN = re.compile(
    r"·\s*·|\(\s*단\s*,\s*[^)]{0,40}·\s*[^)]{0,20}$|(?:또는|및|그리고|그러나)\s*\.{0,3}\s*$"
    r"|\(\s*\)|\s·\s*[가-힣]{1,4}(?:의|는|을|를)\s*·",
)


def _parens_balanced(s: str) -> bool:
    depth = 0
    for ch in s:
        if ch in "(（":
            depth += 1
        elif ch in ")）":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _our_labels(entity_resolution: Any) -> list[str]:
    out: list[str] = []
    our = getattr(entity_resolution, "our_company", None)
    if our is not None:
        for v in (our.label, our.brand_name, our.legal_entity_name):
            v = str(v or "").strip()
            if v and v not in out:
                out.append(v)
                core = re.sub(r"주식회사|㈜|\(주\)", "", v).strip()
                if core and core not in out:
                    out.append(core)
    return out


def our_company_pays(text: str, entity_resolution: Any) -> bool:
    """우리 회사가 이 계약의 지급자인가 — "알로소가 협업자에게 … 지급한다"."""
    for label in _our_labels(entity_resolution):
        if re.search(rf"{re.escape(label)}(?:가|이|는|은)[^.。\n]{{0,80}}지급", text):
            return True
        if re.search(rf"지급\s*주체는\s*{re.escape(label)}", text):
            return True
    return False


# ── 감사 ────────────────────────────────────────────────────────────────────

class _Audit:
    def __init__(self) -> None:
        self.actions: list[dict[str, str]] = []

    def act(self, cr: dict[str, Any], action: str, code: str, detail: str) -> None:
        self.actions.append({
            "clause_id": str(cr.get("clause_id") or ""),
            "action": action,
            "code": code,
            "detail": detail[:300],
        })

    def suppress(self, cr: dict[str, Any], code: str, detail: str) -> None:
        cr["dedup_suppressed"] = True
        cr["senior_audit_removed"] = code
        cr["senior_audit_reason"] = detail
        self.act(cr, "removed", code, detail)

    def set_tier(self, cr: dict[str, Any], tier: str, code: str, detail: str) -> None:
        old = str(cr.get("risk_tier") or "").upper()
        if old == tier:
            return
        cr["risk_tier"] = tier
        cr["severity"] = tier
        # 뒤에서 에이전트 등급을 복원하는 루프가 되돌리지 않게 한다.
        cr["counsel_severity"] = tier
        cr["review_tier"] = {"HIGH": "MUST", "MEDIUM": "SUGGEST"}.get(tier, "OPTIONAL")
        cr["senior_audit_tier_from"] = old
        self.act(cr, f"{old}->{tier}", code, detail)


def _ground(cr: dict[str, Any], index: list[ClauseRef], audit: _Audit) -> bool:
    """지시 2·3·4·18항. False 면 내보내지 않는다."""
    if cr.get("is_entity_name_correction"):
        return True  # 서두·서명란 줄 — 조항이 아닌 위치를 정확히 가리킨다
    art = str(cr.get("article_number") or "").strip()
    path = str(cr.get("display_path") or "")
    original = str(cr.get("original_text") or "")
    # 원문 칸에는 계약 문언이 들어 있다 — "관련 조항" 같은 낱말은 계약 문장에도 나오므로
    # 원문 쪽은 "해당 조항 없음·신설 필요" 표지만 본다.
    claims_new = bool(_RX_NEW_ARTICLE.search(path) or _RX_ABSENT_ORIGINAL.search(original))

    if art and not claims_new:
        return True
    # 위치 표기에 이미 "제N조(제M항)"가 있고 그 조가 실제로 있으면 그 위치가 맞다 —
    # 필드만 비어 있는 것이다. 다른 조로 옮기지 않는다.
    m_path = re.match(r"\s*제\s*(\d+)\s*조(?:\s*제\s*(\d+)\s*항)?", path)
    if m_path and not re.search(r"신설", path) and any(r.article == m_path.group(1) for r in index):
        cr["article_number"] = m_path.group(1)
        if m_path.group(2) and not str(cr.get("paragraph_number") or "").strip():
            cr["paragraph_number"] = m_path.group(2)
        if claims_new and not cr.get("location_instruction"):
            # 없는 문구를 넣는 권고라도 들어갈 조항은 정해져 있다(지시 18항).
            cr["location_instruction"] = f"{path.strip()} 말미에 다음 문구 추가"
        return True

    # 원문 인용이 실제 조항 안에 있으면 그 조항이다("계약서 표지"로 적혀 있어도).
    ref = _clause_containing(original, index) if original and not claims_new else None
    absent = claims_new or not original.strip() or bool(re.search(r"계약\s*전체|부재|없음", original))
    has_reason = any(str(cr.get(k) or "").strip() for k in ("problem", "rewrite_reason", "legal_business_reason"))
    if absent and not has_reason:
        # 위치도 근거도 없는 체크리스트 껍데기 — 붙일 조항을 찾아 줄 이유가 없다.
        audit.suppress(cr, STATUS_CLAUSE_GROUNDING, f"조·항도 근거도 없는 finding ({path or '위치 없음'})")
        return False
    if ref is None:
        topic = topic_of(cr)
        ref = _best_clause_for(topic, index) if topic is not None else None
        if ref is None:
            ref = _clause_by_overlap(cr, index)
        if ref is not None and absent:
            cr["location_instruction"] = f"{ref.display_path} 말미에 다음 문구 추가"
    if ref is None:
        if not has_reason:
            audit.suppress(cr, STATUS_CLAUSE_GROUNDING,
                           f"조·항도 근거도 없는 finding ({path or '위치 없음'})")
            return False
        # 원문 대조로 확인된 지적은 지우지 않는다 — 위치를 못 정한 사실만 남긴다.
        cr["grounding_unresolved"] = True
        audit.act(cr, "grounding_unresolved", STATUS_CLAUSE_GROUNDING,
                  f"관련 조항을 특정하지 못함 ({path or '위치 없음'})")
        return True
    before = path or "(위치 없음)"
    cr["article_number"] = ref.article
    cr["paragraph_number"] = ref.paragraph
    cr["display_path"] = ref.display_path
    cr["clause_title"] = cr.get("clause_title") or ref.title
    if absent:
        # 없는 것을 지적하는 finding 에는 인용할 원문이 없다. 붙일 조항의 본문을
        # 원문으로 빌려 쓰면 그 조항의 (무관하거나 오염된) 문언이 보고서에 실린다
        # (OPC 픽스처의 개발계약 문구 함정). 삽입 위치만 적는다.
        # "해당 조항 없음" 표지는 유지한다 — 인용 대조·DOCX 가 이 표지로 부재 finding 을
        # 알아본다. 대신 실제로 넣을 조항을 함께 적는다(지시 18항).
        cr["original_text"] = f"(해당 조항 없음 — {ref.display_path} 말미에 추가)"
    cr["is_checklist_item"] = False
    cr["reanchored_from"] = before
    audit.act(cr, "reanchored", STATUS_CLAUSE_GROUNDING, f"{before} → {ref.display_path}")
    return True


def _semantic_ok(cr: dict[str, Any], index: list[ClauseRef], audit: _Audit) -> bool:
    """지시 10항 — finding 주제어가 붙은 조항 문언에 하나도 없으면 다른 조항 얘기다."""
    if (
        cr.get("is_entity_name_correction") or cr.get("reanchored_from")
        # 사슬·기본효과·체크리스트는 "없는 것"을 그것이 들어갈 조항에 붙인다 —
        # 그 조항에 주제어가 없는 것이 정상이다.
        or cr.get("is_risk_package") or cr.get("is_effect_baseline") or cr.get("is_checklist_item")
    ):
        return True
    title = _title(cr)
    if re.search(r"없음|않음|부재|미규정|누락|미흡|불명확|특정되지", title):
        return True
    topics = _title_topics(cr)
    original = str(cr.get("original_text") or "")
    if not topics or not original.strip() or any(t.key in ("tax", "notice") for t in topics):
        return True
    # 제목이 여러 주제를 말하면("무과실 하자 손해배상") 그중 하나라도 조항에 있으면 된다.
    haystack = original + " " + str(cr.get("clause_title") or "")
    if any(t.clause.search(haystack) for t in topics):
        return True
    # 제목의 핵심 낱말이 조항에 그대로 있으면 그 조항 얘기다("수금 책임" ↔ "수금 업무").
    title_words = {w for w in _RX_WORD.findall(title) if w not in _STOP and len(w) >= 2}
    if any(w in original for w in title_words):
        return True
    topic = topics[0]
    audit.suppress(cr, STATUS_SEMANTIC_MISMATCH,
                   f"'{topic.label}' finding 이 그 내용을 규정하지 않는 "
                   f"{cr.get('display_path') or '조항'}에 붙어 있음")
    return False


def _redline_ok(cr: dict[str, Any], *, text: str, we_pay: bool, audit: _Audit) -> bool:
    """지시 11·19항. False 면 내보내지 않는다."""
    if cr.get("is_entity_name_correction"):
        return True
    proposal = _proposal(cr)
    if not proposal:
        return True
    original = str(cr.get("original_text") or "")

    added_burden = _added_money_burden(proposal, original)
    if we_pay and added_burden:
        audit.suppress(cr, STATUS_ADVERSE_TO_CLIENT,
                       f"우리 회사가 지급자인데 수정안이 금전 부담({', '.join(added_burden[:3])})을 새로 만듦")
        return False

    foreign_roles = [n for n in _ROLE_NOUNS if n in proposal and n not in text]
    if foreign_roles:
        # 이 계약이 같은 쪽 당사자를 부르는 용어가 하나로 정해지면 그 용어로 바꾼다
        # ("광고주" → 계약의 "고객"). 정해지지 않으면 넣을 수 없는 문안이다.
        terms = _defined_terms(text)
        mapping = {n: _map_role_noun(n, terms) for n in foreign_roles}
        if all(mapping.values()):
            for key in ("suggested_rewrite", "recommendation_text"):
                v = cr.get(key)
                if isinstance(v, str) and v:
                    for n, term in mapping.items():
                        v = _replace_role_noun(v, n, term)
                    cr[key] = v
            proposal = _proposal(cr)
            audit.act(cr, "party_term_mapped", STATUS_REDLINE_QUALITY,
                      ", ".join(f"{n}→{t}" for n, t in mapping.items()))
            foreign_roles = []
        else:
            # 매핑이 안 된 것 중 **계약 당사자 지위**를 뜻하는 명사만 결함이다.
            # "상품 공급자의 귀책사유"처럼 거래 참여자를 서술하는 말은 당사자
            # 명칭이 아니다(그림닷컴 골든 답안).
            foreign_roles = [n for n in foreign_roles if n in _STRICT_ROLE_NOUNS and not mapping.get(n)]
    broken = bool(_RX_BROKEN.search(proposal)) or not _parens_balanced(proposal)
    no_op = _squash(proposal) == _squash(original)
    if foreign_roles or broken or no_op:
        why = (
            f"계약에 없는 당사자 명사({', '.join(foreign_roles)})" if foreign_roles
            else "원문과 같은 수정안" if no_op else "문장이 깨진 수정안"
        )
        # 지적 자체가 서 있으면 수정문만 거두고, 지적도 없으면 통째로 뺀다.
        if str(cr.get("problem") or "").strip() and not foreign_roles:
            cr["suggested_rewrite"] = None
            cr["recommendation_text"] = None
            cr["redline_withheld"] = STATUS_REDLINE_QUALITY
            audit.act(cr, "redline_withheld", STATUS_REDLINE_QUALITY, why)
            return True
        audit.suppress(cr, STATUS_REDLINE_QUALITY, why)
        return False
    return True


#: 지시 9항 — 선급금 보증을 요구할 만한 거래 원형.
_SECURITY_ARCHETYPES = frozenset({"goods_supply", "construction_works", "lease_rental", "distribution_resale"})


def _materiality(
    cr: dict[str, Any], *, text: str, archetype: str, dispute_review: bool, audit: _Audit,
) -> bool:
    """지시 7·8·9·15항."""
    topic = topic_of(cr)
    tier = str(cr.get("risk_tier") or "").upper()
    title = _title(cr)

    if topic is not None and topic.key == "jurisdiction" and not dispute_review:
        if re.search(r"다국가|해외|국제|외국", title):
            audit.suppress(cr, STATUS_BOILERPLATE_LOW,
                           "국내 법인 간 국내 계약에 해외·다국가 분쟁 점검 규칙이 적용됨")
            return False
        cr["boilerplate_low_priority"] = True
        if tier != "LOW":
            audit.set_tier(cr, "LOW", STATUS_BOILERPLATE_LOW,
                           "국내 법인 간 국내 계약의 관할·준거법 문구 — 선택적 정비 사항")
        return True

    if topic is not None and topic.key == "prepayment_security" and archetype not in _SECURITY_ARCHETYPES:
        audit.suppress(cr, "PREPAYMENT_SECURITY_NOT_WARRANTED",
                       f"거래 원형({archetype or '미상'})상 선급금 보증을 자동 요구할 근거 없음")
        return False

    if tier == "HIGH":
        basis = str(cr.get("high_severity_basis") or "")
        # 규칙 기반 finding 은 근거를 rewrite_reason·legal_business_reason 에 적는다.
        problem = " ".join(
            str(cr.get(k) or "").strip()
            for k in ("problem", "rewrite_reason", "legal_business_reason", "risk_description")
        ).strip()
        if topic is not None and not topic.high_allowed:
            audit.set_tier(cr, "MEDIUM", "HIGH_THRESHOLD",
                           f"'{topic.label}'은 체결 전 필수 수정 사항이 아님")
        elif not problem and not basis:
            # 규칙이 "승인 필요"로 선언한 HIGH 는 골든 답안(웹젠·시험용역)이 확인한
            # 판단이다 — 그 표지만으로도 근거가 선 것으로 본다.
            audit.set_tier(cr, "MEDIUM", "HIGH_THRESHOLD",
                           "HIGH 근거(무엇을 잃는가)가 서술되지 않음")
    return True


#: 이용을 **허락하는** 문언 — 이용허락 쟁점이 실제로 걸리는 조항.
_RX_GRANT = re.compile(r"이용권을?\s*허락|이용을?\s*허락|이용\s*허락|사용을?\s*허락|이용할\s*수\s*있다")
_RX_PHYSICAL_CLAUSE = re.compile(r"실물\s*소유권|원본|원작|별개의?\s*권리")


def _relation_reanchor(cr: dict[str, Any], index: list[ClauseRef], audit: _Audit) -> None:
    """지시 14항 C — 2차적 이용·이용허락 쟁점이 **실물 소유권 조항**에 붙어 있으면
    이용을 허락하는 조항으로 옮긴다. 실측: "2차적저작물작성권 포함 여부 불명확"이
    제9조 제3항("실물 소유권과 저작권 및 저작재산권은 별개의 권리로 한다")에 붙었다.
    """
    from runtime.review.statute_grounding import detect_relations

    if cr.get("is_entity_name_correction"):
        return
    rels = detect_relations(cr)
    if not ({"derivative", "ip_license"} & set(rels)) or "physical_ownership" in rels:
        return
    original = str(cr.get("original_text") or "")
    if not _RX_PHYSICAL_CLAUSE.search(original) or _RX_GRANT.search(original):
        return
    grants = [r for r in index if _RX_GRANT.search(r.text)]
    if not grants:
        return
    grants.sort(key=lambda r: -len(re.findall(r"제작|복제|생산|판매|유통|상품|제품", r.text)))
    ref = grants[0]
    before = str(cr.get("display_path") or "")
    cr.update({
        "article_number": ref.article, "paragraph_number": ref.paragraph,
        "display_path": ref.display_path, "clause_title": ref.title or cr.get("clause_title"),
        "original_text": ref.text, "reanchored_from": before,
    })
    # 수정문은 옛 조항 문언 위에 쓰인 것이다 — 새 조항 위에 다시 만든다. 뒤의 인용·
    # 수정문 정합성 게이트가 "다른 조항의 수정문"으로 보고 지운다(실측).
    effects = [str(e) for e in (cr.get("clause_effects") or []) if e] or ["ip_license"]
    try:
        from runtime.review.minimal_edit import minimal_edit_for

        final_text, _addition, position = minimal_edit_for(
            original_text=ref.text, clause_title=ref.title, effects=effects,
        )
    except Exception:  # noqa: BLE001 - 재작성 실패는 수정문 보류로 처리
        final_text, position = "", ""
    if final_text and _squash(final_text) != _squash(ref.text):
        cr["suggested_rewrite"] = final_text
        cr["recommendation_text"] = final_text
        cr.pop("redline_withheld", None)  # 보류는 옛 조항 위의 수정문에 대한 판단이었다
        if position:
            cr.setdefault("negotiation_position", position)
    else:
        cr["suggested_rewrite"] = None
        cr["recommendation_text"] = None
        cr["redline_withheld"] = STATUS_REDLINE_QUALITY
    audit.act(cr, "reanchored", "RELATION_ANCHOR",
              f"이용허락·2차적 이용 쟁점을 실물 소유권 조항({before})에서 이용허락 조항({ref.display_path})으로")


_RX_BACKGROUND_CLAUSE = re.compile(r"이전부터\s*보유|기존\s*(?:지식재산|저작물|작품)")
_RX_AUTHORITY_CLAUSE = re.compile(r"권한|위임|대리|보증")


def _format_paths(refs: list[ClauseRef], extra: list[str]) -> list[str]:
    """같은 조의 연속된 항은 "제20조 제1항~제3항"으로 묶는다."""
    by_art: dict[str, list[int]] = {}
    plain: list[str] = []
    for r in refs:
        if r.paragraph.isdigit():
            by_art.setdefault(r.article, []).append(int(r.paragraph))
        else:
            plain.append(r.display_path)
    rest: list[str] = []
    for p in extra:
        m = re.match(r"\s*제\s*(\d+)\s*조\s*제\s*(\d+)\s*항\s*$", p or "")
        if m:
            by_art.setdefault(m.group(1), []).append(int(m.group(2)))
        else:
            rest.append(p)
    extra = rest
    out: list[str] = []
    for art in sorted(by_art, key=lambda a: int(a) if a.isdigit() else 0):
        ps = sorted(set(by_art[art]))
        run = [ps[0]]
        for p in ps[1:] + [None]:  # type: ignore[list-item]
            if p is not None and p == run[-1] + 1:
                run.append(p)
                continue
            out.append(f"제{art}조 제{run[0]}항" + (f"~제{run[-1]}항" if len(run) > 1 else ""))
            if p is not None:
                run = [p]
    def _covered(path: str) -> bool:
        m = re.match(r"\s*제\s*(\d+)\s*조(?:\s*제\s*(\d+)\s*항)?\s*$", path)
        if not m:
            return False
        for o in out:
            mo = re.match(r"제(\d+)조 제(\d+)항(?:~제(\d+)항)?$", o)
            if mo and mo.group(1) == m.group(1):
                lo, hi = int(mo.group(2)), int(mo.group(3) or mo.group(2))
                if m.group(2) is None or lo <= int(m.group(2)) <= hi:
                    return True
        return False

    for p in plain + extra:
        if p and p not in out and not _covered(p):
            out.append(p)
    return out


def _ground_statutes(cr: dict[str, Any], index: list[ClauseRef], *, archetype: str, audit: _Audit) -> None:
    """지시 1·2·4·8·9항 — 관련 계약조항·조문·법률상 이유·실무상 이유를 분리해 싣는다."""
    from runtime.review.statute_grounding import (
        RELATION_REASON,
        STATUS_STATUTE_GROUNDING,
        audit_cited_statutes,
        detect_relations,
        statutes_for,
        strip_law_mentions,
    )

    tier = str(cr.get("risk_tier") or "").upper()
    lbr = str(cr.get("legal_business_reason") or "")
    if tier == "LOW" and not (cr.get("keep_as_is") and cr.get("triage") == "KEEP"):
        # 참고 사항은 조문을 강제하지 않는다 — 법률명 나열만 걷어 낸다. KEEP 판정은
        # "왜 현행으로 충분한가"의 근거이므로 조문을 싣는다.
        cleaned = strip_law_mentions(lbr)
        if cleaned != lbr.strip() and cleaned:
            cr["legal_business_reason"] = cleaned
        return

    rels = detect_relations(cr, archetype=archetype)
    if cr.get("is_entity_name_correction"):
        rels = ["legal_entity"]
    cited_src = " ".join(str(cr.get(k) or "") for k in ("legal_business_reason", "legal_basis", "rewrite_reason", "problem"))
    kept, removed = audit_cited_statutes(cited_src, rels)
    chosen = list(kept)
    for st in statutes_for(rels):
        if st not in chosen:
            chosen.append(st)
    chosen = chosen[:6]

    # 관련 계약조항 — 대표 조항 + 통합된 하위 쟁점 + 법률관계상 함께 봐야 할 조항.
    own = [r for r in index if r.display_path == cr.get("display_path")]
    if not own:
        own = [r for r in index if r.article == str(cr.get("article_number") or "")
               and r.paragraph == str(cr.get("paragraph_number") or "")]
    refs = list(own)
    if "background_ip" in rels or "ip_license" in rels:
        refs += [r for r in index if r.article == (own[0].article if own else "")
                 and _RX_BACKGROUND_CLAUSE.search(r.text)]
    if "agency" in rels and own:
        refs += [r for r in index if r.article == own[0].article and _RX_AUTHORITY_CLAUSE.search(r.text)]
    extra = [str(p) for p in (cr.get("related_clause_paths") or [])]
    if cr.get("is_entity_name_correction"):
        paths = [str(cr.get("display_path") or "")]
    else:
        uniq: list[ClauseRef] = []
        for r in refs:
            if all(u.display_path != r.display_path for u in uniq):
                uniq.append(r)
        paths = _format_paths(uniq, extra) or [str(cr.get("display_path") or "")]

    reasons = [RELATION_REASON[r] for r in rels if r in RELATION_REASON][:3]
    business = (
        strip_law_mentions(lbr)
        or strip_law_mentions(str(cr.get("problem") or ""))
        or strip_law_mentions(str(cr.get("rewrite_reason") or ""))
        or strip_law_mentions(_title(cr))
    )
    grounding: dict[str, Any] = {
        "contract_clauses": [p for p in paths if p],
        "statutes": [
            {"citation": st.citation, "title": st.title, "effect": st.effect, "role": st.role}
            for st in chosen
        ],
        "relations": rels,
        "legal_reason": " ".join(reasons),
        "business_reason": business,
        "statute_note": "" if chosen else (
            "법률효과는 계약상 약정(권리·의무) 문제로 판단되어 별도 법조문 인용은 생략합니다."
        ),
        "removed_citations": removed,
    }
    cr["legal_grounding"] = grounding
    if business:
        # 보고서의 "법적/실무상 이유" 칸에 법률명 나열이 다시 실리지 않게 한다.
        cr["legal_business_reason"] = business
    if removed:
        audit.act(cr, "statute_removed", STATUS_STATUTE_GROUNDING,
                  "; ".join(f"{r['citation']}({r['reason']})" for r in removed)[:280])


def _is_generated(cr: dict[str, Any]) -> bool:
    from runtime.review.issue_triage import is_protected

    return not is_protected(cr)


def _apply_triage(
    clause_results: list[dict[str, Any]], *, index: list[ClauseRef], text: str, archetype: str, audit: _Audit,
) -> dict[str, Any]:
    """2026-10-01 지시 — MUST/SHOULD/KEEP/FINANCE_CHECK/DROP. 결과는 제자리에서 고친다."""
    from runtime.review.issue_triage import (
        DROP, FINANCE_CHECK, KEEP, MUST_FIX, SHOULD_FIX, axis_of, triage_one,
    )
    from runtime.review.statute_grounding import detect_relations

    has_name_fix = any(isinstance(c, dict) and c.get("is_entity_name_correction") and _visible(c)
                       for c in clause_results)
    out: dict[str, list[dict[str, Any]]] = {MUST_FIX: [], SHOULD_FIX: [], KEEP: [], FINANCE_CHECK: [], DROP: []}

    def _row(cr: dict[str, Any], label: str, reason: str, scores: dict[str, int] | None) -> dict[str, Any]:
        g = cr.get("legal_grounding") or {}
        return {
            "clause_id": str(cr.get("clause_id") or ""),
            "display_path": str(cr.get("display_path") or ""),
            "title": _title(cr),
            "triage": label,
            "reason": reason,
            "materiality": scores or {},
            "contract_clauses": list(g.get("contract_clauses") or []),
            "statutes": [s.get("citation") for s in g.get("statutes") or []],
        }

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        if cr.get("keep_as_is") and cr.get("triage") == KEEP:
            out[KEEP].append(_row(cr, KEEP, str(cr.get("keep_reason") or ""), None))
            continue
        if not _visible(cr):
            continue
        relations = detect_relations(cr, archetype=archetype)
        topic = topic_of(cr)
        axis = axis_of(cr, topic.key if topic else None, relations)
        if axis == "legal_entity" and not cr.get("is_entity_name_correction") and has_name_fix:
            # 법인명 정정 finding 이 위치별로 이미 있다 — 같은 쟁점의 일반 서술은 중복이다.
            cr["triage"] = DROP
            audit.suppress(cr, "TRIAGE_DROP", "당사자 법인명 정정 finding 과 같은 쟁점(중복)")
            out[DROP].append(_row(cr, DROP, "법인명 정정과 중복", None))
            continue
        article = str(cr.get("article_number") or "")
        article_text = "\n".join(r.text for r in index if r.article == article) if article else ""
        label, reason, scores = triage_one(
            cr, axis=axis, relations=relations, contract_text=text, article_text=article_text,
        )
        cr["triage"] = label
        cr["triage_reason"] = reason
        cr["triage_axis"] = axis
        cr["materiality_score"] = scores
        tier = str(cr.get("risk_tier") or "").upper()
        if label == MUST_FIX:
            pass
        elif label == SHOULD_FIX:
            if tier == "HIGH":
                audit.set_tier(cr, "MEDIUM", "TRIAGE_SHOULD_FIX", reason or "중요도상 권장 수정")
        elif label == KEEP:
            cr["keep_as_is"] = True
            cr["keep_reason"] = reason
            cr["display_kind"] = "keep"
            audit.act(cr, "keep", "TRIAGE_KEEP", reason)
        elif label == FINANCE_CHECK:
            cr["finance_check"] = True
            if tier != "LOW":
                audit.set_tier(cr, "LOW", "TRIAGE_FINANCE_CHECK", reason)
        elif label == DROP:
            # DROP 은 "기본 노출에서 제외"다 — LOW(참고)로 내리고 기록은 남긴다. 지우면
            # 계약유형별 핵심축 finding 까지 사라진다(교차 hold-out 실측).
            if tier in ("HIGH", "MEDIUM"):
                audit.set_tier(cr, "LOW", "TRIAGE_DROP", reason)
        out[label].append(_row(cr, label, reason, scores))

    # 같은 조·항의 같은 축 MUST/SHOULD 는 한 건이다(지시 5항) — 실측: 제9조 제1항 실물
    # 소유권이 결정론 점검과 AI 논점으로 두 번 나왔다. 원문 확인 finding(보호 대상)을 남긴다.
    from runtime.review.issue_triage import is_protected

    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for cr in clause_results:
        if not _visible(cr) or cr.get("triage") not in (MUST_FIX, SHOULD_FIX) or cr.get("is_entity_name_correction"):
            continue
        key = (str(cr.get("article_number") or ""), str(cr.get("paragraph_number") or ""),
               str(cr.get("triage_axis") or ""))
        if key[0] and key[2] not in ("", "other"):
            groups.setdefault(key, []).append(cr)
    for items in groups.values():
        if len(items) < 2:
            continue
        items.sort(key=lambda c: (not is_protected(c), c.get("triage") != MUST_FIX))
        rep = items[0]
        for cr in items[1:]:
            cr["dedup_suppressed"] = True
            cr["dedup_merged_into"] = str(rep.get("clause_id") or "")
            rep.setdefault("sub_issues", []).append({
                "clause_id": str(cr.get("clause_id") or ""), "display_path": str(cr.get("display_path") or ""),
                "title": _title(cr), "problem": str(cr.get("problem") or "")[:240],
            })
            audit.act(cr, "merged", "TRIAGE_SAME_CLAUSE", f"같은 조항·같은 쟁점 → {rep.get('clause_id')}")
            for label in (MUST_FIX, SHOULD_FIX):
                out[label] = [r for r in out[label] if r["clause_id"] != str(cr.get("clause_id") or "")]
    return out


def _merge_packages(visible: list[dict[str, Any]], audit: _Audit) -> None:
    """지시 6항 — 같은 주제의 HIGH/MEDIUM 을 대표 하나로."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for cr in visible:
        if cr.get("dedup_suppressed") or cr.get("is_entity_name_correction"):
            continue
        if str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        topic = topic_of(cr)
        if topic is None:
            continue
        scope = "" if topic.merge_across_articles else str(cr.get("article_number") or cr.get("clause_id"))
        groups.setdefault((topic.key, scope), []).append(cr)
    for (key, _), items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda c: (
            -_TIER_RANK.get(str(c.get("risk_tier") or "").upper(), 0),
            -int(bool(_proposal(c))),
            -float(c.get("confidence") or 0),
        ))
        rep, rest = items[0], items[1:]
        subs = rep.setdefault("sub_issues", [])
        paths = [str(rep.get("display_path") or "")]
        for cr in rest:
            subs.append({
                "clause_id": str(cr.get("clause_id") or ""),
                "display_path": str(cr.get("display_path") or ""),
                "title": _title(cr),
                "problem": str(cr.get("problem") or "")[:240],
            })
            paths.append(str(cr.get("display_path") or ""))
            cr["dedup_suppressed"] = True
            cr["dedup_merged_into"] = str(rep.get("clause_id") or "")
            audit.act(cr, "merged", "RISK_PACKAGE",
                      f"{_TOPIC_BY_KEY[key].label} package → {rep.get('clause_id')}")
        rep["risk_package_topic"] = _TOPIC_BY_KEY[key].label
        rep["related_clause_paths"] = [p for p in dict.fromkeys(paths) if p]
        lines = "; ".join(f"{s['display_path']} {s['title']}".strip() for s in subs)
        base = str(rep.get("problem") or "").strip()
        if lines and "[통합된 하위 쟁점]" not in base:
            rep["problem"] = (base + "\n" if base else "") + f"[통합된 하위 쟁점] {lines}"


def _priority(cr: dict[str, Any]) -> tuple[int, float]:
    topic = topic_of(cr)
    order = [t.key for t in TOPICS]
    # 지시 17항: 당사자 → 대금 → IP → 권한 → 검수 → 해지 → 나머지
    preferred = ["payment", "ip", "authority", "acceptance", "termination", "liability", "confidentiality"]
    if cr.get("is_entity_name_correction"):
        rank = -1
    elif topic is not None and topic.key in preferred:
        rank = preferred.index(topic.key)
    else:
        rank = len(preferred) + (order.index(topic.key) if topic is not None else len(order))
    return rank, -float(cr.get("confidence") or 0)


def _limit_counts(clause_results: list[dict[str, Any]], audit: _Audit) -> None:
    """지시 16항 — 핵심 finding 이 과도할 때만 재점검, 같은 제목의 LOW 통합.

    건수는 **목표**이지 절단선이 아니다. 근거가 선 HIGH 를 개수 때문에 내리면
    골든 답안(웹젠 장비구매: 무과실 하자책임·위약금 배수·즉시 배상 등 독립 HIGH
    여럿)이 무너진다. 그래서 핵심이 10건을 넘을 때만, 근거가 서술되지 않은 HIGH 와
    우선순위가 낮은 MEDIUM 부터 내린다.
    """
    core = [c for c in clause_results if _visible(c) and not c.get("is_entity_name_correction")
            and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]
    if len(core) > 10:
        highs = [c for c in core if str(c.get("risk_tier")).upper() == "HIGH"]
        if len(highs) > MAX_HIGH:
            highs.sort(key=_priority)
            for cr in highs[MAX_HIGH:]:
                if not str(cr.get("high_severity_basis") or "").strip():
                    audit.set_tier(cr, "MEDIUM", "FINDING_COUNT_LIMIT",
                                   f"HIGH {MAX_HIGH}건 초과 — 치명 근거가 서술되지 않음")
        mediums = [c for c in clause_results if _visible(c) and not c.get("is_entity_name_correction")
                   and str(c.get("risk_tier")).upper() == "MEDIUM"]
        if len(mediums) > MAX_MEDIUM:
            mediums.sort(key=_priority)
            for cr in mediums[MAX_MEDIUM:]:
                audit.set_tier(cr, "LOW", "FINDING_COUNT_LIMIT",
                               f"핵심 finding 과다 — MEDIUM {MAX_MEDIUM}건 초과분(우선순위 낮음)")
    seen: dict[str, dict[str, Any]] = {}
    for cr in clause_results:
        if not _visible(cr) or str(cr.get("risk_tier")).upper() != "LOW":
            continue
        key = re.sub(r"\s+", "", _title(cr))
        if not key:
            continue
        first = seen.get(key)
        if first is None:
            seen[key] = cr
            continue
        cr["dedup_suppressed"] = True
        cr["dedup_merged_into"] = str(first.get("clause_id") or "")
        first.setdefault("related_clause_paths", [str(first.get("display_path") or "")]).append(
            str(cr.get("display_path") or ""))
        audit.act(cr, "merged", "DUPLICATE_LOW", f"같은 제목 LOW → {first.get('clause_id')}")


def run_senior_counsel_audit(
    clause_results: list[dict[str, Any]],
    *,
    text: str,
    clauses: list[Any] | None,
    entity_resolution: Any = None,
    archetype: str = "",
) -> dict[str, Any]:
    """결과를 제자리에서 고치고 감사 보고를 돌려준다."""
    from runtime.review.jurisdiction_risk_calibration import dispute_needs_review

    body = str(text or "")
    index = _index(clauses)
    audit = _Audit()
    we_pay = our_company_pays(body, entity_resolution)
    dispute_review = dispute_needs_review(body)

    def _count() -> dict[str, int]:
        out = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for c in clause_results:
            if _visible(c):
                out[str(c.get("risk_tier")).upper()] += 1
        return out

    before = _count()
    for cr in clause_results:
        if not _visible(cr):
            continue
        if not _ground(cr, index, audit):
            continue
        if not _semantic_ok(cr, index, audit):
            continue
        if not _redline_ok(cr, text=body, we_pay=we_pay, audit=audit):
            continue
        _materiality(cr, text=body, archetype=archetype, dispute_review=dispute_review, audit=audit)
        if _visible(cr):
            _relation_reanchor(cr, index, audit)

    _merge_packages([c for c in clause_results if _visible(c)], audit)
    # 법조문은 통합이 끝난 뒤에 붙인다 — 대표 finding 이 하위 쟁점의 법률관계까지 덮는다.
    for cr in clause_results:
        if _visible(cr) or (isinstance(cr, dict) and cr.get("keep_as_is") and cr.get("triage") == "KEEP"):
            _ground_statutes(cr, index, archetype=archetype, audit=audit)
    triage = _apply_triage(clause_results, index=index, text=body, archetype=archetype, audit=audit)
    # 건수 상한은 triage(KEEP·재경·DROP) 뒤에 본다 — 앞에서 보면 곧 빠질 항목들 때문에
    # 정작 남겨야 할 SHOULD FIX(지원사업 상위기준)가 개수에 밀려 내려갔다(실측).
    _limit_counts(clause_results, audit)
    after = _count()

    codes = sorted({a["code"] for a in audit.actions})
    core = [c for c in clause_results if _visible(c) and str(c.get("risk_tier")).upper() in ("HIGH", "MEDIUM")]
    # 법인명 정정은 위치(서두·서명란)마다 따로 남는 한 쟁점이다 — 건수 점검에서 뺀다.
    core_issues = [c for c in core if not c.get("is_entity_name_correction")]
    final_check = {
        # 지시 20항 — 출력 직전 점검 결과. 실패 축은 위에서 이미 고쳤어야 한다.
        "high_within_limit": after["HIGH"] <= MAX_HIGH,
        "medium_within_limit": after["MEDIUM"] <= MAX_MEDIUM + 2,  # 법인명 정정은 위치별로 남는다
        "core_grounded": all(
            c.get("is_entity_name_correction") or str(c.get("article_number") or "").strip()
            for c in core
        ),
        "no_new_article_claims": not any(
            _RX_NEW_ARTICLE.search(str(c.get("display_path") or "")) for c in core
        ),
        "no_high_in_minor_topics": not any(
            str(c.get("risk_tier")).upper() == "HIGH"
            and (topic_of(c) is not None and not topic_of(c).high_allowed)
            for c in core
        ),
        "core_count_reasonable": len(core_issues) <= 10,
        "high_target": after["HIGH"] <= 3 or all(not _is_generated(c) for c in core
                                                  if str(c.get("risk_tier")).upper() == "HIGH"),
    }
    return {
        "triage": triage,
        "final_check": final_check,
        "final_check_failed": [k for k, ok in final_check.items() if not ok],
        "before": before,
        "after": after,
        "our_company_pays": we_pay,
        "dispute_structure_needs_review": dispute_review,
        "actions": audit.actions,
        "codes": codes,
        "total_after": sum(after.values()),
        "core_after": after["HIGH"] + after["MEDIUM"],
    }


__all__ = [
    "MAX_HIGH",
    "MAX_MEDIUM",
    "STATUS_ADVERSE_TO_CLIENT",
    "STATUS_BOILERPLATE_LOW",
    "STATUS_CLAUSE_GROUNDING",
    "STATUS_REDLINE_QUALITY",
    "STATUS_SEMANTIC_MISMATCH",
    "TOPICS",
    "our_company_pays",
    "run_senior_counsel_audit",
    "topic_of",
]
