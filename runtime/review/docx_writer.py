from __future__ import annotations

import difflib
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

from runtime.review.word_markers import contains_wordprocessingml_markers
from runtime.review.clause_label import format_clause_label


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PKG_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XML_NS = "http://www.w3.org/XML/1998/namespace"

ET.register_namespace("w", W_NS)


def _contains_wordprocessingml_markers(text: str) -> bool:
    return contains_wordprocessingml_markers(text)


def _w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def _ensure_safe_text(s: str) -> str:
    if _contains_wordprocessingml_markers(s):
        raise ValueError("WordprocessingML markers detected in docx content text")
    return s


def _p(parent: ET.Element) -> ET.Element:
    return ET.SubElement(parent, _w("p"))


def _r(
    parent: ET.Element,
    *,
    bold: bool = False,
    underline: bool = False,
    strike: bool = False,
    color_hex: str | None = None,
    highlight: str | None = None,
) -> ET.Element:
    r = ET.SubElement(parent, _w("r"))
    rpr = None
    if (
        bold
        or underline
        or strike
        or (isinstance(color_hex, str) and color_hex.strip())
        or (isinstance(highlight, str) and highlight.strip())
    ):
        rpr = ET.SubElement(r, _w("rPr"))
    if bold and rpr is not None:
        ET.SubElement(rpr, _w("b"))
    if underline and rpr is not None:
        u = ET.SubElement(rpr, _w("u"))
        u.set(_w("val"), "single")
    if strike and rpr is not None:
        ET.SubElement(rpr, _w("strike"))
    if isinstance(color_hex, str) and color_hex.strip() and rpr is not None:
        c = ET.SubElement(rpr, _w("color"))
        c.set(_w("val"), color_hex.strip())
    if isinstance(highlight, str) and highlight.strip() and rpr is not None:
        h = ET.SubElement(rpr, _w("highlight"))
        h.set(_w("val"), highlight.strip())
    return r


def _t(parent: ET.Element, text: str) -> ET.Element:
    t = ET.SubElement(parent, _w("t"))
    t.set(f"{{{XML_NS}}}space", "preserve")
    t.text = _ensure_safe_text(text)
    return t


def _split_lines(s: str) -> list[str]:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return [x for x in (x.strip() for x in s.split("\n")) if x]


def _norm_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _words(s: str) -> list[str]:
    t = _norm_text(s)
    if not t:
        return []
    return re.findall(r"[0-9A-Za-z가-힣]+|[^\s0-9A-Za-z가-힣]|\s+", t)


def _diff_runs(original: str, revised: str) -> list[tuple[str, dict[str, Any]]]:
    a = _words(original)
    b = _words(revised)
    sm = difflib.SequenceMatcher(a=a, b=b)
    out: list[tuple[str, dict[str, Any]]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            s = "".join(a[i1:i2])
            if s:
                out.append((s, {}))
        elif tag == "insert":
            s = "".join(b[j1:j2])
            if s:
                out.append((s, {"color_hex": "D64545"}))
        elif tag == "delete":
            s = "".join(a[i1:i2])
            if s:
                out.append((s, {"color_hex": "D64545", "strike": True}))
        elif tag == "replace":
            s_del = "".join(a[i1:i2])
            if s_del:
                out.append((s_del, {"color_hex": "D64545", "strike": True}))
            s_ins = "".join(b[j1:j2])
            if s_ins:
                out.append((s_ins, {"color_hex": "D64545"}))
    merged: list[tuple[str, dict[str, Any]]] = []
    for text, style in out:
        if not text:
            continue
        if merged and merged[-1][1] == style:
            merged[-1] = (merged[-1][0] + text, style)
        else:
            merged.append((text, style))
    return merged


def _extract_law_titles(cr: dict[str, Any], *, limit: int = 3) -> list[str]:
    law = cr.get("related_laws")
    out: list[str] = []
    if isinstance(law, dict) and isinstance(law.get("results"), dict):
        for k in ("laws", "precedents", "interpretations"):
            arr = law["results"].get(k)
            if isinstance(arr, list):
                for it in arr:
                    if isinstance(it, dict) and isinstance(it.get("title"), str) and it["title"].strip():
                        t = it["title"].strip()
                        if t not in out:
                            out.append(t)
                    if len(out) >= limit:
                        return out
    return out[:limit]


def _extract_law_titles_from_search(law_search: dict[str, Any] | None, *, limit: int = 6) -> list[str]:
    if not isinstance(law_search, dict):
        return []
    results = law_search.get("results")
    if not isinstance(results, dict):
        return []
    out: list[str] = []
    for k in ("laws", "precedents", "interpretations"):
        arr = results.get(k)
        if isinstance(arr, list):
            for it in arr:
                if isinstance(it, dict) and isinstance(it.get("title"), str) and it["title"].strip():
                    t = it["title"].strip()
                    if t not in out:
                        out.append(t)
                if len(out) >= limit:
                    return out
    return out[:limit]


def _clause_label_from_original_clause(oc: dict[str, Any], *, style: str = "bracketed") -> str:
    cid = str(oc.get("clause_id") or "").strip()
    dp = str(oc.get("display_path") or "").strip()
    if not dp:
        an = str(oc.get("article_number") or "").strip()
        dp = (f"제{an}조" if (an and cid.startswith("KR-")) else an) if an else cid
    ctitle = str(oc.get("clause_title") or "").strip()
    label = format_clause_label(display_path=dp, clause_title=ctitle, style=style).strip()
    return label or cid or "조항"


def _clause_hierarchy_lines_from_original_clause(oc: dict[str, Any]) -> list[str]:
    cid = str(oc.get("clause_id") or "").strip()
    an = str(oc.get("article_number") or "").strip()
    pn = str(oc.get("paragraph_number") or "").strip()
    inum = str(oc.get("item_number") or "").strip()
    sn = str(oc.get("subitem_number") or "").strip()
    title = str(oc.get("clause_title") or "").strip()
    if title.startswith("[") and title.endswith("]"):
        title = title[1:-1].strip()
    lines: list[str] = []
    if an:
        head = f"제{an}조" if cid.startswith("KR-") else an
        lines.append((head + (f" [{title}]" if title else "")).strip())
    else:
        dp = str(oc.get("display_path") or "").strip()
        lines.append((dp or cid or "조항").strip())
        return lines
    if pn:
        lines.append(f"제{pn}항")
    if inum:
        lines.append(f"제{inum}호")
    if sn:
        lines.append(f"{sn}목")
    return [x for x in lines if x]


def _summarize_change_points(original: str, revised: str, *, limit: int = 4) -> tuple[list[str], list[str]]:
    a = [x for x in re.findall(r"[0-9A-Za-z가-힣]+", _norm_text(original)) if x]
    b = [x for x in re.findall(r"[0-9A-Za-z가-힣]+", _norm_text(revised)) if x]
    sm = difflib.SequenceMatcher(a=a, b=b)
    added: list[str] = []
    removed: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace"):
            for w in b[j1:j2]:
                if w not in added:
                    added.append(w)
                if len(added) >= limit:
                    break
        if tag in ("delete", "replace"):
            for w in a[i1:i2]:
                if w not in removed:
                    removed.append(w)
                if len(removed) >= limit:
                    break
        if len(added) >= limit and len(removed) >= limit:
            break
    return added[:limit], removed[:limit]


def _risk_tier_from_clause_result(cr: dict[str, Any]) -> str:
    if bool(cr.get("approval_required")) or bool(cr.get("high_risk")):
        return "HIGH"
    rt = cr.get("risk_tier")
    if isinstance(rt, str) and rt.strip().upper() in ("HIGH", "MEDIUM", "LOW"):
        return rt.strip().upper()
    return "MEDIUM" if bool(cr.get("unfavorable_to_us")) else "LOW"


def _key_phrases(original: str, revised: str, *, limit: int = 2) -> tuple[str, str]:
    before: list[str] = []
    after: list[str] = []
    for t, style in _diff_runs(original or "", revised or ""):
        s = (t or "").strip()
        if not s:
            continue
        if style.get("strike"):
            if s not in before:
                before.append(s)
        elif style.get("color_hex"):
            if s not in after:
                after.append(s)
        if len(before) >= limit and len(after) >= limit:
            break

    def shrink(parts: list[str]) -> str:
        out = []
        for x in parts[:limit]:
            x = re.sub(r"\s+", " ", x).strip()
            if len(x) > 48:
                x = x[:48] + "…"
            out.append(x)
        return " / ".join(out) if out else "-"

    return shrink(before), shrink(after)

def _tbl(parent: ET.Element, *, col_widths: list[int]) -> ET.Element:
    tbl = ET.SubElement(parent, _w("tbl"))
    tbl_pr = ET.SubElement(tbl, _w("tblPr"))
    tbl_w = ET.SubElement(tbl_pr, _w("tblW"))
    tbl_w.set(_w("w"), "0")
    tbl_w.set(_w("type"), "auto")
    tbl_borders = ET.SubElement(tbl_pr, _w("tblBorders"))
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = ET.SubElement(tbl_borders, _w(side))
        el.set(_w("val"), "single")
        el.set(_w("sz"), "4")
        el.set(_w("space"), "0")
        el.set(_w("color"), "000000")
    grid = ET.SubElement(tbl, _w("tblGrid"))
    for w in col_widths:
        gc = ET.SubElement(grid, _w("gridCol"))
        gc.set(_w("w"), str(int(w)))
    return tbl


def _tc(parent_tr: ET.Element, *, width: int) -> ET.Element:
    tc = ET.SubElement(parent_tr, _w("tc"))
    tc_pr = ET.SubElement(tc, _w("tcPr"))
    tcw = ET.SubElement(tc_pr, _w("tcW"))
    tcw.set(_w("w"), str(int(width)))
    tcw.set(_w("type"), "dxa")
    return tc


@dataclass(frozen=True)
class DocxFile:
    filename: str
    content: bytes


def build_revision_docx(
    *,
    entity: str,
    contract_type: str,
    filename: str | None,
    original_clauses: list[dict[str, Any]],
    clause_results: list[dict[str, Any]],
    review_summary: dict[str, Any] | None = None,
    law_search: dict[str, Any] | None = None,
    questions: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    final_review_context: dict[str, Any] | None = None,
    checklist_items: list[dict[str, Any]] | None = None,
) -> bytes:
    contract_name = filename or "미상"
    counterparty = "미상"

    orig_by_id: dict[str, dict[str, Any]] = {}
    orig_order: list[str] = []
    for c in original_clauses:
        if isinstance(c, dict) and isinstance(c.get("clause_id"), str) and str(c.get("clause_id") or "").strip():
            _ensure_safe_text(str(c.get("clause_id") or ""))
            _ensure_safe_text(str(c.get("article_number") or ""))
            _ensure_safe_text(str(c.get("clause_title") or ""))
            _ensure_safe_text(str(c.get("text") or ""))
            cid = str(c.get("clause_id"))
            orig_by_id[cid] = c
            orig_order.append(cid)

    cr_by_id: dict[str, dict[str, Any]] = {}
    for cr in clause_results:
        if isinstance(cr, dict) and isinstance(cr.get("clause_id"), str):
            cr_by_id[str(cr.get("clause_id"))] = cr

    for cid, cr in cr_by_id.items():
        oc = orig_by_id.get(cid)
        if oc is None:
            raise ValueError(f"clause_id not found in original_clauses: {cid}")
        ot = str(oc.get("clause_title") or "").strip()
        rt = str(cr.get("clause_title") or "").strip()
        if ot and rt and ot != rt:
            raise ValueError(f"clause_title mismatch for {cid}")

    frc0 = final_review_context if isinstance(final_review_context, dict) else {}
    jur_kind = (frc0.get("jurisdiction") or {}).get("kind") if isinstance(frc0.get("jurisdiction"), dict) else None
    prof0 = (frc0.get("contract_profile") or {}).get("profile") if isinstance(frc0.get("contract_profile"), dict) else None
    is_dealer_contract = (prof0 == "dealer_consignment") or any(k in str(contract_type or "") for k in ("대리점", "유통", "위탁"))

    def should_show(cr: dict[str, Any]) -> bool:
        tier = _risk_tier_from_clause_result(cr)
        if str(cr.get("display_kind") or "") in ("redline", "guidance", "keep"):
            return True
        if bool(cr.get("user_focus_hit")) or bool(cr.get("factual_hit")):
            return True
        if bool(cr.get("approval_required")) or bool(cr.get("high_risk")):
            return True
        if tier in ("HIGH", "MEDIUM"):
            return True
        if bool(cr.get("has_rewrite_change")):
            return True
        sr = cr.get("suggested_rewrite")
        if isinstance(sr, str) and sr.strip():
            return True
        return False

    show_ids: list[str] = []
    for cid in orig_order:
        cr = cr_by_id.get(cid)
        if isinstance(cr, dict) and should_show(cr):
            show_ids.append(cid)

    tier_by_id: dict[str, str] = {cid: _risk_tier_from_clause_result(cr_by_id.get(cid) or {}) for cid in show_ids}

    for cid in show_ids:
        cr = cr_by_id.get(cid) or {}
        tier = tier_by_id.get(cid) or "LOW"
        if bool(cr.get("keep_as_is")):
            continue
        # dedup_suppressed / guardrail_block 항목은 suggested_rewrite가 None이어도 정상
        if bool(cr.get("dedup_suppressed")):
            continue
        if bool(cr.get("guardrail_block")):
            continue
        if tier in ("HIGH", "MEDIUM"):
            if not bool(cr.get("must_fix")) and not bool(cr.get("approval_required")):
                continue
            # guidance 항목(원문 보존 + 안내문 형식)은 suggested_rewrite 없어도 정상
            if str(cr.get("display_kind") or "") == "guidance":
                continue
            # 체크리스트 항목은 recommendation_text를 사용하므로 suggested_rewrite 불필요
            if bool(cr.get("is_checklist_item")):
                continue
            sr = cr.get("suggested_rewrite")
            if not (isinstance(sr, str) and sr.strip()):
                raise ValueError(f"missing suggested_rewrite for {cid} tier={tier}")

    def _is_advisory_append_format(cr: dict[str, Any]) -> bool:
        sr = str(cr.get("suggested_rewrite") or "")
        return "[추가 권고]" in sr or "[수정 제안" in sr

    redline_ids = [
        cid for cid in show_ids
        if bool((cr_by_id.get(cid) or {}).get("has_rewrite_change"))
        and tier_by_id.get(cid) == "HIGH"
        and not _is_advisory_append_format(cr_by_id.get(cid) or {})
    ]
    guide_ids = [cid for cid in show_ids if cid not in set(redline_ids)]
    medium_ids = [cid for cid in guide_ids if tier_by_id.get(cid) == "MEDIUM"]
    low_ids = [cid for cid in guide_ids if tier_by_id.get(cid) == "LOW"]

    title = "아우리봇 계약 검토·수정본 (법무팀 검토용)"
    meta = [
        f"계약명: {contract_name}",
        f"상대방: {counterparty}",
        f"법인: {entity}",
        f"계약유형: {contract_type}",
    ]

    doc = ET.Element(_w("document"))
    body = ET.SubElement(doc, _w("body"))

    p0 = _p(body)
    r0 = _r(p0, bold=True)
    _t(r0, title)
    for m in meta:
        pm = _p(body)
        rm = _r(pm)
        _t(rm, m)
    pleg = _p(body)
    _t(_r(pleg, bold=True), "표시(legend):")
    pleg1 = _p(body)
    _t(_r(pleg1), "- 필수수정(HIGH): 본문 redline(추가=빨간색, 삭제=빨간 취소선)")
    pleg2 = _p(body)
    _t(_r(pleg2, color_hex="1F7AE0"), "- 권장수정(MEDIUM): 파란 안내(guidance) 섹션에 방향/사유 표시")
    pleg3 = _p(body)
    _t(_r(pleg3, color_hex="1F7AE0"), "- 참고제안(LOW): 파란 안내(guidance) 또는 부록에만 표시(본문 미수정)")
    _p(body)

    high_risk_rows: list[dict[str, str]] = []
    approval_rows: list[dict[str, str]] = []
    for cid in show_ids:
        cr = cr_by_id.get(cid) or {}
        if bool(cr.get("high_risk")):
            high_risk_rows.append({"clause_id": cid, "title": str(cr.get("clause_title") or "")})
        if bool(cr.get("approval_required")):
            approval_rows.append({"clause_id": cid, "title": str(cr.get("clause_title") or "")})

    sec_sum = _p(body)
    _t(_r(sec_sum, bold=True), "1) 표지/요약")
    ps = _p(body)
    _t(_r(ps), f"필수수정(HIGH): {len(redline_ids)} / 권장수정(MEDIUM): {len(medium_ids)} / 참고제안(LOW): {len(low_ids)}")
    ps2 = _p(body)
    _t(_r(ps2), f"High risk 조항 수: {len(high_risk_rows)} / Approval required 조항 수: {len(approval_rows)}")

    frc0 = final_review_context if isinstance(final_review_context, dict) else {}
    if bool(frc0.get("expert_mode")):
        sec_pos = _p(body)
        _t(_r(sec_pos, bold=True), "1-0) 계약 성격 및 우리 측 포지션 분석")
        party0 = frc0.get("party_role") if isinstance(frc0.get("party_role"), dict) else {}
        our_role0 = str(party0.get("our_role") or "")
        our_label0 = str(party0.get("our_label") or "")
        if our_role0 == "supplier":
            our_role_ko = "공급업자"
        elif our_role0 == "contractor":
            our_role_ko = "수급인"
        elif our_role0 == "buyer":
            our_role_ko = "구매자/발주자"
        elif our_role0 == "ordering_party":
            our_role_ko = "도급인/발주자"
        else:
            our_role_ko = "미확정"
        pp0 = _p(body)
        _t(_r(pp0), "우리 측 지위: " + our_role_ko + (f" ({our_label0})" if our_label0 else ""))
        strat0 = frc0.get("expert_strategy") if isinstance(frc0.get("expert_strategy"), list) else []
        for s in [x for x in strat0 if isinstance(x, str) and x.strip()][:4]:
            pps = _p(body)
            _t(_r(pps), "- " + s.strip())
        _p(body)

        sec_top = _p(body)
        _t(_r(sec_top, bold=True), "1-1) 치명적 리스크 Top 3~5 (변호사 Pick)")
        topic_weight_supplier = {
            "dealer_unfair": 40,
            "payment_settlement": 35,
            "termination": 32,
            "cost_burden": 28,
            "personal_data": 18,
            "dispute": 5,
        }
        topic_weight_contractor = {
            "payment_settlement": 40,
            "other": 34,
            "safety": 28,
            "termination": 22,
            "cost_burden": 18,
            "dispute": 6,
        }
        tw0 = topic_weight_supplier if our_role0 == "supplier" else (topic_weight_contractor if our_role0 == "contractor" else {})

        def _score_top3(cr: dict[str, Any]) -> int:
            s = 0
            rt0 = str(cr.get("risk_tier") or "").upper()
            if rt0 == "HIGH":
                s += 110
            elif rt0 == "MEDIUM":
                s += 80
            if bool(cr.get("approval_required")):
                s += 50
            if bool(cr.get("high_risk")):
                s += 40
            if bool(cr.get("must_fix")):
                s += 30
            if bool(cr.get("user_focus_hit")):
                s += 25
            ct0 = str(cr.get("clause_topic") or "")
            s += int(tw0.get(ct0, 0))
            if is_dealer_contract and str(jur_kind or "") == "domestic_korea" and ct0 == "dispute" and not bool(cr.get("user_focus_hit")):
                s -= 80
            return s

        cand0 = [
            cr
            for cr in clause_results
            if isinstance(cr, dict)
            and not bool(cr.get("dedup_suppressed"))
            and not bool(cr.get("keep_as_is"))
            and (str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM") or bool(cr.get("user_focus_hit")) or bool(cr.get("high_risk")) or bool(cr.get("approval_required")))
        ]
        cand0 = sorted(cand0, key=lambda cr: (-_score_top3(cr), str(cr.get("clause_id") or "")))
        picked: list[dict[str, Any]] = []
        seen_articles: set[str] = set()
        for cr in cand0:
            cid = str(cr.get("clause_id") or "")
            oc = orig_by_id.get(cid) or {}
            head = " / ".join(_clause_hierarchy_lines_from_original_clause(oc))
            if head in seen_articles and head:
                continue
            if head:
                seen_articles.add(head)
            picked.append(cr)
            if len(picked) >= 5:
                break
        if not picked:
            pnone_top = _p(body)
            _t(_r(pnone_top), "- 치명적 리스크 Top 3를 자동 선정할 충분한 근거가 부족합니다.")
        else:
            for cr in picked:
                cid = str(cr.get("clause_id") or "")
                oc = orig_by_id.get(cid) or {}
                head = " / ".join(_clause_hierarchy_lines_from_original_clause(oc)) or cid
                issues = cr.get("detected_issue_list") if isinstance(cr.get("detected_issue_list"), list) else []
                it = ""
                for x in issues:
                    if isinstance(x, dict) and bool(x.get("summary_suppress")):
                        continue
                    if isinstance(x, dict) and isinstance(x.get("issue_title"), str) and x["issue_title"].strip():
                        it = x["issue_title"].strip()
                        break
                rr = str(cr.get("rewrite_reason") or "").strip()
                risk1 = it or (rr[:90] if rr else "리스크/보완 필요")
                sr = str(cr.get("suggested_rewrite") or "").strip()
                if "[추가]" in sr:
                    sr = sr.split("[추가]", 1)[1].strip()
                sr = (sr[:220] + "…") if len(sr) > 220 else sr
                p1 = _p(body)
                _t(_r(p1), f"- 조항: {head}")
                p2 = _p(body)
                _t(_r(p2), f"  리스크: {risk1}")
                p3 = _p(body)
                _t(_r(p3), f"  수정 제안: {sr if sr else '(제안 문안 없음)'}")
        _p(body)
    if show_ids:
        ph = _p(body)
        _t(_r(ph, bold=True), "핵심 리스크 요약:")
        shown = 0
        for cid in show_ids:
            cr = cr_by_id.get(cid) or {}
            oc = orig_by_id.get(cid) or {}
            head = " / ".join(_clause_hierarchy_lines_from_original_clause(oc))
            issues = cr.get("detected_issue_list") if isinstance(cr.get("detected_issue_list"), list) else []
            it = ""
            for x in issues:
                if isinstance(x, dict) and bool(x.get("summary_suppress")):
                    continue
                rid0 = str(x.get("rule_id") or "") if isinstance(x, dict) else ""
                if is_dealer_contract and str(jur_kind or "") == "domestic_korea" and rid0 == "ACT-004" and not bool(cr.get("user_focus_hit")):
                    continue
                if isinstance(x, dict) and isinstance(x.get("issue_title"), str) and x["issue_title"].strip():
                    it = x["issue_title"].strip()
                    break
            rr = cr.get("rewrite_reason")
            line = f"- {head}: {it or (str(rr)[:60] if isinstance(rr, str) else '리스크/보완 필요')}"
            pl = _p(body)
            _t(_r(pl), line)
            shown += 1
            if shown >= 8:
                break
    _p(body)

    sec_issues = _p(body)
    _t(_r(sec_issues, bold=True), "2) 핵심 쟁점 요약")
    if isinstance(review_summary, dict) and isinstance(review_summary.get("issue_count"), int):
        ps0 = _p(body)
        _t(_r(ps0), f"검출 이슈 수: {int(review_summary.get('issue_count') or 0)}")
    issue_titles: list[str] = []
    for cid in (show_ids if show_ids else orig_order)[:40]:
        cr = cr_by_id.get(cid)
        if not isinstance(cr, dict):
            continue
        issues = cr.get("detected_issue_list") if isinstance(cr.get("detected_issue_list"), list) else []
        for x in issues:
            if not isinstance(x, dict):
                continue
            if bool(x.get("summary_suppress")):
                continue
            rid0 = str(x.get("rule_id") or "")
            if is_dealer_contract and str(jur_kind or "") == "domestic_korea" and rid0 == "ACT-004" and not bool(cr.get("user_focus_hit")):
                continue
            if isinstance(x, dict) and isinstance(x.get("issue_title"), str) and x["issue_title"].strip():
                t = x["issue_title"].strip()
                if t not in issue_titles:
                    issue_titles.append(t)
            if len(issue_titles) >= 8:
                break
        if len(issue_titles) >= 8:
            break
    if issue_titles:
        for t in issue_titles:
            pl = _p(body)
            _t(_r(pl), f"- {t}")
    else:
        pnone2 = _p(body)
        _t(_r(pnone2), "자동으로 확정적인 수정 권고 조항은 탐지되지 않았습니다.")
    _p(body)

    focus_items = frc0.get("user_focus_issues") if isinstance(frc0.get("user_focus_issues"), list) else []
    focus_titles = [
        str(x.get("title") or x.get("code") or "").strip()
        for x in focus_items
        if isinstance(x, dict) and str(x.get("title") or x.get("code") or "").strip()
    ]
    sec_focus = _p(body)
    _t(_r(sec_focus, bold=True), "2-1) 사용자 요청 핵심 이슈 반영 결과")
    if focus_titles:
        pf0 = _p(body)
        _t(_r(pf0), "요청 이슈: " + " / ".join(focus_titles[:8]))
    else:
        pf0 = _p(body)
        _t(_r(pf0), "요청 이슈: (입력 없음)")
    focus_hits = [cr for cr in clause_results if isinstance(cr, dict) and bool(cr.get("user_focus_hit"))]
    if focus_hits:
        pf1 = _p(body)
        _t(_r(pf1), f"관련 조항: {len(focus_hits)}개")
        for cr in focus_hits[:5]:
            cid = str(cr.get("clause_id") or "")
            oc = orig_by_id.get(cid) or {}
            head = " / ".join(_clause_hierarchy_lines_from_original_clause(oc))
            mt = cr.get("user_focus_match_titles") if isinstance(cr.get("user_focus_match_titles"), list) else []
            mt = [str(x) for x in mt if isinstance(x, str) and x.strip()]
            line = f"- {head}" + (f" (연결: {', '.join(mt[:2])})" if mt else "")
            pl = _p(body)
            _t(_r(pl), line)
    else:
        pf1 = _p(body)
        _t(_r(pf1), "관련 조항: (탐지 없음)")
    if focus_titles:
        for obj in focus_items[:8]:
            if not isinstance(obj, dict):
                continue
            code0 = str(obj.get("code") or "").strip()
            title0 = str(obj.get("title") or obj.get("code") or "").strip()
            if not code0 or not title0:
                continue
            ids = [str(cr.get("clause_id") or "") for cr in clause_results if isinstance(cr, dict) and code0 in (cr.get("user_focus_matches") or [])]
            if not ids:
                pl = _p(body)
                _t(_r(pl), f"- {title0}: (후보 조항 없음)")
                continue
            labels = []
            for cid in ids[:6]:
                oc = orig_by_id.get(cid) or {}
                labels.append(" / ".join(_clause_hierarchy_lines_from_original_clause(oc)) or cid)
            pl = _p(body)
            _t(_r(pl), f"- {title0}: " + " · ".join(labels[:6]))
    _p(body)

    sec_ans = _p(body)
    _t(_r(sec_ans, bold=True), "2-2) 질문 답변 반영 요약")
    ans0 = dict(answers or {})
    def _answer_label(q: dict[str, Any], value: Any) -> str:
        if value is None:
            return ""
        v = str(value)
        opts = q.get("options") if isinstance(q.get("options"), list) else []
        for o in opts:
            if isinstance(o, dict) and str(o.get("value") or "") == v:
                lab = str(o.get("label") or "").strip()
                return lab or v
        return v
    answered_lines: list[str] = []
    for q in questions or []:
        if not isinstance(q, dict) or not isinstance(q.get("question_id"), str):
            continue
        qid = str(q.get("question_id") or "")
        if qid not in ans0:
            continue
        val = ans0.get(qid)
        if not (isinstance(val, str) and val.strip()) and not isinstance(val, (bool, int, float)):
            continue
        title0 = str(q.get("title") or qid).strip()
        answered_lines.append(f"- {title0}: {_answer_label(q, val)}")
        if len(answered_lines) >= 10:
            break
    if answered_lines:
        for line in answered_lines:
            pl = _p(body)
            _t(_r(pl), line)
    else:
        pnone_ans = _p(body)
        _t(_r(pnone_ans), "- (답변 없음)")
    _p(body)

    sec_major = _p(body)
    _t(_r(sec_major, bold=True), "3) 검토된 주요 조항")
    for cid in orig_order[:10]:
        oc = orig_by_id.get(cid) or {}
        head = " / ".join(_clause_hierarchy_lines_from_original_clause(oc))
        pl = _p(body)
        _t(_r(pl), f"- {head}")
    _p(body)

    sec_reco = _p(body)
    _t(_r(sec_reco, bold=True), "4) 수정 권고 조항")
    if show_ids:
        for cid in show_ids[:18]:
            oc = orig_by_id.get(cid) or {}
            tier = tier_by_id.get(cid)
            base = " / ".join(_clause_hierarchy_lines_from_original_clause(oc))
            head = ((f"[{tier}] " if tier else "") + base).strip()
            pl = _p(body)
            _t(_r(pl), f"- {head}")
    else:
        pnone3 = _p(body)
        _t(_r(pnone3), "수정 권고 조항이 없습니다.")
    _p(body)

    sec_red = _p(body)
    _t(_r(sec_red, bold=True), "5) 본문 redline 버전 (필수수정 조항만 표시)")
    if not redline_ids:
        pnone = _p(body)
        _t(_r(pnone), "필수수정(redline) 조항이 없습니다.")
    for cid in redline_ids:
        oc = orig_by_id.get(cid) or {}
        cr = cr_by_id.get(cid) or {}
        tier = tier_by_id.get(cid) or "HIGH"
        head_lines = _clause_hierarchy_lines_from_original_clause(oc)
        if head_lines:
            head_lines[0] = (f"[{tier}] " + head_lines[0]).strip()
        for i, line in enumerate(head_lines or [f"[{tier}] {str(oc.get('clause_id') or '')}".strip()]):
            ph = _p(body)
            _t(_r(ph, bold=True), (("  " + line) if i > 0 else line))

        original_text = str(oc.get("text") or "")
        revised_text = str(cr.get("suggested_rewrite") or "")
        ctx = str(oc.get("context_text") or "").strip() if isinstance(oc.get("context_text"), str) else ""
        if ctx:
            pc = _p(body)
            rr = _r(pc, color_hex="666666")
            _t(rr, ctx[:700] + ("…" if len(ctx) > 700 else ""))
        pr = _p(body)
        for text, style in _diff_runs(original_text, revised_text):
            rr = _r(
                pr,
                bold=bool(style.get("bold")),
                underline=bool(style.get("underline")),
                strike=bool(style.get("strike")),
                color_hex=style.get("color_hex"),
                highlight=style.get("highlight"),
            )
            _t(rr, text)
        _p(body)

    sec_guid = _p(body)
    _t(_r(sec_guid, bold=True), "6) 조항별 검토 의견 (guidance)")
    if not guide_ids:
        pnoneg = _p(body)
        _t(_r(pnoneg), "권장/참고 조항이 없습니다.")
        _p(body)
    for cid in guide_ids:
        oc = orig_by_id.get(cid) or {}
        cr = cr_by_id.get(cid) or {}
        tier = tier_by_id.get(cid) or "MEDIUM"
        head_lines = _clause_hierarchy_lines_from_original_clause(oc)
        if head_lines:
            head_lines[0] = (f"[{tier}] " + head_lines[0]).strip()
        for i, line in enumerate(head_lines or [f"[{tier}] {str(oc.get('clause_id') or '')}".strip()]):
            ph = _p(body)
            _t(_r(ph, bold=True, color_hex="1F7AE0"), (("  " + line) if i > 0 else line))
        rr0 = str(cr.get("rewrite_reason") or "").strip()
        dirs0 = cr.get("suggested_direction") if isinstance(cr.get("suggested_direction"), list) else []
        ot0 = str(oc.get("text") or "")
        sr0 = str(cr.get("suggested_rewrite") or "").strip()
        laws0 = _extract_law_titles(cr, limit=3)
        before_k, _ = _key_phrases(ot0, sr0, limit=2)

        # [Article Review] 통합 코멘트 출력 (지침 4: 포괄적 리스크 범주화)
        arc = str(cr.get("article_review_comment") or "").strip()
        if arc and bool(cr.get("article_review_anchor")):
            parc = _p(body)
            _t(_r(parc, bold=True, color_hex="7B2D8B"), arc[:400])

        # 참조 메시지 출력 (지침 2: 대표 항 외 나머지 항)
        if bool(cr.get("dedup_suppressed")) and bool(cr.get("article_review_ref")):
            ref_id = str(cr.get("article_review_ref") or "")
            pref = _p(body)
            _t(_r(pref, color_hex="888888"),
               "→ " + ref_id + " 조항의 수정안과 동일한 리스크. 통합 관리 필요.")
            _p(body)
            continue

        if dirs0:
            p1 = _p(body)
            _t(_r(p1, color_hex="1F7AE0"), "방향: " + " / ".join(str(x) for x in dirs0 if isinstance(x, str) and x.strip())[:180])
        if before_k:
            p0b = _p(body)
            _t(_r(p0b, color_hex="1F7AE0"), "원문 핵심: " + before_k[:220] + ("…" if len(before_k) > 220 else ""))
        if sr0:
            # 인라인 수정 여부 표시 (지침 3)
            inline_label = " [인라인 수정]" if bool(cr.get("dedup_inline")) else ""
            p3 = _p(body)
            _t(_r(p3, color_hex="1F7AE0"), "제안 문안" + inline_label + ":")
            for line in sr0.splitlines()[:40]:
                pl = _p(body)
                _t(_r(pl, color_hex="1F7AE0"), (line[:260] + ("…" if len(line) > 260 else "")) if line else "")
        if rr0:
            p2 = _p(body)
            _t(_r(p2, color_hex="1F7AE0"), "사유: " + rr0[:320] + ("…" if len(rr0) > 320 else ""))
        if laws0:
            p4 = _p(body)
            _t(_r(p4, color_hex="1F7AE0"), "관련 법령/기준: " + " / ".join(laws0))
        _p(body)

    chk_items = [x for x in (checklist_items or []) if isinstance(x, dict)]
    if chk_items:
        sec_chk = _p(body)
        _t(_r(sec_chk, bold=True), "6-1) 추가 권고 (누락 구조 탐지)")
        for item in chk_items:
            name = str(item.get("clause_title") or "").strip()
            direction = str(item.get("rewrite_reason") or "").strip()
            rec = str(item.get("recommendation_text") or "").strip()
            risk = str(item.get("risk_tier") or "MEDIUM").upper()
            pn = _p(body)
            _t(_r(pn, bold=True, color_hex="b45309"), f"[{risk}] {name}")
            if direction:
                pd = _p(body)
                _t(_r(pd, color_hex="b45309"), "방향: " + direction[:300])
            if rec:
                pr = _p(body)
                _t(_r(pr, color_hex="b45309"), "[추가 권고]")
                for line in rec.splitlines()[:15]:
                    pl = _p(body)
                    _t(_r(pl, color_hex="b45309"), (line[:260] + "…" if len(line) > 260 else line) if line.strip() else "")
            _p(body)

    sec_app = _p(body)
    _t(_r(sec_app, bold=True), "7) 조항별 구체적 수정안 부록")
    tbl = _tbl(body, col_widths=[1100, 1700, 2600, 2200, 1500])

    def add_row(cells: list[list[tuple[str, dict[str, Any]]]]) -> None:
        tr = ET.SubElement(tbl, _w("tr"))
        for i, paras in enumerate(cells):
            tc = _tc(tr, width=int([1200, 1800, 1800, 2400, 1600][i] if i < 5 else 1800))
            for text, style in paras:
                pp = _p(tc)
                rr = _r(
                    pp,
                    bold=bool(style.get("bold")),
                    underline=bool(style.get("underline")),
                    strike=bool(style.get("strike")),
                    color_hex=style.get("color_hex"),
                    highlight=style.get("highlight"),
                )
                _t(rr, text)

    add_row(
        [
            [("조항 위치", {"bold": True})],
            [("원문 핵심 표현", {"bold": True})],
            [("제안 문안", {"bold": True})],
            [("수정 이유", {"bold": True})],
            [("관련 법령/기준", {"bold": True})],
        ]
    )
    if not show_ids:
        add_row(
            [
                [("부록 대상 없음", {})],
                [("-", {})],
                [("-", {})],
                [("-", {})],
                [("-", {})],
            ]
        )
    for cid in show_ids:
        oc = orig_by_id.get(cid) or {}
        cr = cr_by_id.get(cid) or {}
        tier = tier_by_id.get(cid) or "MEDIUM"
        left_lines = _clause_hierarchy_lines_from_original_clause(oc)
        if left_lines:
            left_lines[0] = (f"[{tier}] " + left_lines[0]).strip()
        left_paras = [(line if i == 0 else ("  " + line), {}) for i, line in enumerate(left_lines)] or [
            (f"[{tier}] {str(oc.get('clause_id') or '')}".strip(), {})
        ]

        original_text = str(oc.get("text") or "")
        revised_text = str(cr.get("suggested_rewrite") or "")
        rr = str(cr.get("rewrite_reason") or "").strip() if isinstance(cr.get("rewrite_reason"), str) else ""
        laws = _extract_law_titles(cr, limit=3)
        before_k, _ = _key_phrases(original_text, revised_text, limit=2)
        proposed_lines = [(line[:320] + ("…" if len(line) > 320 else ""), {}) for line in revised_text.splitlines()[:18] if line.strip()]
        if not proposed_lines:
            proposed_lines = [("(제안 문안 없음)", {})]

        add_row(
            [
                left_paras,
                [(before_k, {})],
                proposed_lines,
                [(rr[:260] + ("…" if len(rr) > 260 else ""), {})] if rr else [("(사유 없음)", {})],
                [(" / ".join(laws), {})] if laws else [("-", {})],
            ]
        )

    sec_hr = _p(body)
    _t(_r(sec_hr, bold=True), "8) High risk / Approval required 표")
    tbl2 = _tbl(body, col_widths=[1200, 4200, 1200])

    def add_row2(cells: list[tuple[str, dict[str, Any]]]) -> None:
        tr = ET.SubElement(tbl2, _w("tr"))
        widths = [1200, 4200, 1200]
        for i, (text, style) in enumerate(cells):
            tc = _tc(tr, width=int(widths[i] if i < len(widths) else 2000))
            pp = _p(tc)
            rr = _r(pp, bold=bool(style.get("bold")))
            _t(rr, text)

    add_row2([("조항", {"bold": True}), ("제목", {"bold": True}), ("표시", {"bold": True})])
    for cid in show_ids:
        cr = cr_by_id.get(cid) or {}
        if not (bool(cr.get("high_risk")) or bool(cr.get("approval_required"))):
            continue
        title_txt = " / ".join(_clause_hierarchy_lines_from_original_clause((orig_by_id.get(cid) or {})))
        flag = []
        if bool(cr.get("high_risk")):
            flag.append("HIGH")
        if bool(cr.get("approval_required")):
            flag.append("APPROVAL")
        add_row2([(cid, {}), (title_txt, {}), ("/".join(flag), {"bold": True})])

    ET.SubElement(body, _w("sectPr"))
    document_xml = ET.tostring(doc, encoding="utf-8", xml_declaration=True)

    types_root = ET.Element(f"{{{PKG_TYPES_NS}}}Types")
    d1 = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Default")
    d1.set("Extension", "rels")
    d1.set("ContentType", "application/vnd.openxmlformats-package.relationships+xml")
    d2 = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Default")
    d2.set("Extension", "xml")
    d2.set("ContentType", "application/xml")
    ov = ET.SubElement(types_root, f"{{{PKG_TYPES_NS}}}Override")
    ov.set("PartName", "/word/document.xml")
    ov.set("ContentType", "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml")
    content_types = ET.tostring(types_root, encoding="utf-8", xml_declaration=True)

    rels_root = ET.Element(f"{{{REL_NS}}}Relationships")
    rel = ET.SubElement(rels_root, f"{{{REL_NS}}}Relationship")
    rel.set("Id", "rId1")
    rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument")
    rel.set("Target", "word/document.xml")
    rels = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)

    buf = BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()
