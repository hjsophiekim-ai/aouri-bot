# 171. 한국어 법무 문체 후처리(조사/반복/메타 표현 제거)

## 문제
- 수정문안/부록에 조사 오류(예: `상대방는`), 어색한 연결, 반복 표현이 섞여 가독성이 떨어졌다.
- 사용자에게 보이는 문구에 “buyer_favorable 기준” 같은 메타 표현이 섞일 수 있었다.

## 목표
1) rewrite 후 한국어 문장 품질 후처리  
2) 조사/띄어쓰기/반복 표현 제거  
3) 메타 표현(예: buyer_favorable, 구매자 보호 방향…)이 최종 문서에 노출되지 않게  
4) 사용자 노출 문구를 법무 검토 문체로 정리  
5) 부록도 토큰 나열이 아니라 자연어 중심으로 출력  

## 변경 사항
### 1) 후처리 유틸 추가
- 파일: [korean_polish.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/korean_polish.py)
- 기능:
  - 대표 조사 오류 치환(`상대방는→상대방은` 등)
  - 불필요 메타 문구 제거
  - 공백/개행 정리

### 2) deterministic rewrite 및 AI rewrite 결과에 후처리 적용
- deterministic: [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)
  - 최종 `suggested_rewrite` / `rewrite_reason`에 후처리 적용
  - “구매자 보호 방향(...)” 프리픽스 제거(문서 노출 방지)
- AI rewrite: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
  - AI가 반환한 `rewrite_reason`/`suggested_rewrite`에도 동일 후처리 적용

### 3) 부록 토큰 나열 완화(168 연동)
- Word 부록은 토큰 나열 대신 “수정 전/후 핵심 표현”을 diff 기반으로 뽑아 가독성을 개선한다.

## 기대 효과
- 문서(앱/Word)에서 어색한 조사/메타표현 노출이 줄고, 법무팀이 읽기 쉬운 문체로 정리된다.

