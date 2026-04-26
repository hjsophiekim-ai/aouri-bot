# 124. Clause-Level Review 재설계 계획(Plan)

## 목표(최종)
- “검토 결과”가 아니라 **실제 수정본 Word(.docx) 생성**까지 자동화
- 계약서 전체가 아니라 **조항별**로 이슈/근거/수정문안을 생성하고, 결과 화면에서 미리보기/다운로드 제공

## 현재 파이프라인 기준 우선순위
1) 입력 소스 단일화(첨부 본문이 항상 분석 입력이 되도록)
2) clause extraction 안정화(한글/영문/문단형)
3) clause-level 결과 구조 고정(조항별 원문/이슈/룰/법령/이유/수정문안)
4) law_search를 clause별로 연결(근거 링크/제목 포함)
5) OpenAI를 clause rewrite 엔진으로 제한적 활용(근거 기반/JSON 출력)
6) 최종 산출물(.docx) 생성 및 다운로드

## 단계별 작업 항목
### A. 입력 소스 단일화
- /demo 업로드 경로를 세션 기반으로 전환
- 업로드 응답에 추출 텍스트 존재를 검증할 수 있는 `text_sha256`, `preview` 제공(전체 텍스트 노출 최소화)

### B. Clause Extraction
- `제n조`, `Article n`, `1.`, `2)` 등 헤딩 패턴 최대한 인식
- 패턴 미검출 시 문단 분리 + 과긴 문단 분할로 fallback

### C. Clause-Level Review Engine
- 조항별 결과(`clause_results`)를 표준 구조로 반환
- 업로드 세션 리뷰도 동일 구조를 포함하도록 통일
- DB에 clause 결과 저장(검색/이력/다운로드 재생성 기반)

### D. Law Grounding
- clause별로 검색 토픽을 구성하고 결과를 `related_laws`로 매핑
- 비용/지연을 고려해 “이슈 조항 상위 N개”만 검색

### E. AI Rewrite
- “판정은 rule+law, 문안은 AI”로 역할 분리
- 모델 출력은 JSON으로 강제(파싱 실패 시 fallback 유지)

### F. Word(.docx) 산출물
- 조항별 “원문/수정문/이유/근거”를 문서에 기록
- 현재는 표 형태의 정리 문서로 제공(초기 버전)
- 향후 고도화: 실제 redline(w:ins/w:del) 적용, 변경 하이라이트, 원문 대비 diff 표시

## 완료 기준(Definition of Done)
- 업로드 계약서의 본문이 review 입력으로 사용됨이 `preview/text_sha256`로 검증 가능
- `clause_results`가 조항 단위로 생성되고, `suggested_rewrite`가 비어 있지 않음(이슈 조항 기준)
- `/api/revision/download_docx`로 수정본 문서 다운로드 가능
