# /demo 질문 UX: 단일 질문 플로우(1개씩)

## 목표
- 질문은 한 번에 1개만 표시
- 사용자는 답변도 1개만 입력
- 답변 제출 후 다음 질문으로 이동
- 진행도 표시: `1/4`, `2/4` …
- 마지막 질문 후 자동으로 결과 화면으로 이동

## 구현 방식(MVP)
- `/demo` 화면은 질문 목록을 “한 번에 렌더링”하지 않고,
  `questions[]` 배열 + `qIndex`(현재 질문 인덱스)로 **step state**를 관리한다.
- 답변은 `answers`(dict)로 누적 저장하고, 최종 분석 요청 시 `answers`를 그대로 전달한다.

## 상태(State) 구성
- `questions: []` : 질문 리스트(서버 생성 결과)
- `qIndex: number` : 현재 질문 위치(0-based)
- `answers: { [question_id]: string }` : 이전 답변 저장소
- `progressBadge` : `1/4` 형식으로 표시

## 동작 흐름
1) 시작 화면에서 “검토 시작”
2) 질문 화면으로 전환
3) `askCurrentQuestion()`이 질문 1개를 채팅으로 출력
4) 사용자가 답변 입력 후 “다음”
5) `answers[q.question_id] = raw` 저장 → `qIndex += 1`
6) 마지막 질문이면 `finishAndAnalyze()` 자동 실행 → 결과 화면으로 이동

## 관련 코드
- UI/상태관리: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
  - `questions`, `qIndex`, `answers`
  - `askCurrentQuestion()`, `submitAnswer()`, `finishAndAnalyze()`

