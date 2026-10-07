"""계약별 상태 격리 · 당사자/역할 단일 지도 · 조항 출처(provenance) · 정합성 hard gate (2026-10-07 지시).

실측(시디즈 ↔ ㈜비디앤에스 브랜디드 콘텐츠 제작 계약 — 서명 당사자 2):
    · 서두가 같은 시디즈를 “갑” 과 “광고주” 로 두 번 정의 → 약칭 3개를 당사자 3으로 세어
      "3자 브랜디드 콘텐츠 제작계약" 이 계약 성격에 찍혔다. 직전에 검토한 한글날 3자 협업계약과
      겹쳐 사용자에게는 이전 계약의 흔적(cross-case contamination)으로 보였다.
    · 우리가 새로 제안한 제14조 ⑤~⑦ 이 "관련 계약조항" 목록에 원문 조항처럼 섞였다.
    · AI 가 "광고주(을)" 처럼 당사자 약칭과 역할을 뒤바꿔 쓸 수 있다.
    · 하도급법이 비적용으로 확정된 뒤에도 "적용 가능성 낮음 [LOW]" 표와 Legal Map 의 적용 법률
      목록에 남았다.

같은 프로세스에서 다른 계약을 먼저 검토한 뒤에도 결과가 같다는 것은 회귀테스트로 고정했다
(test_contract_isolation.py). 여기서는 그 결과가 **현재 문서만으로** 설명되는지를 출력 직전에 본다:

    1. ContractReviewState — 매 검토마다 새로 만든다(RESET_PREVIOUS_CONTRACT_STATE). 당사자 이름·
       조항·사용자 지정 쟁점이 현재 문서에 근거하는지 확인한다(근거 없는 값 = 다른 계약에서 온 값).
    2. PartyMap — 법적 당사자(서두·서명란 대조), 약칭별 역할, 비당사자 이해관계자. 모든 섹션이
       이 지도 하나를 쓴다.
    3. Clause provenance — 모든 조항 참조에 ORIGINAL_CONTRACT / PROPOSED_REDLINE / USER_REQUEST.
       원문에 없는 조항은 "기존 관련조항" 목록에 남지 못하고 "신설 제안" 으로 옮긴다.
    4. 출력 직전 정합성 — 당사자 수·역할 표기·계약유형·적용 법률·조항 참조가 모든 섹션에서 같은지.
       고칠 수 있는 것은 고치고 기록한다(제거·기록 후 전달). 고친 뒤에도 남으면 상태 코드를 세운다.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

RESET_PREVIOUS_CONTRACT_STATE = True

STATUS_PARTY_COUNT = "REVIEW_FAILED_PARTY_COUNT_CONTAMINATION"
STATUS_PARTY_ROLE = "REVIEW_FAILED_PARTY_ROLE_MISMATCH"
STATUS_PROVENANCE = "REVIEW_FAILED_CLAUSE_PROVENANCE"
STATUS_STATE_CONFLICT = "REVIEW_FAILED_CANONICAL_STATE_CONFLICT"

SOURCE_ORIGINAL = "ORIGINAL_CONTRACT"
SOURCE_PROPOSED = "PROPOSED_REDLINE"
SOURCE_USER = "USER_REQUEST"

#: 원문 문언을 담는 필드 — 계약서 자체이므로 출력 문장 정규화 대상이 아니다.
_ORIGINAL_TEXT_KEYS = frozenset({
    "original_text", "clause_text", "context_text", "text", "exact_text", "evidence", "quoted_text",
    "unchanged_segment", "original_user_text", "raw_citation", "source_text", "clause_title",
})


# ── 1. 당사자 지도 ───────────────────────────────────────────────────────────

#: 계약유형 → (우리 역할, 상대방 역할) 짧은 이름. 약칭이 역할 명사로 정의돼 있으면 그쪽이 우선한다.
_ROLE_PAIRS: dict[str, tuple[str, str]] = {
    "advertising_content_production": ("광고주", "제작사"),
    "content_production_service": ("발주자", "제작사"),
    "creative_agency_service": ("광고주", "대행사"),
    "advertising_media_placement": ("광고주", "매체사"),
}
_ROLE_CODES: dict[str, str] = {
    "client": "발주자", "service_provider": "수행사", "supplier": "공급자", "buyer": "구매자",
    "seller_or_supplier": "공급자", "contractor": "수급인", "ordering_party": "도급인",
    "principal": "위탁자", "dealer": "대리점", "licensor": "라이선서", "licensee": "라이선시",
}
#: 갑·을류 자리 약칭 — 역할 명사가 아니다.
_POSITION_LABEL = re.compile(r"^(?:[갑을병정](?:사)?|당사|회사|본인)$")
#: 서명하지 않는데 본문에 자주 나오는 사람·기관 — 당사자 수에 넣지 않는다.
_STAKEHOLDER_NOUNS = ("크리에이터", "인플루언서", "출연자", "모델", "협찬사", "관계기관", "주관기관", "주최기관",
                      "아티스트", "연구책임자", "계열사")


@dataclass
class PartyEntry:
    label: str
    legal_entity: str
    role: str = ""
    is_our_company: bool = False
    aliases: list[str] = field(default_factory=list)
    #: 계약서에 적힌 이름 — 현재 문서 근거 확인용(브랜드로 적힌 당사자는 법인명이 본문에 없을 수 있다).
    written_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "legal_entity": self.legal_entity, "role": self.role,
                "is_our_company": self.is_our_company, "aliases": list(self.aliases)}


@dataclass
class PartyMap:
    parties: list[PartyEntry] = field(default_factory=list)
    non_party_stakeholders: list[dict[str, str]] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.parties)

    def owner_of(self, word: str) -> PartyEntry | None:
        """약칭·별칭·역할·법인명 → 당사자."""
        w = _strip_quotes(word)
        for p in self.parties:
            if w and (w == p.label or w in p.aliases or w == p.role):
                return p
        core = _core(w)
        for p in self.parties:
            if core and len(core) >= 2 and core == _core(p.legal_entity):
                return p
        return None

    def to_dict(self) -> dict[str, Any]:
        return {"party_count": self.count, "parties": [p.to_dict() for p in self.parties],
                "non_party_stakeholders": list(self.non_party_stakeholders)}


def _strip_quotes(s: str) -> str:
    return re.sub(r"[“”\"'‘’\s]", "", str(s or ""))


def _core(name: str) -> str:
    return re.sub(r"[\s“”\"'‘’()]|주식회사|㈜|\(주\)|재단법인|\(재\)", "", str(name or "")).lower()


def build_party_map(entity_resolution: Any, text: str, contract_type: str = "",
                    our_role_code: str = "", counterparty_role_code: str = "") -> PartyMap:
    legal = list(getattr(entity_resolution, "legal_parties", []) or [])
    all_parties = list(getattr(entity_resolution, "parties", []) or [])
    pair = _ROLE_PAIRS.get(str(contract_type or ""))
    out: list[PartyEntry] = []
    for p in legal:
        aliases = [q.label for q in all_parties if q.alias_of == p.label and q.label]
        role_alias = next((a for a in aliases if not _POSITION_LABEL.match(a)), "")
        if role_alias:
            role = role_alias
        elif pair:
            role = pair[0] if p.is_our_company else pair[1]
        else:
            code = our_role_code if p.is_our_company else counterparty_role_code
            role = _ROLE_CODES.get(str(code or ""), "")
        if not _POSITION_LABEL.match(p.label) and not role:
            role = p.label
        out.append(PartyEntry(label=p.label, legal_entity=p.legal_entity_name or p.written_name,
                              role=role, is_our_company=bool(p.is_our_company), aliases=aliases,
                              written_name=str(getattr(p, "written_name", "") or "")))
    # 우리 쪽만 역할 명사 약칭이 있고 상대방은 비었으면 유형 기본값으로 채운다.
    if pair:
        for e in out:
            if not e.role:
                e.role = pair[0] if e.is_our_company else pair[1]
    labels = {e.label for e in out} | {a for e in out for a in e.aliases}
    stakeholders: list[dict[str, str]] = []
    body = str(text or "")
    for noun in _STAKEHOLDER_NOUNS:
        if noun in labels or noun not in body:
            continue
        side = ""
        m = re.search(rf"[“\"]?([갑을병정])[”\"]?\s*(?:소속|측|의)\s*{noun}", body)
        if m:
            side = m.group(1)
        stakeholders.append({
            "name": noun, "side": side,
            "note": (f"“{side}” 측 관련자 — 서명 당사자가 아님" if side else "서명 당사자가 아님"),
        })
    return PartyMap(parties=out, non_party_stakeholders=stakeholders)


# ── 2. 계약별 상태 ───────────────────────────────────────────────────────────

@dataclass
class ContractReviewState:
    """한 번의 검토에만 속하는 상태. 다른 검토의 값을 넘겨받을 경로가 없다 — 매번 새로 만든다."""

    document_sha256: str
    contract_type: str
    contract_type_label: str
    party_count: int
    legal_entities: list[str]
    party_roles: dict[str, str]
    brand_entity_map: dict[str, str]
    governing_law: str
    user_focus: list[str]
    applicable_laws: dict[str, str]
    clause_map: list[str]
    risk_findings: list[str]
    reset_previous_contract_state: bool = RESET_PREVIOUS_CONTRACT_STATE
    ungrounded: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "RESET_PREVIOUS_CONTRACT_STATE": self.reset_previous_contract_state,
            "document_sha256": self.document_sha256,
            "contract_type": self.contract_type,
            "contract_type_label": self.contract_type_label,
            "party_count": self.party_count,
            "legal_entities": list(self.legal_entities),
            "party_roles": dict(self.party_roles),
            "brand_entity_map": dict(self.brand_entity_map),
            "governing_law": self.governing_law,
            "user_focus": list(self.user_focus),
            "applicable_laws": dict(self.applicable_laws),
            "clause_map": list(self.clause_map),
            "risk_findings": list(self.risk_findings),
            "ungrounded": list(self.ungrounded),
        }


def build_contract_state(
    *, text: str, meta: dict[str, Any], party_map: PartyMap, entity_resolution: Any,
    clause_index: Any, clause_results: list[dict[str, Any]], focus_paths: list[str],
) -> ContractReviewState:
    body = str(text or "")
    cs = meta.get("canonical_state") or {}
    juris = meta.get("jurisdiction") or {}
    laws = dict(((meta.get("applicable_law_state") or {}).get("statuses") or {}))
    arts = sorted((getattr(clause_index, "articles", {}) or {}).keys(), key=lambda k: (len(k), k))
    brand_map: dict[str, str] = {}
    try:
        brand_map = dict(entity_resolution.brand_map())
    except Exception:  # noqa: BLE001
        pass
    state = ContractReviewState(
        document_sha256=hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest(),
        contract_type=str(cs.get("contract_type") or ""),
        contract_type_label=str(cs.get("contract_type_label") or ""),
        party_count=party_map.count,
        legal_entities=[p.legal_entity for p in party_map.parties],
        party_roles={p.label: p.role for p in party_map.parties},
        brand_entity_map=brand_map,
        governing_law=str(juris.get("governing_law") or juris.get("kind") or ""),
        user_focus=list(focus_paths),
        applicable_laws=laws,
        clause_map=[f"제{a}조" for a in arts],
        risk_findings=[str(c.get("clause_id") or "") for c in clause_results if _live(c)],
    )
    # 현재 문서에 근거가 없는 값 = 다른 검토에서 넘어온 값이다.
    doc = _core(body)
    for p in party_map.parties:
        names = [c for c in (_core(p.legal_entity), _core(p.written_name)) if c]
        if names and not any(c in doc for c in names):
            state.ungrounded.append(f"당사자 '{p.legal_entity}' 가 계약서에 없음")
    # 지정 검토 조항이 문서에 없는 것은 오염이 아니다 — 요청이 초안 기준 번호일 수 있다(와이어드).
    return state


# ── 3. 조항 출처 ─────────────────────────────────────────────────────────────

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_RX_ART = re.compile(r"제\s*(\d+)\s*조(?:\s*의\s*(\d+))?")
_RX_PROPOSED_MARK = re.compile(r"같은\s*조\s*말미|신설|\(추가\)|추가\s*신설")


@dataclass
class ClauseRefParsed:
    article: str
    paragraphs: list[str]
    item: str = ""


def parse_path(path: str) -> ClauseRefParsed | None:
    s = str(path or "")
    m = _RX_ART.search(s)
    if not m:
        return None
    art = m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")
    rest = s[m.end():]
    paras: list[str] = []
    for c in rest:
        if c in _CIRCLED:
            paras.append(str(_CIRCLED.index(c) + 1))
    rng = re.search(r"제?\s*(\d+)\s*항?\s*[~∼\-]\s*제?\s*(\d+)\s*항", rest)
    if rng:
        a, b = int(rng.group(1)), int(rng.group(2))
        paras += [str(i) for i in range(a, b + 1)] if 0 < a <= b <= a + 20 else []
    dots = re.search(r"제\s*(\d+(?:\s*[·,ㆍ]\s*\d+)+)\s*항", rest)
    if dots:
        paras += re.findall(r"\d+", dots.group(1))
    paras += re.findall(r"제\s*(\d+)\s*항", rest)
    item = ""
    im = re.search(r"(\d+)\s*호", rest)
    if im:
        item = im.group(1)
    return ClauseRefParsed(article=art, paragraphs=list(dict.fromkeys(paras)), item=item)


def _exists(ref: ClauseRefParsed, index: Any) -> bool:
    art = ref.article.split("-")[0] if "-" in ref.article and not index.has_article(ref.article) else ref.article
    if not index.has_article(art):
        return False
    for p in ref.paragraphs:
        if not index.has_paragraph(art, p):
            return False
    if ref.item and ref.paragraphs and not index.has_item(art, ref.paragraphs[0], ref.item):
        return False
    return True


def classify_path(path: str, index: Any, *, focus_paths: list[str] | tuple[str, ...] = ()) -> str:
    s = str(path or "").strip()
    if not s:
        return ""
    if _RX_PROPOSED_MARK.search(s):
        return SOURCE_PROPOSED
    ref = parse_path(s)
    if ref is None:
        # 조 번호가 없는 위치("전문", "서명란", "별첨") — 조항 존재를 주장하지 않으므로 원문 위치로 둔다.
        return SOURCE_ORIGINAL
    if _exists(ref, index):
        return SOURCE_ORIGINAL
    if any(_strip_quotes(s) == _strip_quotes(f) for f in focus_paths):
        return SOURCE_USER
    return SOURCE_PROPOSED


def proposed_label(path: str) -> str:
    """"제14조 ⑤(같은 조 말미)" → "제14조 제5항(신설)"."""
    ref = parse_path(path)
    if ref is None:
        return re.sub(r"\s*\(같은\s*조\s*말미\)", "", str(path)).strip() + "(신설)"
    out = f"제{ref.article.replace('-', '조의 ')}조" if "-" in ref.article else f"제{ref.article}조"
    if ref.paragraphs:
        out += f" 제{ref.paragraphs[0]}항"
    if ref.item:
        out += f" 제{ref.item}호"
    return out + "(신설)"


def compress_proposed(paths: list[str]) -> list[str]:
    """["제14조 제5항(신설)", "제14조 제6항(신설)", …] → ["제14조 제5~7항"]."""
    by_art: dict[str, list[int]] = {}
    others: list[str] = []
    for p in paths:
        ref = parse_path(p)
        if ref is None or not ref.paragraphs or ref.item:
            others.append(re.sub(r"\(신설\)", "", p).strip())
            continue
        by_art.setdefault(ref.article, []).append(int(ref.paragraphs[0]))
    out: list[str] = []
    for art, nums in by_art.items():
        nums = sorted(set(nums))
        runs: list[str] = []
        start = prev = nums[0]
        for n in nums[1:] + [None]:  # type: ignore[list-item]
            if n is not None and n == prev + 1:
                prev = n
                continue
            runs.append(f"{start}~{prev}" if prev > start else f"{start}")
            if n is not None:
                start = prev = n
        out.append(f"제{art}조 제{'·'.join(runs)}항")
    return out + [o for o in others if o]


def apply_clause_provenance(
    clause_results: list[dict[str, Any]], index: Any, *, focus_paths: list[str] | tuple[str, ...] = (),
    coverage: list[dict[str, Any]] | None = None, focus_review: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """조항 참조마다 출처를 달고, 원문 근거 목록에서 원문에 없는 조항을 신설 제안으로 옮긴다."""
    moved: list[dict[str, str]] = []
    dropped: list[dict[str, str]] = []

    def _split(paths: list[str], cid: str) -> tuple[list[str], list[str], list[dict[str, str]]]:
        orig: list[str] = []
        prop: list[str] = []
        refs: list[dict[str, str]] = []
        for p in paths:
            p = str(p or "").strip()
            if not p:
                continue
            src = classify_path(p, index, focus_paths=focus_paths)
            if src == SOURCE_ORIGINAL:
                if p not in orig:
                    orig.append(p)
                refs.append({"path": p, "source": src})
            elif src == SOURCE_PROPOSED:
                lb = proposed_label(p)
                if lb not in prop:
                    prop.append(lb)
                refs.append({"path": lb, "source": src})
                if {"clause_id": cid, "path": p, "as": lb} not in moved:
                    moved.append({"clause_id": cid, "path": p, "as": lb})
            elif src == SOURCE_USER:
                refs.append({"path": p, "source": src})
                dropped.append({"clause_id": cid, "path": p, "reason": "사용자 요청 조항이 원문에 없음"})
            else:
                dropped.append({"clause_id": cid, "path": p, "reason": "조항 번호를 확인할 수 없음"})
        return orig, prop, refs

    for cr in clause_results:
        if not isinstance(cr, dict):
            continue
        cid = str(cr.get("clause_id") or "")
        g = cr.get("legal_grounding") if isinstance(cr.get("legal_grounding"), dict) else None
        rel = [str(p) for p in cr.get("related_clause_paths") or []]
        gcl = [str(p) for p in (g or {}).get("contract_clauses") or []]
        if not rel and not gcl and not cr.get("package_linked_edits"):
            continue
        r_orig, r_prop, r_refs = _split(rel, cid)
        g_orig, g_prop, g_refs = _split(gcl, cid)
        for e in cr.get("package_linked_edits") or []:
            if not isinstance(e, dict):
                continue
            dp = str(e.get("display_path") or "")
            src = classify_path(dp, index, focus_paths=focus_paths)
            if src == SOURCE_PROPOSED:
                e["display_path"] = proposed_label(dp)
                if e["display_path"] not in r_prop:
                    r_prop.append(e["display_path"])
            e["source"] = src or SOURCE_PROPOSED
        refs: list[dict[str, str]] = []
        disp = str(cr.get("display_path") or "")
        if disp:
            refs.append({"path": disp, "source": classify_path(disp, index, focus_paths=focus_paths) or SOURCE_ORIGINAL})
        for r in r_refs + g_refs:
            if r not in refs:
                refs.append(r)
        cr["clause_references"] = refs
        if rel:
            cr["related_clause_paths"] = r_orig
        proposed = list(dict.fromkeys(r_prop + g_prop))
        if proposed:
            cr["proposed_clause_paths"] = proposed
        if g is not None:
            g["contract_clauses"] = g_orig
            if proposed:
                g["proposed_clauses"] = compress_proposed(proposed)

    # 요청 답변 행 — 관련 조항은 원문 조항만, 신설 문구는 "[신설 제안]" 으로 표시한다.
    for row in (coverage or []):
        if not isinstance(row, dict):
            continue
        paths = [str(p) for p in row.get("relevant_clause_paths") or []]
        if paths:
            o, p, _ = _split(paths, str(row.get("issue_id") or ""))
            row["relevant_clause_paths"] = o
            if p:
                row["proposed_clause_paths"] = compress_proposed(p)
        pcs = row.get("proposed_clauses")
        if isinstance(pcs, list):
            fixed = []
            for s in pcs:
                s = str(s)
                head, sep, rest = s.partition(": ")
                if sep and classify_path(head, index, focus_paths=focus_paths) == SOURCE_PROPOSED:
                    s = f"[신설 제안] {proposed_label(head).replace('(신설)', '')}: {rest}"
                fixed.append(s)
            row["proposed_clauses"] = fixed
    for row in (focus_review or []):
        if isinstance(row, dict) and row.get("clause_paths"):
            o, p, _ = _split([str(x) for x in row["clause_paths"]], str(row.get("target") or ""))
            row["clause_paths"] = o
            if p:
                row["proposed_clause_paths"] = compress_proposed(p)
    return {"moved_to_proposed": moved, "unverified_removed": dropped}


def provenance_violations(clause_results: list[dict[str, Any]], index: Any,
                          coverage: list[dict[str, Any]] | None = None) -> list[str]:
    """원문 근거 목록에 원문에 없는 조항이 남아 있는가 — 남아 있으면 출력 금지."""
    bad: list[str] = []
    for cr in clause_results:
        if not isinstance(cr, dict) or not _live(cr):
            continue
        g = cr.get("legal_grounding") if isinstance(cr.get("legal_grounding"), dict) else {}
        for p in list(cr.get("related_clause_paths") or []) + list(g.get("contract_clauses") or []):
            if classify_path(str(p), index) != SOURCE_ORIGINAL:
                bad.append(f"{cr.get('clause_id')}: {p}")
    for row in coverage or []:
        if isinstance(row, dict):
            for p in row.get("relevant_clause_paths") or []:
                if classify_path(str(p), index) != SOURCE_ORIGINAL:
                    bad.append(f"{row.get('issue_id')}: {p}")
    return bad


# ── 4. 출력 문장 점검 ────────────────────────────────────────────────────────

def _live(cr: Any) -> bool:
    return (isinstance(cr, dict) and not cr.get("dedup_suppressed")
            and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM", "LOW"))


def _walk_strings(obj: Any, fn, key: str = "") -> Any:
    """원문 필드를 뺀 모든 문자열에 fn 을 적용한다(제자리)."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            if k in _ORIGINAL_TEXT_KEYS:
                continue
            obj[k] = _walk_strings(obj[k], fn, k)
        return obj
    if isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = _walk_strings(obj[i], fn, key)
        return obj
    if isinstance(obj, str):
        return fn(obj)
    return obj


_NUM = {"2": 2, "3": 3, "4": 4, "5": 5, "이": 2, "삼": 3, "사": 4, "오": 5, "두": 2, "세": 3, "네": 4}
#: "3자 계약", "3자 간", "삼자 협업", "세 당사자" — "제3자"·"제삼자"·"3자에게"는 아니다.
_RX_N_PARTY = re.compile(
    r"(?<![가-힣0-9])(?<!제 )(?P<n>[2-5]|[이삼사오])\s*자(?!에|의|가|로|를|는|은|와|과|도|만|들)(?:\s*간)?(?=\s*(?:[가-힣A-Za-z·]+\s*){0,4}?"
    r"(?:계약|협약|약정|협업|구조|거래|합의))"
)
_RX_N_PARTY_WORD = re.compile(r"(?<![가-힣])(?P<n>두|세|네)\s*당사자(?=\s*(?:간|계약|구조))")


def party_count_mentions(s: str, count: int) -> list[str]:
    out = []
    for rx in (_RX_N_PARTY, _RX_N_PARTY_WORD):
        for m in rx.finditer(s):
            if _NUM.get(m.group("n"), 0) != count:
                out.append(m.group(0))
    return out


def fix_party_count(s: str, count: int) -> str:
    def _sub(m: re.Match[str]) -> str:
        if _NUM.get(m.group("n"), 0) == count:
            return m.group(0)
        return "당사자 간" if m.group(0).rstrip().endswith("간") else ""
    s2 = _RX_N_PARTY.sub(_sub, s)
    s2 = _RX_N_PARTY_WORD.sub(lambda m: m.group(0) if _NUM.get(m.group("n"), 0) == count else "당사자", s2)
    return re.sub(r"  +", " ", s2).strip() if s2 != s else s


def _q(word: str) -> str:
    return r"[“\"'‘]?\s*" + re.escape(word) + r"\s*[”\"'’]?"


def role_mismatches(s: str, pm: PartyMap) -> list[tuple[str, str]]:
    """(틀린 표기, 고친 표기) — "광고주(을)" → "광고주(갑)", "을(시디즈)" → "갑(시디즈)"."""
    out: list[tuple[str, str]] = []
    if pm.count < 2:
        return out
    for owner in pm.parties:
        names = [w for w in [owner.role] + owner.aliases if w and w != owner.label]
        core = re.sub(r"주식회사|㈜|\(주\)", "", owner.legal_entity).strip()
        if core and len(core) >= 2:
            names.append(core)
        names = list(dict.fromkeys(names))
        for other in pm.parties:
            if other is owner:
                continue
            lab = other.label
            for w in names:
                # 다른 당사자도 같은 이름을 역할로 쓰면 판단하지 않는다.
                if w == other.role or w in other.aliases:
                    continue
                for rx in (rf"(?<![가-힣]){_q(w)}\s*\(\s*(?P<l>{_q(lab)})\s*\)",
                           rf"(?<![가-힣])(?P<l>{_q(lab)})\s*\(\s*{_q(w)}\s*\)"):
                    for m in re.finditer(rx, s):
                        a, b = m.start("l") - m.start(), m.end("l") - m.start()
                        whole = m.group(0)
                        out.append((whole, whole[:a] + m.group("l").replace(lab, owner.label) + whole[b:]))
    return out


def _fix_roles(s: str, pm: PartyMap) -> str:
    for wrong, right in role_mismatches(s, pm):
        s = s.replace(wrong, right)
    return s


# ── 5. 출력 직전 hard gate ───────────────────────────────────────────────────

def _statute_key(name: str) -> str:
    n = str(name or "")
    aliases = {
        "하도급": "하도급법", "대리점": "대리점법", "대규모유통": "대규모유통업법", "건설산업": "건설산업기본법",
        "산업안전": "산업안전보건법", "표시": "표시광고법", "개인정보": "개인정보보호법", "전자상거래": "전자상거래법",
        "가맹": "가맹사업법", "약관": "약관규제법",
    }
    for k, v in aliases.items():
        if k in n:
            return v
    return n


def run_contract_isolation_gate(
    *,
    text: str,
    meta: dict[str, Any],
    clause_results: list[dict[str, Any]],
    review: dict[str, Any] | None,
    entity_resolution: Any,
    clause_index: Any,
    focus_paths: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """출력 직전 — 고칠 수 있는 것은 고치고 기록, 남은 것은 상태 코드로 돌려준다."""
    cs = meta.get("canonical_state") if isinstance(meta.get("canonical_state"), dict) else {}
    ctype = str(cs.get("contract_type") or "")
    pm = build_party_map(entity_resolution, text, ctype,
                         str(cs.get("party_role") or ""), str(cs.get("counterparty_role") or ""))
    report: dict[str, Any] = {"party_map": pm.to_dict(), "fixed": [], "residual": {}, "status": "", "detail": ""}

    # (a) 계약유형·성격 — 당사자 수는 현재 문서의 서두·서명란으로만.
    comp = meta.get("contract_composition") if isinstance(meta.get("contract_composition"), dict) else None
    targets: list[Any] = [clause_results, meta.get("final_findings"), meta.get("user_review_coverage"),
                          meta.get("contract_composition"), meta.get("contract_legal_map"),
                          meta.get("legal_applicability_review"), meta.get("answer_intent_reviews")]
    if isinstance(review, dict):
        targets += [review.get("executive_summary"), review.get("risk_scenarios"), review.get("strategic_questions")]
    if cs:
        for k in ("primary_contract_type", "contract_type_label"):
            if isinstance(cs.get(k), str):
                v = fix_party_count(cs[k], pm.count)
                if v != cs[k]:
                    report["fixed"].append({"kind": "party_count", "where": f"canonical_state.{k}", "was": cs[k], "now": v})
                    cs[k] = v
    if comp is not None and isinstance(comp.get("primary_contract_type"), str):
        v = fix_party_count(comp["primary_contract_type"], pm.count)
        if v != comp["primary_contract_type"]:
            report["fixed"].append({"kind": "party_count", "where": "contract_composition",
                                    "was": comp["primary_contract_type"], "now": v})
            comp["primary_contract_type"] = v.strip()

    def _fix(s: str) -> str:
        new = _fix_roles(fix_party_count(s, pm.count), pm)
        if new != s:
            report["fixed"].append({"kind": "text", "was": s[:120], "now": new[:120]})
        return new

    for t in targets:
        if t is not None:
            _walk_strings(t, _fix)

    # (b) 적용 법률 — 비적용으로 확정된 법률은 AI 가 스스로 꺼낸 것이면 표에서 내리고(DROP),
    # 사용자가 물은 것이면 결론(비적용·LOW)만 남긴다. Legal Map 목록에서도 뺀다.
    statuses = ((meta.get("applicable_law_state") or {}).get("statuses") or {})
    not_applies = {k for k, v in statuses.items() if str(v).upper() == "NOT_APPLIES"}
    lar = meta.get("legal_applicability_review")
    if isinstance(lar, list) and not_applies:
        kept, dropped = [], []
        for row in lar:
            key = _statute_key(str((row or {}).get("statute") or "")) if isinstance(row, dict) else ""
            if key in not_applies or str((row or {}).get("canonical_status") or "").upper() == "NOT_APPLIES":
                if str(row.get("source") or "") == "ai_self_identified":
                    dropped.append(str(row.get("statute") or ""))
                    continue
                # 사용자가 물었거나 유형 정책이 반드시 싣는 행(대리점·위탁판매의 대리점법 등)은 그 행의 결론을
                # 그대로 둔다 — 여기서 등급을 바꾸면 사업부가 정한 golden 판단을 뒤집는다(그림닷컴 실측).
            kept.append(row)
        if dropped:
            meta["legal_applicability_review"] = kept
            meta["legal_applicability_dropped"] = [
                {"statute": s, "reason": "현재 계약의 거래구조가 적용요건을 충족하지 않아 검토 대상에서 제외(DROP)"}
                for s in dropped
            ]
    lm = meta.get("contract_legal_map")
    if isinstance(lm, dict) and isinstance(lm.get("applicable_statutes"), str) and not_applies:
        parts = [p.strip() for p in re.split(r",\s*(?![^()]*\))", lm["applicable_statutes"]) if p.strip()]
        keep = [p for p in parts if _statute_key(p.split("(")[0]) not in not_applies]
        if len(keep) != len(parts):
            report["fixed"].append({"kind": "legal_map_statutes", "removed": [p for p in parts if p not in keep]})
            lm["applicable_statutes"] = ", ".join(keep)

    # 비적용 법률을 근거 조문으로 인용한 finding — 인용만 걷어 낸다(판단은 계약상 효과로 남는다).
    if not_applies:
        for cr in clause_results:
            g = cr.get("legal_grounding") if isinstance(cr, dict) else None
            if not isinstance(g, dict) or not g.get("statutes"):
                continue
            keep = [st for st in g["statutes"]
                    if _statute_key(str((st or {}).get("citation") or "")) not in not_applies]
            if len(keep) != len(g["statutes"]):
                report["fixed"].append({"kind": "statute_citation", "clause_id": cr.get("clause_id"),
                                        "removed": [st.get("citation") for st in g["statutes"] if st not in keep]})
                g["statutes"] = keep

    # (c) 조항 출처.
    prov = apply_clause_provenance(clause_results, clause_index, focus_paths=focus_paths,
                                   coverage=meta.get("user_review_coverage"),
                                   focus_review=meta.get("user_focus_review"))
    report["provenance"] = prov

    # ── 남은 위반 ─────────────────────────────────────────────────────────
    residual_count: list[str] = []
    residual_role: list[str] = []

    def _scan(s: str) -> str:
        residual_count.extend(party_count_mentions(s, pm.count))
        residual_role.extend(w for w, _ in role_mismatches(s, pm))
        return s

    for t in targets + [cs]:
        if t is not None:
            _walk_strings(t, _scan)
    if pm.count and int(_count_in_comp(comp, pm.count)) != pm.count:
        residual_count.append(str((comp or {}).get("primary_contract_type")))
    residual_prov = provenance_violations(clause_results, clause_index, meta.get("user_review_coverage"))

    # 계약유형·적용 법률의 단일 상태.
    conflicts: list[str] = []
    label = str(cs.get("contract_type_label") or "")
    if comp is not None and comp.get("canonical_label") and label and comp["canonical_label"] != label:
        conflicts.append(f"계약유형: canonical_state '{label}' ↔ 계약 성격 '{comp['canonical_label']}'")
    for row in meta.get("legal_applicability_review") or []:
        if not isinstance(row, dict):
            continue
        key = _statute_key(str(row.get("statute") or ""))
        if (key in not_applies and str(row.get("source") or "") == "ai_self_identified"
                and str(row.get("risk_level") or "").upper() in ("HIGH", "MEDIUM")):
            conflicts.append(f"{key}: 비적용 확정인데 적용성 표 {row.get('risk_level')}")
    for cr in clause_results:
        if not _live(cr) or str(cr.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
            continue
        for st in ((cr.get("legal_grounding") or {}).get("statutes") or []):
            key = _statute_key(str((st or {}).get("citation") or ""))
            if key in not_applies:
                conflicts.append(f"{cr.get('clause_id')}: 비적용 법률 {key} 를 근거로 인용")
    for row in meta.get("user_review_coverage") or []:
        if isinstance(row, dict) and str(row.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM"):
            blob = " ".join(str(row.get(k) or "") for k in ("normalized_issue", "conclusion"))
            hit = [k for k in not_applies if k in blob and not re.search(rf"{k}[^.。]{{0,40}}(?:적용되지|비적용|해당하지)", blob)]
            if hit:
                conflicts.append(f"{row.get('issue_id')}: 비적용 법률 {', '.join(hit)} 를 {row.get('risk_tier')} 근거로 사용")

    state = build_contract_state(text=text, meta=meta, party_map=pm, entity_resolution=entity_resolution,
                                 clause_index=clause_index, clause_results=clause_results,
                                 focus_paths=list(focus_paths))
    report["contract_state"] = state.to_dict()
    report["residual"] = {
        "party_count": sorted(set(residual_count)), "party_role": sorted(set(residual_role)),
        "clause_provenance": residual_prov, "state_conflicts": conflicts, "ungrounded": state.ungrounded,
    }
    if residual_count or state.ungrounded:
        report["status"] = STATUS_PARTY_COUNT
        report["detail"] = "; ".join((sorted(set(residual_count)) + state.ungrounded)[:4])
    elif residual_role:
        report["status"] = STATUS_PARTY_ROLE
        report["detail"] = "; ".join(sorted(set(residual_role))[:4])
    elif residual_prov:
        report["status"] = STATUS_PROVENANCE
        report["detail"] = "; ".join(residual_prov[:4])
    elif conflicts:
        report["status"] = STATUS_STATE_CONFLICT
        report["detail"] = "; ".join(conflicts[:4])
    return report


def _count_in_comp(comp: dict[str, Any] | None, count: int) -> int:
    """계약 성격 문자열이 말하는 당사자 수 — 말하지 않으면 확정값과 같다고 본다."""
    if not comp:
        return count
    m = _RX_N_PARTY.search(str(comp.get("primary_contract_type") or ""))
    return _NUM.get(m.group("n"), count) if m else count


__all__ = [
    "RESET_PREVIOUS_CONTRACT_STATE", "STATUS_PARTY_COUNT", "STATUS_PARTY_ROLE", "STATUS_PROVENANCE",
    "STATUS_STATE_CONFLICT", "SOURCE_ORIGINAL", "SOURCE_PROPOSED", "SOURCE_USER",
    "PartyMap", "PartyEntry", "ContractReviewState", "build_party_map", "build_contract_state",
    "parse_path", "classify_path", "proposed_label", "compress_proposed", "apply_clause_provenance",
    "provenance_violations", "party_count_mentions", "fix_party_count", "role_mismatches",
    "run_contract_isolation_gate",
]
