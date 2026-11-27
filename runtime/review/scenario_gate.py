"""계약 전체 상황별 검증 게이트 — 조항 지목 요청 검토(requested_clause_review)의 수정안을 모두 넣은 계약으로 판단한다.

수정안은 요청마다 따로 만들어진다(9.9 보험·면책은 요청 4, 10.1 지식재산 면책은 내부 지적 재검토, 13.4 종료 후 처리와
4.1 로열티 존속은 요청 6). 각각은 그럴듯해도 합치면 같은 위험을 반대로 정하거나(한 조항은 '책임 없음', 다른 조항은
'책임 있음'), 무상 A/S 에 로열티가 붙는 일이 생긴다. 여기서는:

1. 모든 살아 있는 수정안을 원문에 넣어 수정 후 계약 지도를 만들고 deal_scenarios.evaluate 로 상황별 결과를 계산한다.
2. 고칠 문제(block·fix)가 있으면 관련 요청들의 수정안을 한 번에 AI 에 되돌려 함께 고치게 한다(최대 2회) — 고친 수정안도
   requested_clause_review.verify_edit 로 다시 검증한다.
3. 그래도 남은 block(의미 역전·충돌·새 부담)은 그 조항의 수정안을 보류한다(출력 차단 — 법무 추가 확인 중으로 표시).
   남은 fix 는 그 요청의 measure_gaps 로 남겨 '부분 반영' 과 ⚠ 표시가 되게 한다.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from runtime.review.deal_scenarios import Parties, evaluate

logger = logging.getLogger(__name__)


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", _s(s)).strip()


def _attr(c: Any, name: str) -> str:
    return _s(c.get(name) if isinstance(c, dict) else getattr(c, name, ""))


def _new_path(num: str, location: str) -> str:
    if num:
        return f"Article {num}" if re.match(r"^\d", num) else num
    m = re.search(r"(?:Article|Section|Clause)\s+\d+(?:\.\d+)*|제\s*\d+\s*조(?:의\s*\d+)?(?:\s*제\s*\d+\s*항)?", location or "")
    return m.group(0) if m else (location or "신설 조항")


def original_map(clauses: list[Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in clauses or []:
        p = _attr(c, "display_path")
        t = _ws(_attr(c, "text"))
        if p and t:
            out[p] = (out[p] + " " + t) if p in out and t not in out[p] else t
    return out


def _apply(text: str, target: str, replacement: str, mode: str) -> str:
    t = _ws(target)
    if not t:
        return text
    if t not in text:
        return text
    if mode == "delete":
        return _ws(text.replace(t, "", 1))
    if mode == "insert_after":
        return text.replace(t, f"{t} {_ws(replacement)}", 1)
    return text.replace(t, _ws(replacement), 1)


def clause_maps_from_results(clauses: list[Any] | None, clause_results: list[dict[str, Any]],
                             applied_ids: set[str] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """검토 결과(finding)의 살아 있는 수정안으로 수정 전/후 지도 — 화면·다운로드에 실린 것과 같은 수정안만."""
    orig = original_map(clauses)
    rev = dict(orig)
    for cr in clause_results or []:
        if not isinstance(cr, dict) or cr.get("dedup_suppressed") or cr.get("keep_as_is") or not cr.get("has_rewrite_change"):
            continue
        if applied_ids is not None and _s(cr.get("clause_id")) not in applied_ids:
            continue
        ri = cr.get("redline_instruction") if isinstance(cr.get("redline_instruction"), dict) else {}
        if ri.get("held"):
            continue
        path = _s(cr.get("display_path"))
        if ri.get("edit_mode") == "new_paragraph" or (ri.get("edit_type") == "insert_after" and not ri.get("target_text")):
            np = _new_path(_s(ri.get("new_paragraph_number")), _s(ri.get("edit_location")))
            rev[np] = _ws(_s(ri.get("replacement_text") or cr.get("suggested_rewrite")))
            continue
        tgt = _s(ri.get("target_text"))
        repl = _s(ri.get("replacement_text"))
        if tgt and path in rev:
            mode = "replace"   # replacement_text 는 이미 insert_after 를 "원문 + 덧붙임" 으로 풀어 둔 값이다
            rev[path] = _apply(rev[path], tgt, repl, mode) if repl or ri.get("edit_mode") == "delete" else rev[path]
        elif _s(cr.get("suggested_rewrite")).strip() and path:
            rev[path] = _ws(_s(cr.get("suggested_rewrite")))
    return orig, rev


def _edit_path(e: Any, r: Any) -> str:
    from runtime.review.requested_clause_review import _host_for

    if e.mode == "new_paragraph":
        return _new_path(e.new_paragraph_number, "")
    host = _host_for(e, list(r.targets) + list(r.context))
    return _attr(host, "display_path")


def maps_from_reviews(clauses: list[Any] | None, reviews: list[Any]) -> tuple[dict[str, str], dict[str, str], dict[str, list[tuple[Any, Any]]]]:
    """요청 검토(RequestedReview)의 살아 있는 수정안으로 수정 전/후 지도와 {조항: [(검토, 수정안)]}."""
    orig = original_map(clauses)
    rev = dict(orig)
    owners: dict[str, list[tuple[Any, Any]]] = {}
    for r in reviews:
        if not r.data or not r.targets or _s(r.data.get("action_type")).strip() in ("사업부 결정", "현행 유지"):
            continue
        for e in r.edits:
            if e.held:
                continue
            p = _edit_path(e, r)
            if not p:
                continue
            owners.setdefault(p, []).append((r, e))
            if e.mode == "new_paragraph":
                rev[p] = _ws(e.new_text)
            else:
                rev[p] = _apply(rev.get(p, ""), e.target_text, e.new_text, e.mode)
    return orig, rev, owners


def _descriptions(owners: dict[str, list[tuple[Any, Any]]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p, pairs in owners.items():
        ds = []
        for r, _e in pairs:
            d = " ".join(_s(r.data.get(k)) for k in ("action",))
            if d and d not in ds:
                ds.append(d)
        out[p] = " ".join(ds)
    return out


_REPAIR_SYSTEM = """너는 우리 회사 사내변호사 책임자다. 같은 계약의 여러 수정안을 모두 넣은 결과를 코드가 상황별로 검증했더니 아래 문제가 나왔다.
관련 요청들의 수정안을 함께 고쳐, 계약 전체에서 책임·권리·비용이 의도대로 나오게 하라.

원칙
- 같은 위험(제3자 청구·지식재산 침해·제조물책임 등)을 다루는 배상·면책·보증·보험 조항은 하나의 체계로 정리한다: 누가 / 누구에게 /
  어떤 원인으로 / 어떤 책임을 / 어떤 예외·한도로. 두 조항이 같은 상황을 반대로 정하면 한 조항이 다른 조항을 'subject to' 또는
  'notwithstanding' 으로 가리키게 하거나 원인 범위를 맞춘다. 우리 제공 사양이 원인인 지식재산 침해처럼 우리가 책임지기로 한 원인을
  다른 조항의 '책임 없음' 목록에서 지우지 말고 예외로 명시한다.
- 일반 과실과 고의·중과실을 구분해 쓴다. 상대방 귀책·상대방 디자인/지식재산 원인 손해는 우리 책임에서 뺀다.
- 책임한도를 두면 (1) 건당 한도와 누적(연간 또는 계약 전체) 한도를 구분하고 (2) 방어비용·변호사비용·배상·면책 금액 전부에 적용되는지
  (3) 보호대상자(계열사·임직원 등) 전원에 대한 책임에 적용되는지 문구로 정한다. 금액이 합의되지 않았으면 [●].
- 연장: 요청이 '위반이 없으면 연장' 이면 상대방 동의 없이 연장되게 쓴다 — 연장권자(또는 자동 연장), 행사 방식·기한, 연장 기간·조건,
  연장을 막을 수 있는 위반(중대한 위반)과 시정절차(서면 통지 후 시정기간 내 미시정), '추가 동의 불필요' 를 모두 적는다.
  '양 당사자 동의' 나 '동의를 부당하게 거절하지 못함' 만으로는 반영된 것이 아니다.
- 종료 후 활동(확정 주문 납품·재고 판매·A/S): 활동별로 기간·대상·필요한 사용권·정산/보고 의무를 나눠 적는다. 로열티는 판매분에만 —
  무상 보증수리·부품 보관·무상 부품 공급에는 로열티가 없다고 명시한다. 종료 후 판매한 제품의 A/S 도 허용하고, A/S 사용권은 해당 제품의
  보증의무가 끝날 때까지 존속시킨다(보증보다 짧은 고정 상한 금지). 기존 지역·표시 제한(예: 특정 지역에서 특정 표시 사용 금지)은 종료 후에도
  그대로 적용된다고 적는다. 만료와 중도해지(사유별) 가운데 어디에 적용되는지 적는다.
- 사용자가 주지 않은 기간·금액(통지기간·시정기간 등)은 [●] 로 두고, 제안값은 undecided 에 "제안값: 30 days(법무 제안, 미합의)" 처럼 적는다.
- 고칠 문장(target_text)은 그 요청이 볼 수 있는 조항 원문(아래 [조항 원문])에서 글자 그대로 복사한다. 새 항은 mode=new_paragraph.
- 한글 설명(action·risk_to_us)과 수정 문구의 책임 방향이 같아야 한다. 부정문·예외(except, unless, not)로 방향이 뒤집히지 않게 한다.
- 요청과 무관한 합의조건(금액·비율·기간)은 바꾸지 않는다. 계약 정의어를 쓴다.

JSON 하나만: {"reviews": [{"key": "...", "action": "필요한 조치(한국어)", "risk_to_us": "...",
  "edits": [{"mode": "replace|insert_after|new_paragraph|delete", "target_text": "...", "new_text": "...", "new_paragraph_number": "",
             "undecided": ["..."], "changed_terms": []}],
  "measures": [{"measure": "...", "edit_index": 0, "not_reflected_reason": ""}]}]}
문제와 무관한 요청은 reviews 에 넣지 않는다. 넣은 요청의 edits 는 그 요청의 수정안 전체를 대신한다(고치지 않을 수정안도 그대로 다시 적는다)."""


def _involved(problems: list[dict[str, Any]], reviews: list[Any], owners: dict[str, list[tuple[Any, Any]]]) -> list[Any]:
    out: list[Any] = []
    for p in problems:
        for path in p.get("paths") or []:
            for r, _e in owners.get(path, []):
                if r not in out:
                    out.append(r)
            if not owners.get(path):
                # 아무 수정안도 없는 조항(원문 그대로)과의 충돌 — 그 조항을 지목·참조한 검토가 고친다
                for r in reviews:
                    if r in out or not r.data:
                        continue
                    if path in [_attr(c, "display_path") for c in list(r.targets) + list(r.context)]:
                        out.append(r)
                        break
    return out


def _repair(provider: Any, *, model: str, problems: list[dict[str, Any]], involved: list[Any], revised: dict[str, str],
            facts: str, timeout_sec: float, max_tokens: int) -> dict[str, Any] | None:
    from runtime.review.requested_clause_review import _build_request, _try_json

    paths = sorted({p for x in problems for p in x.get("paths") or []})
    rows = []
    for r in involved:
        rows.append({
            "key": str(r.block.index),
            "request": r.block.text[:1500],
            "clauses_visible": [_attr(c, "display_path") for c in list(r.targets) + list(r.context)],
            "action": _s(r.data.get("action")), "risk_to_us": _s(r.data.get("risk_to_us")),
            "edits": [{"mode": e.mode, "target_text": e.target_text, "new_text": e.new_text,
                       "new_paragraph_number": e.new_paragraph_number, "undecided": e.undecided} for e in r.edits if not e.held],
        })
    src = []
    seen: set[str] = set()
    for r in involved:
        for c in list(r.targets) + list(r.context):
            p = _attr(c, "display_path")
            if p and p not in seen:
                seen.add(p)
                src.append(f"[{p}] {_ws(_attr(c, 'text'))}")
    user = ("[거래 사실]\n" + facts + "\n\n[코드 검증 문제]\n- " + "\n- ".join(f"({p['code']}) {p['message']}" for p in problems)
            + "\n\n[현재 수정안을 모두 넣은 조항(문제 조항)]\n" + "\n".join(f"[{p}] {revised.get(p, '(없음)')}" for p in paths)
            + "\n\n[관련 요청과 현재 수정안]\n" + json.dumps(rows, ensure_ascii=False, indent=1)
            + "\n\n[조항 원문 — target_text 는 여기서 글자 그대로]\n" + "\n\n".join(src))
    try:
        resp = provider.complete(_build_request(model=model, system=_REPAIR_SYSTEM, user=user, timeout_sec=timeout_sec,
                                                max_tokens=max_tokens, temperature=0.1))
        out = _try_json(getattr(resp, "content", "") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("scenario repair call failed: %s", exc)
        return None
    return out if isinstance(out, dict) else None


def run_scenario_gate(
    *,
    reviews: list[Any],
    clauses: list[Any] | None,
    contract_text: str,
    parties: Parties,
    request_text: str,
    answers_text: str,
    provider: Any = None,
    model: str = "",
    facts: str = "",
    timeout_sec: float = 150.0,
    max_tokens: int = 6000,
    rounds: int = 2,
) -> dict[str, Any]:
    from runtime.review.requested_clause_review import _is_latin, verify_edit

    latin = _is_latin(contract_text[:20000])
    log: list[dict[str, Any]] = []
    orig, rev, owners = maps_from_reviews(clauses, reviews)
    res = evaluate(original=orig, revised=rev, parties=parties, request_text=request_text, answers_text=answers_text,
                   descriptions=_descriptions(owners))
    first = [p["code"] for p in res["to_fix"]]
    for n in range(rounds):
        todo = res["to_fix"]
        if not todo or provider is None:
            break
        involved = _involved(todo, reviews, owners)
        if not involved:
            break
        out = _repair(provider, model=model, problems=todo, involved=involved, revised=rev, facts=facts,
                      timeout_sec=timeout_sec, max_tokens=max_tokens)
        if not out:
            log.append({"round": n + 1, "result": "AI 응답 없음"})
            break
        by_key = {str(r.block.index): r for r in involved}
        changed: list[str] = []
        backup = {k: (r.edits, dict(r.data)) for k, r in by_key.items()}
        for item in out.get("reviews") or []:
            r = by_key.get(_s(item.get("key")))
            if r is None or not isinstance(item.get("edits"), list):
                continue
            joined = "\n".join(_attr(c, "text") for c in list(r.targets) + list(r.context))
            new_edits = [verify_edit(e, clause_text=joined, contract_text=contract_text, request_text=r.block.text,
                                     answers_text=answers_text, latin=latin)
                         for e in item["edits"] if isinstance(e, dict)]
            if not new_edits or sum(e.held for e in new_edits) > sum(e.held for e in r.edits):
                continue
            r.edits = new_edits
            for k in ("action", "risk_to_us"):
                if _s(item.get(k)).strip():
                    r.data[k] = _s(item.get(k)).strip()
            if isinstance(item.get("measures"), list):
                r.data["measures"] = item["measures"]
            r.data["_repaired"] = list(r.data.get("_repaired") or []) + [f"[계약 전체 검증] {p['message']}" for p in todo
                                                                          if set(p["paths"]) & set(_paths_of(r))]
            changed.append(str(r.block.index))
        orig2, rev2, owners2 = maps_from_reviews(clauses, reviews)
        res2 = evaluate(original=orig2, revised=rev2, parties=parties, request_text=request_text, answers_text=answers_text,
                        descriptions=_descriptions(owners2))
        # 고친 결과가 오히려 나빠지면(막아야 할 문제가 늘면) 되돌린다
        if len(res2["blocking"]) > len(res["blocking"]) or (len(res2["to_fix"]) > len(res["to_fix"])):
            for k, (edits, data) in backup.items():
                by_key[k].edits, by_key[k].data = edits, data
            log.append({"round": n + 1, "changed": changed, "result": "개선되지 않아 되돌림",
                        "after": [p["code"] for p in res2["to_fix"]]})
            break
        log.append({"round": n + 1, "changed": changed, "before": [p["code"] for p in todo],
                    "after": [p["code"] for p in res2["to_fix"]]})
        orig, rev, owners, res = orig2, rev2, owners2, res2
    # 남은 block → 그 조항 수정안 보류(출력 차단), 남은 fix → 요청의 measure_gaps
    held: list[dict[str, Any]] = []
    for p in res["blocking"]:
        for path in p["paths"]:
            for r, e in owners.get(path, []):
                if e.held:
                    continue
                e.held, e.hold_reason = True, f"계약 전체 검증 미통과 — {p['message']}"
                held.append({"request": r.block.index, "path": path, "code": p["code"]})
    for p in res["problems"]:
        if p["severity"] != "fix":
            continue
        for path in p["paths"]:
            for r, _e in owners.get(path, []):
                gaps = list(r.data.get("_measure_gaps") or [])
                if p["message"] not in gaps:
                    gaps.append(p["message"])
                r.data["_measure_gaps"] = gaps
                r.data["_scenario_open"] = True
    if held:
        orig, rev, owners = maps_from_reviews(clauses, reviews)
        res = evaluate(original=orig, revised=rev, parties=parties, request_text=request_text, answers_text=answers_text,
                       descriptions=_descriptions(owners))
    res["repair_log"] = log
    res["held_by_gate"] = held
    res["initial_codes"] = first
    res["revised_paths"] = sorted(p for p in rev if rev[p] != orig.get(p))
    return res


def _paths_of(r: Any) -> list[str]:
    out = [_attr(c, "display_path") for c in list(r.targets) + list(r.context)]
    for e in r.edits:
        if e.mode == "new_paragraph" and e.new_paragraph_number:
            out.append(_new_path(e.new_paragraph_number, ""))
    return out


def parties_from(entity_resolution: Any) -> Parties:
    ours, theirs = [], []
    for p in getattr(entity_resolution, "parties", []) or []:
        lab = _s(getattr(p, "label", ""))
        names = [x for x in (lab, _s(getattr(p, "written_name", ""))) if x and len(x) <= 40]
        (ours if getattr(p, "is_our_company", False) else theirs).extend(names)
    return Parties(ours=ours or ["Customer", "Licensee"], theirs=theirs or ["Supplier", "Licensor"])


__all__ = ["clause_maps_from_results", "maps_from_reviews", "original_map", "parties_from", "run_scenario_gate"]
