"""국제 물품매매(international_sale_of_goods) 체크리스트.

조항 번호·회사명·품목명을 조건으로 쓰지 않는다. 위치는 문언(“지체상금”, “클레임”, “Incoterms” …)으로 찾고, 수정 문안의
조항 참조·당사자 호칭도 원문에서 찾은 값으로 채운다. 정할 수 없는 값은 `[  ]` 로 남겨 사업부 결정과 잇는다.
매수인(우리) 관점 항목은 우리가 구매자일 때만, 매도인 관점 항목은 우리가 공급자일 때만 돈다.
"""
from __future__ import annotations

import re

from runtime.review.cross_border import statutes as S
from runtime.review.cross_border.blanks import CLASS_MUST
from runtime.review.cross_border.context import Ctx
from runtime.review.cross_border.evidence import quote_around
from runtime.review.cross_border.findings import (
    ACTION_CONFIRM, ACTION_KEEP, ACTION_MUST, ACTION_SUGGEST, Edit, Finding,
)

_F_GROUP = ("FCA", "FAS", "FOB", "EXW")
_C_GROUP = ("CFR", "CIF", "CPT", "CIP")
_D_GROUP = ("DAP", "DPU", "DDP")
_RX_FREIGHT_COLLECT = re.compile(r"ASSEGNATO|porto\s+assegnato|freight\s+collect|운임\s*착불", re.I)
_RX_EXPORT_VAT = re.compile(r"NI\s*ART\.?\s*8|non\s+imponibile|영세율|VAT\s+exempt(?:ion)?|zero[- ]rated|export\s+VAT", re.I)
_RX_SELLER_EXPORT = re.compile(r"수출\s*통관[^.\n]{0,40}(?:을|Seller|공급자)|(?:Seller|을)[^.\n]{0,40}export\s+customs|Seller\s+shall\s+handle\s+export", re.I)
_RX_CODE = re.compile(r"\b(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b")


# ── 공통 도우미 ───────────────────────────────────────────────────────────────

def _q(ctx: Ctx, label: str) -> str:
    """원문이 호칭을 따옴표로 감싸 쓰면 같은 방식으로."""
    for o, c in (('"', '"'), ("“", "”")):
        if f"{o}{label}{c}" in ctx.text:
            return f"{o}{label}{c}"
    return label


def _en_label(ctx: Ctx, label: str, role_word: str) -> str:
    from runtime.review.direction_gate import expand_labels

    group = [x for x in expand_labels([label], ctx.text) if re.fullmatch(r"[A-Za-z ]+", x)]
    if not group:
        return role_word
    en = ctx.pairs and " ".join(p.en for p in ctx.pairs)
    return max(group, key=lambda g: (en or "").count(g))


def _para_line(ctx: Ctx, rx: re.Pattern[str], lang: str) -> tuple[str, str]:
    """(경로, 그 언어의 항 본문) — 항 머리("1. 잔금에서의 직접 공제:")가 rx 에 맞는 항을 먼저, 없으면 본문이 맞는 첫 항."""
    hits = [p for p in ctx.pairs if (p.ko if lang == "ko" else p.en) and rx.search(p.ko if lang == "ko" else p.en)]
    for p in hits:
        s = p.ko if lang == "ko" else p.en
        head = s.split(":", 1)[0] if ":" in s[:80] else ""
        if head and rx.search(head):
            return p.path, s
    if hits:
        p = hits[0]
        return p.path, (p.ko if lang == "ko" else p.en)
    return "", ""


def _article_of(path: str) -> str:
    m = re.search(r"제(\d+)조", path)
    return m.group(1) if m else ""


def _para_of(path: str) -> str:
    m = re.search(r"제(\d+)항", path)
    return m.group(1) if m else ""


def _en_ref(path: str) -> str:
    a, p = _article_of(path), _para_of(path)
    return f"paragraph {p} of Article {a}" if p else f"Article {a}"


def _next_para(ctx: Ctx, art: str) -> int:
    nums = [int(_para_of(p.path)) for p in ctx.pairs if _article_of(p.path) == art and _para_of(p.path).isdigit()]
    return (max(nums) + 1) if nums else 1


def _sentence(line: str, rx: re.Pattern[str]) -> str:
    m = rx.search(line)
    if not m:
        return ""
    starts = [x.end() for x in re.finditer(r"다\.\s*|\.\s+", line[:m.start()])]
    s = starts[-1] if starts else 0
    e_m = re.search(r"다\.|\.(?:\s|$)", line[m.end():])
    e = m.end() + e_m.end() if e_m else len(line)
    return line[s:e].strip()


def _labels(ctx: Ctx) -> tuple[str, str, str, str]:
    """(우리 국문, 상대 국문, 우리 영문, 상대 영문) — 우리가 구매자일 때 기준."""
    ours = ctx.our_label or ctx.facts.label_of_role("buyer")
    theirs = ctx.their_label or ctx.facts.label_of_role("seller")
    return _q(ctx, ours), _q(ctx, theirs), _en_label(ctx, ours, "Buyer"), _en_label(ctx, theirs, "Seller")


# ── S1. Incoterms ────────────────────────────────────────────────────────────

def incoterms(ctx: Ctx) -> list[Finding]:
    b = next((x for x in ctx.blanks if x.category == "delivery_terms" and x.kind == "options"), None)
    if b is None:
        return []
    codes = list(dict.fromkeys(_RX_CODE.findall(" ".join(b.options))))
    collect = ctx.exact(_RX_FREIGHT_COLLECT)
    vat = ctx.exact(_RX_EXPORT_VAT)
    seller_export = ctx.has(_RX_SELLER_EXPORT)
    proposed = ctx.proposed_value(_RX_CODE)
    f_opts = [c for c in codes if c in _F_GROUP]
    c_opts = [c for c in codes if c in _C_GROUP]
    consistency = []
    if collect:
        consistency.append(f"견적서의 “{collect}”(운임 착불)")
    if vat:
        consistency.append(f"수출 부가세 영세율 문구(“{vat}”)")
    if seller_export:
        consistency.append("수출 통관·적재를 공급자가 맡는 구조")
    prob = (f"인도 조건이 “{' / '.join(b.options)}” 선택지로만 적혀 있고 하나로 정해지지 않았다. "
            "인도 조건이 정해지지 않으면 운임·보험·수출입 통관을 누가 부담하는지, 물품 위험이 언제 넘어오는지가 모두 비어 있다.")
    if consistency and (f_opts or c_opts):
        prob += (f" 계약의 다른 문언 — {', '.join(consistency)} — 은 매수인이 운임을 부담하는 F조건({'/'.join(f_opts) or 'FCA·FOB'})과 맞고, "
                 f"매도인이 운임·보험을 부담하는 C조건({'/'.join(c_opts) or 'CIF'})과는 충돌한다.")
    risk_txt = ("F조건에서는 물품 위험이 출발지(운송인 인도 또는 본선 적재)에서 우리에게 넘어오는데, 검수는 한국 창고 입고 후에 한다 — "
                "운송 중 파손·젖음이 생기면 공급자 하자로 다투기 어렵고 적하보험으로만 회수할 수 있다. 그래서 적하보험은 우리(매수인)가 부보해야 한다.")
    rec = ""
    loc_ko = "FCA [지정 인도 장소], Incoterms 2020"
    loc_en = "FCA [named place of delivery], Incoterms 2020"
    if proposed:
        if proposed == "FOB":
            rec = ("사업부가 답한 FOB 는 상대방과 합의 전 제안값이다. FOB 로 정한다면 ① 지정 선적항(이탈리아 항구명)이 아직 공란이고, "
                   "② 위험이 선적항에서 본선 적재 시 넘어오므로 우리가 적하보험을 부보해야 하며, ③ 내륙 출고지에서 선적항까지의 운송·수출 통관은 공급자 부담이 된다. "
                   "다만 ICC 는 컨테이너 화물에는 FOB 대신 FCA 를 쓰도록 권고한다(컨테이너는 본선 적재 전에 터미널에서 인도되므로 그 사이 위험 공백이 생긴다).")
            loc_ko = "FOB [지정 선적항], Incoterms 2020"
            loc_en = "FOB [named port of shipment], Incoterms 2020"
        else:
            rec = f"사업부가 답한 {proposed} 는 상대방과 합의 전 제안값이다 — 지정 장소를 함께 확정해야 한다."
            loc_ko = f"{proposed} [지정 장소], Incoterms 2020"
            loc_en = f"{proposed} [named place], Incoterms 2020"
    else:
        rec = "운임 착불·수출 영세율 구조와 맞는 FCA(지정 인도 장소 명시)를 권한다. 컨테이너 화물이면 ICC 권고도 FOB 보다 FCA 다."
    edits: list[Edit] = []
    for tok in dict.fromkeys(b.tokens):
        ko = bool(re.search(r"[가-힣]", tok))
        edits.append(Edit(location=b.path, target=tok, replacement=(loc_ko if ko else loc_en), lang="ko" if ko else "en"))
    return [Finding(
        code="incoterms_unselected", title="인도 조건(Incoterms) 미선택 — 운임·보험·위험 이전 미확정", path=b.path, risk="HIGH",
        action=ACTION_MUST, topics=["delivery", "tax", "insurance"], quotes=b.quotes, problem=prob, risk_to_us=risk_txt,
        loss_path="운송 중 손상 또는 운임·통관비 청구 → 인도 조건 미정 → 부담 주체 다툼·보험 공백 → 손실 자체 부담",
        action_text="인도 조건을 하나로 확정하고(지정 장소 포함), F조건이면 우리 쪽 적하보험 부보를 준비한다.",
        edits=edits, recommendation=rec,
        statutes=S.cisg("38"),
        checks=[{"what": "인도 조건과 지정 장소(또는 선적항)를 상대방과 확정", "who": "사업부(협상)·물류", "when": "서명 전"},
                {"what": "F조건 확정 시 적하보험(창고 간 담보) 부보 준비", "who": "사업부·물류", "when": "첫 선적 전"}],
        negotiation="견적서가 이미 운임 착불·수출 영세율로 되어 있어 F조건 확정은 상대방에게도 자연스럽다 — 협상 부담이 작다.",
        family="international_sale_of_goods",
    )]


# ── S2. 선적 기한 공란(+ 지체상금 연동) ────────────────────────────────────────

def shipment_deadline(ctx: Ctx) -> list[Finding]:
    b = next((x for x in ctx.blanks if x.category == "delivery_time" and x.classification == CLASS_MUST), None)
    if b is None:
        return []
    deps = b.dependencies
    dep_txt = "; ".join(f"{d['path']} — {d['effect']}" for d in deps)
    return [Finding(
        code="shipment_deadline_blank", title="선적 기한 공란" + (" — 지체상금 조항 작동 불가" if deps else ""), path=b.path, risk="HIGH",
        action=ACTION_CONFIRM, topics=["delivery", "blank"], quotes=b.quotes + [d["quote"] for d in deps],
        problem="선적 기한이 공란이다." + (f" 이 기한을 기준으로 하는 조항이 있다: {dep_txt}." if deps else ""),
        risk_to_us="선적 기한이 없으면 공급자가 늦게 선적해도 지연으로 볼 기준일이 없다 — 지체상금도, 지연을 이유로 한 해제도 주장하기 어렵다.",
        loss_path="공급자 선적 지연 → 기한 공란 → 지체상금·해제 불가 → 생산 일정 차질 손실을 우리가 부담",
        action_text="선적 기한(주 또는 일)을 상대방과 확정해 공란을 숫자로 채운다 — 체결 전 필수 확정(사업부, 서명 전).",
        statutes=S.kr("civil_398"),
        family="international_sale_of_goods",
    )]


# ── S3. 선급금 보호·지체상금 상한 후 구제수단 ──────────────────────────────────

_RX_LD = re.compile(r"지체상금|liquidated\s+damages", re.I)
_RX_CAP = re.compile(r"최대\s*\d+(?:\.\d+)?\s*%\s*한도|\d+(?:\.\d+)?\s*%\s*(?:를\s*)?한도|capped\s+at\s+\d+(?:\.\d+)?\s*%|maximum\s+of\s+\d+(?:\.\d+)?\s*%", re.I)
_RX_ADV_REFUND = re.compile(r"선급금[^.\n]{0,80}(?:반환|환급)|(?:refund|return|repay)[^.\n]{0,60}advance|advance[^.\n]{0,80}(?:refund|return|repaid)", re.I)
_RX_TERMINATE = re.compile(r"해제할\s*수|해지할\s*수|terminate|rescind|avoid\s+(?:the|this)", re.I)


def advance_and_delay_remedies(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side:
        return []
    f = ctx.facts
    adv = f.advance_pct
    no_refund = not ctx.has(_RX_ADV_REFUND)
    no_term = not ctx.has(_RX_TERMINATE)
    ld_path, ld_ko = _para_line(ctx, _RX_LD, "ko")
    _p2, ld_en = _para_line(ctx, _RX_LD, "en")
    cap = bool(ld_ko and _RX_CAP.search(ld_ko + " " + ld_en))
    if not ((adv and adv >= 20 and no_refund and no_term) or (cap and no_term)):
        return []
    quotes = [x for x in (f.split_quote, _sentence(ld_ko, _RX_CAP) if ld_ko else "", _sentence(ld_en, _RX_CAP) if ld_en else "") if x]
    o_ko, t_ko, o_en, t_en = _labels(ctx)
    art = _article_of(ld_path)
    n = _next_para(ctx, art) if art else 0
    edits = []
    if art:
        edits = [
            Edit(location=f"제{art}조 제{n - 1}항", target="", edit_type="insert_after", lang="ko",
                 replacement=(f"{n}. 지체상금이 제{_para_of(ld_path)}항의 한도에 이르거나 {t_ko}이 약정된 선적 기한으로부터 [  ]일이 지나도록 "
                              f"선적을 완료하지 못한 경우, {o_ko}은 서면 통지로 본 계약의 전부 또는 일부를 해제할 수 있다. 이 경우 {t_ko}은 "
                              f"해제 통지를 받은 날로부터 [  ]영업일 이내에 이미 받은 선급금 전액을 반환하여야 한다.")),
            Edit(location=f"Article {art}", target="", edit_type="insert_after", lang="en",
                 replacement=(f"{n}. If the liquidated damages reach the cap under paragraph {_para_of(ld_path)}, or if {t_en} fails to complete "
                              f"shipment within [  ] days after the agreed shipment date, {o_en} may terminate this Agreement in whole or in part "
                              f"by written notice, in which case {t_en} shall refund the full advance payment received within [  ] business days "
                              f"after receipt of such notice.")),
        ]
    adv_path = ctx.layout.path(ctx.text.find(f.split_quote)) if f.split_quote and f.split_quote in ctx.text else ""
    return [Finding(
        code="advance_and_delay_remedies",
        title="선급금 반환·해제권 없음" + (" — 지체상금 상한 도달 후 구제수단 부재" if cap else ""),
        path=ld_path or adv_path, risk="MEDIUM", action=ACTION_SUGGEST, topics=["payment", "delivery"], quotes=quotes,
        problem=(f"대금의 {adv}%를 선급하는데 공급자가 끝내 선적하지 않을 때 계약을 해제하고 선급금을 돌려받는 조항이 없다."
                 if adv else "공급자 불이행 시 해제와 기지급금 반환 조항이 없다.")
                + (" 지체상금은 상한에 이르면 더 늘지 않는데, 그 뒤의 구제수단(해제·반환)이 없다." if cap else ""),
        risk_to_us="지연이 길어져 지체상금이 상한에 닿으면 공급자에게 더 이행을 재촉할 수단이 없고, 선급금은 해외 중재로만 회수해야 한다.",
        loss_path="장기 미선적 → 지체상금 상한 도달·해제 조항 없음 → 선급금 묶임 → 해외 중재 회수 비용",
        action_text="지체상금 한도 도달 또는 일정 기간 미선적 시 해제권과 선급금 반환(기한 포함)을 신설한다.",
        edits=edits,
        recommendation=("계약 금액 규모를 고려하면 선급금 보증(APG)·신용장까지 요구하는 것은 과할 수 있다 — 해제·반환 조항과 송금 증빙 보관으로 충분하다."
                        if (f.total_amount and float(f.total_amount.replace(",", "") or 0) < 200000) else
                        "계약 금액이 크면 선급금 보증(APG) 또는 신용장 결제를 함께 검토한다."),
        statutes=S.cisg("49", "81"),
        negotiation="해제·반환은 공급자에게 새 부담이 아니라 당연한 원상회복을 적는 것이라 수용 가능성이 높다. [ ] 값(유예 일수·반환 기한)은 사업부가 정한다.",
        family="international_sale_of_goods",
    )]


# ── S4. 잔금 기한 ↔ 클레임 기간, 검수 완료 정의 ───────────────────────────────

_RX_DAYS_AFTER_ARRIVAL = re.compile(r"(?:입고일|도착일|수령일|arrival|receipt)[^.\n]{0,20}?\[?\s*(\d{1,3})\s*\]?\s*(?:일|days)|\[?\s*(\d{1,3})\s*\]?\s*days\s+after\s+arrival", re.I)
_RX_CLAIM = re.compile(r"클레임|claim\s+period|claim", re.I)
_RX_BALANCE = re.compile(r"잔금|Balance", re.I)
_RX_INSPECTION_DONE = re.compile(r"검수를?\s*완료|completion\s+of\s+(?:arrival\s+)?inspection", re.I)
_RX_INSPECTION_DEF = re.compile(r"검수\s*완료(?:란|는|라\s*함은|일은)|inspection\s+shall\s+be\s+deemed\s+(?:complete|completed)|\"Completion\s+of\s+inspection\"\s+means", re.I)


def _days(line: str) -> int | None:
    m = _RX_DAYS_AFTER_ARRIVAL.search(line)
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def balance_vs_claim(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side:
        return []
    bal_path, bal_ko = _para_line(ctx, re.compile(r"잔금[^\n]*(?:입고일|도착일)"), "ko")
    _b2, bal_en = _para_line(ctx, re.compile(r"Balance[^\n]*arrival", re.I), "en")
    clm_path, clm_ko = _para_line(ctx, re.compile(r"클레임[^\n]*(?:입고일|도착일)"), "ko")
    _c2, clm_en = _para_line(ctx, re.compile(r"claim\s+period[^\n]*arrival", re.I), "en")
    if not (bal_ko and clm_ko):
        return []
    d_bal, d_clm = _days(bal_ko), _days(clm_ko)
    conflict = d_bal is not None and d_clm is not None and d_bal < d_clm
    undefined = bool(_RX_INSPECTION_DONE.search(bal_ko + bal_en)) and not ctx.has(_RX_INSPECTION_DEF)
    if not (conflict or undefined):
        return []
    q = [x for x in (_sentence(bal_ko, re.compile(r"입고일|도착일")), _sentence(clm_ko, re.compile(r"입고일|도착일")),
                     _sentence(bal_ko, _RX_INSPECTION_DONE) if undefined else "") if x]
    o_ko, t_ko, o_en, t_en = _labels(ctx)
    clm_ref_ko = clm_path.replace(" ", " ")
    edits = [
        Edit(location=bal_path, target="", edit_type="insert_after", lang="ko",
             replacement=(f"“검수 완료”란 {clm_ref_ko}의 클레임 제기 기한이 지난 날과 {o_ko}이 {t_ko}에게 검수 완료를 서면으로 통지한 날 중 먼저 오는 날을 말하며, "
                          f"잔금 지급 기한은 검수 완료일로부터 [  ]일로 한다.")),
        Edit(location=bal_path, target="", edit_type="insert_after", lang="en",
             replacement=(f"\"Completion of inspection\" means the earlier of (i) the expiry of the claim period under {_en_ref(clm_path)} and "
                          f"(ii) the date on which {o_en} notifies {t_en} in writing that the inspection is complete, and the Balance shall be due "
                          f"within [  ] days after the completion of inspection.")),
    ]
    prob = []
    if conflict:
        prob.append(f"잔금은 입고 후 {d_bal}일 안에 내야 하는데 품질 클레임은 입고 후 {d_clm}일까지 할 수 있어, 잔금을 먼저 다 내고 나서 하자를 발견하는 순서가 된다")
    if undefined:
        prob.append("잔금 지급을 ‘검수 완료’까지 유예한다고 하면서 검수 완료가 언제인지(정의·기한)를 정하지 않았다")
    return [Finding(
        code="balance_claim_timing", title="잔금 기한과 클레임 기간 선후 충돌·‘검수 완료’ 정의 없음", path=bal_path, risk="MEDIUM",
        action=ACTION_SUGGEST, topics=["payment", "defect"], quotes=q, problem="; ".join(prob) + ".",
        risk_to_us="잔금을 낸 뒤에 하자가 드러나면 잔금 공제라는 가장 쉬운 회수 수단을 잃고, 공급자에게 환급을 청구해야 한다. 검수 완료 시점이 불명확하면 "
                   "공급자는 입고 후 곧바로 잔금 지연을 주장할 수 있다.",
        loss_path="잔금 지급 후 하자 발견 → 공제할 잔금 없음 → 해외 환급 청구·회수 지연",
        action_text="‘검수 완료’를 클레임 기한 경과일 또는 서면 통지일 중 먼저 오는 날로 정의하고, 잔금 기한을 그날부터 기산한다.",
        edits=edits, statutes=S.cisg("38", "39"),
        negotiation="잔금 유예는 이미 계약에 있는 취지(검수 연동)를 분명히 하는 것이다 — 기산일만 명확히 하자고 요청한다.",
        family="international_sale_of_goods",
    )]


# ── S5. 숨은 하자 배제 ────────────────────────────────────────────────────────

_RX_LATENT_KO = re.compile(r"단,\s*[^.\n]{0,60}?(?:재단|가공|사용|설치|절단)[^.\n]{0,40}?전[^.\n]{0,40}?(?:한한다|한함)\.?")
_RX_LATENT_EN = re.compile(r"provided\s+(?:that\s+)?[^.\n]{0,80}?not\s+been\s+(?:cut|processed|used|installed|altered)[^.\n]*\.?", re.I)


def latent_defects(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side:
        return []
    path, ko = _para_line(ctx, _RX_LATENT_KO, "ko")
    _p, en = _para_line(ctx, _RX_LATENT_EN, "en")
    if not ko and not en:
        return []
    mk = _RX_LATENT_KO.search(ko) if ko else None
    me = _RX_LATENT_EN.search(en) if en else None
    acts_ko = "·".join(dict.fromkeys(re.findall(r"재단|가공|사용|설치|절단", mk.group(0)))) if mk else "가공"
    acts_en = " or ".join(dict.fromkeys(re.findall(r"cut(?:ting)?|process(?:ed|ing)|used|install(?:ed)?", me.group(0), re.I))) if me else "processing"
    acts_en = acts_en.replace("cut", "cutting").replace("processed", "processing").replace("cuttingting", "cutting")
    o_ko, t_ko, o_en, t_en = _labels(ctx)
    edits = []
    if mk:
        edits.append(Edit(location=path, target=mk.group(0), lang="ko",
                          replacement=(f"단, {acts_ko} 전에는 발견하기 어려운 숨은 하자는 {o_ko}이 이를 발견한 날로부터 [  ]일 이내에 통지하는 경우 "
                                       f"입고일로부터 [  ]개월까지 클레임을 제기할 수 있다.")))
    if me:
        edits.append(Edit(location=path, target=me.group(0), lang="en",
                          replacement=(f"provided, however, that for latent defects which could not reasonably be discovered before {acts_en}, "
                                       f"{o_en} may make a claim within [  ] months after arrival if it notifies {t_en} within [  ] days after discovery.")))
    return [Finding(
        code="latent_defects_excluded", title="재단·가공 전 하자로 한정 — 숨은 하자 배제", path=path, risk="MEDIUM", action=ACTION_SUGGEST,
        topics=["defect", "quality"], quotes=[x.group(0) for x in (mk, me) if x],
        problem=f"클레임을 {acts_ko} 전 상태에서 발견된 하자로 한정했다. {acts_ko} 과정에서야 드러나는 숨은 하자(코팅·발수 불량, 조직 결함 등)는 클레임할 수 없다.",
        risk_to_us="원단은 재단·가공 후에야 결함이 드러나는 경우가 많다 — 그때는 이미 재작업비까지 들어간 뒤라 손실이 가장 크다. CISG 는 숨은 하자도 발견 후 합리적 기간 내 "
                   "통지하면 주장할 수 있게 하지만(최장 2년), 계약이 이를 좁히면 계약 조항이 우선한다(제6조).",
        loss_path="재단 후 숨은 하자 발견 → 가공 전 하자 한정 조항 → 클레임 불가 → 원단값·재작업비 손실",
        action_text="숨은 하자는 발견 후 [ ]일 내 통지하면 입고 후 [ ]개월까지 클레임할 수 있도록 별도 기간을 둔다.",
        edits=edits, statutes=S.cisg("35", "39", "6"),
        negotiation="공급자가 기간 연장을 꺼리면 숨은 하자의 입증 책임을 우리가 지는 조건으로 기간만 확보한다.",
        family="international_sale_of_goods",
    )]


# ── S6. 품질 기준의 객관성 ────────────────────────────────────────────────────

_RX_SUBJ_KO = re.compile(r"(?:승인\s*샘플\s*대비\s*)?(?:심한|현저한|상당한)\s*(?:색상\s*편차|이색|색차)")
_RX_SUBJ_EN = re.compile(r"(?:severe|significant|substantial|noticeable)\s+colou?r\s+(?:shading|difference|deviation)"
                         r"(?:\s+(?:vs\.?|versus|against|compared\s+(?:to|with))\s+(?:the\s+)?approved\s+sample)?", re.I)
_RX_TOL_KO = re.compile(r"허용\s*오차\s*초과")
_RX_TOL_EN = re.compile(r"Out\s+of\s+tolerance", re.I)


def quality_objectivity(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side:
        return []
    path, ko = _para_line(ctx, re.compile(r"색상|이색|허용\s*오차"), "ko")
    _p, en = _para_line(ctx, re.compile(r"colou?r|tolerance", re.I), "en")
    subj_ko = _RX_SUBJ_KO.search(ko) if ko else None
    tol_ko = _RX_TOL_KO.search(ko) if ko else None
    tol_num = bool(ko and re.search(r"±|\d+(?:\.\d+)?\s*(?:mm|cm|%)\s*(?:이내|이하)", ko))
    if not subj_ko and not (tol_ko and not tol_num):
        return []
    subj_en = _RX_SUBJ_EN.search(en) if en else None
    tol_en = _RX_TOL_EN.search(en) if en else None
    # 호·목이 줄마다 나뉘어 있어(한 줄 = Word 한 문단) 낱말 단위로 따로 고친다
    edits = []
    if subj_ko:
        edits.append(Edit(location=path, target=subj_ko.group(0), lang="ko",
                          replacement="승인 샘플(양 당사자가 서명해 각 1부씩 보관한 것) 대비 그레이스케일 [ ]급 미만 또는 ΔE [ ] 초과의 색상 편차"))
    if subj_en:
        edits.append(Edit(location=path, target=subj_en.group(0), lang="en",
                          replacement="colour shading against the approved sample (signed and retained by both parties) below Grey Scale grade [ ] "
                                      "or exceeding ΔE [ ]"))
    if tol_ko and not tol_num:
        edits.append(Edit(location=path, target=tol_ko.group(0), replacement="허용 오차(±[ ]cm) 초과", lang="ko"))
    if tol_en and not tol_num:
        edits.append(Edit(location=path, target=tol_en.group(0), replacement="Out of tolerance (±[ ] cm)", lang="en"))
    quotes = [x for x in (subj_ko.group(0) if subj_ko else "", tol_ko.group(0) if tol_ko else "",
                          subj_en.group(0) if subj_en else "") if x]
    return [Finding(
        code="quality_subjective", title="색상 편차 기준 주관적·치수 허용 오차 수치 없음", path=path, risk="LOW", action=ACTION_SUGGEST,
        topics=["quality", "defect"], quotes=quotes,
        problem=("색상 불량을 ‘심한 색상 편차’처럼 주관적 표현으로 정했고" if subj_ko else "")
                + (", 재단물 치수 ‘허용 오차’의 수치가 없다" if tol_ko and not tol_num else "") + ".",
        risk_to_us="불량 판정 기준이 주관적이면 공급자가 ‘심하지 않다’고 다툴 때 객관적 반박 근거가 없다 — 공제·반송이 늦어진다.",
        loss_path="색상·치수 불량 주장 → 기준 없음 → 판정 다툼 → 공제 지연",
        action_text="승인 샘플 보관 방식과 측정 기준(그레이스케일 등급 또는 ΔE)·치수 허용 오차 수치를 넣는다.",
        edits=edits, statutes=S.cisg("35"),
        family="international_sale_of_goods",
    )]


# ── S7. 구제수단(교체·재납품·손해배상) ─────────────────────────────────────────

_RX_REPLACE = re.compile(r"교체|재납품|대체품|재선적|replace|substitut|re-?deliver|re-?ship", re.I)
_RX_DAMAGES = re.compile(r"손해\s*배상|damages(?!\s+for\s+delay)|indemnif", re.I)
_RX_DEDUCT = re.compile(r"공제|deduct", re.I)


def remedies(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side:
        return []
    if ctx.has(_RX_REPLACE):
        return []
    path, ko = _para_line(ctx, _RX_DEDUCT, "ko")
    if not ko:
        return []
    art = _article_of(path)
    n = _next_para(ctx, art)
    o_ko, t_ko, o_en, t_en = _labels(ctx)
    ret_path, ret_ko = _para_line(ctx, re.compile(r"반송|폐기"), "ko")
    q = [_sentence(ko, _RX_DEDUCT)] + ([_sentence(ret_ko, re.compile(r"반송"))] if ret_ko else [])
    no_damages = not ctx.has(re.compile(r"(?<!지연\s)(?<!지체)손해\s*배상|(?<!Liquidated\s)Damages\s+(?!for\s+Delay)", re.I))
    edits = [
        Edit(location=f"제{art}조 제{n - 1}항", target="", edit_type="insert_after", lang="ko",
             replacement=(f"{n}. {o_ko}은 제1항의 공제에 갈음하여 또는 이와 함께 {t_ko}에게 부적합 물품의 교체품을 [  ]일 이내에 {t_ko}의 비용으로 "
                          f"재선적하도록 요구할 수 있으며, 부적합 물품으로 인하여 {o_ko}에게 발생한 재작업비 등 직접 손해의 배상을 청구할 수 있다.")),
        Edit(location=f"Article {art}", target="", edit_type="insert_after", lang="en",
             replacement=(f"{n}. In lieu of or in addition to the deduction under paragraph 1, {o_en} may require {t_en} to re-ship replacement goods "
                          f"for the Defective Goods at {t_en}'s cost within [  ] days, and may claim compensation for direct losses, including rework "
                          f"costs, incurred by {o_en} as a result of the Defective Goods.")),
    ]
    return [Finding(
        code="remedies_deduction_only", title="불량 시 구제수단이 잔금 공제뿐 — 교체·재납품·손해배상 규정 없음", path=path, risk="MEDIUM",
        action=ACTION_SUGGEST, topics=["defect", "payment"], quotes=[x for x in q if x],
        problem="불량이 확정되면 잔금에서 공제·초과분 환급만 정했다. 교체품 재선적을 요구할 권리와 재작업비 등 손해배상 청구가 없고, 반송은 공급자가 원할 때만 한다.",
        risk_to_us="생산 일정상 원단이 다시 필요할 때 교체품을 요구할 근거가 약하고, 불량으로 생긴 재작업·지연 비용은 공제액(단가×수량)으로 보전되지 않는다. "
                   "불량품을 반품하고 환불받으려는 사업부 의도와도 맞지 않는다(반송 여부가 공급자 선택).",
        loss_path="불량 확정 → 공제만 가능 → 교체품 확보·재작업비 회수 불가 → 생산 차질 비용 부담",
        action_text="공제와 별도로 교체품 재선적 요구권과 직접 손해(재작업비 등) 배상 청구권을 신설한다.",
        edits=edits, statutes=S.cisg("46", "50", "74"),
        recommendation=("불량품을 반품·환불받고 싶다면 반송 여부를 ‘공급자가 원할 경우’가 아니라 ‘구매자의 선택에 따라’로 바꾸는 것도 함께 요청한다."
                        if ret_ko and re.search(r"원할\s*경우", ret_ko) else ""),
        family="international_sale_of_goods",
    )]


# ── S8. 원산지·FTA 관세 추징 부담 ─────────────────────────────────────────────

_RX_ORIGIN = re.compile(r"원산지\s*(?:신고서|증명서|증명)|Origin\s+Declaration|Certificate\s+of\s+Origin|FTA", re.I)
_RX_ORIGIN_LIAB = re.compile(r"추징|관세[^.\n]{0,30}(?:부담|배상|보전)|(?:duty|duties|customs)[^.\n]{0,60}(?:borne|reimburs|indemnif|compensat)|원산지[^.\n]{0,40}(?:부적격|무효|부적정)", re.I)


def origin_duty(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side or not ctx.has(_RX_ORIGIN) or ctx.has(_RX_ORIGIN_LIAB):
        return []
    path, ko = _para_line(ctx, _RX_ORIGIN, "ko")
    _p, en = _para_line(ctx, _RX_ORIGIN, "en")
    o_ko, t_ko, o_en, t_en = _labels(ctx)
    q = [x for x in (_sentence(ko, _RX_ORIGIN), _sentence(en, _RX_ORIGIN)) if x]
    edits = [
        Edit(location=path, target="", edit_type="insert_after", lang="ko",
             replacement=(f"{t_ko}이 제공한 원산지 증빙이 부적정하거나 원산지 요건을 충족하지 못하여 {o_ko}이 협정관세를 적용받지 못하거나 관세 등을 "
                          f"추징당한 경우, {t_ko}은 그 추징 세액·가산세 및 관련 비용을 {o_ko}에게 배상한다.")),
        Edit(location=path, target="", edit_type="insert_after", lang="en",
             replacement=(f"If {o_en} is denied preferential tariff treatment or is assessed additional customs duties because the origin documentation "
                          f"provided by {t_en} is invalid or the goods do not satisfy the rules of origin, {t_en} shall compensate {o_en} for such "
                          f"duties, penalties and related costs.")),
    ]
    return [Finding(
        code="origin_duty_liability", title="원산지 부적격 시 관세 추징액 부담 주체 미규정", path=path, risk="MEDIUM", action=ACTION_SUGGEST,
        topics=["tax", "origin"], quotes=q,
        problem="공급자가 FTA 원산지 증빙을 제공하도록 했지만, 그 증빙이 부적정해 협정관세 적용이 거부되거나 사후 추징될 때 누가 부담하는지 정하지 않았다.",
        risk_to_us="수입 신고 후 원산지 검증으로 협정관세가 배제되면 일반 관세와 가산세를 수입자인 우리가 먼저 납부해야 한다.",
        loss_path="원산지 검증 → 증빙 부적정 → 관세·가산세 추징 → 공급자에게 구상할 근거 없음",
        action_text="원산지 증빙 부적정으로 인한 추징 세액·가산세를 공급자가 배상한다는 조항을 넣는다.",
        edits=edits, statutes=S.kr("fta_special"),
        checks=[{"what": "공급자의 인증수출자 번호와 원산지신고 문안 확인", "who": "물류·관세 담당", "when": "첫 선적 전"}],
        family="international_sale_of_goods",
    )]


# ── S9. 제품 적합성 증빙 ─────────────────────────────────────────────────────

_RX_ECO = re.compile(r"PFC[\s-]*FREE|PFAS[\s-]*free|친환경|무독성|non[- ]toxic|REACH|OEKO|formaldehyde[- ]free|lead[- ]free|BPA[- ]free|방염|flame[- ]retardant", re.I)
_RX_CERT = re.compile(r"시험\s*성적서|test\s+report|certificat|인증서|적합성\s*(?:증빙|확인)|declaration\s+of\s+conformity", re.I)


def conformity_evidence(ctx: Ctx) -> list[Finding]:
    if not ctx.buyer_side:
        return []
    m = _RX_ECO.search(ctx.text)
    if not m or ctx.has(_RX_CERT):
        return []
    q = quote_around(ctx.text, m.start(), m.end(), before=40, after=30)
    claim = m.group(0)
    qpath, qko = _para_line(ctx, re.compile(r"품질|규격|사양"), "ko")
    o_ko, t_ko, o_en, t_en = _labels(ctx)
    art = _article_of(qpath)
    edits = [
        Edit(location=qpath or "품질 조항", target="", edit_type="insert_after", lang="ko",
             replacement=(f"{t_ko}은 품명·규격에 표시된 친환경·안전 표시(“{claim}” 등)를 입증하는 공인 시험성적서를 선적 전에 {o_ko}에게 제공하고, "
                          f"그 표시가 사실과 다른 경우 해당 물품은 부적합 물품으로 본다.")),
        Edit(location=f"Article {art}" if art else "quality clause", target="", edit_type="insert_after", lang="en",
             replacement=(f"{t_en} shall provide {o_en}, before shipment, with test reports from an accredited laboratory substantiating any "
                          f"environmental or safety claims in the description (including \"{claim}\"), and goods not conforming to such claims "
                          f"shall be deemed Defective Goods.")),
    ]
    return [Finding(
        code="conformity_evidence", title=f"“{claim}” 표기에 대한 시험성적서 제공 의무 없음", path=qpath or ctx.layout.path(m.start()), risk="LOW",
        action=ACTION_SUGGEST, topics=["quality", "compliance"], quotes=[q],
        problem=f"품명·규격에 “{claim}” 같은 친환경·안전 표시가 있지만 이를 입증하는 시험성적서·적합성 증빙 제공 의무가 없다.",
        risk_to_us="이 원단으로 만든 제품에 같은 표시를 하거나 고객이 증빙을 요구하면 근거 자료가 없다 — 표시가 사실과 다르면 제품 표시·광고 책임은 판매자인 우리가 진다.",
        loss_path="고객·당국의 증빙 요구 → 공급자 자료 없음 → 표시 철회·회수 비용",
        action_text="표시 사항에 대한 공인 시험성적서를 선적 전 제공하고, 표시와 다르면 부적합품으로 보는 조항을 넣는다.",
        edits=edits, statutes=S.cisg("35"),
        checks=[{"what": f"“{claim}” 등 표시가 수입국 규제·고객 요구 기준에 해당하는지 확인", "who": "품질·사업부", "when": "첫 선적 전"}],
        family="international_sale_of_goods",
    )]


# ── 좋은 조항(현행 유지) ──────────────────────────────────────────────────────

_GOOD: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("good_deemed_acceptance", "공급자 무응답 시 검수 결과 승인 간주", re.compile(r"이의\s*제기가\s*없을\s*경우[^.\n]{0,40}승인한\s*것으로\s*본다|failure\s+to\s+object\s+constitutes", re.I),
     "공급자가 기한 내 반박하지 않으면 우리 검수 결과가 확정된다 — 공제 다툼을 줄이는 유리한 조항."),
    ("good_quantity_tolerance", "수량 허용 오차와 실수량 정산", re.compile(r"허용\s*오차\s*정산|±\s*\d+\s*%[^.\n]{0,80}(?:실수량|실제)|actual\s+shipped\s+and\s+accepted\s+quantity", re.I),
     "허용 오차 안의 증감은 실제 선적·합격 수량으로 정산한다 — 과다 청구를 막는다."),
    ("good_return_cost", "반송 비용 공급자 부담", re.compile(r"반송[^.\n]{0,60}(?:비용|물류비)[^.\n]{0,40}을\"?이?\s*전액\s*부담|returned\s+at\s+Seller'?s\s+sole\s+expense", re.I),
     "불량품 반송 비용을 공급자가 전부 부담한다."),
    ("good_fixed_account", "지급 계좌 특정", re.compile(r"IBAN\s*:", re.I), "지급 계좌를 계약에 특정해 임의 변경 위험을 줄였다(변경 검증 절차는 별도 권고)."),
    ("good_export_vat", "수출 통관·영세율 증빙 협조 구조", re.compile(r"EU\s*역외\s*반출\s*증빙|proof\s+of\s+export\s+outside\s+the\s+EU", re.I),
     "공급자가 수출 통관을 맡고 우리는 반출 증빙에만 협조한다 — 이탈리아 부가세 부담이 우리에게 오지 않는 구조."),
)


def good_clauses(ctx: Ctx) -> list[Finding]:
    out: list[Finding] = []
    if not ctx.buyer_side:
        return out
    for code, title, rx, why in _GOOD:
        hit = ctx.find(rx, before=60, after=80)
        if not hit:
            continue
        q, path = hit
        out.append(Finding(code=code, title=f"{title} — 현행 유지", path=path, risk="LOW", action=ACTION_KEEP, topics=["keep"], quotes=[q],
                           problem=why, risk_to_us=why, loss_path="", action_text="현행 유지", family="international_sale_of_goods"))
    return out


def run_sale(ctx: Ctx) -> list[Finding]:
    out: list[Finding] = []
    for fn in (incoterms, shipment_deadline, advance_and_delay_remedies, balance_vs_claim, latent_defects, quality_objectivity,
               remedies, origin_duty, conformity_evidence, good_clauses):
        out.extend(fn(ctx))
    return out


#: 수정 문안의 [  ] 가 무엇의 빈칸인지 — 전달본이 문장 조각 대신 항목 이름으로 적는다(2026-11-27).
UNDECIDED_LABELS: dict[str, list[str]] = {
    "incoterms_unselected": ["지정 선적항(또는 인도 장소)"],
    "advance_and_delay_remedies": ["해제 유예 기간(일)", "선급금 반환 기한(영업일)"],
    "balance_claim_timing": ["잔금 지급 기한(검수 완료 후 일)"],
    "latent_defects_excluded": ["숨은 하자 통지 기간(일)", "숨은 하자 클레임 기간(개월)"],
    "quality_subjective": ["그레이스케일 등급", "ΔE 허용치", "치수 허용 오차(cm)"],
    "remedies_deduction_only": ["교체품 재선적 기한(일)"],
    "shipment_deadline_blank": ["선적 기한(주)"],
}
