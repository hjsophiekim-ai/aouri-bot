# 133. 5개 계약서 조항별 수정 제안 + DOCX 결과물 검증

## 주의
- 저장소에 실제 계약서 원본 파일이 포함되어 있지 않아, 검증은 비식별 샘플 텍스트 fixture 5건으로 수행했습니다.
- 민감정보 노출 방지를 위해 본문은 160자 미리보기만 기록합니다.

## 요약 표
| 문서 | upload | text_len | sha(12) | suggest | clauses | docx_allowed | docx | zip | bytes | time |
|---|---:|---:|---|---:|---:|---:|---:|---|---:|---:|
| 물품공급/구매 | 200 | 258 | edf2b1f7714e | 200 | 1 | True | 200 | OK | 2319 | 0.34s |
| 용역/자문 | 200 | 221 | ea28c7c41f3b | 200 | 0 | True | 200 | OK | 1768 | 0.06s |
| 대리점/유통 | 200 | 181 | 1c3b44abb1fa | 200 | 3 | True | 200 | OK | 2754 | 12.40s |
| 개인정보/DPA | 200 | 506 | cec25682add8 | 200 | 2 | True | 200 | OK | 2822 | 6.81s |
| 광고/모델계약 | 200 | 221 | f07b373dd05b | 200 | 0 | True | 200 | OK | 1769 | 0.13s |

## Guardrail 확인(짧은 요약문만 있는 경우)
- short_summary upload status: 200
- download_docx status: 400 (blocked=True)
- Content-Type: application/json; charset=utf-8
- error: insufficient contract text for docx generation
- meta.warnings: ['contract_text_too_short_warning', 'clause_count_too_low_warning', 'contract_text_too_short_block', 'insufficient_contract_structure_block']

