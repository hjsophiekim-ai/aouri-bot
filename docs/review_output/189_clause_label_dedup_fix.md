# 189) 조항 표시(label) 중복 제거 및 단일 규칙화

## 문제

- 조항 표기가 아래처럼 “제N조 … 제N조 …” 형태로 중복되는 케이스가 확인됨
  - `제23조 제1항 4호 제23조 [계약해지]`
  - `제5조 제2항 제5조 용역업무의 검수 등`
  - `제13조 제1항 4호 제13조 개인정보 보호`
- 원인: `display_path`와 `clause_title`을 출력 지점마다 임의로 결합하면서, `clause_title` 내부에 이미 `제N조…`가 포함된 경우 중복이 발생.

## 목표

- 조항 표시 문자열 생성 규칙을 단일화
- 출력 형식은 아래 중 하나로 통일(현 구현: bracketed)
  - `제23조 제1항 제4호 [계약해지]`
  - `제23조 제1항 제4호 계약해지`
- UI/Word/부록/리스크표 모두 동일 규칙 적용

## 해결 방식

### 1) 공용 포매터 추가

- `runtime/review/clause_label.py`
  - `format_clause_label(display_path, clause_title, style="bracketed"|"plain")`
  - `display_path`가 `제23조 제1항 제4호`이고, `clause_title`이 `제23조 [계약해지]`처럼 시작하면 title에서 prefix를 제거하여 중복 방지
  - title에 이미 대괄호가 있으면 제거 후 단일 bracket 규칙으로 재출력

### 2) DOCX 출력 전체 적용

- `docx_writer.py`에서 헤더/부록/리스크표 등 모든 “조항 표기”를 공용 포매터 기반으로 생성하도록 통일

### 3) /demo UI 적용

- demo 조항 카드 제목에서 `display_path + clause_title` 단순 결합을 제거하고, 중복 제거 규칙으로 title을 구성

## 변경 파일

- [clause_label.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_label.py)
- [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)
- [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)

