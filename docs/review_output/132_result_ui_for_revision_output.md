# 132. 결과 UI를 “수정본 중심”으로 개편

## 목표
- “generic risk 안내” 중심 결과 화면에서 벗어나, 조항별 수정안과 최종 docx 다운로드가 중심이 되도록 변경

## 적용 범위
- /demo(채팅형) 결과 화면(UI) 개편
- 파일: [internal_demo_chat_ui.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

## 최종 결과 화면 포함 항목(반영)
1) 대표 결론  
- 기존처럼 “high risk → 법무검토” 단문으로 끝나지 않게, 조항별 수정안을 기본 액션으로 안내

2) 조항별 수정 제안 리스트  
- `revisionResult.clause_results[]` 기반으로 카드 리스트 렌더링
- 각 카드: 조항명/원문 일부/추천 수정문안 일부

3) 조항별 수정 이유  
- 카드 하단에 `rewrite_reason`를 표시

4) 관련 법령/판례 요약  
- `related_laws.results`에서 대표 제목을 추출해 카드 하단에 요약 표시

5) 최종 수정본 다운로드 버튼  
- 버튼: “최종 수정본 다운로드(.docx)”
- 동작: `POST /api/revision/download_docx` 후 브라우저 다운로드 트리거

6) 수정본 생성 완료 상태  
- `docxStatus` 텍스트로 표시
- 생성 불가(docx_allowed=false)인 경우 버튼 비활성화 + 상태 문구 표시

7) 필요 시 초안 작성 버튼  
- 기존 템플릿 기반 초안 작성 버튼 유지

## 연동 API
- 업로드 기반: `/api/upload` → session_id 획득 → `/api/question_sessions/{id}/review` → `/api/revision/suggest(session_id)`
- docx 다운로드: `POST /api/revision/download_docx` with `{ "session_id": "..." }`

## 주의
- UI는 요약/설명문을 “원문 텍스트”로 취급하지 않도록, 업로드 기반일 때는 세션 텍스트를 사용하도록 구성했습니다.
