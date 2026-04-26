# 15. Batch Review 스크립트 (02_extracted_texts 대상, MVP)

## 1) 목표
- `docs/review_output/02_extracted_texts`의 추출 텍스트(.txt)를 대상으로 batch review를 실행한다.
- 결과를 JSONL로 저장하고(옵션으로 DB 저장), 실패 파일은 별도 로그로 남긴다.
- OCR/HWP/legacy DOC 처리 같은 backlog는 이번 범위에서 제외한다.

## 2) 구현 파일
- 스크립트: `scripts/run_batch_review.py`

## 3) 실행 방법
### 3.1 dry-run(저장 없이 실행)
```bash
python scripts/run_batch_review.py --dry-run --limit 10
```

### 3.2 실제 저장(DB + JSONL)
```bash
python scripts/run_batch_review.py --limit 100
```

## 4) 옵션
- `--input-dir`: 입력 디렉토리(기본: `docs/review_output/02_extracted_texts`)
- `--dry-run`: DB 저장을 하지 않음(요약/JSONL만 생성)
- `--output-jsonl`: 결과 JSONL 저장 경로
- `--fail-log`: 실패 로그 경로
- `--limit`: 처리 파일 수 제한(0이면 전체)

## 5) entity / contract_type 매핑 방법(MVP)
- 현재는 “파일명 + 텍스트” 기반 휴리스틱 자동추정 사용:
  - `runtime/review/classify.py`
- 향후 운영 품질을 위해 다음 중 하나로 고도화 가능:
  - 파일명 prefix 규칙(법인별 폴더/네이밍) 기반 매핑 테이블
  - 업로드 단계에서 사용자 입력을 우선 저장(질문 플로우와 결합)

## 6) 로그/결과 파일
- 결과 JSONL: `docs/review_output/15_batch_review_results_YYYYMMDD_HHMMSS.jsonl`
- 실패 로그: `docs/review_output/15_batch_review_failures_YYYYMMDD_HHMMSS.log`
- 성공/실패 카운트는 스크립트 종료 시 콘솔 출력

