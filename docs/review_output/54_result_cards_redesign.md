# /demo 결과 화면 카드 리디자인

## 목표
- 결과 화면을 “카드형 레이아웃”으로 정리해 한눈에 핵심을 볼 수 있게 개선
- 밝은 블루/하늘색 톤 유지(화이트 + 라이트 블루 테두리/그림자)
- 위험도는 색상으로 구분하되 톤을 깨지 않게(soft background + 강조 텍스트)
- 작은 창/모바일에서도 크게 깨지지 않게(그리드 → 1열 fallback)

## 필수 카드 구성(반영 결과)
우측 “검토 결과” 패널에 아래 카드가 포함된다.

1) 검토 요약 카드
- applicable/matched/checklist 숫자를 KV 형태로 표시

2) high risk / approval required 배지 카드
- HIGH RISK, APPROVAL REQUIRED 상태를 badge로 표시
- 오남용 방지 문구 포함(“최종 판단은 사람이 확인”)

3) detected issues 카드
- matched_rules 상위 12개를 리스트로 표시(title + rule_id + risk_level)
- 이슈가 없으면 안내 문구 표시

4) 질문 답변 요약 카드
- answers key/value를 리스트로 표시
- 답변이 없으면 안내 문구 표시

5) 수정 제안 카드
- 수정 제안 생성 후 요약(meta) 표시
- “열기” 버튼으로 탭 전환 지원

6) 초안 추천 카드
- `/api/draft/suggest` 결과를 요약(meta)로 표시
- “열기” 버튼으로 탭 전환 지원

## 구현 파일
- UI: [internal_demo_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_ui.py)
  - `.cards` + `.mini` 카드 스타일
  - `renderSummary()`에서 카드 내용 업데이트
  - `renderRevision()`/`suggestTemplates()`에서 카드 meta 업데이트

## 디자인 원칙 구현
- 카드: 라이트 블루 테두리 + shadow (`--line`, `--shadow`)
- 배경: radial + 라이트 블루 그라데이션
- 모바일 대응: `@media (max-width: 1100px)`에서 1열 레이아웃으로 전환

