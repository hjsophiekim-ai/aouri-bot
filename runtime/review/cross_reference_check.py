"""계약 원문 안의 상호참조가 실제로 그 대상을 가리키는지 확인한다 (2026-10-21 지시 3·4항).

왜 필요했나 (실측 — 프리랜서 콘텐츠 용역계약)
─────────────────────────────────────────────
제2조 제1항은 1호 원소스 콘텐츠 · 2호 채널별 미러링 · 3호 큐레이션형 뉴스레터 ·
4호 이미지 활용 제안 · 5호 월 1회 진행 상황 공유 다. 그런데 제2조 제2항과 제5조
제3항은 "제1항 제2호 및 제5호에 따른 채널별 미러링 및 큐레이션형 뉴스레터" 라고
적었다. 큐레이션형 뉴스레터는 제3호다 — 제5호는 진행 상황 공유다. 문언대로
읽으면 뉴스레터의 수량 협의·수정 횟수 한도가 엉뚱한 업무에 걸린다.

기존 게이트는 **검토 결과**가 인용한 조항이 존재하는지만 본다. 계약서 자체의
참조가 틀린 것은 아무도 보지 않았다.

판정
────
· 존재: 가리키는 조·항·호가 원문에 없으면 오류다.
· 내용: 참조와 함께 대상 이름을 적었는데(예: "… 제5호에 따른 큐레이션형 뉴스레터",
  "큐레이션형 뉴스레터(… 제5호)"), 그 이름이 **참조된 호 어디에도 없고 다른 호에만**
  있으면 오류다. 이름이 어느 호에도 없으면 판단하지 않는다 — 모르는 것으로 지적하지 않는다.
· 회사명·조항번호·업무명을 상수로 쓰지 않는다. 같은 조 안의 목록 구조와 문언만 본다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_RX_ITEM_LIST = r"제\s*(\d+)\s*호(?:\s*(?:및|·|,|과|와|또는)\s*제\s*(\d+)\s*호)*"
#: "[제N조] 제M항 제A호 (및 제B호)" — 조가 없으면 같은 조 안의 참조다.
_RX_REF = re.compile(
    r"(?:제\s*(?P<art>\d+)\s*조\s*)?제\s*(?P<para>\d+)\s*항\s*(?P<items>" + _RX_ITEM_LIST + r")"
)
_RX_ITEM_NUM = re.compile(r"제\s*(\d+)\s*호")
#: 이름 목록을 끊는 조사·어미
_RX_NAME_SPLIT = re.compile(r"\s*(?:및|·|,|과\s|와\s)\s*")


def _attr(obj: Any, name: str) -> str:
    v = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return "" if v is None else str(v)


def _n(s: str) -> str:
    return re.sub(r"[\s\"'“”‘’]", "", str(s or ""))


@dataclass
class XrefError:
    article: str            # 참조가 적힌 조
    paragraph: str          # 참조가 적힌 항
    ref_article: str
    ref_paragraph: str
    cited_items: list[str]
    name: str               # 문언상 가리키려던 대상
    actual_items: list[str]  # 그 이름이 실제로 있는 호
    sentence: str
    kind: str               # "missing_target" | "content_mismatch"
    #: 함께 적힌 다른 이름이 맞게 가리키는 호 — 이 호들은 틀리지 않았다.
    matched_items: tuple[str, ...] = ()

    @property
    def wrong_items(self) -> list[str]:
        return [i for i in self.cited_items if i not in self.actual_items and i not in self.matched_items]

    def corrected(self) -> str:
        """오인용 호를 실제 호로 바꾼 문장 — 바꿀 짝이 하나로 정해질 때만."""
        wrong = self.wrong_items
        if self.kind != "content_mismatch" or len(wrong) != 1 or len(self.actual_items) != 1:
            return ""
        return re.sub(rf"제\s*{wrong[0]}\s*호", f"제{self.actual_items[0]}호", self.sentence, count=1)


def _structure(clauses: list[Any]) -> dict[tuple[str, str], dict[str, str]]:
    """(조, 항) → {호: 호 원문}."""
    out: dict[tuple[str, str], dict[str, str]] = {}
    for c in clauses:
        art, para, item = _attr(c, "article_number"), _attr(c, "paragraph_number"), _attr(c, "item_number")
        if art and para and item:
            out.setdefault((art, para), {})[item] = _attr(c, "text")
    return out


def _names_near(sentence: str, m: re.Match[str]) -> list[str]:
    """참조와 함께 적힌 대상 이름들."""
    after = sentence[m.end():]
    before = sentence[:m.start()]
    names: list[str] = []
    a = re.match(r"\s*(?:에\s*따른|의|에\s*해당하는|에서\s*정한)\s*(.{2,60}?)(?:의\s|은\s|는\s|을\s|를\s|에\s|이\s|가\s|\()", after)
    if a:
        names += _RX_NAME_SPLIT.split(a.group(1))
    b = re.search(r"([^.\n(（]{2,60})[(（]\s*$", before)
    if b:
        names += _RX_NAME_SPLIT.split(b.group(1))
    out = []
    for nm in names:
        nm = re.sub(r"^(?:등|각|해당|위|그)\s*", "", nm.strip())
        if len(_n(nm)) >= 4:
            out.append(nm)
    return out


def find_cross_reference_errors(clauses: list[Any] | None) -> list[XrefError]:
    clauses = list(clauses or [])
    struct = _structure(clauses)
    errors: list[XrefError] = []
    seen: set[tuple[str, str, str]] = set()
    for c in clauses:
        art, para = _attr(c, "article_number"), _attr(c, "paragraph_number")
        text = _attr(c, "text")
        if not art or not text or _attr(c, "item_number"):
            continue
        for sent in re.split(r"(?<=[.。])\s+", text):
            for m in _RX_REF.finditer(sent):
                ref_art = m.group("art") or art
                ref_para = m.group("para")
                cited = _RX_ITEM_NUM.findall(m.group("items"))
                items = struct.get((ref_art, ref_para))
                if not items:
                    continue  # 호 구조를 모르는 항 — 판단하지 않는다
                key = (art, para, m.group(0))
                if key in seen:
                    continue
                seen.add(key)
                missing = [i for i in cited if i not in items]
                if missing:
                    errors.append(XrefError(art, para, ref_art, ref_para, cited, "", [], sent.strip(), "missing_target"))
                    continue
                names = _names_near(sent, m)
                hits_by_name = {nm: [i for i, t in items.items() if _n(nm) in _n(t)] for nm in names}
                matched = tuple(sorted({i for h in hits_by_name.values() for i in h if i in cited}))
                for name, hits in hits_by_name.items():
                    if hits and not set(hits) & set(cited):
                        errors.append(XrefError(art, para, ref_art, ref_para, cited, name.strip(), hits,
                                                sent.strip(), "content_mismatch", matched))
    return errors


def _item_text(clauses: list[Any] | None, art: str, para: str, item: str) -> str:
    for c in clauses or []:
        if (_attr(c, "article_number"), _attr(c, "paragraph_number"), _attr(c, "item_number")) == (art, para, item):
            return _attr(c, "text")
    return ""


def build_findings(errors: list[XrefError], clauses: list[Any] | None) -> list[dict[str, Any]]:
    """오류마다 해당 항을 고치는 finding 하나. 같은 원인의 다른 항은 연계 수정으로 묶는다."""
    by_path = {(_attr(c, "article_number"), _attr(c, "paragraph_number")): c for c in (clauses or [])
               if not _attr(c, "item_number")}
    findings: list[dict[str, Any]] = []
    for e in errors:
        chunk = by_path.get((e.article, e.paragraph))
        if chunk is None:
            continue
        path = f"제{e.article}조 제{e.paragraph}항"
        target = f"제{e.ref_article}조 제{e.ref_paragraph}항" if e.ref_article != e.article else f"제{e.ref_paragraph}항"
        original = _attr(chunk, "text").strip()
        if e.kind == "missing_target":
            problem = (f"{path}에서 {target} " + "·".join(f"제{i}호" for i in e.cited_items)
                       + "를 가리키지만 원문에 그 호가 없습니다. 어떤 업무·대상에 적용되는지 문언만으로 정해지지 않습니다.")
            rewrite = ""
        else:
            wrong = e.wrong_items
            wrong_desc = "·".join(
                f"제{i}호({re.sub(r'\s+', ' ', _item_text(clauses, e.ref_article, e.ref_paragraph, i))[:30]})"
                for i in wrong)
            problem = (f"{path}에서 '{e.name}'의 근거로 {target} " + "·".join(f"제{i}호" for i in e.cited_items)
                       + f"를 들고 있으나, '{e.name}'은 {target} 제{'·'.join(e.actual_items)}호이고 "
                       + f"{wrong_desc}는 다른 업무입니다. 문언대로 적용하면 이 항의 수량·조건이 의도와 다른 업무에 "
                       "걸리고, 정작 해당 업무에는 근거가 비게 됩니다.")
            fixed = e.corrected()
            rewrite = original.replace(e.sentence, fixed) if fixed and e.sentence in original else ""
        findings.append({
            "clause_id": f"xref_{e.article}_{e.paragraph}",
            "clause_title": _attr(chunk, "title"),
            "display_path": path,
            "article_number": e.article,
            "paragraph_number": e.paragraph,
            "original_text": original,
            "issue_title": "상호참조 호 번호 불일치",
            "detected_issue_list": [{"issue_title": "상호참조 호 번호 불일치"}],
            "problem": problem,
            "rewrite_reason": problem,
            "legal_business_reason": "계약 해석상 다툼을 줄이기 위한 문언 정정 — 법률 적용 문제가 아니라 계약 문언의 정확성 문제입니다.",
            "suggested_rewrite": rewrite,
            "proposed_revision": rewrite,
            "recommendation_text": rewrite,
            "risk_tier": "MEDIUM", "severity": "MEDIUM", "review_tier": "SUGGEST",
            "must_fix": False, "confidence": 0.95, "legal_core": False,
            "is_cross_reference_error": True,
            "has_rewrite_change": bool(rewrite),
            "location_instruction": f"{path} 교체",
            "cross_reference": {
                "cited": [f"제{i}호" for i in e.cited_items], "name": e.name,
                "actual": [f"제{i}호" for i in e.actual_items], "kind": e.kind,
            },
        })
    # 같은 이름·같은 오인용이 여러 항에 있으면 하나를 주 지적으로 두고 나머지를 연계 수정으로 싣는다.
    primary: dict[tuple[str, str], dict[str, Any]] = {}
    out: list[dict[str, Any]] = []
    for f in findings:
        xr = f["cross_reference"]
        k = (xr["name"], ",".join(xr["cited"]))
        if xr["kind"] == "content_mismatch" and k in primary:
            p = primary[k]
            p["related_clause_paths"] = list(dict.fromkeys((p.get("related_clause_paths") or [p["display_path"]]) + [f["display_path"]]))
            p.setdefault("package_linked_edits", []).append(
                {"display_path": f["display_path"], "text": f["suggested_rewrite"] or f["original_text"]})
            p["problem"] += f" 같은 오인용이 {f['display_path']}에도 있어 함께 고쳐야 합니다."
            p["rewrite_reason"] = p["problem"]
            continue
        primary[k] = f
        out.append(f)
    return out
