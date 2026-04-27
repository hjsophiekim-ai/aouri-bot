# 187) Review Latency Benchmark

- base_url: `http://127.0.0.1:8787`
- generated_at: `2026-04-27 15:28:17`

## 측정 항목

- fast(1차 summary)까지 시간: `POST /api/review/analyze_fast`
- deep(정밀 조항결과)까지 추가 시간: `POST /api/review/analyze_deep`
- docx 준비(다운로드 응답)까지 추가 시간: `POST /api/revision/download_docx`
- 개선 전(순차) 총 소요: `/api/review/analyze` → `/api/revision/suggest_text` → `/api/draft/suggest`

## 결과 요약

| 케이스 | fast avg/max | deep avg/max | docx avg/max | baseline total avg/max |
|---|---:|---:|---:|---:|
| 짧은 계약서(NDA) | 0.04s / 0.08s | 0.02s / 0.02s | 0.02s / 0.03s | 0.04s / 0.04s |
| 중간 길이(services) | 0.00s / 0.01s | 0.02s / 0.02s | 0.02s / 0.03s | 0.04s / 0.04s |
| 긴 계약서(app-dev) | 0.01s / 0.01s | 12.31s / 24.61s | 0.03s / 0.03s | 27.43s / 31.14s |

## 병목 단계(관찰)

- deep 단계가 가장 큰 비중을 차지하는 경우가 대부분이며, 법령검색/AI 호출의 영향을 크게 받는다.
- fast는 AI/Law를 제외하고 규칙 기반 screening 중심이라 비교적 안정적으로 짧다.

