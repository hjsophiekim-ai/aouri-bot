"""사용자가 조항번호로 지목한 요청사항을 그 조항 원문에 붙여 직접 검토한다.

2026-11-02 지시(Norden 디자인 계약 실측)
──────────────────────────────────────────
담당자가 "제6.5조(위약금)", "제9.9조(제조물책임보험)", "제13.1조(연장)", "제13.3조(종료 후 처리)" 처럼 조항을 짚어
7개를 물었는데, 검토 결과는
  · 4개를 "이 쟁점을 직접 다루는 조항이 계약에 없다" 고 답했다 — "제6.5조" 와 "Article 6.5" 를 문자열로 비교했다.
  · 제13.3조(wind-down) 질문을 낱말 검색으로 제15.2조(제재 준수)에 붙여 "현재 문언으로 커버됩니다" 라고 답했다.
  · AI 가 제13.3조·제9.9조에 낸 HIGH 지적은 국문 계약용 게이트(외래어 오염·국문 주제어 대조·인용 일치율)가 지웠다.
요청마다 실제 근거와 실질 답을 잇는 단계가 없었다 — 조항 단위 AI 검토가 우연히 같은 조항을 지적해야만 답이 생겼다.

이 단계는
  1. 요청 블록(세부 줄·제안 문구 포함)을 자르고, 지목된 조항을 **번호로** 찾는다(없으면 문서 전체를 다시 찾는다).
  2. 그 조항 원문 + 같은 조의 앞뒤 항 + 원문이 참조하는 조항 + 당사자·준거법 + 사용자 답변을 AI 에 주고,
     판단·위험도·조치 유형·쉬운 설명·**원문 언어의** 최소 수정안을 받는다.
  3. 받은 수정안을 코드로 검증한다: 고칠 문장이 원문에 그대로 있는가, 계약 언어와 같은가, 기존 금액·비율·기간을
     지우지 않는가, "…" 로 잘리지 않았는가, 원문·답변에 없는 숫자는 협의용 표시로 남겼는가.
  4. 검증을 통과한 수정안만 확정 수정안으로, 나머지는 "법무 추가 확인 중" 으로 내보낸다.
결과는 clause_results 와 같은 모양의 finding 이며, 같은 조항의 다른 지적은 이 판단으로 하나로 모은다(화면·문서가 한 판단).
"""
from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from runtime.ai.enhance import _build_request, _try_json
from runtime.ai.provider import AIProvider
from runtime.ai.safe import sanitize_error_message
from runtime.review.clause_label import clause_path_key, clause_path_relation

logger = logging.getLogger(__name__)

ID_PREFIX = "rq"
CATEGORY_BY_ACTION = {
    "필수수정": "필수수정", "권장수정": "권장수정", "체결 전 확인": "체결 전 확인",
    "사업부 결정": "사업부 결정", "현행 유지": "현행 유지",
}
STATUS_PENDING = "법무 추가 확인 중"

_RX_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*(\S.*)$")
_RX_CITE = re.compile(
    r"제\s*\d{1,4}(?:\s*\.\s*\d{1,3})?\s*조(?:\s*의\s*\d{1,3})?(?:\s*제?\s*\d{1,3}\s*항)?(?:\s*제?\s*\d{1,3}\s*호)?"
    r"|(?:Article|Section|Clause)\s+\d{1,4}(?:\.\d{1,3}){0,2}",
    re.IGNORECASE,
)
#: 원문이 다른 조항을 부르는 표현 — "clause 6", "clause 9.6", "Article 4.1", "제9조 제3항".
_RX_XREF = re.compile(
    r"(?:clause|article|section|art\.)\s+(\d{1,3}(?:\.\d{1,3})?)|제\s*(\d{1,3})\s*조(?:\s*제\s*(\d{1,2})\s*항)?",
    re.IGNORECASE,
)
_RX_TERMS = re.compile(
    r"\d+(?:[.,]\d+)?\s*%|(?:EUR|USD|KRW|€|\$|₩)\s*[\d.,]+|[\d.,]+\s*(?:원|유로|달러)"
    r"|\b\d+\s*(?:days?|weeks?|months?|years?|일|주|개월|년)\b|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|"
    r"twelve|twenty|thirty)\s+(?:\(\d+\)\s*)?(?:days?|weeks?|months?|years?)\b",
    re.IGNORECASE,
)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _attr(c: Any, name: str) -> str:
    return _s(c.get(name) if isinstance(c, dict) else getattr(c, name, ""))


def _ws(s: str) -> str:
    return " ".join(_s(s).split())


def _is_latin(text: str) -> bool:
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    return latin > 0 and latin >= 3 * max(1, hangul)


def _has_hangul(text: str) -> bool:
    return any("가" <= ch <= "힣" for ch in text)


# ── 1. 요청 블록 ──────────────────────────────────────────────────────────────

@dataclass
class RequestBlock:
    index: int
    head: str
    text: str
    cited: list[str] = field(default_factory=list)


def split_request_blocks(review_focus: str) -> list[RequestBlock]:
    """번호 요청과 그 아래 세부 줄(■·○·제안 문구)까지를 한 블록으로. 1부터 차례로 올라가는 번호만."""
    from runtime.review.user_request_answers import parse_numbered_requests_detailed

    numbered = parse_numbered_requests_detailed(review_focus or "")
    if not numbered:
        return []
    body = _s(review_focus).split("[사용자 확인 답변]")[0]
    lines = body.replace("\r", "").split("\n")
    starts: list[tuple[int, int, str]] = []
    want = {n: t for n, t, _ in numbered}
    for i, ln in enumerate(lines):
        m = _RX_NUMBERED.match(ln)
        if m and int(m.group(1)) in want and want[int(m.group(1))][:15] in " ".join(m.group(2).split()):
            if not any(s[0] == int(m.group(1)) for s in starts):
                starts.append((int(m.group(1)), i, want[int(m.group(1))]))
    out: list[RequestBlock] = []
    for k, (n, i, head) in enumerate(starts):
        end = starts[k + 1][1] if k + 1 < len(starts) else len(lines)
        text = "\n".join(ln.rstrip() for ln in lines[i:end]).strip()
        text = re.sub(r"\n{3,}", "\n\n", text)
        cites = [m.group(0) for m in _RX_CITE.finditer(head)]
        out.append(RequestBlock(index=n, head=head, text=text, cited=cites))
    return out


# ── 2. 조항 찾기 ──────────────────────────────────────────────────────────────

def resolve_cited(cites: list[str], clauses: list[Any] | None) -> list[Any]:
    """번호로 찾는다: 같은 항 > 그 조 안의 항 > 그 항을 품은 조. 낱말이 비슷하다고 다른 조항을 잇지 않는다."""
    buckets: dict[str, list[Any]] = {"exact": [], "inside": [], "contains": []}
    for c in clauses or []:
        dp = _attr(c, "display_path")
        if not dp or not _attr(c, "text").strip():
            continue
        rels = {clause_path_relation(w, dp) for w in cites}
        for rel in ("exact", "inside", "contains"):
            if rel in rels:
                buckets[rel].append(c)
                break
    for rel in ("exact", "inside", "contains"):
        if buckets[rel]:
            return buckets[rel]
    return []


def recheck_in_text(cite: str, contract_text: str) -> str:
    """색인에서 못 찾은 조항을 문서 전체에서 다시 찾는다(줄 머리의 "6.5", "제6조"). 찾으면 그 줄부터의 원문."""
    key = clause_path_key(cite)
    if not key:
        return ""
    num = ".".join(key[:2]) if len(key) >= 2 else key[0]
    pats = [rf"(?m)^\s*{re.escape(num)}\.?\s+\S"]
    if len(key) == 1:
        pats.append(rf"(?m)^\s*제\s*{re.escape(key[0])}\s*조")
    for p in pats:
        m = re.search(p, contract_text or "")
        if m:
            return contract_text[m.start(): m.start() + 900]
    return ""


def context_clauses(target: Any, clauses: list[Any] | None, *, limit: int = 6) -> list[Any]:
    """같은 조의 바로 앞뒤 항 + 원문이 참조하는 조항."""
    seq = [c for c in clauses or [] if _attr(c, "display_path")]
    ids = [_attr(c, "clause_id") for c in seq]
    out: list[Any] = []
    tid = _attr(target, "clause_id")
    if tid in ids:
        i = ids.index(tid)
        for j in (i - 1, i + 1):
            if 0 <= j < len(seq) and _attr(seq[j], "article_number") == _attr(target, "article_number"):
                out.append(seq[j])
    for m in _RX_XREF.finditer(_attr(target, "text")):
        ref = m.group(1) or (f"{m.group(2)}.{m.group(3)}" if m.group(3) else m.group(2))
        for c in resolve_cited([f"Article {ref}"], seq):
            if _attr(c, "clause_id") != tid and c not in out:
                out.append(c)
    return out[:limit]


#: 법률 주제 — 근거 조항이 같은 주제를 다루는지(세금 조항을 A/S 보호 근거로 드는 일 방지), 다른 조의 관련 조항 찾기.
TOPICS: dict[str, re.Pattern[str]] = {k: re.compile(v, re.I) for k, v in {
    "tax": r"\btax|withhold|세금|원천징수|부가가치세|과세",
    "insurance": r"insur|보험",
    "indemnity": r"indemnif|hold\s+harmless|\bdefend\b|recourse|면책|구상",
    "liability": r"\bliab|damages?\b|손해배상|책임\s*제한",
    "ip": r"proprietary\s+right|intellectual|infring|patent|trademark|design\s+right|지식재산|침해|상표|디자인권",
    "termination": r"terminat|expir|wind[- ]down|sell[- ]off|종료|해지|만료",
    "after_sales": r"after[- ]sales|warrant|spare\s+part|repair|A/S|하자\s*보수|부품",
    "price": r"royalt|reimbursement|remuneration|\bprice\b|invoice|로열티|대금|가격|청구",
    "license": r"licen[cs]|right\s+to\s+use|usage|\breference\b|사용권|라이선스|이용\s*허락",
    "renewal": r"\bextend|extension|renew|연장|갱신",
    "penalty": r"penalt|liquidated|위약금|손해배상액의\s*예정",
    "law": r"governed|jurisdiction|\bcourt\b|arbitrat|준거법|관할|중재",
    "assignment": r"\btransfer|assign|sub-?licen|양도",
}.items()}
#: 관련 주제 — 이 주제 조항을 볼 때 다른 조의 이런 주제 조항도 함께 본다.
_RELATED = {"indemnity": ("ip", "liability", "insurance", "after_sales"), "insurance": ("indemnity", "liability"),
            "termination": ("license", "price", "after_sales"), "renewal": ("termination",),
            "price": ("price",), "penalty": ("liability",), "license": ("termination", "assignment"),
            "ip": ("indemnity",)}


def topics_of(text: str) -> dict[str, int]:
    return {k: n for k, rx in TOPICS.items() if (n := len(rx.findall(text or "")))}


def primary_topic(text: str) -> str:
    t = topics_of(text)
    return max(t, key=t.get) if t else ""


def related_clauses(target: Any, clauses: list[Any] | None, exclude: list[Any], *, limit: int = 4) -> list[Any]:
    """다른 조에서 같은·관련 주제를 주로 다루는 조항(예: 9.9 면책 ↔ 10.1 지식재산 침해 면책, 13.3 종료 ↔ 4.1 로열티 기간)."""
    want: set[str] = set()
    tt = topics_of(_attr(target, "text"))
    for k in sorted(tt, key=tt.get, reverse=True)[:2]:
        want |= {k, *(_RELATED.get(k) or ())}
    art = _attr(target, "article_number")
    scored: list[tuple[int, Any]] = []
    for c in clauses or []:
        if c is target or c in exclude or not _attr(c, "display_path") or _attr(c, "article_number") == art:
            continue
        p = primary_topic(_attr(c, "text"))
        if p and p in want:
            scored.append((topics_of(_attr(c, "text"))[p], c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:limit]]


_RX_REF = re.compile(r"(?:Article|Section|Clause|clause|제)\s*(\d{1,3}(?:\.\d{1,3})?)\s*(?:조)?")


def guard_protection(data: dict[str, Any], *, issue_text: str, clauses: list[Any] | None) -> list[str]:
    """이미 있는 보호의 근거 조항이 실재하고 같은 주제를 다루는지. 아니면 그 문장을 빼고 '근거 확인 필요' 로 남긴다."""
    prot = _s(data.get("existing_protection")).strip()
    if not prot:
        return []
    refs = [_s(r) for r in data.get("existing_protection_refs") or [] if _s(r).strip()]
    nums = list(dict.fromkeys([m.group(1) for r in refs for m in _RX_REF.finditer(r)]
                              + [m.group(1) for m in _RX_REF.finditer(prot)]))
    issue_topics = set(topics_of(issue_text))
    dropped: list[str] = []
    for n in nums:
        found = resolve_cited([f"Article {n}"], clauses)
        if not found:
            dropped.append(f"Article {n}(계약에 없음)")
            continue
        p = primary_topic(" ".join(_attr(c, "text") for c in found))
        if p and issue_topics and p not in issue_topics:
            dropped.append(f"{_attr(found[0], 'display_path')}({p} 조항 — 이 쟁점의 근거 아님)")
    if dropped:
        bad = {re.sub(r"\D", "", d.split("(")[0]) for d in dropped}
        keep = [s for s in re.split(r"(?<=[.。])\s+|\n", prot)
                if s.strip() and not ({re.sub(r"\D", "", m.group(1)) for m in _RX_REF.finditer(s)} & bad)]
        data["existing_protection"] = " ".join(keep)
        data["legal_limits"] = (_s(data.get("legal_limits")) + " 근거 확인 필요: " + ", ".join(dropped)
                                + " 은(는) 보호 근거에서 뺐다.").strip()
    elif not nums:
        data["existing_protection"] = prot + " (근거 조항 확인 필요)"
    return dropped


_MEASURE_HINTS = (
    (re.compile(r"상한|한도|\bcap\b"), re.compile(r"exceed|\bcap\b|maximum|aggregate|in no event|한도|상한|초과", re.I), "누적·총액 상한"),
    (re.compile(r"존속|계속\s*(?:유효|적용)|survive"), re.compile(r"surviv|continue|remain\s+in\s+(?:full\s+)?force|존속|계속", re.I), "존속"),
    (re.compile(r"부당하게|unreasonabl"), re.compile(r"unreasonabl|부당", re.I), "부당 거절 금지"),
)


def measure_problems(data: dict[str, Any], edits: list["VerifiedEdit"]) -> list[str]:
    """설명(조치)이 요구한 것이 수정 문구에 실제로 있는지 — 없으면 이유가 있어야 한다."""
    probs: list[str] = []
    live = [e for e in edits if not e.held]
    text = " ".join(e.new_text for e in live)
    for i, m in enumerate(data.get("measures") or []):
        if not isinstance(m, dict) or not _s(m.get("measure")).strip():
            continue
        ix = m.get("edit_index")
        ok_ix = isinstance(ix, int) and 0 <= ix < len(edits) and not edits[ix].held
        if not ok_ix and not _s(m.get("not_reflected_reason")).strip():
            probs.append(f"measures[{i}] '{_s(m.get('measure'))[:40]}' 이 반영된 edits 가 없고 미반영 이유도 없음")
    said = " ".join(_s(data.get(k)) for k in ("action", "answer"))
    reasons = " ".join(_s(m.get("not_reflected_reason")) for m in data.get("measures") or [] if isinstance(m, dict))
    if _s(data.get("action_type")) in ("필수수정", "권장수정") and live:
        for ask, has, name in _MEASURE_HINTS:
            if ask.search(said) and not has.search(text) and not ask.search(reasons):
                probs.append(f"설명은 '{name}' 을 요구하는데 수정 문구에 없음 — 문구에 넣거나 measures 에 미반영 이유(협상 미확정 등)를 적을 것")
    if re.search(r"unreasonabl", text, re.I) and re.search(r"\boption\b|right\s+to\s+extend|automatic(?:ally)?\s+(?:renew|extend)",
                                                          text, re.I) and re.search(r"extend|renew", text, re.I):
        probs.append("연장 선택권 구조와 '동의를 부당하게 거절하지 못함' 구조가 한 수정안에 섞임 — 하나만 쓸 것")
    return probs


_RX_PRICE_DEF = re.compile(r"price['’\"]?\s*(?:shall\s+)?means?\b|['‘\"][^'’\"]{0,40}price['’\"]\s+(?:shall\s+)?mean", re.I)
_RX_CATCH_ALL = re.compile(r"any\s+and\s+all|all\s+third[- ]party\s+claims|in\s+connection\s+with|no\s+right\s+of\s+recourse"
                           r"|harmless\s+from\s+all", re.I)
_RX_WIND_DOWN = re.compile(r"sell[- ]off|wind[- ]down|after\s+(?:the\s+)?(?:termination|expiration)", re.I)
_RX_RIGHTS_SURVIVE = re.compile(r"licen[cs]|right\s+to\s+use|surviv|continue\s+to\s+(?:use|apply)|remain\s+in\s+(?:full\s+)?force"
                                r"|entitled\s+to\s+(?:use|refer)", re.I)
_RX_TERM_LIMIT = re.compile(r"until\s+the\s+end\s+of\s+the\s+(?:contract|agreement)(?:\s+(?:period|term))?", re.I)


def _sentences_en(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", _ws(text)) if len(s.strip()) > 20]


#: 가격 정의가 할인·리베이트 처리(공제 전/후)를 정하지 않음 — 합의 전 값은 문구에 넣지 않고 확인 사항으로 남긴다(2026-11-03 ③).
PRICE_DISCOUNT_GAP = ("가격 정의가 할인·리베이트를 공제하기 전 금액인지 후 금액인지 정하지 않음 — 합의된 기준이 없으면 "
                      "[공제 전 / 공제 후] 선택지로 두거나 checks 에 확인 사항으로 남길 것")
PRICE_DISCOUNT_CHECK = ("dealer supply price 가 딜러 할인·리베이트를 공제하기 전 금액인지 후 금액인지 상대방과 확인 "
                        "(이메일 합의 정의에는 공제 언급 없음 — 순청구액 기준으로 볼지 함께 정함)")


def drafting_problems(data: dict[str, Any], edits: list["VerifiedEdit"], *, targets: list[Any], ctx: list[Any],
                      request_text: str, answers_text: str) -> list[str]:
    """계약 언어 수정안의 구조 점검 — 설명이 아니라 문구가 거래 구조와 모순되지 않는지(2026-11-02 Norden ②③⑤⑥).

    낱말 하나로 판단하지 않고, 문구가 실제로 다루는 법률 구조(가격 정의·포괄 면책·종료 후 처리·누적 상한)가 있을 때만 본다.
    """
    probs: list[str] = []
    live = [e for e in edits if not e.held]
    text = " ".join(e.new_text for e in live)
    reasons = " ".join(_s(m.get("not_reflected_reason")) for m in data.get("measures") or [] if isinstance(m, dict))
    checks = " ".join(_s(c.get("what")) for c in data.get("checks") or [] if isinstance(c, dict))
    asked = request_text + " " + answers_text
    # ③ 가격·로열티 기준 정의
    for e in live:
        if not _RX_PRICE_DEF.search(e.new_text):
            continue
        if re.search(r"ex-?factory|list\s+price|price\s+list", e.new_text, re.I) and re.search(r"discount|rebate|deduct", e.new_text, re.I) \
                and not re.search(r"\[[^\]]*(?:discount|rebate|deduct)[^\]]*\]", e.new_text, re.I):
            probs.append("가격 정의가 공장도가(목록가) 기준과 할인·리베이트 공제 후 순청구액 기준을 함께 정함 — 기준을 하나로 정하고, "
                         "공제 여부는 합의 전이면 [option] 선택지로 두고 undecided 에 적을 것")
        if re.search(r"discount|rebate", e.new_text, re.I) and not re.search(r"discount|rebate|할인|리베이트|공제", asked, re.I) \
                and not re.search(r"\[[^\]]*(?:discount|rebate)[^\]]*\]", e.new_text, re.I):
            probs.append("요청·답변에 없는 할인·리베이트 공제를 확정 문구로 넣음 — 합의하지 않은 공제는 [option] 선택지·빈칸으로")
        if re.search(r"ex-?factory|list\s+price|price\s+list|supplied\s+to\s+dealers", e.new_text, re.I) \
                and not re.search(r"discount|rebate|deduct|\bnet\b", e.new_text, re.I) \
                and not re.search(r"할인|리베이트|공제|discount|rebate", checks + reasons, re.I):
            probs.append(PRICE_DISCOUNT_GAP)
        if not re.search(r"direct|end[- ]customer|affiliat|without\s+(?:a\s+)?dealer", e.new_text, re.I) \
                and not re.search(r"직접\s*판매|계열사|direct|affiliat", checks + reasons, re.I):
            probs.append("딜러를 거치지 않는 직접판매·계열사 판매의 기준가가 정의에 없음 — 문구로 정하거나(값 미확정이면 [●]) checks 에 확인 사항으로 남길 것")
    # ② 포괄 면책·구상권 제한 — 면책 조항이면 그 문장들을 검토했는지
    if any(TOPICS["indemnity"].search(_attr(t, "text")) for t in targets) and live:
        broad = [s for t in targets for s in _sentences_en(_attr(t, "text")) if _RX_CATCH_ALL.search(s)
                 and TOPICS["indemnity"].search(s)]
        touched = [s for s in broad if any(e.target_text and (e.target_text[:60] in s or s[:60] in e.target_text) for e in live)]
        untouched = [s for s in broad if s not in touched]
        if untouched and not re.search(r"포괄|catch|in connection|all third|구상", reasons + checks, re.I):
            rel = [_attr(c, "display_path") for c in ctx if TOPICS["indemnity"].search(_attr(c, "text"))
                   and _attr(c, "article_number") != _attr(targets[0], "article_number")]
            probs.append("면책 조항의 포괄 면책·구상권 제한 문장을 검토하지 않음: " + " / ".join(f"'{s[:110]}'" for s in untouched[:3])
                         + " — 우리 귀책 없는 손해·상대방 디자인/지식재산 원인 손해까지 떠안지 않게 범위를 한정하거나, 유지 이유를 measures 에"
                         + (f". 같은 사안을 다루는 {', '.join(rel)} 와 정합성을 맞출 것" if rel else ""))
    # ⑤ 종료 후 처리 — 사용권 존속, 다른 조항의 '계약기간 종료까지' 와의 충돌
    if any(_RX_WIND_DOWN.search(e.new_text) for e in live):
        if not _RX_RIGHTS_SURVIVE.search(text):
            probs.append("종료 후 허용 활동(확정 주문·재고 판매·A/S 부품)에 필요한 사용권(디자인·표시 사용 등)의 존속이 문구에 없음")
        for c in ctx:
            m = _RX_TERM_LIMIT.search(_ws(_attr(c, "text")))
            if not m:
                continue
            hit = any(e.target_text and e.target_text in _ws(_attr(c, "text")) for e in live)
            if not hit and _attr(c, "display_path") not in reasons:
                probs.append(f"{_attr(c, 'display_path')} 의 '{m.group(0)}' 이 종료 후 로열티·의무 존속과 충돌 — 그 조항도 edits 로 고치거나 "
                             "measures 에 이유를 적을 것")
    # ⑥ 누적·총액 상한
    said = " ".join(_s(data.get(k)) for k in ("action", "answer"))
    if re.search(r"누적|총액|합계|aggregate|cumulative", said, re.I) and live \
            and not re.search(r"aggregate|cumulative|in\s+total|total\s+amount", text, re.I) \
            and not re.search(r"누적|총액|합계", reasons):
        probs.append("설명은 누적·총액 상한을 말하는데 수정 문구에 없음 — 상한 문장(금액 [●])을 넣거나 measures 에 '협상 미확정' 이유를 적을 것")
    return probs


def restore_number_notation(target: str, new: str) -> str:
    """바꾸지 않은 금액의 표기를 원문대로 — "EUR 50.000" 을 "EUR 50,000" 으로 바꿔 쓰면 원문 표기가 달라진다."""
    def key(x: str) -> str:
        return re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", re.sub(r"\s+", "", x.lower()))

    for m in _RX_TERMS.finditer(target or ""):
        raw = m.group(0)
        if raw in new:
            continue
        for m2 in _RX_TERMS.finditer(new):
            if key(m2.group(0)) == key(raw) and m2.group(0) != raw:
                new = new.replace(m2.group(0), raw)
    return new


_RX_FORUM_CLAUSE = re.compile(r"governed\s+by|governing\s+law|applicable\s+law|law\s+shall\s+apply|laws?\s+of\s+the\s+(?:federal\s+)?republic"
                       r"|exclusive\s+(?:place\s+of\s+)?jurisdiction|place\s+of\s+jurisdiction|\bvenue\b|arbitrat"
                       r"|준거법|전속\s*관할|관할\s*법원|중재", re.I)
_RX_CAPPED = re.compile(r"\blimit|\bcap\b|exceed|maximum|in\s+no\s+event|한도|상한", re.I)


def severity_guard(risk: str, action_type: str, r: "RequestedReview") -> tuple[str, str]:
    """AI 등급에 대한 최소한의 법률 구조 기준(2026-11-02 Norden: 관할 HIGH·무상한 면책 MEDIUM 의 역전).

    · 준거법·관할 조항: 변경 요구는 상대방 수용이 필요한 협상 사항 — HIGH 로 두지 않는다(MEDIUM 상한).
    · 제3자 청구 전부를 우리가 면책하는 포괄 면책에 상한이 없으면: 고치라는 판단인 한 HIGH·필수수정(하한).
    """
    text = " ".join(_attr(t, "text") for t in r.targets)
    # 준거법·관할 '조항' 인지는 그 조항이 실제로 준거법·관할을 정하는지로 본다. "court having jurisdiction" 이 한 번 나오는
    # 위약금 조항(Norden 6.5)이 주제어 개수로 관할 조항이 되어 HIGH 필수수정 → MEDIUM 사업부 결정으로 깎였다(2026-11-03).
    tt = topics_of(text)
    forum = bool(_RX_FORUM_CLAUSE.search(text)) and not any(tt.get(k) for k in ("penalty", "indemnity", "liability", "price"))
    if forum and risk == "HIGH":
        risk = "MEDIUM"
    if forum and action_type in ("필수수정", "사업부 결정"):
        # 2026-11-03 지시 4항: 준거법·관할도 법무 권고안과 불수용 시 대안을 먼저 낸다 — 상대방 수용 여부를 사업부 결정으로 넘기지 않는다.
        action_type = "권장수정"
    broad = [s for s in _sentences_en(text) if _RX_CATCH_ALL.search(s) and TOPICS["indemnity"].search(s)]
    if broad and not any(_RX_CAPPED.search(s) for s in _sentences_en(text) if TOPICS["indemnity"].search(s)
                         and not re.search(r"do(?:es)?\s+not\s+limit", s, re.I)) \
            and action_type in ("필수수정", "권장수정"):
        risk, action_type = "HIGH", "필수수정"
    return risk, action_type


def blank_invented_numbers(new: str, known: str) -> tuple[str, list[str]]:
    """원문·요청·답변에 없는 숫자를 괄호에 넣어 제안하면("[30] days") 합의하지 않은 값이 된다 — [●] 로 비우고 제안값은 미확정 조건에 적는다."""
    notes: list[str] = []

    def sub(m: re.Match[str]) -> str:
        num, unit = m.group(1), (m.group(2) or "").strip()
        if re.search(rf"(?<![\d.,]){re.escape(num)}(?![\d.,])", known):
            return m.group(0)
        notes.append(f"[●] {unit} — 원문·요청에 없는 값(제안 예시 {num} {unit}, 협의 필요)".replace("  ", " "))
        return "[●]" + (" " + unit if unit else "")

    out = re.sub(r"\[\s*(\d[\d.,]*)\s*\]\s*(days?|weeks?|months?|years?|%|EUR|USD)?", sub, new)
    return out, notes


REQUEST_STATUSES = ("반영됨", "부분 반영", "미반영", "사업 판단 필요")


_CALIBRATE_SYSTEM = """너는 우리 회사 사내변호사 책임자다. 같은 계약에서 나온 쟁점 목록 전체를 보고 위험도·조치 구분·요청 반영 상태를 최종 조정한다.
기준: 우리 회사의 역할과 거래 목적, 금전 부담(상한 유무·규모), 권리 확보(제조·판매·사용), 종료 시 손실.
- HIGH = 그대로 서명하면 상한 없는·중대한 금전 부담, 핵심 권리 상실, 종료 시 큰 손실이 생기는 것. action_type 은 필수수정.
- 상대방에게 더 유리한 조건을 요구하는 개선(상대방 책임 확대, 관할·준거법 변경, 동의 요건 완화 등)은 대개 MEDIUM 권장수정(협상 권고)이다.
- 사실·상대방 확인만 필요한 것은 체결 전 확인, 사업적 선택이 필요한 것은 사업부 결정이다.
- 모든 쟁점을 HIGH 로 두지 않는다. 위험의 크기를 서로 비교해 정한다.
- request_status(요청이 있는 쟁점만): 요청한 조건·문구가 현재 원문에 이미 있으면 반영됨, 일부만 있으면 부분 반영, 없으면 미반영, 법무 판단보다 사업적 선택이 핵심이면 사업 판단 필요.
JSON 하나만: {"items": [{"key": "...", "risk": "HIGH|MEDIUM|LOW", "action_type": "필수수정|권장수정|체결 전 확인|사업부 결정|현행 유지", "request_status": "", "why": "한 줄"}]}"""


def calibrate_reviews(provider: AIProvider | None, *, model: str, reviews: list["RequestedReview"], facts: str,
                      timeout_sec: float = 120.0) -> dict[str, Any]:
    """계약 전체의 쟁점을 한 번에 비교해 위험도·조치·요청 상태를 조정한다(일반 개선사항의 HIGH 부풀림 방지)."""
    live = [r for r in reviews if r.data and r.targets]
    if provider is None or len(live) < 2:
        return {"skipped": True}
    rows = []
    for r in live:
        d = r.data
        new = " / ".join(e.new_text[:260] for e in r.edits if not e.held)
        rows.append({"key": str(r.block.index), "clause": ", ".join(r.paths), "request": r.block.head[:160]
                     if r.block.index < FINDING_INDEX_BASE else "", "issue": _s(d.get("issue_title")),
                     "current": _s(d.get("current"))[:300], "risk_to_us": _s(d.get("risk_to_us"))[:300],
                     "proposed_edit": new, "now": {"risk": _s(d.get("risk")), "action_type": _s(d.get("action_type")),
                                                   "request_status": _s(d.get("request_status"))}})
    user = "[거래 사실]\n" + facts + "\n\n[쟁점 목록]\n" + json.dumps(rows, ensure_ascii=False, indent=1)
    try:
        resp = provider.complete(_build_request(model=model, system=_CALIBRATE_SYSTEM, user=user,
                                                timeout_sec=timeout_sec, max_tokens=2500, temperature=0.1))
        out = _try_json(getattr(resp, "content", "") or "")
    except Exception as exc:  # noqa: BLE001
        return {"error": sanitize_error_message(str(exc))}
    if not isinstance(out, dict):
        return {"error": "응답을 읽지 못함"}
    by = {str(r.block.index): r for r in live}
    changed = []
    for it in out.get("items") or []:
        r = by.get(_s(it.get("key")))
        if r is None:
            continue
        risk = _s(it.get("risk")).upper()
        act = _s(it.get("action_type")).strip()
        if risk not in ("HIGH", "MEDIUM", "LOW") or act not in CATEGORY_BY_ACTION:
            continue
        if act == "현행 유지" and any(not e.held for e in r.edits):
            act = "권장수정"   # 검증된 수정안이 있는 쟁점을 조정 단계가 지우지 않는다
        before = (_s(r.data.get("risk")), _s(r.data.get("action_type")), _s(r.data.get("request_status")))
        r.data["risk"], r.data["action_type"] = risk, act
        if _s(it.get("request_status")).strip() and r.block.index < FINDING_INDEX_BASE:
            r.data["request_status"] = _s(it.get("request_status")).strip()
        r.data["calibration_note"] = _s(it.get("why"))
        changed.append({"key": r.block.index, "before": before, "after": (risk, act, _s(r.data.get("request_status")))})
    return {"changed": changed}


def norm_request_status(v: Any, verdict: str) -> str:
    # 판단이 '사업부 결정' 이면 요청 상태도 사업 판단 필요 하나로 답한다 — 요청이 "리스크 검토" 였던 16.8(준거법)이
    # 원문에 독일법이 '있다' 는 이유로 '반영됨' 으로 표시됐다(2026-11-03). 반영됨은 요청한 조건이 원문에 들어 있다는 뜻이다.
    if _s(verdict).strip().startswith("사업"):
        return "사업 판단 필요"
    t = re.sub(r"\s+", "", _s(v))
    for s in REQUEST_STATUSES:
        if re.sub(r"\s+", "", s) == t:
            return s
    if "부분" in t:
        return "부분 반영"
    if "사업" in t or "결정" in t:
        return "사업 판단 필요"
    if "미반영" in t or "누락" in t:
        return "미반영"
    if verdict.startswith("현행"):
        return "반영됨"
    return "사업 판단 필요" if verdict.startswith(("사업", "체결")) else "미반영"


_COUNTRIES = ("Austria", "Germany", "Switzerland", "South Korea", "Korea", "Republic of Korea", "China", "Japan",
              "United States", "USA", "United Kingdom", "France", "Italy", "Netherlands", "Singapore", "Hong Kong",
              "Taiwan", "Vietnam", "Spain", "Sweden", "Denmark", "Belgium", "Canada", "Australia")
_KO_COUNTRY = {"Austria": "오스트리아", "Germany": "독일", "Switzerland": "스위스", "South Korea": "한국", "Korea": "한국",
               "China": "중국", "Japan": "일본", "United States": "미국", "USA": "미국", "United Kingdom": "영국",
               "France": "프랑스", "Italy": "이탈리아", "Netherlands": "네덜란드", "Singapore": "싱가포르"}
_TEXT_FIELDS = ("answer", "current", "risk_to_us", "action", "existing_protection", "legal_limits")


def _counterparty_country(facts: str) -> str:
    m = re.search(r"\[상대방\][^\n]*\n\s*·[^\n]*소재 국가\(원문 표시\):\s*([A-Za-z ]+)", facts or "")
    return _KO_COUNTRY.get(m.group(1).strip(), "") if m else ""


def _wrong_nationality(text: str, country: str) -> list[str]:
    others = sorted({v for v in _KO_COUNTRY.values() if v not in (country, "한국")})
    rx = re.compile(rf"(?:상대방|[A-Z]{{2,6}}|상대\s*회사|상대방\s*회사)[^.。\n]{{0,12}}?({'|'.join(others)})\s*(?:계|회사|법인|기업)"
                    rf"|({'|'.join(others)})계\s*(?:상대방|회사|법인|기업)?")
    return [m.group(0) for m in rx.finditer(text or "")]


def nationality_problems(data: dict[str, Any], facts: str) -> list[str]:
    """상대방 소재국을 원문 표시와 다르게 적었는가(예: 오스트리아 법인을 '독일계' — 준거법 국가와 혼동)."""
    country = _counterparty_country(facts)
    if not country:
        return []
    bad = [w for k in _TEXT_FIELDS for w in _wrong_nationality(_s(data.get(k)), country)]
    return [f"'{w}' — 상대방 소재국은 원문 표시대로 {country}다(준거법 국가와 혼동하지 말 것)" for w in dict.fromkeys(bad)]


def fix_nationality(data: dict[str, Any], facts: str) -> None:
    country = _counterparty_country(facts)
    if not country:
        return
    for k in _TEXT_FIELDS:
        v = _s(data.get(k))
        for w in _wrong_nationality(v, country):
            v = v.replace(w, re.sub(r"(독일|스위스|중국|일본|미국|영국|프랑스|이탈리아|네덜란드|싱가포르|오스트리아)", country, w))
        if v != _s(data.get(k)):
            data[k] = v


_RX_LAW = re.compile(r"governed\s+by|law\s+shall\s+apply|laws?\s+of\s+[A-Z]|준거법|에\s*따라\s*해석", re.IGNORECASE)
_RX_FORUM = re.compile(r"jurisdiction|arbitrat|court|관할|중재", re.IGNORECASE)


def deal_facts(*, contract_text: str, clauses: list[Any] | None, parties: list[Any] | None,
               our_display: str) -> str:
    """AI 에 줄 공통 사실 — 원문에서 그대로 가져온 것만(당사자 표시 줄, 준거법·관할 조항, 문서 언어)."""
    lines: list[str] = []
    head = _s(contract_text)[:4000].splitlines()
    for p in parties or []:
        name = _s(getattr(p, "written_name", "") or getattr(p, "legal_entity_name", ""))
        if not name:
            continue
        src = next((ln.strip() for ln in head if name and name in ln), "")
        mark = " [우리 회사]" if getattr(p, "is_our_company", False) else " [상대방]"
        lines.append(f"- 당사자 {_s(getattr(p, 'label', ''))}: {name}{mark}" + (f" — 원문 표시: {src}" if src else ""))
        country = next((c for c in _COUNTRIES if re.search(rf"\b{c}\b", src)), "") if src else ""
        if country:
            lines.append(f"  · {name} 소재 국가(원문 표시): {country}")
    if our_display:
        lines.append(f"- 우리 회사: {our_display}")
    for c in clauses or []:
        t = _ws(_attr(c, "text"))
        if _RX_LAW.search(t) and _RX_FORUM.search(t):
            lines.append(f"- 준거법·분쟁해결 조항 [{_attr(c, 'display_path')}]: {t[:600]}")
            break
    lines.append("- 계약서 언어: " + ("영문" if _is_latin(_s(contract_text)[:20000]) else "국문"))
    return "\n".join(lines)


# ── 3. AI 검토 ───────────────────────────────────────────────────────────────

_SYSTEM = """너는 우리 회사(아래 '우리 회사') 사내변호사다. 담당자가 계약서의 특정 조항을 짚어 물은 요청 하나에 답한다.

판단 원칙
- 지목된 조항 원문을 먼저 읽고, 같은 조의 앞뒤 항과 원문이 참조하는 조항까지 함께 본다. 다른 조항의 낱말이 비슷하다고 그 조항으로 답하지 않는다.
- 기존 보호(이미 있는 상한·예외·절차)를 먼저 인정하고, 부족한 부분만 말한다.
- 이 계약의 준거법이 외국법이면 한국법의 결론(무효·감액·약관규제법 등)을 그대로 적용하지 않는다. 확인하지 못한 외국법 판단은 legal_limits 에 한계로 적는다.
- 사용자 답변을 포괄적 위험 수용으로 넓히지 않는다. 자료가 없다는 것을 안전하다는 뜻으로 읽지 않는다.
- 위험도(HIGH/MEDIUM/LOW)와 조치 유형(필수수정/권장수정/체결 전 확인/사업부 결정/현행 유지)을 구분한다. 고칠 필요가 없으면 '현행 유지'다.

수정안 원칙(edits)
- 계약서 원문 언어로 쓴다(영문 계약 → 영문). 설명(answer·current·risk_to_us·action)은 한국어로 쓴다.
- 최소 수정: 바꿀 문장만 바꾸거나 문장·항을 덧붙인다. 로열티율·지급기한·권리 범위·지역·기간·담보·면책 등 요청과 무관한 합의조건을 지우거나 바꾸지 않는다.
- 정의를 보완할 때는 기존 문장을 지우지 말고 정의 문장을 덧붙인다(mode=insert_after). 계약에 정의 조항이 없으면 그 용어가 처음 쓰인 지목 조항 문장 바로 뒤에 덧붙인다 — 계약에 없는 조항("1. Definitions" 등)을 target_text 로 쓰지 않는다.
- 수정안이 요청 목적을 실제로 이루는지 스스로 확인한다. 예: "위반이 없는 한 자동 연장" 요청이면 상대방이 임의 통지만으로 연장을 막을 수 있는 문구를 쓰지 않는다(우리 쪽 해지·불갱신 선택권은 남겨도 된다).
- 당사자의 국적·소재지는 [거래 사실]의 원문 표시대로 쓴다. 준거법 국가와 당사자 소재국을 섞지 않는다.
- 바꾸지 않는 숫자·금액은 원문 표기 그대로 둔다(예: "EUR 50.000" 을 "EUR 50,000" 으로 고치지 않는다).
- existing_protection 에는 우리에게 유리하게 이미 작동하는 보호만 적는다. 불리한 점은 risk_to_us 에 적는다.
- target_text 는 지목 조항 원문에서 **글자 그대로** 복사한 문장(교체·삭제 대상, 또는 그 뒤에 덧붙일 문장)이다. 줄바꿈은 공백 하나로 써도 된다.
- new_text 는 계약서에 그대로 넣을 완성 문장이다. "…", "..." 로 줄이지 않는다. 계약의 정의어(예: Customer, NDG, Design Product)를 쓴다 — 담당자가 준 문구의 다른 이름(SIDIZ, Licensed Products 등)은 계약 정의어로 바꾸고 changed_terms 에 적는다.
- 원문·담당자 요청·답변에 없는 금액·기간·비율은 지어내지 말고 "[●] months" 처럼 괄호 빈칸으로 두고 undecided 에 적는다.
- 상대방 소유 권리·라이선스의 범위·기간·지역·종료 규정을 넘어서는 무제한 권리 문구를 넣지 않는다.
- 새 항을 만들면 mode=new_paragraph, new_paragraph_number 에 번호(예: 13.4)를 적고 target_text 는 비운다.
- 합의하지 않은 가격·공제·책임 범위·금액을 확정 문구로 넣지 않는다. 필요하면 "[●]" 빈칸이나 "[option A / option B]" 선택지로 두고 undecided 에 적는다.

위험도·조치 구분(일반 개선사항을 HIGH 로 올리지 않는다)
- HIGH 는 그대로 서명하면 우리 회사에 상한 없는·중대한 금전 부담, 핵심 권리(제조·판매·사용) 상실, 종료 시 큰 손실이 생기는 경우뿐이며, 이때 action_type 은 필수수정이다.
- 협상으로 개선하면 좋은 사항은 MEDIUM 또는 LOW 의 권장수정(협상 권고)이다. 사실·상대방 확인만 필요한 것은 체결 전 확인(사실 확인)이다.
- request_status 는 담당자가 요청한 조건·문구가 **현재 계약 원문**에 반영되어 있는지 하나만 고른다: 반영됨 / 부분 반영 / 미반영 / 사업 판단 필요.

계약 전체 정합성(함께 볼 조항에 다른 조의 관련 조항도 준다 — 꼭 대조한다)
- 근거·보호로 드는 조항은 그 쟁점과 같은 주제를 실제로 다루는 조항만 든다. 예: 세금·원천징수 조항은 A/S·재고·종료 후 처리의 보호 근거가 아니다. existing_protection_refs 에 근거 조항 번호를 적고, 원문에서 근거를 찾지 못하면 existing_protection 을 비운다.
- 가격·로열티 산정 기준을 정의할 때: 기준가(목록가인지 실제 청구액인지)를 하나로 정하고, 할인·리베이트·반품 공제 여부를 그 기준과 모순 없이 적는다(합의 근거가 없으면 선택지·빈칸). 딜러를 거치지 않는 직접판매·계열사 판매·무상 공급의 기준가도 함께 정하거나 확인 사항으로 남긴다. 청구·정산 시점 문장과 충돌하지 않게 한다.
- 배상·면책 조항은 그 조항 전체(면책 범위, 방어 의무, 포괄 면책 문구, 보험, 구상권 제한)를 함께 보고, 같은 사안을 다르게 정한 다른 조항(지식재산 침해 면책, 보증, 책임 제한)과 정합성을 맞춘다 — 상대방 귀책·상대방 디자인/지식재산이 원인인 손해까지 우리가 떠안는 문구를 남기지 않는다.
- 책임 조항은 '누가 / 누구에게 / 어떤 원인으로 / 어떤 책임(배상·방어·면책)을 / 어떤 예외·한도로' 로 나눠 쓴다. 같은 원인을 한 조항은 책임 있음, 다른 조항은 책임 없음으로 정하지 않는다 — 우리가 책임지기로 한 원인(예: 우리 제공 사양이 원인인 지식재산 침해)을 다른 조항의 면제 목록이 지우면 그 원인을 예외로 적거나 'subject to Article X' 로 우선 관계를 적는다. 일반 과실과 고의·중과실을 구분한다.
- 책임한도를 제안하면 건당 한도와 누적(연간 또는 계약 전체) 한도를 구분하고, 방어비용·변호사비용·배상·면책 금액 전부에, 보호대상자(계열사·임직원 등) 전원에 대한 책임에 적용되는지 문구로 정한다.
- 한글 설명(action·risk_to_us)과 수정 문구의 책임 방향이 같아야 한다. 'except', 'unless', 'not' 으로 의미가 뒤집히지 않았는지 다시 읽는다.
- 기간 연장은 두 구조를 구분한다: (1) 우리 회사의 연장 선택권(통지로 행사, 중대한 위반이 없을 것) 또는 자동 연장 (2) 상대방이 동의를 부당하게 거절·지연하지 못한다는 의무. "위반이 없으면 연장" 요청이면 (1)이고 (2)나 '양 당사자 동의' 로는 반영된 것이 아니다. 담당자가 '자동연장' 을 원하면 자동 연장으로 쓴다. 연장권자(또는 자동), 행사 방식·기한, 연장 기간·조건, 연장을 막을 수 있는 위반(중대한 위반)과 시정절차(서면 통지 후 시정기간 내 미시정), 상대방의 추가 동의가 필요 없다는 점을 모두 적는다.
- 종료 후 처리(확정 주문 이행·재고 판매·A/S 부품)를 허용하면 활동마다 기간·대상·필요한 사용권(디자인·표시 사용 등)·정산/보고 의무를 나눠 정하고, "계약기간 종료까지만" 같은 다른 조항 문구와 충돌하지 않게 연결한다(필요하면 그 조항도 edits 로 고친다). 로열티는 판매분에만 붙는다 — 무상 보증수리·부품 보관·무상 부품 공급에는 로열티가 없다고 명시하고, 로열티 문장에 '부품 공급' 같은 비판매 활동을 넣지 않는다. 종료 후 판매한 제품의 A/S 도 허용하고, A/S 사용권은 그 제품의 보증의무가 끝날 때까지 존속시킨다(보증보다 짧은 고정 상한 금지). 기존 지역·표시 제한(특정 지역에서 특정 표시 사용 금지 등)은 종료 후에도 그대로 적용된다고 적는다. 만료와 중도해지(해지 사유별) 가운데 어디에 적용되는지 적는다.
- 사용자가 주지 않은 통지기간·시정기간·금액은 [●] 로 두고 undecided 에 "제안값: 30 days(법무 제안, 미합의)" 처럼 제안값을 적는다 — 합의된 조건처럼 쓰지 않는다.
- 준거법·관할 같은 협상 조항도 법무 권고안을 먼저 낸다: recommendation(구체적 권고 — 예: 중립 중재지, 피고 소재지 관할), fallback(상대방이 거절할 때의 대안 또는 현행 유지 이유). 상대방이 받아들일지는 사업부 결정이 아니다.
- decisions 에는 사업부가 실제로 정할 것(거래조건·비용 부담·상대방이 거절하면 그래도 진행할지)만 쓴다. "상대방 동의 여부 확인", "법률 효력 확인" 은 decisions 가 아니라 checks 다.
- 위약금·손해배상 예정에 누적 상한을 제안했다면 수정 문구에 상한 문장(금액은 [●])을 넣거나, 넣지 않은 이유(협상 미확정)를 measures 에 적는다.
- action 에서 요구한 조치마다 measures 에 적고, 그 조치를 담은 edits 번호(0부터)를 쓰거나 반영하지 않은 이유를 쓴다. 설명과 수정 문구가 어긋나면 안 된다.
- 근거·위험 설명에서 확정되지 않은 외국법·법률 판단은 단정하지 않는다("~할 수 있음", "확인 필요").

JSON 하나만 출력한다:
{
 "answer": "요청에 대한 직답 1~2문장",
 "verdict": "수정 필요|현행 유지|체결 전 확인|사업부 결정",
 "risk": "HIGH|MEDIUM|LOW",
 "action_type": "필수수정|권장수정|체결 전 확인|사업부 결정|현행 유지",
 "issue_title": "짧은 쟁점 제목(한국어, 40자 이내)",
 "current": "현재 조건 — 조항이 실제로 정한 것(쉬운 한국어)",
 "risk_to_us": "우리에게 생길 위험",
 "action": "필요한 조치",
 "existing_protection": "이미 있는 보호(없으면 빈 문자열)",
 "existing_protection_refs": ["근거 조항 번호(예: Article 9.6)"],
 "legal_limits": "검증하지 못한 법률 판단의 한계(없으면 빈 문자열)",
 "request_status": "반영됨|부분 반영|미반영|사업 판단 필요",
 "business_todo": "사업팀이 할 일 한 줄(상대방에 제안·값 확정·확인 등)",
 "edits": [{"mode": "replace|insert_after|new_paragraph|delete", "target_text": "...", "new_text": "...",
            "new_paragraph_number": "", "undecided": ["..."], "changed_terms": ["..."]}],
 "measures": [{"measure": "action 이 요구한 조치 하나", "edit_index": 0, "not_reflected_reason": ""}],
 "checks": [{"what": "체결 전 확인할 일", "who": "사업부 또는 법무 또는 상대방", "when": "서명 전 또는 협상 중"}],
 "recommendation": "법무 권고안 한 줄(상대방에 무엇을 요구할지)",
 "fallback": "상대방이 권고안을 거절할 때의 대안 또는 현행 유지 이유",
 "decisions": ["사업부가 정할 것 — 거래조건·비용·상대방 거절 시 진행 여부만"]
}"""


def _clause_block(c: Any) -> str:
    return f"[{_attr(c, 'display_path')}] {_attr(c, 'title')}\n{_ws(_attr(c, 'text'))}"


def _build_user_prompt(
    block: RequestBlock, targets: list[Any], ctx: list[Any], *, facts: str, answers_text: str, hints: str,
) -> str:
    parts = [
        "[거래 사실]", facts,
        "", f"[담당자 요청 {block.index}]", block.text,
        "", "[지목 조항 원문]", "\n\n".join(_clause_block(c) for c in targets),
    ]
    if ctx:
        parts += ["", "[함께 볼 조항(앞뒤 항·참조 조항·다른 조의 관련 조항)]", "\n\n".join(_clause_block(c) for c in ctx)]
    if answers_text.strip():
        parts += ["", "[담당자 사전질문 답변]", answers_text]
    if hints.strip():
        parts += ["", "[다른 검토 단계가 이 조항에 남긴 지적(참고 — 맞는 것만 반영)]", hints]
    return "\n".join(parts)


def _call(provider: AIProvider, *, model: str, user: str, timeout_sec: float, max_tokens: int) -> Any:
    try:
        resp = provider.complete(_build_request(
            model=model, system=_SYSTEM, user=user, timeout_sec=timeout_sec, max_tokens=max_tokens, temperature=0.1,
        ))
    except Exception as exc:  # noqa: BLE001
        logger.warning("requested clause review call failed: %s", sanitize_error_message(str(exc)))
        return None
    return _try_json(getattr(resp, "content", "") or "")


FINDING_INDEX_BASE = 100


def finding_review_blocks(clause_results: list[dict[str, Any]], *, covered_paths: set[str],
                          limit: int = 8) -> list[RequestBlock]:
    """요청 밖의 HIGH/MEDIUM 지적도 같은 방식(원문 대조·검증된 최소 수정안)으로 다시 본다 — 영문 계약용.

    국문 계약 기준 규칙·게이트를 거친 지적은 영문 조항에서 제목이 규칙 이름("정산식·차감사유·증빙 필수화")이 되고,
    수정 문구가 "원문 + [추가 권고] + 고친 원문" 으로 바뀌어 반영하면 같은 의무가 두 번(서로 다르게) 적힌다.
    """
    out: list[RequestBlock] = []
    seen: set[str] = set(covered_paths)
    live = [cr for cr in clause_results if isinstance(cr, dict) and not cr.get("dedup_suppressed")
            and not cr.get("keep_as_is") and not cr.get("is_requested_clause_review")
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")]
    live.sort(key=lambda c: 0 if str(c.get("risk_tier")).upper() == "HIGH" else 1)
    for cr in live:
        path = _s(cr.get("display_path"))
        if not clause_path_key(path) or path in seen:
            continue
        seen.add(path)
        risk = _ws(_s(cr.get("our_company_risk") or cr.get("rewrite_reason") or cr.get("problem")))[:600]
        if not risk:
            continue
        n = FINDING_INDEX_BASE + len(out) + 1
        text = (f"[내부 검토 지적 — {path}] {risk}\n이 지적이 원문에 비추어 맞는지 먼저 확인하라. 맞으면 위험도·조치와 최소 수정안을, "
                "과장되었거나 다른 조항으로 이미 보호되면 '현행 유지' 로 답하라.")
        out.append(RequestBlock(index=n, head=f"{path} 검토 지적", text=text, cited=[path]))
        if len(out) >= limit:
            break
    return out


# ── 4. 수정안 검증 ────────────────────────────────────────────────────────────

@dataclass
class VerifiedEdit:
    mode: str
    target_text: str
    new_text: str
    new_paragraph_number: str = ""
    undecided: list[str] = field(default_factory=list)
    changed_terms: list[str] = field(default_factory=list)
    held: bool = False
    hold_reason: str = ""


def merge_same_target_additions(edits: list[VerifiedEdit]) -> list[VerifiedEdit]:
    """같은 문장 뒤에 덧붙이는 수정 여러 개를 하나로 — 따로 두면 둘째가 '같은 원문을 이미 교체함' 으로 보류된다.

    2026-11-03 Norden 제12조: 첫 수정은 "Affiliates" 를 쓰고, 둘째 수정이 그 정의를 덧붙였는데 둘째만 보류돼
    클린본에 정의 없는 "Affiliates" 가 남았다. 원문 문장을 그대로 두고 뒤에 붙이는 수정만 합친다(교체는 그대로).
    """
    def addition(e: VerifiedEdit) -> str | None:
        if e.held or not e.target_text:
            return None
        if e.mode == "insert_after":
            return e.new_text.strip()
        t, n = _ws(e.target_text).strip(), _ws(e.new_text).strip()
        if e.mode == "replace" and n.startswith(t) and len(n) > len(t):
            return n[len(t):].strip()
        return None

    out: list[VerifiedEdit] = []
    first_by_target: dict[str, int] = {}
    for e in edits:
        add = addition(e)
        key = _ws(e.target_text).strip()
        if add is None:
            out.append(e)
            continue
        if key in first_by_target:
            base = out[first_by_target[key]]
            merged_add = addition(base) or ""
            out[first_by_target[key]] = VerifiedEdit(
                mode="replace", target_text=base.target_text, new_text=f"{key} {merged_add} {add}".strip(),
                new_paragraph_number=base.new_paragraph_number,
                undecided=list(dict.fromkeys(base.undecided + e.undecided)),
                changed_terms=list(dict.fromkeys(base.changed_terms + e.changed_terms)))
            continue
        first_by_target[key] = len(out)
        out.append(e)
    return out


def _find_in(clause_text: str, target: str) -> str:
    """원문에서 target 과 같은 구간(공백 차이 무시)을 원문 모양 그대로 돌려준다."""
    flat_c = _ws(clause_text)
    t = _ws(target).strip().strip("\"'“”")
    if t and t in flat_c:
        return t
    return ""


def _terms(text: str) -> set[str]:
    # "EUR 50.000" 과 "EUR 50,000" 은 같은 조건이다 — 자리 구분 기호를 지우고 비교한다.
    return {re.sub(r"(?<=\d)[.,](?=\d{3}\b)", "", re.sub(r"\s+", "", m.group(0).lower()))
            for m in _RX_TERMS.finditer(text or "")}


def verify_edit(raw: dict[str, Any], *, clause_text: str, contract_text: str, request_text: str,
                answers_text: str, latin: bool) -> VerifiedEdit:
    mode = _s(raw.get("mode")).strip().lower() or "replace"
    if mode not in ("replace", "insert_after", "new_paragraph", "delete"):
        mode = "replace"
    target = _s(raw.get("target_text")).strip()
    new = _s(raw.get("new_text")).strip()
    e = VerifiedEdit(mode=mode, target_text=target, new_text=new,
                     new_paragraph_number=_s(raw.get("new_paragraph_number")).strip(),
                     undecided=[_s(x) for x in raw.get("undecided") or [] if _s(x).strip()],
                     changed_terms=[_s(x) for x in raw.get("changed_terms") or [] if _s(x).strip()])
    if mode in ("replace", "insert_after", "delete"):
        found = _find_in(clause_text, target)
        if not found:
            e.held, e.hold_reason = True, "고칠 문장을 지목 조항 원문에서 글자 그대로 찾지 못함"
            return e
        e.target_text = found
    if mode != "delete" and not new:
        e.held, e.hold_reason = True, "수정 문구가 비어 있음"
        return e
    if re.search(r"…|\.\.\.(?!\])", new):
        e.held, e.hold_reason = True, "수정 문구가 말줄임으로 잘림"
        return e
    if latin and _has_hangul(new):
        e.held, e.hold_reason = True, "영문 계약에 국문 수정 문구"
        return e
    if mode == "replace":
        e.new_text = new = restore_number_notation(e.target_text, new)
        lost = _terms(e.target_text) - _terms(new) - _terms(request_text)
        if lost:
            e.held, e.hold_reason = True, f"기존 합의조건이 수정 문구에서 빠짐({', '.join(sorted(lost))})"
            return e
    # 계약에 없는 정의어처럼 보이는 낱말(대문자 두 낱말 이상, 예: "Licensed Products")은 정의어 확인 대상으로 남긴다.
    if latin:
        flat_contract = _ws(contract_text)
        for m in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", new):
            term = m.group(0)
            if new[m.end():m.end() + 1] == ":" or new[max(0, m.start() - 1):m.start()] in ("-", "("):
                continue  # 항목 소제목("(a) Fulfillment of Confirmed Purchase Orders:")·복합어 뒷부분은 정의어가 아니다
            if term not in flat_contract and term not in " ".join(e.undecided):
                e.undecided.append(f"{term} — 계약에 정의되지 않은 용어(계약 정의어로 맞출지 확인)")
    # 원문·요청·답변에 없는 숫자 조건은 협의용 표시로 남긴다.
    known = _ws(contract_text + " " + request_text + " " + answers_text).lower()
    e.new_text, _notes = blank_invented_numbers(e.new_text, known)
    new = e.new_text
    e.undecided.extend(n for n in _notes if n not in e.undecided)
    for t in _RX_TERMS.finditer(new):
        tok = t.group(0)
        if _ws(tok).lower() not in known and tok not in " ".join(e.undecided):
            e.undecided.append(f"{tok} — 원문·요청에 없는 조건(협의 필요)")
    return e


def apply_edit(clause_text: str, e: VerifiedEdit) -> str:
    flat = _ws(clause_text)
    if e.mode == "replace":
        return flat.replace(e.target_text, e.new_text, 1)
    if e.mode == "delete":
        return re.sub(r"\s{2,}", " ", flat.replace(e.target_text, "", 1)).strip()
    if e.mode == "insert_after":
        return flat.replace(e.target_text, f"{e.target_text} {e.new_text}", 1)
    return flat


# ── 5. finding 으로 ───────────────────────────────────────────────────────────

@dataclass
class RequestedReview:
    block: RequestBlock
    targets: list[Any]
    data: dict[str, Any]
    edits: list[VerifiedEdit]
    absent: bool = False
    error: str = ""
    #: 함께 본 조항(앞뒤 항·참조 조항) — 고칠 문장이 지목 조항이 아니라 여기 있으면(예: 9.2 지적의 핵심 문장이 9.3) 그 조항을 고친다.
    context: list[Any] = field(default_factory=list)

    @property
    def paths(self) -> list[str]:
        return [_attr(c, "display_path") for c in self.targets]


def _answers_text(answers: dict[str, Any] | None, questions: list[dict[str, Any]] | None) -> str:
    titles = {str(q.get("question_id")): str(q.get("title") or "") for q in questions or [] if isinstance(q, dict)}
    out = []
    for k, v in (answers or {}).items():
        if _s(v).strip():
            out.append(f"- {titles.get(str(k), str(k))}: {_s(v).strip()}")
    return "\n".join(out)


def run_requested_clause_review(
    *,
    provider: AIProvider | None,
    model: str,
    review_focus: str,
    clauses: list[Any] | None,
    contract_text: str,
    facts: str,
    answers: dict[str, Any] | None = None,
    questions: list[dict[str, Any]] | None = None,
    clause_results: list[dict[str, Any]] | None = None,
    timeout_sec: float = 120.0,
    max_tokens: int = 3000,
    blocks: list[RequestBlock] | None = None,
) -> list[RequestedReview]:
    if blocks is None:
        blocks = [b for b in split_request_blocks(review_focus) if b.cited]
    if not blocks or provider is None:
        return []
    latin = _is_latin(contract_text[:20000])
    ans = _answers_text(answers, questions)
    jobs: list[tuple[RequestBlock, list[Any], str, list[Any]]] = []
    out: list[RequestedReview] = []
    for b in blocks:
        targets = resolve_cited(b.cited, clauses)
        if not targets:
            found = next((recheck_in_text(c, contract_text) for c in b.cited if recheck_in_text(c, contract_text)), "")
            out.append(RequestedReview(block=b, targets=[], data={}, edits=[], absent=not found,
                                       error="" if not found else "조항 색인에는 없지만 원문에 있음 — 조항 분리 확인 필요"))
            continue
        ctx = [c for t in targets for c in context_clauses(t, clauses) if c not in targets]
        # 요청 본문이 함께 부른 조항(예: wind-down 요청 안의 "제4.1조에 따른 로열티")도 함께 본다.
        for c in resolve_cited([m.group(0) for m in _RX_CITE.finditer(b.text)], clauses):
            if c not in targets and c not in ctx:
                ctx.append(c)
        # 다른 조의 같은·관련 주제 조항(면책↔지식재산 침해 면책, 종료↔로열티 기간·사용권) — 조항 간 충돌·기존 보호 확인용.
        for t in targets:
            for c in related_clauses(t, clauses, list(targets) + ctx):
                if c not in ctx:
                    ctx.append(c)
        paths = {_attr(t, "display_path") for t in targets}
        hints = "\n".join(
            f"- {cr.get('display_path')}: {_ws(_s(cr.get('our_company_risk') or cr.get('rewrite_reason') or cr.get('problem')))[:300]}"
            for cr in clause_results or [] if isinstance(cr, dict) and _s(cr.get("display_path")) in paths
            and _s(cr.get("our_company_risk") or cr.get("rewrite_reason") or cr.get("problem")).strip()
        )[:2500]
        jobs.append((b, targets, _build_user_prompt(b, targets, ctx, facts=facts, answers_text=ans, hints=hints), ctx))

    def _run(job: tuple[RequestBlock, list[Any], str]) -> RequestedReview:
        b, targets, prompt, ctx = job
        data = _call(provider, model=model, user=prompt, timeout_sec=timeout_sec, max_tokens=max_tokens)
        if not isinstance(data, dict):
            return RequestedReview(block=b, targets=targets, data={}, edits=[], error="AI 응답을 읽지 못함", context=ctx)
        # 고칠 문장은 지목 조항 또는 함께 보여 준 조항(앞뒤 항·참조 조항) 원문에 글자 그대로 있어야 한다.
        joined = "\n".join(_attr(t, "text") for t in list(targets) + list(ctx))

        def _verify(d: dict[str, Any]) -> list[VerifiedEdit]:
            return [verify_edit(e, clause_text=joined, contract_text=contract_text, request_text=b.text,
                                answers_text=ans, latin=latin)
                    for e in d.get("edits") or [] if isinstance(e, dict)]

        edits = _verify(data)
        # 검증에서 걸린 이유를 한 번 되돌려 고치게 한다 — 보류로 끝나면 담당자는 쓸 수 있는 문안을 받지 못한다.
        problems = [f"edits[{i}]: {e.hold_reason}" for i, e in enumerate(edits) if e.held]
        problems += [f"edits[{i}]: {u.split(' — ')[0]} 는 원문·요청·답변에 없는 조건 — 지어내지 말고 [●] 로 비워 둘 것"
                     for i, e in enumerate(edits) for u in e.undecided
                     if "원문·요청에 없는 조건" in u and re.search(r"\d", u.split(" — ")[0])]
        problems += [f"edits[{i}]: {u.split(' — ')[0]} 는 계약에 없는 용어 — 계약의 정의어로 바꿀 것"
                     for i, e in enumerate(edits) for u in e.undecided if "정의되지 않은 용어" in u]
        problems += nationality_problems(data, facts)
        problems += measure_problems(data, edits)
        problems += drafting_problems(data, edits, targets=list(targets), ctx=list(ctx), request_text=b.text,
                                      answers_text=ans)
        # 검증에서 걸린 문제를 최대 두 번 되돌려 고치게 한다(2차는 1차 수정본에 남은 구조 문제만).
        for _round in range(2):
            if not problems:
                break
            fix_prompt = (prompt + "\n\n[이전 답변]\n" + json.dumps(data, ensure_ascii=False)
                          + "\n\n[코드 검증 결과 — 아래만 고쳐 같은 형식의 JSON 전체를 다시 출력]\n- " + "\n- ".join(problems))
            fixed = _call(provider, model=model, user=fix_prompt, timeout_sec=timeout_sec, max_tokens=max_tokens)
            if not (isinstance(fixed, dict) and fixed.get("edits") is not None):
                break
            fixed_edits = _verify(fixed)
            if sum(e.held for e in fixed_edits) > sum(e.held for e in edits):
                break
            data, edits = fixed, fixed_edits
            data["_repaired"] = list(data.get("_repaired") or []) + problems
            problems = [f"edits[{i}]: {e.hold_reason}" for i, e in enumerate(edits) if e.held]
            problems += measure_problems(data, edits) + drafting_problems(
                data, edits, targets=list(targets), ctx=list(ctx), request_text=b.text, answers_text=ans)
        fix_nationality(data, facts)   # 고쳐 오지 않았으면 원문 표시대로 바로잡는다
        remaining = measure_problems(data, edits) + drafting_problems(
            data, edits, targets=list(targets), ctx=list(ctx), request_text=b.text, answers_text=ans)
        if PRICE_DISCOUNT_GAP in remaining:
            # 공제 기준은 상대방과 합의할 값이다 — 문구를 지어내지 않고 체결 전 확인 사항으로 남긴다.
            if not isinstance(data.get("checks"), list):
                data["checks"] = []
            data["checks"].append({"what": PRICE_DISCOUNT_CHECK, "who": "사업부", "when": "서명 전"})
            remaining = [x for x in remaining if x != PRICE_DISCOUNT_GAP]
        if remaining:
            data["_measure_gaps"] = remaining
        issue_text = " ".join([b.text, _s(data.get("issue_title")), _s(data.get("current"))]
                              + [_attr(t, "text") for t in targets])
        guard_protection(data, issue_text=issue_text, clauses=clauses)
        return RequestedReview(block=b, targets=targets, data=data, edits=edits, context=ctx)

    with ThreadPoolExecutor(max_workers=4) as pool:
        out.extend(pool.map(_run, jobs))
    out.sort(key=lambda r: r.block.index)
    return out


def _host_for(e: VerifiedEdit, targets: list[Any]) -> Any:
    if e.target_text:
        for t in targets:
            if e.target_text in _ws(_attr(t, "text")):
                return t
    return targets[0]


#: 사업부가 정할 일이 아닌 것 — 상대방이 받아들일지(협상 결과), 법률 효력(법무 확인). 결정사항에 두면 사업부가 정할 수 없는 것을 떠안는다.
_RX_NOT_DECISION = re.compile(r"(?:상대방|상대\s*회사|[A-Z]{2,})\s*(?:의|이|가)?\s*(?:동의|수용|수락|승낙)|(?:동의|수용|수락|승낙)\s*(?:여부|가능)"
                              r"|받아들일지|협의하여\s*확정|효력|적법|유효(?:성|한지)|강행규정|법률\s*검토", re.I)
#: 사업부가 정할 수 있는 것 — 금액·기간·비용·범위 같은 거래조건, 거절 시 진행 여부.
_RX_BUSINESS = re.compile(r"금액|기간|비용|부담|보험료|한도|상한|범위|수량|일정|가격|로열티|진행할지|진행\s*여부|거절\s*시|포기|감수|우선순위|선택", re.I)

DELIVERY_STATUSES = ("반영", "부분 반영", "미반영", "확인 필요")


def split_decisions(decisions: list[str]) -> tuple[list[str], list[str]]:
    """(사업부 결정, 확인 사항) — 상대방 동의 여부·법률 효력은 확인 사항으로 옮긴다."""
    keep, move = [], []
    for d in decisions:
        d = _s(d).strip()
        if not d:
            continue
        if _RX_NOT_DECISION.search(d) and not re.search(r"진행할지|진행\s*여부|거절\s*시", d):
            move.append(d)
        elif _RX_BUSINESS.search(d):
            keep.append(d)
        else:
            move.append(d)
    return keep, move


def delivery_status(r: "RequestedReview", action_type: str) -> tuple[str, str]:
    """요청 하나의 전달 상태(반영 / 부분 반영 / 미반영 / 확인 필요)와 한 줄 이유 — 화면·검토의견서·변경추적본이 같은 값을 쓴다.

    반영: 요청 취지를 수정안(또는 이미 원문)에 담았고 계약 전체 검증에서 남은 문제가 없음.
    부분 반영: 수정안은 있으나 보류된 문구·반영하지 않은 조치·계약 전체 검증에서 남은 문제가 있음.
    미반영: 법무가 고치지 않기로 했거나 수정안을 모두 보류함.
    확인 필요: 판단 전에 사실·상대방·외국법 확인이 먼저 필요하거나 검토가 끝나지 않음.
    """
    if r.absent or not r.data:
        return "확인 필요", "지목한 조항을 찾지 못했거나 검토가 끝나지 않음"
    d = r.data
    live = [e for e in r.edits if not e.held]
    held = [e for e in r.edits if e.held]
    gaps = [g for g in d.get("_measure_gaps") or [] if _s(g).strip()]
    unreflected = [m for m in d.get("measures") or [] if isinstance(m, dict) and _s(m.get("measure")).strip()
                   and not (isinstance(m.get("edit_index"), int) and 0 <= m["edit_index"] < len(r.edits)
                            and not r.edits[m["edit_index"]].held)]
    if action_type == "현행 유지":
        return "반영", "현재 문구로 요청 취지가 지켜짐"
    if action_type == "사업부 결정":
        return "확인 필요", "사업부가 거래조건을 정한 뒤 반영"
    if not live:
        if held:
            return "미반영", "수정 문구를 보류함 — " + held[0].hold_reason
        if action_type == "체결 전 확인" or _s(d.get("verdict")).startswith(("체결", "사업")):
            return "확인 필요", "수정 전에 확인할 사항이 있음"
        return "미반영", _s(d.get("fallback") or d.get("action"))[:120] or "수정안 없음"
    if held or gaps or unreflected:
        why = (f"보류 {len(held)}건" if held else "") or (gaps[0][:120] if gaps else "") or \
            ("반영하지 않은 조치: " + _s(unreflected[0].get("measure"))[:80])
        return "부분 반영", why
    return "반영", "수정안에 반영함"


def to_findings(reviews: list[RequestedReview]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in reviews:
        if not r.data or not r.targets:
            continue
        d = r.data
        action_type = CATEGORY_BY_ACTION.get(_s(d.get("action_type")).strip(), "")
        risk = _s(d.get("risk")).upper().strip()
        risk = risk if risk in ("HIGH", "MEDIUM", "LOW") else "MEDIUM"
        if action_type == "현행 유지" or not action_type and _s(d.get("verdict")).startswith("현행"):
            action_type, risk = "현행 유지", "LOW"
        elif action_type in ("필수수정", "권장수정") and risk == "LOW":
            # 고치라고 하면서 LOW 로 매기면 전달본·변경추적본(HIGH/MEDIUM 만 반영)에서 수정안이 사라진다(11-02 최종 실행 6.6).
            risk = "MEDIUM"
        risk, action_type = severity_guard(risk, action_type, r)
        if risk == "HIGH" and action_type != "필수수정":
            # HIGH 는 필수 수정에만 — 협상 권고·사실 확인을 HIGH 로 세면 일반 개선사항까지 HIGH 로 부풀려진다(2026-11-02 지시 1항).
            risk = "MEDIUM"
        title = _s(d.get("issue_title")).strip() or f"요청 {r.block.index} 검토"
        checks = [{"what": _s(c.get("what")).strip(), "who": _s(c.get("who")).strip() or "사업부",
                   "when": _s(c.get("when")).strip() or "서명 전"}
                  for c in d.get("checks") or [] if isinstance(c, dict) and _s(c.get("what")).strip()]
        _dec_keep, _dec_move = split_decisions([_s(x) for x in d.get("decisions") or []])
        decisions = [f"사업부 결정: {x}" for x in _dec_keep]
        for x in _dec_move:
            # 상대방 수용 여부는 협상 결과로 확인한다 — 법무 권고안·대안은 카드에 먼저 보인다.
            checks.append({"what": re.sub(r"\s*(?:은|는)?\s*사업부가?\s*(?:최종\s*)?(?:결정|정할\s*것|확정)\.?$", "", x).rstrip(". ")
                           + " (협상 결과 확인)", "who": "사업부(협상)·법무", "when": "서명 전"})
        # 사업부 결정 사항은 계약서에 고쳐 넣지 않는다 — 대안 문구는 '선택 시 제안 문구' 로만 보인다.
        # 2026-11-03 Norden 16.8: 관할·준거법 리스크 검토 요청에 한국법·서울 법원 문구가 변경추적본에 그대로 들어가,
        # 합의하지 않은 조건이 우리 수정안처럼 보였다.
        decision_only = action_type == "사업부 결정"
        options = [e.new_text for e in r.edits if decision_only and not e.held and e.new_text.strip()]
        if options:
            checks.append({"what": "사업부가 대안을 택하면 제안할 문구(합의 전 — 계약서에는 반영하지 않음): " + " / ".join(options),
                           "who": "사업부", "when": "협상 전"})
        measures = []
        for m in d.get("measures") or []:
            if not isinstance(m, dict) or not _s(m.get("measure")).strip():
                continue
            ix = m.get("edit_index")
            refl = isinstance(ix, int) and 0 <= ix < len(r.edits) and not r.edits[ix].held and not decision_only
            reason = _s(m.get("not_reflected_reason")).strip()
            if decision_only and not reason:
                reason = "사업부 결정 사항 — 계약서에는 반영하지 않고 선택 시 제안 문구로만 둠"
            if not refl and not reason and any(e.held for e in r.edits):
                reason = "수정 문구 자동 적용 보류 — " + next(e.hold_reason for e in r.edits if e.held)
            measures.append({"measure": _s(m.get("measure")).strip(), "reflected": refl, "not_reflected_reason": reason})
            if not refl and reason and not decision_only:
                checks.append({"what": f"수정 문구에 반영하지 않은 조치: {_s(m.get('measure')).strip()} — {reason}",
                               "who": "사업부·법무", "when": "협상 중"})
        common = {
            "issue_title": title,
            "problem": _s(d.get("current")),
            "our_company_risk": _s(d.get("risk_to_us")),
            "rewrite_reason": _s(d.get("risk_to_us")),
            "legal_business_reason": _s(d.get("risk_to_us")),
            "brief_current": _s(d.get("current")),
            "brief_risk": _s(d.get("risk_to_us")),
            "brief_action": _s(d.get("action")),
            "existing_protection_note": _s(d.get("existing_protection")),
            "legal_limits": _s(d.get("legal_limits")),
            "request_index": r.block.index,
            # 요청 상태 = 이 검토의 전달 결과(반영/부분 반영/미반영/확인 필요). 원문 상태(AI 의 request_status)는 따로 둔다.
            "request_status": delivery_status(r, action_type)[0],
            "request_status_reason": delivery_status(r, action_type)[1],
            "original_request_status": norm_request_status(d.get("request_status"),
                                                           "사업부 결정" if decision_only else _s(d.get("verdict"))),
            "recommendation": _s(d.get("recommendation")).strip(),
            "fallback": _s(d.get("fallback")).strip(),
            "business_todo": _s(d.get("business_todo")).strip(),
            "measures": measures,
            "measure_gaps": list(d.get("_measure_gaps") or []),
            "existing_protection_refs": [_s(x) for x in d.get("existing_protection_refs") or [] if _s(x).strip()],
            "reviewed_paths": list(r.paths),
            "request_answer": _s(d.get("answer")),
            "required_actions": [_s(d.get("action"))] + decisions,
            "brief_checks": checks,
            "is_requested_clause_review": True,
            "ai_deep_reviewed": True,
            "review_category": action_type or ("권장수정" if risk != "LOW" else "현행 유지"),
            "risk_tier": risk if action_type != "현행 유지" else "LOW",
            "severity": risk,
            "keep_as_is": action_type == "현행 유지",
            "confidence": 0.85,
        }
        live_edits = [] if decision_only else merge_same_target_additions(
            [e for e in r.edits if e.mode != "delete" or e.target_text])
        if not live_edits:
            t = r.targets[0]
            out.append({**common, "clause_id": f"{ID_PREFIX}{r.block.index}_{_attr(t, 'clause_id')}",
                        "display_path": _attr(t, "display_path"), "clause_title": _attr(t, "title"),
                        "article_number": _attr(t, "article_number"), "paragraph_number": _attr(t, "paragraph_number"),
                        "original_text": _attr(t, "text"), "action_only": True,
                        "suggested_rewrite": None, "has_rewrite_change": False})
            continue
        for k, e in enumerate(live_edits, 1):
            t = _host_for(e, list(r.targets) + list(r.context))
            clause_text = _attr(t, "text")
            path = _attr(t, "display_path")
            if e.mode == "new_paragraph":
                num = e.new_paragraph_number or ""
                loc = f"{('Article ' + num) if num else path + ' 다음'} 신설"
                ri = {"edit_type": "insert_after", "edit_location": loc, "target_text": "",
                      "replacement_text": e.new_text, "final_clause_text": e.new_text}
                final = e.new_text
            else:
                final = apply_edit(clause_text, e)
                ri = {"edit_type": "replace", "edit_location": path, "target_text": e.target_text,
                      "replacement_text": (e.new_text if e.mode == "replace" else
                                           f"{e.target_text} {e.new_text}" if e.mode == "insert_after" else ""),
                      "final_clause_text": final}
            ri.update({"held": e.held, "hold_reason": e.hold_reason, "edit_mode": e.mode,
                       "new_paragraph_number": e.new_paragraph_number})
            out.append({
                **common,
                "clause_id": f"{ID_PREFIX}{r.block.index}_{k}_{_attr(t, 'clause_id')}",
                "display_path": path, "clause_title": _attr(t, "title"),
                "article_number": _attr(t, "article_number"), "paragraph_number": _attr(t, "paragraph_number"),
                "original_text": clause_text,
                "suggested_rewrite": final, "recommendation_text": final,
                "has_rewrite_change": not e.held, "redline_instruction": ri,
                "undecided_terms": list(e.undecided), "changed_terms": list(e.changed_terms),
                "edit_index": k,
            })
    return out


def supersede_same_clause(clause_results: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[str]:
    """요청 검토가 답한 조항의 다른 지적은 그 판단으로 모은다 — 한 조항에 판단이 둘이면 화면·문서가 갈린다."""
    # 검토한 조항(지목·재검토 대상)과 실제로 고친 조항(앞뒤 항일 수 있다) 모두 — 9.2 지적을 9.3 문장으로 고쳤으면 9.2 의 옛 지적도 모은다.
    paths = {f["display_path"] for f in new if f.get("display_path")}
    paths |= {p for f in new for p in f.get("reviewed_paths") or []}
    done: list[str] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or cr.get("is_requested_clause_review") or cr.get("dedup_suppressed"):
            continue
        if _s(cr.get("display_path")) in paths:
            cr["dedup_suppressed"] = True
            cr["dedup_reason"] = "superseded_by_requested_clause_review"
            done.append(_s(cr.get("clause_id")))
    return done


def _short_head(head: str) -> str:
    """요청 머리의 짧은 이름 — "제6.5조(위약금 조항): …" → "제6.5조(위약금 조항)"."""
    h = re.sub(r"\s+", " ", head).strip()
    m = re.match(r"^(.{4,60}?)\s*[:：]", h)
    return m.group(1) if m else h[:60]


def coverage_rows(reviews: list[RequestedReview], findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in reviews:
        if r.block.index >= FINDING_INDEX_BASE:
            continue  # 요청이 아닌 내부 지적 재검토 — 요청 답변 행을 만들지 않는다
        ids = [f["clause_id"] for f in findings if f.get("request_index") == r.block.index]
        if r.absent:
            ans = "문서 전체를 다시 확인했지만 지목한 조항을 찾지 못했습니다 — 조항 번호를 확인해 주세요."
            status, need = "사실관계 추가확인", False
        elif not r.data:
            ans = f"{STATUS_PENDING} — {r.error or 'AI 검토 실패'}. 체결 판단 전 법무 확인이 필요합니다."
            status, need = STATUS_PENDING, False
        else:
            d = r.data
            held = [e for e in r.edits if e.held]
            ans = _s(d.get("answer")).strip()
            if held:
                ans += f" (수정 문구 {len(held)}건은 {STATUS_PENDING}: {held[0].hold_reason})"
            status = _s(d.get("verdict")).strip() or "수정 필요"
            need = status == "수정 필요"
        rows.append({
            "issue_id": f"user_request_{r.block.index}",
            "source": "requested_clause_review",
            "request_index": r.block.index,
            "original_user_text": r.block.head,
            "normalized_issue": _short_head(r.block.head),
            "relevant_clause": ", ".join(r.paths) or "해당 조항 없음(문서 전체 재확인)",
            "relevant_clause_paths": r.paths,
            "answer_clause_paths": r.paths,
            "direct_answer": ans, "conclusion": ans, "judgment": ans,
            "review_status": status, "needs_revision": need,
            # 요청 상태는 그 요청의 finding 이 가진 값(조치 구분까지 반영한 최종값) 하나를 쓴다 — 화면 요청표와 카드가 같게.
            "request_status": (next((_s(f.get("request_status")) for f in findings
                                     if f.get("request_index") == r.block.index and _s(f.get("request_status"))), "")
                               or delivery_status(r, "")[0]),
            "request_status_reason": (next((_s(f.get("request_status_reason")) for f in findings
                                            if f.get("request_index") == r.block.index and _s(f.get("request_status_reason"))), "")
                                      or delivery_status(r, "")[1]),
            "matched_finding_ids": ids,
            "custom_user_issue": True,
        })
    return rows


def _row_paths(row: dict[str, Any]) -> set[tuple[str, ...]]:
    ps = row.get("relevant_clause_paths") or row.get("answer_clause_paths") or []
    if isinstance(ps, str):
        ps = [ps]
    keys = {clause_path_key(_s(p)) for p in ps}
    # 요청 문장이 직접 부른 조항("제6.5조(위약금 조항)", "Article 6.5")도 같은 요청의 표지다.
    for m in _RX_CITE.finditer(_s(row.get("original_user_text") or row.get("normalized_issue"))):
        keys.add(clause_path_key(m.group(0)))
    return {k for k in keys if k}


def dedupe_request_rows(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """요청 답변 행을 의미 기준으로 한 번씩 — 조항 지목 요청 검토 행이 있으면 같은 조항을 가리키는 다른 단계의 행은 뺀다.

    2026-11-03 Norden: 화면에는 요청 7건인데 다운로드 검토의견서에는 같은 7건을 다른 단계(사전질문 답변 의도 분석)가 다시 적은
    요청 8~14 가 덧붙어 14건이 됐고, 그 행들이 엉뚱한 결정 번호에 연결됐다.
    """
    rows = [r for r in rows or [] if isinstance(r, dict)]
    primary = [r for r in rows if r.get("source") == "requested_clause_review"]
    taken: set[tuple[str, ...]] = set()
    for r in primary:
        taken |= _row_paths(r)
    out: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    for r in rows:
        k = re.sub(r"[\s\"'“”()\[\]:：.,]", "", _s(r.get("original_user_text") or r.get("normalized_issue")))[:40]
        if r.get("source") != "requested_clause_review" and not r.get("is_comprehensive_scope"):
            ps = _row_paths(r)
            if ps and ps & taken:
                continue
            if k and k in seen_text:
                continue
        if k:
            seen_text.add(k)
        out.append(r)
    return out


def merge_coverage(existing: list[dict[str, Any]] | None, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 요청(같은 지목 조항·같은 문장 머리)의 기존 행을 이 행으로 바꾼다."""
    out = [dict(r) for r in existing or [] if isinstance(r, dict)]

    def _k(s: Any) -> str:
        return re.sub(r"[\s\"'“”()\[\]]", "", _s(s))[:24]

    for row in rows:
        k = _k(row["original_user_text"])
        idx = next((i for i, r in enumerate(out) if k and _k(r.get("original_user_text"))
                    and (k in _k(r.get("original_user_text")) or _k(r.get("original_user_text")) in k)), None)
        if idx is None:
            idx = next((i for i, r in enumerate(out)
                        if set(_s(p) for p in r.get("relevant_clause_paths") or []) & set(row["relevant_clause_paths"])
                        and _k(r.get("original_user_text"))[:8] == k[:8]), None)
        if idx is None:
            out.append(row)
        else:
            out[idx] = row
    out.sort(key=lambda r: (0, int(r["request_index"])) if r.get("source") == "requested_clause_review"
             else (1, 0))
    return out


def summary(reviews: list[RequestedReview], findings: list[dict[str, Any]], superseded: list[str]) -> dict[str, Any]:
    return {
        "requests": [
            {"index": r.block.index, "cited": r.block.cited, "paths": r.paths, "absent": r.absent, "error": r.error,
             "verdict": _s(r.data.get("verdict")), "risk": _s(r.data.get("risk")),
             "action_type": _s(r.data.get("action_type")),
             "edits": [{"mode": e.mode, "held": e.held, "hold_reason": e.hold_reason, "undecided": e.undecided}
                       for e in r.edits]}
            for r in reviews
        ],
        "finding_ids": [f["clause_id"] for f in findings],
        "superseded": superseded,
    }


__all__ = [
    "RequestBlock", "RequestedReview", "VerifiedEdit", "apply_edit", "context_clauses", "coverage_rows",
    "merge_coverage", "recheck_in_text", "resolve_cited", "run_requested_clause_review", "split_request_blocks",
    "summary", "supersede_same_clause", "to_findings", "verify_edit",
]
