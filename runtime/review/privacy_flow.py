"""개인정보 처리 흐름 검토 — '개인정보' 라는 낱말이 없어도 처리 흐름이 보이면 별도로 검토한다 (2026-11-12).

시작 조건(단서): 개인(임직원·회원·고객·이용자 등)을 가리키는 명사가 있고, 다음 중 하나가 보일 때
  명단 전달·대상자 지정 / 회원가입·이용 동의 / 개인별 이용·결제·구매 내역 / 관리자 화면·사이트 / 외부 업체로의 전달·접근.
'관련 법령을 준수한다' 는 일반 조항만으로는 충분하다고 보지 않는다.

처리 활동별로 '누가 → 어떤 항목을 → 누구에게 → 어떤 목적으로' 를 정리하고, 계약 원문으로 확인된 사실과 실제 운영 확인이
필요한 부분을 나눈다. 처리 관계(우리 지시에 따른 위탁 / 사업자의 독자적 처리 / 제3자 제공)는 활동마다 후보를 적고,
운영약관·처리방침·가입 화면·위탁계약서가 없으면 그 판단만 보류한다 — 계약 전체를 한 가지로 일괄 분류하지 않는다.
회사명·로고 사용 승인(법인 정보)과 개인 정보의 광고·홍보 이용은 다른 문제로 나눈다.

자료가 부족해도 확인할 항목, 임시 수정 방향(관계를 단정하지 않는 계약 문구), 데이터 제공·서비스 개시 전 충족할 조건을 낸다.
처리 흐름이 없는 계약에는 아무것도 만들지 않는다(불필요한 위탁 조항 금지). 회사명·조항 번호는 코드에 없다.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from runtime.review import term_linkage as _tl

# 개인을 가리키는 명사 — '고객회사·고객사·회원사' 같은 법인 호칭은 제외
_RX_SUBJECT = re.compile(r"(?:이용\s*회원|회원(?!사)|임직원|직원|근로자|파견\s*근로자|파견직|구성원|고객(?!\s*(?:회사|사|법인|기업|업체))|"
                         r"이용자|사용자(?!\s*(?:회사|측))|가입자|수강생|환자|입주자|방문객|소비자(?!\s*가(?:격|\s*기준|\s*\d))|"
                         r"출연자|참가자|응모자|지원자|구직자|당첨자|개인(?!\s*사업자))")
# 명단 전달 — 사람 목록이 실제로 넘어가는 문장(목록 낱말 + 전달 동사)이거나, 대상자를 지정해 알리는 문장
_RX_ROSTER = re.compile(r"(?:명단|명부|목록|리스트)[^.]{0,40}(?:제공|전달|등록|통보|송부|공유|제출|지정)|"
                        r"(?:대상자|이용\s*회원|회원|임직원|직원|소속)[^.]{0,60}(?:자를|을|를)?\s*지정하여|"
                        r"(?:성명|이름|연락처|전화\s*번호|휴대\s*전화|이메일\s*주소|사번|생년월일)[^.]{0,15}?(?:을|를)\s*(?:사전에\s*)?(?:제공|전달|등록|통보|송부|제출)")
_RX_CONTACT = re.compile(r"성명|이름|연락처|전화\s*번호|휴대\s*전화|이메일|사번|생년월일|주민")
_RX_PER_PERSON = re.compile(r"개인별|회원별|이용자별|직원별|임직원별|고객별|인별|1인당|명별")
_RX_SIGNUP = re.compile(r"(?<![가-힣])가입(?:한다|하여|을|시|절차|신청)?|회원\s*등록|계정\s*(?:을\s*)?(?:생성|발급)|"
                        r"이용에\s*필요한\s*동의|동의를\s*거부|본인\s*인증|로그인")
_RX_HISTORY = re.compile(r"(?:이용|결제|구매|발급|주문|사용|거래|출입|근태|포인트|적립|배송|상담)\s*(?:취소\s*)?(?:내역|이력|기록|현황)")
_RX_ADMIN = re.compile(r"관리자\s*(?:사이트|화면|페이지|계정|권한|모드|시스템|웹)|어드민|admin\s*(?:page|site|console)|관리\s*페이지|대시보드", re.I)
_RX_THIRD = re.compile(r"(?:제휴|가맹|협력)\s*(?:식당|업체|업소|점포|가맹점|매장|병원|기관|사(?![가-힣]))?|외부\s*업체|하도급|재위탁|제3자|수탁자|대행\s*업체")
_RX_TRANSFER = re.compile(r"제공|전달|공유|열람|접근|조회|전송|이전|사용|구매|결제")
_RX_RETAIN = re.compile(r"보관|보존|저장|파기|삭제|반환")
_RX_PROMO = re.compile(r"홍보|마케팅|광고|브랜드|소개서|리플릿|SNS|홈페이지|사례|보도|레퍼런스")
_RX_PRIV_WORD = re.compile(r"개인\s*정보|personal\s+(?:data|information)", re.I)
_RX_GENERIC_ONLY = re.compile(r"(?:관련\s*)?법령[^.]{0,30}(?:따른\s*)?(?:의무를\s*)?준수|법령을\s*준수|관계\s*법령에\s*따라")
_RX_LIST_ITEMS = re.compile(r"([가-힣A-Za-z ]{0,18}?(?:내역|이력|현황|명단|정보|번호|주소|성명|이름|연락처|사번|이메일))(?=[,，、\s및)）]|과\s|와\s|을\s|를\s|$)")

DOCS_NEEDED = ("사업자 운영약관(서비스 이용약관)", "사업자 개인정보 처리방침", "가입 화면·이용 동의서(수집 항목·목적·보유기간 고지)",
               "개인정보 처리 위탁계약서 또는 위탁 문서(위탁 관계인 처리가 있을 때)")

CHECK_TOPICS = (
    ("purpose_items", "처리 목적·최소 항목", re.compile(r"최소(?:한)?(?:의)?\s*(?:범위|항목)|수집\s*항목|처리\s*항목|목적\s*(?:외|이외)(?:의)?\s*(?:용도|이용)")),
    ("admin_access", "관리자 권한(열람자·범위·접근 기록)", re.compile(r"접근\s*권한|열람\s*(?:권한|범위)|접속\s*기록|권한\s*(?:관리|부여)")),
    ("onward", "재위탁·외부 제공·국외 이전", re.compile(r"재위탁|다시\s*위탁|제3자(?:에게)?\s*제공|국외\s*(?:로\s*)?이전|해외\s*이전")),
    ("retention", "보관·반환·파기", re.compile(r"파기|반환|삭제|보유\s*기간|보관\s*기간")),
    ("security", "보안·사고 통지·감독", re.compile(r"안전(?:성)?\s*(?:확보)?(?:에\s*필요한)?\s*조치|암호화|유출|침해\s*사고|보안\s*(?:조치|사고|점검)")),
)


def _s(v: Any) -> str:
    return str(v or "").strip()


def _ws(v: Any) -> str:
    return " ".join(str(v or "").split())


@dataclass
class Activity:
    key: str
    name: str
    who: str
    items: str
    to: str
    purpose: str
    basis: list[str]
    contract_fact: str          # 계약 원문으로 확인된 사실
    ops_check: str              # 실제 운영 확인이 필요한 부분
    relation_candidates: list[str]
    relation: str               # 판단 또는 '판단 보류 — …'


@dataclass
class PrivacyReview:
    active: bool = False
    trigger: list[str] = field(default_factory=list)      # 시작 근거(단서·조항)
    subject: str = ""                                      # 정보주체 명사
    privacy_word: bool = False
    activities: list[Activity] = field(default_factory=list)
    checklist: list[dict[str, str]] = field(default_factory=list)
    generic_only: list[str] = field(default_factory=list)  # 일반 준수 조항만 있는 조
    privacy_paths: list[str] = field(default_factory=list)
    promo: dict[str, Any] = field(default_factory=dict)
    docs_missing: list[str] = field(default_factory=list)
    held: list[str] = field(default_factory=list)
    pre_launch: list[str] = field(default_factory=list)
    to_confirm: list[str] = field(default_factory=list)
    user_facts: list[str] = field(default_factory=list)
    laws: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.。])\s+|\n", text or "") if x.strip()]


def _subject_noun(text: str) -> str:
    counts: dict[str, int] = {}
    for m in _RX_SUBJECT.finditer(text or ""):
        k = re.sub(r"\s", "", m.group(0))
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return ""
    best = max(counts, key=lambda k: counts[k])
    # 원문 표기(띄어쓰기) 그대로
    m = re.search(r"\s*".join(map(re.escape, best)), text)
    return m.group(0) if m else best


def _items(sentence: str) -> list[str]:
    out = []
    for m in _RX_LIST_ITEMS.finditer(sentence or ""):
        it = _ws(re.sub(r"^(?:[가-힣]\s+|및\s*|또는\s*|기타\s*|그\s*밖의\s*)+", "", m.group(1)))
        words = it.split()[-3:]
        while len(words) > 1 and re.search(r"(?:가|이|은|는|의|를|을|에게|에서|으로|로)$", words[0]):
            words = words[1:]   # "담당자가 고객별 상담 내역" → "고객별 상담 내역"
        it = " ".join(words)
        if 2 <= len(it) <= 18 and not re.search(r"당사자|본\s*계약|관련\s*사항", it):
            out.append(it)
    return list(dict.fromkeys(out))


def _answer_facts(answers_text: str) -> list[str]:
    out = []
    for ln in str(answers_text or "").split("\n"):
        ln = ln.strip(" -•\t")
        if re.search(r"개인\s*정보|동의|약관|처리\s*방침|위탁|명단|회원|파견|임직원", ln) and ("?" in ln or ":" in ln):
            out.append(_ws(ln)[:200])
    return out


def analyze(text: str, *, ours: str, theirs: str, answers_text: str = "", request_text: str = "") -> PrivacyReview:
    pr = PrivacyReview()
    arts, _annex = _tl.articles(text)
    if not arts:
        return pr
    subject = _subject_noun(" ".join(a.body for a in arts))
    pr.subject = subject
    pr.privacy_word = bool(_RX_PRIV_WORD.search(text or ""))
    hits: dict[str, list[tuple[str, str]]] = {k: [] for k in ("roster", "signup", "history", "admin", "third", "retain", "promo", "privacy")}
    for a in arts:
        for u in _tl.units(a.body):
            for s in _sentences(u) or [u]:
                has_subj = bool(_RX_SUBJECT.search(s))
                if _RX_ROSTER.search(s) and (has_subj or _RX_CONTACT.search(s)):
                    hits["roster"].append((a.path, s))
                # 보험·공제 가입은 회원가입이 아니다 — 줄이 문장 중간에서 끊겨도 보이도록 앞 문맥까지 본다
                _at = a.body.find(s[:20])
                _ctx = a.title + " " + (a.body[max(0, _at - 80):_at + len(s)] if _at >= 0 else u)
                if _RX_SIGNUP.search(s) and not re.search(r"보험|공제|보증|조합|협회|단체", _ctx):
                    hits["signup"].append((a.path, s))
                # 이용·결제 내역은 사람(정보주체)과 같은 문장이거나, 관리자 화면·개인별 표시와 함께일 때만(자금 사용 내역 등 제외)
                if _RX_HISTORY.search(s) and (has_subj or _RX_PER_PERSON.search(s) or _RX_ADMIN.search(s)):
                    hits["history"].append((a.path, s))
                if _RX_ADMIN.search(s):
                    hits["admin"].append((a.path, s))
                if _RX_THIRD.search(s) and has_subj and _RX_TRANSFER.search(s):
                    hits["third"].append((a.path, s))
                if _RX_RETAIN.search(s) and (_RX_HISTORY.search(s) or has_subj or re.search(r"정보", s)):
                    hits["retain"].append((a.path, s))
                if _RX_PROMO.search(s) and re.search(r"소개|게재|활용|사용|공개|노출", s):
                    hits["promo"].append((a.path, s))
                if _RX_PRIV_WORD.search(s):
                    hits["privacy"].append((a.path, s))
    person_flow = bool(subject) and bool(hits["roster"] or hits["signup"] or (hits["history"] and (hits["admin"] or subject))
                                         or (hits["third"] and hits["history"]))
    if not person_flow:
        return pr
    pr.active = True
    pr.trigger = [f"{k}: {p} “{_ws(s)[:60]}”" for k in ("roster", "signup", "history", "admin", "third") for p, s in hits[k][:2]]
    pr.privacy_paths = list(dict.fromkeys(p for p, _ in hits["privacy"]))
    for p in pr.privacy_paths:
        body = " ".join(s for pp, s in hits["privacy"] if pp == p)
        if _RX_GENERIC_ONLY.search(body) and not any(rx.search(body) for _k, _n, rx in CHECK_TOPICS[:3]):
            pr.generic_only.append(p)
    O, T, S = ours or "우리", theirs or "상대방", subject or "정보주체"
    acts: list[Activity] = []
    if hits["roster"]:
        # 정의 조항("4. 이용회원: …")보다 실제로 넘기는 문장(지정하여 준다·명단을 제공한다)을 근거로 쓴다
        hits["roster"].sort(key=lambda x: (1 if re.match(r"^\d+\.\s*[^:：]{1,15}[:：]", x[1]) else 0,
                                           0 if re.search(r"지정하여|명단|명부|목록|리스트|전달|통보", x[1]) else 1))
        p, s = hits["roster"][0]
        its = _items(s)
        acts.append(Activity(
            "roster", f"{S} 명단·대상자 지정", O, ", ".join(its) or "원문 미기재", T, f"{T}의 서비스 제공 대상 등록",
            [p], f"{p}: {O}{_tl.josa(O, "이가")} {T}에게 {S}{_tl.josa(S, "을를")} 지정해 알린다 — “{_ws(s)[:90]}”",
            "실제로 넘기는 항목(성명·소속·사번·휴대전화번호 등)과 전달 방식(파일·관리자 화면 등록 등)" if not its else "전달 방식·주기",
            [f"{O} 지시에 따른 처리위탁({O}의 업무를 위해 {T}{_tl.josa(T, '이가')} 처리)",
             f"제3자 제공({T}{_tl.josa(T, '이가')} 자기 서비스 회원 관리 목적으로 받는 경우 — 정보주체 동의 등 근거 필요)"],
            ""))
    if hits["signup"]:
        hits["signup"].sort(key=lambda x: 0 if _RX_SUBJECT.search(x[1]) else 1)   # 개인의 가입을 법인 가입보다 앞에
        p, s = hits["signup"][0]
        acts.append(Activity(
            "signup", f"{S}의 서비스 가입·이용 동의", S, "가입 정보(원문 미기재)", T, f"{T} 서비스 계정 생성·이용",
            list(dict.fromkeys(pp for pp, _ in hits["signup"][:3])), f"{p}: “{_ws(s)[:90]}”",
            "가입 화면의 수집 항목·동의 문구·필수/선택 구분, 동의 거부 시 불이익(서비스 제한) 범위",
            [f"{T}의 독자적 처리(자기 약관·동의에 따른 회원 관리)", f"{O} 위탁 업무의 일부(가입이 {O} 업무 수행만을 위한 것일 때)"],
            ""))
    if hits["history"]:
        paths = list(dict.fromkeys(pp for pp, _ in hits["history"][:4]))
        its = list(dict.fromkeys(i for _p, s in hits["history"][:4] for i in _items(s)))
        acts.append(Activity(
            "history", f"{S}별 이용·거래 내역 생성·보관", T, ", ".join(its[:6]) or f"{S}별 이용·거래 내역", T + " 내부",
            "본 계약의 서비스 제공·정산", paths, "; ".join(f"{pp}: “{_ws(s)[:70]}”" for pp, s in hits["history"][:2]),
            f"내역이 {S} 개인별로 식별되는지, 보관 기간과 이용 목적(계약 이행 외 분석·마케팅 이용 여부)",
            [f"위탁({O}의 업무 목적으로 {T}{_tl.josa(T, '이가')} 처리)", f"{T}의 독자적 처리(자기 서비스 운영 목적)"],
            ""))
    if hits["admin"]:
        p, s = hits["admin"][0]
        its = _items(s)
        acts.append(Activity(
            "admin", "관리자 화면 열람", T, ", ".join(its[:6]) or f"{S}별 내역", f"{O} 관리자(담당자)", f"{O}의 {S} 관리·정산",
            [p], f"{p}: “{_ws(s)[:90]}”",
            f"관리자 계정 수·권한 등급, {S} 개인별 상세 조회 가능 여부, 접근 기록 보관",
            [f"{O}의 처리(위탁 관계라면 {O} 정보의 열람)",
             f"{T}의 제3자 제공({T}{_tl.josa(T, '이가')} 독자적으로 처리하는 정보라면 {O}에게 제공하는 것 — 근거 필요)"],
            ""))
    if hits["third"]:
        p, s = hits["third"][0]
        tp = _RX_THIRD.search(s).group(0)
        acts.append(Activity(
            "third", f"외부 업체({_ws(tp)}) 전달·접근", T, "원문 미기재", _ws(tp), "서비스 이행(결제·이용 확인 등)",
            list(dict.fromkeys(pp for pp, _ in hits["third"][:3])), f"{p}: “{_ws(s)[:90]}”",
            f"{_ws(tp)}에 {S} 개인 정보가 넘어가는지(이름·사번·결제 내역 등), 넘어가면 항목·방식",
            ["재위탁(" + f"{T}{_tl.josa(T, '이가')} {O}에게서 위탁받은 처리를 다시 맡기는 경우 — {O} 동의 필요)", "제3자 제공(외부 업체가 자기 목적으로 쓰는 경우)"],
            ""))
    if hits["retain"]:
        p, s = hits["retain"][0]
        acts.append(Activity(
            "retain", "보관·종료 후 처리", T, "원문 조항 대상 정보", T + " 내부", "법령상 보존·처리 목적 달성",
            list(dict.fromkeys(pp for pp, _ in hits["retain"][:3])), f"{p}: “{_ws(s)[:90]}”",
            "계약 종료 후 반환·파기 시점과 증빙, 법령상 보존 대상의 범위",
            ["보관 근거는 원문에 있으나 종료 시 반환·파기 의무가 원문에 있는지 확인"], ""))
    # 처리 관계 — 운영 자료가 없으면 판단만 보류한다(활동별)
    keys = {a.key for a in acts}
    needed = [d for d in DOCS_NEEDED if ("운영약관" not in d and "가입 화면" not in d) or "signup" in keys]
    provided = [d for d in needed if re.search(re.escape(d.split("(")[0][:4]), request_text or "") and re.search(r"첨부|별첨|제공", request_text or "")]
    pr.docs_missing = [d for d in needed if d not in provided]
    # 계약 원문이 '상대방이 우리 업무를 대행·수탁한다' 고 정하고 정보주체의 별도 가입 관계가 없으면, 우리가 넘기는 정보의 처리는
    # 원문상 우리 업무의 위탁으로 읽힌다 — 이 판단은 운영 자료 없이도 원문으로 확인된 사실이다(나머지 활동만 보류).
    outsourcing = [(a.path, s) for a in arts for s in _sentences(a.body)
                   if re.search(r"대행|위탁(?:하|받|한다)|수탁|대신하여", s) and (theirs and theirs in s or re.search(r"업무", s))][:1]
    for a in acts:
        if outsourcing and "signup" not in keys and a.key in ("roster", "history", "admin", "retain"):
            p0, s0 = outsourcing[0]
            a.relation = (f"원문상 {O} 업무의 처리위탁으로 읽힘({p0}: “{_ws(s0)[:60]}”) — 위탁 문서(개인정보 보호법 제26조) 필요"
                          if a.key != "admin" else f"원문상 위탁받은 처리의 결과를 {O}{_tl.josa(O, '이가')} 열람(위탁자 열람) — 열람 권한 관리 필요")
            continue
        if len(a.relation_candidates) > 1:
            a.relation = ("판단 보류 — " + ", ".join(d.split("(")[0] for d in pr.docs_missing[:3]) + " 미제공. 후보: "
                          + " / ".join(a.relation_candidates)) if pr.docs_missing else a.relation_candidates[0]
        else:
            a.relation = a.relation_candidates[0] if a.relation_candidates else ""
    pr.activities = acts
    # 홍보 — 회사명·로고(법인 정보) 사용 승인 ≠ 개인 정보의 광고·홍보 이용
    if hits["promo"]:
        p, s = hits["promo"][0]
        personal = bool(re.search(r"사례|후기|사진|이미지|인터뷰|이용\s*모습|운영", s))
        pr.promo = {"path": p, "sentence": _ws(s),
                    "corporate": f"{O}의 상호·로고·계약 체결 사실 공개 — 개인정보가 아니라 회사 승인 사항(사전 서면 승인 필요 여부)",
                    "personal": (f"‘운영 사례’ 등에 {S}의 이름·사진·이용 내역·후기가 들어가면 개인 정보의 광고·홍보 이용 — "
                                 f"{S} 본인의 별도 동의가 필요하고 회사 승인으로 대신할 수 없음") if personal else "",
                    "approval_in_contract": bool(re.search(r"사전\s*(?:서면\s*)?(?:승인|동의)", s))}
    # 점검표
    all_priv = " ".join(s for _p, s in hits["privacy"]) + " " + " ".join(s for _p, s in hits["retain"])
    for key, name, rx in CHECK_TOPICS:
        # '관련 법령 준수' 일반 조항 안의 낱말(위탁·파기 등)은 보호 장치로 세지 않는다
        m = [(p, s) for a in arts for s in _sentences(a.body) for p in [a.path] if p not in pr.generic_only and rx.search(s)
             and (_RX_PRIV_WORD.search(s) or _RX_SUBJECT.search(s) or _RX_HISTORY.search(s) or _RX_ADMIN.search(s))]
        if key == "admin_access" and not hits["admin"]:
            continue
        if key == "retention" and not m:
            m = [(p, s) for p, s in hits["retain"] if p not in pr.generic_only][:1]
        if m:
            status = f"원문 있음({', '.join(dict.fromkeys(p for p, _ in m))}) — 범위 확인"
            if key == "retention" and not re.search(r"파기|반환|삭제", " ".join(s for _p, s in m)):
                status = f"보관 근거만 있음({', '.join(dict.fromkeys(p for p, _ in m))}) — 종료 시 반환·파기 없음"
        elif pr.generic_only:
            status = f"없음 — {', '.join(pr.generic_only)}의 일반 법령 준수 조항만 있음(충분하지 않음)"
        else:
            status = "없음"
        pr.checklist.append({"topic": name, "key": key, "status": status})
    # 확인 항목·개시 전 조건
    pr.to_confirm = [f"{a.name}: {a.ops_check}" for a in acts]
    pr.held = [f"{a.name} — 처리 관계 {a.relation}" for a in acts if a.relation.startswith("판단 보류")]
    pr.pre_launch = [
        f"{O}{_tl.josa(O, '이가')} {T}에게 넘기는 {S} 정보 항목을 서면으로 확정(필요 최소 항목)하고, 그 전에는 명단을 전달하지 않는다",
        f"{T}의 운영약관·개인정보 처리방침·가입 화면을 받아 활동별 처리 관계(위탁/독자 처리/제3자 제공)를 확정한다",
        "위탁 관계인 처리가 있으면 개인정보 보호법 제26조에 따른 위탁 문서를 작성하고 수탁자를 공개한다",
        f"{S}에게 수집 항목·목적·보유기간을 알리는 절차(가입 화면 또는 {O} 내부 고지)를 갖춘다",
    ]
    if hits["admin"]:
        pr.pre_launch.append(f"{O} 관리자 계정을 담당자로 한정하고 열람 범위(개인별 상세 조회 여부)를 정한다")
    if any(a.key == "third" for a in acts):
        pr.pre_launch.append(f"외부 업체로 넘어가는 {S} 정보가 있으면 항목·근거를 확인한다(없으면 그 사실을 확인)")
    pr.user_facts = _answer_facts(answers_text)
    pr.laws = ["개인정보 보호법 제26조(업무위탁에 따른 개인정보의 처리 제한) — 위탁 문서 필수 사항, 재위탁 시 위탁자 동의",
               "개인정보 보호법 제17조(개인정보의 제공) — 제3자 제공 시 정보주체 동의 등 근거",
               "개인정보 보호법 제28조의8(개인정보의 국외 이전)",
               "개인정보 보호법 제29조(안전조치의무)",
               "개인정보 보호법 제21조(개인정보의 파기)",
               "개인정보 보호법 제34조(개인정보 유출 등의 통지·신고)"]
    return pr


# ── 임시 수정 문구(관계를 단정하지 않는다) ────────────────────────────────────

def revision(pr: PrivacyReview, text: str, *, ours: str, theirs: str) -> dict[str, Any] | None:
    """처리 흐름이 있고 원문 보호 장치가 부족할 때만 — 개인정보 조 바로 뒤에 새 조(제N조의2)를 둔다."""
    if not (pr.active and ours and theirs):
        return None
    missing = [c for c in pr.checklist if c["status"].startswith(("없음", "보관 근거만"))]
    if not missing:
        return None
    arts, _annex = _tl.articles(text)
    by_path = {a.path: a for a in arts}
    host_path = (pr.privacy_paths[:1] or [a.basis[0] for a in pr.activities if a.basis][:1])
    host = by_path.get(host_path[0]) if host_path else None
    if host is None:
        return None
    base_no = host.no.split("의")[0]
    k = 2
    while f"{base_no}의{k}" in {a.no for a in arts}:
        k += 1
    new_no = f"{base_no}의{k}"
    new_path = _tl.art_path(new_no)
    O, T = _tl.label_quote(text, ours), _tl.label_quote(text, theirs)
    S = pr.subject or "정보주체"
    style = _tl.number_style(text)
    mk = (lambda i: f"({i})") if style == "paren" else (lambda i: _tl._CIRCLED[i - 1])
    jo = _tl.josa
    keys = {a.key for a in pr.activities}
    lines: list[str] = []

    def add(s: str) -> None:
        lines.append(f"{mk(len(lines) + 1)} {s}")

    add(f"{T}{jo(theirs, '은는')} 본 계약의 이행을 위하여 처리하는 {S}의 개인정보를 본 계약의 이행 목적에 필요한 최소한의 항목으로 "
        f"한정하여 처리하며, 처리 항목은 서비스 개시 전에 당사자가 서면으로 확정한다."
        + (f" {O}{jo(ours, '이가')} {T}에게 제공하는 {S} 정보도 같다." if "roster" in keys else ""))
    ref1 = "제(1)항" if style == "paren" else "제1항"
    add(f"{T}{jo(theirs, '은는')} {ref1}의 개인정보와 서비스 이용 과정에서 생성되는 {S}별 이용 내역을 {S}의 별도 동의 없이 "
        f"광고·마케팅 등 본 계약의 이행 목적 외의 용도로 이용하거나 제3자에게 제공하지 아니한다.")
    if "admin" in keys:
        add(f"{T}{jo(theirs, '이가')} {O}에게 제공하는 관리자 화면의 접근 권한은 {O}{jo(ours, '이가')} 지정한 담당자로 한정하며, "
            f"{T}{jo(theirs, '은는')} 관리자 화면의 접근 기록을 보관하고 {O}의 요청이 있으면 제공한다.")
    add(f"{T}{jo(theirs, '은는')} {O}의 사전 서면 동의 없이 {ref1}의 개인정보 처리를 제3자에게 다시 위탁하거나 국외로 이전하지 아니한다.")
    add(f"{T}{jo(theirs, '은는')} 개인정보 보호법 제29조에 따른 안전성 확보에 필요한 조치를 하여야 하고, 개인정보의 분실·도난·유출 "
        f"사실을 알게 된 때에는 지체 없이 그 사실과 대응 조치를 {O}에게 서면으로 통지하며, {O}의 점검 및 자료 제출 요청에 협조한다.")
    add(f"본 계약이 종료되면 {T}{jo(theirs, '은는')} 관계 법령에 따라 보존하여야 하는 정보를 제외하고 {ref1}의 개인정보를 지체 없이 "
        f"파기하거나 {O}에게 반환하고, 그 결과를 {O}에게 서면으로 통지한다.")
    add(f"{ref1}의 처리 가운데 {T}{jo(theirs, '이가')} {O}의 업무를 위탁받아 처리하는 부분에 대하여는 당사자가 서비스 개시 전에 "
        f"개인정보 보호법 제26조 제1항 각 호의 사항을 정한 문서를 작성한다.")
    head = f"{new_path} (개인정보의 처리)"
    return {"key": "privacy_flow", "article": host, "new_article": True, "new_no": new_no,
            "lines": [head] + lines, "location": f"{new_path} 신설",
            "issue_title": f"{S} 개인정보 처리 흐름에 맞는 보호 조항",
            "problem": (f"계약상 {S} 명단 전달·가입·개인별 이용 내역·관리자 열람 등 개인정보 처리 흐름이 있는데"
                        + (f" {', '.join(pr.generic_only)}는 ‘관련 법령 준수’ 일반 조항뿐이라" if pr.generic_only else " 개인정보 조항이 없어")
                        + " 처리 목적·항목, 목적 외 이용 금지, 재위탁·국외 이전, 안전조치·유출 통지, 종료 시 파기·반환이 정해져 있지 않습니다. "
                        "처리 관계(위탁·독자 처리·제3자 제공)는 운영약관·처리방침 확인 전이라 단정하지 않고, 어느 관계여도 필요한 의무만 둡니다."),
            "memo": ("처리 관계별 판단은 운영약관·개인정보 처리방침·가입 화면·위탁계약서를 받은 뒤 확정합니다. 위탁 관계로 확인되면 "
                     "마지막 항에 따라 위탁 문서를 따로 작성합니다. 회사명·로고 사용 승인은 홍보 조항에서 다루는 별개 문제입니다."),
            "tier": "HIGH" if len(pr.activities) >= 2 else "MEDIUM"}


def promo_sentence(pr: PrivacyReview, text: str, *, ours: str, theirs: str) -> str:
    """홍보 조항에 덧붙일 문장 — 회사 승인과 개인 정보 이용을 나눈다."""
    if not (pr.active and pr.promo):
        return ""
    O, T = _tl.label_quote(text, ours), _tl.label_quote(text, theirs)
    S = pr.subject or "정보주체"
    out = ""
    if not pr.promo.get("approval_in_contract"):
        out += f"{T}{_tl.josa(theirs, '은는')} {O}의 상호·로고 및 계약 체결 사실을 소개하기 전에 {O}의 사전 서면 승인을 받아야 한다. "
    out += (f"이 경우에도 {S} 등 개인을 알아볼 수 있는 정보(성명·사진·이용 내역 등)는 해당 개인의 별도 동의 없이 소개 자료에 포함하지 아니한다.")
    return out


def section_lines(pr: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    if not isinstance(pr, dict) or not pr.get("active"):
        return []
    out: list[tuple[str, str, str]] = [("heading", "0-1. 개인정보 처리 흐름 (활동별)", "")]
    out.append(("text", "검토 시작 근거: " + "; ".join(pr.get("trigger") or [])[:400], ""))
    if pr.get("generic_only"):
        out.append(("bullet", f"{', '.join(pr['generic_only'])}: ‘관련 법령 준수’ 일반 조항뿐 — 처리 흐름에 대한 보호로는 충분하지 않음", "high"))
    for a in pr.get("activities") or []:
        out.append(("bold", f"■ {a['name']}: {a['who']} → [{a['items']}] → {a['to']} (목적: {a['purpose']})", "medium"))
        out.append(("bullet", f"원문 확인: {a['contract_fact']}", ""))
        out.append(("bullet", f"운영 확인 필요: {a['ops_check']}", ""))
        out.append(("bullet", f"처리 관계: {a['relation']}", "high" if str(a['relation']).startswith("판단 보류") else ""))
    if pr.get("promo"):
        pm = pr["promo"]
        out.append(("bold", f"홍보 조항({pm['path']}) — 회사 승인과 개인 정보 이용을 구분", ""))
        out.append(("bullet", pm["corporate"], ""))
        if pm.get("personal"):
            out.append(("bullet", pm["personal"], "high"))
    out.append(("bold", "점검 항목", ""))
    for c in pr.get("checklist") or []:
        out.append(("bullet", f"{c['topic']}: {c['status']}", "high" if c["status"].startswith(("없음", "보관 근거만")) else ""))
    if pr.get("user_facts"):
        out.append(("bold", "사용자 답변(원문 아님)", ""))
        for f in pr["user_facts"]:
            out.append(("bullet", f, ""))
    if pr.get("docs_missing"):
        out.append(("bold", "미제공 자료 — 처리 관계 판단만 보류", "medium"))
        for d in pr["docs_missing"]:
            out.append(("bullet", d, ""))
    out.append(("bold", "데이터 제공·서비스 개시 전 충족할 조건", "high"))
    for c in pr.get("pre_launch") or []:
        out.append(("bullet", c, ""))
    out.append(("text", "적용 법령: " + "; ".join(pr.get("laws") or []), ""))
    return out


__all__ = ["Activity", "PrivacyReview", "analyze", "promo_sentence", "revision", "section_lines"]
