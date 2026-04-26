# 123. Shallow Review 원인 분석 (Root Cause)

## 결론
- “결과가 너무 단순(고위험 → 법무검토 필요)”하게만 보였던 1차 원인은 **/demo(채팅형)에서 업로드 파일 기반인 경우 계약서 본문(text)을 일부러 비워서 /api/review/analyze 로 보내는 버그**였습니다.
- 2차 원인은 파이프라인이 **문서 전체 keyword 매칭 중심**이라, “조항별 이슈/수정문안/근거”까지 연결되는 출력 구조가 기본값으로는 충분히 노출되지 않았던 점입니다.
- 3차 원인은 “업로드 세션” 경로(`/api/question_sessions/{id}/review`)가 기존에는 `service.analyze()`만 수행해 **조항 분해/조항별 결과(clause_results)** 를 포함하지 않았던 점입니다.

## 증상 ↔ 직접 원인 매핑
### 1) /demo 결과가 요약문처럼 보임 / 계약서 본문을 안 읽는 것 같음
- 원인: 채팅형 데모 UI가 업로드 기반일 때 `text=''` 를 강제해서 `/api/review/analyze` 호출
- 위치: [internal_demo_chat_ui.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py) (기존 `finishAndAnalyze()` 로직)
- 결과: 서버는 `/api/review/analyze`에서 `body.text`만 쓰기 때문에([server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py)), 업로드로 추출된 계약서 본문이 분석에 들어가지 못함

### 2) “고위험”만 뜨고 조항별 구체성이 부족
- 원인(기능적): `service.analyze()`는 문서 전체 텍스트에서 트리거 키워드가 있는 룰을 찾는 구조라([query_service.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/services/query_service.py)), 기본 출력이 `matched_rules` 중심으로 끝나기 쉬움
- 원인(UI): /demo 결과 화면이 `matched_rules`를 단순 나열하고 결론 문구를 고정형으로 만드는 구조라([internal_demo_chat_ui.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)), “조항별 수정문안”이 보조 정보로만 표시됨

### 3) 업로드 흐름에서도 조항별 결과가 부족
- 원인: `/api/question_sessions/{id}/review` 는 세션에 저장된 `text`를 사용하긴 했지만, 기존에는 `service.analyze()`만 실행해서 조항별 결과가 응답에 포함되지 않았음
- 위치: [storage.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/questions/storage.py) `run_review_with_session()`

## 실제 입력 소스 현황(기존)
- 업로드(/upload): `/api/upload` → `extract_text_from_file()`로 텍스트 추출 후 세션에 저장([server.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/api/server.py), [text_extract.py](file:///g:/%EB%8B%A4%EB%A5%B8%20%EC%BB%B4%ED%93%A8%ED%84%B0/%EB%82%B4%20%EB%85%B8%ED%8A%B8%EB%B6%81%20(2)/Desktop/aouribot/aouri-bot/runtime/review/text_extract.py))
- /demo-v1(textarea): textarea 텍스트가 `/api/review/analyze`로 직접 전달
- /demo(채팅형): 업로드를 해도 **세션 text를 쓰지 않고** `/api/review/analyze`를 직접 호출하면서 text를 비워서 전달(버그)

## 개선 방향(요약)
- /demo 업로드 경로를 “세션 기반”으로 통일: `/api/question_sessions/{id}/answers` → `/api/question_sessions/{id}/review` → `/api/revision/suggest(session_id)`로 변경
- 조항 분해 + 조항별 결과 구조를 엔진 레벨에서 생성: `clause_results`(원문/이슈/룰/법령/이유/수정문안/승인필요)
- 최종 산출물: 조항별 수정안을 모아 `.docx` 다운로드까지 제공
