# 25. EP 화면 내 “계약서 초안 작성” 탭(MVP)

## 1) 목표
- EP 화면 안 아우리봇 패널에 “계약서 초안 작성” 탭을 제공한다.
- MVP 기능:
  - 표준계약서 유형(템플릿) 선택
  - 법인 선택
  - 계약유형 선택
  - 기본 당사자 정보 입력
  - 표준계약서 템플릿 기반으로 간단한 초안 생성
  - 결과를 텍스트로 표시
- 원칙:
  - `docs/Standard Contract` 템플릿 재사용
  - LLM 없이 템플릿+룰 조합으로 1차 구현
  - 향후 LLM 초안생성으로 확장 가능하게 구조 분리

## 2) 구현 개요(이 레포 기준)
- 템플릿 스캔/초안 생성 서비스:
  - `aouri-bot/runtime/draft/service.py`
- API:
  - `GET /api/draft/templates`
  - `POST /api/draft/generate`
- UI(EP Mock 화면 탭으로 제공):
  - `aouri-bot/runtime/admin/ep_legal_request_ui.py` 내 “계약서 초안 작성” 탭

## 3) 템플릿 처리 방식(MVP)
- 템플릿 소스: `docs/Standard Contract/*`
- 지원:
  - `.docx`, `.txt`만 지원
- 제외(backlog):
  - `.doc`(legacy) 및 HWP/PDF 템플릿은 MVP에서 제외

## 4) 초안 생성 결과(MVP)
- 출력:
  - `draft_text`: 선택 템플릿의 텍스트 + 입력 메타(당사/상대방/목적 등) 헤더
  - `suggestions`: rule_id 기반 간단 수정 제안 목록(예: 책임상한/기술자료 제한 등)

## 5) 향후 확장 포인트
- DOCX placeholder 치환(서식 유지)
- LLM 기반 조항 자동 수정/대체안 생성(옵션 기능으로 분리)
- EP 신청 정보(상대방/목적/금액/기간)를 템플릿 본문에 자동 반영(정교화)

