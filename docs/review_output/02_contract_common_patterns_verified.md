# 실제 계약서 공통 패턴(검증본, CONFIRMED/ESTIMATED 분리)

## 전제/원칙

- CONFIRMED: 실제 본문 텍스트 추출 성공 + 품질 기준 통과한 문서만 반영
- ESTIMATED: 파일명 기반 추정(본문 미확인)으로, 패턴/리스크 확정에 사용하지 않음
- FAILED: 본문 추출 실패(분석 제외 또는 ESTIMATED로만 유지)

## CONFIRMED 커버리지

- docs/Contract 전체: 315
- CONFIRMED(분석 포함): 207
- UNCONFIRMED(통계 제외 권장): 61
- FAILED(본문 미확인): 47

## 1) 계약유형 분류(CONFIRMED 기반)

| 계약유형 | CONFIRMED 건수 | 대표 파일 |
|---|---:|---|
| NDA/비밀유지 | 100 | Sample-Employee Handbook-Fursys America LLC_241120 법무팀검토본_수정.docx, 첨부1_Collaboration Agreement_reviewed by Fursys legal team.docx |
| 개인정보/처리위탁(DPA) | 29 | 시공계약서_260724 법무팀검토본_수정.docx, 2026년 (주)일룸-데스커_DESKER MATE 위탁거래 계약서_260226 법무팀검토본_수정.docx |
| 광고/마케팅/협찬 | 16 | ☆ 퍼시스 농심 인테리어 공사계약서 검토(법무팀).docx, ☆ 시디즈 한국e스포츠협회 후원계약서 검토(법무팀)_2차.docx |
| 대리점/위탁/유통 | 14 | 시디즈 매입 상품 판매 약정서_240808 법무팀검토본_수정.docx, ☆ 시디즈 히히웍스 콘텐츠 제작 용역계약서 검토(법무팀).docx |
| 물품공급/구매/매매 | 13 | FURSYS-PORTOROCHA SOW_reviewed by Kim.docx, OMPSRL_FURSYS - Sales Contract - Final review version - 251113 법무팀검토본_수정본.docx |
| 임대차/전대차 | 13 | Template Standard Lease Agreement_reviewed by legal team.docx, 임대차계약서_법무팀.docx |
| 용역/자문/SOW | 8 | 20250317 Fursys America LLC Engagement Agreement_reviewed by Legal Team.docx, extracted_engagement.txt |
| 공사/도급/하도급 | 6 | ☆ 퍼시스 공간사업부 퍼시스 베트남법인 인테리어공사계약서 검토(법무팀, 영문).docx, ☆ 일룸 아이디스튜디오 프리미엄샵 노원 조명 보수 공사계약서 검토(법무팀).docx |
| 라이선스/로열티 | 3 | ☆ 퍼시스 서울예술대학교 공사도급계약서 검토(법무팀).docx, Termination Notice of License and Settlement Agreement_initial draft.docx |
| 공문/의견/확인 | 2 | ☆ 시디즈 가구 포장용기(종이 박스) 표기사항 관련 의견(법무팀).docx, 감정보완에 대한 의견1.docx |
| 합의/정산/해지 | 2 | 2. 탄소배출권 사업 서약서_이케아바로스_20240717_수정.docx, ☆ 시디즈 페이레터 통합결제서비스 이용계약서 검토(법무팀).docx |
| 근로/고용 | 1 | Sample-Information for Employee handbook-Fursys America LLC_법무팀검토본_최종.docx |

## 2) 반복 조항 토픽(CONFIRMED 기반, 파일 기준 빈도)

| 토픽 | 빈도 | 수준 | 대표 문구 예시 | 근거 파일(예시) |
|---|---:|---|---|---|
| 대금/지급/정산 | 185/207 | HIGH | er project expenses such as payments for observations) (collectively, “Compensation”). Services are provided on a fixed fee plus expenses basis unless another arrangement is set fo… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx |
| 목적/범위 | 183/207 | HIGH | ated expenses for such services. Effective Date: ________________, 2024 ENGAGEMENT; STANDARD OF SERVICE 1.1 Engagement; Scope of Services. Client hereby engages IDEO, and IDEO agre… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx |
| 기간/갱신 | 182/207 | HIGH | VISED TO CONSULT WITH LEGAL COUNSEL REGARDING THE TERMS OF THIS AGREEMENT AND THAT CLIENT HAD THE OPPORTUNITY TO DO SO. TERM AND TERMINATION 8.1 Term. This Agreement shall commence… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx |
| 해지/종료 | 182/207 | HIGH | AND TERMINATION 8.1 Term. This Agreement shall commence on the Effective Date and remain in full force and effect until terminated as provided herein. 8.2 Termination. This Agreeme… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx |
| 당사자/정의 | 174/207 | HIGH | er for each party to access, use and track the other party’s proprietary information, the parties agree as follows: 3.2 Definition. “Confidential Information” as used in this Agree… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx |
| 준거법/관할/분쟁 | 163/207 | HIGH | 니다. 향후 상표 사용 금지: 향후 어떠한 방식으로든 CAPTURE 및 TRENDWAY 상표 또는 이와 혼동될 수 있는 유사 상표를 사용하지 않을 것을 서면으로 약속드립니다. Fursys는 귀하와의 이 문제를 법적 분쟁 없이 우호적으로 해결하기를 원하며, 귀사의 지적 재산권을 존중하고 보호하는 데 최선을 다할 것입니다. … | (20240618) Trendway Corp 대응 letter_법무팀.docx, (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx |
| 손해배상/면책/배상 | 154/207 | HIGH | epurpose the Observation Materials or use them beyond Client’s own internal evaluation of the Deliverables. Client will indemnify IDEO, its employees, directors, contractors, and a… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx |
| 비밀유지 | 135/207 | HIGH | verify any tax credit, set off, rebate or refund in respect of Taxes paid or payable in connection with this Agreement. CONFIDENTIALITY 3.1 General. It is anticipated that the part… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx |
| 양도/하도급/재위탁 | 125/207 | HIGH | rights and rights in any inventions described or embodied in the Deliverables. IDEO agrees to make a full, irrevocable assignment to Client of all such rights upon IDEO’s receipt o… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx |
| 지재권/IP | 114/207 | HIGH | e this matter very seriously and aim to address it promptly. Firstly, we deeply respect Trendway Corp.’s trademarks and intellectual property rights. We are committed to resolving … | (20240618) Trendway Corp 대응 letter_법무팀.docx, (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx |
| 품질/검수/하자 | 106/207 | HIGH | ce and information. Nothing herein shall restrict Client’s right to participate in any such defense at its own expense. WARRANTY DISCLAIMER; LIMITATION OF LIABILITY EXCEPT AS MAY B… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx |
| 불가항력 | 87/207 | HIGH | Information; or (ii) to restrict IDEO from reassigning or otherwise deploying its personnel in its sole discretion. 9.5 Force Majeure. Except for payment of amounts due hereunder, … | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx, ☆ 시디즈 금형 컨설팅 계약서(법무팀).docx |
| 개인정보 | 61/207 | MEDIUM | rves third parties who consent to restricted and confidential use of their information by IDEO. In order to protect the privacy and publicity rights of such third party observation… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 민음사 콘텐츠 제작 및 마케팅 용역계약서 검토(법무팀).docx, ☆ 시디즈 베리띵즈 SNS채널 운영 대행계약서 변경안(법무팀)_수정.docx |
| 위약금/지체상금 | 49/207 | MEDIUM | to such Services, the IDEO must adhere to the final deadline. Failure to do so may result in the IDEO being liable for liquidated damages. 1.3 Reliance on Client Instructions and I… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx, ☆ 시디즈 금형 컨설팅 계약서(법무팀).docx |
| 안전/산안법/중대재해 | 49/207 | MEDIUM | 용품 사용으로 발생할 수 있는 잠재적 위해사항 명시 * 제품 또는 포장에 표시 가능 ■ 가죽제품, 가구(762mm 이상의 가정용 서랍정 및 사무용 파일링 캐비닛은 제외), 침대 매트리스, 합성수지제품 ◎ 전기생활용품안전법상 각 제품별 표시사항 표시 예) 품명, 외형치수, 구조부재, 표면가공, 제조연월, 제조자명, 수입자명… | ☆ 시디즈 가구 포장용기(종이 박스) 표기사항 관련 의견(법무팀).docx, ☆ 시디즈 베리띵즈 행사 대행 계약서 검토(법무팀).docx, ☆ 시디즈 비에스온 렌탈서비스계약서 검토(법무팀).docx |
| 독점/경업 | 46/207 | MEDIUM | ranteed. If IDEO fails to perform the Services in accordance with the Standard of Service or the SOW, Client’s sole and exclusive remedy is to require IDEO to re-perform such Servi… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 와이븐 방송 프로그램 협찬 계약서 검토(법무팀).docx, ☆ 시디즈 케이에스브이이스포츠코리아(젠지) 제품후원계약서(법무팀).docx |
| 기술자료/자료요구 | 40/207 | MEDIUM | 법률’ 위반의 문제가 발생한다는 점에 대해 계약 당사자는 충분히 인지한다. ⑤ 상기의 “비밀정보”의 공개와 사용에 대한 제한은 “정보수령자”가 “정보제공자”의 재화와 용역과 경쟁적 관계에 있는 자신의 재화와 용역을 설계, 개발, 획득, 서비스 및 다른 방법으로 다루는 권리를 제한하는 것은 아니다. 제 5 조 (권리) 제공… | ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx, ☆ 시디즈 금형 컨설팅 계약서(법무팀).docx |
| 책임제한/한도 | 37/207 | MEDIUM | othing herein shall restrict Client’s right to participate in any such defense at its own expense. WARRANTY DISCLAIMER; LIMITATION OF LIABILITY EXCEPT AS MAY BE EXPRESSLY SET FORTH… | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx, ☆ 시디즈 베리띵즈 SNS채널 운영 대행계약서 변경안(법무팀)_수정.docx |

## 3) 표준계약서에는 없지만 반복적으로 등장한 토픽(추출 기반 비교)

- 비교 기준: docs/review_output/01_standard_contract_summary.md(동일 추출 로직으로 재생성)

| 항목(패턴) | 빈도 | 수준 | 대표 문구 예시 | 근거 파일(예시) |
|---|---:|---|---|---|
| (없음) | 0/207 | - | 표준계약서(현재 폴더 구성)에서도 동일/유사 패턴이 발견되어 '표준에 없음'으로 확정 불가 | - |

## 4) 자주 협상/수정 흔적 문구(CONFIRMED 기반)

| 패턴 | 빈도 | 수준 | 근거 파일(예시) |
|---|---:|---|---|
| 상호협의/별도협의 | 128/207 | HIGH | ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx, ☆ 시디즈 금형 컨설팅 계약서(법무팀).docx, ☆ 시디즈 대한항공 물품공급계약서 검토(법무팀).docx |
| 사전 서면동의 | 90/207 | HIGH | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 LCA 컨설팅 용역 계약(켐토피아) 및 비밀유지계약(한국에스지에스, 켐토피아) 검토안(법무팀).docx, ☆ 시디즈 LG전자 사상자동화 검증 용역계약서 검토(법무팀).docx, ☆ 시디즈 금형 컨설팅 계약서(법무팀).docx, ☆ 시디즈 대상웰라이프 물품교환계약서 검토(법무팀).docx |
| 요청 시/요구 시 | 20/207 | LOW | ☆ 일룸 LG전자 상품 위수탁거래계약서 검토(법무팀).docx, ☆ 일룸 그래비티벤처스 투자계약서 검토(법무팀).docx, ☆ 일룸 스타필드 고양 대리점 영업지원금 합의서 검토(법무팀).docx, ☆ 일룸 슬로우 안테나 이효리 모델 계약서 검토(법무팀)_수정.docx, ☆ 일룸 슬로우베드 전주현(개인) 인플루언서 마케팅 계약서 검토(법무팀).docx |
| 불리한 일방표현(갑 중심) | 13/207 | LOW | ☆ 시디즈 동일인테리어 물품공급계약서 검토(법무팀).docx, ☆ 시디즈 베리띵즈 SNS채널 운영 대행계약서 변경안(법무팀)_수정.docx, ☆ 시디즈 서울프라퍼티인사이트 콘텐츠 제작 용역계약서 검토(법무팀).docx, ☆ 시디즈 스튜디오X 컨텐츠 제작 용역계약서 검토(법무팀).docx, ☆ 시디즈 코엑스 부스 및 조형물 제작, 설치 계약서 검토(법무팀).docx |
| 추후 정함/추후 협의 | 6/207 | LOW | ☆ 시디즈 케이에스브이이스포츠코리아(젠지) 제품후원계약서(법무팀).docx, ☆ 시디즈 큰그림컴퍼니 광고계약서 검토(법무팀).docx, ☆ 퍼시스 에스오일 사무환경컨설팅 용역계약서 검토(법무팀).docx, ☆ 홀딩스 피닉스랩 비밀유지계약서(법무팀).docx, ★ 시디즈 크래프톤 스폰서쉽(제품 협찬) 계약서 검토(법무팀).docx |

## 5) 고위험 조항 후보(CONFIRMED 기반)

- 아래 항목은 규칙 기반 키워드 탐지 결과이며, 실제 의미(상호/일방, 한도 유무 등)는 원문 맥락 검토가 필요함

| 고위험 항목 | CONFIRMED 탐지 파일 수 | 파일명(예시) | 대표 문구 예시 |
|---|---:|---|---|
| 안전책임 공백(후보: 안전 조항 부재) | 36 | (20240618) Trendway Corp 대응 letter_법무팀.docx, ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 시디즈 코엑스 부스 및 조형물 제작, 설치 계약서 검토(법무팀).docx | - |
| 일방 면책/일방 배상(후보) | 20 | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 시디즈 베리띵즈 행사 대행 계약서 검토(법무팀).docx, ☆ 시디즈아메리카 ODK 마케팅 등 제휴 계약서 검토(법무팀)_수정.docx | aterials and Client may not in any way repurpose the Observation Materials or use them beyond Client’s own internal evaluation of the Deliverables. Client will indemnify IDEO, its … |
| 무제한 책임(또는 사실상 무한대) | 10 | (MSA) IDEO Services Agreement v2024_reviewed by legal dep..docx, ☆ 일룸 데스커 공급계약서 검토(법무팀)_수정.docx, 20250318 Cooperation Agreement APAC Fursys_250401.docx | WHICH ARE EXPRESSLY DISCLAIMED. IN NO EVENT SHALL EITHER PARTY BE LIABLE FOR ANY INCIDENTAL, CONSEQUENTIAL, SPECIAL, OR INDIRECT DAMAGES OF ANY KIND, INCLUDING WITHOUT LIMITATION T… |
| 대리점 비용전가 | 8 | ☆ 26년 일룸 위탁대리점계약서 검토(법무팀) _수정.docx, ☆ 일룸 입점대리점 매장운영합의서 검토(법무팀).docx, ☆ 일룸 평택대리점 인테리어 원상회복 합의서 검토(법무팀).docx | ﻿일룸 26년 위탁판매 대리점 계약서 검토 * 대리점 계약서 본문 ■ 귀 팀 요청에 따라 원상회복과 관련하여 아래 조항 신설하였습니다. 적절히 활용해 주시기 바랍니다. 제16조 [원상회복 등] 대리점은 계약이 종료되거나 해지되는 경우, 계약기간 중 대리점이 설치, 변경한 범위 내에서 공급업자의 요구에 따라 매장 |
| 기술자료 요구 | 5 | ☆ 일룸 LG전자 상품 위수탁거래계약서 검토(법무팀).docx, ☆ 일룸 그래비티벤처스 투자계약서 검토(법무팀).docx, ☆ 퍼시스 에스오일 사무환경컨설팅 용역계약서 검토(법무팀).docx | 사’는 파트너사에게 판매 중단의 이유와 기간 등 구체적인 사항을 사전 통지하고 해당 상품의 판매를 중단할 수 있다. ① 지식재산권 침해 등의 경고, 클레임 등이 제3자에 의해 접수된 경우 ② 관련 법령 등의 위반으로 정부기관 등(경찰, 검찰 등 수사기관 및 소비자 단체 포함)의 조사, 자료제출 등 요청이 발생한 경우 ③ … |
| 하도급 단가감액 | 1 | ☆ 표준하도급계약서 배포안(240701)_수정.docx | ﻿하도급 계약서 ■ 계약명 : ■ 계약기간 : [ ]년 [ ]월 [ ]일부터 [ ]년 [ ]월 [ ]일까지 ■ 계약금액 : 별첨 단가합의서 및 개별 발주서의 내용에 따름 ■ 납품(완성)일자 및 장소 : 별첨 개별 발주서의 내용에 따름 ■ 하도급대금 연동제 적용 여부 ◇ 연동제 적용대상 없음 ( |

## 6) 법인별로 다르게 적용될 가능성이 있는 토픽(편중 징후)

- 기준: 특정 법인 그룹에서 토픽 출현 비중이 상대적으로 높은 경우(탐지 기반)

| 법인 그룹 | 편중 토픽(상위 5) |
|---|---|
| 퍼시스 | 대금/지급/정산(89), 해지/종료(87), 목적/범위(82), 기간/갱신(82), 당사자/정의(79) |
| 일룸/데스커 | 목적/범위(84), 기간/갱신(83), 대금/지급/정산(81), 해지/종료(80), 당사자/정의(78) |
| 시디즈 | 당사자/정의(54), 대금/지급/정산(53), 목적/범위(52), 해지/종료(52), 기간/갱신(52) |
| 해외법인(미국/베트남 등) | 대금/지급/정산(18), 해지/종료(16), 준거법/관할/분쟁(15), 목적/범위(15), 기간/갱신(13) |
| 미상 | 기간/갱신(9), 손해배상/면책/배상(9), 해지/종료(9), 당사자/정의(8), 목적/범위(8) |
| 퍼시스홀딩스 | 당사자/정의(9), 기간/갱신(9), 목적/범위(8), 대금/지급/정산(8), 손해배상/면책/배상(7) |

## 7) Rule 후보(초안, CONFIRMED 기반)

| Rule ID | 트리거(키워드/조건) | 설명 | 조치(리뷰 포인트) | 근거(빈도/파일) |
|---|---|---|---|---|
| R-HIGH-001 | 무제한/without limitation/unlimited liability | 책임한도 부재 또는 무제한 책임 후보 | 책임제한/손해범위/간접손해 제외/총액 캡 협상 | 무제한 책임 탐지 결과 참조 |
| R-HIGH-002 | hold harmless/indemnify/면책/일체 책임 없음 | 일방 면책/일방 배상 후보 | 상호성·범위·절차(방어/통지)·보험 연계 확인 | 일방 면책/배상 탐지 결과 참조 |
| R-HIGH-003 | 기술자료/원가자료/도면/소스코드 | 기술자료 요구 조항 | 제공 범위·목적·비밀유지·반환/폐기·하도급법 이슈 점검 | 기술자료 요구 탐지 결과 참조 |
| R-HIGH-004 | 하도급 + 단가 감액/인하 | 하도급 단가감액 후보 | 감액 사유/절차/서면/소급 여부·하도급법 리스크 확인 | 하도급 단가감액 탐지 결과 참조 |
| R-HIGH-005 | 대리점 + 비용부담/판촉비/반품비/광고비 | 대리점 비용전가 후보 | 공정거래/대리점 정책 일관성·증빙·상한 확인 | 대리점 비용전가 탐지 결과 참조 |

## 8) ESTIMATED(파일명 기반) 섹션

- 아래는 본문 미확인(FAILED/UNCONFIRMED)로, 패턴 확정/고위험 확정에 포함하지 않음

| ESTIMATED 계약유형 | 건수 | 예시 파일 | 상태 구성 |
|---|---:|---|---|
| 기타/미분류 | 42 | (용인물류)_관리형토지신탁계약서(안)_퍼시스검토.docx, (첨부1) [논스] 데스커 라운지 대구 공간 운영 계약서_초안_법무검토요청_법무팀.docx, [계약서] 패스트캠퍼스_퍼시스_ChatGPT 비즈니스 활용 과정_기업교육계약서_법무팀.docx | UNCONFIRMED:16, FAILED:26 |
| 광고/마케팅/협찬 | 13 | [일그램] 2024 퍼시스 그룹_온라인 마케팅 업무(링크드인)_법무팀.docx, ☆ 시디즈 레니프 지식재산권 침해 및 부당한 비교광고 중지 공문 검토(법무팀).docx, ☆ 시디즈 알로소 크리에이팁 마케팅 대행 계약서 검토(법무팀).docx | FAILED:5, UNCONFIRMED:8 |
| 임대차/전대차 | 10 | ☆ 일룸 신세계 파주점 임대차계약 연장 및 원상회복 관련 의견(법무팀).docx, ☆ 일룸 울산점 전대차 동의서 검토(법무팀).docx, ☆ 일룸 태릉목동대리점 전대차물건 원상회복 비용 분담 합의서 검토(법무팀).docx | UNCONFIRMED:8, FAILED:2 |
| 물품공급/구매/매매 | 8 | ☆ 시디즈 CJ대한통운 물품 구매 계약서 검토(법무팀).docx, ☆ 시디즈 에스앤아이코퍼레이션 물품공급계약서 검토(법무팀).docx, ☆ 일룸 파르나스호텔 물품공급계약서 검토(법무팀).docx | UNCONFIRMED:6, FAILED:2 |
| 용역/자문/SOW | 8 | 관리용역 사업 영업양도 및 승계 안내_수정.docx, [K&C] Engagement letter_reviewed by Kim.doc, ☆ 시디즈 소파연구용역계약서 검토(법무팀)_수정.doc | UNCONFIRMED:1, FAILED:7 |
| 대리점/위탁/유통 | 7 | ☆ 일룸 고양대리점 키즈 체험 프로그램 설치 및 운영 합의서 검토(법무팀).docx, ☆ 일룸 대리점 매장 원상회복 의무 부담 건에 대한 의견(법무팀).docx, ☆ 일룸 수원대리점 키즈 체험 프로그램 철거 합의서 검토(법무팀).docx | UNCONFIRMED:6, FAILED:1 |
| 합의/정산/해지 | 6 | ☆ 시디즈 논현점 계약상 지위 양도 양수 합의서 검토(법무팀).docx, ☆ 시디즈 성수점 계약상 지위 양도 양수 합의서 검토(법무팀).docx, ☆ 일룸 퍼시스 맥스골프 3자간 손해배상 합의서 검토(법무팀).docx | UNCONFIRMED:5, FAILED:1 |
| 공문/의견/확인 | 6 | ☆ 시디즈 서울대 지식재산권 사용 관련 회신 공문(법무팀).docx, ☆ 시디즈 한국교직원공제회 S2B학교장터 협조공문 검토(법무팀).docx, ☆ 일룸 대전도안점 개인회생 관련 공문 검토(법무팀).docx | UNCONFIRMED:6 |
| 공사/도급/하도급 | 5 | ☆ 시디즈 하도급거래 종료 합의서 검토(법무팀).docx, ☆ 일룸 LX하우시스 원상복구 공사 합의서 검토(법무팀).docx, ☆ 퍼시스 공간사업부 서울대학교 공과대학 환경개선공사계약서 검토안(법무팀).docx | UNCONFIRMED:3, FAILED:2 |
| 개인정보/처리위탁(DPA) | 1 | ☆ 참고. 개인정보 수집 이용 동의서(법무팀).docx | UNCONFIRMED:1 |
| 라이선스/로열티 | 1 | ★ 일룸 MBC 마코컴퍼니 라이선스 계약서 검토(법무팀).docx | UNCONFIRMED:1 |
| 근로/고용 | 1 | 2. 공간사업부 현장 일용직 근로계약서(After)_240703 법무팀검토본.xlsx | FAILED:1 |

## 9) 아직 본문 확인이 안 되어 3번 프롬프트에 반영하면 안 되는 항목

- 조건: CONFIRMED에서 0건이거나(미탐지), 안전책임 공백처럼 '부재' 판단이 불확실한 항목

| 항목 | 사유 |
|---|---|
| 안전책임 공백(후보: 안전 조항 부재) | 부재 판정은 계약유형/원문 구조에 따라 오탐 가능 |
