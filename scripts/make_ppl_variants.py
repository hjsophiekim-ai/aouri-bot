"""협찬(PPL) 계약 검증용 변형 4종을 만든다 — 회사명·조번호·보호조건·당사자 역할을 바꾼다.

Usage: python scripts/make_ppl_variants.py INPUT.docx OUT_DIR

  v1_renamed_shifted.txt   당사자·브랜드·프로그램명 변경 + 앞에 조 하나를 끼워 모든 조번호(본문 참조 포함)를 하나씩 민다
  v2_sufficient.txt        보장 사항 확정·집계 기준·미달 처리·최종 기한·게시일 연동 청구·라이선스 승인 면제·표시 의무를 넣는다
  v3_missing.txt           불이행분 정산·반환 조항(해지 시 반환, 손해배상 반납)을 지운다
  v4_role_reversed.docx    두 회사의 자리를 바꾼다 — 우리 회사가 협찬을 받아 제작·게시하는 쪽(을)
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _shift(text: str) -> str:
    t = re.sub(r"제\s*(\d+)\s*조", lambda m: f"제 {int(m.group(1)) + 1} 조" if " " in m.group(0) else f"제{int(m.group(1)) + 1}조", text)
    head, sep, rest = t.partition("제 2 조 (계약의 목적)")
    return head + "제 1 조 (정의)\n본 계약에서 \"게시일\"이란 대상 프로그램이 해당 채널에 최초로 공개된 날을 말한다.\n" + sep + rest


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    from runtime.review.text_extract import extract_text_from_file

    text = extract_text_from_file(src).text

    v1 = (text.replace("주식회사 시디즈", "주식회사 한빛가구").replace("시디즈", "한빛가구")
          .replace("주식회사 씨제이이엔엠", "주식회사 다온미디어").replace("씨제이이엔엠", "다온미디어")
          .replace("CJ ENM", "다온미디어").replace("알로소", "루미에").replace("적수다", "오늘의 거실")
          .replace("사피엔스스튜디오", "다온스튜디오"))
    (out / "v1_renamed_shifted.txt").write_text(_shift(v1), encoding="utf-8")

    v2 = text
    v2 = v2.replace("손해배상을 청구할 수 있다. ‘", "손해배상을 청구할 수 있다. 다만, 제1항 제1호 및 제4호의 보장·최소 수량은 예정 사항에 해당하지 아니하며 ‘을’은 ‘갑’의 사전 서면 동의 없이 이를 변경하거나 축소할 수 없다.")
    v2 = v2.replace("본편 및 브랜디드 쇼츠는 게시일 기준 최소 3개월간 공개 상태를 유지한다",
                    "본편 및 브랜디드 쇼츠는 게시일 기준 최소 3개월간 공개 상태를 유지한다\n"
                    "⑩ 제1항 제1호의 조회수는 유튜브 스튜디오 공식 통계로 게시일부터 3개월간 집계하며 유료 광고 유입은 포함하지 아니한다. "
                    "‘을’은 집계 결과와 증빙을 ‘갑’에게 제공하고, 보장 조회수에 미달하면 집계 종료일부터 30일 이내에 추가 노출로 보완하며, "
                    "보완되지 아니한 부분은 협찬 대금 중 오프닝 PPL 배분액 3천만원에 미달 비율을 곱한 금액을 반환한다.\n"
                    "⑪ ‘을’은 협찬 콘텐츠에 ‘갑’과의 경제적 이해관계(유료광고 포함 사실)를 관련 법령과 심사지침에 따라 표시한다.")
    v2 = v2.replace("2026년 10월 29일자로", "대상 프로그램의 실제 게시일 이후에")
    v2 = v2.replace("사전 협의된 기간 내에서 프로그램의 방송 일정을 조정 또는 연장할 수 있다.",
                    "사전 협의된 기간 내에서 프로그램의 방송 일정을 조정 또는 연장할 수 있다. 다만, 늦어도 2026년 12월 31일까지 게시하지 "
                    "아니한 사항은 제9조 제3항에 따라 정산·반환한다.")
    v2 = v2.replace("‘을’과 사전 서면 합의를 거쳐야 한다.",
                    "‘을’과 사전 서면 합의를 거쳐야 한다. 다만, 제3조 제1항 제3호의 마케팅 라이선스 범위 안의 활용과 그 기간(최초 게시일부터 기산)에는 "
                    "사전 서면 합의를 요하지 아니한다.")
    (out / "v2_sufficient.txt").write_text(v2, encoding="utf-8")

    v3 = re.sub(r"③ ‘을’은 해제 또는 해지 시점까지[^\n]*\n", "", text)
    v3 = re.sub(r"\n③ 본 계약이 ‘을’의 귀책사유로 해제 또는 해지 된 경우[^\n]*", "", v3)
    v3 = re.sub(r"① ‘을’이 본 계약의 협찬의 대가를 계약내용대로 이행하지 않았을 경우[^\n]*\n", "", v3)
    v3 = re.sub(r"\n① ‘을’이 본 계약의 협찬의 대가를[^\n]*", "", v3)
    v3 = re.sub(r"(?m)^‘을’이 본 계약의 협찬의 대가를 계약내용대로 이행하지 않았을 경우[^\n]*\n?", "", v3)
    v3 = re.sub(r"(?m)^본 계약이 ‘을’의 귀책사유로 해제 또는 해지 된 경우[^\n]*\n?", "", v3)
    (out / "v3_missing.txt").write_text(v3, encoding="utf-8")

    with zipfile.ZipFile(src) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    xml = parts["word/document.xml"].decode("utf-8")
    # 회사명은 DOCX 안에서 별도 run 으로 쪼개져 있다 — 이름 단위로 바꾼다.
    xml = xml.replace("시디즈", "@@A@@").replace("씨제이이엔엠", "시디즈").replace("@@A@@", "한빛전자")
    parts["word/document.xml"] = xml.encode("utf-8")
    with zipfile.ZipFile(out / "v4_role_reversed.docx", "w", zipfile.ZIP_DEFLATED) as z:
        for n, b in parts.items():
            z.writestr(n, b)
    print("ok")


if __name__ == "__main__":
    main()
