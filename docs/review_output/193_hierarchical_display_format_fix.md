# 193) 조항 계층형 표시 포맷(UI/Word/부록/리스크표)

## 목표

- 원계약서의 계층 구조(조/항/호/목)를 결과 화면과 Word 산출물에서 그대로 읽을 수 있게 표시한다.
- `제23조 제1항 제4호 [계약해지]` 같은 한 줄 병렬 표기 대신,
  - `제23조 [계약해지]`
  - `제1항`
  - `제4호`
  형태로 계층을 분리해 가독성을 높인다.

## 변경 사항

### 1) /demo(UI) 조항 카드: 계층 라인 분리 표시

- 표시 라인을 `article_number/paragraph_number/item_number/subitem_number` 기준으로 생성해 렌더링한다.
- 위치: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py#L962-L1010)

### 2) /demo-v1(UI) 조항 카드: 줄바꿈 기반 계층 표시

- 조항 라벨을 여러 줄(`\\n`)로 구성하고, 표시 영역에 `white-space: pre-line`을 적용했다.
- 위치: [internal_demo_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_ui.py#L80-L390)

### 3) Word(.docx): 본문 redline / guidance / 부록 / 리스크표에 계층형 표기 반영

- 조항 표시를 단일 문자열이 아니라 “여러 줄”로 만들고,
  - 본문(redline)과 guidance 섹션에서는 여러 문단으로 출력
  - 부록(표)에서는 셀 내부에 여러 문단으로 출력
  - High risk/Approval 표에서는 `제N조 [제목] / 제M항 / ...` 형태로 통일 출력
- 위치: [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py#L176-L620)

## 기대 효과

- 앱 화면에서 조항 위치가 원계약서 구조 그대로 읽혀 “어디를 고치는지”가 빨라진다.
- Word 산출물에서 조항 위치가 계층으로 분리되어, 법무 검토자가 원문 구조를 따라가며 검토하기 쉬워진다.

