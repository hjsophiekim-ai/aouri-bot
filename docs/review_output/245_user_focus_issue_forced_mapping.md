# 245. user_focus_issues 강제 매핑 레이어(표준화 + 표 출력)

## 목표
- 사용자 입력 중점 이슈(user_focus_issues)를 의미 기반으로 조항에 강제 매핑한다.
- 탐지 실패 시 “(탐지 없음)”으로만 끝내지 않고, 목적별 후보 조항/라벨을 결과에 포함한다.

## 변경(코드)
- dealer 계약에서 조항번호 기반으로 user_focus 매핑을 주입하고, 결과 메타에 테이블 형태로 제공:
  - [clause_level.py (user_focus_matches 주입)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L610-L706)
  - [clause_level.py (meta.user_focus_mapping_table)](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py#L1520-L1542)
- DOCX에도 목적별 후보 조항을 “중점 검토 내용” 섹션에 표기:
  - [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L489-L543)

