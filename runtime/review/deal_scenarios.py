"""계약 전체 상황별 법률효과 검증 — 수정안을 모두 넣은 계약이 실제로 의도한 책임·권리·비용을 만드는지(2026-11-03).

문구 포함 여부가 아니라 "이 상황이면 누가 무엇을 부담하는가" 로 본다. 특정 계약·조항 번호에 기대지 않는다 —
조항 번호는 결과 표시에만 쓰고, 판단은 문장의 법률 구조(주체·상대·원인·예외·한도·기간)로 한다.

1. 책임 구조화: 배상·면책·방어 문장을 누가 / 누구에게 / 어떤 원인으로 / 어떤 예외·한도로 부담하는지로 나눈다.
   상황(상대방 일반 과실, 상대방 제공 디자인·지식재산, 우리 제공 사양, 우리 일반 과실, 우리 고의·중과실)마다
   조항별 결과를 계산하고, 같은 상황에 조항끼리 결론이 다르면(우선 관계 없이) 충돌이다.
   책임한도는 건당/누적, 방어·배상 비용 포함 여부, 보호대상자 전원 적용 여부를 본다.
2. 연장: 요청·답변이 "위반이 없으면 연장" 이면 상대방 동의 없이 연장되는지, 연장권자·행사 방식·기한·기간,
   거절 가능한 위반과 시정절차, 추가 동의 필요 여부가 문구에 있는지.
3. 종료 후 활동: 확정 주문 이행·재고 판매·A/S 를 허용하면 활동별 기간·대상·사용권·정산/보고, 비판매 활동(무상 A/S·
   부품 보관)에 로열티가 붙지 않는지, 종료 후 판매분의 A/S, 보증의무보다 사용권이 먼저 끝나지 않는지, 기존 지역·표시
   제한과의 충돌, 만료·중도해지 적용 범위.
4. 수정 전후 비교: 수정으로 새로 생긴 책임·로열티 대상, 지워진 우리 권리·예외.
5. 합의 기록: 요청·답변에 적힌 이메일·구두 합의를 원문·수정안 반영 여부와 함께 남긴다.

결과의 problems 는 severity 가 "block"(출력 전에 고쳐야 함) 또는 "warn"(설명·확인이 필요) 이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── 공통 ──────────────────────────────────────────────────────────────────────

LIABLE, NOT_LIABLE, SILENT = "책임 있음", "책임 없음", "정함 없음"
#: 원인을 좁힌 조항("only to the extent caused by X")에서 X 가 아닌 상황 — 그 조항이 책임을 지우지 않을 뿐 면제하는 것은 아니다.
OUT_OF_SCOPE = "이 조항 범위 밖"

#: severity — block: 의미 역전·조항 충돌·의도하지 않은 새 부담(고치지 못하면 그 수정안을 내보내지 않는다).
#: fix: 필요한 요소가 빠짐(AI 가 보완 — 남으면 '부분 반영' 과 법무 추가 검토 표시). warn: 설명·확인 필요.
_BLOCK_CODES = {"LIABILITY_CONFLICT", "DIRECTION_MISMATCH", "NEW_LIABILITY", "NEW_ROYALTY_BASE", "ROYALTY_NONSALE",
                "RENEWAL_CONSENT", "RENEWAL_BLOCKABLE"}

#: 상황 — 원인이 누구 쪽인지와 성격. 결과 표에 그대로 쓰는 이름.
SCENARIOS: tuple[tuple[str, str], ...] = (
    ("their_negligence", "상대방 일반 과실로 생긴 제3자 청구"),
    ("their_design", "상대방이 제공한 디자인·지식재산이 원인인 제3자 청구"),
    ("our_spec", "우리가 제공한 사양·지시가 원인인 제3자 청구(우리 과실 없음)"),
    ("our_negligence", "우리 일반 과실로 생긴 제3자 청구"),
    ("our_gross", "우리 고의·중과실로 생긴 제3자 청구"),
)
SCENARIO_LABEL = dict(SCENARIOS)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", _s(s)).strip()


def sentences(text: str) -> list[str]:
    """문장 단위 — ';' 와 '(a)' 같은 열거는 한 문장 안에 둔다(열거 항목은 앞 문장의 조건이다)."""
    t = _ws(text)
    parts = re.split(r"(?<=[.。])\s+(?=[A-Z(\"“가-힣\[])", t)
    return [p.strip() for p in parts if len(p.strip()) > 3]


def _alt(names: list[str]) -> str:
    """당사자 이름 정규식. 한글 이름(갑·을·회사)은 조사가 붙어 \\b 경계가 없다 — 앞은 한글이 아니고 뒤는 조사·비한글이면 이름이다
    ("을은", "을의" 는 당사자 을, "계약을" 의 을은 아니다)."""
    parts = []
    for n in sorted({n for n in names if n}, key=len, reverse=True):
        if re.search(r"[가-힣]", n):
            parts.append(rf"(?<![가-힣]){re.escape(n)}(?=(?:은|는|이|가|의|을|를|에게|에|과|와|도|측|으로|로)?(?![가-힣]))")
        else:
            parts.append(rf"\b{re.escape(n)}\b")
    return "(?:" + "|".join(parts) + ")" if parts else r"(?!x)x"


@dataclass
class Parties:
    ours: list[str]
    theirs: list[str]

    #: 상호·약칭(예: "Sidiz Inc." → "Sidiz", 담당자가 쓰는 "SIDIZ") — 합의 문구와 계약 문구를 비교할 때만 쓴다.
    aliases_ours: list[str] = field(default_factory=list)
    aliases_theirs: list[str] = field(default_factory=list)
    #: 우리 당사자를 원문·당사자 지도에서 확정했는가 — 기본값 이름("Customer")으로 채웠으면 False(방향 검증을 신뢰할 수 없다).
    confirmed: bool = True

    def __post_init__(self) -> None:
        # 계약 정의어는 대소문자를 섞어 쓴다("the customer", "Customer") — 비교는 대소문자 무시.
        self.rx_ours = re.compile(rf"{_alt(self.ours)}", re.I)
        self.rx_theirs = re.compile(rf"{_alt(self.theirs)}", re.I)

        def expand(names: list[str], extra: list[str]) -> list[str]:
            out = list(names) + list(extra)
            for n in names + extra:
                first = (n.split() or [""])[0].strip(",.")
                if len(first) >= 4 and first[:1].isupper() and first.lower() not in ("the", "studio", "design", "korea"):
                    out.append(first)
            return out

        self.rx_ours_alias = re.compile(rf"{_alt(expand(self.ours, self.aliases_ours))}", re.I)
        self.rx_theirs_alias = re.compile(rf"{_alt(expand(self.theirs, self.aliases_theirs))}", re.I)

    def who(self, text: str) -> str:
        """문장 조각에서 먼저 나오는 당사자 — 'ours' / 'theirs' / ''."""
        mo, mt = self.rx_ours.search(text or ""), self.rx_theirs.search(text or "")
        if mo and (not mt or mo.start() < mt.start()):
            return "ours"
        if mt:
            return "theirs"
        return ""


# ── 1. 책임 구조화 ─────────────────────────────────────────────────────────────

_RX_INDEMNITY_VERB = re.compile(
    r"indemnif\w*|hold\s+\w+(?:\s+\w+){0,6}\s+harmless|hold\s+harmless|\bdefend\b|be\s+liable|bear\s+(?:all\s+)?(?:the\s+)?(?:costs|liabilit)"
    r"|배상|면책|방어|책임(?:을|이)?\s*(?:진다|지며|지고|지지|지는|부담)", re.I)
_RX_NEG = re.compile(r"shall\s+not\s+be\s+(?:liable|obliged|required|responsible)|shall\s+have\s+no\s+(?:obligation|liability)"
                     r"|is\s+not\s+(?:liable|obliged)|no\s+obligation\s+to\s+(?:indemnify|defend)|not\s+be\s+(?:liable|obliged)\s+to\s+indemnify"
                     r"|책임(?:을|이)?\s*(?:지지|부담하지)\s*(?:아니한|아니하|않)|면책(?:되|된)", re.I)
_RX_EXCEPT = re.compile(r"\b(?:except|save)\s+(?:to\s+the\s+extent|where|insofar\s+as|in\s+the\s+case)|unless\s+(?:caused|resulting|arising)"
                        r"|다만[^.]{0,40}(?:경우|때)에?는", re.I)
_RX_TO_EXTENT = re.compile(r"(?:only\s+)?to\s+the\s+extent\s+(?:that\s+)?(?:such\s+\w+\s+)?(?:arises?|arising|results?|resulting|is\s+caused|are\s+caused|caused)"
                           r"|only\s+(?:against|for|in\s+respect\s+of)\b|solely\s+(?:from|to\s+the\s+extent)|(?:으)?로\s*한정|에\s*한하여", re.I)

#: 원인 표지 — (이름, 정규식 틀). {P} 자리에 당사자 이름 정규식이 들어간다.
_CAUSES: tuple[tuple[str, str], ...] = (
    ("gross", r"(?:{P}(?:'s|’s)?\s+(?:\w+\s+){0,3}?(?:gross(?:ly)?\s+neglig\w*|wil+ful\s+misconduct|intent\w*|wil+ful)"
              r"|(?:gross(?:ly)?\s+neglig\w*|wil+ful\s+misconduct|intent(?:ional)?\s+\w+)\s+(?:of|by)\s+{P}"
              r"|{P}\s*(?:의)?\s*{EMP}(?:고의|중(?:대한\s*)?과실))"),
    # 일반 과실 — 'gross negligence'·'중대한 과실' 은 일반 과실이 아니다(2026-11-03: 중과실로 한정한 문장을 일반 과실 책임으로 읽음).
    # 국문은 당사자와 귀책 사이에 사용인이 낄 수 있다("임차인 또는 임차인의 고용인의 고의 또는 과실").
    ("negligence", r"(?:{P}(?:'s|’s)?\s+(?:(?!gross(?:ly)?\b)\w+\s+){0,3}?neglig\w*|(?<!gross\s)(?<!grossly\s)neglig\w*\s+(?:of|by)\s+{P}"
                   r"|{P}(?:'s|’s)?\s+(?:breach|acts?\s+or\s+omissions?|fault)|(?:breach|acts?\s+or\s+omissions?|fault)\s+(?:of|by)\s+{P}"
                   r"|{P}\s*(?:의|측)?\s*{EMP}(?:고의\s*(?:또는|나|및|·|,)\s*)?(?!중(?:대한\s*)?과실)(?:과실|귀책|채무불이행|위반))"),
    ("spec", r"(?:{P}(?:'s|’s)?\s+(?:\w+\s+){0,2}?(?:specifications?|instructions?|standards?|materials?|requirements?)"
             r"|(?:specifications?|instructions?|standards?|materials?)\s+(?:\w+\s+){0,2}(?:provided|furnished|supplied|given)\s+by\s+{P}"
             r"|complying\s+with\s+{P}(?:'s|’s)?\s+(?:standards?|specifications?|instructions?)"
             r"|{P}\s*(?:가|이)?\s*(?:제공한|지정한)?\s*사양)"),
    ("design", r"(?:(?:design|intellectual\s+property|IP|know-?how|drawings?)[\w\s,]{0,40}?(?:provided|furnished|supplied|created|owned)\s+by\s+{P}"
               r"|{P}(?:'s|’s)?\s+(?:design|intellectual\s+property|drawings?)"
               r"|{P}\s*(?:가|이)?\s*(?:제공한)?\s*(?:디자인|지식재산))"),
)
#: 당사자 없이 쓰인 원인(같은 문장의 다른 당사자 표지로 귀속) — "the Design" 처럼 상대방 소유가 정의된 경우는 계약마다 다르다.
_RX_CATCHALL = re.compile(r"any\s+and\s+all\s+(?:third[- ]party\s+)?claims|all\s+(?:third[- ]party\s+)?claims"
                          r"|any\s+(?:third[- ]party\s+)?claims?(?:\s*,\s*[\w\s]{2,30}?){0,3}\s+(?:arising|relating|in\s+connection)"
                          r"|(?:arising\s+(?:out\s+of|from)|relating\s+to|in\s+connection\s+with)[\w\s,’']{0,40}?(?:the\s+)?(?:design\s+products?|products?|licensed\s+products?|use\s+of\s+the\s+design)"
                          r"|모든\s*(?:제3자\s*)?청구", re.I)
_RX_PROTECTED = re.compile(r"\b(?:affiliates?|officers?|directors?|employees?|agents?|customers?|successors?|representatives?)\b", re.I)
_RX_DEFENCE_COST = re.compile(r"\bdefen[cs]e\b|\bdefend\b|legal\s+fees|attorney|counsel\s+fees|costs|expenses|방어|소송\s*비용|변호사", re.I)

_RX_CAP = re.compile(r"shall\s+(?:in\s+no\s+event|not)\s+exceed|in\s+no\s+event\s+exceed|maximum\s+(?:limit|amount|liability)|limited\s+to\s+(?:an?\s+)?(?:amount|EUR|USD|KRW|€|\$|\[)"
                     # '보상한다'·'손상한' 안의 '상한' 은 한도가 아니다(2026-11-03: 상대방 보상 의무를 상대방 책임한도로 읽음)
                     r"|cap(?:ped)?\s+at|aggregate\s+liability|total\s+liability|한도|(?<![보손])상한(?!다)|초과하지", re.I)
_RX_PER_CLAIM = re.compile(r"per\s+(?:claim|occurrence|event|incident|case)|each\s+(?:claim|occurrence|event)|any\s+(?:single|one)\s+(?:claim|occurrence|event)|건당|사고당|청구당", re.I)
_RX_AGGREGATE = re.compile(r"in\s+the\s+aggregate|aggregate|in\s+total|cumulative|total\s+(?:liability|amount)|per\s+(?:contract\s+)?year|annual|during\s+the\s+term|누적|총액|연간|합계", re.I)
_RX_INSURED_ONLY = re.compile(r"covered\s+by\s+(?:such|the|this)\s+insurance|(?:insurance|insured)\s+claims?\s+only|보험(?:으로|이)\s*(?:담보|보상)되는", re.I)


@dataclass
class LiabilityRule:
    path: str
    sentence: str
    obligor: str           # ours / theirs
    beneficiary: str       # ours / theirs / ""
    negative: bool         # "책임 없음" 을 정하는 문장
    causes: dict[str, set[str]]       # {"ours": {...}, "theirs": {...}} — 책임을 지우는 원인(또는 negative 면 면제 원인)
    except_causes: dict[str, set[str]]  # 예외로 되살리는 원인
    catch_all: bool
    limited: bool          # "only / to the extent" 로 원인을 좁힌 문장
    protected: list[str]
    defence: bool
    costs: bool
    refs: list[str]        # 이 문장이 우선관계로 가리키는 조항 번호(subject to / notwithstanding)


@dataclass
class CapRule:
    path: str
    sentence: str
    obligor: str
    per_claim: bool
    aggregate: bool
    includes_costs: bool
    covers_protected: bool
    insured_only: bool
    scope_paths: list[str]


_RX_ARTREF = re.compile(r"(?:Article|Section|Clause|clause|article|section|제)\s*(\d{1,3}(?:\.\d{1,3})*)\s*(?:조)?")
_RX_PRECEDENCE = re.compile(r"subject\s+to|notwithstanding|without\s+prejudice\s+to|except\s+as\s+(?:provided|set\s+out)\s+in|shall\s+prevail|에\s*불구하고|에\s*따른다|우선", re.I)


#: 국문 사용인 사슬 — "임차인의 고용인의 고의", "을의 임직원 등의 과실" (선택)
_KO_EMP = r"(?:(?:임직원|고용인|직원|사용인|대리인|피용자|이행보조자|하수급인|수급인)(?:\s*등)?\s*의\s*)?"

_RX_CAUSE_LINK = re.compile(r"(?:arising|resulting)\s+(?:out\s+of|from)|caused\s+by|attributable\s+to|due\s+to|as\s+a\s+result\s+of"
                            r"|(?:으)?로\s*인(?:한|하여|해)|에\s*기인", re.I)


def _causes_in(seg: str, parties: Parties) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {"ours": set(), "theirs": set()}
    for side, rxp in (("ours", parties.rx_ours.pattern), ("theirs", parties.rx_theirs.pattern)):
        for name, tmpl in _CAUSES:
            if re.search(tmpl.replace("{EMP}", _KO_EMP).replace("{P}", rxp), seg, re.I):
                out[side].add(name)
    if out["ours"] & {"gross"} and not re.search(r"(?<!gross\s)(?<!grossly\s)\bneglig", seg.replace("gross negligence", ""), re.I):
        pass
    return out


def _split_except(sentence: str) -> tuple[str, str]:
    m = _RX_EXCEPT.search(sentence)
    if not m:
        return sentence, ""
    return sentence[:m.start()], sentence[m.end():]


def _strip_parties(text: str, parties: Parties) -> str:
    """당사자 정의어(소유격 포함)를 지운다 — 'Customer's obligation' 의 Customer 를 보호대상자 'customers' 로 읽지 않게."""
    t = re.sub(parties.rx_ours.pattern + r"(?:'s|’s)?", " ", text or "", flags=re.I)
    return re.sub(parties.rx_theirs.pattern + r"(?:'s|’s)?", " ", t, flags=re.I)


def _beneficiary_span(after: str) -> str:
    """동사 뒤 보호대상자 열거 — 'from/against' 앞까지(그 뒤는 손해·원인 설명이다)."""
    m = re.search(r"\b(?:from|against|for|in\s+respect\s+of|with\s+respect\s+to)\b", after, re.I)
    return after[:m.start()] if m else after[:160]


def parse_liability(path: str, text: str, parties: Parties) -> tuple[list[LiabilityRule], list[CapRule]]:
    rules: list[LiabilityRule] = []
    caps: list[CapRule] = []
    # 국문 계약은 당사자를 “임차인” 처럼 따옴표로 쓴다 — 닫는 따옴표가 주격조사("”은")를 가려 주체를 놓쳤다(2026-11-03)
    sents = sentences(re.sub(r"[“”]", "", text or ""))
    last_obligor = ""
    for s in sents:
        verb = _RX_INDEMNITY_VERB.search(s)
        cap = _RX_CAP.search(s)
        if not verb and not cap:
            continue
        # 주체: 동사 앞 가장 가까운 당사자. "the customer is obliged to defend, indemnify ..." / "Customer shall not be liable".
        # 한도만 정한 문장("The total liability of Customer … shall not exceed")은 문장 안의 첫 당사자가 책임 주체다.
        head = s[:verb.start()] if verb else s
        neg_m = _RX_NEG.search(s)
        if neg_m and (not verb or neg_m.start() <= verb.start() + 40):
            head = s[:neg_m.start()]
        ob = ""
        tail_names = list(parties.rx_ours.finditer(head)) + list(parties.rx_theirs.finditer(head))
        if tail_names:
            # 국문은 주어-목적어-동사 순서 — 주격 조사(은·는·이·가)가 붙은 당사자가 주체다("을은 … 갑을 면책").
            subj = [m for m in tail_names if re.match(r"(?:은|는|이|가)(?![가-힣])", s[m.end():m.end() + 2])]
            # 주제격(은·는)이 붙은 당사자가 문장의 주체다 — '이·가' 는 관형절 안의 주어("임대인과 토지소유자는 … 임차인이 설치한
            # 시설비를 … 배상하여야 한다")일 수 있다(2026-11-03)
            topic = [m for m in subj if re.match(r"(?:은|는)(?![가-힣])", s[m.end():m.end() + 2])]
            subj = topic or subj
            # 영문: 동사 문장은 동사에 가장 가까운(마지막) 당사자, 한도 문장은 첫 당사자("Customer's liability to NDG …")
            last = max(subj, key=lambda m: m.start()) if subj else \
                (max(tail_names, key=lambda m: m.start()) if verb else min(tail_names, key=lambda m: m.start()))
            ob = "ours" if parties.rx_ours.fullmatch(last.group(0)) else "theirs"
        if not ob and re.search(r"\b(?:it|such\s+party|the\s+same)\b", head, re.I):
            ob = last_obligor
        if not ob:
            continue
        last_obligor = ob
        if cap and not (verb and verb.start() < cap.start() and not re.search(r"liabil|obligation|indemnif|책임|배상", s[cap.start() - 80:cap.start()], re.I)):
            per = bool(_RX_PER_CLAIM.search(s))
            agg = bool(_RX_AGGREGATE.search(s))
            if cap or per or agg:
                caps.append(CapRule(
                    path=path, sentence=s, obligor=ob, per_claim=per, aggregate=agg,
                    includes_costs=bool(re.search(r"includ\w*[^.]{0,60}(?:costs|fees|expenses|defen)|inclusive\s+of|all\s+amounts|비용\s*(?:을|를)?\s*포함", s, re.I)),
                    covers_protected=bool(_RX_PROTECTED.search(_strip_parties(s, parties)) or re.search(r"indemnified\s+part(?:y|ies)|any\s+person|all\s+(?:indemnified|protected)", s, re.I)),
                    insured_only=bool(_RX_INSURED_ONLY.search(s)),
                    scope_paths=[m.group(1) for m in _RX_ARTREF.finditer(s)],
                ))
                if not verb or (verb and cap.start() < verb.start()):
                    continue
        if not verb:
            continue
        after = s[verb.end():]
        bene = parties.who(after[:160])
        after_np = _strip_parties(after, parties)
        main, exc = _split_except(s)
        # 부정은 책임 주체의 동사에 걸릴 때만 — "to whom NDG is not liable internally" 같은 관계절의 부정으로 면책 문장을
        # 면제 문장으로 뒤집지 않는다(부정 표현이 동사 앞이나 바로 곁에 있고, 그 앞의 당사자가 책임 주체일 때).
        negative = False
        if neg_m and neg_m.start() <= verb.start() + 40:
            before_neg = list(parties.rx_ours.finditer(s[:neg_m.start()])) + list(parties.rx_theirs.finditer(s[:neg_m.start()]))
            # 국문은 여격·목적격·관형격 당사자("갑에게", "갑을", "을의")가 동사 앞에 온다 — 그 당사자는 부정의 주체가 아니다(2026-11-03:
            # "을은 … 갑에게 발생한 손해에 대하여 책임을 지지 아니한다" 를 면제문으로 읽지 못함).
            before_neg = [m for m in before_neg if not (re.search(r"[가-힣]", m.group(0))
                                                        and re.match(r"(?:에게|께|을|를|의|에\s*대하여|에\s*대한)", s[m.end():m.end() + 5]))]
            nearest = max(before_neg, key=lambda m: m.start()) if before_neg else None
            # 부정 바로 앞의 당사자가 상대방이면 상대방의 책임을 말하는 관계절이다
            negative = nearest is None or bool((parties.rx_ours if ob == "ours" else parties.rx_theirs).fullmatch(nearest.group(0)))
        limited = bool(_RX_TO_EXTENT.search(main))
        causes = _causes_in(main, parties)
        # "all claims arising from NDG's negligence" — '모든 청구' 라도 원인을 당사자 원인으로 묶었으면 그 원인에 한정된다(2026-11-03:
        # 원인 한정 배상을 원인 불문 포괄 배상으로 읽어, 바르게 고친 수정안을 '상대방 책임 감소' 로 오판).
        # 면제 문장의 열거 항목("(iii) any third party claims relating to …")은 진짜 포괄 면제라 건드리지 않는다.
        _ca = _RX_CATCHALL.search(main)
        if not negative and _ca and (causes["ours"] or causes["theirs"]) and _RX_CAUSE_LINK.search(main[_ca.end():_ca.end() + 40]):
            limited = True
        exc_causes = _causes_in(exc, parties) if exc else {"ours": set(), "theirs": set()}
        rules.append(LiabilityRule(
            path=path, sentence=s, obligor=ob, beneficiary=bene, negative=negative, causes=causes,
            except_causes=exc_causes, catch_all=bool(_RX_CATCHALL.search(main)), limited=limited,
            protected=[] if negative else sorted({m.group(0).lower().rstrip("s") for m in _RX_PROTECTED.finditer(_beneficiary_span(after_np))}),
            defence=bool(re.search(r"\bdefend\b|defen[cs]e|방어", s, re.I)),
            costs=bool(re.search(r"legal\s+fees|attorney|costs|expenses|비용", s, re.I)),
            refs=[m.group(1) for m in _RX_ARTREF.finditer(s) if _RX_PRECEDENCE.search(s[max(0, m.start() - 40):m.start()])],
        ))
    return rules, caps


def _scenario_hits(scn: str, causes: dict[str, set[str]]) -> bool:
    """상황이 이 원인 목록에 해당하는가. 중과실은 과실에 포함된다(과실 책임 문장은 중과실에도 적용)."""
    o, t = causes.get("ours", set()), causes.get("theirs", set())
    return {
        "their_negligence": bool(t & {"negligence", "gross"}),
        "their_design": bool(t & {"design"}),
        "our_spec": bool(o & {"spec"}),
        "our_negligence": bool(o & {"negligence"}),
        "our_gross": bool(o & {"negligence", "gross"}),
    }[scn]


def clause_outcome(rules: list[LiabilityRule], scn: str, *, obligor: str = "ours") -> str:
    """한 조항(같은 path)의 문장들을 순서대로 적용한 결과.

    · 원인이 맞는 적극 문장 → 책임 있음. 원인을 가리지 않는 포괄 문장 → 책임 있음(예외로 뺀 원인은 책임 없음).
    · 원인을 좁힌 문장("only to the extent caused by X")에서 X 가 아니면 → 이 조항 범위 밖(면제가 아니다).
    · 면제 문장("shall not be liable for … (i) … (ii) …, except to the extent caused by Y") → 맞는 원인은 책임 없음, Y 는 되살아남.
    """
    out = SILENT
    for r in rules:
        if r.obligor != obligor:
            continue
        hit = _scenario_hits(scn, r.causes)
        rehit = _scenario_hits(scn, r.except_causes)
        if r.negative:
            if (hit or r.catch_all) and not rehit:
                out = NOT_LIABLE
            continue
        if hit and not rehit:
            out = LIABLE
        elif r.catch_all and not r.limited:
            out = NOT_LIABLE if rehit else LIABLE
        elif r.limited and out == SILENT:
            out = OUT_OF_SCOPE
    return out


def liability_table(texts: dict[str, str], parties: Parties) -> dict[str, Any]:
    """{path: {scenario: outcome}} 와 한도·문장 구조."""
    rules_by: dict[str, list[LiabilityRule]] = {}
    caps: list[CapRule] = []
    for path, text in texts.items():
        r, c = parse_liability(path, text, parties)
        if any(x.obligor == "ours" for x in r):
            rules_by[path] = r
        caps.extend(x for x in c if x.obligor == "ours")
    table = {p: {k: clause_outcome(rs, k) for k, _ in SCENARIOS} for p, rs in rules_by.items()}
    return {"table": table, "rules": rules_by, "caps": caps}


def _num(path: str) -> str:
    m = re.search(r"(\d{1,3}(?:\.\d{1,3})*)", path or "")
    return m.group(1) if m else ""


def liability_problems(lt: dict[str, Any]) -> list[dict[str, Any]]:
    probs: list[dict[str, Any]] = []
    table, rules_by, caps = lt["table"], lt["rules"], lt["caps"]
    paths = list(table)
    for i, a in enumerate(paths):
        for b in paths[i + 1:]:
            ra, rb = rules_by[a], rules_by[b]
            prec = any(_num(b) in r.refs or _num(b).split(".")[0] in r.refs for r in ra) or \
                any(_num(a) in r.refs or _num(a).split(".")[0] in r.refs for r in rb)
            if prec:
                continue
            for k, label in SCENARIOS:
                x, y = table[a][k], table[b][k]
                if {x, y} == {LIABLE, NOT_LIABLE}:
                    probs.append({"code": "LIABILITY_CONFLICT", "severity": "block", "paths": [a, b], "scenario": k,
                                  "message": f"'{label}' 에서 {a} 는 {x}, {b} 는 {y} — 같은 위험을 두 조항이 반대로 정하고 우선 관계도 없음. "
                                             "한 조항으로 모으거나 'subject to / notwithstanding' 로 우선 관계를 정할 것"})
    # 책임한도
    for c in caps:
        rs = rules_by.get(c.path) or []
        cover_cost = any(r.costs or r.defence for r in rs)
        if not (c.per_claim or c.aggregate):
            probs.append({"code": "CAP_BASIS", "severity": "fix", "paths": [c.path],
                          "message": f"{c.path} 책임한도가 건당 한도인지 누적(연간·총액) 한도인지 정하지 않음 — 둘을 구분해 적을 것"})
        if cover_cost and not c.includes_costs:
            probs.append({"code": "CAP_COSTS", "severity": "fix", "paths": [c.path],
                          "message": f"{c.path} 은 방어·변호사 비용까지 부담시키는데, 한도 문장이 배상액만 묶는지 방어·배상·면책 비용 전부를 묶는지 정하지 않음"})
        prot = sorted({p for r in rs for p in r.protected})
        if prot and not c.covers_protected:
            probs.append({"code": "CAP_PERSONS", "severity": "fix", "paths": [c.path],
                          "message": f"{c.path} 의 보호대상자({', '.join(prot)})에 대한 책임에도 한도가 적용되는지 문구에 없음"})
        if c.insured_only:
            probs.append({"code": "CAP_INSURED_ONLY", "severity": "warn", "paths": [c.path],
                          "message": f"{c.path} 한도가 보험으로 담보되는 청구에만 적용 — 보험이 거절·미담보하는 청구에는 한도가 없음"})
        if c.per_claim and not c.aggregate:
            probs.append({"code": "CAP_NO_AGGREGATE", "severity": "warn", "paths": [c.path],
                          "message": f"{c.path} 은 건당 한도만 있고 누적 한도가 없음 — 누적 상한이 필요한지 확인"})
    # 같은 위험에 한도 둘(관계 미정)
    cap_paths = sorted({c.path for c in caps})
    for i, a in enumerate(cap_paths):
        for b in cap_paths[i + 1:]:
            both = [k for k, _ in SCENARIOS if table.get(a, {}).get(k) == LIABLE and table.get(b, {}).get(k) == LIABLE]
            if both and not any(re.search(r"aggregate[^.]{0,80}(?:all|this\s+agreement)|under\s+this\s+agreement", c.sentence, re.I) for c in caps):
                probs.append({"code": "CAP_OVERLAP", "severity": "warn", "paths": [a, b],
                              "message": f"{a}·{b} 가 같은 상황('{SCENARIO_LABEL[both[0]]}')에 각각 한도를 둠 — 합산인지 별도인지 정할 것"})
    return probs


# 한글 설명의 책임 방향 — "우리 귀책 있는 손해로 한정", "NDG 디자인 원인 손해 제외" 같은 말이 수정 문구와 같은 방향인지.
_RX_KO_OURS = r"(?:우리\s*회사|우리|당사|{OURS})"
_RX_KO_THEIRS = r"(?:상대방|상대\s*회사|{THEIRS})"


def description_intents(text: str, parties: Parties) -> dict[str, str]:
    """한글 설명에서 상황별 의도 결과를 읽는다 — 읽을 수 있는 것만(나머지는 비교하지 않음)."""
    t = _ws(text)
    ours = _RX_KO_OURS.replace("{OURS}", "|".join(re.escape(x) for x in parties.ours) or "우리")
    theirs = _RX_KO_THEIRS.replace("{THEIRS}", "|".join(re.escape(x) for x in parties.theirs) or "상대방")
    out: dict[str, str] = {}
    if re.search(rf"{ours}\s*(?:의|측)?\s*귀책(?:이)?\s*(?:있는|이\s*있는)\s*(?:손해|경우|청구)?[^.]{{0,12}}(?:로|에)\s*(?:한정|제한)", t):
        out.update({"our_negligence": LIABLE, "their_negligence": NOT_LIABLE, "their_design": NOT_LIABLE})
    if re.search(rf"{ours}\s*(?:의|측)?\s*귀책\s*(?:이\s*)?없는\s*(?:손해|경우|청구)[^.]{{0,40}}(?:책임지지\s*않|부담하지\s*않|삭제|제외|면제)", t):
        out.update({"their_negligence": NOT_LIABLE, "their_design": NOT_LIABLE})
    if re.search(rf"{theirs}\s*(?:의|측)?\s*(?:귀책|과실)(?:이)?\s*없는\s*경우(?:에|로)\s*(?:한정|만)", t):
        out["their_negligence"] = NOT_LIABLE
    if re.search(rf"{theirs}\s*(?:의|측|가)?\s*(?:제공한\s*)?(?:디자인|지식재산|디자인·지식재산)[^.]{{0,20}}(?:원인|로\s*인한)[^.]{{0,30}}(?:삭제|제외|한정|책임지지\s*않|부담하지\s*않)", t):
        out["their_design"] = NOT_LIABLE
    if re.search(rf"{theirs}\s*(?:의|측)?\s*(?:귀책|과실)[^.]{{0,30}}(?:제외|면제|책임지지\s*않|부담하지\s*않)", t):
        out["their_negligence"] = NOT_LIABLE
    if re.search(rf"{ours}\s*(?:가|이)?\s*(?:제공한|지정한)?\s*사양[^.]{{0,30}}(?:한정|만\s*책임|에\s*한하여)", t):
        out["our_spec"] = LIABLE
    return out


def direction_problems(desc: str, lt: dict[str, Any], paths: list[str], parties: Parties) -> list[dict[str, Any]]:
    """설명이 말한 방향과 수정 문구의 상황별 결과가 반대면 차단."""
    want = description_intents(desc, parties)
    probs: list[dict[str, Any]] = []
    for p in paths:
        row = lt["table"].get(p)
        if not row:
            continue
        for k, v in want.items():
            got = row.get(k)
            # 뒤집힘만 본다: 설명은 '책임 없음' 인데 문구는 '책임 있음', 또는 설명은 '책임 있음' 인데 문구가 명시적으로 면제.
            # 원인을 좁힌 조항의 '범위 밖' 은 면제가 아니고 그 조항이 책임을 지우지도 않는다 — 설명 '책임 없음' 과 같은 방향.
            if (v == NOT_LIABLE and got == LIABLE) or (v == LIABLE and got == NOT_LIABLE):
                probs.append({"code": "DIRECTION_MISMATCH", "severity": "block", "paths": [p], "scenario": k,
                              "message": f"설명은 '{SCENARIO_LABEL[k]}' 을 {v} 으로 말하는데, {p} 수정 문구로는 {got} — "
                                         "부정문·예외 문구로 방향이 뒤집혔는지 확인하고 문구를 고칠 것"})
    return probs


# ── 2. 연장 ──────────────────────────────────────────────────────────────────

_RX_EXT = re.compile(r"\bextend\w*|extension|\brenew\w*|연장|갱신", re.I)
_RX_CONSENT = re.compile(r"consent\s+of\s+(?:both|the)\s+parties|mutual(?:ly)?\s+(?:written\s+)?(?:consent|agree\w*)|subject\s+to\s+(?:the\s+)?(?:prior\s+)?(?:written\s+)?(?:consent|agreement|approval)"
                         r"|upon\s+(?:mutual\s+)?(?:written\s+)?agreement|(?:if|where)\s+(?:both\s+)?parties\s+(?:so\s+)?agree|agreed\s+(?:upon\s+)?by\s+(?:both|the)\s+parties"
                         r"|consent[^.]{0,40}not\s+(?:to\s+)?be\s+unreasonably\s+withheld|쌍방\s*(?:의\s*)?(?:합의|동의)|양\s*당사자(?:의)?\s*(?:합의|동의)|합의(?:하여|에\s*따라|한\s*경우)", re.I)
_RX_NO_CONSENT = re.compile(r"without\s+(?:the\s+need\s+for\s+)?(?:any\s+)?(?:further\s+|additional\s+)?(?:consent|approval|agreement)|no\s+(?:further\s+|additional\s+)?(?:consent|approval)\s+(?:of|from|by)"
                            r"|별도(?:의)?\s*(?:동의|합의)\s*없이|추가\s*(?:동의|합의)\s*없이", re.I)
_RX_AUTO = re.compile(r"automatic\w*\s+(?:be\s+)?(?:extend|renew)|shall\s+(?:automatically\s+)?(?:be\s+)?(?:extended|renewed)\b(?![^.]{0,30}(?:by|upon)\s+mutual)|자동(?:으로)?\s*(?:연장|갱신)|(?:연장|갱신)된\s*것으로\s*본다", re.I)
_RX_OPTION = re.compile(r"(?:right|option)\s+to\s+(?:extend|renew)|may\s+(?:extend|renew)|at\s+(?:the\s+)?(?:sole\s+)?option\s+of|연장(?:을)?\s*(?:요구|선택)할\s*(?:수|권리)", re.I)
_RX_NONRENEW_BY = re.compile(r"(?:either\s+party|{THEIRS})\s+(?:may|gives?|serves?)[^.]{0,60}(?:notice\s+of\s+non-?renewal|not\s+to\s+(?:extend|renew)|terminate\s+at\s+the\s+end)"
                             r"|(?:어느\s*(?:한\s*)?(?:일방|당사자)|당사자\s*(?:일방|중\s*어느\s*한\s*쪽)|{THEIRS})[^.]{0,60}(?:해지|갱신\s*거절|연장\s*거절|종료)[^.]{0,20}(?:의사|통지)", re.I)
_RX_BREACH_COND = re.compile(r"(?:unless|provided\s+that|if\s+no|so\s+long\s+as|as\s+long\s+as)[^.]{0,80}breach|위반(?:이|사실이)?\s*없(?:는\s*한|으면|을\s*경우)|위반이\s*있[^.]{0,80}(?:경우가\s*아니면|경우를\s*제외하고|않는\s*한)", re.I)
_RX_MATERIAL = re.compile(r"material\s+breach|material\s+(?:obligation|term)|중대한\s*(?:위반|의무)", re.I)
_RX_CURE = re.compile(r"(?:cured?|remed(?:y|ied))\b[^.]{0,80}(?:within|after)|uncured|not\s+(?:been\s+)?(?:cured|remedied)|시정(?:하지|되지|기간)", re.I)
_NUMW = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve|\d+|\[[^\]]*\])(?:\s*\(\d+\))?"
_RX_PERIOD = re.compile(rf"(?:further|additional|another|renewal|successive)\s+(?:term\s+of\s+|period\s+of\s+)?{_NUMW}[\s-]*(?:years?|months?)"
                        rf"|{_NUMW}[\s-]*(?:years?|months?)[^.]{{0,30}}(?:extension|renewal|term)|\d+\s*년", re.I)
_RX_NOTICE_TIMING = re.compile(r"(?:at\s+least|no\s+later\s+than|not\s+less\s+than)\s+(?:\w+\s*\(\d+\)|\w+|\d+|\[[^\]]*\])\s*(?:days?|months?)[^.]{0,40}(?:prior|before)|(?:\d+|\[[^\]]*\])\s*(?:일|개월)\s*전", re.I)

_RX_INTENT_EXT = re.compile(r"(?:위반|breach)(?:이|사항이|사실이)?\s*없(?:는\s*한|으면|을\s*경우|다면)|자동\s*(?:연장|갱신)|unless[^.]{0,30}breach", re.I)
_RX_INTENT_AUTO = re.compile(r"자동\s*(?:연장|갱신)|automatic(?:ally)?\s+(?:renew|extend)", re.I)


def renewal_intent(request_text: str, answers_text: str) -> dict[str, bool]:
    t = _ws(request_text + " " + answers_text)
    if not _RX_EXT.search(t):
        return {}
    return {"unless_breach": bool(_RX_INTENT_EXT.search(t)), "automatic": bool(_RX_INTENT_AUTO.search(t))}


def renewal_structure(text: str, parties: Parties) -> dict[str, Any]:
    ss = [s for s in sentences(text) if _RX_EXT.search(s)]
    t = " ".join(ss)
    rx_nonrenew = re.compile(_RX_NONRENEW_BY.pattern.replace("{THEIRS}", parties.rx_theirs.pattern), re.I)
    holder = ""
    m = _RX_OPTION.search(t)
    if m:
        holder = parties.who(t[max(0, m.start() - 80):m.start()]) or parties.who(t[m.end():m.end() + 60])
    return {
        "present": bool(ss),
        "consent_required": bool(_RX_CONSENT.search(t)) and not _RX_NO_CONSENT.search(t),
        "no_consent_stated": bool(_RX_NO_CONSENT.search(t)),
        "automatic": bool(_RX_AUTO.search(t)),
        "option_holder": holder,
        "counterparty_can_block": bool(rx_nonrenew.search(t)),
        "breach_condition": bool(_RX_BREACH_COND.search(t)),
        "material": bool(_RX_MATERIAL.search(t)),
        "cure": bool(_RX_CURE.search(t)),
        "period": bool(_RX_PERIOD.search(t)),
        "notice_timing": bool(_RX_NOTICE_TIMING.search(t)),
        "text": t,
    }


def extension_outcome(st: dict[str, Any]) -> str:
    """'우리 위반이 없을 때' 연장되는가."""
    if not st.get("present"):
        return "연장 조항 없음"
    if st["consent_required"]:
        return "상대방 동의가 있어야 연장(상대방이 거절 가능)"
    if st["counterparty_can_block"]:
        return "상대방 불갱신 통지로 막을 수 있음"
    if st["automatic"]:
        return "자동 연장(상대방 동의 불필요)"
    if st["option_holder"] == "ours":
        return "우리 통지로 연장(상대방 동의 불필요)"
    if st["option_holder"] == "theirs":
        return "상대방 선택으로 연장"
    return "연장 요건 불명"


def renewal_problems(path: str, st: dict[str, Any], intent: dict[str, bool]) -> list[dict[str, Any]]:
    if not intent.get("unless_breach") or not st.get("present"):
        return []
    probs: list[dict[str, Any]] = []
    out = extension_outcome(st)

    def add(code: str, msg: str, sev: str = "") -> None:
        sev = sev or ("block" if code in _BLOCK_CODES else "fix")
        probs.append({"code": code, "severity": sev, "paths": [path], "message": msg})

    if st["consent_required"]:
        add("RENEWAL_CONSENT", f"{path}: 요청은 '위반이 없으면 연장' 인데 문구는 여전히 상대방 동의(또는 '부당하게 거절하지 못함')가 필요 — 반영 완료가 아님")
    if st["counterparty_can_block"]:
        add("RENEWAL_BLOCKABLE", f"{path}: 상대방이 불갱신 통지로 연장을 막을 수 있음 — 요청 목적과 어긋남")
    if not st["consent_required"] and not st["automatic"] and st["option_holder"] != "ours":
        add("RENEWAL_HOLDER", f"{path}: 누가 연장을 정하는지(자동 연장 또는 우리 회사의 연장권) 문구에 없음")
    if intent.get("automatic") and not st["automatic"] and st["option_holder"] == "ours":
        add("RENEWAL_NOT_AUTOMATIC", f"{path}: 답변은 자동 연장인데 문구는 우리가 통지해야 연장되는 선택권 — 자동 연장으로 쓰거나 선택권으로 한 이유를 measures 에")
    if not st["breach_condition"]:
        add("RENEWAL_BREACH_SCOPE", f"{path}: 연장을 거절할 수 있는 위반이 무엇인지(중대한 위반) 정하지 않음")
    elif not st["material"]:
        add("RENEWAL_BREACH_SCOPE", f"{path}: 경미한 위반으로도 연장을 거절할 수 있게 읽힘 — '중대한 위반' 으로 한정할 것")
    if st["breach_condition"] and not st["cure"]:
        add("RENEWAL_CURE", f"{path}: 위반이 있을 때 서면 통지·시정기간을 거쳐도 시정되지 않은 경우로 한정하는 시정절차가 없음")
    if not st["period"]:
        add("RENEWAL_PERIOD", f"{path}: 연장 기간이 문구에 없음")
    if st["option_holder"] == "ours" and not st["automatic"] and not st["notice_timing"]:
        add("RENEWAL_EXERCISE", f"{path}: 연장권 행사 방식·기한(만료 몇 개월 전 서면 통지)이 없음")
    if not st["no_consent_stated"] and not st["consent_required"]:
        add("RENEWAL_FURTHER_CONSENT", f"{path}: 연장에 상대방의 추가 동의가 필요 없다는 점을 명시하지 않음")
    _ = out
    return probs


# ── 3. 종료 후 활동 ────────────────────────────────────────────────────────────

_RX_POST = re.compile(r"after\s+(?:the\s+)?(?:effective\s+date\s+of\s+)?(?:termination|expiration|expiry)|following\s+(?:the\s+)?(?:termination|expiration)"
                      r"|upon\s+(?:the\s+)?(?:termination|expiration)|as\s+from\s+the\s+termination|post-?termination|sell[- ]?off|wind[- ]?down"
                      r"|(?:종료|만료|해지)\s*(?:후|이후|시)", re.I)
_ACTIVITIES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("order", "확정 주문 납품", re.compile(r"purchase\s+orders?|(?:accepted|confirmed|binding)\s+orders?|orders?\s+(?:accepted|confirmed|received)|order\s+fulfil+ment|확정\s*(?:주문|수주)|수주", re.I)),
    ("selloff", "재고 판매", re.compile(r"sell[- ]?off|inventor(?:y|ies)|(?:existing|remaining)\s+stock|재고", re.I)),
    ("service", "A/S·보증 부품", re.compile(r"warranty|after[- ]sales|spare\s+parts?|repair|replacement\s+parts?|\bA/S\b"
                                          # '보증금'·'연대보증'·'보증인'·'보증보험' 은 A/S 가 아니다(임대차 보증금을 A/S 로 읽음, 2026-11-03)
                                          r"|(?<!연대)보증(?!금|인|보험|채무|서|증권)|수리|부품", re.I)),
)
_RX_LICENSE = re.compile(r"(?:use|using)\s+(?:the\s+)?(?:design|reference|trademark|logo|marks?|licensed)|right\s+to\s+use|licen[cs]e\s+(?:shall\s+)?(?:continue|surviv)|entitled\s+to\s+use|may\s+use|사용(?:할\s*수|권)", re.I)
_RX_REPORT = re.compile(r"report|statement|notif\w+|record|account|정산|보고|통지", re.I)
_RX_PERIOD_ANY = re.compile(r"(?:\d+|\[[^\]]*\]|\w+\s*\(\d+\))\s*(?:days?|weeks?|months?|years?)|warranty\s+period|일\b|개월|년", re.I)
_RX_ROYALTY_BASE = re.compile(r"(?:royalt\w*|reimbursement|licen[cs]e\s+fee|로열티|사용료)[^.]{0,120}(?:%|percent|per\s+(?:unit|item)|sold|sales|price|매출|판매)"
                              r"|(?:%|percent)[^.]{0,80}(?:royalt|reimbursement)", re.I)
_RX_ROYALTY = re.compile(r"royalt\w*|reimbursement|licen[cs]e\s+fee|remuneration|commission|로열티|사용료|실시료", re.I)
_RX_NONSALE_IN_BASE = re.compile(r"parts?\s+(?:supplied|delivered|provided)|(?:supplied|delivered|provided)\s+(?:spare\s+)?parts|repairs?|services?\s+(?:performed|rendered)|warranty\s+(?:work|service)|free\s+of\s+charge|부품\s*공급|수리", re.I)
_RX_NO_ROYALTY_NONSALE = re.compile(r"no\s+(?:royalt\w*|reimbursement|fee)[^.]{0,120}(?:warranty|repair|spare|parts|free\s+of\s+charge|storage|after[- ]sales)"
                                    r"|(?:warranty|repair|spare\s+parts?|after[- ]sales)[^.]{0,120}(?:shall\s+not\s+(?:be\s+subject\s+to|give\s+rise\s+to|bear)|not\s+subject\s+to|free\s+of)\s+(?:any\s+)?(?:royalt|reimbursement|fee)"
                                    r"|(?:only|solely)\s+(?:for|on|in\s+respect\s+of)[^.]{0,40}(?:sold|sales)[^.]{0,80}(?:royalt|reimbursement)|(?:royalt|reimbursement)[^.]{0,80}(?:only|solely)\s+(?:for|on|in\s+respect\s+of)[^.]{0,30}(?:sold|sales?)"
                                    r"|무상\s*(?:A/S|수리|보증)[^.]{0,40}(?:로열티|사용료)[^.]{0,10}(?:없|제외|부과하지)", re.I)
_RX_SOLD_BEFORE_ONLY = re.compile(r"sold\s+(?:prior\s+to|before)\s+(?:the\s+)?(?:effective\s+date\s+of\s+)?(?:termination|expiration|expiry)|종료\s*(?:전|이전)(?:에)?\s*판매", re.I)
_RX_SOLD_DURING = re.compile(r"(?:sold|delivered)\s+(?:during|within|in\s+accordance\s+with|pursuant\s+to|under)[^.]{0,60}(?:sell[- ]?off|period|paragraph|subparagraph|clause|\([a-z]\))"
                             r"|including\s+(?:those|products?|design\s+products?)[^.]{0,60}(?:sold|delivered)[^.]{0,40}(?:after|following|during)"
                             r"|(?:sold|delivered)[^.]{0,40}(?:before|prior\s+to)[^.]{0,40}or\s+(?:during|after|pursuant)", re.I)
_RX_HARD_CAP = re.compile(r"(?:but\s+)?in\s+no\s+event\s+(?:longer|later|more)\s+than|not\s+(?:to\s+)?exceed(?:ing)?\s+(?:\[|\d)|최대\s*(?:\[|\d)", re.I)
_RX_WARRANTY_TIE = re.compile(r"(?:until|for\s+the\s+duration\s+of|throughout)[^.]{0,40}warranty|(?:expiry|expiration|end)\s+of\s+(?:the\s+|any\s+|its\s+)?(?:applicable\s+)?warranty|warranty\s+(?:period|obligations?)\s+(?:applicable|remain|continue)|보증기간\s*(?:종료|만료)\s*(?:시|까지)", re.I)
_RX_BOTH_ENDS = (re.compile(r"terminat\w+|해지", re.I), re.compile(r"expir\w+|만료", re.I))
_RX_TERM_CAUSE = re.compile(r"for\s+any\s+reason|regardless\s+of\s+(?:the\s+)?(?:reason|cause)|other\s+than|except\s+(?:in\s+the\s+case\s+of\s+|for\s+)?(?:a\s+)?termination|termination\s+(?:by\s+\w+\s+)?for\s+(?:cause|breach)"
                            r"|termination\s+(?:pursuant|under|in\s+accordance)|사유를\s*불문|해지\s*사유", re.I)
_RX_BLANKET_STOP = re.compile(r"(?:shall|must)\s+(?:immediately\s+)?(?:refrain|cease|stop|discontinue)[^.]{0,200}(?:manufactur|sale|sell|use|distribut)|(?:즉시\s*)?(?:중단|중지)하여야", re.I)
_RX_RESTRICT = re.compile(r"(?:without\s+(?:the\s+)?(?:reference|use)\s+(?:to\s+)?|shall\s+not\s+use\s+(?:the\s+)?(?:design\s+)?(?:reference|designation|name|trademark|logo)?\s*)"
                          r"[\"“'‘]([^\"”'’]{3,60})[\"”'’]", re.I)
_RX_TERRITORY_NEAR = re.compile(r"\b(?:in|within|to|for)\s+((?:Mainland\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})")


_RX_ITEM = re.compile(r"(?:(?<=\s)|^)(?:\(\s*[a-z]\s*\)|[a-z]\]|\(\s*(?:i|ii|iii|iv|v|vi)\s*\))\s+", re.I)


def _units(text: str) -> list[str]:
    """종료 후 처리 조항의 판단 단위 — 열거 항목((a)(b)…)이 있으면 항목, 없으면 문장."""
    t = _ws(text)
    # 항목 표지는 차례대로((a)→(b)→(c))인 것만 — 본문 안의 "under (a) and (b)" 같은 참조를 항목 경계로 읽지 않는다.
    marks = []
    seq: list[str] = []
    for m in _RX_ITEM.finditer(t):
        letter = re.sub(r"[^a-z]", "", m.group(0).lower())
        if not marks:
            if letter == "a":
                seq = list("abcdefghijklmnop")
            elif letter == "i":
                seq = ["i", "ii", "iii", "iv", "v", "vi"]
            else:
                continue
        if len(marks) < len(seq) and letter == seq[len(marks)]:
            marks.append(m)
    if len(marks) >= 2:
        out = [t[:marks[0].start()].strip()]
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(t)
            out.append(t[m.start():end].strip())
        return [u for u in out if len(u) > 3]
    return sentences(t)


def wind_down_structure(texts: dict[str, str]) -> dict[str, Any]:
    """종료 후 처리 조항(들)을 찾고 활동별로 기간·사용권·보고·로열티를 본다."""
    wind_paths = [p for p, t in texts.items()
                  if _RX_POST.search(t) and sum(bool(rx.search(t)) for _, _, rx in _ACTIVITIES) >= 1
                  and re.search(r"entitled|\bmay\b|permitted|allowed|right\s+to|continue\s+to|허용|할\s*수", t, re.I)
                  and not _RX_ROYALTY_BASE.search(t[:200])]
    acts: dict[str, dict[str, Any]] = {}
    units = [u for p in wind_paths for u in _units(texts[p])]
    for key, label, rx in _ACTIVITIES:
        # 활동 이름이 머리에 있는 항목(예: "(c) After-Sales Service Parts: …")을 우선 — 다른 항목의 낱말 한 번으로 섞지 않는다
        own = [u for u in units if rx.search(u[:80])] or [u for u in units if rx.search(u)]
        if not own:
            continue
        j = " ".join(own)
        acts[key] = {"label": label, "sentences": own, "period": bool(_RX_PERIOD_ANY.search(j)),
                     "license": bool(_RX_LICENSE.search(j)), "report": bool(_RX_REPORT.search(j)),
                     "royalty": bool(_RX_ROYALTY.search(j))}
    wtext = " ".join(texts[p] for p in wind_paths)
    under = bool(re.search(r"under\s+this\s+Agreement|in\s+accordance\s+with\s+this\s+Agreement|(?:본|이)\s*계약에\s*(?:따라|의하여)",
                           wtext, re.I)) and set(acts) <= {"order"}
    return {"paths": wind_paths, "activities": acts, "units": units, "under_agreement": under}


def wind_down_problems(texts: dict[str, str], original: dict[str, str] | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    wd = wind_down_structure(texts)
    probs: list[dict[str, Any]] = []
    acts, wpaths = wd["activities"], wd["paths"]
    if not wpaths:
        return wd, probs
    wtext = " ".join(texts[p] for p in wpaths)

    def add(code: str, paths: list[str], msg: str, sev: str = "") -> None:
        sev = sev or ("block" if code in _BLOCK_CODES else "fix")
        probs.append({"code": code, "severity": sev, "paths": paths, "message": msg})

    # 종료 때 남은 확정 주문을 '이 계약에 따라' 계속 이행하게 한 조항(공급계약 15.6 형태)은 그 주문의 기간·사용권·정산을 계약 본문이
    # 그대로 정한다 — 라이선스형 종료 후 판매처럼 따로 기간·사용권·보고를 요구하지 않는다(2026-11-13 시디즈 영문 공급계약 실측).
    under_this = bool(re.search(r"under\s+this\s+Agreement|in\s+accordance\s+with\s+this\s+Agreement|(?:본|이)\s*계약에\s*(?:따라|의하여)",
                                wtext, re.I)) and set(acts) <= {"order"}
    for key, a in ([] if under_this else acts.items()):
        if not a["period"]:
            add("WD_PERIOD", wpaths, f"종료 후 '{a['label']}' 의 허용 기간이 없음")
        if not a["license"]:
            add("WD_LICENSE", wpaths, f"종료 후 '{a['label']}' 에 필요한 사용권(디자인·표시 사용 등)이 없음")
        if key in ("order", "selloff") and not a["report"]:
            add("WD_REPORT", wpaths, f"종료 후 '{a['label']}' 의 정산·보고 의무가 없음", "warn")
    # 로열티 산정 대상 — 비판매 활동
    roy_paths = [p for p, t in texts.items() if _RX_ROYALTY_BASE.search(t) or (p in wpaths and _RX_ROYALTY.search(t))]
    for p in roy_paths:
        for s in sentences(texts[p]):
            if _RX_ROYALTY.search(s) and _RX_NONSALE_IN_BASE.search(s) and not _RX_NO_ROYALTY_NONSALE.search(s) \
                    and not re.search(r"\bno\s+(?:royalt|reimbursement)|not\s+(?:be\s+)?(?:subject|payable|due)", s, re.I):
                add("ROYALTY_NONSALE", [p], f"{p}: 로열티가 판매가 아닌 활동(부품 공급·수리 등)에도 붙게 읽힘 — '{s[:140]}'")
    if "service" in acts and not _RX_NO_ROYALTY_NONSALE.search(" ".join(texts[p] for p in roy_paths + wpaths)):
        add("ROYALTY_NONSALE_UNSTATED", sorted(set(roy_paths[:2] + wpaths)),
            "무상 보증수리·부품 보관 등 비판매 A/S 활동에 로열티가 붙지 않는다는 점(로열티는 판매분에만)이 문구에 없음")
    # 종료 후 판매분의 A/S
    if "service" in acts and ({"order", "selloff"} & set(acts)):
        svc = " ".join(acts["service"]["sentences"])
        if _RX_SOLD_BEFORE_ONLY.search(svc) and not _RX_SOLD_DURING.search(svc):
            add("WD_SERVICE_SCOPE", wpaths, "A/S 허용이 종료 전 판매분에만 걸려 있어, 종료 후 재고 판매·확정 주문 납품분의 A/S 가 빠짐")
        if _RX_HARD_CAP.search(svc) and not re.search(r"not\s+(?:be\s+)?shorter\s+than|at\s+least\s+(?:the|until)", svc, re.I):
            add("WD_SERVICE_CAP", wpaths, "A/S 기간에 고정 상한('in no event longer than')이 있어 보증의무보다 사용권이 먼저 끝날 수 있음 — 보증기간 만료까지 존속시킬 것")
        elif not _RX_WARRANTY_TIE.search(svc) and not re.search(r"warranty\s+period", svc, re.I):
            add("WD_SERVICE_CAP", wpaths, "A/S 사용권 기간이 보증의무 기간과 연결되어 있지 않음", "warn")
    # 지역·표시 제한과의 충돌
    for p, t in texts.items():
        for m in _RX_RESTRICT.finditer(t):
            mark = m.group(1).strip()
            around = t[max(0, m.start() - 200):m.end() + 120]
            terr = next((x.group(1) for x in _RX_TERRITORY_NEAR.finditer(around) if x.group(1) not in ("Studio", "Design")), "")
            uses = [s for s in _units(wtext) if mark.lower() in s.lower() and re.search(r"use|entitled|may", s, re.I)]
            if not uses:
                continue
            ok = any(re.search(rf"subject\s+to|in\s+accordance\s+with[^.]{{0,40}}(?:restriction|clause|article)|same\s+restrictions|{re.escape(terr) if terr else '(?!x)x'}"
                               rf"|except\s+(?:in|within)|{re.escape(_num(p)) if _num(p) else '(?!x)x'}", s, re.I) for s in uses)
            if not ok:
                add("WD_RESTRICTION", sorted({p, *wpaths}),
                    f"종료 후 '{mark}' 사용을 허용하면서 {p} 의 제한(" + (f"{terr} 에서는 " if terr else "") + "이 표시 사용 불가)을 유지하지 않음")
    # 만료·중도해지 적용 범위
    if not all(rx.search(wtext) for rx in _RX_BOTH_ENDS):
        add("WD_SCOPE", wpaths, "종료 후 허용이 만료와 중도해지 가운데 어디에 적용되는지 명시하지 않음", "warn" if under_this else "")
    elif not _RX_TERM_CAUSE.search(wtext):
        add("WD_SCOPE", wpaths, "중도해지(우리 귀책 해지 포함) 시에도 적용되는지 해지 사유별 적용 범위를 정하지 않음", "warn")
    # 종료 즉시 중단 조항과의 관계
    for p, t in texts.items():
        if p in wpaths:
            continue
        if _RX_BLANKET_STOP.search(t) and _RX_POST.search(t):
            linked = re.search(r"subject\s+to|except\s+as\s+(?:provided|set)|notwithstanding|단서|제외하고", t, re.I) or \
                re.search(rf"notwithstanding[^.]{{0,40}}{re.escape(_num(p))}", wtext, re.I)
            if not linked:
                add("WD_BLANKET_STOP", [p, *wpaths], f"{p} 의 종료 즉시 중단 의무가 종료 후 허용 조항과 연결되지 않음('subject to' 또는 'notwithstanding')")
    # 로열티 존속이 계약기간까지만
    for p, t in texts.items():
        m = re.search(r"until\s+the\s+end\s+of\s+the\s+(?:contract|agreement)(?:\s+(?:period|term))?", t, re.I)
        if m and _RX_ROYALTY.search(t) and ({"order", "selloff"} & set(acts)):
            tail = t[m.end():m.end() + 260]
            if not re.search(r"provided|except|save|including|sold\s+(?:after|during|pursuant)|surviv", tail, re.I):
                add("WD_ROYALTY_TERM", [p], f"{p}: 로열티를 '계약기간 종료까지' 로만 정해 종료 후 허용 판매분의 로열티·정산 근거가 없음")
    return wd, probs


# ── 4. 수정 전후 비교 ──────────────────────────────────────────────────────────

def change_problems(original: dict[str, str], revised: dict[str, str], parties: Parties,
                    lt_before: dict[str, Any], lt_after: dict[str, Any]) -> list[dict[str, Any]]:
    probs: list[dict[str, Any]] = []
    # 책임 확대: 수정 전에는 '책임 없음/정함 없음' 이던 상황이 수정 후 '책임 있음'
    for p, row in lt_after["table"].items():
        before = lt_before["table"].get(p) or {}
        for k, label in SCENARIOS:
            if row.get(k) == LIABLE and before.get(k) in (NOT_LIABLE,) and p in original:
                probs.append({"code": "NEW_LIABILITY", "severity": "block", "paths": [p], "scenario": k,
                              "message": f"{p}: 수정 전에는 '{label}' 에 책임이 없었는데 수정 후 책임이 생김"})
    # 새 로열티 대상
    for p, t in revised.items():
        o = original.get(p, "")
        new_s = [s for s in sentences(t) if _RX_ROYALTY.search(s) and s not in _ws(o)]
        for s in new_s:
            if _RX_NONSALE_IN_BASE.search(s) and not _RX_NONSALE_IN_BASE.search(o) and not re.search(r"\bno\s+(?:royalt|reimbursement)|not\s+(?:be\s+)?(?:subject|payable|due)", s, re.I):
                probs.append({"code": "NEW_ROYALTY_BASE", "severity": "block", "paths": [p],
                              "message": f"{p}: 수정으로 로열티 산정 대상에 판매가 아닌 활동이 새로 들어감 — '{s[:140]}'"})
    # 지워진 우리 권리·예외
    rx_right = re.compile(rf"{parties.rx_ours.pattern}[^.]{{0,40}}(?:may|is\s+entitled|shall\s+be\s+entitled|shall\s+have\s+the\s+right|is\s+permitted)"
                          rf"|{parties.rx_theirs.pattern}\s+shall\s+not\s+unreasonably|shall\s+not\s+be\s+liable", re.I)
    for p, o in original.items():
        if p not in revised:
            continue
        r = _ws(revised[p])
        for s in sentences(o):
            if rx_right.search(s) and _ws(s) not in r:
                core = re.sub(r"\W+", " ", s.lower())
                keep = [w for w in core.split() if len(w) > 4]
                hit = sum(1 for w in keep if w in r.lower())
                if keep and hit / len(keep) < 0.6:
                    probs.append({"code": "RIGHT_REMOVED", "severity": "warn", "paths": [p],
                                  "message": f"{p}: 우리에게 유리한 기존 문장이 수정으로 사라짐 — '{s[:140]}'"})
    return probs


# ── 5. 합의 기록 ──────────────────────────────────────────────────────────────

_RX_AGREEMENT_SRC = re.compile(r"이메일|메일|e-?mail|구두|통화|미팅|회의|협의|합의|확인해\s*(?:준|주었)|confirmed", re.I)
_RX_QUOTE = re.compile(r"[\"“]([^\"”\n]{25,600})[\"”]")


def _overlap(a: str, b: str) -> float:
    """문구 a 가 b 에 얼마나 그대로 들어 있는가 — 낱말 3개 묶음(shingle) 기준. 낱말 하나씩 세면 흔한 낱말이 계약 어디엔가
    있다는 이유로 '부분 반영' 이 된다(정의가 없는데 'price', 'dealers' 가 다른 조항에 있음)."""
    wa = re.findall(r"[a-z0-9]+", a.lower())
    wb = " " + " ".join(re.findall(r"[a-z0-9]+", b.lower())) + " "
    if len(wa) < 3:
        return 1.0 if wa and f" {' '.join(wa)} " in wb else 0.0
    grams = [" ".join(wa[i:i + 3]) for i in range(len(wa) - 2)]
    return sum(1 for g in grams if f" {g} " in wb) / len(grams)


def agreement_records(request_text: str, answers_text: str, original_all: str, revised_all: str,
                      renewal: dict[str, Any] | None = None, parties: Parties | None = None) -> list[dict[str, Any]]:
    """요청·답변에 적힌 이메일·구두 합의를 원문 반영 여부와 함께 — 계약 원문(문서)과 합의(문서 밖)를 섞지 않는다."""
    out: list[dict[str, Any]] = []
    if parties is not None:
        # 합의 문구는 상호("SIDIZ")로, 계약은 정의어("Customer")로 쓴다 — 같은 당사자는 같은 표지로 바꿔 비교한다.
        def norm(t: str) -> str:
            return parties.rx_theirs_alias.sub(" partytheirs ", parties.rx_ours_alias.sub(" partyours ", t))
        original_all, revised_all = norm(original_all), norm(revised_all)
    else:
        def norm(t: str) -> str:
            return t

    def grade(x: float) -> str:
        return "반영" if x >= 0.85 else ("부분 반영" if x >= 0.6 else "미반영")

    # 번호 요청 단위(1. … 2. …)로 나눈다 — 빈 줄로 나누면 "메일로 이렇게 정의했다" 와 인용문이 갈라진다.
    blocks = re.split(r"\n(?=\s*\d{1,2}\s*[.)]\s)", _s(request_text)) + [_s(answers_text)]
    for blk in blocks:
        if not _RX_AGREEMENT_SRC.search(blk):
            continue
        src = "이메일" if re.search(r"이메일|메일|e-?mail", blk, re.I) else ("구두" if re.search(r"구두|통화|미팅|회의", blk) else "협의")
        quotes = [m for m in _RX_QUOTE.finditer(blk)]
        latin_q = [m.group(1) for m in quotes if len(re.findall(r"[A-Za-z]", m.group(1))) > 0.6 * len(m.group(1))]
        for m in quotes:
            q = m.group(1)
            # 인용 바로 앞(같은 문장·앞 문장)에 합의 출처가 있어야 합의다 — 계약 문구를 인용한 것("동의(subject to …)로만 규정")은 아니다.
            before = blk[max(0, m.start() - 160):m.start()]
            if not _RX_AGREEMENT_SRC.search(before) or re.search(r"(?:로만|으로)?\s*규정되어|정하고\s*있|규정하", blk[m.end():m.end() + 30]):
                continue
            is_latin = q in latin_q
            if is_latin:
                o, r = _overlap(norm(q), original_all), _overlap(norm(q), revised_all)
                out.append({"source": src, "content": _ws(q)[:300], "in_original": grade(o), "in_revision": grade(r)})
            elif latin_q:
                # 국문으로 적은 합의(예: 이메일 확인 내용) — 같은 요청에 적은 영문 문구로 반영 여부를 본다
                # 영문 문구의 문장 가운데 가장 잘 맞는 것 — 제안 문구가 기존 제한을 다시 적은 문장과 허용 문장을 함께 담는다.
                # 원문에 이미 있는 제한을 다시 적은 문장이 아니라, 원문과 가장 다른(= 새로 넣자는) 문장으로 본다.
                lsents = [x for q2 in latin_q for x in sentences(q2)] or latin_q
                best = min(lsents, key=lambda x: (_overlap(norm(x), original_all), -len(x)))
                o, r = _overlap(norm(best), original_all), _overlap(norm(best), revised_all)
                out.append({"source": src, "content": _ws(q)[:300], "in_original": grade(o), "in_revision": grade(r)})
            else:
                out.append({"source": src, "content": _ws(q)[:300], "in_original": "확인 필요", "in_revision": "확인 필요"})
    if renewal and renewal.get("intent", {}).get("unless_breach"):
        out.append({"source": "요청·답변", "content": "위반이 없으면 연장" + (" (자동 연장)" if renewal["intent"].get("automatic") else ""),
                    "in_original": "반영" if renewal.get("before_outcome", "").startswith(("자동", "우리 통지")) else "미반영",
                    "in_revision": "반영" if not [p for p in renewal.get("problems") or [] if p["severity"] in ("block", "fix")]
                    and renewal.get("after_outcome", "").startswith(("자동", "우리 통지")) else "부분 반영"})
    seen: set[str] = set()
    uniq = []
    for x in out:
        k = x["content"][:80]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(x)
    return uniq


# ── 묶음 ──────────────────────────────────────────────────────────────────────

def evaluate(*, original: dict[str, str], revised: dict[str, str], parties: Parties, request_text: str = "",
             answers_text: str = "", descriptions: dict[str, str] | None = None) -> dict[str, Any]:
    """original/revised: {조항 표시: 원문} — revised 는 모든 수정안을 넣은 본(신설 항 포함).

    descriptions: {조항 표시: 그 조항 수정의 한글 설명(필요한 조치·위험)} — 방향 검증용.
    """
    lt_b = liability_table(original, parties)
    lt_a = liability_table(revised, parties)
    probs = liability_problems(lt_a)
    for p, desc in (descriptions or {}).items():
        probs += direction_problems(desc, lt_a, [p], parties)
    intent = renewal_intent(request_text, answers_text)
    ren: dict[str, Any] = {"intent": intent}
    ren_paths = [p for p, t in revised.items() if _RX_EXT.search(t) and re.search(r"term|years?|기간|년", t, re.I)
                 and not _RX_POST.search(t[:120])]
    if ren_paths:
        p = ren_paths[0]
        st_a = renewal_structure(revised[p], parties)
        st_b = renewal_structure(original.get(p, ""), parties)
        ren.update({"path": p, "before_outcome": extension_outcome(st_b), "after_outcome": extension_outcome(st_a),
                    "structure": {k: v for k, v in st_a.items() if k != "text"}})
        rp = renewal_problems(p, st_a, intent)
        ren["problems"] = rp
        probs += rp
    wd, wp = wind_down_problems(revised, original)
    _wd_b, wp_b = wind_down_problems(original)
    probs += wp
    probs += change_problems(original, revised, parties, lt_b, lt_a)
    agreements = agreement_records(request_text, answers_text, " ".join(original.values()), " ".join(revised.values()), ren,
                                  parties=parties)
    scen_rows = []
    for k, label in SCENARIOS:
        row = {"scenario": k, "label": label,
               "before": {p: v[k] for p, v in lt_b["table"].items() if v[k] != SILENT},
               "after": {p: v[k] for p, v in lt_a["table"].items() if v[k] != SILENT}}
        if row["before"] or row["after"]:
            scen_rows.append(row)
    wd_rows = [{"activity": a["label"], "period": a["period"], "license": a["license"], "report": a["report"],
                "royalty_mentioned": a["royalty"]} for a in wd["activities"].values()]
    # 중복 제거(같은 코드·같은 조항·같은 상황)
    seen: set[tuple[str, str, str]] = set()
    uniq = []
    nonsale = {",".join(p["paths"]) for p in probs if p["code"] == "ROYALTY_NONSALE"}
    probs = [p for p in probs if not (p["code"] == "NEW_ROYALTY_BASE" and ",".join(p["paths"]) in nonsale)]
    for p in probs:
        k = (p["code"], ",".join(p["paths"]), p.get("scenario", ""))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return {
        "liability": scen_rows,
        "caps": [{"path": c.path, "per_claim": c.per_claim, "aggregate": c.aggregate, "includes_costs": c.includes_costs,
                  "covers_protected": c.covers_protected, "insured_only": c.insured_only} for c in lt_a["caps"]],
        "renewal": ren,
        "wind_down": {"paths": wd["paths"], "activities": wd_rows, "under_agreement": bool(wd.get("under_agreement")), "before_problems": [p["code"] for p in wp_b]},
        "agreements": agreements,
        "problems": uniq,
        "blocking": [p for p in uniq if p["severity"] == "block"],
        "to_fix": [p for p in uniq if p["severity"] in ("block", "fix")],
    }


__all__ = [
    "LIABLE", "NOT_LIABLE", "SILENT", "SCENARIOS", "Parties", "agreement_records", "change_problems", "clause_outcome",
    "description_intents", "direction_problems", "evaluate", "extension_outcome", "liability_problems", "liability_table",
    "parse_liability", "renewal_intent", "renewal_problems", "renewal_structure", "sentences", "wind_down_problems",
]
