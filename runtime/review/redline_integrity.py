"""수정안 무결성 게이트 — 모든 수정안(AI·룰·체크리스트)을 원문과 한 줄씩 대조해 고치거나 보류한다 (2026-11-13).

시디즈 영문 물품공급계약(우리 = Supplier) 실측 실패에서 나왔다. 계약 유형·회사에 맞춘 규칙은 두지 않는다.

  1. 계약 언어 — 영문 계약 본문에 국문 문구(괄호 지침·①②)를 끼워 넣지 않는다(13.4).
  2. 계약에 없는 호칭 — 갑/을·위탁자/수탁자 같은 호칭을 쓴 문안은 계약에 넣지 않는다(4.3 위탁판매 정산 문안).
  3. 기존 문구 보존 — 지적 이유가 삭제를 말하지 않는데 하위 항목 (a)(b)(c)·예외·사양 보증 같은 원문을 지운 수정은
     지운 부분을 되살린다. 되살릴 수 없게 문장을 다시 쓴 수정은 보류한다(4.5 구제수단 삭제, 9.1 사양 보증 삭제, 13.3 예외 삭제).
  4. 근거 없는 값 — 원문·요청·사용자 답변 어디에도 없는 기간·이율·금액은 넣지 않는다. 공란 채우기라면 공란을 그대로 두고
     사업부 확정 사항으로 넘긴다(4.5 연 6%). 사용자 답변 값은 '사용자 답변 기준'으로 표시한다(9.1 12개월).
  5. 변경 없는 수정 — 공백·괄호만 다른 "수정"은 수정이 아니다(16.3 '[ ]'→'[]').
  6. 상호 조항 오독 — 'Each Party shall indemnify' 를 일방 배상으로 읽은 지적은 전제가 틀렸다(13.4 HIGH).
  7. 부재 지적 재확인 — "없다/명시하라" 는 지적은 계약 전체에서 같은 주제를 찾아 이미 있으면 내린다(취소·반품·지급·인도·해지).
     지적이 전제한 거래 요소(주문제작·설치 등)가 계약에 없으면 이 계약의 쟁점이 아니다.
  8. HIGH 근거 — 공란 채우기만 남은 HIGH 는 MEDIUM, 전제가 틀린 지적은 LOW(현행 수용).
  9. 우리에게 유리한 조항에 붙은 일반 룰 지적(수정 문안 없음)은 '현행 수용'으로 내린다.
 10. 영문 계약 신설 위치 — '제18조 신설' 처럼 국문 조 번호로 영문 계약에 조를 만들지 않는다.

각 처리는 finding 의 ``redline_integrity`` 와 meta['redline_integrity'] 에 남는다. 이 단계는 필수 검증(verification_gate)
직전에 돈다 — 검증이 고친 뒤의 수정안 집합을 본다.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any

_HANGUL = re.compile(r"[가-힣]")
_RX_BLANK = re.compile(r"\[[^\[\]]{0,200}\]")
_PUNCT_ONLY = re.compile(r"^[\s.,;:()\"“”'’%/\-–—]*$")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "by", "with", "as", "be", "is", "that", "such",
         "any", "all", "its", "their", "this", "shall", "may", "will", "at", "from"}
_KO_LABELS = ("갑", "을", "병", "위탁자", "수탁자", "수급인", "도급인", "하수급인", "임대인", "임차인", "매도인", "매수인",
              "공급자", "구매자", "판매자", "라이선서", "라이선시", "발주자", "수급사업자", "원사업자", "대리점", "본사")
_EN_LABELS = ("Licensor", "Licensee", "Consignor", "Consignee", "Contractor", "Subcontractor", "Lessor", "Lessee",
              "Distributor", "Dealer", "Principal", "Agent", "Client", "Customer", "Vendor", "Seller", "Purchaser",
              "Supplier", "Buyer", "Company", "Service Provider")
_DELETE_INTENT = re.compile(r"삭제|제외|빼|없앤|delete|remove|strike", re.I)

# 부재 지적 재확인용 주제 — (이름, 원문 검색 정규식, 지적 문장 검색 정규식)
TOPICS: tuple[tuple[str, str, str], ...] = (
    ("대금 지급", r"\bpay(?:ment|able)?\b|\binvoice\b|T/T|대금|지급", r"대금\s*지급|지급\s*조건|결제|payment"),
    ("인도·선적 조건", r"\bdeliver(?:y|ed)?\b|\bFOB\b|\bCIF\b|\bDAP\b|\bEXW\b|Incoterms|\bshipment\b|인도|납품|선적",
     r"인도\s*조건|납품\s*조건|선적|FOB|delivery"),
    ("주문 취소·변경", r"\bcancel(?:lation|led)?\b|취소", r"(?:주문|발주)\s*취소|취소|cancel"),
    ("반품", r"\breturn\b|반품", r"반품|return"),
    ("계약 해지·종료", r"\bterminat\w*|해지|해제", r"해지|종료|terminat"),
    ("보증", r"\bwarrant\w*|보증", r"보증|warranty"),
    ("검수", r"\binspect\w*|\baccept(?:ance|ed)\b|검수|검사", r"검수|검사|inspection|acceptance"),
    ("소유권·위험 이전", r"\btitle\b|risk\s+of\s+loss|소유권|위험\s*부담", r"소유권|위험\s*(?:부담|이전)|title|risk of loss"),
    ("책임 한도", r"shall\s+not\s+exceed|aggregate\s+liability|한도|상한", r"책임\s*(?:한도|상한|제한)|liability cap"),
    ("비밀유지", r"confidential\w*|비밀", r"비밀\s*유지|confidential"),
    ("지식재산권", r"intellectual\s+property|trademark|지식재산|상표", r"지식\s*재산|지재권|intellectual property|IP\b"),
    ("준거법·관할", r"governing\s+law|jurisdiction|arbitration|준거법|관할|중재", r"준거법|관할|중재|governing law|jurisdiction"),
    ("관세·통관", r"customs|dut(?:y|ies)|import|export|관세|통관", r"관세|통관|customs|dut(?:y|ies)"),
)
_ABSENCE = re.compile(r"없[다음어으는]|부재|미규정|규정\s*(?:되어\s*)?있지\s*않|누락|빠져|명시(?:하세요|하십시오|할\s*것|\s*필요)"
                      r"|신설|추가하(?:세요|십시오)|not\s+(?:provided|addressed|specified)|absent|missing|no\s+provision", re.I)
# 지적이 전제한 거래 요소 — 계약에 그 요소가 없으면 이 계약의 쟁점이 아니다
_PREMISES: tuple[tuple[str, str, str], ...] = (
    ("주문제작", r"주문\s*제작|맞춤\s*제작|custom[- ]?made|made[- ]to[- ]order|customi[sz]ed", r"주문\s*제작|맞춤\s*제작|\bcustom(?!s)\b|custom[- ]?made|made[- ]to[- ]order"),
    ("설치", r"설치|installation|install", r"설치|installation|install"),
    ("위탁판매", r"위탁\s*판매|consign", r"위탁(?:판매|자|매매)|수탁자|consign"),
    ("렌탈", r"렌탈|rental|lease", r"렌탈|rental"),
)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _ws(v: Any) -> str:
    return " ".join(_s(v).split())


def is_english(text: str) -> bool:
    t = _s(text)
    letters = len(re.findall(r"[A-Za-z]", t))
    return letters > 200 and len(_HANGUL.findall(t)) < letters * 0.03


# ── 값(숫자+단위) ─────────────────────────────────────────────────────────────

_UNIT = (r"(?P<unit>%|percent|per\s*cent|calendar\s+days?|business\s+days?|days?|months?|years?|weeks?|USD|KRW|EUR|"
         r"영업일|일|개월|달|년|주|퍼센트|원|달러)")
_RX_VAL = re.compile(r"(?P<num>\d+(?:[.,]\d+)*)\s*\)?\s*" + _UNIT, re.I)
_UNIT_KEY = {"%": "pct", "percent": "pct", "percent ": "pct", "퍼센트": "pct", "day": "day", "days": "day", "일": "day",
             "영업일": "day", "month": "month", "months": "month", "개월": "month", "달": "month", "year": "year",
             "years": "year", "년": "year", "week": "week", "weeks": "week", "주": "week"}


def _unit_key(u: str) -> str:
    u = re.sub(r"^(?:calendar|business)\s+", "", u.lower()).strip()
    if u.startswith("per"):
        return "pct"
    return _UNIT_KEY.get(u, u)


def values(text: str) -> set[tuple[str, str]]:
    return {(m.group("num").replace(",", ""), _unit_key(m.group("unit"))) for m in _RX_VAL.finditer(_s(text))}


# 숫자 표현 전체(영문 'six percent (6%)', 'twelve (12) months', 국문 '연 6%')
_RX_VAL_SPAN = re.compile(
    r"(?:(?:[a-z\-]+\s+){0,2}(?:percent\s+)?\(\s*\d+(?:\.\d+)?\s*%?\s*\)\s*(?:percent|%)?|\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?)"
    r"(?:\s*(?:calendar\s+|business\s+)?(?:days?|months?|years?|weeks?)|\s*(?:영업일|일|개월|년|주))?", re.I)


# ── 토큰 비교 ────────────────────────────────────────────────────────────────

def _tokens(text: str) -> list[str]:
    t = _RX_BLANK.sub(" ⁣BLANK⁣ ", _s(text))
    return t.split()


def _is_blankish(toks: list[str]) -> bool:
    rest = [x for x in toks if x != "⁣BLANK⁣"]
    return len(rest) < len(toks) and all(_PUNCT_ONLY.match(x) for x in rest)


_RX_MARKER = re.compile(r"^(?:\(?[a-z]\)|\(\d{1,2}\)|\d{1,2}\)|[①-⑳]|\d{1,2}\.\d{1,2}|제\d+호)$")


def _starts_items(toks: list[str]) -> bool:
    """원문 구간이 하위 항목 머리((b)·②·4.6 등)로 시작하는가."""
    return bool(toks) and bool(_RX_MARKER.match(toks[0]))


def _content_words(toks: list[str]) -> list[str]:
    out = []
    for x in toks:
        w = re.sub(r"[^\w가-힣]", "", x).lower()
        if w and w not in _STOP and not w.isdigit() and w != "blank":
            out.append(w)
    return out


@dataclass
class DiffResult:
    deleted: list[str] = field(default_factory=list)       # 지운 원문 구간(내용어가 있는 것)
    rewritten: list[tuple[str, str]] = field(default_factory=list)   # 원문 구간을 다른 말로 바꾼 것
    blank_fills: list[tuple[str, str]] = field(default_factory=list)  # 공란 → 값
    inserted: list[str] = field(default_factory=list)
    noop: bool = False


def diff(original: str, new: str) -> DiffResult:
    a, b = _tokens(original), _tokens(new)
    res = DiffResult()
    na = [re.sub(r"[.,;:]+$", "", x).lower() for x in a]
    nb = [re.sub(r"[.,;:]+$", "", x).lower() for x in b]
    sm = difflib.SequenceMatcher(a=na, b=nb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        aseg, bseg = a[i1:i2], b[j1:j2]
        if op == "insert":
            res.inserted.append(" ".join(bseg))
        elif op == "delete":
            if _content_words(aseg):
                res.deleted.append(" ".join(aseg))
        else:  # replace
            if _starts_items(aseg) and not any(_RX_MARKER.match(x) for x in bseg):
                # 하위 항목을 통째로 지우고 그 자리에 새 문장을 넣었다 → 삭제 + 추가로 본다(되살릴 때 항목 앞에 넣는다)
                res.deleted.append(" ".join(aseg))
                res.inserted.append(" ".join(bseg))
                continue
            if _is_blankish(aseg):
                res.blank_fills.append((" ".join(aseg), " ".join(bseg)))
            elif not _content_words(aseg) and not _content_words(bseg):
                continue   # 구두점만 다르다
            elif set(_content_words(bseg)) <= set(_content_words(aseg)):
                res.deleted.append(" ".join(aseg))   # 원문 일부만 남겼다 = 삭제
            elif not _content_words(aseg):
                res.inserted.append(" ".join(bseg))
            else:
                res.rewritten.append((" ".join(aseg), " ".join(bseg)))
    res.noop = not (res.deleted or res.rewritten or res.blank_fills or res.inserted) or (
        _ws(_RX_BLANK.sub("[ ]", original)) == _ws(_RX_BLANK.sub("[ ]", new)))
    return res


def project(original: str, new: str, *, keep_fill: Any = None) -> str:
    """원문을 기준으로 수정안의 '추가'와 '공란 채우기'만 반영한다(지운 부분은 되살린다).

    keep_fill(old, new) -> bool: 그 공란 채우기를 반영할지. False 면 원문 공란을 둔다.
    """
    a, b = _tokens(original), _tokens(new)
    na = [re.sub(r"[.,;:]+$", "", x).lower() for x in a]
    nb = [re.sub(r"[.,;:]+$", "", x).lower() for x in b]
    sm = difflib.SequenceMatcher(a=na, b=nb, autojunk=False)
    out: list[str] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        aseg, bseg = a[i1:i2], b[j1:j2]
        if op == "equal":
            out.extend(aseg)
        elif op == "insert":
            out.extend(bseg)
        elif op == "replace" and _starts_items(aseg) and not any(_RX_MARKER.match(x) for x in bseg):
            out.extend(bseg)
            out.extend(aseg)
        elif op == "replace" and _is_blankish(aseg) and (keep_fill is None or keep_fill(" ".join(aseg), " ".join(bseg),
                                                                                       " ".join(a[i2:i2 + 2]))):
            out.extend(bseg)
        else:
            out.extend(aseg)
    txt = " ".join(out)
    # 원문 공란 표기 복원
    blanks = iter(_RX_BLANK.findall(_s(original)))
    return re.sub("⁣BLANK⁣", lambda _m: next(blanks, "[ ]"), txt)


# ── 공란(미확정 상업조건) ─────────────────────────────────────────────────────

_BLANK_LABELS: tuple[tuple[str, str], ...] = (
    (r"Incoterms|인도\s*조건|delivery\s+terms?", "인도 조건(Incoterms)"),
    (r"선적\s*기한|shipment\s+(?:date|schedule)", "선적 기한"),
    (r"interest|이자|연체", "연체이자율"),
    (r"days\s+from\s+the\s+(?:date\s+of\s+the\s+)?bill\s+of\s+lading|payment\s+term|지급\s*기일|지급기한", "대금 지급기일"),
    (r"warrant|보증", "보증기간"),
    (r"territory|판매\s*지역|지역", "판매지역(Territory)"),
    (r"jurisdiction|courts?\s+of|관할", "관할 법원"),
    (r"exclusive|독점", "독점·비독점 여부"),
    (r"port\s+of\s+shipment|선적항", "선적항"),
    (r"force\s+majeure|consecutive\s+days|불가항력", "불가항력 해지 기간"),
    (r"survive|confidential|비밀", "비밀유지 존속기간"),
    (r"destination|도착국", "도착 국가"),
    (r"unit\s+price|단가|price", "단가"),
    (r"organized\s+under|principal\s+office|company|법인", "상대방 법인 정보"),
    (r"name|title|signature|date|서명|일자", "서명란"),
)


_RX_SIGNATURE_BLOCK = re.compile(
    r"(?m)^.*(?:계약\s*체결일|Date\s+of\s+Execution|IN\s+WITNESS\s+WHEREOF|서명\s*날인|기명\s*날인|Authorized\s+Signature)", re.I)
_RX_FILLED_VALUE = re.compile(r"\[\s*[\d.,]+\s*%?\s*\]")
_RX_LABEL_BRACKET = re.compile(r"\[\s*(?:[A-Z]{1,4}|(?:CM|MM|KG|PCS)\b[^\]]*\d[^\]]*)\s*\]", re.I)
_RX_HEADING_LABEL = re.compile(r"^\s*(?:\d{1,2}\.\s*)?([^:(\[\n]{1,30}?)\s*(?:\([^)]*\))?\s*:")


def blank_terms(text: str, clauses: list[Any] | None = None) -> list[dict[str, str]]:
    """원문의 공란·선택지 표시와 그 위치·항목명. 같은 항목은 한 번만.

    2026-11-27 보정(국제 매매계약 실측):
    - 공란 뒤 문맥은 **같은 줄 안에서만** 본다 — 서명란이 마지막 조에 붙어 추출되면 체결일 공란 뒤 "상호 (Company)" 가
      라벨이 되어 없는 "상대방 법인 정보 공란"을 만들었다.
    - 라벨표에 없는 공란도 버리지 않는다 — 항 머리("1. 선적 기한 (…):")를 라벨로 쓴다(선적 기한·인도 조건 공란 누락).
    - 서명란·전문(당사자 표)의 공란은 "대표자 성명·체결일" 같은 기재 사항으로 남긴다(사업부 결정).
    - 값이 이미 든 대괄호([ 3 ], [ 30 ])와 단위 표기([ML], [CM 79X95 …])는 공란이 아니다.
    """
    from runtime.review.cross_border.blanks import Layout, _execution_item

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    src = [(_path(c), _s(c.get("text") if isinstance(c, dict) else getattr(c, "text", ""))) for c in clauses or []]
    if not src:
        src = [("", _s(text))]
    else:
        lay = Layout(_s(text))
        if lay.articles and lay.first_article > 0:
            src.insert(0, ("전문(당사자 표)", _s(text)[:lay.first_article]))
    for path, t in src:
        sig = _RX_SIGNATURE_BLOCK.search(t)
        sig_start = sig.start() if sig else len(t)
        for m in _RX_BLANK.finditer(t):
            inner = m.group(0)
            if re.fullmatch(r"\[\s*(?:페이지|page)\s*\d+\s*\]", inner, re.I):
                continue
            if _RX_FILLED_VALUE.fullmatch(inner) or _RX_LABEL_BRACKET.fullmatch(inner):
                continue
            if re.search(r"\d\s*%", inner) and not re.search(r"입력|기재|선택|insert|choose|select|TBD", inner, re.I):
                continue   # "[50% Advance / 50% Balance]" 같은 설명 괄호
            line_start = t.rfind("\n", 0, m.start()) + 1
            line_end = t.find("\n", m.end())
            line_end = len(t) if line_end < 0 else line_end
            ctx = t[max(line_start, m.start() - 120): min(line_end, m.end() + 80)]
            if path == "전문(당사자 표)" or m.start() >= sig_start:
                # 서명란·당사자 표의 기재 사항 — 대표자 성명·체결일 등(사업부 결정)
                head = _RX_HEADING_LABEL.match(t[line_start:line_end])
                label = _execution_item(head.group(1).strip() if head else "", t[line_start:line_end])
                key = f"{path if path == '전문(당사자 표)' else '서명란'}:{label}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"label": label, "path": "서명란" if m.start() >= sig_start else path, "blank": _ws(inner),
                             "context": _ws(ctx)[:200], "classification": "사업부 결정"})
                continue
            # 공란 안 문구 → 바로 앞 문장 조각 → 뒤(같은 줄 안) 순서로 본다('[exclusive / non-exclusive] … Territory' 를 지역으로 읽지 않게)
            before = re.split(r"(?<!\d)[.;:]\s", t[max(0, m.start() - 300): m.start()])[-1]
            after = t[m.end(): min(line_end, m.end() + 60)]
            label = ""
            for zone in (inner, before, after):
                label = next((lab for rx, lab in _BLANK_LABELS if re.search(rx, zone, re.I)), "")
                if label:
                    break
            if not label:
                head = _RX_HEADING_LABEL.match(t[line_start:line_end])
                heading = head.group(1).strip() if head and head.end() <= m.start() - line_start + 1 else ""
                # 항 머리도 라벨표로 한 번 더 맞춘다 — 국문 "선적 기한"과 영문 "Shipment Schedule"이 같은 항목이 되게
                label = next((lab for rx, lab in _BLANK_LABELS if heading and re.search(rx, heading, re.I)), heading)
            if not label or label in ("서명란", "단가"):
                continue
            key = label
            if key in seen:
                continue
            seen.add(key)
            # 마지막 조에 붙어 추출된 별지·부속서의 공란은 그 별지 이름으로 가리킨다(서명란 뒤 Schedule A 를 17.6 으로 적던 실측)
            sched = None
            for sched in re.finditer(r"(?m)^\s*((?:SCHEDULE|ANNEX|APPENDIX|EXHIBIT|별지|부속서|별첨)\b[^\n–\-]{0,12})", t[:m.start()], re.I):
                pass
            rows.append({"label": label, "path": _ws(sched.group(1)) if sched else path, "blank": _ws(inner),
                         "context": _ws(ctx)[:200]})
    return rows


def _path(c: Any) -> str:
    if isinstance(c, dict):
        return _s(c.get("display_path") or c.get("path") or "")
    return _s(getattr(c, "display_path", "") or getattr(c, "path", ""))


def _ctext(c: Any) -> str:
    if isinstance(c, dict):
        return _s(c.get("text") or c.get("original_text") or "")
    return _s(getattr(c, "text", ""))


# ── 사용자 값 ────────────────────────────────────────────────────────────────

def user_value_lines(request_text: str, answers_text: str) -> list[str]:
    return [ln.strip() for ln in f"{request_text}\n{answers_text}".splitlines() if ln.strip()]


def _value_from_user(label: str, user_lines: list[str]) -> str:
    """사용자 답변에서 그 항목의 값('12개월', '미국', '미확정')을 찾는다."""
    keys = {"보증기간": r"보증|warranty", "판매지역(Territory)": r"판매\s*지역|territory", "관할 법원": r"관할|jurisdiction",
            "대금 지급기일": r"지급\s*기일|지급|payment", "독점·비독점 여부": r"독점|exclusive", "연체이자율": r"이자|interest"}
    rx = keys.get(label)
    if not rx:
        return ""
    for ln in user_lines:
        m = re.match(r"^[-•·\s]*(?P<q>.+?)\s*[:：]\s*(?P<a>[^:：]+)$", ln)
        if m and re.search(rx, m.group("q"), re.I):
            return m.group("a").strip()
    return ""


_UNDECIDED_ANS = re.compile(r"미확정|확정되지\s*않|정해지지\s*않|모르|협의\s*중|미정|TBD", re.I)


# ── 우리 관점 문장 판독 ───────────────────────────────────────────────────────

def clause_posture(text: str, ours: list[str], theirs: list[str]) -> str:
    """'favorable'(우리 권리·상대 의무만) / 'mutual' / 'burden'(우리 의무) / ''"""
    t = _ws(text)
    if not t or not ours or not theirs:
        return ""
    o = "|".join(re.escape(x) for x in ours if x)
    th = "|".join(re.escape(x) for x in theirs if x)
    if re.search(r"\b(?:Each|Either|Neither)\s+Party\b|각\s*당사자|쌍방|상호", t):
        return "mutual"
    our_burden = re.search(rf"\b(?:the\s+)?(?:{o})\s+shall(?!\s+have\s+no\s+obligation)(?!\s+not\s+be\s+(?:liable|obliged))"
                           rf"|(?:{o})\s*(?:은|는|이|가)\s*[^.。]{{0,60}}?(?:하여야|해야|한다)", t, re.I)
    their_side = re.search(rf"\b(?:the\s+)?(?:{th})\s+shall\b|borne\s+by\s+the\s+(?:{th})|\b(?:{o})\s+may\b"
                           rf"|(?:{o})'s\s+prior\s+written\s+consent|remain\s+with\s+the\s+(?:{o})"
                           rf"|(?:{o})\s+shall\s+have\s+no\s+obligation", t, re.I)
    if our_burden:
        return "burden"
    return "favorable" if their_side else ""


def _is_mutual_indemnity(text: str) -> bool:
    t = _ws(text)
    return bool(re.search(r"\b(?:Each|Either)\s+Party\s+shall\s+(?:indemnify|defend|hold)|각\s*당사자는?[^.。]{0,40}(?:배상|면책)"
                          r"|상호\s*(?:배상|면책)|쌍방", t, re.I))


# ── 게이트 ───────────────────────────────────────────────────────────────────

@dataclass
class Ctx:
    text: str
    clauses: list[Any]
    english: bool
    ours: list[str]
    theirs: list[str]
    user_lines: list[str]
    contract_vals: set[tuple[str, str]]
    user_vals: set[tuple[str, str]]
    clause_by_path: dict[str, str]
    assigned: dict[str, int] = field(default_factory=dict)
    our_kind: str = ""

    def next_sub(self, host: str) -> str:
        """영문 계약 host 조의 다음 항 번호 — 같은 조에 신설이 여럿이면 차례로 번호를 준다."""
        subs = [int(m.group(1)) for p in self.clause_by_path for m in [re.match(rf"^Article\s+{host}\.(\d+)$", p.strip())] if m]
        n = max([*subs, self.assigned.get(host, 0)]) + 1
        self.assigned[host] = n
        return f"{host}.{n}"


def _placeholder(ctx: Ctx, label: str) -> str:
    return f"[To be confirmed: {label}]" if ctx.english else f"[확정 필요: {label}]"


def _note(cr: dict[str, Any], action: str, detail: str, report: list[dict[str, Any]]) -> None:
    rec = {"finding_id": _s(cr.get("finding_id") or cr.get("clause_id")), "path": _s(cr.get("display_path")),
           "action": action, "detail": detail}
    cr.setdefault("redline_integrity", []).append({"action": action, "detail": detail})
    report.append(rec)


def _edit_fields(cr: dict[str, Any]) -> tuple[str, str]:
    """(원문, 새 문안) — 교체 수정만. 추가형은 ('', 추가 문안)."""
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
    et = _s(ri.get("edit_type"))
    if et in ("insert_after", "new_clause"):
        return "", _s(ri.get("final_clause_text") or ri.get("replacement_text"))
    if cr.get("has_rewrite_change") and _s(cr.get("suggested_rewrite")).strip():
        return _s(cr.get("original_text")), _s(cr.get("suggested_rewrite"))
    if et == "replace" and _s(ri.get("replacement_text")).strip():
        return _s(ri.get("target_text") or cr.get("original_text")), _s(ri.get("replacement_text"))
    return "", ""


def _addition(cr: dict[str, Any]) -> str:
    return _s(cr.get("addition_text")) if cr.get("has_addition") else ""


def _hold(cr: dict[str, Any], reason: str, memo: str = "") -> None:
    ri = cr.get("redline_instruction")
    if not isinstance(ri, dict):
        ri = {}
        cr["redline_instruction"] = ri
    ri["held"] = True
    ri["hold_reason"] = reason
    cr["has_rewrite_change"] = False
    cr["has_addition"] = False
    cr["integrity_held"] = reason
    if memo:
        cr["drafting_memo"] = (_s(cr.get("drafting_memo")) + "\n" + memo).strip()


def exclude_from_brief(cr: dict[str, Any], reason: str) -> None:
    """사업팀 전달본에서 빼고 법무 내부 분석본에만 남긴다 — 사유를 함께 기록한다."""
    cr["excluded_from_brief"] = True
    cr["internal_only_reason"] = reason
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        # 법무 내부 분석본(DOCX·PDF)은 보류 사유를 이미 싣는다 — 같은 자리에 전달본 제외 사실을 남긴다.
        ri["hold_reason"] = (_s(ri.get("hold_reason")) + " — 사업팀 전달본에서 제외(법무 내부 기록)").strip(" —")


def _redraft(cr: dict[str, Any]) -> None:
    """문안이 잘못돼 보류했을 뿐 위험은 남는다 — 등급은 그대로 두고 '수정문 재작성 필요' 로 표시한다(위험을 숨기지 않는다)."""
    cr["redline_status"] = "수정문 재작성 필요 — 변경추적본에는 원문 유지"
    cr["needs_redraft"] = True


def _set_tier(cr: dict[str, Any], tier: str) -> None:
    for k in ("risk_tier", "severity"):
        cr[k] = tier
    if tier == "LOW":
        cr["high_risk"] = False
        cr["must_fix"] = False
    if isinstance(cr.get("redline_instruction"), dict):
        cr["redline_instruction"]["severity"] = tier


def _set_text(cr: dict[str, Any], new: str) -> None:
    cr["suggested_rewrite"] = new
    cr["has_rewrite_change"] = True
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict) and _s(ri.get("edit_type")) in ("", "replace"):
        ri["replacement_text"] = new
        if ri.get("final_clause_text"):
            ri["final_clause_text"] = new


def _labels_missing(new: str, ctx: Ctx) -> list[str]:
    miss = []
    for lab in _KO_LABELS:
        if re.search(rf"(?<![가-힣]){lab}(?:은|는|이|가|의|에게|과|와|을|를|로|\s|$)", new) and not re.search(
                rf"(?<![가-힣]){lab}(?:은|는|이|가|의|에게|과|와|을|를|로|\s|\)|”|\"|$)", ctx.text):
            miss.append(lab)
    for lab in _EN_LABELS:
        if re.search(rf"\b(?:the\s+)?{lab}\b", new) and not re.search(rf"\b{lab}\b", ctx.text):
            miss.append(lab)
    return miss


def _map_labels(cr: dict[str, Any], miss: list[str], ctx: Ctx, report: list[dict[str, Any]]) -> bool:
    """매도인·구매자 같은 역할 명사를 계약의 정의어로 바꾼다 — 우리 역할(매도/매수)을 확정했을 때만."""
    from runtime.review.deal_flow import role_kind

    if not (ctx.our_kind and ctx.ours and ctx.theirs):
        return False
    table: dict[str, str] = {}
    for lab in miss:
        k = role_kind(lab)
        if not k:
            return False   # 위탁자·수탁자 같은 다른 거래 구조의 호칭은 바꾸지 않는다(다른 계약 문안)
        table[lab] = ctx.ours[0] if k == ctx.our_kind else ctx.theirs[0]

    def sub(t: str) -> str:
        for a, b in table.items():
            t = re.sub(rf"(?<![가-힣A-Za-z]){re.escape(a)}(?![A-Za-z])", b, t)
        return t
    for k in ("suggested_rewrite", "addition_text"):
        if cr.get(k):
            cr[k] = sub(_s(cr[k]))
    ri = cr.get("redline_instruction")
    if isinstance(ri, dict):
        for k in ("replacement_text", "final_clause_text"):
            if ri.get(k):
                ri[k] = sub(_s(ri[k]))
    _note(cr, "party_label_mapped", f"역할 명사를 계약 정의어로 통일: {table}", report)
    return True


def _invented(new_part: str, ctx: Ctx) -> list[str]:
    out = []
    for v in values(new_part):
        if v in ctx.contract_vals or v in ctx.user_vals:
            continue
        out.append(f"{v[0]}{'%' if v[1] == 'pct' else ' ' + v[1]}")
    return out


def _blank_label(original: str, at: str) -> str:
    i = _s(original).find(at) if at else -1
    ctx = _s(original)[max(0, i - 120): i + 80] if i >= 0 else _s(original)
    return next((lab for rx, lab in _BLANK_LABELS if re.search(rx, ctx, re.I)), "공란 항목")


def _reason_text(cr: dict[str, Any]) -> str:
    return " ".join(_s(cr.get(k)) for k in ("rewrite_reason", "clause_title", "issue", "suggested_direction")) + " " + " ".join(
        _s(x.get("issue_title")) + " " + _s(x.get("issue_detail")) for x in cr.get("detected_issue_list") or [] if isinstance(x, dict))


def _absence_check(cr: dict[str, Any], ctx: Ctx, report: list[dict[str, Any]]) -> bool:
    """부재 지적을 계약 전체로 재확인. 내렸으면 True."""
    reason = _reason_text(cr)
    # (1) 지적이 전제한 거래 요소(주문제작·설치·위탁판매·렌탈)가 계약에 없다 — 부재 지적이 아니어도 이 계약의 쟁점이 아니다
    for name, in_contract, in_finding in _PREMISES:
        if re.search(in_finding, reason, re.I) and not re.search(in_contract, ctx.text, re.I):
            _hold(cr, f"지적 전제('{name}')가 이 계약에 없음 — 이 계약의 쟁점이 아님")
            _set_tier(cr, "LOW")
            cr["keep_as_is"] = True
            _note(cr, "premise_absent", f"지적이 전제한 '{name}' 거래 요소가 계약 전체에 없음 — 수정안 보류·현행 수용", report)
            return True
    if not _ABSENCE.search(reason):
        return False
    real = _s(cr.get("clause_id")) and any(_s(cr.get("display_path")) == p for p in ctx.clause_by_path)
    is_new = (not real) or bool(cr.get("has_addition")) or _s((cr.get("redline_instruction") or {}).get("edit_type")) in (
        "insert_after", "new_clause")
    if not is_new:
        return False
    # (2) 같은 주제의 조항이 이미 있다
    topic_src = _s(cr.get("clause_title")) or _s(cr.get("rewrite_reason"))[:120]   # 지적의 주제 = 제목(이유 본문의 낱말로 넓히지 않는다)
    for name, in_contract, in_finding in TOPICS:
        if not re.search(in_finding, topic_src, re.I):
            continue
        hits = [p for p, t in ctx.clause_by_path.items() if p and re.search(in_contract, t, re.I)]
        if hits:
            _hold(cr, f"'{name}' 조항이 이미 있음({', '.join(hits[:4])}) — 부재 지적 철회")
            _set_tier(cr, "LOW")
            cr["keep_as_is"] = True
            cr["existing_protection_paths"] = hits[:6]
            _note(cr, "absence_refuted", f"계약 전체 검색 결과 '{name}' 관련 조항 존재: {', '.join(hits[:6])}", report)
            return True
    return False


def _fix_en_location(cr: dict[str, Any], ctx: Ctx, report: list[dict[str, Any]]) -> None:
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else None
    if not ri or not ctx.english or _s(ri.get("edit_type")) not in ("new_clause", "insert_after"):
        return
    loc = _s(ri.get("edit_location"))
    if not re.search(r"제\s*\d+\s*조", loc):
        return
    # 근거 원문이 든 조의 마지막 항 다음에 영문 항 번호로 둔다
    target = _ws(ri.get("target_text") or cr.get("original_text"))
    host = ""
    for p, t in ctx.clause_by_path.items():
        if target and target[:60] and _ws(target)[:60].lstrip("0123456789. ") in _ws(t):
            m = re.search(r"(\d+)", p)
            host = m.group(1) if m else ""
            break
    if not host:
        m = re.search(r"Article\s+(\d+)", _s(cr.get("display_path")))
        host = m.group(1) if m else ""
    if not host:
        _hold(cr, f"영문 계약에 국문 조 번호 위치('{loc}')로 신설 — 넣을 조를 정하지 못함")
        _note(cr, "location_unresolved", f"영문 계약의 국문 신설 위치('{loc}')에 대응하는 조를 찾지 못해 보류", report)
        return
    nxt = ctx.next_sub(host)
    ri["edit_location"] = f"Article {nxt} 신설"
    ri["edit_type"] = "insert_after"
    _note(cr, "location_fixed", f"영문 계약의 국문 조 번호 위치('{loc}') → 'Article {nxt} 신설'", report)


def check_finding(cr: dict[str, Any], ctx: Ctx, report: list[dict[str, Any]]) -> None:
    ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
    if ri.get("held") or cr.get("source") == "redline_integrity":
        return
    # 6. 상호 조항을 일방 조항으로 읽은 지적
    reason = _reason_text(cr)
    if re.search(r"일방|one[- ]sided|unilateral", reason, re.I) and re.search(r"배상|면책|indemn", reason, re.I) \
            and _is_mutual_indemnity(_s(cr.get("original_text"))):
        _hold(cr, "원문은 상호 배상 구조(Each Party) — 일방 배상 전제가 틀림")
        _set_tier(cr, "LOW")
        cr["keep_as_is"] = True
        _note(cr, "premise_wrong", "원문이 상호 배상인데 일방 배상으로 읽은 지적 — 수정안 보류·현행 수용", report)
        return
    # 7. 부재 지적 재확인
    if _absence_check(cr, ctx, report):
        return
    original, new = _edit_fields(cr)
    add = _addition(cr)
    if not new and not add:
        return
    # 1·2. 계약 언어·호칭 — 추가되는 부분만 본다
    added_part = add
    d = None
    if original and new:
        d = diff(original, new)
        added_part = " ".join([*d.inserted, *[b for _a, b in d.rewritten], *[b for _a, b in d.blank_fills], add])
    elif new:
        added_part = new + " " + add
    if ctx.english and _HANGUL.search(added_part):
        _hold(cr, "영문 계약 본문에 국문 문구 삽입 — 계약 언어 불일치",
              memo="국문 지침(계약 본문에 넣지 않음): " + _ws(re.findall(r"[^.]*[가-힣][^.]*", added_part)[0] if re.findall(
                  r"[^.]*[가-힣][^.]*", added_part) else added_part)[:300])
        _note(cr, "language_mismatch", "영문 계약에 국문 문구를 넣는 수정 — 본문 반영 보류, 지침은 메모로", report)
        _redraft(cr)
        return
    miss = _labels_missing(added_part, ctx)
    if miss:
        mapped = _map_labels(cr, miss, ctx, report)
        if mapped:
            original, new = _edit_fields(cr)
            add = _addition(cr)
            added_part = (new or "") + " " + (add or "")
            miss = _labels_missing(added_part, ctx)
    if miss:
        _hold(cr, f"계약에 없는 당사자 호칭 사용({', '.join(miss)}) — 다른 계약 유형의 문안")
        _note(cr, "undefined_party_label", f"계약에 정의되지 않은 호칭 {miss} 를 쓴 문안 — 보류", report)
        # 다른 계약 유형의 문안이라고 시스템이 스스로 판정했다 — 그 finding 은 이 계약의 쟁점이라는 근거가 없다.
        # 라벨만 붙여 사업팀 전달본에 "법무 확인 중"으로 내보내지 않고, 법무 내부 분석본에만 사유와 함께 남긴다(2026-11-27).
        exclude_from_brief(cr, f"다른 계약 유형의 문안으로 판정 — 계약에 없는 당사자 호칭({', '.join(miss)}) 사용")
        _redraft(cr)
        return
    if d is not None:
        # 5. 변경 없음
        if d.noop:
            _hold(cr, "원문과 실질적으로 같은 문안 — 수정 아님")
            _note(cr, "noop", "공백·괄호만 다른 수정 — 수정안 제거", report)
            return
        # 3. 기존 문구 보존
        if d.deleted and d.inserted:
            ins_w = set(_content_words(" ".join(d.inserted).split()))
            del_w = set(_content_words(" ".join(d.deleted).split()))
            if ins_w and len(ins_w & del_w) >= max(2, len(ins_w) // 3):
                # 지운 내용을 다른 자리에 다른 말로 다시 썼다(13.3: 예외를 앞으로 옮기며 fraud·willful misconduct 를 지움)
                d.rewritten.append((" ".join(d.deleted), " ".join(d.inserted)))
        if (d.deleted or d.rewritten) and not _DELETE_INTENT.search(_s(cr.get("rewrite_reason"))):
            if d.rewritten:
                lost = "; ".join(a for a, _b in d.rewritten)[:300]
                _hold(cr, "원문 문구를 지적 이유와 무관하게 다시 써 기존 내용이 바뀜 — 보류",
                      memo=f"원문에서 바뀌는 부분: {lost}")
                _note(cr, "rewrote_existing", f"지적 이유에 없는 원문 변경(예외·범위 등): {lost}", report)
                _redraft(cr)
                return
            restored = project(original, new)
            _note(cr, "restored_deleted", "지운 원문을 되살림: " + "; ".join(d.deleted)[:300], report)
            new = restored
            _set_text(cr, new)
            d = diff(original, new)
        # 4. 근거 없는 값 — 공란 채우기
        user_fill_notes = []
        if d.blank_fills:
            def _keep(old: str, val: str, nxt: str = "") -> bool:
                return not _invented(f"{val} {nxt}", ctx)
            new2 = project(original, new, keep_fill=_keep)
            if _ws(new2) != _ws(new):
                inv = sorted({v for v in _invented(new, ctx)})
                _note(cr, "invented_value_removed", f"원문·요청·답변에 없는 값 {inv} — 공란 유지(사업부 확정 사항)", report)
                new = new2
                _set_text(cr, new)
                d = diff(original, new)
            new_vals = values(new) - values(original)
            user_fill_notes = [f"{v}{'%' if u == 'pct' else ' ' + u}" for v, u in sorted(new_vals & ctx.user_vals)]
            user_fill_notes += [b for _a, b in d.blank_fills if any(w and w in b for w in _user_words(ctx))]
        if d.noop:
            _hold(cr, "남는 수정이 없음 — 공란 값은 사업부 확정 사항")
            _note(cr, "noop_after_repair", "근거 없는 값·삭제를 걷어내니 원문과 같음 — 수정안 보류, 공란은 사업부 결정 항목", report)
            if _s(cr.get("risk_tier")) == "HIGH":
                _set_tier(cr, "MEDIUM")
            return
        if user_fill_notes:
            cr["user_answer_values"] = user_fill_notes
            _note(cr, "user_value", f"사용자 답변 값으로 공란 기재: {user_fill_notes} — 상대방 합의 전 제안값", report)
        # 8. 공란 채우기만 남은 HIGH
        if _s(cr.get("risk_tier")) == "HIGH" and not (d.inserted or d.deleted or d.rewritten):
            _set_tier(cr, "MEDIUM")
            _note(cr, "high_downgraded", "공란 기재만 남은 수정 — HIGH 근거 없음, MEDIUM", report)
        # 추가 문안 속 근거 없는 값
        if d.inserted:
            new3 = new
            for seg in d.inserted:
                for v in _invented(seg, ctx):
                    pass
            new3 = _replace_invented(new, original, ctx)
            if _ws(new3) != _ws(new):
                _note(cr, "invented_value_placeholder", "추가 문안의 근거 없는 값을 확정 필요 표시로 바꿈", report)
                _set_text(cr, new3)
    else:
        target_key = "addition_text" if add else None
        body = add or new
        new3 = _replace_invented(body, "", ctx)
        if _ws(new3) != _ws(body):
            _note(cr, "invented_value_placeholder", "신설 문안의 근거 없는 값을 확정 필요 표시로 바꿈", report)
            if target_key:
                cr["addition_text"] = new3
            ri2 = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
            for k in ("replacement_text", "final_clause_text"):
                if _s(ri2.get(k)).strip() == body.strip():
                    ri2[k] = new3
            if _s(cr.get("suggested_rewrite")).strip() == body.strip():
                cr["suggested_rewrite"] = new3
        _fix_en_location(cr, ctx, report)


def _user_words(ctx: Ctx) -> list[str]:
    words = []
    for ln in ctx.user_lines:
        m = re.match(r"^[-•·\s]*.+?[:：]\s*(.+)$", ln)
        if m and not _UNDECIDED_ANS.search(m.group(1)):
            words += [w for w in re.findall(r"[A-Za-z]{4,}", m.group(1))]
    return words


def _replace_invented(new: str, original: str, ctx: Ctx) -> str:
    """새로 넣는 문장 속 원문·요청·답변에 없는 값 → 확정 필요 표시. 원문에 이미 있던 표현은 그대로."""
    def sub(m: re.Match[str]) -> str:
        span = m.group(0)
        vs = values(span)
        if not vs or not any(v not in ctx.contract_vals and v not in ctx.user_vals for v in vs):
            return span
        if original and span in original:
            return span
        unit = next(iter(vs))[1]
        lab = {"pct": "rate", "day": "number of days", "month": "number of months", "year": "number of years"}.get(unit, "amount")
        if not ctx.english:
            lab = {"pct": "비율", "day": "일수", "month": "개월 수", "year": "연수"}.get(unit, "금액")
        return _placeholder(ctx, lab)
    return _RX_VAL_SPAN.sub(sub, new)


def downgrade_favorable(clause_results: list[dict[str, Any]], ctx: Ctx, report: list[dict[str, Any]]) -> None:
    """수정 문안 없이 일반 룰 문구만 붙은 MEDIUM 지적이 우리에게 유리한/상호 조항이면 현행 수용."""
    for cr in clause_results:
        if not isinstance(cr, dict) or _s(cr.get("risk_tier")) != "MEDIUM":
            continue
        if cr.get("has_rewrite_change") or cr.get("has_addition") or cr.get("user_focus_hit") and False:
            continue
        reason = _s(cr.get("rewrite_reason"))
        if not re.match(r"^\s*(?:검출 이슈|사용자 중점 이슈)", reason) or cr.get("is_requested_clause_review"):
            continue
        posture = clause_posture(_s(cr.get("original_text")), ctx.ours, ctx.theirs)
        if posture in ("favorable", "mutual"):
            _set_tier(cr, "LOW")
            cr["keep_as_is"] = True
            cr["integrity_posture"] = posture
            _note(cr, "accept_as_is", ("우리 권리·상대방 의무만 정한 조항" if posture == "favorable" else "상호 동일 조건 조항")
                  + " — 일반 점검 룰 지적은 현행 수용", report)


# ── 독점권 부여 + 최소 구매 의무 없음 ────────────────────────────────────────

def exclusivity_gap(ctx: Ctx, user_lines: list[str]) -> dict[str, Any] | None:
    """우리가 독점권을 주는데(원문 또는 사용자 답변) 최소 구매·성과 조건과 미달 시 전환·해지 권리가 없으면 협상 권고."""
    grant = None
    for p, t in ctx.clause_by_path.items():
        if re.search(r"\bgrants?\b[^.]{0,80}\bexclusive\b|독점(?:적)?\s*(?:판매|유통)?\s*권", t, re.I):
            grant = (p, t)
            break
    if grant is None or not ctx.ours:
        return None
    o = "|".join(re.escape(x) for x in ctx.ours)
    if not re.search(rf"(?:the\s+)?(?:{o})\s+(?:hereby\s+)?grants?|(?:{o})\s*(?:은|는)\s*[^.]{{0,40}}독점", grant[1], re.I):
        return None   # 우리가 독점권을 받는 쪽이면 이 위험이 아니다
    optional = bool(re.search(r"\[\s*exclusive\s*/\s*non-?exclusive\s*\]|\[\s*독점\s*/\s*비독점\s*\]", grant[1], re.I))
    user_excl = any(re.search(r"독점|exclusive", ln, re.I) and not re.search(r"비독점|non-?exclusive", ln.split(":")[-1], re.I)
                    and re.search(r"[:：]\s*(?:네|예|yes|독점)", ln, re.I) for ln in user_lines)
    if optional and not user_excl:
        return None
    if re.search(r"minimum\s+(?:annual\s+)?(?:purchase|order|quantity|sales|commitment)|purchase\s+target|최소\s*(?:구매|발주|매입|판매)|목표\s*(?:구매|매출)",
                 ctx.text, re.I):
        return None
    host = re.search(r"(\d+)", grant[0])
    host_no = host.group(1) if host else ""
    new_no = ctx.next_sub(host_no) if ctx.english and host_no else ""
    our = ctx.ours[0]
    their = ctx.theirs[0] if ctx.theirs else ""
    if ctx.english:
        clause = (f"{new_no} If exclusive rights are granted to the {their} under Article {grant[0].replace('Article ', '')}, the {their} "
                  f"shall purchase Products in an aggregate amount of not less than {_placeholder(ctx, 'minimum annual purchase amount')} "
                  f"in each contract year. If the {their} fails to meet such minimum purchase amount in any contract year, the {our} may, "
                  f"by written notice to the {their}, convert such exclusive rights into non-exclusive rights or terminate this Agreement.")
        loc = f"Article {new_no} 신설"
    else:
        clause = (f"{their}이 {grant[0]}에 따라 독점권을 부여받는 경우, {their}은 매 계약연도마다 {_placeholder(ctx, '연간 최소 구매금액')} "
                  f"이상의 제품을 구매하여야 한다. {their}이 어느 계약연도에 위 최소 구매금액을 달성하지 못한 경우 {our}은 서면 통지로 "
                  f"독점권을 비독점권으로 전환하거나 이 계약을 해지할 수 있다.")
        loc = f"{grant[0]} 다음 항 신설"
    return {"grant_path": grant[0], "grant_text": grant[1], "clause": clause, "location": loc, "user_confirmed": user_excl}


def exclusivity_finding(gap: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    p = gap["grant_path"]
    m = re.search(r"(\d+)(?:\.(\d+))?", p)
    return {
        "clause_id": f"integrity_exclusivity__{p}",
        "finding_id": f"integrity_exclusivity__{p}",
        "article_number": m.group(1) if m else "",
        "paragraph_number": (m.group(2) or "") if m else "",
        "display_path": p,
        "clause_title": "독점권 부여 — 최소 구매 의무·미달 시 전환권 없음",
        "original_text": _s(gap["grant_text"]),
        "risk_tier": "MEDIUM", "severity": "MEDIUM", "review_tier": "협상 권고",
        "rewrite_reason": (
            f"발생 상황: 상대방이 독점권을 받고도 구매 실적이 저조함 → 우리 손실: 계약기간 동안 해당 지역에 다른 판매자를 둘 수 없어 "
            f"매출 기회를 잃음 → 기존 보호: {p} 외 최소 구매 의무 없음, 중대한 위반 해지(이행 부진은 위반이 아님)·만료 시 갱신 거절만 가능 "
            f"→ 남은 위험: 다음 갱신 거절 시점까지 독점 유지 → 조치: 연간 최소 구매금액과 미달 시 비독점 전환·해지 권리 추가"
            + (" (독점 부여는 사용자 답변 기준)" if gap.get("user_confirmed") else "")),
        "has_rewrite_change": False, "has_addition": True, "addition_text": gap["clause"],
        "suggested_rewrite": gap["clause"], "recommendation_text": gap["clause"],
        "insert_after": p,
        "redline_instruction": {"finding_id": f"integrity_exclusivity__{p}", "clause_id": f"integrity_exclusivity__{p}",
                                "severity": "MEDIUM", "edit_location": gap["location"], "edit_type": "insert_after",
                                "target_text": _s(gap["grant_text"]), "replacement_text": gap["clause"]},
        "undecided_terms": ["연간 최소 구매금액"],
        "source": "redline_integrity",
        "keep_as_is": False,
    }


# ── 요청 주제별 답 ────────────────────────────────────────────────────────────

def request_topic_rows(request_text: str, ctx: Ctx, clause_results: list[dict[str, Any]],
                       blanks: list[dict[str, str]]) -> list[dict[str, Any]]:
    """요청에 나열한 주제(대금지급조건, 인도 조건, warranty, 관세, 지식재산권 …)마다 관련 조항·우리 관점·남은 일."""
    base = re.split(r"\n\s*\[사용자 확인 답변\]", _s(request_text))[0]
    rows: list[dict[str, Any]] = []
    n = 0
    for name, in_contract, in_request in TOPICS:
        m = re.search(in_request, base, re.I)
        if not m:
            continue
        n += 1
        hits = [(p, t) for p, t in ctx.clause_by_path.items() if p and re.search(in_contract, t, re.I)]
        if not hits:
            judgment = f"계약 전체에서 '{name}' 관련 조항을 찾지 못했습니다 — 조항 신설 여부를 법무가 판단합니다."
            rows.append(_row(n, m.group(0), name, judgment, [], [], True))
            continue
        fav, bur, mut = [], [], []
        for p, t in hits[:12]:
            pos = clause_posture(t, ctx.ours, ctx.theirs)
            (fav if pos == "favorable" else bur if pos == "burden" else mut).append(p)
        paths = [p for p, _t in hits]
        edits = [cr for cr in clause_results if isinstance(cr, dict) and _s(cr.get("risk_tier")) in ("HIGH", "MEDIUM")
                 and _s(cr.get("display_path")) in paths and (cr.get("has_rewrite_change") or cr.get("has_addition"))
                 and not (cr.get("redline_instruction") or {}).get("held")]
        bl = [b for b in blanks if b["path"] in paths]
        parts = [f"관련 조항: {', '.join(paths[:8])}{' 외' if len(paths) > 8 else ''}."]
        if fav:
            parts.append(f"우리에게 유리하거나 상대방 의무를 정한 조항: {', '.join(fav[:6])}.")
        if bur:
            parts.append(f"우리 의무를 정한 조항: {', '.join(bur[:6])}.")
        if edits:
            parts.append("수정 제안: " + ", ".join(f"{_s(c.get('display_path'))}({_s(c.get('risk_tier'))})" for c in edits[:5]) + ".")
        else:
            parts.append("우리에게 불리해 고칠 문언은 찾지 못했습니다(현행 수용).")
        if bl:
            parts.append("확정 필요 공란: " + ", ".join(f"{b['label']}({b['path']})" for b in bl) + " — 사업부가 상대방과 정합니다.")
        rows.append(_row(n, m.group(0), name, " ".join(parts), paths[:8], [_s(c.get("finding_id") or c.get("clause_id")) for c in edits],
                         bool(edits)))
    return rows


def _row(n: int, user_text: str, name: str, judgment: str, paths: list[str], ids: list[str], needs: bool) -> dict[str, Any]:
    return {
        "issue_id": f"integrity_request_{n}", "source": "deal_request", "answer_format": "flow", "request_index": n,
        "original_user_text": user_text, "normalized_issue": name, "topic": f"integrity:{name}",
        "relevant_clause_paths": paths, "answer_clause_paths": paths, "review_status": "검토 완료",
        "needs_revision": needs, "conclusion": judgment, "direct_answer": judgment, "judgment": judgment,
        "basis": "계약 전체 조항 검색(주제어)과 우리/상대방 주어 판독", "existing_protection": "", "residual_risk": "",
        "required_action": "", "additional_checks": [], "needed_documents": [], "matched_finding_ids": ids,
        "request_status": "반영", "request_status_reason": "", "brief_answer": judgment[:200], "substantive": True,
        "override": True, "held": False, "proposed_clauses": [],
    }


# ── 진입점 ───────────────────────────────────────────────────────────────────

def run(*, clause_results: list[dict[str, Any]], clauses: list[Any] | None, contract_text: str, ours: list[str],
        theirs: list[str], request_text: str = "", answers_text: str = "", our_kind: str = "") -> dict[str, Any]:
    clauses = list(clauses or [])
    cbp: dict[str, str] = {}
    for c in clauses:
        p = _path(c)
        if p:
            cbp[p] = (cbp.get(p, "") + "\n" + _ctext(c)).strip()
    user_lines = user_value_lines(request_text, answers_text)
    user_vals = set()
    for ln in user_lines:
        if not _UNDECIDED_ANS.search(ln):
            user_vals |= values(ln)
    ctx = Ctx(text=_s(contract_text), clauses=clauses, english=is_english(contract_text), ours=[x for x in ours if x],
              theirs=[x for x in theirs if x], user_lines=user_lines, contract_vals=values(contract_text), user_vals=user_vals,
              clause_by_path=cbp, our_kind=our_kind)
    report: list[dict[str, Any]] = []
    # 방향 게이트 — 생성 단계 뒤에 들어온 수정안(AI·조항 지목 검토)까지 같은 기준으로(2026-11-27)
    from runtime.review.direction_gate import apply_direction_gate

    for row in apply_direction_gate(clause_results, contract_text=_s(contract_text), ours=list(ctx.ours), theirs=list(ctx.theirs)):
        report.append({"finding_id": row["clause_id"], "path": "", "action": "direction_blocked",
                       "detail": "; ".join(f"{b['kind']}: {b['sentence'][:80]}" for b in row["blocked"])})
    for cr in clause_results:
        if isinstance(cr, dict):
            try:
                check_finding(cr, ctx, report)
            except Exception as exc:  # noqa: BLE001 - 한 finding 의 실패가 전체를 막지 않게(기록은 남긴다)
                _note(cr, "error", f"무결성 검사 실패: {exc}", report)
    downgrade_favorable(clause_results, ctx, report)
    # 화면 요약·Word 가 서로 다른 등급을 말하지 않게 수정 지시의 등급을 finding 등급에 맞춘다(요약 HIGH ↔ 본문 MEDIUM 실측)
    for cr in clause_results:
        if isinstance(cr, dict) and isinstance(cr.get("redline_instruction"), dict) and cr.get("risk_tier"):
            cr["redline_instruction"]["severity"] = cr["risk_tier"]
    added = []
    gap = exclusivity_gap(ctx, user_lines)
    if gap and not any(_s(c.get("clause_id")).startswith("integrity_exclusivity__") for c in clause_results if isinstance(c, dict)):
        f = exclusivity_finding(gap, ctx)
        clause_results.append(f)
        added.append(f["finding_id"])
    blanks = blank_terms(contract_text, clauses)
    commercial = []
    for b in blanks:
        uv = _value_from_user(b["label"], user_lines)
        status = "사용자 답변: " + uv if uv and not _UNDECIDED_ANS.search(uv) else ("사업부 미확정(답변)" if uv else "미확정")
        commercial.append({**b, "user_value": uv if uv and not _UNDECIDED_ANS.search(uv) else "", "status": status,
                           "decider": "사업부(상대방과 협상)"})
    return {
        "english": ctx.english, "ours": ctx.ours, "theirs": ctx.theirs,
        "actions": report, "added_findings": added, "commercial_terms": commercial,
        "request_rows": request_topic_rows(request_text, ctx, clause_results, blanks),
        "counts": {k: sum(1 for r in report if r["action"] == k) for k in sorted({r["action"] for r in report})},
    }


__all__ = ["blank_terms", "clause_posture", "diff", "is_english", "project", "run", "values"]
