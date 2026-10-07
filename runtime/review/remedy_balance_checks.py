"""책임·제재의 균형 점검 — 계약유형과 무관한 법률효과 점검 3종 (2026-10-07 긴급 보정 5·6·8·11·12항).

실측(시디즈 ↔ ㈜비디앤에스 브랜디드 콘텐츠 제작 계약, 우리 = 갑·광고주):

    제13조 제1항  손해 "전부"(명성·이미지 포함) 배상 — 단, 을의 배상액만 제작료 한도.   → 비대칭 책임
    제14조        광고주 귀책(을의 판단 포함) → 을의 즉시 해지 + 제작료 50% 위약벌 + "이와 별도로" 모든
                  손해 + 게시 콘텐츠 삭제 + 잔여대금 지급의무 존속. 을 쪽 귀책에 대한 조치는 없음.
    제13조 제4항  같은 사유(광고주 물의)로 또 50% 위약벌.                                 → 제재 중첩
    제9조·제10조  콘텐츠 IP 는 을 단독 소유, 자체 채널·광고소재·숏폼 활용은 전부 별도 유상합의/금지
                  — 우리는 자체 채널·광고소재로 쓸 계획(사전질문 답변).

수정 전 결과: 제13조 비대칭은 "배상 상한 = 사업부 결정"으로 재경 확인에 갔고, 제14조는 DROP, HIGH 0건.

여기서 만드는 finding 은 모두 **법무 핵심 finding**(`legal_core`)이다 — 재경·사업 확인으로 보내지 않는다.
수정문은 새 조를 신설하지 않고 해당 조항을 직접 고친다(지시 14항).
"""
from __future__ import annotations

import re
from typing import Any

CODE_ASYMMETRIC = "LEGAL_RISK_ASYMMETRIC_LIABILITY"
CODE_STACKING = "REMEDY_STACKING_RISK"
CODE_CONTENT_USE = "LEGAL_RISK_CONTENT_USE_RIGHTS"

_Q = "[“”\"]"


def _attr(c: Any, name: str) -> str:
    if isinstance(c, dict):
        return str(c.get(name) or "")
    return str(getattr(c, name, "") or "")


def _flat(s: str) -> str:
    return re.sub(r"\s*\n\s*", " ", str(s or "")).strip()


def _lab(label: str) -> str:
    """약칭 정규식 — 따옴표 모양이 섞여 있다(“갑”, ”갑”, "갑”)."""
    return _Q + "?" + re.escape(label) + _Q + "?"


def _p(word: str, with_b: str, without_b: str) -> str:
    core = re.sub(r"[\s“”\"'()]+$", "", word or "")
    last = core[-1:] if core else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _q(label: str) -> str:
    return f"“{label}”"


def _short_labels(labels: list[str]) -> list[str]:
    """본문에서 따옴표로 쓰는 짧은 약칭만(“갑”, “광고주”)."""
    return [lb for lb in labels if lb and len(lb) <= 6 and not re.search(r"주식회사|㈜|\(주\)", lb)]


def _finding(anchor: Any, **kw: Any) -> dict[str, Any]:
    base = {
        "clause_title": _attr(anchor, "title"),
        "display_path": _attr(anchor, "display_path"),
        "article_number": _attr(anchor, "article_number"),
        "paragraph_number": _attr(anchor, "paragraph_number"),
        "original_text": _attr(anchor, "text"),
        "risk_tier": "HIGH", "severity": "HIGH", "must_fix": True, "review_tier": "MUST",
        "confidence": 0.97, "is_common_legal_risk": True, "is_transaction_package": True,
        # 지시 5항 — 법무 핵심 finding. 재경·사업부 확인으로 보내지 않는다.
        "legal_core": True,
    }
    base.update(kw)
    base.setdefault("rewrite_reason", base.get("problem", ""))
    base.setdefault("recommendation_text", base.get("suggested_rewrite", ""))
    base.setdefault("negotiation_strategy", base.get("negotiation_position", ""))
    return base


def _with_linked(problem: str, linked: list[dict[str, str]]) -> str:
    if not linked:
        return problem
    return problem + " [연계 수정] " + " / ".join(f"{e['display_path']}: {e['text']}" for e in linked)


# ── 1. 비대칭 책임 한도 (지시 11항) ─────────────────────────────────────────────

def find_asymmetric_liability(
    *, clauses: list[Any] | None, our: list[str], them: list[str],
) -> list[dict[str, Any]]:
    """상호 손해배상 조항에서 **상대방의 배상액만** 한도로 묶은 단서."""
    them_s = _short_labels(them)
    our_s = _short_labels(our)
    if not them_s or not our_s:
        return []
    out: list[dict[str, Any]] = []
    for c in clauses or []:
        t = _flat(_attr(c, "text"))
        if not re.search(r"손해", t) or not re.search(r"배상", t):
            continue
        for lb in them_s:
            m = re.search(r"단,?\s*" + _lab(lb) + r"의\s*손해배상(?:금액|액|책임)?(?:은|는)\s*([^.]{1,60}?)"
                          r"(?:를|을)?\s*(?:초과하지\s*(?:않|아니)|한도로)", t)
            if not m:
                continue
            if any(re.search(_lab(o) + r"의\s*손해배상(?:금액|액|책임)?(?:은|는)[^.]{0,60}(?:초과하지|한도)", t)
                   for o in our_s):
                continue  # 우리 쪽에도 한도가 있으면 대칭이다
            cap = m.group(1).strip()
            us = _q(our_s[0])
            th = _q(lb)
            broad = bool(re.search(r"명성|이미지|평판|전부\s*배상|모든\s*손해", t))
            original = _attr(c, "text").rstrip()
            new_proviso = (f"단, 각 당사자의 손해배상금액은 {cap}를 초과하지 않는다. 다만, 고의 또는 중대한 과실로 "
                           "인한 손해는 그러하지 아니하다.")
            proposal = re.sub(r"단,?\s*" + _lab(lb) + r"의\s*손해배상[^.]*\.", new_proviso, original, count=1)
            if proposal == original:
                proposal = f"{original} {new_proviso}"
            out.append(_finding(
                c,
                clause_id=f"lr_asymmetric_liability__{_attr(c, 'clause_id')}",
                legal_effect_code=CODE_ASYMMETRIC,
                problem=(f"상호 손해배상 조항인데 {_p(th, '의', '의')} 배상액만 {cap}로 한도가 있고 {_p(us, '은', '는')} 한도 없이 "
                         + ("명성·이미지 손해까지 포함한 손해 전부를 " if broad else "손해 전부를 ")
                         + "배상하도록 되어 있다. 같은 위반이라도 우리 회사의 책임만 무제한이다."),
                legal_business_reason=("손해배상 한도는 금액을 얼마로 할지의 사업 판단 이전에 '누구에게 한도를 주는가'의 "
                                       "권리 배분 문제다. 한쪽에만 한도를 두면 분쟁 시 우리 회사의 노출만 무제한으로 남는다."),
                high_severity_basis="우리 회사만 무제한 손해배상 부담(상대방만 책임 한도)",
                suggested_rewrite=proposal,
                negotiation_position=(f"한도를 없애기보다 같은 한도를 양쪽에 두는 것(상호주의)이 1순위입니다. "
                                      "고의·중과실은 양쪽 모두 한도에서 뺍니다."),
                # 손해배상을 정한 다른 조(비밀유지 위반 배상 등)의 "한도 없음" 지적도 같은 손실 시나리오다(지시 13항).
                package_articles=sorted({_attr(c, "article_number")} | {
                    _attr(x, "article_number") for x in clauses or []
                    if re.search(r"손해[^.]{0,30}배상", _flat(_attr(x, "text"))) and _attr(x, "article_number")}),
                package_pattern=r"한도|상한|무제한|불균형|비대칭|\bcap\b",
                detected_issue_list=[{"issue_title": "[책임 한도 비대칭] 상대방만 제작료 한도, 우리 회사는 무제한 손해배상"}],
            ))
            break
    return out


# ── 2. 상대방 일방 해지 + 제재 중첩 (지시 6·7·8항) ─────────────────────────────

def _by_article(clauses: list[Any] | None) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for c in clauses or []:
        a = _attr(c, "article_number")
        if a:
            out.setdefault(a, []).append(c)
    return out


def find_remedy_stacking(
    *, clauses: list[Any] | None, our: list[str], them: list[str], text: str = "",
) -> list[dict[str, Any]]:
    them_s = _short_labels(them)
    our_s = _short_labels(our)
    if not them_s or not our_s:
        return []
    th_rx = "(?:" + "|".join(_lab(x) for x in them_s) + ")"
    us_rx = "(?:" + "|".join(_lab(x) for x in our_s) + ")"
    th = _q(them_s[0])
    body = _flat(text)
    deliverable = "“콘텐츠”" if "“콘텐츠”" in body else "결과물"
    fee = "제작료" if "제작료" in body else "대금"
    out: list[dict[str, Any]] = []
    arts = _by_article(clauses)
    for art, cs in arts.items():
        joined = " ".join(_flat(_attr(c, "text")) for c in cs)
        term_c = next((c for c in cs if re.search(th_rx + r"(?:은|는)[^.]{0,60}(?:해제|해지)할\s*수\s*있", _flat(_attr(c, "text")))), None)
        pen_c = next((c for c in cs if re.search(r"위약벌", _attr(c, "text"))
                      and re.search(us_rx + r"(?:은|는)", _flat(_attr(c, "text")))), None)
        if term_c is None or pen_c is None:
            continue
        pen_t = _flat(_attr(pen_c, "text"))
        m_pct = re.search(r"(\d{1,3})\s*%[^.]{0,20}위약벌", pen_t)
        subj_c = next((c for c in cs if re.search(th_rx + r"의\s*판단", _flat(_attr(c, "text")))), None)
        del_c = next((c for c in cs if re.search(r"삭제할\s*수\s*있", _attr(c, "text"))), None)
        pay_c = next((c for c in cs if re.search(r"(?:잔여\s*대금|대금)[^.]{0,20}지급\s*의무를?\s*면하지", _flat(_attr(c, "text")))), None)
        checks = [
            {"check": "귀책사유가 객관적인가", "ok": subj_c is None,
             "detail": (f"{_attr(subj_c, 'display_path')} — {th}의 판단만으로 귀책사유가 됨" if subj_c else "객관적 사유")},
            {"check": f"{th}의 판단만으로 해지 가능한가", "ok": subj_c is None,
             "detail": "판단 기준이 상대방의 주관" if subj_c else ""},
            {"check": "시정기간·사전 협의가 있는가", "ok": bool(re.search(r"시정|최고|기간을\s*정하여|협의", _flat(_attr(term_c, "text")))),
             "detail": f"{_attr(term_c, 'display_path')} — 서면 통지로 즉시 해제·해지"},
            {"check": "갑·을 책임이 대칭적인가", "ok": False, "detail": ""},
            {"check": "위약벌이 있는가", "ok": m_pct is None,
             "detail": f"{_attr(pen_c, 'display_path')} — 제작료 {m_pct.group(1)}% 위약벌" if m_pct else "위약벌"},
            {"check": "별도 손해배상이 추가되는가", "ok": not re.search(r"별도로[^.]{0,30}(?:모든\s*)?손해", pen_t),
             "detail": "위약벌과 별도로 모든 손해 배상"},
            {"check": "콘텐츠·결과물 삭제권이 있는가", "ok": del_c is None,
             "detail": f"{_attr(del_c, 'display_path')} — 동의 없이 즉시 비공개·삭제" if del_c else ""},
            {"check": "삭제 후에도 잔여대금 지급의무가 남는가", "ok": pay_c is None,
             "detail": f"{_attr(pay_c, 'display_path')} — 잔여 대금 지급 의무 존속" if pay_c else ""},
        ]
        # 상대방 귀책에 대한 우리의 같은 권리가 있는가(대칭).
        reciprocal = bool(re.search(us_rx + r"(?:은|는)[^.]{0,80}(?:해제|해지)할\s*수\s*있[^.]{0,0}", body)
                          and re.search(th_rx + r"(?:\s*또는\s*[^.]{0,20})?의\s*(?:위법|부적절|물의|사회적\s*비난)", body))
        checks[3]["ok"] = reciprocal
        checks[3]["detail"] = "" if reciprocal else f"{th} 쪽 귀책(위법행위·논란)에 대한 우리 회사의 해지·환급 조치가 없음"
        failed = [x for x in checks if not x["ok"]]
        if len(failed) < 4:
            continue

        # 같은 사유로 다른 조에서도 위약벌을 지우는가(조를 넘는 제재 중첩).
        other_pen = [c for a2, cs2 in arts.items() if a2 != art for c in cs2
                     if re.search(r"위약벌", _attr(c, "text")) and re.search(us_rx + r"(?:은|는)", _flat(_attr(c, "text")))
                     and re.search(r"물의|사회적|상규|평판|명예", _attr(c, "text"))]

        original = _attr(pen_c, "text").rstrip()
        proposal = re.sub(r"위약벌로\s*지급하여야\s*하며,?\s*이와\s*별도로[^.]*손해를\s*배상하여야\s*한다\.",
                          "손해배상액의 예정으로 지급하며, 이 외에 별도의 손해배상 책임은 부담하지 아니한다.", original)
        if proposal == original:
            proposal = re.sub(r"위약벌로", "손해배상액의 예정으로", original)
        linked: list[dict[str, str]] = []
        if subj_c is not None:
            linked.append({"display_path": _attr(subj_c, "display_path"),
                           "text": re.sub(th_rx + r"의\s*판단에\s*비추어\s*볼\s*때", "객관적으로 보아",
                                          _flat(_attr(subj_c, "text")))})
        if not checks[2]["ok"]:
            # "즉시" 를 남기면 뒤에 붙인 사전 협의 단서와 모순된다.
            term_text = re.sub(r"즉시\s*", "", _flat(_attr(term_c, "text")))
            linked.append({"display_path": _attr(term_c, "display_path"),
                           "text": (f"{term_text} 다만, {_p(th, '은', '는')} 해제 또는 해지 전에 그 사유를 "
                                    f"구체적으로 적어 서면으로 통지하고, 7일 이상의 기간을 정하여 {_p(_q(our_s[0]), '과', '와')} 협의하여야 한다.")})
        if pay_c is not None:
            linked.append({"display_path": _attr(pay_c, "display_path"),
                           "text": re.sub(r"이\s*경우에도[^.]*(?:잔여\s*대금|대금)[^.]*면하지\s*못한다\.",
                                          f"이 경우 {_q(our_s[0])}의 대금 지급 의무는 제3항에 따른 금액으로 한정한다.",
                                          _flat(_attr(pay_c, "text")))})
        if not reciprocal:
            person = "소속 크리에이터" if "크리에이터" in body else "임직원"
            brand = _q(our_s[-1]) if len(our_s) > 1 else _q(our_s[0])
            n_par = max((int(_attr(c, "paragraph_number")) for c in cs if _attr(c, "paragraph_number").isdigit()),
                        default=0) + 1
            circled = "①②③④⑤⑥⑦⑧⑨⑩"[n_par - 1] if 1 <= n_par <= 10 else f"제{n_par}항"
            linked.append({"display_path": f"제{art}조 {circled}(같은 조 말미)",
                           "text": (f"{circled} {th} 또는 {th} {person}의 법령 위반, 부적절한 언행 등으로 사회적 비난이 "
                                    f"야기되어 {brand}의 브랜드 이미지가 실추되거나 실추될 현저한 우려가 있는 경우, "
                                    f"{_p(_q(our_s[0]), '은', '는')} 서면 통지로써 본 계약을 해제 또는 해지하고 {th}에게 {deliverable}의 비공개 또는 "
                                    f"삭제를 요청할 수 있다. 이 경우 {_p(th, '은', '는')} 기 지급받은 {fee} 전액을 반환하고 "
                                    f"{_p(_q(our_s[0]), '이', '가')} 입은 손해를 배상하여야 한다.")})
        for oc in other_pen:
            linked.append({"display_path": _attr(oc, "display_path"),
                           "text": (re.sub(r"위약벌로", "손해배상액의 예정으로", _flat(_attr(oc, "text")))
                                    + f" 다만, 같은 사유로 제{art}조에 따른 금액을 지급하는 경우에는 본 항을 적용하지 아니한다.")})
        short = ["위약벌" + (f"(제작료 {m_pct.group(1)}%)" if m_pct else ""), "위약벌과 별도의 손해배상",
                 "결과물 비공개·삭제", "삭제 후 잔여대금 지급의무"]
        stacked = [lbl for lbl, x in zip(short, checks[4:]) if not x["ok"]]
        problem = (
            f"{th}에게 일방적 해지권이 있고"
            + (f"(우리 회사 귀책 사유를 {th}의 판단만으로도 인정)" if subj_c is not None else "")
            + ", 해지되면 " + _p("·".join(stacked), "이", "가") + " 한꺼번에 적용된다(책임 중첩). "
            + ("같은 사유에 대한 위약벌이 " + ", ".join(_attr(c, "display_path") for c in other_pen) + "에도 있어 이중으로 부과될 수 있다. "
               if other_pen else "")
            + (checks[3]["detail"] + "." if not reciprocal else "")
        )
        paths = [_attr(pen_c, "display_path")] + [e["display_path"] for e in linked]
        out.append(_finding(
            pen_c,
            clause_id=f"lr_remedy_stacking__{_attr(pen_c, 'clause_id')}",
            legal_effect_code=CODE_STACKING,
            semantic_checks=checks,
            problem=_with_linked(problem, linked),
            rewrite_reason=problem,
            legal_business_reason=(
                "위약벌은 손해배상액의 예정과 달리 법원이 감액할 수 없고(민법 제398조 제2항은 손해배상 예정에만 적용), "
                "실손해 배상과 별도로 청구된다. 상대방의 주관적 판단만으로 해지 사유가 성립하면, 콘텐츠는 내려가는데 대금 "
                "전액·위약벌·손해배상을 모두 부담하는 결과가 될 수 있다."
            ),
            high_severity_basis="상대방 일방 해지·삭제권 + 우리 회사만 위약벌·무제한 손해배상 + 잔여대금 존속(책임 중첩)",
            suggested_rewrite=proposal,
            package_linked_edits=linked,
            related_clause_paths=[p for p in dict.fromkeys(paths) if p],
            package_articles=sorted({art} | {_attr(c, "article_number") for c in other_pen}),
            package_pattern=r"위약|해지|해제|삭제|비공개|귀책|물의|평판|명예|브랜드|광고\s*중단|잔여|조치",
            negotiation_position=("우선순위: ① 위약벌 → 손해배상액의 예정(별도 손해배상 삭제) ② 상대방 판단 기준 삭제 "
                                  "③ 삭제 시 잔여대금 정리 ④ 상대방 귀책 시 우리 회사의 해지·환급권 신설."),
            detected_issue_list=[{"issue_title": f"[책임 중첩] 제{art}조 — 상대방 일방 해지 + 위약벌·손해배상·삭제·잔여대금 중첩, 상대방 귀책 조치 부재"}],
        ))
    return out


# ── 3. 결과물 이용권과 사업 목적 (지시 12항) ────────────────────────────────────

_RX_SOLE_OWNER = re.compile(r"지식재산권은?\s*" + _Q + r"?([^”\"]{1,6})" + _Q + r"?(?:이|가)\s*단독으로\s*소유")
_RX_PAID_ONLY = re.compile(r"별도\s*(?:유상\s*)?합의에\s*의하여[^.]{0,30}(?:활용|이용|사용)")
_RX_EDIT_BAN = re.compile(r"숏폼|번역|편집|각색|가공")


def find_content_use_gap(
    *, clauses: list[Any] | None, our: list[str], them: list[str], plan_confirmed: bool,
) -> list[dict[str, Any]]:
    our_s = _short_labels(our)
    them_s = _short_labels(them)
    if not our_s or not them_s:
        return []
    sole = next((c for c in clauses or [] if (m := _RX_SOLE_OWNER.search(_flat(_attr(c, "text"))))
                 and m.group(1) in them_s), None)
    paid = next((c for c in clauses or [] if _RX_PAID_ONLY.search(_flat(_attr(c, "text")))), None)
    if sole is None or paid is None:
        return []
    art_text = " ".join(_attr(c, "text") for c in clauses or [] if _attr(c, "article_number") == _attr(paid, "article_number"))
    bans = [c for c in clauses or [] if _attr(c, "article_number") == _attr(paid, "article_number") and c is not paid
            and _RX_EDIT_BAN.search(_attr(c, "text"))] if re.search(r"금지", art_text) else []
    us, th = _q(our_s[0]), _q(them_s[0])
    client = _q(our_s[-1]) if len(our_s) > 1 else ""
    who = f"{us} 및 {client}" if client else us
    body_all = " ".join(_attr(c, "text") for c in clauses or [])
    deliverable = "“콘텐츠”" if "“콘텐츠”" in body_all else "결과물"
    new_text = (f"{_p(who, '은', '는')} {_p(deliverable, '을', '를')} 게시일로부터 1년간 자체 운영 채널(공식 유튜브 채널, 홈페이지, SNS)에 "
                "게시하거나 링크·임베드하는 방식으로 무상으로 이용할 수 있다. 광고소재 활용, 숏폼 제작 등 편집 이용을 포함한 "
                "그 밖의 2차 라이선스는 "
                f"{_p(th, '과', '와')} 별도 유상합의에 의하되, 그 대가는 본 계약 체결 시 함께 정한다.")
    original = _attr(paid, "text").rstrip()
    lead = original[:1] if re.match(r"^[①-⑳]", original) else ""
    proposal = f"{lead} {new_text}".strip()
    problem = (f"결과물의 지식재산권은 {_p(th, '이', '가')} 단독 소유하고({_attr(sole, 'display_path')}), {_p(us, '은', '는')} 자체 채널 게시·"
               f"광고소재·숏폼 등 어떤 2차 활용도 별도 유상합의 없이는 할 수 없다"
               + (f". 편집·숏폼 제작은 계약기간 중 명시적으로 금지된다({', '.join(_attr(c, 'display_path') for c in bans)})" if bans else "")
               + ". " + ("사전질문 답변상 자체 채널 게시·광고소재 활용 계획이 있어, 지금 계약대로면 제작비를 내고도 계획한 "
                         "마케팅에 쓰려면 추가 대가 협상이 필요하다." if plan_confirmed else
                         "홍보 목적 계약인데 우리 채널 활용 범위가 정해져 있지 않다."))
    paths = [_attr(paid, "display_path"), _attr(sole, "display_path")] + [_attr(c, "display_path") for c in bans]
    tier = "HIGH" if plan_confirmed else "MEDIUM"
    return [_finding(
        paid,
        clause_id=f"lr_content_use_rights__{_attr(paid, 'clause_id')}",
        legal_effect_code=CODE_CONTENT_USE,
        risk_tier=tier, severity=tier, must_fix=tier == "HIGH", review_tier="MUST" if tier == "HIGH" else "SUGGEST",
        problem=problem,
        legal_business_reason=("홍보용 콘텐츠 계약의 목적은 우리 제품의 마케팅이다. 자체 채널 게시까지 별도 대가가 필요하면 "
                               "계약 목적 달성이 제한되고, 사후 협상에서는 상대방이 가격을 정한다."),
        high_severity_basis="핵심 이용권 확보 실패 — 계획된 자체 채널·광고소재 활용 불가" if tier == "HIGH" else "",
        suggested_rewrite=proposal,
        related_clause_paths=[p for p in dict.fromkeys(paths) if p],
        package_articles=sorted({_attr(paid, "article_number"), _attr(sole, "article_number")}),
        package_pattern=r"라이선스|이용|활용|2차|숏폼|편집|자체\s*채널|지식재산|저작|초상|광고소재",
        negotiation_position=("자체 채널 무상 게시가 1순위, 광고소재·숏폼은 지금 단가를 정해 두는 것이 2순위입니다. "
                              "크리에이터 초상·성명 사용은 별도 계약이 통상적이므로 그대로 둡니다."),
        detected_issue_list=[{"issue_title": "[이용권] 제작비를 내고도 자체 채널·광고소재 활용에 별도 유상합의 필요"}],
    )]


__all__ = [
    "CODE_ASYMMETRIC", "CODE_CONTENT_USE", "CODE_STACKING",
    "find_asymmetric_liability", "find_content_use_gap", "find_remedy_stacking",
]
