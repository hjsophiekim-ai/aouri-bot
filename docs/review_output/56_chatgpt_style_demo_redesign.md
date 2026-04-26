# /demo (ChatGPT 스타일) UX 리디자인

## 목표
- EP 탑재 전 시연용 화면을 “대화형 중심”으로 단순화
- 첫 화면은 아우리봇 이미지 + 핵심 카피 + 최소 입력(법인/계약유형/첨부/텍스트)만 노출
- 질문은 한 번에 1개씩(진행률 표시)
- 결과는 “대표 결론 1개” 중심으로 보여주고, 상세는 접을 수 있게 제공
- 기존 API를 최대한 재사용(`/api/questions/generate`, `/api/review/analyze`, `/api/revision/suggest_text`, `/api/draft/suggest`)

## 최종 URL
- ChatGPT 스타일 데모(신규 기본): `http://127.0.0.1:8787/demo`
- 기존 카드형 데모(보존): `http://127.0.0.1:8787/demo-v1`
- 이미지(정적): `http://127.0.0.1:8787/static/aouribot.png`

## 1) 화면 구조(3단계)
### 1단계: 시작 화면
- 아우리봇 이미지
- 큰 제목: “무슨 계약을 검토하고 싶으세요?”
- 부제: “계약서를 첨부하거나 내용을 입력하면 아우리봇이 먼저 검토 방향을 잡아드릴게요.”
- 입력 필드(최소):
  - 법인(entity)
  - 계약유형(contract_type)
  - 계약서 첨부(file, 선택)
  - 계약 내용 입력(text)
- CTA: “검토 시작”

### 2단계: 질문 화면
- 채팅형 UI(버블)
- 아우리봇이 1개 질문씩 표시
- 사용자는 답변 1개 입력 후 “다음”
- 상단 진행상태 배지: `질문 n/N`
- Enter로 다음(Shift+Enter 줄바꿈)

### 3단계: 결과 화면
- 상단 아우리봇 이미지 + “검토가 완료되었어요”
- 결과는 대표 결론 1개:
  - “위험도가 높아 법무 검토 권장”
  - “템플릿 기반 초안 작성 추천”
  - “먼저 수정 제안 확인 추천”
- 이유는 3~5줄로 간단히 표시(주요 이슈/추천 템플릿 등)
- 상세는 접을 수 있는 영역으로 제공:
  - 검출 issue
  - 적용 rule
  - 수정 제안 조항(JSON)
  - 추천 초안 템플릿/초안 생성 결과(JSON)
- CTA:
  - 수정 제안 확정(데모 확인용)
  - 초안 작성 확정(추천 템플릿이 있으면 기본값으로 `/api/draft/generate` 호출)
  - 다시 질문 보기
  - 처음으로

## 2) API 재사용 방식
- 질문 생성
  - 텍스트 입력: `POST /api/questions/generate`
  - 파일 첨부: `POST /api/upload`(서버 텍스트 추출 후 questions 반환)
- 최종 검토
  - `POST /api/review/analyze` (answers 포함)
  - `POST /api/revision/suggest_text` (answers 포함)
  - `GET /api/draft/suggest?contract_type=...`

## 3) 대표 결론 결정 로직(MVP)
- `high_risk=true` 또는 `approval_required=true` → “법무 검토 권장”
- 그 외:
  - 추천 템플릿 존재 + 이슈 조항이 거의 없으면 → “초안 작성 추천”
  - 기본값 → “수정 제안 확인 추천”

## 4) 구현 코드
- 데모 UI(신규): [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
- 라우팅 변경: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
  - `/demo` → ChatGPT 스타일 UI로 교체
  - `/demo-v1` → 기존 카드형 데모 유지

## 5) 실행/테스트 방법
1) 서버 실행
   - `cd aouri-bot`
   - `python -m runtime.app`
2) 브라우저 접속
   - `http://127.0.0.1:8787/demo`
3) “샘플 넣기” → “검토 시작”
4) 질문에 답변(Enter로 다음)
5) 결과 화면에서 대표 결론/상세 보기/CTA 확인

