# 150) DOCX redline 출력 개선(변경 부분만 표시)

문제:
- 수정본 Word에서 문장/문단 전체가 빨간색으로 보이며, 무엇이 바뀌었는지 한눈에 파악하기 어려움

목표:
1) 삭제된 부분만 취소선 + 빨간색  
2) 추가된 부분만 빨간색  
3) 변경 없는 문구는 원래 색 유지  
4) 문단 전체를 통째로 빨갛게 칠하지 않기  
5) token/phrase 단위 diff  
6) 조항별 수정 이유는 표(부록)로 정리

---

## 1) 구현 변경

### 1.1 토큰화 개선(더 세밀한 diff)

- 기존: 공백 vs 비공백 단위로만 분해 → replace 블록이 커질 수 있음
- 개선: 한글/영문/숫자 “단어” + “구두점” + “공백” 단위로 분해해 diff granularity를 높임

구현: [docx_writer.py:_words](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

### 1.2 스타일 정책 변경

- insert: 빨간색(color)만
- delete: 빨간색(color) + 취소선(strike)
- equal: 스타일 없음(기본 검정)
- underline은 제거(요구사항: 추가는 red만)

구현: [docx_writer.py:_diff_runs](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

---

## 2) python-docx 사용 여부

현재 실행 환경에서 `python-docx`가 설치되어 있지 않아, python-docx 대신 기존 방식(WordprocessingML DOM 생성)을 유지하되,
- “run 단위” 텍스트 노드(w:t)를 세밀하게 구성하여
- 실질적으로 python-docx의 `run` 조립과 동일한 결과를 내도록 개선했습니다.

---

## 3) 회귀 테스트

- 변경 run(색 있는 run)과 변경 없는 run이 함께 존재하는지 검사:
  - [test_buyer_favorable_regression.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression.py)
  - [test_buyer_favorable_regression_v2.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/tests/test_buyer_favorable_regression_v2.py)

