# 199) anchor clause 선택 정밀화(개인정보/침해사고)

## 문제

- 개인정보/침해사고 topic의 anchor가 기본원칙/목적 조항으로 잡혀,
  실제 보안/개인정보 조항이 아닌 곳에 대표 수정이 들어가는 문제가 발생.

## 개선

- anchor 점수 산정 시:
  - `보안/개인정보/정보보호` 키워드가 제목에 포함되면 가중치 강화
  - `목적/기본원칙` 등은 anchor 점수에서 감점
- 기본원칙/일반준수 조항은 keep_as_is로 우선 판정하여 anchor 후보에서 제외

## 구현 위치

- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

