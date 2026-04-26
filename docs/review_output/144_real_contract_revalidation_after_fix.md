# 144. Real Contract Revalidation After Fix

## 실행 환경
- LAW_API_ENABLED: True
- LAW_API_KEY_present: True
- base_url: https://www.law.go.kr/DRF

## 검증 결과(업로드→질문→리비전→DOCX)
### 케이스: dealer_fixture
- filename: demo_upload.txt
- extraction.success: True
- extraction.text_length: 181
- extraction.preview: 제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제11조(면책) 상대방은 어떠한 경우에도 책임을 부담하지 아니한다.
제12조(기술자료) 당사는 상대방 요청 시 기술자료/원가자료/도면/소스코드를 제출한다.
제13조(해지) 상대방은 
- questions.count: 3
- Q-CA-002-liability-cap: 손해배상/책임 조항에 책임 상한(캡)과 간접손해 제외가 필요해 보입니다. 당사 기준 상한을 무엇으로 둘까요?
- Q-CA-003-indemnity-procedure: 면책/배상(특히 제3자 청구) 조항에 통지·방어권·승인 절차와 범위/한도를 명시할 필요가 있나요?
- Q-CA-999-template-owner: 상대방 양식인지, 당사 양식인지 확인
- session_id: 3a46a795c7184cce9ee31146fe85d062
- clause_results.count: 3
- meta.docx_allowed: True
- meta.warnings: ['contract_text_too_short_warning']
- rewrite.generic_template_detected: False
- download.content_type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- download.docx_bytes: 2396
- docx.text_contains_word_xml_string: False

### 케이스: privacy_fixture
- filename: dpa_privacy.txt
- extraction.success: True
- extraction.text_length: 506
- extraction.preview: 개인정보 처리위탁 계약(DPA)

Article 1 (Purpose) This Agreement governs the processing of personal information by Processor on behalf of Controller.
Article 2 (Security) 
- questions.count: 3
- Q-CA-002-liability-cap: 손해배상/책임 조항에 책임 상한(캡)과 간접손해 제외가 필요해 보입니다. 당사 기준 상한을 무엇으로 둘까요?
- Q-CA-004-privacy-delegation: 개인정보 처리/위탁 정황이 있는데, 재위탁·보안조치·보관/파기·침해사고 통지 기준이 계약서에 충분히 포함돼 있나요?
- Q-CA-999-template-owner: 상대방 양식인지, 당사 양식인지 확인
- session_id: c13922172dd642cba18a9b49ce37a21c
- clause_results.count: 2
- meta.docx_allowed: True
- meta.warnings: []
- rewrite.generic_template_detected: False
- download.content_type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- download.docx_bytes: 2232
- docx.text_contains_word_xml_string: False

### 케이스: services_fixture
- filename: services_consulting.txt
- extraction.success: True
- extraction.text_length: 221
- extraction.preview: 용역/자문계약서

제1조(용역 범위) 을은 갑에게 자문 용역을 제공한다.
제2조(비용 및 지급) 갑은 을에게 월 정액으로 지급한다. 갑은 지급을 임의로 유보할 수 있다.
제3조(비밀유지) 을은 계약 및 업무상 비밀을 준수한다.
제4조(지식재산권) 을이 수행 과정에서 산출한 결과물의 지식
- questions.count: 3
- Q-CA-999-template-owner: 상대방 양식인지, 당사 양식인지 확인
- Q-CA-998-overseas: 해외법인/해외거래 관련 여부
- Q-CA-997-personal-data: 개인정보 처리(수집/이용/제공/위탁) 여부
- session_id: 8ec9e2815a854117947bd0200579790f
- clause_results.count: 0
- meta.docx_allowed: True
- meta.warnings: ['contract_text_too_short_warning']
- rewrite.generic_template_detected: False
- download.content_type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- download.docx_bytes: 1760
- docx.text_contains_word_xml_string: False

### 케이스: track_changes_docx
- filename: tracked.docx
- extraction.success: True
- extraction.text_length: 65
- extraction.preview: 제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
삽입문현재문
- questions.count: 3
- Q-CA-002-liability-cap: 손해배상/책임 조항에 책임 상한(캡)과 간접손해 제외가 필요해 보입니다. 당사 기준 상한을 무엇으로 둘까요?
- Q-CA-999-template-owner: 상대방 양식인지, 당사 양식인지 확인
- Q-CA-998-overseas: 해외법인/해외거래 관련 여부
- session_id: 1f1caf07c69249d094dd23703becba7f
- clause_results.count: 1
- meta.docx_allowed: False
- meta.warnings: ['contract_text_too_short_warning', 'clause_count_too_low_warning', 'contract_text_too_short_block', 'insufficient_contract_structure_block']
- rewrite.generic_template_detected: False
- download.content_type: application/json; charset=utf-8
- download.docx_bytes: 556
- docx.download_error_preview: {"error": "insufficient contract text for docx generation", "meta": {"text_length": 65, "text_sha256": "00da170ff77471f6bdaf6b600c6c6b006d683117f98167a844c65776c657628a", "clause_count": 1, "issue_cla

## 대상 문서(일룸/데스커 DESKER MATE 위탁거래 계약서)
- 현재 워크스페이스에서 원본 파일을 찾지 못해(파일 미존재) 직접 업로드 기반 재검증은 미실시.
- 재검증 방법: 해당 DOCX를 `aouri-bot/runtime/tests/fixtures/`에 배치 후 위 스크립트에 케이스로 추가하여 동일 절차로 확인.

