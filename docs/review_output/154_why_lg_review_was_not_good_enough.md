# 154) LG 계약 검토 결과가 충분히 똑똑하지 못했던 원인 보고서

이번 LG(장비구매/설치/시운전) 유형에서 “당사 보호 관점”이 약해 보였던 이유를, 엔진 레이어별로 정리합니다.

---

## 1) party orientation 실패

원인:
- 기존 posture 판별이 `contract_type` 키워드 위주로 단순했고, “우리가 구매자/발주자/설치 수요자”인지 구조적으로 저장되지 않았습니다.

개선:
- `party_role` 추론(구매자/발주자/설치 수요자) + `review_posture`를 meta로 명시적으로 보존
- buyer_favorable 기본값 강화(구매+설치/시운전 계약)

관련 코드:
- [party_role.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/party_role.py)
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)

---

## 2) clause identity mismatch

원인 후보:
- 조항번호가 반복되는 문서(별첨/부칙)에서 clause_id 충돌 가능
- 조항 추출/정규화가 불안정하면 “조항-수정문” 매핑이 흔들릴 수 있음

개선:
- clause_id 중복 시 자동 disambiguate(`.D2` 등)
- clause_title mismatch 발견 시 출력 전에 block 처리
- `article_number`를 별도 필드로 보존해 docx 출력에서도 조항번호 중심으로 표시

관련 코드:
- [clause_extraction.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_extraction.py)
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
- [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

---

## 3) law grounding mismatch

원인:
- clause 단위 검색에도 “법인 우선순위 토픽”이나 일반 키워드가 섞이면,
  - purchase/install 계약에서 대리점법 같은 무관 토픽이 끼어들 수 있음

개선:
- `purchase_installation` 계약 프로파일 도입
- 해당 프로파일에서 `민법/상법/산안법/중대재해/제조물책임` 중심으로 기본 쿼리 구성
- clause scope에서 판례(prec)를 기본 비활성 + 노이즈 타이틀 필터링 + overlap 점수 기반 rerank

관련 코드:
- [search_service.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/law/search_service.py)

---

## 4) rewrite genericity

원인:
- rule_id 기반 템플릿이 “상호주의/공정성” 기준으로 작성되어, buyer 관점의 리스크 감소가 약함
- 패턴 미매칭 시 generic fallback_text로 떨어져 조항 맞춤성이 약해짐

개선:
- buyer_favorable일 때 책임상한/면책/비용전가 템플릿을 “당사 보호” 중심으로 분기
- 패턴이 약해도 최소 변경으로 clause-specific rewrite를 생성하도록 보장
- 안전(설치/현장) 영역은 “이미 충분히 유리한 조항이면 수정하지 않음”을 추가

관련 코드:
- [rewrite_engine.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/rewrite_engine.py)

---

## 5) redline granularity 실패

원인:
- diff 토큰화가 거칠면 replace 블록이 커져 “문단 전체가 빨갛게” 보일 수 있음

개선:
- token/구두점/공백 단위로 토큰화하여 diff granularity 개선
- insert=빨강, delete=빨강+취소선, equal=기본색 유지로 정책 명확화

관련 코드:
- [docx_writer.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/docx_writer.py)

---

## 6) docx readability 문제

원인:
- 조항번호/제목이 흔들리면 문서가 “무엇이 왜 바뀌었는지” 이해하기 어려움
- 변경 표시가 과도하면 검토 피로도가 증가

개선:
- `article_number` 출력 반영(조항번호 중심)
- redline 세분화로 변경 지점만 강조
- 부록 표에 “수정 사유/관련 법령”을 별도로 정리

