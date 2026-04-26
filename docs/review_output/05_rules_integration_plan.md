# 05. Rules JSON 탑재 구현 계획 (MVP)

## 0. 목표/범위 요약
- 목표: `04_review_rules_master.json`을 레포에 “실제 탑재”하여, **rule 기반 계약검토 MVP**를 실행 가능 상태로 만든다.
- 우선순위: 추가 계약서 전수분석/OCR/포맷 확장보다 **시스템 탑재(로더/엔진/API/관리 기능)**를 먼저 구현한다.
- MVP 원칙:
  - 새 프레임워크 도입 금지(표준 라이브러리만 사용)
  - 기존 레포 구조(문서 중심 + 스크립트) 최대 유지
  - backlog(OCR/hwp/legacy doc) 처리는 이번 구현 범위에서 제외

## 1. 현재 repo 구조 분석
- 루트: `c:\Users\FURSYS\Desktop\aouribot`
- 주요 디렉토리
  - `docs/Contract`: 계약서 원본(대량)
  - `docs/Standard Contract`: 표준계약서 원본
  - `docs/review_output`: 추출/분석 산출물 및 스크립트(파이썬 1개, PowerShell 다수)
  - `aouri-bot/docs`: 요구사항/DB/API/프로그램/화면 설계 문서(.docx)
- 실행 가능한 코드(현재)
  - 파이썬: `docs/review_output/generate_verified_reports.py`
  - PowerShell: `docs/review_output/run_contract_text_extraction.ps1` 등
- 애플리케이션 코드 부재(현 상태)
  - `package.json/pyproject.toml/requirements.txt` 등 빌드/런타임 엔트리 없음
  - 백엔드/프론트/DB/API/Admin UI 구현 코드 없음(설계 문서만 존재)

## 2. 현재 기술스택 요약(“구현된 것” 기준)
- 운영/실행 환경: Windows + PowerShell
- 스크립트 런타임: Python(표준 라이브러리 사용), PowerShell
- 데이터 저장: 파일 기반(MD/JSON/CSV/TXT)
- 백엔드/프론트/DB: **현 레포에는 구현체 없음**(문서로만 정의됨)

## 3. 백엔드 / 프론트 / DB / API / Admin UI 구조 파악(현실 기준)
### 3.1 현 레포에서 확인 가능한 것
- API/DB/UI 설계 문서 위치: `aouri-bot/docs/아우리봇_*_v1.docx`
- 그러나 실제 서버/클라이언트/DB 코드가 없으므로 “현 구조 파악”은 불가능(미구현 상태).

### 3.2 MVP에서의 현실적인 구조 정의(새 프레임워크 없이)
- Backend(API): Python 표준 라이브러리 `http.server` 기반의 최소 JSON API(옵션)
- Review Service(핵심): 순수 Python 모듈(규칙 로드 + 룰 적용 + 결과 산출)
- DB: MVP에서는 **파일 저장소(JSONL/JSON)** 사용(마이그레이션 없음)
- Admin UI: MVP에서는 “관리 화면” 대신
  - (1) 룰/검토결과를 조회하는 JSON API 엔드포인트, 또는
  - (2) CLI(콘솔) 명령으로 룰 필터링/검증/프리뷰 제공

## 4. `04_review_rules_master.json` 배치/로딩 결정
### 4.1 배치 결정(권장)
- 소스(작성/검증본): `docs/review_output/04_review_rules_master.json` (유지)
- 런타임(탑재본): `aouri-bot/runtime/resources/review_rules_master.json` (신규)
  - 이유: `docs/review_output`는 산출물/분석 영역이고, 런타임은 “앱 리소스”로 분리하는 것이 운영에 유리
  - 규칙 업데이트 흐름: 산출물 JSON → (검수/승인) → 런타임 리소스로 복사(수동 또는 스크립트)

### 4.2 로딩 방식(MVP)
- 서버/CLI 시작 시 1회 로딩 + 메모리 캐시
- 로딩 시 검증:
  - `schema_version`, `status_enum`, `rules_by_status` 존재
  - 각 rule에 필수 필드 존재(요구: `rule_id, entity, contract_type, clause_type, rule_level, title, description, contract_evidence, risk_level, review_action, approval_required, tags`)
- 실패 시: 서비스 시작 실패(“룰 미탑재” 방지)

## 5. 모듈/컴포넌트 설계(어떤 파일에 넣을지)
> 새 프레임워크 없이도 “운영 가능한 MVP”를 만들기 위해, 최소한의 런타임 패키지를 추가한다.

### 5.1 Rule Loader
- 파일: `aouri-bot/runtime/rules/loader.py`
- 책임:
  - rules JSON 로드/스키마 검증/정규화(예: entity/contract_type 배열화)
  - status별 인덱스 구성

### 5.2 Review Service(룰 적용 엔진)
- 파일: `aouri-bot/runtime/review/engine.py`
- 입력:
  - `entity`(법인), `contract_type`(유형), `text`(본문), `metadata`(파일명 등)
- 출력(표준화된 결과 JSON):
  - 적용된 rule 목록(상태/리스크/승인필요/근거)
  - “탐지형” 룰과 “체크리스트형” 룰을 구분
- MVP 룰 적용 방식(현 JSON 제약 반영):
  - 체크리스트형(기본): `entity`/`contract_type`/`clause_type` 기반으로 관련 rule을 “반드시 보여줌”
  - 탐지형(제한적): `contract_evidence.example_phrase` 또는 `tags`(예: `trigger:*`)를 단순 키워드로 사용해 텍스트 포함 여부로 표시
  - 주의: 이 단계에서는 정교한 NLP/파싱 없이 “운영 가능한 1차 검토 체크”에 집중

### 5.3 Review API(선택: HTTP JSON)
- 파일: `aouri-bot/runtime/api/server.py`
- 프레임워크: Python 표준 라이브러리(`http.server`)
- MVP 엔드포인트(예시):
  - `GET /health`
  - `GET /rules` (필터: status/entity/contract_type)
  - `POST /review` (body: entity, contract_type, text, filename)
  - `GET /backlog` (참고용 backlog 반환)

### 5.4 Admin UI(이번 MVP에서는 UI “대체”)
- 구현 목표를 “관리 UI”가 아니라 “관리 기능”으로 정의
- 파일(옵션 A: CLI):
  - `aouri-bot/runtime/admin/cli.py`
  - 기능: 룰 목록/필터, 특정 룰 상세 보기, JSON 검증, 샘플 리뷰 실행
- 파일(옵션 B: 정적 문서):
  - `docs/review_output/06_rules_admin_guide.md` (운영자 가이드)

### 5.5 데이터 저장(결과/로그)
- 폴더: `aouri-bot/runtime/data/`
- 저장 형식(MVP):
  - 리뷰 결과: `review_runs/YYYYMMDD/*.json` (파일 기반)
  - 실행 로그: `logs/review_api.log` (텍스트)

## 6. Migration 필요 여부 판단
- DB 미구현 상태이므로 **마이그레이션 없음**
- 단, 향후 DB를 붙일 경우(설계문서 기준) 후보:
  - `review_rules`(룰셋 버전/상태/본문)
  - `review_runs`(검토 실행 이력)
  - `review_findings`(룰별 탐지 결과)
- 이번 MVP에서는 파일 저장으로 대체

## 7. 새로 만들 파일 목록(MVP)
- `aouri-bot/runtime/__init__.py`
- `aouri-bot/runtime/resources/review_rules_master.json` (탑재본)
- `aouri-bot/runtime/rules/__init__.py`
- `aouri-bot/runtime/rules/loader.py`
- `aouri-bot/runtime/review/__init__.py`
- `aouri-bot/runtime/review/engine.py`
- `aouri-bot/runtime/api/__init__.py`
- `aouri-bot/runtime/api/server.py` (선택)
- `aouri-bot/runtime/admin/__init__.py` (선택)
- `aouri-bot/runtime/admin/cli.py` (선택)
- `aouri-bot/runtime/data/.gitkeep` (또는 폴더만)
- `aouri-bot/runtime/README.md` (실행 방법)

## 8. 수정할 기존 파일 목록(MVP)
- 없음(권장): 기존 추출/분석 스크립트는 유지
- 단, “탑재본 JSON” 복사 자동화를 원하면 아래 중 하나를 추가(선택):
  - `docs/review_output/04_review_rules_master.json` → `aouri-bot/runtime/resources/` 복사 스크립트(새 파일)

## 9. 구현 순서(MVP)
1) 런타임 디렉토리 추가(`aouri-bot/runtime/*`) 및 rules JSON 탑재본 복사
2) Rule Loader 구현(로드/검증/정규화/인덱싱)
3) Review Engine 구현(체크리스트형 + 제한적 탐지형)
4) CLI(관리/테스트) 구현: 룰 로드 검증 + 단일 텍스트 리뷰 실행
5) (옵션) HTTP API 서버 구현: `/rules`, `/review`, `/backlog`
6) 샘플 입력 2~3건으로 “운영 시나리오” 검증(룰 출력/승인 필요 표시)

## 10. MVP 범위(이번 단계에서 제공)
- `review_rules_master.json` 로드/검증
- `entity + contract_type + text` 입력에 대해
  - 적용 대상 rule 목록 반환
  - 승인 필요(rule status: `approval_required`)만 필터링 반환 가능
  - backlog는 참고용으로만 제공(판정 로직에 사용하지 않음)
- 실행 형태:
  - CLI 우선(가장 간단하고 레포 현 상태와 정합)
  - 필요 시 HTTP API 추가

## 11. 이번 단계에서 하지 않을 것(명시)
- OCR/PDF 스캔본 처리 파이프라인
- hwp/hwpx/legacy doc 완전 지원
- DB 구축 및 마이그레이션
- 프론트엔드(Web UI) 신규 구현(프레임워크 도입 금지 준수)
- 정교한 조항 파싱(NLP/LLM 기반 자동 분류/요약)

## 12. 예상 위험요소
- 레포에 앱 코드가 없어서 “탑재”의 정의가 모호할 수 있음 → MVP는 **런타임 모듈 + CLI/API**로 명확히 정의
- rules JSON 일부 rule은 트리거 패턴이 명시적이지 않음 → MVP는 체크리스트 중심 + 제한적 탐지로 시작
- entity/contract_type 입력 표준화 필요 → loader에서 정규화(별칭 매핑) 필요
- 파일 기반 저장은 동시성/권한 이슈 가능 → MVP는 단일 실행 기준, 이후 DB 전환 고려

## 13. 다음 명령에서 바로 구현 가능한 준비 상태 여부
- 준비 상태: **YES**
- 근거:
  - 탑재 대상 룰셋 JSON이 이미 존재하고 파싱 검증 완료(`docs/review_output/04_review_rules_master.json`)
  - 계약서 본문 추출/분석 파이프라인이 별도로 존재(필요 시 샘플 텍스트 확보 가능)
- 단, “기존 백엔드/프론트/DB에 붙이는 작업”은 **코드가 아직 없기 때문에** 이번 MVP에서는 런타임 모듈/CLI/API 형태로 구현한다.

