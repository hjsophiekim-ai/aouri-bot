# 20. 사내 시스템 탑재를 위한 배포 준비 문서 (Rules 기반 계약검토 MVP)

## 1) 현재 완성 범위
- Rules 탑재/검증
  - `aouri-bot/runtime/resources/review_rules_master.json` 로드 및 schema validation
- 계약서 업로드/검토(테스트용 UI 포함)
  - `.txt/.docx` 업로드 → 텍스트 추출 → 사전 질문 → 답변 반영 검토 → 결과 표시
- Review 결과 저장/조회
  - SQLite 기반 저장: request/result/applied_rule/issue/rules_version_log
  - 조회 API: 목록/상세/필터
  - 관리자 UI: rules 조회, 리뷰 결과 조회
- Approval Queue(MVP)
  - high risk 또는 approval_required 건 자동 등록
  - 상태(new/in_review/approved/rejected) 변경 API/UI
- Batch review
  - `02_extracted_texts` 대상 batch 실행(dry-run 지원, JSONL/실패로그)
- Rules 갱신 스크립트
  - 검증/백업/교체/버전로그/롤백

## 2) 아직 미완료 범위(명시)
- OCR/PDF 스캔본 처리, HWP/HWPX, legacy DOC 처리
- 본격적인 사용자/권한/인증(사내 SSO/권한 분리)
- 실제 결재 시스템 연동(Approval Queue는 MVP 상태관리만)
- 정교한 조항 파싱/정규화(NLP/LLM 기반 자동 추출)
- 운영 환경용 관측(메트릭/알림/에러 트래킹)

## 3) 배포 전 체크리스트
- 규칙 파일 준비
  - `review_rules_master.json` 스키마 검증 통과 여부
- 서버 기동/포트 확인
  - 사내 네트워크 정책에 맞는 host/port 할당
- 저장소 경로/권한 확인
  - SQLite DB 파일 생성/쓰기 권한
  - rules 백업 폴더 쓰기 권한
- 기본 기능 점검
  - `/health`, `/admin`, `/upload`, `/admin/reviews`, `/admin/approval`
- 테스트 실행(가능하면)
  - `python -m unittest discover -s runtime/tests -v`

## 4) 필요한 환경변수
- 필수 환경변수는 없음(MVP 기본값으로 동작)
- 권장(운영 편의상) 환경변수(추후 적용 가능):
  - `AOURIBOT_HOST` (기본 `127.0.0.1`)
  - `AOURIBOT_PORT` (기본 `8787`)
  - `AOURIBOT_DB_PATH` (기본 `aouri-bot/runtime/data/db/aouribot.db`)
  - 현재 구현은 기본 경로/값을 사용하며, 운영 시 확장이 필요하면 추가 적용한다.

## 5) migration 적용 순서
- 서버 시작 시 자동으로 `schema_migrations` 기반 마이그레이션을 적용한다.
- 수동으로 확인하려면:
  - DB 파일: `aouri-bot/runtime/data/db/aouribot.db`
  - 적용 버전: `schema_migrations` 테이블 조회

## 6) rules 파일 반영 순서
1. 신규 rules JSON 준비(예: `docs/review_output/04_review_rules_master.json`)
2. 검증/적용:
   - 검증만: `python scripts/update_rules.py --new <path>`
   - 운영본 교체: `python scripts/update_rules.py --new <path> --apply`
3. 서버 재시작(권장)
4. 관리자 화면에서 rules_version_log 확인(조회 API 또는 DB)

## 7) 서버 실행/재시작 순서
- 실행:
  - `cd aouri-bot`
  - `python -m runtime.app`
- 재시작(Windows 콘솔 기준):
  - 기존 프로세스 종료(Ctrl+C)
  - 동일 명령으로 재기동

## 8) 점검 포인트
- 업로드/텍스트 추출 성공률
  - `.txt/.docx`만 지원, 그 외는 backlog로 처리됨
- 사전 질문 동작
  - 업로드 후 질문 생성 여부, 답변 반영 여부
- 결과 저장/조회
  - `/api/reviews` 목록 및 상세 조회 가능 여부
  - `rules_version`가 함께 표시되는지
- Approval Queue
  - high risk/approval_required 건 자동 등록 여부
  - 상태 변경 후 목록/상세에 반영되는지

## 9) 롤백 방법
- Rules 롤백
  - `aouri-bot/runtime/resources/backup/`에서 직전 백업본을 운영본으로 되돌린 후 서버 재시작
- DB 롤백(단순 MVP)
  - 운영 중에는 DB 삭제/초기화는 신중히 수행
  - 필요 시 `aouribot.db`를 백업 파일로 교체(데이터 유실 가능)

## 10) 운영 중 주의사항
- 현재 API/UI는 인증/권한이 없는 MVP이므로, 사내망 내부에서만 접근되도록 제한 필요
- rules 파일 교체는 운영자만 수행하고, 교체 후 서버 재시작/점검을 수행
- HWP/PDF(OCR) 등 미지원 포맷은 “추출 실패”로 돌아오며, 운영 절차에서 예외처리 필요
- 분류(entity/contract_type) 자동 추정은 편의용이므로, 중요한 건은 사용자 확인/수정 후 진행 권장

