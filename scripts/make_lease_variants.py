"""천안 상가 임대차 변형 계약 — 회사명·조번호·담보 수준·당사자 역할을 바꾼 4건을 만든다.

같은 판단이 회사명·조번호가 아니라 거래 내용에서 나오는지 확인하기 위한 입력이다.
  v1_renamed_shifted  회사명·금액·조번호(제3조 신설로 이후 +1)·내부 참조를 모두 바꿈 — 핵심 지적이 남아야 한다
  v2_sufficient       1순위 근저당이 보증금 전액을 넘게 담보, 선순위 없음, 보증 최고액 금액 특정, 주차장 단독소유·승계 포함
                      — 불필요한 수정이 줄어야 한다
  v3_missing          근저당·질권·연대보증 없음 — 보증금 무담보 핵심 지적이 남아야 한다
  v4_role_reversed    우리 회사가 임대인 — 보증금 회수 위험을 우리 위험으로 쓰면 안 된다

Usage: python scripts/make_lease_variants.py SRC_TXT OUT_DIR
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def renamed_shifted(t: str) -> str:
    t = t.replace("주식회사 가람개발", "주식회사 한빛개발").replace("가람빌딩", "한빛빌딩")
    t = t.replace("남궁민", "김정호").replace("남 궁 민", "김 정 호")
    t = t.replace("㈜일룸", "주식회사 시디즈").replace("주식회사 일룸", "주식회사 시디즈").replace("일룸", "시디즈")
    t = t.replace("홍 대 표", "홍 길 동")
    t = t.replace("충남 가온시 가온읍 가온리 100", "경기 평택시 고덕면 여염리 512")
    t = t.replace("가온읍 가온리 98", "고덕면 여염리 520").replace("가온리 98", "여염리 520")
    # 금액: 보증금 6억(계약금·잔금 각 3억), 채권최고액 3.6억, 월 임대료 3,500만
    t = t.replace("금오억원(₩500,000,000)", "금육억원(₩600,000,000)").replace("금오억원", "금육억원")
    t = t.replace("금 오억원(\\500,000,000)", "금 육억원(\\600,000,000)")
    t = t.replace("금이억오천만원(₩250,000,000)", "금삼억원(₩300,000,000)")
    t = t.replace("금이억오천만원(\\250,000,000)", "금삼억원(\\300,000,000)")
    t = t.replace("금이억오천만원", "금삼억원")
    t = t.replace("채권최고액 금삼억원", "채권최고액 금삼억육천만원")
    t = t.replace("金 삼천만원(\\30,000,000)", "金 삼천오백만원(\\35,000,000)")
    t = t.replace("금 구천만원", "금 일억오백만원")
    # 조번호: 제2조 뒤에 정의 조항을 신설 → 제3조 이후 +1, 본문 참조도 함께
    def bump_head(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return f"제 {n + 1 if n >= 3 else n}조"
    t = re.sub(r"제 (\d+)조(?=\()", bump_head, t)
    t = re.sub(r"제 ?(\d+)조(?!\()", lambda m: f"제 {int(m.group(1)) + 1 if int(m.group(1)) >= 3 else int(m.group(1))}조", t)
    t = t.replace("제 3조(임대차 기간)", "제 3조(정의)\n본 계약에서 “임대차 목적물”은 제1조에 표시된 토지·건물·주차장 사용 부분을 말한다.\n제 4조(임대차 기간)", 1)
    return t


def sufficient(t: str) -> str:
    t = t.replace("채권최고액 금삼억원의 근저당권을 공동으로 설정한다.",
                  "채권최고액 금육억원의 1순위 근저당권을 공동으로 설정한다. “임대인”은 근저당권 설정 당시 목적물 및 대지에 선순위 담보권·가압류가 없음을 보증한다.")
    t = re.sub(r"잔금 지급 시에는 잔금 상당액을[\s\S]*?재질권설정 진행한다\. ", "", t)
    t = t.replace("(6) 임대보증금의 계약금을 “임대인”이 지정하는 통장으로 입금하며, 잔금 진행시 금이억오천만원(\\250,000,000)에 대해서는 질권설정을 진행한다.",
                  "(6) 임대보증금은 “임대인”이 지정하는 통장으로 입금한다.")
    t = t.replace("근저당권(3억원)", "근저당권(6억원)").replace("\n질권\n", "\n근저당권\n")
    # 선순위 담보 전제 문구 제거
    t = t.replace("3. 선순위 담보채무의 이자 또는 원리금 1개월 이상 연체\n", "")
    t = re.sub(r"\(4\) “임대인”이 선순위 담보채무의[^\n]*\n", "", t)
    t = t.replace("“임대인”의 보증금 반환채무 중 질권으로 담보되지 않는 금이억오천만원에 대하여는", "“임대인”의 보증금 반환채무에 대하여는")
    # 보증 최고액 금액 특정
    t = t.replace("손해배상채무(일룸 투자비 한도)를 “임대인”과 연대하여 보증한다.",
                  "손해배상채무를 “임대인”과 연대하여 보증한다. 이 보증채무의 최고액은 금칠억원(₩700,000,000)으로 한다.")
    # 주차장: 단독 소유 + 승계 포함
    t = t.replace("주차장 일부(9829.2분의 929.97)", "주차장 부지 전체")
    t = t.replace("양수인이 제 1호의 승낙을 승계하도록 한다.", "양수인이 제 1호의 승낙 및 제2호의 사용 승인을 승계하도록 한다.")
    return t


def missing(t: str) -> str:
    t = re.sub(r"“임대인”은 계약금 지급과 동시에[\s\S]*?위 담보 설정 비용은 “임차인”이 부담한다\.", "", t)
    t = t.replace("근저당권(3억원)", "-").replace("\n질권\n", "\n-\n")
    t = t.replace("(6) 임대보증금의 계약금을 “임대인”이 지정하는 통장으로 입금하며, 잔금 진행시 금이억오천만원(\\250,000,000)에 대해서는 질권설정을 진행한다.",
                  "(6) 임대보증금은 “임대인”이 지정하는 통장으로 입금한다.")
    t = re.sub(r"\(3\) 다음 각 호의 사유가 발생한 경우, “임대인”의 보증금 반환채무 중[\s\S]*?4\. “임대인” 또는 “토지소유자”에 대한 회생 또는 파산 신청\n", "", t)
    t = re.sub(r"\(4\) “임대인”이 선순위 담보채무의[^\n]*\n", "", t)
    t = t.replace("4. 본 계약에 따른 “임대인”의 보증금(금오억원) 반환채무 및 손해배상채무(일룸 투자비 한도)를 “임대인”과 연대하여 보증한다.\n", "")
    t = t.replace("[토지소유주 겸 연대보증인]", "[토지소유주]")
    return t


def role_reversed(t: str) -> str:
    # 우리 회사(일룸)가 건물 소유 임대인, 상대방(가람개발)이 임차인
    t = t.replace("주식회사 가람개발(이하 “임대인”이라 한다)", "주식회사 일룸(이하 “임대인”이라 한다)")
    t = t.replace("㈜일룸(이하 “임차인”이라 한다)", "주식회사 가람개발(이하 “임차인”이라 한다)")
    t = t.replace("- 소유자 주식회사 가람개발", "- 소유자 주식회사 일룸")
    t = t.replace("예금주\n계좌정보\n주식회사 가람개발", "예금주\n계좌정보\n주식회사 일룸")
    t = t.replace("[임대인]\n법 인 명 : 주식회사 가람개발", "[임대인]\n법 인 명 : 주식회사 일룸@@")
    t = t.replace("[임차인]\n법 인 명 : 주식회사 일룸", "[임차인]\n법 인 명 : 주식회사 가람개발")
    t = t.replace("주식회사 일룸@@", "주식회사 일룸")
    t = t.replace("손해배상채무(일룸 투자비 한도)", "손해배상채무(임차인 투자비 한도)")
    return t


FOCUS_V1 = """제  목

 평택고덕(가칭) 매장 임대차계약서 법무검토 요청

신청배경 : 시디즈가 평택 건물에 임대차 계약을 체결하려고 함. 토지 소유주와 건물 소유주가 다르고, 보증금 6억 중 3억은 건물과 토지에 근저당(채권최고액 3.6억), 토지 소유자를 물상보증인으로, 나머지 3억은 예금 질권을 설정하려고 함.

요청사항

 1. 임대차계약서 초안 검토

 2. 보증금에 대한 보호

  - 3억 근저당권(채권최고액 3.6억)에 대한 보호(낙찰가율이 좋지 않아 제 15조 특약으로 보완함)

    감정평가 80억(선순위 근저당 55억 포함)

  - 건물 뒤 공동 주차장(여염리 520 일부 지분, 토지주 보유, 감정평가 제외)까지 공동담보 설정 여부

 3. 토지주와 건물주(임대인) 상이에 따른 연대보증

 4. 매장 공동사용을 위한 계열사 전대 동의

 5. 매장 투자비에 대한 안전장치

 6. 기타 계약시 체크해야할 사항
"""

FOCUS_V4 = """제  목

 가온 건물 임대(임대인 입장) 법무검토 요청

신청배경 : 일룸 소유 건물을 가람개발에 임대하려고 함. 임차인이 보증금 보호를 위해 건물·토지 근저당과 예금 질권을 요구함.

요청사항

 1. 임대차계약서 초안 검토

 2. 임차인이 요구하는 보증금 담보(근저당·질권) 제공에 따른 우리 측 부담

 3. 기타 계약시 체크해야할 사항
"""


def main() -> None:
    src = Path(sys.argv[1]).read_text(encoding="utf-8")
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    base_focus = (Path(__file__).resolve().parents[1] / "reports_evidence/cheonan_lease/config/review_focus.txt").read_text(encoding="utf-8")
    (out / "v1_renamed_shifted.txt").write_text(renamed_shifted(src), encoding="utf-8")
    (out / "v1_focus.txt").write_text(FOCUS_V1, encoding="utf-8")
    (out / "v2_sufficient.txt").write_text(sufficient(src), encoding="utf-8")
    (out / "v2_focus.txt").write_text(base_focus.replace(
        "감정평가 64억(선순위 근저당 44.5억+일룸 근저당 3억 포함시 43.7억 -> 74.1% 수준)", "선순위 담보 없음(1순위 근저당)"), encoding="utf-8")
    (out / "v3_missing.txt").write_text(missing(src), encoding="utf-8")
    (out / "v3_focus.txt").write_text(base_focus, encoding="utf-8")
    (out / "v4_role_reversed.txt").write_text(role_reversed(src), encoding="utf-8")
    (out / "v4_focus.txt").write_text(FOCUS_V4, encoding="utf-8")
    print(sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main()
