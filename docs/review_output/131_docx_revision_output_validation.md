# 131. DOCX 수정본 출력 검증

## 검증 항목
- /api/upload → 추출 텍스트 존재
- /api/revision/suggest(session_id) → clause_results/meta(docx_allowed) 반환
- /api/revision/download_docx(session_id) → docx(zip) 바이너리 반환

## 물품공급/구매
- upload status: 200
- extraction.text_length: 258
- extraction.text_sha256(12): edf2b1f7714e
- extraction.preview(160):

```
물품공급계약서

제1조(목적) 본 계약은 당사(갑)가 공급하고 상대방(을)이 구매하는 물품의 공급조건을 정함을 목적으로 한다.
제2조(대금지급) 을은 납품일로부터 60일 이내에 대금을 지급한다. 지연 시 연 24%의 지연손해금을 지급한다.
제3조(검수) 을은 납품 후 3일 내 검수하며,
```
- revision/suggest status: 200
- clause_results: 1
- meta.docx_allowed: True
- meta.warnings: []
- download_docx status: 200
- docx Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- docx zip signature(PK): True
- docx bytes: 2319

## 용역/자문
- upload status: 200
- extraction.text_length: 221
- extraction.text_sha256(12): ea28c7c41f3b
- extraction.preview(160):

```
용역/자문계약서

제1조(용역 범위) 을은 갑에게 자문 용역을 제공한다.
제2조(비용 및 지급) 갑은 을에게 월 정액으로 지급한다. 갑은 지급을 임의로 유보할 수 있다.
제3조(비밀유지) 을은 계약 및 업무상 비밀을 준수한다.
제4조(지식재산권) 을이 수행 과정에서 산출한 결과물의 지식
```
- revision/suggest status: 200
- clause_results: 0
- meta.docx_allowed: True
- meta.warnings: ['contract_text_too_short_warning']
- download_docx status: 200
- docx Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- docx zip signature(PK): True
- docx bytes: 1768

## 대리점/유통
- upload status: 200
- extraction.text_length: 181
- extraction.text_sha256(12): 1c3b44abb1fa
- extraction.preview(160):

```
제10조(손해배상) 당사는 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제11조(면책) 상대방은 어떠한 경우에도 책임을 부담하지 아니한다.
제12조(기술자료) 당사는 상대방 요청 시 기술자료/원가자료/도면/소스코드를 제출한다.
제13조(해지) 상대방은 
```
- revision/suggest status: 200
- clause_results: 3
- meta.docx_allowed: True
- meta.warnings: ['contract_text_too_short_warning']
- download_docx status: 200
- docx Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- docx zip signature(PK): True
- docx bytes: 2754

## 개인정보/DPA
- upload status: 200
- extraction.text_length: 506
- extraction.text_sha256(12): cec25682add8
- extraction.preview(160):

```
개인정보 처리위탁 계약(DPA)

Article 1 (Purpose) This Agreement governs the processing of personal information by Processor on behalf of Controller.
Article 2 (Security) 
```
- revision/suggest status: 200
- clause_results: 2
- meta.docx_allowed: True
- meta.warnings: []
- download_docx status: 200
- docx Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- docx zip signature(PK): True
- docx bytes: 2822

## 광고/모델계약
- upload status: 200
- extraction.text_length: 221
- extraction.text_sha256(12): f07b373dd05b
- extraction.preview(160):

```
광고/모델계약서

제1조(목적) 모델(을)은 광고 촬영 및 홍보 활동에 협조한다.
제2조(초상권 사용) 갑은 을의 초상/성명/음성을 기간 제한 없이, 지역 제한 없이 사용할 수 있다.
제3조(비방 금지) 을은 계약 기간 및 종료 후에도 갑에 대해 일체의 비판을 할 수 없다.
제4조(위약
```
- revision/suggest status: 200
- clause_results: 0
- meta.docx_allowed: True
- meta.warnings: ['contract_text_too_short_warning']
- download_docx status: 200
- docx Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
- docx zip signature(PK): True
- docx bytes: 1769

