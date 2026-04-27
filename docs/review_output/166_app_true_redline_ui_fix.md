# 166. 앱 화면 True Redline(diff) UI 적용 + Risk tier 컬러 체계

## 문제
- 기존 데모 UI는 `suggested_rewrite` 전체 블록을 `.rewrite` 클래스로 빨간색+밑줄 처리하여,
  - 어디가 삭제/추가/변경인지 한눈에 구분이 불가능했다.

## 목표
1) 앱 화면에서도 원문 vs 수정문 diff 계산  
2) 삭제만 빨간색 + 취소선  
3) 추가만 빨간색  
4) 변경 없는 문구는 기본 검정색  
5) 고위험(HIGH)만 빨간색 redline  
6) 중간/중간이하(MEDIUM/LOW)는 파란색 guidance box  
7) 화면상 “수정된 부분만” 눈에 들어오게 하기  

## 변경 사항
### 1) 블록 전체 강조 제거 및 diff 기반 렌더링 도입
- 파일: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
- 변경:
  - `.rewrite`(전체 빨간색/밑줄) 스타일 제거
  - 토큰 단위 diff를 계산해 `<span class="ins">` / `<span class="del">`로 렌더링
    - insert: 빨간색
    - delete: 빨간색 + 취소선
    - equal: 기본색

### 2) Risk tier 기반 표시 정책
- 고위험/승인필요(`high_risk || approval_required`)만 “필수 수정(redline)”로 표시
- 그 외는 “권장/참고(guidance)”로 파란색 박스에 정리
  - 방향(suggested_direction)
  - 사유(rewrite_reason)
  - 참고 문안(suggested_rewrite)

### 3) UI에서 조항 위치 표시(display_path) 반영
- 조항 카드 제목에 `display_path`를 우선 노출하여 `제n조 제m항 k호` 맥락이 유지되도록 했다.

## 서버 응답 필드 보강
- UI에서 guidance에 방향을 보여줄 수 있도록, clause-level 결과에 `suggested_direction`을 포함했다.
- 파일: [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

