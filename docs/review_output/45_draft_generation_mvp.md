# 템플릿형 계약서 초안 작성 MVP (docs/Standard Contract 기반)

## 목표
- 법인 선택
- 계약유형 선택
- 기본 변수 입력(당사/상대방/목적)
- 표준계약서 기반 초안 생성
- 화면 텍스트 미리보기 + 다운로드 가능한 텍스트 제공(문서 생성은 후속)

## 구현 상태(실제 코드)
### 서비스
- 템플릿 목록/지원 여부: [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)
  - `list_standard_templates()`
  - `generate_draft_text(...)`
- 샘플 템플릿 매핑(계약유형 → 추천 템플릿): [service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/draft/service.py)
  - `DEFAULT_TEMPLATE_HINTS`
  - `suggest_template_ids(contract_type)`

### API
Base URL: `http://127.0.0.1:8787`
- `GET /api/draft/templates`
  - 표준 템플릿 목록 + `supported` 여부
- `GET /api/draft/suggest?contract_type=...`
  - 계약유형 문자열 기반 추천 템플릿 ID 목록(`suggested_template_ids`)
- `POST /api/draft/generate`
  - body: `{ template_id, entity, contract_type, party_a, party_b, purpose? }`
  - 응답에 `draft_text` 포함(JSON)
- `POST /api/draft/download`
  - 동일 body로 호출
  - 응답: `Content-Disposition` 첨부로 `.txt` 다운로드

### UI
- EP Mock의 “계약서 초안 작성” 탭에서 사용 가능:
  - [ep_legal_request_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/ep_legal_request_ui.py)
- EP 없이 시연 가능한 내부 데모 화면에서도 사용 가능:
  - `GET /demo`

## 동작 원칙(MVP)
- LLM 없이 템플릿(docx/txt)에서 텍스트를 추출해 “변수 치환 + 기본 구성”으로 초안을 생성한다.
- 표준계약서가 없는 유형(또는 MVP 미지원 템플릿)은 `supported=false`로 노출된다.
  - UI에서 선택은 가능하되, MVP에서는 생성 실패 또는 “초안 불가/기준 필요” 형태로 처리하는 방향이 안전하다.

## 사용 예시(PowerShell)
```powershell
$base = 'http://127.0.0.1:8787'

# 1) 추천 템플릿 조회
Invoke-RestMethod "$base/api/draft/suggest?contract_type=%EB%AC%BC%ED%92%88%EA%B3%B5%EA%B8%89"

# 2) 초안 생성(JSON)
$payload = @{
  template_id = '영문 물품공급 계약서.docx'
  entity = '퍼시스'
  contract_type = '물품공급/구매/매매'
  party_a = '퍼시스 주식회사'
  party_b = '상대방'
  purpose = '물품 공급'
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "$base/api/draft/generate" `
  -ContentType 'application/json; charset=utf-8' -Body $payload
```

## 후속 고도화(구조만 준비)
- docx 출력/다운로드(서식 유지) 및 EP 첨부 연결
- 템플릿 없는 유형에 대해:
  - rule 기반 체크리스트로 “필수 조항 누락” 안내
  - (AI 도입 시) 템플릿 기반 + AI 보완 생성

