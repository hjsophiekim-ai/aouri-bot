# 153. LG Purchase/Installation Revalidation

## 실행 환경
- LAW_API_ENABLED: True
- LAW_API_KEY_present: True
- base_url: https://www.law.go.kr/DRF

## 케이스: lg_fixture
- filename: lg_purchase_installation.txt
- extraction.success: True
- extraction.text_length: 420
- questions.count: 3
  - Q-CA-002-liability-cap: 손해배상/책임 조항에 책임 상한(캡)과 간접손해 제외가 필요해 보입니다. 당사 기준 상한을 무엇으로 둘까요?
  - Q-CA-003-indemnity-procedure: 면책/배상(특히 제3자 청구) 조항에 통지·방어권·승인 절차와 범위/한도를 명시할 필요가 있나요?
  - Q-CA-999-template-owner: 상대방 양식인지, 당사 양식인지 확인
- review_posture: buyer_favorable
- clause_results.count: 3
- docx_allowed: True
- warnings: []
- download.content_type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- download.bytes: 2720
- docx.text_contains_word_xml_string: False

## 실파일(LG 계약서) 적용 방법
- `runtime/tests/fixtures/lg_purchase_installation_real.docx`로 저장 후 이 스크립트를 재실행하면 동일 검증을 수행한다.
