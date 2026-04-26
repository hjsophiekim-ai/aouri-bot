# /demo 블루 톤 UI 테마 적용(아우리봇 브랜딩)

## 목표
- 밝은 블루/하늘색 + 화이트 기반의 “세련된 AI/법률검토 서비스” 톤
- 아우리봇 캐릭터 색감과 일관된 배경/카드/버튼/배지/탭 스타일 통일
- 과도한 애니메이션 없이 카드/그림자 중심의 안정적인 UI

## 반영 내용(요약)
- 브랜딩 헤더(로고/서비스 설명/네비게이션 pill)
- 시작 화면(히어로 카드)에 아우리봇 이미지 + 요구 문구 적용
- 결과 화면(우측 패널) 상단에 아우리봇 배지 + 결과 상태 문구 영역
- 카드형 레이아웃 + 블루 계열 변수 기반 통일

## 구현 파일
- 데모 UI: [internal_demo_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_ui.py)
  - 인라인 CSS로 테마를 정의(`:root` 색상 변수)
  - favicon/apple-touch-icon을 아우리봇 이미지로 지정

## 스타일 구성
### 색상 토큰(:root)
- 배경: `--bg`
- 카드: `--card`
- 라인/테두리: `--line`
- 메인 블루: `--primary`, `--primary2`
- 라이트 블루: `--primarySoft`
- 위험도: `--danger`, `--warn`, `--ok` (톤을 깨지 않도록 soft 배경 + 강조 텍스트)

### 컴포넌트
- 카드: `.card` (라이트 블루 테두리 + 부드러운 그림자)
- 버튼: `.btnPrimary`(그라데이션 블루), `.btnSoft`(라이트 블루), `.btnGhost`(텍스트형)
- 탭: pill 스타일 `.tab` + active 시 라이트 블루 배경
- 배지: `.badge*` 계열(high/approval/ok)

## EP 이식 관점
- 이 UI는 “우측 패널/탭 구조”를 그대로 유지해서 EP 패널 이식에 용이함
- 정적 리소스(`/static`)를 통해 이미지가 깨지지 않도록 서버 측도 함께 준비됨(53 문서 참조)

