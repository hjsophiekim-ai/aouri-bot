"""Entity Resolution — 법적 계약당사자와 브랜드·상호·사업명을 분리한다.

2026-09-29 지시 (범용 보정)
─────────────────────────
계약서에는 브랜드명·사업명·상호·법인명이 섞여 나온다. 이를 같은 법적 당사자로
오인하거나, 브랜드를 독립 법인처럼 다루면 권리·의무의 귀속 주체가 틀린다.
그래서 모든 검토 **전에** 당사자마다 아래를 따로 확정한다.

    legal_entity_name  권리·의무가 귀속되는 법인 (예: 주식회사 시디즈)
    brand_name         브랜드·상호·사업부명 (예: 알로소)
    role_in_contract   계약상 역할 (예: 브랜드·제품 제작 및 판매 주체)
    label              계약서가 쓰는 약칭 (예: “알로소”, “갑”)
    signing_entity     서명란의 법인
    affiliated         퍼시스그룹 계열사인가

사실관계의 출처는 세 가지이고, 앞의 것이 이긴다.
  1. 담당자가 알려 준 사실("알로소는 주식회사 시디즈의 브랜드")
  2. `group_entities` registry
  3. 계약서의 표기(외부 당사자는 적힌 그대로)

계약서에 "주식회사 알로소"라고 적혀 있어도 그것을 사실로 받아들이지 않는다 —
`LEGAL_ENTITY_MISMATCH` 로 표시하고, 정정은 `entity_name_correction` 이 한다.

불일치 유형
──────────
  BRAND_AS_LEGAL_ENTITY          브랜드에 법인격 표기를 붙임(주식회사 알로소)
  BRAND_ONLY_PARTY               당사자 자리에 브랜드만 적음
  GROUP_NAME_AS_PARTY            그룹명(퍼시스그룹)을 당사자로 씀
  PREAMBLE_SIGNATURE_MISMATCH    서두와 서명란의 법인명이 다름
  NON_PARTY_AFFILIATE_AS_PARTY   당사자가 아닌 계열사를 본문에서 당사자처럼 씀

하나라도 있으면 `REVIEW_FAILED_LEGAL_ENTITY_MISMATCH`. 정정 문안이 함께 나가므로
전달은 막지 않는다(`delivery_gate` — 제거·기록 후 전달).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from runtime.review.entity_name_correction import (
    KIND_BRAND,
    KIND_GROUP,
    BrandFact,
    find_name_hits,
    registry_brand_facts,
    split_party_regions,
)
from runtime.review.group_entities import (
    GROUP_ENTITIES,
    GroupEntity,
    _norm,
    resolve_entity,
)

STATUS_LEGAL_ENTITY_MISMATCH = "REVIEW_FAILED_LEGAL_ENTITY_MISMATCH"

MISMATCH_BRAND_AS_LEGAL_ENTITY = "BRAND_AS_LEGAL_ENTITY"
MISMATCH_BRAND_ONLY_PARTY = "BRAND_ONLY_PARTY"
MISMATCH_GROUP_NAME_AS_PARTY = "GROUP_NAME_AS_PARTY"
MISMATCH_PREAMBLE_SIGNATURE = "PREAMBLE_SIGNATURE_MISMATCH"
MISMATCH_NON_PARTY_AFFILIATE = "NON_PARTY_AFFILIATE_AS_PARTY"

_CORP = r"(?:주식회사|㈜|\(\s*주\s*\)|유한회사|유한책임회사|합자회사|사단법인|재단법인)"
_NAME = r"[가-힣A-Za-z0-9&][가-힣A-Za-z0-9&·.\-]*"
_RX_ORG_KO_PREFIX = re.compile(rf"{_CORP}\s*{_NAME}")
#: "베리띵즈 주식회사" — 이름이 두 글자 이상이어야 한다("와 주식회사"를 이름으로 읽지 않게).
_RX_ORG_KO_SUFFIX = re.compile(rf"(?<![가-힣A-Za-z0-9])[가-힣A-Za-z0-9&][가-힣A-Za-z0-9&·.\-]+\s*{_CORP}")
_RX_ORG_EN = re.compile(
    r"\b[A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*)*,?\s+"
    r"(?:Inc\.?|Co\.,?\s*Ltd\.?|Ltd\.?|LLC|GmbH|Corporation|Corp\.?|Limited)"
)
_RX_ALIAS = re.compile(r"이하\s*[“\"'‘]\s*([^”\"'’]{1,20}?)\s*[”\"'’]")
_RX_PLACEHOLDER = re.compile(r"_{3,}|○{2,}|\[\s*\]")
#: 당사자란의 부가 정보 줄 — 이름 줄로 읽지 않는다.
_RX_META_LINE = re.compile(r"^\s*(?:대표|주소|연락처|사업자|전화|담당|참여|회사명|성명|\(인\)|이하)")


@dataclass
class PartyRecord:
    label: str = ""
    written_name: str = ""
    legal_entity_name: str = ""
    brand_name: str = ""
    role_in_contract: str = ""
    signing_entity: str = ""
    affiliated: bool = False
    is_our_company: bool = False
    entity_key: str = ""
    #: 같은 법인을 다른 약칭으로 한 번 더 정의한 경우 먼저 정의된 약칭 — "[시디즈](이하 “갑”) …
    #: “갑”의 광고주 [시디즈](이하 “광고주”)" 의 광고주는 갑의 별칭이지 세 번째 당사자가 아니다.
    alias_of: str = ""
    #: 이름을 어디서 읽었나 — "inline"(같은 문장의 "(이하" 앞) | "table"(위 줄) | "".
    name_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "written_name": self.written_name,
            "legal_entity_name": self.legal_entity_name,
            "brand_name": self.brand_name,
            "role_in_contract": self.role_in_contract,
            "signing_entity": self.signing_entity,
            "affiliated_entity": self.affiliated,
            "is_our_company": self.is_our_company,
            "alias_of": self.alias_of,
        }


@dataclass
class EntityMismatch:
    code: str
    location: str
    written: str
    correct: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code, "location": self.location, "written": self.written,
            "correct": self.correct, "detail": self.detail,
        }


@dataclass
class EntityResolution:
    parties: list[PartyRecord] = field(default_factory=list)
    mismatches: list[EntityMismatch] = field(default_factory=list)
    user_brands: tuple[BrandFact, ...] = ()
    #: 계약서가 약칭으로 정의한 브랜드 — 본문의 "알로소"는 정의어라 그대로 둔다.
    defined_brand_aliases: tuple[str, ...] = ()
    #: 이 계약에 실제로 나오는 브랜드 — 서술 정규화는 이 브랜드만 다룬다.
    present_brands: tuple[str, ...] = ()
    #: 서명란에서 확인된 당사자 약칭(서두 약칭 기준) — 당사자 수 확정의 근거.
    signature_labels: tuple[str, ...] = ()
    #: 서명 문구의 계약서 부수("계약서 2통을 작성 … 각 1통씩 보관") — 0 이면 못 읽음.
    copies: int = 0

    @property
    def legal_parties(self) -> list[PartyRecord]:
        """법적 계약당사자 — 서두·정의 약칭과 서명란을 대조해 확정한다(2026-10-07 지시 2항).

        같은 법인의 별칭(alias_of)은 세지 않는다. 서명란에서 둘 이상이 확인되고, 서명하지 않는 서두
        약칭이 자기 이름조차 없으며, 계약서 부수가 서명 당사자 수를 넘지 않으면 그 약칭은 당사자가
        아니다(관계기관·연구책임자 등). 서명란을 못 읽으면 서두를 따른다 — 빈칸 서명란이 흔하다.
        """
        primary: list[PartyRecord] = []
        for p in self.parties:
            if not p.label or p.alias_of or any(q.label == p.label for q in primary):
                continue
            # 표 형식에서 위 줄 이름을 빌려 온 약칭이 앞 당사자와 같은 법인이고 서명란에도 없으면
            # 그 당사자의 다른 이름이다("본건 업무" ← 을사 줄).
            if (p.name_source == "table" and p.label not in self.signature_labels and p.legal_entity_name
                    and any(_norm(q.legal_entity_name) == _norm(p.legal_entity_name) for q in primary)):
                continue
            primary.append(p)
        if self.copies and len(primary) > self.copies:
            # "계약서 2통" 인데 서두 약칭이 셋 — 이름 없는 약칭("본건 업무")은 당사자가 아니다.
            named = [p for p in primary if p.written_name]
            if len(named) >= 2:
                primary = named
        signed = [p for p in primary if p.label in self.signature_labels]
        if len(signed) < 2 or (self.copies and self.copies > len(signed)):
            return primary
        return [p for p in primary if p in signed or p.written_name]

    @property
    def legal_party_count(self) -> int:
        return len(self.legal_parties)

    @property
    def status(self) -> str:
        return STATUS_LEGAL_ENTITY_MISMATCH if self.mismatches else ""

    @property
    def our_company(self) -> PartyRecord | None:
        for p in self.parties:
            if p.is_our_company:
                return p
        return None

    def brand_map(self) -> dict[str, str]:
        """브랜드 → 법인명. 담당자 사실이 registry 보다 우선한다."""
        out: dict[str, str] = {}
        for f in registry_brand_facts():
            if not f.english:
                out[f.brand] = f.legal_name_ko
        for f in self.user_brands:
            out[f.brand] = f.legal_name_ko
        if self.present_brands:
            out = {b: v for b, v in out.items() if b in self.present_brands}
        return out

    def our_company_display(self) -> str:
        p = self.our_company
        if p is None:
            return ""
        return f"{p.legal_entity_name} (브랜드: {p.brand_name})" if p.brand_name else p.legal_entity_name

    def to_dict(self) -> dict[str, Any]:
        our = self.our_company
        return {
            "status": self.status,
            "parties": [p.to_dict() for p in self.parties],
            "our_company": (
                {"legal_entity_name": our.legal_entity_name, "brand_name": our.brand_name}
                if our else None
            ),
            "our_company_display": self.our_company_display(),
            "mismatches": [m.to_dict() for m in self.mismatches],
            "user_brand_facts": [
                {"brand": f.brand, "legal_entity_name": f.legal_name_ko} for f in self.user_brands
            ],
            "defined_brand_aliases": list(self.defined_brand_aliases),
            "legal_party_count": self.legal_party_count,
            "legal_party_labels": [p.label for p in self.legal_parties],
            "signature_labels": list(self.signature_labels),
            "copies": self.copies,
        }


# ── 담당자 사실관계 ─────────────────────────────────────────────────────────

_RX_USER_BRAND = re.compile(
    r"(?P<brand>[가-힣A-Za-z0-9]{2,20})(?:\s*\(\s*[A-Za-z0-9 ]{2,20}\s*\))?\s*(?:은|는|이|가)\s*"
    r"(?P<corp1>주식회사\s*|㈜\s*|\(주\)\s*)?(?P<owner>[가-힣A-Za-z0-9]{2,20})"
    r"(?P<corp2>\s*주식회사)?\s*의\s*브랜드"
)


def parse_user_brand_facts(*sources: Any) -> tuple[BrandFact, ...]:
    """담당자가 적어 보낸 문장에서 "X는 (주식회사) Y의 브랜드" 를 읽는다.

    Y 가 계열사 registry 에 있으면 그 법인명을 쓰고, 아니면 담당자가 적은
    법인격 표기를 살려 "주식회사 Y" 로 만든다(법인격 표기가 없으면 Y 그대로).
    """
    facts: dict[str, BrandFact] = {}
    for src in sources:
        if isinstance(src, dict):
            texts = [str(v) for v in src.values() if isinstance(v, (str, int, float))]
        else:
            texts = [str(src or "")]
        for t in texts:
            for m in _RX_USER_BRAND.finditer(t):
                brand, owner = m.group("brand"), m.group("owner")
                if brand == owner:
                    continue
                known = resolve_entity(owner)
                if known is not None and known.legal_name_ko:
                    legal_ko, legal_en, key = known.legal_name_ko, known.legal_name_en, known.key
                else:
                    corp = m.group("corp1") or m.group("corp2")
                    legal_ko = f"주식회사 {owner}" if corp else owner
                    legal_en, key = "", None
                facts[brand] = BrandFact(brand, legal_ko, legal_en, key, source="user")
    return tuple(facts.values())


# ── 당사자 추출 ─────────────────────────────────────────────────────────────

def _split_regions(text: str) -> tuple[str, str, int]:
    """(서두, 서명란, 서명란 시작 위치). 못 찾으면 빈 문자열·-1.

    경계는 정정 finding 과 같은 `split_party_regions` 로 정한다 — 둘이 서명란을
    다르게 자르면 불일치 표시와 정정 문안이 서로 다른 줄을 가리킨다.
    """
    body_start, sig_start = split_party_regions(text)
    preamble = text[:body_start]
    if sig_start >= len(text):
        return preamble, "", -1
    return preamble, text[sig_start:], sig_start


#: 법인격 표기 없이 한 줄로 적혀도 이름으로 읽는 표기 — registry 에 있는
#: 이름·브랜드·그룹명과 **정확히** 같을 때만. 부분일치로 읽으면 "제19조
#: (알로소 제공자료…)" 같은 조문 제목이 서명 당사자로 잡혔다.
_EXACT_NAMES: frozenset[str] = frozenset(
    {_norm(n) for e in GROUP_ENTITIES for n in e.all_names()} | {_norm("퍼시스그룹")}
)


def _org_names(line: str) -> list[str]:
    names = [m.group(0).strip() for m in _RX_ORG_KO_PREFIX.finditer(line)]
    if not names:
        names = [m.group(0).strip() for m in _RX_ORG_KO_SUFFIX.finditer(line)]
    names += [m.group(0).strip() for m in _RX_ORG_EN.finditer(line)]
    if not names:
        stripped = line.strip()
        # 법인격 표기 없이 계열사명·브랜드·그룹명만 한 줄로 적힌 당사자란.
        if stripped and _norm(stripped) in _EXACT_NAMES:
            names.append(stripped)
    return names


#: 양식의 대괄호 빈칸에 적힌 이름 — "[시디즈] (이하 “갑”)".
_RX_BRACKET_NAME = re.compile(r"\[\s*([^\[\]]{1,30}?)\s*\]\s*$")
#: 당사자를 가리키는 약칭. 이름 없이 "콘텐츠"·"본 계약"·"서비스" 를 정의한 것은 당사자가 아니다.
_RX_PARTY_LABEL = re.compile(r"^(?:[갑을병정]|회사|고객|당사)$|(?:사|자|인|주|처|원|단|청)$")


def _extract_preamble_parties(preamble: str) -> list[PartyRecord]:
    lines = [ln.rstrip() for ln in preamble.splitlines()]
    parties: list[PartyRecord] = []
    for i, line in enumerate(lines):
        prev_end = 0
        for am in _RX_ALIAS.finditer(line):
            label = am.group(1).strip()
            # 인라인: "(이하" 앞의 이름 — **앞 약칭 뒤부터**만 본다. 줄 전체를 보면
            # "㈜비디앤에스(이하 “을”)는 “갑”의 광고주 [시디즈] (이하 “광고주”)" 의 광고주가
            # ㈜비디앤에스가 됐다(2026-10-07 브랜디드 콘텐츠 계약 실측).
            before = line[prev_end: am.start()]
            prev_end = am.end()
            names = _org_names(before)
            if not names:
                bm = _RX_BRACKET_NAME.search(before.rstrip(" ("))
                if bm and _norm(bm.group(1)) in _EXACT_NAMES:
                    names = [bm.group(1).strip()]
            written = names[-1] if names else ""
            role = ""
            if not written:
                # 표 형식: 위로 올라가며 이름 줄과 그 위의 역할 줄을 찾는다.
                for j in range(i - 1, max(-1, i - 6), -1):
                    cand = lines[j].strip()
                    if not cand or _RX_META_LINE.match(cand) or _RX_PLACEHOLDER.search(cand):
                        continue
                    if _RX_ALIAS.search(cand):
                        break
                    found = _org_names(cand)
                    if found:
                        written = found[-1]
                        for k in range(j - 1, max(-1, j - 3), -1):
                            r = lines[k].strip()
                            if r and not _RX_META_LINE.match(r) and not _org_names(r) \
                                    and not _RX_ALIAS.search(r) and len(r) <= 40:
                                role = r
                                break
                        break
            # 문장 안에서 이름 없이 정의된 약칭("…콘텐츠(이하 “콘텐츠”)", "계약(이하 “본 계약”)")은 당사자가 아니다.
            # 표 형식(약칭만 한 줄)은 이름 칸이 빈칸이어도 당사자 자리이므로 그대로 둔다.
            if not written and before.strip() and not _RX_PARTY_LABEL.search(label):
                continue
            parties.append(PartyRecord(label=label, written_name=written, role_in_contract=role,
                                       name_source=("inline" if names else ("table" if written else ""))))
    return parties


_RX_COPIES = re.compile(r"계약서\s*(\d+|[일이삼사오두세네])\s*(?:부|통)")
_KO_NUM = {"일": 1, "이": 2, "두": 2, "삼": 3, "세": 3, "사": 4, "네": 4, "오": 5}


def _signature_labels(signature: str, labels: list[str]) -> tuple[str, ...]:
    """서명란에 약칭이 단독(또는 "약칭:"·"(약칭)") 으로 적힌 당사자 — “갑” / 갑 : / (을)."""
    out: list[str] = []
    for lb in labels:
        q = r"[“\"'‘]?\s*" + re.escape(lb) + r"\s*[”\"'’]?"
        if (re.search(rf"(?m)^\s*(?:\(\s*)?{q}(?:\s*\))?\s*(?:[:：]|$)", signature)
                or re.search(rf"(?m)^\s*\(\s*{re.escape(lb)}\s*\)", signature)
                or re.search(rf"(?m)^\s*{q}\s*[:：]?\s*(?:회\s*사\s*명|상\s*호|주식회사|㈜|\(주\))", signature)):
            out.append(lb)
    return tuple(out)


def _extract_signature_names(signature: str) -> list[str]:
    names: list[str] = []
    for line in signature.splitlines():
        s = line.strip()
        if not s or _RX_PLACEHOLDER.fullmatch(s):
            continue
        # "갑: 주식회사 X 대표이사 (인)" 형식도 이름 부분만 본다.
        s = re.sub(r"^\s*[갑을병정][\s:：]+", "", s)
        for n in _org_names(s):
            if n not in names:
                names.append(n)
    return names


# ── 해석 ──────────────────────────────────────────────────────────────────

def _brand_owner(name: str, facts: tuple[BrandFact, ...]) -> BrandFact | None:
    core = re.sub(_CORP, "", name).strip()
    for f in facts:
        if not f.english and core == f.brand:
            return f
        if f.english and core.lower().startswith(f.brand.lower()):
            return f
    return None


def _resolve_name(
    written: str, facts: tuple[BrandFact, ...], entity: str | None,
) -> tuple[str, str, GroupEntity | None, str]:
    """(법인명, 브랜드, 계열사, 불일치 코드). 불일치가 없으면 코드는 빈 문자열."""
    if not written:
        return "", "", None, ""
    hits = find_name_hits(written, entity=entity, user_brands=facts)
    brand_fact = _brand_owner(written, facts)
    if brand_fact is not None:
        owner = resolve_entity(brand_fact.legal_name_ko) if brand_fact.entity_key else None
        has_corp = bool(re.search(_CORP, written)) or bool(
            re.search(r"(?i)\b(?:Inc|Ltd|Co|Corp)\b", written))
        code = MISMATCH_BRAND_AS_LEGAL_ENTITY if has_corp else MISMATCH_BRAND_ONLY_PARTY
        return brand_fact.legal_name_ko, brand_fact.brand, owner, code
    if any(h.rule.kind == KIND_GROUP for h in hits):
        return hits[0].correct, "", resolve_entity(hits[0].correct), MISMATCH_GROUP_NAME_AS_PARTY
    known = resolve_entity(written)
    if known is not None:
        return (known.legal_name_ko or written), "", known, ""
    return written, "", None, ""


def _core(name: str) -> str:
    """법인격 표기·공백·괄호를 뗀 이름 — "㈜ 한빛" 과 "주식회사 한빛" 은 같은 이름이다."""
    return re.sub(r"[\s「」『』\"'“”‘’]", "", re.sub(_CORP, "", str(name or ""))).lower()


def _same_entity(a: PartyRecord, legal: str, key: str) -> bool:
    if key and a.entity_key and key == a.entity_key:
        return True
    if legal and _norm(a.legal_entity_name) == _norm(legal):
        return True
    return bool(legal) and bool(a.legal_entity_name) and _core(a.legal_entity_name) == _core(legal)


_OBLIGATION = r"(?:한다|하여야|해야|부담|지급|책임|보증|배상|진다)"


def resolve_entities(
    text: str | None,
    *,
    entity: str | None = None,
    review_focus: str | None = None,
    answers: dict[str, Any] | None = None,
) -> EntityResolution:
    body = str(text or "")
    user = parse_user_brand_facts(review_focus or "", answers or {})
    user_names = {f.brand for f in user}
    facts = user + tuple(f for f in registry_brand_facts() if f.brand not in user_names)
    res = EntityResolution(
        user_brands=user,
        present_brands=tuple(f.brand for f in facts if not f.english and f.brand in body)
        or ("(none)",),
    )

    preamble, signature, sig_start = _split_regions(body)
    parties = _extract_preamble_parties(preamble)
    sig_names = _extract_signature_names(signature)

    aliases: list[str] = []
    for p in parties:
        legal, brand, known, code = _resolve_name(p.written_name, facts, entity)
        p.legal_entity_name, p.brand_name = legal, brand
        p.affiliated = known is not None
        p.entity_key = known.key if known is not None else ""
        if brand and p.label == brand:
            aliases.append(brand)
        if code:
            res.mismatches.append(EntityMismatch(
                code, "서두(당사자 표시)", p.written_name, legal,
                _mismatch_detail(code, p.written_name, legal, brand),
            ))
    res.defined_brand_aliases = tuple(aliases)

    # 서명란 — 서두의 당사자와 짝을 짓고, 틀린 표기·짝 없는 이름을 잡는다.
    sig_hit_labels: list[str] = []
    for name in sig_names:
        legal, brand, known, code = _resolve_name(name, facts, entity)
        key = known.key if known is not None else ""
        match = next((p for p in parties if _same_entity(p, legal, key)), None)
        if code:
            res.mismatches.append(EntityMismatch(
                code, "서명란", name, legal, _mismatch_detail(code, name, legal, brand),
            ))
        if match is None:
            # 서두가 법인격 표기 없이 적은 당사자("한빛로보틱스(이하 “도급인”)")는
            # 이름을 못 뽑는다 — 서명란 이름의 핵심이 서두에 있으면 그 당사자다.
            core = _core(name)
            unnamed = [p for p in parties if not p.written_name]
            if core and core in _core(preamble):
                if len(unnamed) == 1:
                    match = unnamed[0]
                    match.written_name = match.written_name or name
                    match.legal_entity_name = match.legal_entity_name or legal
                    match.affiliated = match.affiliated or known is not None
                    match.entity_key = match.entity_key or key
                else:
                    continue  # 서두에 있는 이름이다 — 누구인지 모를 뿐 불일치는 아니다.
        if match is not None:
            sig_hit_labels.append(match.alias_of or match.label)
            match.signing_entity = legal
            if (not code and match.written_name
                    and _core(name) != _core(match.written_name)
                    and _norm(name) != _norm(match.written_name)):
                res.mismatches.append(EntityMismatch(
                    MISMATCH_PREAMBLE_SIGNATURE, "서두↔서명란", f"{match.written_name} / {name}",
                    legal, f"서두에는 '{match.written_name}', 서명란에는 '{name}'로 적혀 있습니다. "
                           f"같은 법인이라면 두 곳을 '{legal}'로 통일하십시오.",
                ))
        elif parties:
            res.mismatches.append(EntityMismatch(
                MISMATCH_PREAMBLE_SIGNATURE, "서명란", name, "",
                f"서명란의 '{name}'{_iga(name)} 서두의 당사자 중 누구인지 확인되지 않습니다. "
                "서명 법인이 서두의 당사자와 같은 법인인지 확인하십시오.",
            ))

    # 같은 법인을 다시 부르는 약칭은 별칭이다 — 당사자 수에 넣지 않는다.
    for i, p in enumerate(parties):
        # 표 형식에서 위 줄을 거슬러 읽은 이름은 옆 칸 당사자의 이름일 수 있다(서울대 연구계약 "학교").
        if not p.label or p.name_source != "inline" or not (p.legal_entity_name or p.entity_key):
            continue
        # 해석 결과(registry)만 같다고 별칭으로 보지 않는다 — 서두에 **같은 이름**을 두 번 적은 경우만.
        # "㈜일룸(갑) / 퍼시스데스커드림센터(을)" 은 registry 가 둘 다 일룸으로 읽어도 다른 당사자다.
        first = next((q for q in parties[:i] if q.label and not q.alias_of and q.name_source == "inline"
                      and q.written_name and _core(q.written_name) == _core(p.written_name)
                      and _same_entity(q, p.legal_entity_name, p.entity_key)), None)
        if first is not None:
            p.alias_of = first.label
    res.signature_labels = _signature_labels(signature, [p.label for p in parties if p.label]) + tuple(
        lb for lb in sig_hit_labels if lb)
    res.signature_labels = tuple(dict.fromkeys(res.signature_labels))
    copies = _RX_COPIES.search(signature + " " + body[-1500:])
    if copies:
        n = copies.group(1)
        res.copies = int(n) if n.isdigit() else _KO_NUM.get(n, 0)

    # 서명란에 이름이 없는 당사자는 서두의 해석을 서명 법인으로 둔다
    # (빈칸 서명란은 불일치가 아니다).
    for p in parties:
        if not p.signing_entity and p.legal_entity_name and not _RX_PLACEHOLDER.search(p.written_name):
            p.signing_entity = p.legal_entity_name

    # 우리 회사 — 계열사 당사자 중 검토 요청 법인과 같은 쪽, 없으면 첫 계열사.
    named = resolve_entity(entity)
    ours = [p for p in parties if p.affiliated]
    pick = next((p for p in ours if named is not None and p.entity_key == named.key), None)
    pick = pick or (ours[0] if ours else None)
    if pick is not None:
        pick = next((q for q in parties if q.label == pick.alias_of), pick) if pick.alias_of else pick
        pick.is_our_company = True
    res.parties = parties

    # 본문에서 당사자가 아닌 계열사를 당사자처럼 쓰는 경우.
    party_keys = {p.entity_key for p in parties if p.entity_key}
    if party_keys:
        body_part = body[len(preamble): sig_start if sig_start >= 0 else len(body)]
        for e in GROUP_ENTITIES:
            if e.key in party_keys:
                continue
            for nm in (e.name,) + tuple(a for a in e.aliases if re.search("[가-힣]", a)):
                rx = re.compile(
                    rf"(?<![가-힣A-Za-z0-9]){re.escape(nm)}(?:은|는|이|가)\s[^.。\n]{{0,60}}{_OBLIGATION}"
                )
                m = rx.search(body_part)
                if m:
                    res.mismatches.append(EntityMismatch(
                        MISMATCH_NON_PARTY_AFFILIATE, "본문", m.group(0)[:60], "",
                        f"'{nm}'{_eunneun(nm)} 이 계약의 당사자가 아닌데 본문에서 의무의 주체로 쓰였습니다: "
                        f"“{m.group(0)[:60]}”. 실제 의무를 지는 당사자 법인으로 고치거나, "
                        "그 계열사를 당사자로 추가하십시오.",
                    ))
                    break
    return res


def _batchim(word: str) -> bool:
    last = str(word or "").rstrip()[-1:]
    return "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0


def _iga(word: str) -> str:
    return "이" if _batchim(word) else "가"


def _eunneun(word: str) -> str:
    return "은" if _batchim(word) else "는"


def _mismatch_detail(code: str, written: str, legal: str, brand: str) -> str:
    if code == MISMATCH_BRAND_AS_LEGAL_ENTITY:
        return (f"'{written}'{_eunneun(written)} 존재하지 않는 법인명입니다. {brand}{_eunneun(brand)} {legal}의 브랜드이므로 "
                f"법적 당사자는 {legal}입니다.")
    if code == MISMATCH_BRAND_ONLY_PARTY:
        return (f"당사자 자리에 브랜드 '{written}'만 적혀 있습니다. 법적 당사자는 {legal}입니다 — "
                f"'{legal}(브랜드명: {brand})'로 적으십시오.")
    if code == MISMATCH_GROUP_NAME_AS_PARTY:
        return (f"'{written}'{_eunneun(written)} 법적 엔터티가 아니어서 당사자가 될 수 없습니다. "
                f"실제 계약 주체 법인({legal})으로 적으십시오.")
    return ""


# ── 서술 정규화 ─────────────────────────────────────────────────────────────

_RX_BRAND_FACT_AFTER = re.compile(r"(?:은|는|이|가)\s*[^.。\n]{0,30}?의\s*브랜드")
_RX_QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"|‘[^’]*’|「[^」]*」")


def collapse_dual_party(text: str | None, res: EntityResolution) -> str:
    """브랜드와 그 법인을 두 당사자처럼 나란히 쓴 표현을 하나로 합친다
    (2026-09-30 지시 13항) — "시디즈 및 알로소의 동의" → "주식회사 시디즈(알로소)의 동의",
    "알로소 법인" → "주식회사 시디즈(알로소)".
    """
    s = str(text or "")
    if not s:
        return s
    particle = r"(?P<p>에게|의|에|도|만|은|는|이|가|을|를|과|와)?(?![가-힣A-Za-z])"
    for brand, legal in res.brand_map().items():
        core = re.sub(r"주식회사|㈜|\(주\)", "", legal).strip()
        names = "|".join(re.escape(x) for x in dict.fromkeys((legal, core)) if x)
        b = re.escape(brand)
        joiner = r"\s*(?:및|와|과|,|·|또는|그리고)\s*"
        merged = f"{legal}({brand})"

        def _sub(m: re.Match[str], merged: str = merged, legal: str = legal) -> str:
            p = m.group("p") or ""
            if p in ("은", "는", "이", "가", "을", "를", "과", "와"):
                pairs = {"은": ("은", "는"), "는": ("은", "는"), "이": ("이", "가"), "가": ("이", "가"),
                         "을": ("을", "를"), "를": ("을", "를"), "과": ("과", "와"), "와": ("과", "와")}
                p = pairs[p][0] if _batchim(legal) else pairs[p][1]
            return merged + p

        s = re.sub(rf"(?:{names})(?:\s*\(\s*{b}\s*\))?{joiner}{b}{particle}", _sub, s)
        s = re.sub(rf"(?<![가-힣A-Za-z]){b}{joiner}(?:{names})(?:\s*\(\s*{b}\s*\))?{particle}", _sub, s)
        s = re.sub(rf"(?<![가-힣A-Za-z]){b}\s*법인{particle}", _sub, s)
    return s


def normalize_party_narrative(text: str | None, res: EntityResolution) -> str:
    """검토의견·협상포지션 같은 서술 문장에서 브랜드를 권리·의무 주체로 쓰면
    법인명을 앞세운다 — "알로소가 손해배상 책임을 부담한다" →
    "주식회사 시디즈(알로소)가 손해배상 책임을 부담한다" (지시 7항).

    인용부호 안(계약 원문 인용)은 건드리지 않는다 — 인용을 바꾸면 원문과
    어긋나 인용 검증 게이트가 가짜 인용으로 본다.
    """
    s = str(text or "")
    if not s:
        return s
    brand_map = res.brand_map()
    if not brand_map:
        return s
    protected = [(m.start(), m.end()) for m in _RX_QUOTED.finditer(s)]

    def _inside(i: int) -> bool:
        return any(a <= i < b for a, b in protected)

    out: list[str] = []
    pos = 0
    pattern = re.compile(
        r"(?<![가-힣A-Za-z0-9(:])(" + "|".join(re.escape(b) for b in sorted(brand_map, key=len, reverse=True))
        + r")(?=(?:은|는|이|가|에게|의|와|과|을|를)(?![가-힣]))"
    )
    for m in pattern.finditer(s):
        if _inside(m.start()):
            continue
        if _RX_BRAND_FACT_AFTER.match(s, m.end()):
            continue  # "알로소는 주식회사 시디즈의 브랜드" — 브랜드 사실을 말하는 문장
        legal = brand_map[m.group(1)]
        before = s[max(0, m.start() - len(legal) - 2): m.start()]
        if legal in before:
            continue  # 이미 "주식회사 시디즈(알로소" 처럼 법인명이 앞에 있다.
        out.append(s[pos:m.start()])
        out.append(f"{legal}({m.group(1)})")
        pos = m.end()
        # 조사는 괄호 앞 법인명의 받침을 따른다 — "주식회사 일룸(데스커)은".
        nxt = s[pos:pos + 2]
        for with_b, without_b in (("은", "는"), ("이", "가"), ("을", "를"), ("과", "와")):
            if nxt.startswith(with_b) or nxt.startswith(without_b):
                last = legal[-1]
                batchim = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
                out.append(with_b if batchim else without_b)
                pos += 1
                break
    out.append(s[pos:])
    return "".join(out)


#: 서술 정규화를 적용할 finding 필드 — 계약 원문(original_text)·인용(quote)은 제외.
NARRATIVE_FIELDS: tuple[str, ...] = (
    "problem", "rewrite_reason", "legal_business_reason", "negotiation_position",
    "negotiation_strategy", "worst_case_scenario", "our_exposure", "why_matters",
    "risk_description", "practical_position_text",
)


def normalize_findings(clause_results: list[dict[str, Any]], res: EntityResolution) -> list[str]:
    """모든 finding 의 서술 필드와, 약칭 정의가 없는 수정문안에 법인명을 맞춘다."""
    touched: list[str] = []
    defined = set(res.defined_brand_aliases)
    for cr in clause_results or []:
        # 정정 finding 의 설명은 "알로소는 주식회사 시디즈의 브랜드"처럼 브랜드
        # 자체를 말한다 — 여기에 법인명을 앞세우면 "주식회사 시디즈(알로소)는
        # 주식회사 시디즈의 브랜드"가 된다.
        if not isinstance(cr, dict) or cr.get("is_entity_name_correction"):
            continue
        changed = False
        # 브랜드와 법인을 두 당사자로 나란히 쓴 표현은 서술·수정문 어디서든 틀리다.
        for key in NARRATIVE_FIELDS + ("suggested_rewrite", "recommendation_text"):
            v = cr.get(key)
            if isinstance(v, str) and v:
                nv = collapse_dual_party(v, res)
                if nv != v:
                    cr[key] = nv
                    changed = True
        for key in NARRATIVE_FIELDS:
            v = cr.get(key)
            if isinstance(v, str) and v:
                nv = normalize_party_narrative(v, res)
                if nv != v:
                    cr[key] = nv
                    changed = True
        # 수정문안은 계약 문언이다. 계약이 브랜드를 약칭으로 정의했으면 본문의
        # "알로소"는 정의어라 그대로 두고, 정의가 없을 때만 법인명을 앞세운다.
        if not cr.get("is_entity_name_correction"):
            for key in ("suggested_rewrite", "recommendation_text"):
                v = cr.get(key)
                if isinstance(v, str) and v:
                    nv = v
                    if not defined:
                        nv = normalize_party_narrative(v, res)
                    if nv != v:
                        cr[key] = nv
                        changed = True
        if changed:
            touched.append(str(cr.get("clause_id") or ""))
    return touched


__all__ = [
    "KIND_BRAND",
    "EntityResolution",
    "PartyRecord",
    "STATUS_LEGAL_ENTITY_MISMATCH",
    "normalize_findings",
    "normalize_party_narrative",
    "parse_user_brand_facts",
    "resolve_entities",
]
