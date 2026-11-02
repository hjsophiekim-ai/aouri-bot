"""Transaction Reconstruction — 프로그램 협찬·PPL·브랜디드 콘텐츠 계약 (광고주 관점).

2026-10-21 지시
──────────────
실측(유튜브 채널 예능 프로그램 협찬 계약, 광고주 = 우리 회사):
  · 계약유형이 "지식재산권 실시허락(라이선스) 계약", 우리 지위가 "구매자/발주자" 로 나갔다 — 대가 목록에
    "마케팅 라이선스" 한 줄이 있다는 이유로 거래 실질 재판정이 라이선스를 급부의 중심으로 봤다.
  · 업로드 분류는 "라이선스/로열티" 규칙팩을 골라 "오픈소스 사용/라이선스 위반" HIGH 가 양도금지 조에 붙었다.
  · 정작 핵심 — "조회수 보장·최소 N회 개런티" 를 같은 조 다음 항이 "예정에 해당, 사전 협의로 변경" 으로
    무력화하는 충돌, 대가 목록이 준 마케팅 라이선스를 지식재산권 조가 "별도 사전 서면 합의" 로 다시 묶는
    충돌 — 은 지적되지 않았다.

이 모듈은 분류기보다 먼저 **거래 실질**을 세운다(research_model 과 같은 구조).

    협찬사(광고주)        협찬 대가를 지급하고 노출·콘텐츠·이용권을 받는다
    협찬 수령자(제작·채널)  프로그램을 기획·제작·게시하고 대가 목록의 사항을 제공한다
    급부                  노출(PPL·오프닝·쇼츠 등) + 마케팅 이용권
    대가                  협찬금

여기서 만드는 finding 은 원문 문형으로 찾은 조항에만 붙는다. 회사명·프로그램명·조항번호를 쓰지 않는다.
계약에 없는 금액·기간·수량은 만들지 않는다 — 그런 공백은 사업부 확인사항으로 낸다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CANONICAL_TYPE = "advertising_sponsorship"
LABEL = "협찬·스폰서십·PPL(광고) 계약"
SPONSOR_ROLE_LABEL = "광고주(협찬사 — 협찬금 지급, 노출·이용권 수령)"
RECIPIENT_ROLE_LABEL = "협찬 수령자(제작·채널 운영 — 노출·콘텐츠·이용권 제공)"
SPONSOR_SHORT = "광고주(협찬사)"
RECIPIENT_SHORT = "제작·채널 운영사"

_RX_SPONSOR = re.compile(r"협\s*찬|\bPPL\b|간접\s*광고|브랜디드\s*(?:콘텐츠|쇼츠)|스폰서|후\s*원|sponsor", re.IGNORECASE)
_RX_PAY = re.compile(
    r"협찬\s*(?:금|금액|대금|비)|협찬의\s*대가|광고비|후원금|스폰서(?:십)?\s*(?:비용|금액|대가)"
    r"|그에\s*대한\s*대가를\s*지급|협찬\s*(?:물품|제품|품)|(?:물품|제품)을?\s*(?:제공|지원|협찬)"
)
#: 협찬 수령자가 주는 것 — 노출·홍보 혜택. 이것이 없으면 협찬이 아니라 단순 제품 제공이다.
_RX_MEDIA = re.compile(
    r"프로그램|방송|채널|유튜브|YouTube|게시|노출|조회수|쇼츠|편성|로고|브랜드\s*(?:노출|표기)|홍보\s*(?:활동|업무|기회)"
    r"|스폰서십\s*혜택|협찬\s*고지|게재|부스|행사", re.IGNORECASE)
#: 모델료·원고료가 대가인 계약은 출연·콘텐츠 제작 계약이다 — 협찬 모델로 잡지 않는다.
_RX_PERFORMER_FEE = re.compile(r"모델료|원고료|출연료")
_RX_ONLINE = re.compile(r"YouTube|유튜브|인스타그램|틱톡|TikTok|웹\s*예능|온라인\s*(?:채널|플랫폼)|SNS|네이버\s*TV", re.IGNORECASE)
_RX_BROADCASTER = re.compile(r"지상파|종합편성|케이블\s*(?:TV|방송)|방송사업자|IPTV|홈쇼핑")

_RX_GUARANTEE = re.compile(r"보장|최소\s*\d|개런티|확약")
_RX_TENTATIVE = re.compile(r"예정에\s*해당|예정\s*사항|변동\s*가능|변경될\s*수\s*있|변경할\s*수\s*있|협의하여\s*변경")
_RX_CONSULT = re.compile(r"사전\s*협의")
_RX_CONSENT = re.compile(r"사전\s*(?:서면\s*)?(?:동의|승인)")
_RX_METRIC = re.compile(r"조회\s*수|노출\s*수|재생\s*수|도달|임프레션|impression|view", re.IGNORECASE)
_RX_MEASURE = re.compile(r"집계|산정\s*기준|공식\s*통계|애널리틱스|analytics|스튜디오\s*통계|조회수\s*증빙|결과\s*보고", re.IGNORECASE)
_RX_SHORTFALL = re.compile(r"미달|미달성|목표\s*미충족")
_RX_REFUND = re.compile(r"(?:불이행\s*(?:분|된[^.]{0,20}분)|미이행\s*분)[^.]{0,60}(?:정산|반환|반납|환급)|(?:정산|반환|반납|환급)[^.]{0,30}불이행\s*분")
_RX_SCHEDULE_VAR = re.compile(r"변동\s*가능|일정을?\s*(?:조정|변경|연장)|편성\s*변경|조정\s*또는\s*연장")
_RX_FINAL_DEADLINE = re.compile(r"늦어도|최종\s*(?:게시|방송|이행)\s*기한|까지\s*(?:게시|방송|방영)하지\s*(?:아니|못)")
_RX_PAY_CLAUSE = re.compile(r"세금계산서[^.]{0,40}(?:청구|발행)|(?:청구|지급)한다")
_RX_FIXED_DATE = re.compile(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일")
_RX_PAY_LINKED = re.compile(r"(?:게시|방송|방영|노출)\s*(?:완료|후|이후|확인)[^.]{0,40}(?:청구|지급)|(?:청구|지급)[^.]{0,40}(?:게시|방송|방영)\s*(?:완료|후|이후)")
_RX_LICENSE = re.compile(r"라이선스|이용\s*허락|사용할\s*수\s*있는|이용할\s*수\s*있는")
_RX_LICENSE_START = re.compile(r"기산|부터\s*\d+\s*개월|최초\s*(?:게시|방송|방영)일부터|시작일")
_RX_SEPARATE_APPROVAL = re.compile(r"(?:활용|사용|이용)[^.]{0,40}경우[^.]{0,20}사전\s*서면\s*(?:합의|승인|동의)를?\s*(?:거쳐야|받아야)")
_RX_TALENT = re.compile(r"초상|음성|성명")
_RX_TALENT_OURS = re.compile(r"초상[^.]{0,30}(?:갑|광고주)[’'”\"]?의\s*책임과\s*비용|(?:갑|광고주)[’'”\"]?의\s*책임과\s*비용[^.]{0,20}초상")
_RX_DISCLOSURE = re.compile(r"경제적\s*이해관계|유료\s*광고\s*(?:포함|표시)|광고\s*표시|협찬\s*(?:사실\s*)?표시|뒷광고")
_RX_SHORTS = re.compile(r"쇼츠|숏폼|숏츠|short", re.IGNORECASE)
_RX_SHORTS_SPEC = re.compile(r"(?:쇼츠|숏폼)[^.]{0,60}(?:납품|제공)\s*(?:기한|일)|분량|해상도|길이|규격")
_RX_PRODUCT = re.compile(r"제품\s*협찬|협찬\s*제품|제품을\s*제공|제품\s*활용")
_RX_PRODUCT_TERMS = re.compile(
    r"제품[^.]{0,30}(?:대여|증정|반납|회수|운송|배송|설치|파손|훼손)|(?:대여|증정|반납|회수)[^.]{0,20}제품"
)
_RX_AGENCY = re.compile(r"대행사|광고\s*대행|유료\s*광고\s*집행|매체\s*집행")
_RX_ITEM_HEAD = re.compile(r"^\s*(?:\(\s*\d+\s*\)|\d+\s*[.)])")


@dataclass
class SponsorshipModel:
    confident: bool = False
    basis: str = ""
    sponsor_label: str = ""
    recipient_label: str = ""
    our_side: str = ""                 # "sponsor" | "recipient" | ""
    online_channel: bool = False
    broadcaster: bool = False
    signals: list[str] = field(default_factory=list)

    @property
    def canonical_contract_type(self) -> str:
        return CANONICAL_TYPE if self.confident else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "confident": self.confident, "basis": self.basis,
            "canonical_contract_type": self.canonical_contract_type,
            "label": LABEL if self.confident else "",
            "sponsor_label": self.sponsor_label, "recipient_label": self.recipient_label,
            "our_side": self.our_side, "online_channel": self.online_channel,
            "broadcaster": self.broadcaster, "signals": list(self.signals),
        }


def _attr(c: Any, name: str) -> str:
    v = c.get(name) if isinstance(c, dict) else getattr(c, name, None)
    return "" if v is None else str(v)


def _flat(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


_Q = r"[‘’'“”\"]"
_ROLE_SPONSOR = re.compile(r"^(?:스폰서(?:사)?|협찬사|후원사|광고주)$")


def _labels(body: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(rf"\(\s*이하\s*{_Q}?([^‘’'“”\")]{{1,10}}?){_Q}?\s*(?:이라|라)?\s*(?:한다|칭함|함)?\s*\)", body):
        lab = m.group(1).strip()
        if lab and lab not in out and not re.match(r"^(?:본|이\s|효력|계약|행사)", lab):
            out.append(lab)
    return out


def _sponsor_label(body: str, labels: list[str]) -> str:
    """협찬하는 쪽(돈·물품을 대고 노출을 받는 쪽)의 약칭."""
    for lab in labels:  # 1. 약칭이 역할명이다 — "스폰서", "협찬사"
        if _ROLE_SPONSOR.match(lab):
            return lab
    for lab in labels:  # 2. 당사자 표기에 역할을 적었다 — "[갑(협찬사) 회사명]"
        if re.search(rf"{re.escape(lab)}\s*\(\s*(?:협찬사|스폰서|후원사|광고주)\s*\)", body):
            return lab
    lab_alt = "|".join(re.escape(l) for l in labels)
    if not lab_alt:
        return ""
    # "시디즈가 슈퍼플레이가 주관하는 행사에 물품을 제공" — "슈퍼플레이가 주관하는" 은 관형절의 주어다.
    not_adnominal = r"(?!\s*(?:주관|주최|운영|제작|진행|편성|기획|개최)(?:하는|한))"
    pats = (
        # 3. "Y는 X의 협찬에 대하여 … 제공한다" — X 가 협찬사
        rf"{_Q}?({lab_alt}){_Q}?\s*의\s*(?:협찬|후원)에\s*대하여",
        # 4. "X가 … 협찬을 실시/제공", "X가 … 협찬금·후원금·스폰서 비용을 … 지급"
        rf"{_Q}?({lab_alt}){_Q}?\s*(?:은|는|이|가){not_adnominal}\s*[^.]{{0,120}}(?:협찬|후원)을?\s*(?:실시|제공)",
        rf"{_Q}?({lab_alt}){_Q}?\s*(?:은|는|이|가)\s*[^.]{{0,80}}(?:협찬\s*(?:금|금액|대금|비)|후원금|스폰서(?:십)?\s*비용|협찬의\s*대가|그에\s*대한\s*대가)[^.]{{0,40}}지급",
        rf"{_Q}?({lab_alt}){_Q}?\s*(?:은|는|이|가)\s*[^.]{{0,40}}(?:스폰서|후원사|협찬사)로서",
        rf"{_Q}?({lab_alt}){_Q}?\s*(?:은|는|이|가){not_adnominal}\s*[^.]{{0,160}}(?:물품|제품)을?\s*(?:제공|지원|협찬)",
    )
    for rx in pats:
        m = re.search(rx, body)
        if m:
            return m.group(1)
    return ""


def resolve_sponsorship_model(*, contract_text: str, entity: str = "") -> SponsorshipModel:
    body = _flat(contract_text)
    model = SponsorshipModel()
    n_sp = len(_RX_SPONSOR.findall(body))
    if n_sp < 2 or not _RX_PAY.search(body) or not _RX_MEDIA.search(body):
        return model
    if _RX_PERFORMER_FEE.search(body) and not re.search(r"협찬\s*(?:금|대금)|후원금|스폰서(?:십)?\s*비용", body):
        return model
    labels = _labels(body)
    payer = _sponsor_label(body, labels)
    others = [l for l in labels if l != payer]
    if not payer or not others:
        return model
    other = others[0]
    model.sponsor_label, model.recipient_label = payer, other
    from runtime.review.party_label_binding import bind_party_labels_to_entities

    bound = bind_party_labels_to_entities(str(contract_text or ""), entity) if entity else None
    if bound:
        model.our_side = "sponsor" if bound[0] == payer else "recipient" if bound[0] == other else ""
    elif entity and (re.search(re.escape(entity), payer) or re.search(
            rf"{re.escape(entity)}[^()]{{0,20}}\(\s*이하\s*{_Q}?{re.escape(payer)}{_Q}?", body)):
        model.our_side = "sponsor"
    elif entity and (re.search(re.escape(entity), other) or re.search(
            rf"{re.escape(entity)}[^()]{{0,20}}\(\s*이하\s*{_Q}?{re.escape(other)}{_Q}?", body)):
        model.our_side = "recipient"
    model.online_channel = bool(_RX_ONLINE.search(body))
    model.broadcaster = bool(_RX_BROADCASTER.search(body))
    model.signals = [w for w, rx in (("협찬·PPL·스폰서십", _RX_SPONSOR), ("협찬 대가", _RX_PAY), ("노출·홍보 혜택", _RX_MEDIA))
                     if rx.search(body)]
    model.confident = True
    model.basis = (f"협찬·스폰서십 신호 {n_sp}건, 협찬하는 쪽 '{payer}', 노출·혜택을 제공하는 쪽 '{other}' — "
                   "협찬(금전·물품)을 대고 노출·이용권을 받는 거래")
    return model


# ── 조항 찾기 ────────────────────────────────────────────────────────────────

def _chunks(clauses: list[Any] | None) -> list[Any]:
    return [c for c in clauses or [] if _attr(c, "article_number")]


def _find(clauses: list[Any] | None, rx: re.Pattern[str], *, need: re.Pattern[str] | None = None,
          exclude_items: bool = False) -> Any:
    for c in _chunks(clauses):
        if exclude_items and _attr(c, "item_number"):
            continue
        t = _flat(_attr(c, "text"))
        if rx.search(t) and (need is None or need.search(t)):
            return c
    return None


def _all(clauses: list[Any] | None, rx: re.Pattern[str]) -> list[Any]:
    return [c for c in _chunks(clauses) if rx.search(_flat(_attr(c, "text")))]


def _ref(c: Any, *, home: str = "") -> str:
    """조·항·호 참조. home 과 같은 조면 조를 생략한다."""
    art, para, item = _attr(c, "article_number"), _attr(c, "paragraph_number"), _attr(c, "item_number")
    out = "" if art == home else f"제{art}조"
    if para:
        out += (" " if out else "") + f"제{para}항"
    if item:
        out += f" 제{item}호"
    return out.strip()


def _refs(cs: list[Any], *, home: str = "") -> str:
    """같은 항의 호는 묶는다 — "제1항 제1호·제4호"."""
    out: list[str] = []
    last_head = ""
    for c in cs:
        r = _ref(c, home=home)
        m = re.match(r"^(.*?)(제\d+호)$", r)
        if m and m.group(1).strip() and m.group(1).strip() == last_head:
            out.append(m.group(2))
        else:
            out.append(r)
            last_head = m.group(1).strip() if m else ""
    return "·".join(out)


def _eun(word: str) -> str:
    return _josa(word, "은", "는")


def _q(label: str, body: str, *, prefer: str = "") -> str:
    """약칭의 따옴표 모양 — 고칠 조항(prefer)이 쓰는 모양을 먼저 따른다."""
    for hay in (prefer, body):
        m = re.search(rf"([‘'“\"]){re.escape(label)}([’'”\"])", hay or "")
        if m:
            return f"{m.group(1)}{label}{m.group(2)}"
    return label


def _josa(word: str, with_b: str, without_b: str) -> str:
    core = re.sub(r"[\s“”‘’\"'()]+$", "", word or "")
    last = core[-1:] if core else ""
    has = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return word + (with_b if has else without_b)


def _finding(anchor: Any, **kw: Any) -> dict[str, Any]:
    base = {
        "clause_title": _attr(anchor, "title"),
        "display_path": _attr(anchor, "display_path"),
        "article_number": _attr(anchor, "article_number"),
        "paragraph_number": _attr(anchor, "paragraph_number"),
        "original_text": _attr(anchor, "text"),
        "risk_tier": "MEDIUM", "severity": "MEDIUM", "confidence": 0.95,
        # 원문 문형으로 직접 확인해 만든 판단 — 낱말 점수로 등급을 내리지 않는다(research_model 과 같다).
        "is_common_legal_risk": True, "is_transaction_package": True, "is_sponsorship_review": True,
    }
    base.update(kw)
    base.setdefault("rewrite_reason", base.get("problem", ""))
    base.setdefault("recommendation_text", base.get("suggested_rewrite", ""))
    base.setdefault("proposed_revision", base.get("suggested_rewrite", ""))
    base.setdefault("negotiation_strategy", base.get("negotiation_position", ""))
    tier = str(base.get("risk_tier") or "").upper()
    rw = str(base.get("suggested_rewrite") or "").strip()
    if rw and not base.get("redline_instruction"):
        from runtime.review.redline_instruction import build_redline_instruction

        new_para = base.pop("_new_paragraph_of", None)
        if new_para:
            # 기존 조에 항을 더한다 — 원문을 교체하지 않는다(기존 보호 보존).
            art, last = new_para
            base["redline_instruction"] = build_redline_instruction(
                clause_id=str(base.get("clause_id") or ""), severity=tier,
                edit_location=f"제{art}조 제{last}항 뒤에 제{last + 1}항 신설", edit_type="insert_after",
                replacement_text=rw, reason=str(base.get("rewrite_reason") or ""),
            )
        else:
            original = str(base.get("original_text") or "").strip()
            base["redline_instruction"] = build_redline_instruction(
                clause_id=str(base.get("clause_id") or ""), severity=tier,
                edit_location=f"{base.get('display_path')} 교체", edit_type="replace",
                target_text=original, replacement_text=rw, original_text=original,
                reason=str(base.get("rewrite_reason") or ""),
            )
    base.pop("_new_paragraph_of", None)
    base["has_rewrite_change"] = bool(rw)
    base["severity"] = tier
    base["must_fix"] = tier == "HIGH"
    base["review_tier"] = "MUST" if tier == "HIGH" else "SUGGEST"
    return base


def _base(c: Any) -> str:
    """원문 문장 — 문장 끝에 홀로 남은 따옴표(원문 오타)는 떼고 잇는다."""
    return re.sub(r"\.\s*[‘’'“”\"]\s*$", ".", _flat(_attr(c, "text")))


def _last_paragraph(clauses: list[Any] | None, art: str) -> int:
    nums = [int(_attr(c, "paragraph_number")) for c in _chunks(clauses)
            if _attr(c, "article_number") == art and _attr(c, "paragraph_number").isdigit()]
    return max(nums) if nums else 0


def _business_check(anchor: Any, cid: str, title: str, problem: str) -> dict[str, Any]:
    """계약에 없는 상업 조건 — 수치를 지어내지 않고 사업부가 정할 사항으로 낸다."""
    return _finding(
        anchor, clause_id=cid, risk_tier="MEDIUM", business_check=True,
        issue_title=title, detected_issue_list=[{"issue_title": title}],
        problem=problem, legal_business_reason=problem, suggested_rewrite="",
        is_transaction_package=False,
    )


def sponsorship_findings(model: SponsorshipModel, clauses: list[Any] | None,
                         contract_text: str) -> list[dict[str, Any]]:
    """광고주(우리) 관점의 핵심 판단. 우리가 협찬 수령자면 그쪽 관점의 노출만 본다."""
    if not model.confident:
        return []
    if model.our_side == "recipient":
        return _recipient_findings(model, clauses, contract_text)
    if model.our_side != "sponsor":
        return []
    body = str(contract_text or "")
    flat = _flat(body)
    _pref = "\n".join(_attr(c, "text") for c in _chunks(clauses) if not _attr(c, "item_number"))
    us, them = _q(model.sponsor_label, body, prefer=_pref), _q(model.recipient_label, body, prefer=_pref)
    out: list[dict[str, Any]] = []

    items = [c for c in _chunks(clauses) if _attr(c, "item_number")]
    tentative = _find(clauses, _RX_TENTATIVE, exclude_items=True)
    # 보장 항목은 대가 목록(협찬·노출 어휘가 든 각 호) 안에서만 찾는다 — 해지 사유의 "진술 보증" 같은 다른 조의
    # 호가 섞이지 않게. '예정' 조항이 같은 조에 있으면 그 조의 각 호로 한정한다.
    scope_art = _attr(tentative, "article_number") if tentative is not None and re.search(
        r"본\s*조|각\s*호", _flat(_attr(tentative, "text"))) else ""
    guaranteed = [c for c in items if _RX_GUARANTEE.search(_flat(_attr(c, "text")))
                  and (not scope_art or _attr(c, "article_number") == scope_art)
                  and re.search(r"PPL|노출|조회|쇼츠|방송|게시|회|건", _flat(_attr(c, "text")))]
    deliver_art = _attr(guaranteed[0], "article_number") if guaranteed else ""
    refund_clauses = _all(clauses, _RX_REFUND)
    refund_ref = " 및 ".join(_ref(c) for c in refund_clauses[:2])

    # 1. 보장 사항 vs "예정·협의로 변경" ─────────────────────────────────────
    if guaranteed and tentative is not None and not _RX_CONSENT.search(_flat(_attr(tentative, "text"))):
        home = _attr(tentative, "article_number")
        g_refs = _refs(guaranteed, home=home)
        g_desc = " / ".join(_flat(_attr(c, "text"))[:40] for c in guaranteed)
        consult = bool(_RX_CONSULT.search(_flat(_attr(tentative, "text"))))
        problem = (
            f"{_eun(g_refs)} '{g_desc}'처럼 보장·최소 수량으로 정해져 있는데, {_eun(_ref(tentative))} 같은 각 호를 "
            f"'예정'에 해당한다고 하고 변경을 {'사전 협의' if consult else '협의'}로 허용한다. 협의는 우리 동의가 없어도 "
            "거친 것으로 볼 여지가 있어, 보장 수량이 줄거나 빠져도 계약 위반이 되지 않는다고 다툴 수 있다 — "
            "협찬금을 정한 핵심 대가가 확정 의무가 아니게 된다."
        )
        addition = (
            f"다만, {g_refs}에서 보장 또는 최소 수량으로 정한 사항은 예정 사항에 해당하지 아니하며, "
            f"{_josa(them, '은', '는')} {us}의 사전 서면 동의 없이 이를 변경하거나 축소할 수 없다."
        )
        out.append(_finding(
            tentative, clause_id=f"sp_guarantee_vs_tentative__{_attr(tentative, 'clause_id')}",
            risk_tier="HIGH",
            issue_title="보장·최소 제공사항이 '예정·협의 변경' 조항으로 확정 의무가 아니게 됨",
            detected_issue_list=[{"issue_title": "[협찬 대가] 보장·최소 제공사항이 '예정·협의 변경' 조항으로 확정 의무가 아니게 됨"}],
            problem=problem,
            legal_business_reason=(
                "계약상 '보장'은 결과에 대한 확정 의무지만, 같은 계약이 그 항목을 '예정'으로 두고 협의만으로 변경할 수 "
                "있게 하면 어느 쪽이 우선하는지 해석 다툼이 생기고, 미이행 시 반환·손해배상 청구의 근거가 약해진다. "
                "'사전 협의'는 의견을 듣는 절차이고 '사전 동의'는 우리가 거부할 수 있는 권리다."
            ),
            high_severity_basis="협찬금의 대가로 정한 보장 노출이 확정 의무가 아니게 되는 구조",
            suggested_rewrite=f"{_base(tentative)} {addition}",
            location_instruction=f"{_attr(tentative, 'display_path')} 말미에 문장 추가",
            related_clause_paths=[_attr(tentative, "display_path")] + [_attr(c, "display_path") for c in guaranteed],
            package_articles=[home] + ([deliver_art] if deliver_art and deliver_art != home else []),
            package_pattern=r"예정|변경|협의|보장|개런티|최소|확약",
            negotiation_position=(
                "보장 항목만 예정 사항에서 빼고, 그 밖의 구성 변경은 협의로 두는 안이 최소 수정입니다."
            ),
        ))

    # 2. 성과 보장 — 집계 기준·미달 처리 ────────────────────────────────────
    metric = next((c for c in guaranteed if _RX_METRIC.search(_flat(_attr(c, "text")))), None)
    if metric is not None:
        gaps = []
        if not _RX_MEASURE.search(flat):
            gaps.append("집계 기준(어느 통계로 셀지·유료 광고 유입 포함 여부)과 집계 기간")
        if not _RX_SHORTFALL.search(flat):
            gaps.append("미달 시 보완 기한·대체 노출")
        if not re.search(r"배분|항목별\s*(?:금액|단가)|개별\s*(?:금액|단가)", flat):
            gaps.append("패키지 대금 중 이 항목에 배분된 금액(미달 시 반환액의 기준)")
        if gaps:
            keep_period = re.search(r"게시일\s*기준\s*(?:최소\s*)?(\d+\s*개월)", flat)
            period = (f"게시일부터 {keep_period.group(1)}이 되는 날까지" if keep_period
                      else "당사자가 서면으로 정한 집계 기간 동안")
            settle = (f"{refund_ref}에 따라 정산·반환한다" if refund_ref
                      else f"그 미달 비율에 상응하는 금액을 {_josa(them, '이', '가')} {us}에게 반환한다")
            text = (
                f"{_ref(metric, home=_attr(metric, 'article_number'))}의 조회수는 해당 콘텐츠가 게시된 플랫폼의 공식 통계에 따라 {period} 집계하며, "
                f"유료 광고를 통하여 발생한 조회수의 포함 여부는 당사자가 서면으로 정한다. {_josa(them, '은', '는')} 집계 결과와 "
                f"그 증빙을 {us}에게 서면으로 제공하고, 보장 조회수에 미달하는 경우 {_josa(us, '과', '와')} 협의한 추가 노출로 "
                f"보완하며, 집계 기간 내에 보완되지 아니한 부분은 {settle}. 이 경우 반환액은 협찬 대금 중 해당 "
                "제공사항에 배분된 금액에 미달 비율을 곱하여 산정하며, 그 배분액은 당사자가 서면으로 정한다."
            )
            existing = (f"기존 {refund_ref}의 불이행분 정산·반환은 그대로 유효하지만, 무엇을 '불이행'으로 셀지 "
                        "기준이 없어 조회수 미달에 바로 쓰기 어렵다. " if refund_ref else
                        "미이행 시 협찬금을 돌려받는 조항이 계약에 없다. ")
            out.append(_finding(
                metric, clause_id=f"sp_performance_guarantee__{_attr(metric, 'clause_id')}",
                risk_tier="MEDIUM" if refund_ref else "HIGH",
                # 반환 조항이 아예 없을 때만 HIGH — 협찬금의 핵심 대가가 미달해도 돌려받을 계약상 근거가 없다.
                high_severity_basis=("" if refund_ref else
                                     "보장 노출 미달 시 이미 지급한 협찬금을 돌려받을 계약상 근거 부재"),
                issue_title="조회수 보장의 집계 기준·미달 시 보완·정산 기준 부재",
                detected_issue_list=[{"issue_title": "[성과 보장] 조회수 집계 기준·미달 시 보완·정산 기준 부재"}],
                problem=existing + "다음이 정해져 있지 않다: " + ", ".join(gaps) + ". 일부 미달이면 미달분만 돌려받는지 "
                        "대금 전부를 다투는지, 협찬 대금 전체 중 얼마를 이 항목의 대가로 볼 것인지 다툼이 생긴다.",
                legal_business_reason=(
                    "보장 조건은 측정 방법과 미달 시 효과가 함께 정해져야 집행할 수 있다. 측정 기준이 없으면 미달 사실 "
                    "자체를 입증하기 어렵고, 배분액이 없으면 패키지 전체 대금 중 반환 범위를 정할 수 없다."
                ),
                suggested_rewrite=text,
                business_items=["보장 조회수의 집계 기간", "유료 광고 유입 포함 여부",
                                "협찬 대금 중 각 제공사항 배분액", "미달 시 보완(추가 노출) 기한"],
                location_instruction=f"제{_attr(metric, 'article_number')}조에 항 신설",
                _new_paragraph_of=(_attr(metric, "article_number"),
                                   _last_paragraph(clauses, _attr(metric, "article_number"))),
                related_clause_paths=[_attr(metric, "display_path")] + [_attr(c, "display_path") for c in refund_clauses[:2]],
                package_articles=sorted({_attr(metric, "article_number")} | {_attr(c, "article_number") for c in refund_clauses}),
                package_pattern=r"조회\s*수|미달|보상|환급|반환|반납|재노출|추가\s*노출|성과",
                negotiation_position="수치는 사업부가 정할 사항이고, 계약에는 집계 방법과 미달 시 처리 순서만 넣으면 됩니다.",
            ))

    # 3. 일정 변동 — 최종 이행기한 ──────────────────────────────────────────
    extension = _find(clauses, re.compile(r"조정\s*또는\s*연장|일정을?\s*(?:조정|연장)|편성\s*변경"), exclude_items=True)
    if extension is not None and _RX_SCHEDULE_VAR.search(flat) and not _RX_FINAL_DEADLINE.search(flat):
        settle = f"{refund_ref}에 따라 정산·반환한다" if refund_ref else f"{_josa(them, '이', '가')} {us}에게 그 대가를 반환한다"
        out.append(_finding(
            extension, clause_id=f"sp_schedule_deadline__{_attr(extension, 'clause_id')}",
            issue_title="방송·게시 일정 변경·연장의 최종 기한과 미이행 시 정산 부재",
            detected_issue_list=[{"issue_title": "[운영 중단] 게시 일정 변경·연장의 최종 기한 부재"}],
            problem=(f"방송 일정은 '변동 가능'으로 되어 있고 {_eun(_ref(extension))} 편성 변경 등으로 일정을 조정·연장할 수 있게 "
                     "하지만, 언제까지 게시되지 않으면 이행이 없는 것으로 보는지가 없다. 일정이 계속 밀리면 협찬금을 "
                     "지급하고도 노출을 받지 못한 채 해지·정산 시점을 잡을 수 없다."),
            legal_business_reason="최종 이행기한이 없으면 이행지체를 주장할 기준일이 없어 해제·반환 청구가 늦어진다.",
            suggested_rewrite=(f"{_base(extension)} 다만, 방송 일정의 조정·연장은 {us}의 사전 서면 동의를 받은 "
                               f"기간 내에서만 할 수 있으며, 그 기간 내에 제공되지 아니한 사항은 {settle}."),
            location_instruction=f"{_attr(extension, 'display_path')} 말미에 문장 추가",
            business_items=["게시가 늦어질 경우 허용할 최종 게시 기한"],
            package_articles=sorted({_attr(extension, "article_number")}),
            package_pattern=r"일정|편성|연장|조정|지연|취소|방영|방송",
            negotiation_position="연장 자체를 막지 않고, 우리 동의 없는 무기한 연장만 막는 안입니다.",
        ))

    # 4. 지급 시점 — 게시와의 연결 ─────────────────────────────────────────
    pay = _find(clauses, _RX_PAY_CLAUSE, need=_RX_FIXED_DATE, exclude_items=True)
    if pay is not None and _RX_SCHEDULE_VAR.search(flat) and not _RX_PAY_LINKED.search(flat):
        full = bool(re.search(r"100\s*%|전액", _flat(_attr(pay, "text"))))
        out.append(_finding(
            pay, clause_id=f"sp_payment_timing__{_attr(pay, 'clause_id')}",
            issue_title="협찬금 청구일이 게시 여부와 무관하게 고정됨",
            detected_issue_list=[{"issue_title": "[지급 조건] 협찬금 청구·지급이 게시와 연결되지 않음"}],
            problem=(f"{_eun(_ref(pay))} 협찬금{' 전액' if full else ''}을 확정 일자에 청구하도록 하는데, 방송 일정은 변동될 수 "
                     "있다. 지급기한이 정해져 있다는 것만으로 지급 조건이 적정한 것은 아니다 — 일정이 밀리면 노출 전에 "
                     "대금 전액이 지급된다."),
            legal_business_reason="선지급 구조에서는 이행이 늦어지거나 일부만 이행돼도 이미 낸 대금을 돌려받는 절차를 밟아야 한다.",
            suggested_rewrite=(f"{_base(pay)} 다만, 대상 프로그램의 게시일이 변경된 경우 청구는 실제 게시일 "
                               "이후에 한다."),
            location_instruction=f"{_attr(pay, 'display_path')} 말미에 문장 추가",
            business_items=["잔금을 게시 완료·성과 확인 후로 나누는 분할 지급 여부"],
            package_articles=sorted({_attr(pay, "article_number")}),
            package_pattern=r"청구\s*(?:일|시점)|선지급|지급\s*(?:시점|조건)|게시일",
            negotiation_position="청구 시점만 실제 게시일에 맞추는 최소 수정입니다. 분할 지급은 사업부가 판단할 협상안입니다.",
        ))

    # 5. 마케팅 이용권 vs 별도 사전 승인 ────────────────────────────────────
    license_item = next((c for c in items if _RX_LICENSE.search(_flat(_attr(c, "text")))
                         and re.search(r"광고|홍보|마케팅", _flat(_attr(c, "text")))), None)
    approval = _find(clauses, _RX_SEPARATE_APPROVAL, exclude_items=True)
    if approval is not None and re.search(
            r"라이선스[^.]{0,60}(?:요하지\s*(?:아니|않)|필요하지\s*(?:아니|않)|제외)", _flat(_attr(approval, "text"))):
        approval = None  # 이미 이용권 범위 안의 활용은 별도 합의 대상에서 빼 두었다 — 다시 지적하지 않는다
    if license_item is not None and approval is not None:
        lic_ref = _ref(license_item, home=_attr(approval, "article_number"))
        linked: list[dict[str, str]] = []
        if not _RX_LICENSE_START.search(_flat(_attr(license_item, "text"))):
            linked.append({"display_path": _attr(license_item, "display_path"),
                           "text": "마케팅 라이선스 기간은 대상 프로그램의 최초 게시일부터 기산한다.",
                           "source": "PROPOSED_REDLINE"})
        problem = (f"{_eun(_ref(license_item))} 협찬의 대가로 마케팅 라이선스(재편집·광고·홍보 활용)를 주는데, "
                   f"{_eun(_ref(approval))} 우리가 광고·홍보 목적으로 활용하려면 다시 사전 서면 합의를 거치도록 한다. "
                   "대가로 받은 이용권이 상대방의 별도 승인에 묶여 실제로 쓰지 못할 수 있다.")
        if linked:
            problem += " 라이선스 기간(3개월 등)이 언제부터 기산되는지도 정해져 있지 않다."
        out.append(_finding(
            approval, clause_id=f"sp_license_vs_approval__{_attr(approval, 'clause_id')}",
            risk_tier="HIGH",
            issue_title="대가로 받은 마케팅 라이선스가 별도 사전 서면 합의에 묶임",
            detected_issue_list=[{"issue_title": "[마케팅 이용권] 대가로 받은 라이선스와 별도 사전 승인 요구의 충돌"}],
            problem=problem,
            legal_business_reason=(
                "저작권은 상대방에게 남아 있어도 이용허락을 받은 범위 안의 이용은 침해가 아니다. 다만 같은 계약이 그 "
                "이용에 별도 합의를 요구하면 허락 범위가 불명확해지고, 합의가 이뤄지지 않으면 이용권 자체를 행사할 수 없다. "
                "저작권 양도를 받을 필요는 없고, 허락 범위 안의 이용에 추가 승인이 필요 없다는 점만 분명히 하면 된다."
            ),
            high_severity_basis="협찬 대가의 일부인 이용권이 실질적으로 행사 불가능해지는 구조",
            suggested_rewrite=(f"{_base(approval)} 다만, {lic_ref}의 마케팅 라이선스 범위 안의 활용에는 "
                               "본 항 전단의 사전 서면 합의를 요하지 아니한다."),
            package_linked_edits=linked,
            location_instruction=f"{_attr(approval, 'display_path')} 말미에 문장 추가",
            business_items=["광고대행사·매체사를 통한 활용과 유료 광고 집행이 이용 범위에 포함되는지"]
            if not _RX_AGENCY.search(flat) else [],
            related_clause_paths=[_attr(approval, "display_path"), _attr(license_item, "display_path")],
            package_articles=sorted({_attr(approval, "article_number"), _attr(license_item, "article_number")}),
            package_pattern=r"라이선스|이용|활용|재편집|플랫폼|저작|2차적|홍보|광고\s*목적|기산|기간",
            negotiation_position="저작권 귀속은 그대로 두고, 이미 준 이용권의 행사에 추가 승인이 필요 없다는 점만 확인하는 안입니다.",
        ))

    # 6. 경제적 이해관계 표시 ─────────────────────────────────────────────
    if model.online_channel and not _RX_DISCLOSURE.search(flat):
        anchor = _find(clauses, re.compile(r"방송법|협찬고지|관련\s*법령"), exclude_items=True) or (
            guaranteed[0] if guaranteed else None)
        if anchor is not None:
            covenant = bool(re.search(r"방송법|협찬고지", _flat(_attr(anchor, "text"))))
            out.append(_finding(
                anchor, clause_id=f"sp_disclosure__{_attr(anchor, 'clause_id')}",
                issue_title="온라인 게시 협찬의 경제적 이해관계 표시 책임 미정",
                detected_issue_list=[{"issue_title": "[규제] 협찬·유료광고 표시 책임 미정"}],
                problem=("대상 콘텐츠는 온라인 채널에 게시된다. "
                         + ("현재 조항은 방송 관련 규정의 준수를 약정할 뿐, 온라인 게시물에 협찬·유료광고 사실을 누가 어떻게 "
                            "표시하는지는 정하지 않는다. " if covenant else "협찬·유료광고 사실의 표시 책임이 정해져 있지 않다. ")
                         + "표시가 빠지면 소비자를 속이는 광고로 문제될 수 있고, 광고주도 제재 대상이 될 수 있다."),
                legal_business_reason=(
                    "온라인 게시물의 협찬·광고 표시는 「표시·광고의 공정화에 관한 법률」과 그 심사지침(추천·보증 등)의 문제다. "
                    "방송법 준수 약정은 계약상 의무일 뿐이고, 온라인 채널에 방송법이 바로 적용되는지는 그 채널의 법적 지위에 "
                    "따라 따로 확인해야 한다."
                ),
                suggested_rewrite=(f"{_josa(them, '은', '는')} 대상 프로그램과 쇼츠 등 협찬 콘텐츠를 게시할 때 {us}과의 경제적 "
                                   "이해관계(협찬·유료광고 포함 사실)를 관련 법령과 심사지침에 따라 소비자가 쉽게 알 수 있도록 "
                                   f"표시하며, {_josa(us, '은', '는')} 제공하는 제품 정보·광고 표현의 사실 여부에 대하여 책임진다."),
                location_instruction=f"제{_attr(anchor, 'article_number')}조에 항 신설",
                _new_paragraph_of=(_attr(anchor, "article_number"),
                                   _last_paragraph(clauses, _attr(anchor, "article_number"))),
                package_articles=sorted({_attr(anchor, "article_number")}),
                package_pattern=r"표시|광고법|방송법|협찬고지|심의|규제",
                negotiation_position="표시 의무는 게시하는 쪽, 제품 정보의 사실 확인은 광고주 쪽으로 나누는 안입니다.",
            ))

    # 6-1. 불가항력·귀책 없는 취소 — 미제공분 반환 ─────────────────────────────
    fm = _find(clauses, re.compile(r"불가항력|천재지변"), need=re.compile(r"책임을?\s*지지\s*(?:않|아니)|면책|면제"))
    fault_only = bool(refund_clauses) and all(re.search(r"귀책", _flat(_attr(c, "text"))) for c in refund_clauses)
    if fm is not None and (fault_only or not refund_clauses) \
            and not re.search(r"불가항력[^.]{0,80}(?:반환|정산|환급)", flat):
        out.append(_finding(
            fm, clause_id=f"sp_force_majeure_refund__{_attr(fm, 'clause_id')}",
            issue_title="불가항력·귀책 없는 취소 시 선지급 협찬금 중 미제공분 반환 근거 부재",
            detected_issue_list=[{"issue_title": "[운영 중단] 불가항력·귀책 없는 취소 시 미제공분 반환 근거 부재"}],
            problem=(f"{_eun(_ref(fm))} 불가항력이면 '책임을 지지 않는다'고만 정하고, "
                     + (f"반환 조항({refund_ref})은 상대방의 귀책사유가 있을 때로 한정되어 있다. "
                        if fault_only else "미이행분 반환 조항이 없다. ")
                     + "협찬금을 먼저 지급하는 구조에서 편성 취소·플랫폼 조치·불가항력으로 노출이 이뤄지지 않으면, 이미 낸 "
                       "협찬금 중 제공되지 않은 부분을 돌려받을 근거를 두고 다툼이 생긴다."),
            legal_business_reason=(
                "불가항력 면책은 손해배상 책임을 면하게 하는 것이지 받은 대가를 보유할 근거가 아니다. 쌍무계약에서 "
                "당사자 쌍방의 책임 없는 사유로 이행할 수 없게 되면 상대방의 이행도 청구할 수 없다(민법 제537조). "
                "계약에 반환 문언을 두면 이 다툼을 줄일 수 있다."
            ),
            suggested_rewrite=(f"{_base(fm)} 다만, 본 조는 손해배상 책임에 관한 것이며, 불가항력 등 당사자의 귀책사유 없이 "
                               f"제공되지 아니한 사항이 있는 경우 {_josa(them, '은', '는')} 이미 지급받은 협찬 대금 중 그에 해당하는 "
                               f"금액을 {us}에게 반환한다."),
            location_instruction=f"{_attr(fm, 'display_path')} 말미에 문장 추가",
            related_clause_paths=[_attr(fm, "display_path")] + [_attr(c, "display_path") for c in refund_clauses[:2]],
            package_articles=sorted({_attr(fm, "article_number")}),
            package_pattern=r"불가항력|천재지변|취소|면책",
            negotiation_position="상대방의 면책은 그대로 두고, 받은 대가 중 미제공분만 돌려받는 안입니다.",
        ))

    # 7. 사업부 확인 — 계약에 없는 상업 조건 ────────────────────────────────
    shorts = next((c for c in items if _RX_SHORTS.search(_flat(_attr(c, "text")))), None)
    if shorts is not None and not _RX_SHORTS_SPEC.search(flat):
        out.append(_business_check(
            shorts, f"sp_biz_shorts__{_attr(shorts, 'clause_id')}",
            "쇼츠·소재 납품 사양과 기한 미정",
            "쇼츠 제공은 정해져 있으나 분량·규격·게시 채널·납품(게시) 기한과 우리 채널 재사용용 원본 제공 여부가 없다 — "
            "사업부가 원하는 조건을 정해 계약에 넣어야 한다."))
    product_anchor = _find(clauses, _RX_PRODUCT)
    if product_anchor is not None and not _RX_PRODUCT_TERMS.search(flat):
        out.append(_business_check(
            product_anchor, f"sp_biz_product__{_attr(product_anchor, 'clause_id')}",
            "협찬 제품의 대여·증정 여부와 운송·설치·파손·회수 책임 미정",
            "제품 협찬은 정해져 있으나 제품을 빌려주는지 증정하는지, 운송·설치 비용, 촬영 중 파손 책임, 종료 후 회수 여부가 "
            "없다 — 사업부 확인 후 계약에 넣어야 한다."))
    license_for_talent = license_item or _find(clauses, _RX_TALENT)
    if license_for_talent is not None and _RX_TALENT.search(flat):
        allocated = bool(_RX_TALENT_OURS.search(flat))
        out.append(_business_check(
            license_for_talent, f"sp_biz_talent__{_attr(license_for_talent, 'clause_id')}",
            "출연자 초상·음성·성명 이용의 확보 주체·추가 비용·미확보 시 대안 확인",
            ("계약은 출연자 초상·음성·성명 이용을 광고주의 책임과 비용으로 정하고 있다(명시된 비용분담 — 누락이 아니다). "
             if allocated else "출연자 초상·음성·성명 이용은 별도 협의로 남겨져 있다. ")
            + "광고 소재에 출연자가 나오는지, 소속사 확보 비용과 기간, 확보하지 못하면 출연자 없는 소재로 대체 제공받을 수 "
              "있는지 사업부가 확인해야 한다. 비용 분담을 바꾸려면 협상안(상대방의 소속사 협의 주선·비용 일부 부담)으로 "
              "제시한다 — 누락 보완이 아니다."))
    return out


def _recipient_findings(model: SponsorshipModel, clauses: list[Any] | None,
                        contract_text: str) -> list[dict[str, Any]]:
    """우리가 협찬을 받아 제작·게시하는 쪽 — 성과 보장은 우리 부담이다."""
    body = str(contract_text or "")
    flat = _flat(body)
    us, them = _q(model.recipient_label, body), _q(model.sponsor_label, body)
    metric = next((c for c in _chunks(clauses) if _attr(c, "item_number")
                   and _RX_GUARANTEE.search(_flat(_attr(c, "text")))
                   and _RX_METRIC.search(_flat(_attr(c, "text")))), None)
    if metric is None or _RX_MEASURE.search(flat):
        return []
    return [_finding(
        metric, clause_id=f"sp_recipient_guarantee_exposure__{_attr(metric, 'clause_id')}",
        risk_tier="HIGH",
        issue_title="우리가 지는 조회수 보장의 집계 기준·책임 한도 부재",
        detected_issue_list=[{"issue_title": "[성과 보장 — 우리 부담] 집계 기준·미달 시 책임 범위 부재"}],
        problem=(f"우리({us})가 조회수를 보장하는데 집계 기준·기간과 미달 시 책임 범위가 없다. 플랫폼 정책·알고리즘처럼 "
                 "우리가 통제할 수 없는 사유로 미달해도 협찬금 반환·손해배상을 요구받을 수 있다."),
        legal_business_reason="결과 보장은 귀책 없는 미달에도 책임이 생길 수 있어 측정 방법과 책임 한도를 함께 정해야 한다.",
        suggested_rewrite=(f"{_ref(metric)}의 조회수는 게시 플랫폼의 공식 통계에 따라 당사자가 서면으로 정한 기간 동안 집계하며, "
                           f"보장 조회수에 미달하는 경우 {_josa(us, '은', '는')} {them}과 협의한 추가 노출로 보완하고, 그 보완으로 "
                           "미달에 따른 책임을 다한 것으로 본다."),
        location_instruction=f"제{_attr(metric, 'article_number')}조에 항 신설",
        _new_paragraph_of=(_attr(metric, "article_number"),
                           _last_paragraph(clauses, _attr(metric, "article_number"))),
        package_articles=[_attr(metric, "article_number")],
        package_pattern=r"조회\s*수|미달|보상|환급|반환|보장",
        negotiation_position="보완 노출로 책임을 한정하는 안입니다. 반환을 피할 수 없으면 해당 항목 배분액을 상한으로 둡니다.",
    )]
