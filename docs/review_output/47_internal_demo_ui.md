# 내부 데모용 단일 화면(/demo) (EP 없이 시연 가능)

## 목표
- EP 연동 전에도 바로 시연할 수 있는 최소 워크플로우 제공
  - 계약 텍스트 입력/업로드(본 화면은 텍스트 입력)
  - 법인 선택
  - 계약유형 선택
  - 질문 엔진 실행
  - review analyze 실행
  - 수정 제안 보기
  - 초안 작성 보기
  - 결과 요약 보기

## 접속 주소
- 내부 데모 화면: `http://127.0.0.1:8787/demo`

## 구현 코드
- UI: [internal_demo_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_ui.py)
- 라우팅: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
  - `GET /demo`
  - `POST /api/questions/generate`
  - `POST /api/revision/suggest_text`
  - `GET /api/draft/suggest`
  - `POST /api/draft/generate`
  - `POST /api/draft/download`
  - `POST /api/review/analyze` (기존)

## 화면 구성(MVP UX)
- 좌측: 입력 + 질문/답변
  - entity / contract_type 입력
  - 계약 텍스트 입력
  - “질문 엔진 실행” → 질문 리스트 생성
  - 질문 답변 선택 후 “답변 반영해서 재검토”
- 우측: 탭 구조(EP 패널 이식이 쉬운 형태)
  - 결과 요약(JSON)
  - 수정 제안(조항별 이슈/적용 rule/대체 문안)
  - 초안 작성(템플릿 선택/추천/생성/다운로드)

## 동작 흐름
1) 텍스트 입력 + entity/contract_type 지정  
2) 질문 엔진 실행  
   - `/api/questions/generate` 호출
   - 내부적으로 1회 analyze를 수행해 detected_rule_ids를 얻고, 질문 세트를 생성한다.
3) 답변 선택 후 재검토  
   - `/api/review/analyze`에 `answers` 포함 호출
4) 수정 제안 탭  
   - `/api/revision/suggest_text`로 조항 분해 + rule 매칭 기반 수정 제안 생성(v2 포함)
5) 초안 작성 탭  
   - `/api/draft/templates`로 목록 로드
   - `/api/draft/suggest`로 계약유형 기반 추천 템플릿 표시
   - `/api/draft/generate`로 초안 생성(JSON 미리보기)
   - `/api/draft/download`로 `.txt` 다운로드

## 검증(테스트 클라이언트)
- `/demo` HTTP 200 확인
- `/api/questions/generate` 정상 응답(예: count=9, detected rules 포함)
- `/api/revision/suggest_text` 정상 응답(issue_clause_count>0)
- `/api/draft/suggest` 정상 응답(추천 템플릿 ID 목록)

## 제약(MVP)
- 본 화면은 “텍스트 입력” 중심(파일 업로드는 `/upload` 화면 사용)
- 결과는 키워드 기반 스크리닝이므로, 법률 판단/결재 자동화에 직접 사용하면 안 됨

