# AI 기능 연동 설계 (Rule 기반 MVP 위 확장)

## 목표
- 현재 rule 기반 MVP 구조를 유지하면서, AI API 키만 추가되면 “질문/초안/수정제안/설명 생성”을 단계적으로 붙일 수 있게 한다.
- AI가 실패하거나 비용/보안상 제한될 때에도 시스템이 멈추지 않도록 fallback을 제공한다.

## 1) Rule만으로 처리할 기능(현 유지)
- Rule 기반 검토(`/api/review/analyze`)
  - 적용 rule 목록, approval_required/high_risk 플래그, 체크리스트 제공
- Rule 기반 질문 생성(사전 질문 세트)
- 템플릿 기반 초안 생성(docs/standard contract 기반)
- “수정 제안 뷰”의 기본 구성(조항 분해 + rule 매칭 + fallback_text)

## 2) AI API가 필요한 기능(정확도/설명 품질을 위해)
- 계약서 문맥 기반 Q&A
  - 질문에 대한 답을 계약서에서 근거 문장과 함께 찾아 설명(키워드 매칭보다 정밀)
- 초안 작성 고도화
  - 템플릿이 없는 유형/변형된 유형에서 맞춤 조항 생성
  - 당사 정책에 맞는 문구 스타일링
- 조항 수정 제안 문안 생성
  - rule이 “수정 방향”만 주는 경우 실제 대체 조항(문장)을 생성
  - (추후) redline 생성
- rule 기반 검토 결과 “설명 생성”
  - 왜 이슈인지, 어떤 위험인지, 어떤 수정이 필요한지 자연어 요약(법무 보고서 품질)

## 3) AI adapter 계층 구조(Repo 기준 제안)
새 모듈 경로(권장):
- `aouri-bot/runtime/ai/`
  - `config.py`: provider/model/api_key/timeout/max_tokens/temperature 로딩(ENV/파일)
  - `provider.py`: Provider 인터페이스(Protocol) + 공통 DTO(AIResult/Usage)
  - `mock_provider.py`: 키가 없을 때 동작하는 mock(결정적 출력 + rule 기반 텍스트 조합)
  - `factory.py`: config → provider 인스턴스 생성(키 없으면 mock)
  - `prompts.py` 또는 `prompts/*.txt`: prompt template 정의/관리
  - `service.py`: AouriBot 도메인 작업 단위(설명 생성/수정문안 생성/질문 응답 생성)를 제공

기존 서비스와 결합 지점(예):
- `runtime/services/query_service.py`
  - analyze 결과 생성 후, 요청 옵션에 따라 `ai.service`를 호출해 `explanations`를 추가
- `runtime/review/revision.py`
  - 현재 fallback_text 기반 → (옵션) AI 문안 생성으로 `suggested_rewrite` 추가
- `runtime/questions/*`
  - 질문 생성 자체는 rule 기반 유지
  - 질문에 대한 “계약서 기반 답변”은 AI로 보강(옵션)

## 4) prompt template 구조
프롬프트는 “기능 단위”로 분리한다.

권장 템플릿(최소):
- `explain_issues`:
  - 입력: 계약서 원문(또는 관련 조항), matched_rules, issue 요약, entity/contract_type
  - 출력: 이슈별 설명(근거/리스크/권장 액션)
- `draft_from_intake`:
  - 입력: 계약유형, 당사/상대방/목적/기간/금액, 선택 템플릿, rule 체크리스트
  - 출력: 초안 텍스트(템플릿 기반 + 보완 조항)
- `rewrite_clause`:
  - 입력: 원문 조항, 적용 rule, 수정 방향, 제약(금지 표현/필수 포함 문구)
  - 출력: 대체 조항(plain text), “주의/검토 포인트”

템플릿 방식:
- 기본은 문자열 템플릿(표준 라이브러리)로 구성
- prompt에는 반드시:
  - 입력 데이터 경계(원문/룰/요약)
  - 출력 JSON 스키마(파싱 안정성)
  - 금지/주의(비밀/개인정보, 과장 금지, 법률 자문 아님)

## 5) fallback 전략(키가 없거나 실패하는 경우)
- Provider 선택:
  - `api_key`가 없으면 무조건 `mock_provider`로 동작
- 기능별 fallback:
  - 설명 생성 실패 → rule의 `description`/`review_action` 기반 요약만 제공
  - 수정문안 생성 실패 → 현재 `fallback_text`/`suggested_direction`만 표시
  - 초안 생성 실패 → “초안 불가/기준 필요” 메시지 + 템플릿 목록만 제공
- 장애 격리:
  - AI 호출 실패는 5xx로 전체를 실패시키지 않고, 결과에 `ai.error`로만 기록

## 6) 로그/비용/보안 고려사항
- 로그
  - 기본: 요청 ID/기능명/모델/응답시간/토큰 사용량(가능할 때)/실패 사유만 기록
  - 금지: 계약서 원문 전체, API key, 개인식별정보 원문을 로그에 남기지 않음
- 비용
  - 요청 단위 토큰 상한(`max_tokens`) 강제
  - 긴 계약서는 조항 단위로 쪼개고 필요한 부분만 전송
  - 캐시(추후): 동일 clause/rule 조합 재생성 방지
- 보안
  - API key는 ENV/secret file/secret manager로만 주입
  - 서버 응답에 key/endpoint 등 민감정보를 포함하지 않음
  - 데이터 보관 정책(원문 저장/마스킹/보관기간)을 EP 연동 전에 확정

## 7) MVP에서 우선 붙일 AI 기능 3개(추천)
1. rule 기반 검토 결과 “설명 생성”
   - 기존 rule description/review_action을 문장으로 정리해 사용자 이해를 크게 개선
2. 조항 수정 제안 “대체 문안 생성”(redline 제외)
   - fallback_text가 부족한 케이스에서 실사용 가치가 크게 올라감
3. 계약서 기반 Q&A(질문에 대한 근거 문장 추출)
   - 사전 질문 답을 계약서에서 찾아주면 법무팀 검토 속도가 개선

