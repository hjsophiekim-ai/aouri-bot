# 162. 앱 개발계약서 질문 엔진(clause-aware) 보강

## 목표
- 앱 개발계약서에서 질문이 계약 내용에 맞게 달라지도록 “없는 조항/애매한 조항”만 질문한다.
- 질문 수는 최대 5개 이내로 제한한다.
- 질문마다 reason_code를 보존한다.
- AI는 문구 다듬기(polish) 뿐 아니라, 우선순위 산정(prioritize)에도 사용한다(가능할 때만).

## 변경 내용
### 1) clause-aware “있음/애매/없음” 판정 추가
- 파일: [generator.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/questions/generator.py)
- 구현:
  - 토픽별로 `missing/ambiguous/clear` 상태를 계산한다.
  - “별도 협의/추후 협의/to be agreed/TBD” 등 문구가 토픽 앵커 주변에 있으면 `ambiguous`로 판정한다.
  - 토픽이 `clear`이면 질문을 생성하지 않는다.

### 2) 앱 개발계약 전용 질문 후보 확장(최대 5개로 컷)
- 토픽(질문 후보):
  - 산출물/IP 귀속
  - 오픈소스 사용/라이선스 준수
  - 개발 범위/사양(SOW) 및 변경관리
  - 검수 기준/기간(간주검수/재검수)
  - SLA(장애 대응 시간/가용성)
  - 개인정보 처리/위탁(DPA) 및 통제조항
  - 소스코드 인도(저장소 이전 포함)
  - 유지보수 범위/기간
  - 재위탁(외주/하도급) 승인/책임
  - 보안사고 책임 구조
  - 종료 시 데이터/소스 반환·삭제 및 인수인계/전환
- 점수 기반 후보 정렬 후 상위 5개만 반환한다.

### 3) reason_code 저장
- 각 질문은 `tags`에 `reason_code:*`를 포함한다.
- 예시:
  - `reason_code:missing_ip_ownership_terms`
  - `reason_code:missing_source_code_delivery_terms`
  - `reason_code:missing_acceptance_terms`

### 4) AI 우선순위 산정(prioritize) + 문구 다듬기(polish)
- 파일:
  - AI 우선순위: [enhance.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/ai/enhance.py)
  - API 적용: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)
- 동작:
  - OpenAI가 활성이고, 앱 개발계약 힌트가 있으면:
    1) 후보 질문을 AI로 재정렬(prioritize)
    2) 최종 질문 문구를 AI로 다듬기(polish)
  - AI 비활성 시에는 deterministic 점수 로직만 사용한다.

## 기대 효과
- 앱 개발계약서에서 “이미 적힌 내용”은 되묻지 않고, “없는/애매한 조항” 중심으로 질문이 생성된다.
- 질문이 최대 5개로 유지되면서도, IP/소스코드/검수/SLA/개인정보/전환 등 핵심 포인트를 빠뜨리지 않는다.

