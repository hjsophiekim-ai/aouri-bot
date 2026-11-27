"""크로스보더 공통 체크리스트 — 모든 국제계약.

각 항목은 조항이 **있는지**가 아니라 내용이 **확정됐고 서로 맞는지**를 본다. 해당 신호가 없으면 아무것도 만들지 않는다
(예: 제재·수출통제는 품목·국가 신호가 있을 때만).
"""
from __future__ import annotations

import re

from runtime.review.cross_border import statutes as S
from runtime.review.cross_border.context import Ctx
from runtime.review.cross_border.evidence import quote_around
from runtime.review.cross_border.findings import (
    ACTION_CONFIRM, ACTION_KEEP, ACTION_MUST, ACTION_SUGGEST, Edit, Finding,
)
from runtime.review.cross_border.signals import COUNTRIES, cisg_status
from runtime.review.cross_border.types import INTERNATIONAL_SALE_OF_GOODS

_RX_GOV = re.compile(r"준거법|governing\s+law|governed\s+by|laws?\s+of\s+(?:the\s+)?(?:State|Republic|Province)", re.I)
_RX_ALT_KO = re.compile(r"\(\s*또는\s*[^()]{1,40}\)|(?<=[가-힣)])\s*또는\s+[가-힣A-Za-z ]{1,20}?법")
_RX_ALT_EN = re.compile(r"\blaws?\s+of\s+[A-Z][A-Za-z ]{1,40}\s+or\s+(?:the\s+)?(?:laws?\s+of\s+)?[A-Z][A-Za-z ]{1,40}|\bor\s+(?:a\s+)?neutral\s+(?:country|jurisdiction)", re.I)
_RX_NEUTRAL = re.compile(r"중립국|neutral\s+(?:country|jurisdiction|law)", re.I)
_RX_CISG = re.compile(r"\bCISG\b|국제물품매매계약에\s*관한\s*(?:유엔|국제연합)\s*협약|Convention\s+on\s+Contracts\s+for\s+the\s+International\s+Sale", re.I)
_RX_CISG_EXCLUDED = re.compile(r"(?:CISG|Convention)[^.\n]{0,60}(?:shall\s+not\s+apply|is\s+(?:hereby\s+)?excluded|적용하지\s*아니|배제)", re.I)

_LAW_KO = {"대한민국": "Korea", "한국": "Korea", "뉴욕": "New York", "이탈리아": "Italy", "독일": "Germany", "중국": "China",
           "일본": "Japan", "싱가포르": "Singapore", "영국": "England", "미국": "United States", "스위스": "Switzerland"}
_LAW_EN = {"Republic of Korea": "Korea", "Korea": "Korea", "Korean": "Korea", "New York": "New York", "Italy": "Italy", "Italian": "Italy",
           "Germany": "Germany", "German": "Germany", "China": "China", "PRC": "China", "Japan": "Japan", "Singapore": "Singapore",
           "England": "England", "English law": "England", "Switzerland": "Switzerland", "Swiss": "Switzerland"}

# 중재기관: 키 → (국문 이름, 국문 규칙, 기본 중재지 국문, 영문 이름, 영문 규칙, 영문 중재지)
INSTITUTIONS: dict[str, tuple[str, str, str, str, str, str]] = {
    "KCAB": ("대한상사중재원(KCAB)", "국제중재규칙", "대한민국 서울", "the Korean Commercial Arbitration Board (KCAB)",
             "International Arbitration Rules", "Seoul, Republic of Korea"),
    "SIAC": ("싱가포르국제중재센터(SIAC)", "중재규칙", "싱가포르", "the Singapore International Arbitration Centre (SIAC)",
             "Arbitration Rules", "Singapore"),
    "ICC": ("국제상업회의소(ICC) 국제중재법원", "중재규칙", "[중재지]", "the International Chamber of Commerce (ICC)",
            "Rules of Arbitration", "[seat]"),
    "HKIAC": ("홍콩국제중재센터(HKIAC)", "기관중재규칙", "홍콩", "the Hong Kong International Arbitration Centre (HKIAC)",
              "Administered Arbitration Rules", "Hong Kong"),
    "CIETAC": ("중국국제경제무역중재위원회(CIETAC)", "중재규칙", "[중재지]", "the China International Economic and Trade Arbitration Commission (CIETAC)",
               "Arbitration Rules", "[seat]"),
    "LCIA": ("런던국제중재법원(LCIA)", "중재규칙", "영국 런던", "the London Court of International Arbitration (LCIA)",
             "Arbitration Rules", "London, England"),
}
_RX_INST = re.compile(r"\b(SIAC|ICC|HKIAC|CIETAC|LCIA|KCAB)\b|(대한상사중재원)|(싱가포르\s*국제\s*중재)|(Korean\s+Commercial\s+Arbitration\s+Board)"
                      r"|(Singapore\s+International\s+Arbitration)|(중국\s*국제\s*경제\s*무역\s*중재)", re.I)
_RX_SEAT = re.compile(r"중재지|seat\s+of\s+(?:the\s+)?arbitration|place\s+of\s+arbitration|seated\s+in|(?:서울|싱가포르|홍콩|런던)에서\s*(?:진행|행)", re.I)
_RX_ARBITRATORS = re.compile(r"중재인\s*(?:의\s*수|\d|[일삼]\s*인|1인|3인)|(?:\d|[일이삼])\s*인의?\s*중재인|(?:one|three|sole|single|\d)\s+(?:\(\d\)\s+)?arbitrators?|sole\s+arbitrator|\bby\s+(?:one|three)\s+arbitrators?", re.I)
_RX_COURT = re.compile(r"(?:courts?\s+(?:of|in|located\s+in)\s+(?P<en>[A-Z][A-Za-z ,]{2,60}?)(?:\s+shall|\s+have|,|\.|\s+for))|(?P<ko>[가-힣]{2,10})\s*(?:지방)?법원을?\s*(?:전속|합의)?\s*관할", re.I)
_RX_EXCLUSIVE = re.compile(r"exclusive\s+jurisdiction|전속\s*관할", re.I)


def _inst_key(m: re.Match[str]) -> str:
    s = m.group(0).upper()
    if "대한상사" in m.group(0) or "KOREAN" in s:
        return "KCAB"
    if "싱가포르" in m.group(0) or "SINGAPORE" in s:
        return "SIAC"
    if "중국" in m.group(0):
        return "CIETAC"
    return s.strip()


def _laws(text: str, table: dict[str, str]) -> set[str]:
    return {v for k, v in table.items() if re.search(rf"(?<![A-Za-z]){re.escape(k)}(?![A-Za-z])", text)}


def _sentence_with(line: str, rx: re.Pattern[str]) -> str:
    """줄 안에서 rx 가 든 문장 그대로."""
    m = rx.search(line)
    if not m:
        return ""
    # 문장 경계: "…다." / ". " / 항 머리 "…(Governing Law & Arbitration): "
    starts = [x.end() for x in re.finditer(r"다\.\s*|\.\s+|\):\s+|:\s+(?=[가-힣A-Z\"“])", line[:m.start()])]
    s = starts[-1] if starts else 0
    e_m = re.search(r"다\.|\.(?:\s|$)", line[m.end():])
    e = m.end() + e_m.end() if e_m else len(line)
    return line[s:e].strip()


# ── 1. 준거법 ────────────────────────────────────────────────────────────────

def governing_law(ctx: Ctx) -> list[Finding]:
    p = ctx.pair(_RX_GOV)
    if p is None:
        anchor = ctx.find(re.compile(r"중재|arbitrat|관할|jurisdiction|dispute", re.I)) or ctx.find(re.compile(r"\S.{10,80}"))
        if not anchor:
            return []
        q, path = anchor
        return [Finding(
            code="governing_law_missing", title="준거법 미지정", path=path or "계약 전체", risk="HIGH", action=ACTION_MUST,
            topics=["dispute", "governing_law"], quotes=[q],
            problem="계약에 준거법 조항이 없다. 분쟁이 생기면 어느 나라 법으로 계약을 해석할지부터 다투게 된다.",
            risk_to_us="준거법이 없으면 법원·중재판정부가 국제사법(저촉규범)으로 준거법을 정한다 — 상대방 소재국 법이 적용될 수 있어 "
                       "계약 문언의 효과(책임 제한·해지·손해배상)를 예측할 수 없다.",
            loss_path="분쟁 발생 → 준거법 조항 없음 → 상대방 국가 법 적용 가능성·선결 쟁점 비용 → 회수 지연",
            action_text="준거법 조항을 신설한다(우리에게 익숙한 대한민국 법을 우선 제안).",
            edits=[Edit(location=path or "분쟁해결 조항", target="", edit_type="insert_after",
                        replacement="본 계약은 대한민국 법에 따라 규율되고 해석된다.", lang="ko"),
                   Edit(location=path or "dispute resolution clause", target="", edit_type="insert_after",
                        replacement="This Agreement shall be governed by and construed in accordance with the laws of the Republic of Korea.",
                        lang="en")] if ctx.assessment.bilingual else
                  [Edit(location=path or "dispute resolution clause", target="", edit_type="insert_after",
                        replacement="This Agreement shall be governed by and construed in accordance with the laws of the Republic of Korea.",
                        lang="en" if not re.search(r"[가-힣]", q) else "ko")],
            negotiation="대한민국 법을 우선 요청하고, 상대방이 거절하면 중립국 법(예: 싱가포르법·스위스법) 중 하나로 확정한다 — 어느 쪽이든 하나로 정하는 것이 핵심이다.",
            statutes=[], checks=[{"what": "준거법을 어느 나라 법으로 할지 상대방과 합의", "who": "사업부(협상)·법무", "when": "서명 전"}],
        )]
    ko_line, en_line = p.ko, p.en
    # 항 머리("준거법 및 중재 (Governing Law …):")가 아니라 준거법을 정하는 문장
    rx_sent = re.compile(r"준거법으로|준거법은|governed\s+by|governing\s+law\s+(?:of|shall)", re.I)
    ko_s = (_sentence_with(ko_line, rx_sent) or _sentence_with(ko_line, _RX_GOV)) if ko_line else ""
    en_s = (_sentence_with(en_line, rx_sent) or _sentence_with(en_line, _RX_GOV)) if en_line else ""
    alt_ko = _RX_ALT_KO.search(ko_s) if ko_s else None
    alt_en = _RX_ALT_EN.search(en_s) if en_s else None
    neutral_ko, neutral_en = bool(_RX_NEUTRAL.search(ko_s)), bool(_RX_NEUTRAL.search(en_s))
    laws_ko, laws_en = _laws(ko_s, _LAW_KO), _laws(en_s, _LAW_EN)
    mismatch = bool(ko_s and en_s) and (bool(alt_ko) != bool(alt_en) or neutral_ko != neutral_en or laws_ko != laws_en)
    undetermined = bool(alt_ko or alt_en or neutral_ko or neutral_en)
    out: list[Finding] = []
    cisg_on = bool(_RX_CISG.search(ko_s + " " + en_s)) and not _RX_CISG_EXCLUDED.search(ctx.text)
    if undetermined or mismatch:
        prev = ctx.assessment.prevailing_language
        prevailing_text = en_s if prev == "en" else ko_s if prev == "ko" else ""
        prevailing_alt = bool(prevailing_text) and bool(_RX_ALT_KO.search(prevailing_text) or _RX_ALT_EN.search(prevailing_text)
                                                       or _RX_NEUTRAL.search(prevailing_text))
        risk = "HIGH" if (not prevailing_text or prevailing_alt) else "MEDIUM"
        alt_phrase = alt_ko.group(0).strip() if alt_ko else (alt_en.group(0).strip() if alt_en else "")
        result = ""
        if prev and prevailing_text and not prevailing_alt:
            result = (f" 언어 우선 조항({'영문' if prev == 'en' else '국문'} 우선)에 따라 {'영문' if prev == 'en' else '국문'} 문언대로 "
                      + ("대한민국 법" if "Korea" in (laws_en if prev == "en" else laws_ko) else "해당 국가 법")
                      + (" + CISG" if cisg_on else "") + " 로 해석될 가능성이 크지만, 다른 언어본의 선택 문구가 남아 있으면 상대방이 이를 근거로 준거법을 다툴 수 있다.")
        # 선택형 문구를 지운 문장 전체를 교체 문안으로 — 변경추적이 그 문장에 정확히 들어간다
        fixed: list[Edit] = []
        if alt_ko:
            fixed.append(Edit(location=p.path, target=ko_s, lang="ko",
                              replacement=re.sub(r"\s{2,}", " ", ko_s.replace(alt_ko.group(0), "")).strip()))
        if alt_en:
            keep = re.split(r"\s+or\s+", alt_en.group(0), maxsplit=1)[0]
            fixed.append(Edit(location=p.path, target=en_s, lang="en",
                              replacement=re.sub(r"\s{2,}", " ", en_s.replace(alt_en.group(0), keep)).strip()))
        out.append(Finding(
            code="governing_law_undetermined", title="준거법 선택형 문구·국영문 불일치", path=p.path, risk=risk,
            action=ACTION_MUST if risk == "HIGH" else ACTION_SUGGEST, topics=["dispute", "governing_law"],
            quotes=[x for x in (ko_s, en_s) if x],
            problem=("준거법이 " + (f"“{alt_phrase}” 처럼 선택형으로 적혀 하나로 확정되지 않았고" if undetermined else "")
                     + (", 국문과 영문의 준거법 문언이 서로 다르다." if mismatch else ".")).replace("고,", "고") + result,
            risk_to_us="준거법이 하나로 정해지지 않으면 분쟁 초기에 어느 법을 적용할지부터 다투게 되고, 그 사이 대금 회수·손해배상 청구가 늦어진다.",
            loss_path="품질·납기 분쟁 → 준거법 선택 문구로 선결 다툼 → 중재·소송 비용과 기간 증가",
            action_text="선택형 문구(“또는 …”)를 지워 준거법을 하나로 확정하고, 국문·영문을 같은 문언으로 맞춘다.",
            edits=fixed,
            recommendation=("CISG 가 적용되는 매매라면 'CISG 가 규율하지 않는 사항은 대한민국 법에 따른다'는 보충 관계를 함께 적어 두면 해석이 분명해진다."
                            if cisg_on else ""),
            statutes=S.cisg("1", "6") if cisg_on else [],
            negotiation="영문 우선 조항이 있어 협상 부담이 작은 정리 수정이다 — 국문 선택 문구 삭제를 그대로 요청한다." if prev else "",
        ))
    # CISG 적용 관계(국제 물품매매)
    if ctx.intl_type == INTERNATIONAL_SALE_OF_GOODS:
        theirs = [c for c in ctx.assessment.countries if c != "Korea"]
        statuses = {c: cisg_status(c) for c in theirs}
        if cisg_on and statuses and all(v == "체약국" for v in statuses.values()) and ctx.assessment.korea_party:
            pass   # CISG 지정 + 양국 체약국 — 정합. 별도 지적 없음(현행 유지 기록은 good_clauses)
        elif not cisg_on and not _RX_CISG_EXCLUDED.search(ctx.text) and statuses and all(v == "체약국" for v in statuses.values()) and ctx.assessment.korea_party:
            q = ko_s or en_s
            out.append(Finding(
                code="cisg_auto_apply", title="CISG 자동 적용 여부 미정리", path=p.path, risk="LOW", action=ACTION_SUGGEST,
                topics=["governing_law"], quotes=[q],
                problem="양 당사자 소재국이 모두 CISG 체약국이라 준거법 조항과 별개로 CISG 가 자동 적용된다(제1조 제1항 (a)). 계약은 이 점을 정리하지 않았다.",
                risk_to_us="검사·통지 기간(제38·39조), 해제 요건 등 CISG 규칙이 계약 문언의 빈 곳을 채우게 되어 예상과 다른 결과가 나올 수 있다.",
                loss_path="하자·지연 분쟁 → CISG 규칙 적용 → 계약에 없는 요건(통지 기간 등)으로 권리 상실 가능",
                action_text="CISG 를 적용할지(보충법 지정) 배제할지(제6조) 계약에 명시한다.",
                statutes=S.cisg("1", "6"),
            ))
    return out


# ── 2. 분쟁해결 ──────────────────────────────────────────────────────────────

def dispute_resolution(ctx: Ctx) -> list[Finding]:
    p = ctx.pair(re.compile(r"중재|arbitrat", re.I))
    if p is not None:
        # 중재기관 이름이 든 문장 — 항 머리("준거법 및 중재")의 '중재'를 잡지 않게
        ko_s = (_sentence_with(p.ko, _RX_INST) or _sentence_with(p.ko, re.compile(r"중재에\s*의|중재로|중재\s*절차"))) if p.ko else ""
        en_s = (_sentence_with(p.en, _RX_INST) or _sentence_with(p.en, re.compile(r"by\s+arbitration|arbitration\s+(?:in|under)", re.I))) if p.en else ""
        both = f"{ko_s} {en_s}"
        whole = f"{p.ko} {p.en}"   # 중재지·중재인 수·언어는 다음 문장에 이어 적는 경우가 많다 — 항 전체로 본다
        insts = list(dict.fromkeys(_inst_key(m) for m in _RX_INST.finditer(both)))
        alternative = len(insts) >= 2 and bool(re.search(r"또는|\bor\b", both))
        seat = bool(_RX_SEAT.search(whole))
        arbitrators = bool(_RX_ARBITRATORS.search(whole))
        language = re.search(r"영어|English|한국어|Korean\s+language", whole, re.I)
        missing = [x for x, ok in (("중재지(seat)", seat), ("중재인 수", arbitrators), ("중재 언어", bool(language))) if not ok]
        if not alternative and not missing:
            return []
        risk = "HIGH" if alternative or not seat else "MEDIUM"
        # 추천 기관: 우리가 한국 측이고 선택지에 KCAB 가 있으면 KCAB·서울, 아니면 첫 기관
        pick = "KCAB" if ("KCAB" in insts and ctx.korean_side) else (insts[0] if insts else "KCAB")
        k_name, k_rules, k_seat, e_name, e_rules, e_seat = INSTITUTIONS.get(pick, INSTITUTIONS["KCAB"])
        lang_ko = "영어" if (language and re.search(r"영어|English", language.group(0), re.I)) or not language else "한국어"
        lang_en = "English" if lang_ko == "영어" else "Korean"
        edits: list[Edit] = []
        mk = re.search(r"(?:싱가포르|대한상사|국제상업|홍콩|중국|런던|SIAC|ICC|KCAB|HKIAC|CIETAC|LCIA)[^.]*?중재에\s*의(?:하여|해)\s*최종\s*해결한다\.", ko_s)
        if mk:
            edits.append(Edit(location=p.path, target=mk.group(0),
                              replacement=f"{k_name}의 {k_rules}에 따라 {k_seat}을 중재지로 하여 1인의 중재인이 {lang_ko}로 진행하는 중재에 의하여 최종 해결한다.",
                              lang="ko"))
        me = re.search(r"(?:shall\s+be\s+)?finally\s+resolved\s+by\s+arbitration[^.]*\.", en_s, re.I)
        if me:
            edits.append(Edit(location=p.path, target=me.group(0),
                              replacement=(f"shall be finally resolved by arbitration administered by {e_name} in accordance with its {e_rules}. "
                                           f"The seat of arbitration shall be {e_seat}, the tribunal shall consist of one (1) arbitrator, "
                                           f"and the language of the arbitration shall be {lang_en}."),
                              lang="en"))
        prob = []
        if alternative:
            prob.append(f"중재기관이 “{' 또는 '.join(insts)}” 처럼 선택형으로 적혀 어느 기관에 신청해야 하는지 정해지지 않았다(병리적 중재조항)")
        if missing:
            prob.append("중재 조항에 " + "·".join(missing) + "에 관한 정함이 없다")
        return [Finding(
            code="arbitration_pathological", title="중재기관 선택형·중재지 미지정", path=p.path, risk=risk,
            action=ACTION_MUST if risk == "HIGH" else ACTION_SUGGEST, topics=["dispute"],
            quotes=[x for x in (ko_s, en_s) if x], problem=", ".join(prob) + ".",
            risk_to_us="선택형 중재조항은 상대방이 다른 기관에 먼저 신청하거나 관할 항변으로 절차를 지연시킬 수 있고, 중재지가 없으면 중재판정 취소·집행의 "
                       "기준 법원이 불분명해진다. 계약 금액에 비해 중재 비용이 커질 수 있어 신속절차·단독 중재인이 실익이 있다.",
            loss_path="품질·대금 분쟁 → 중재기관·중재지 다툼 → 절차 지연·비용 증가 → 소액 청구는 사실상 포기",
            action_text=f"중재기관을 하나({k_name})로 정하고 중재지·중재인 수·언어를 명시한다.",
            edits=edits,
            negotiation=(f"{k_name}·{k_seat} 단독 중재를 우선 제안하고, 상대방이 중립지를 원하면 싱가포르(SIAC) 단독으로 확정한다 — "
                         "어느 쪽이든 하나로 정하는 것이 핵심이다."),
            statutes=[S.NEW_YORK],
            checks=[{"what": "중재기관·중재지 선택을 상대방과 확정", "who": "사업부(협상)·법무", "when": "서명 전"}],
        )]
    # 법원 관할
    m = _RX_COURT.search(ctx.text)
    if m:
        place = (m.group("en") or m.group("ko") or "").strip()
        foreign = bool(place) and not re.search(r"Korea|Seoul|서울|대한민국|한국", place) and (
            any(k in place for k in COUNTRIES) or bool(m.group("en")))
        if not foreign:
            return []
        q = quote_around(ctx.text, m.start(), m.end(), before=40, after=80)
        exclusive = bool(_RX_EXCLUSIVE.search(q))
        return [Finding(
            code="foreign_court_jurisdiction", title="외국 법원 " + ("전속" if exclusive else "") + "관할 — 집행·비용 부담",
            path=ctx.layout.path(m.start()), risk="MEDIUM", action=ACTION_SUGGEST, topics=["dispute"], quotes=[q],
            problem=f"분쟁을 {place} 법원{'의 전속' if exclusive else ''}관할로 정했다.",
            risk_to_us="외국 법원 소송은 현지 대리인 비용이 크고, 한국에서 그 판결을 집행하려면 별도의 승인 절차(상호보증 등 요건)를 거쳐야 한다. "
                       "중재판정은 뉴욕협약으로 대부분 국가에서 집행이 쉽다.",
            loss_path="상대방 채무불이행 → 외국 법원 소송 강제 → 비용·기간 부담 → 소액 청구 포기",
            action_text="중재(단독 중재인·신속절차)로 바꾸거나, 최소한 비전속 관할로 완화해 우리 법원에서도 제소할 수 있게 한다.",
            statutes=[S.KR["civil_217"], S.NEW_YORK],
            negotiation="상대방 본거지 법원을 고집하면 비전속 관할로 완화하는 것을 대안으로 둔다.",
        )]
    # 분쟁해결 조항 자체가 없음
    anchor = ctx.find(_RX_GOV) or ctx.find(re.compile(r"\S.{10,80}"))
    if not anchor:
        return []
    q, path = anchor
    return [Finding(
        code="dispute_missing", title="분쟁해결 조항 없음", path=path or "계약 전체", risk="HIGH", action=ACTION_MUST,
        topics=["dispute"], quotes=[q],
        problem="계약에 분쟁해결(중재·관할) 조항이 없다.",
        risk_to_us="분쟁 시 어느 나라 법원에 제소할지부터 다투게 되고, 상대방 소재국 법원에서 소송해야 할 수 있다.",
        loss_path="분쟁 발생 → 관할 미정 → 상대방 국가 법원 제소 강제 → 비용·집행 부담",
        action_text="중재 조항(기관·중재지·중재인 수·언어)을 신설한다.",
        statutes=[S.NEW_YORK],
    )]


# ── 3. 언어 ──────────────────────────────────────────────────────────────────

def language(ctx: Ctx) -> list[Finding]:
    if not ctx.assessment.bilingual or ctx.assessment.prevailing_language:
        return []
    q = ctx.find(re.compile(r"\S.{20,100}"))
    if not q:
        return []
    return [Finding(
        code="no_prevailing_language", title="국·영 병기인데 우선 언어 조항 없음", path="계약 전체", risk="MEDIUM",
        action=ACTION_SUGGEST, topics=["language"], quotes=[q[0]],
        problem="계약이 국문과 영문을 함께 적었는데 두 언어가 다를 때 어느 쪽이 우선하는지 정하지 않았다.",
        risk_to_us="두 언어본의 의미가 다르면 각자 유리한 언어본을 주장하게 된다.",
        loss_path="해석 분쟁 → 우선 언어 없음 → 각자 유리한 문언 주장 → 분쟁 장기화",
        action_text="우선 언어 조항을 넣는다(상대방이 읽을 수 있는 영문 우선이 일반적).",
    )]


# ── 4. 서류 간 우선순위 ───────────────────────────────────────────────────────

_RX_DOCS = re.compile(r"견적송장|Proforma\s+Invoice|\bP/?O\b|Purchase\s+Order|발주서|Commercial\s+Invoice|상업송장|일반\s*거래?\s*약관|General\s+(?:Terms|Conditions)|부동문자", re.I)
_RX_PRECEDENCE = re.compile(r"우선하여\s*적용|우선\s*적용|supersede|take\s+precedence|shall\s+prevail\s+over|우선한다", re.I)


def document_precedence(ctx: Ctx) -> list[Finding]:
    if not ctx.has(_RX_DOCS):
        return []
    found = None
    for rx in (re.compile(r"(?:모든\s*조항은|본\s*계약(?:서)?(?:의\s*조항)?은)[^.\n]{0,160}우선하여\s*적용"),
               re.compile(r"(?:terms\s+of\s+this\s+Agreement|This\s+Agreement)[^.\n]{0,80}(?:supersede|take\s+precedence|prevail)", re.I),
               _RX_PRECEDENCE):
        m = rx.search(ctx.text)
        line = ctx.layout.paragraph_text(m.start()) if m else ""
        if m and re.search(r"영문|국문|English\s+version|Korean\s+version|language", line, re.I):
            m = None   # 언어 우선 조항("영문본이 우선한다")은 서류 간 우선순위가 아니다
        if m and not ctx.layout.region(m.start()):
            found = (quote_around(ctx.text, m.start(), m.end(), before=10, after=80), ctx.layout.path(m.start()))
            break
    if found:
        q, path = found
        return [Finding(code="good_precedence", title="서류 간 우선순위 조항 — 현행 유지", path=path, risk="LOW", action=ACTION_KEEP,
                        topics=["documents"], quotes=[q],
                        problem="계약서가 견적송장·발주서·상업송장과 상대방 부동문자 약관보다 우선한다고 정했다.",
                        risk_to_us="상대방 약관의 짧은 클레임 기간·만기일 같은 불리한 조건을 차단한다 — 현행 유지.",
                        loss_path="", action_text="현행 유지")]
    q, path = ctx.find(_RX_DOCS)  # type: ignore[misc]
    # 상대방 부동문자 약관·견적송장이 거래 서류로 쓰이면 충돌 위험이 실재한다(MEDIUM). 발주서 언급뿐이면 참고(LOW).
    risk = "MEDIUM" if ctx.has(re.compile(r"약관|부동문자|General\s+(?:Terms|Conditions)|Standard\s+Terms|Proforma|견적송장", re.I)) else "LOW"
    return [Finding(
        code="precedence_missing", title="계약서와 PI·PO·약관의 우선순위 미정", path=path, risk=risk, action=ACTION_SUGGEST,
        topics=["documents"], quotes=[q],
        problem="계약이 견적송장·발주서 등 다른 거래 서류를 언급하지만 서로 충돌할 때 무엇이 우선하는지 정하지 않았다.",
        risk_to_us="상대방 서류의 부동문자 약관(짧은 클레임 기간, 책임 제한)이 계약서 조건을 덮을 수 있다.",
        loss_path="품질 분쟁 → 상대방 약관의 단기 클레임 기간 주장 → 클레임 권리 상실",
        action_text="본 계약서가 다른 모든 거래 서류·약관보다 우선한다는 조항을 넣는다.",
    )]


# ── 5. 지급 보호(매매 외 유형) ───────────────────────────────────────────────

_RX_ADV_REFUND = re.compile(r"선급금[^.\n]{0,80}(?:반환|환급)|(?:refund|return|repay)[^.\n]{0,60}advance|advance[^.\n]{0,80}(?:refund|return|repaid)", re.I)
_RX_TERMINATION = re.compile(r"해제|해지|terminat|rescind|rescission|avoid\s+(?:the\s+)?(?:contract|agreement)", re.I)


def payment_protection(ctx: Ctx) -> list[Finding]:
    if ctx.intl_type == INTERNATIONAL_SALE_OF_GOODS or not ctx.buyer_side:
        return []   # 매매는 checklist_sale 이 지체 구제수단과 함께 본다
    f = ctx.facts
    if f.advance_pct is None or f.advance_pct < 20 or ctx.has(_RX_ADV_REFUND):
        return []
    return [Finding(
        code="advance_unprotected", title=f"선급금 {f.advance_pct}% 반환·해제 장치 없음", path=ctx.layout.path(ctx.text.find(f.split_quote)) or "",
        risk="MEDIUM", action=ACTION_SUGGEST, topics=["payment"], quotes=[f.split_quote],
        problem=f"계약 금액의 {f.advance_pct}%를 먼저 지급하는데, 상대방이 이행하지 않을 때 선급금을 돌려받는 조항과 해제권이 없다.",
        risk_to_us="상대방이 이행하지 않거나 파산하면 해외 소송·중재로 선급금을 회수해야 한다.",
        loss_path="상대방 불이행 → 반환 조항·해제권 없음 → 해외 회수 절차 → 선급금 손실",
        action_text="불이행 시 해제권과 선급금 반환 의무(지연이자 포함)를 넣는다. 금액이 크면 선급금 보증(APG)을 검토한다.",
    )]


# ── 6. 송금 계좌 ─────────────────────────────────────────────────────────────

_RX_ACCOUNT = re.compile(r"\bIBAN\b|계좌|bank\s+account|account\s+(?:no|number)", re.I)
_RX_ACCOUNT_CHANGE = re.compile(r"계좌[^.\n]{0,30}변경|변경[^.\n]{0,20}계좌|change[^.\n]{0,40}(?:bank\s+)?account|account[^.\n]{0,30}change", re.I)
_RX_FEES = re.compile(r"송금\s*수수료|은행\s*수수료|bank\s+charges?|remittance\s+(?:fee|charge)|charges?\s+(?:shall\s+be\s+)?borne", re.I)


def remittance_account(ctx: Ctx) -> list[Finding]:
    m = _RX_ACCOUNT.search(ctx.text)
    if not m or not ctx.buyer_side:
        return []
    if ctx.has(_RX_ACCOUNT_CHANGE):
        return []
    q = quote_around(ctx.text, m.start(), m.end(), before=80, after=80)
    path = ctx.layout.path(m.start())
    no_fee = not ctx.has(_RX_FEES)
    from runtime.review.cross_border.checklist_sale import _labels

    o_ko, t_ko, o_en, t_en = _labels(ctx)
    fee_ko = " 송금 수수료는 송금 은행 수수료는 송금인이, 수취 은행 수수료는 수취인이 각각 부담한다." if no_fee else ""
    fee_en = " Remitting bank charges shall be borne by the remitter and receiving bank charges by the beneficiary." if no_fee else ""
    edits = [
        Edit(location=path, target="", edit_type="insert_after", lang="ko",
             replacement=(f"지급 계좌의 변경은 {t_ko}의 권한 있는 서명권자가 서명한 서면 통지를 {o_ko}이 받고, {o_ko}이 기존 담당자에게 "
                          f"전화로 확인한 때에만 효력이 있다.{fee_ko}")),
        Edit(location=path, target="", edit_type="insert_after", lang="en",
             replacement=(f"Any change to the designated bank account shall be effective only upon {o_en}'s receipt of a written notice signed by "
                          f"an authorized signatory of {t_en} and {o_en}'s confirmation of such change by telephone with {t_en}'s existing "
                          f"contact person.{fee_en}")),
    ] if ctx.assessment.bilingual else [
        Edit(location=path, target="", edit_type="insert_after", lang="en",
             replacement=(f"Any change to the designated bank account shall be effective only upon {o_en}'s receipt of a written notice signed by "
                          f"an authorized signatory of {t_en} and {o_en}'s confirmation of such change by telephone with {t_en}'s existing "
                          f"contact person.{fee_en}"))]
    out = [Finding(
        code="account_change_verification", title="송금 계좌 변경 시 검증 절차 없음", path=path, risk="LOW", action=ACTION_SUGGEST,
        topics=["payment"], quotes=[q],
        problem="지급 계좌를 계약에 특정한 것은 좋지만, 계좌 변경 요청이 왔을 때의 확인 절차가 없다." + (" 송금 수수료 부담 주체도 정하지 않았다." if no_fee else ""),
        risk_to_us="해외 거래에서는 거래처를 사칭한 이메일로 계좌 변경을 요청하는 송금 사기가 잦다 — 잘못 보낸 대금은 회수가 어렵다.",
        loss_path="사칭 이메일의 계좌 변경 요청 → 검증 없이 송금 → 대금 이중 지급·회수 불능",
        action_text="계좌 변경은 서명된 서면과 기존 담당자 전화 확인을 모두 거친 경우에만 효력이 있다는 문구를 넣는다.",
        edits=edits,
        checks=[{"what": "송금 전 수취 계좌를 기존 담당자와 전화로 확인(이메일 지시만으로 변경 금지)", "who": "재경", "when": "매 송금 전"}],
    )]
    return out


# ── 7. 세금(원천징수) ────────────────────────────────────────────────────────

_RX_ROYALTY = re.compile(r"royalt(?:y|ies)|로열티|사용료|license\s+fee|service\s+fees?|용역\s*대가|consulting\s+fees?", re.I)
_RX_WHT = re.compile(r"원천징수|withhold|withholding|gross[- ]?up|tax(?:es)?\s+deducted", re.I)


def withholding_tax(ctx: Ctx) -> list[Finding]:
    from runtime.review.cross_border.types import INTERNATIONAL_LICENSE, INTERNATIONAL_SERVICES

    if ctx.intl_type not in (INTERNATIONAL_LICENSE, INTERNATIONAL_SERVICES):
        return []
    m = _RX_ROYALTY.search(ctx.text)
    if not m or ctx.has(_RX_WHT):
        return []
    q = quote_around(ctx.text, m.start(), m.end(), before=60, after=80)
    payer_is_us = ctx.buyer_side
    return [Finding(
        code="withholding_tax_missing", title="해외 지급 대가의 원천징수 조항 없음", path=ctx.layout.path(m.start()), risk="MEDIUM",
        action=ACTION_SUGGEST, topics=["tax"], quotes=[q],
        problem="해외 상대방에게 로열티·용역대가를 지급하는데 원천징수 처리(누가 부담하는지, 세액 공제 후 지급인지)를 정하지 않았다.",
        risk_to_us=("우리가 지급자라면 원천징수 의무를 진다 — 계약이 '세금 공제 없는 총액 지급'으로 읽히면 원천세를 우리가 추가 부담(gross-up)하게 될 수 있다."
                    if payer_is_us else "상대방이 원천징수 후 지급하면 수령액이 줄어든다 — 조세조약 제한세율 적용 서류를 미리 준비해야 한다."),
        loss_path="대가 지급 → 원천징수 미정 → 세액 추가 부담 또는 과소 수령",
        action_text="대가는 관련 법령상 원천징수 세액을 공제한 후 지급하고, 지급자는 납부 증빙을 제공하며, 조세조약 제한세율 적용에 협조한다는 조항을 넣는다.",
        statutes=S.kr("corp_tax_98"),
        checks=[{"what": "상대방 거주지국과의 조세조약 제한세율·거주자증명서 확인", "who": "재경·세무", "when": "첫 지급 전"}],
    )]


# ── 8. 불가항력 ──────────────────────────────────────────────────────────────

_RX_FM = re.compile(r"불가항력|force\s+majeure|천재지변|act\s+of\s+god", re.I)


def force_majeure(ctx: Ctx) -> list[Finding]:
    # 불가항력 조항은 이행하는 쪽(공급자·용역 제공자)의 면책 장치다 — 우리가 대금을 내고 물건·용역을 받는 쪽이면
    # 조항이 없는 편이 오히려 유리하고, 장기 불이행 시의 해제·반환은 지급 보호 항목이 다룬다.
    if ctx.has(_RX_FM) or ctx.buyer_side or not ctx.our_role:
        return []
    anchor = None
    for m in re.finditer(r"(?:선적|인도|납기|shipment|delivery)[^\n]{0,60}", ctx.text, re.I):
        if not ctx.layout.region(m.start()) and ctx.layout.article(m.start()):
            anchor = (quote_around(ctx.text, m.start(), m.end(), before=0, after=0), ctx.layout.path(m.start()))
            break
    if not anchor:
        return []
    q, path = anchor
    return [Finding(
        code="force_majeure_missing", title="불가항력 조항 없음", path=path, risk="LOW", action=ACTION_SUGGEST,
        topics=["delivery"], quotes=[q],
        problem="국제 운송·생산이 걸린 계약인데 불가항력(전쟁·항만 봉쇄·자연재해 등) 조항이 없다.",
        risk_to_us="불가항력 사유로 장기간 이행이 막혀도 계약을 끝낼 기준이 없어 선급금이 묶일 수 있다.",
        loss_path="장기 불가항력 → 해제 기준 없음 → 선급금 장기 동결",
        action_text="불가항력 사유·통지·장기화(예: [60]일) 시 해제와 선급금 반환을 정하는 조항을 넣는다.",
    )]


def run_common(ctx: Ctx) -> list[Finding]:
    out: list[Finding] = []
    for fn in (governing_law, dispute_resolution, language, document_precedence, payment_protection, remittance_account,
               withholding_tax, force_majeure):
        out.extend(fn(ctx))
    return out
