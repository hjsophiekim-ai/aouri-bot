# 라이브 데모 런북 (Internal Demo /demo)

## 목적
- 현재 구현된 내부 데모 화면을 브라우저에서 바로 테스트할 수 있도록 “실행/검증/테스트 순서”를 정리한다.

## 1) runtime 앱 실행
- 작업 디렉토리: `aouri-bot/`
- 실행(권장):
  - `python -m runtime.app`

실행 시 콘솔 출력(예):
- `[AouriBot MVP] rules API started: http://127.0.0.1:8787/admin`
- `[AouriBot MVP] upload & review: http://127.0.0.1:8787/upload`

## 2) /health 확인
- URL: `GET http://127.0.0.1:8787/health`
- 기대 응답:
  - `{"status":"ok"}`

PowerShell:
```powershell
$base='http://127.0.0.1:8787'
Invoke-RestMethod "$base/health"
```

## 3) /demo 접속 주소 확인
- 내부 데모 화면: `http://127.0.0.1:8787/demo`
- Admin(참고): `http://127.0.0.1:8787/admin`

브라우저에서 바로 접속:
- `http://127.0.0.1:8787/demo`

## 4) 브라우저용 샘플 입력값 3개
아래 3개 중 하나를 /demo 화면에 붙여넣고 테스트한다.

### 샘플 A (물품공급/구매, high risk + approval 기대)
- entity: `퍼시스`
- contract_type: `물품공급/구매/매매`
- text:
```
제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제11조(면책) 상대방은 어떠한 경우에도 책임을 부담하지 아니한다.
제12조(기술자료) 당사는 상대방 요청 시 기술자료/원가자료/도면/소스코드를 제출한다.
제13조(해지) 상대방은 사전 통지 없이 즉시 해지할 수 있다.
```
- 기대: `high_risk=true`, `approval_required=true`, 수정 제안(issue_clause_count>0)

### 샘플 B (NDA, high risk + approval 기대)
- entity: `시디즈`
- contract_type: `NDA/비밀유지`
- text:
```
본 계약은 비밀유지 목적이며, 당사 또는 상대방이 제공하는 모든 정보는 비밀정보로 한다.
상대방은 위반 시 손해 전액을 배상하고, 책임 제한 없이(without limitation) 부담한다.
```
- 기대: `high_risk=true`, `approval_required=true`, 수정 제안(issue_clause_count>0)

### 샘플 C (대리점/유통, high risk + approval 기대)
- entity: `일룸`
- contract_type: `대리점/위탁/유통`
- text:
```
당사는 대리점 판촉비, 광고비, 반품 비용을 부담한다.
목표 미달 시 패널티를 부과한다.
```
- 기대: `high_risk=true`, `approval_required=true`, 수정 제안(issue_clause_count>0)

## 5) /api/questions/generate 테스트
- API: `POST http://127.0.0.1:8787/api/questions/generate`
- body: `{ entity, contract_type, filename?, text }`

PowerShell(샘플 A):
```powershell
$base='http://127.0.0.1:8787'
$body = @{
  entity='퍼시스'
  contract_type='물품공급/구매/매매'
  filename='case_supply.txt'
  text="제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다."
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Method Post -Uri "$base/api/questions/generate" `
  -ContentType 'application/json; charset=utf-8' -Body $body
```
- 기대:
  - `count`가 0보다 큼(상황에 따라 6~9개 수준)
  - `questions[]`에 `question_id/title/options` 포함

## 6) /api/review/analyze 테스트
- API: `POST http://127.0.0.1:8787/api/review/analyze`
- body: `{ entity, contract_type, filename?, text, answers? }`

PowerShell(샘플 A):
```powershell
$base='http://127.0.0.1:8787'
$body = @{
  entity='퍼시스'
  contract_type='물품공급/구매/매매'
  filename='case_supply.txt'
  text=@"
제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제11조(면책) 상대방은 어떠한 경우에도 책임을 부담하지 아니한다.
제12조(기술자료) 당사는 상대방 요청 시 기술자료/원가자료/도면/소스코드를 제출한다.
제13조(해지) 상대방은 사전 통지 없이 즉시 해지할 수 있다.
"@
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Method Post -Uri "$base/api/review/analyze" `
  -ContentType 'application/json; charset=utf-8' -Body $body
```
- 확인 포인트:
  - `summary.high_risk` / `summary.approval_required`
  - `matched_rules[]` (트리거 기반 매칭)
  - `checklist_rules[]` (체크리스트 성격의 룰)

## 7) /api/revision/suggest_text 테스트
- API: `POST http://127.0.0.1:8787/api/revision/suggest_text`
- body: `{ entity, contract_type, filename?, text, answers? }`

PowerShell(샘플 A):
```powershell
$base='http://127.0.0.1:8787'
$body = @{
  entity='퍼시스'
  contract_type='물품공급/구매/매매'
  filename='case_supply.txt'
  text=@"
제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제12조(기술자료) 당사는 상대방 요청 시 기술자료/원가자료/도면/소스코드를 제출한다.
"@
} | ConvertTo-Json -Depth 6

Invoke-RestMethod -Method Post -Uri "$base/api/revision/suggest_text" `
  -ContentType 'application/json; charset=utf-8' -Body $body
```
- 확인 포인트:
  - `revision.summary.issue_clause_count`
  - `revision.items[].applied_rules[].matched_keywords` (설명가능성)
  - `revision.items[].recommended_rewrite` (대표 대체 문안)

## 8) /api/draft/suggest 테스트
- API: `GET http://127.0.0.1:8787/api/draft/suggest?contract_type=...`

PowerShell 예시:
```powershell
$base='http://127.0.0.1:8787'
Invoke-RestMethod "$base/api/draft/suggest?contract_type=%EB%AC%BC%ED%92%88%EA%B3%B5%EA%B8%89"
```
- 확인 포인트:
  - `suggested_template_ids[]`에 추천 템플릿이 들어오는지
  - `items[]`에서 `supported=false`는 MVP에서 생성 불가(참고용 노출)

## 9) 문제 발생 시 즉시 점검 포인트
- `/health`가 OK가 아니면
  - 서버 콘솔 로그 확인(규칙 로드/DB 마이그레이션 실패 여부)
  - 이미 8787 포트가 사용 중인지 확인(중복 실행)
- `/demo`가 404면
  - 최신 코드로 재시작 필요(`python -m runtime.app`)
- `review/analyze`가 matched=0이어도
  - `checklist_rules`가 채워질 수 있음(특히 체크리스트 성격의 계약유형)
  - “이슈 탐지”가 아니라 “검토 포인트 제시” 목적일 수 있음

## 10) 브라우저에서 클릭 테스트 순서(권장)
1. `http://127.0.0.1:8787/demo` 접속
2. 샘플 A 텍스트 붙여넣기 + entity/contract_type 확인
3. “질문 엔진 실행” 클릭 → 질문 생성 확인
4. 질문에서 몇 개 선택(예: 개인정보/하도급/대리점 여부) 후 “답변 반영해서 재검토”
5. 우측 탭 “수정 제안” → “수정 제안 생성” 클릭
6. 우측 탭 “초안 작성” → “추천 템플릿” → “초안 생성” → “다운로드(.txt)”

## 라이브 데모용 URL(복사/붙여넣기)
- Health: `http://127.0.0.1:8787/health`
- Demo: `http://127.0.0.1:8787/demo`
- Admin: `http://127.0.0.1:8787/admin`
- EP Mock(참고): `http://127.0.0.1:8787/ep/mock/legal_request`

