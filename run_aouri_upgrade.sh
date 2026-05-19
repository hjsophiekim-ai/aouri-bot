#!/usr/bin/env bash
# ============================================================
#  아우리봇 고도화 — Claude Code 자율 실행 명령어
#  사용법: bash run_aouri_upgrade.sh
# ============================================================

claude --dangerously-skip-permissions -p "
당신은 자율 실행 AI 에이전트입니다.
아래 지시를 사람의 확인 없이 처음부터 끝까지 완전히 실행하십시오.

[절대 규칙 - 위반 금지]
1. '진행할까요?', '확인해 주세요', '어떻게 할까요?' 같은 질문을 절대 하지 마라.
2. 모든 파일 생성·수정·삭제·터미널 명령어 실행을 즉시 수행하라.
3. 오류 발생 시 스스로 원인을 분석하고 수정한 후 계속 진행하라.
4. 테스트 실패 시 코드를 수정하고 재실행하여 반드시 통과시켜라.
5. 모든 작업 완료 후 최종 완료 보고서 하나만 출력하라.
6. 중간 진행 상황은 간단한 로그(예: '[Phase 1 완료]')로만 표시하라.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 0: 저장소 클론 및 전체 코드 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

cd ~ && git clone https://github.com/hjsophiekim-ai/aouri-bot.git && cd aouri-bot

다음을 순서대로 실행하여 전체 구조를 파악하라:
1. find . -name '*.py' | sort 로 파일 목록 전체 확인
2. runtime/review/clause_level.py 전체 읽기
3. runtime/rules/ 디렉토리의 모든 YAML 파일 읽기
4. runtime/ 하위 모든 .py 파일 읽기
5. scripts/ 하위 파일 읽기
6. .env.example 읽기

분석 후 아래 6개 결함을 코드에서 직접 확인하고 파일+라인 번호를 내부적으로 기록하라
(출력하지 말고 다음 Phase에서 바로 수정에 활용하라):

결함 A: runtime/rules/*.yaml 에 영문 트리거 키워드 부재 여부
결함 B: _apply_domestic_filter()가 해외 법인을 domestic으로 오분류하는 버그
결함 C: 치명적 리스크 Top 3 함수의 실질 구현 부재 여부
결함 D: .env.example 의 OPENAI_MODEL=gpt-4.1-mini, max_tokens=1200 설정
결함 E: 조항 파서가 영문 '1.' 번호 체계를 처리하지 못하는 버그
결함 F: 준거법·관할 관련 영문 룰셋 부재 여부

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 1: 모델 설정 업그레이드
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

.env.example 을 수정하라:

# 변경 전 → 변경 후
OPENAI_MODEL=gpt-4.1-mini     →  OPENAI_MODEL=gpt-4.1
OPENAI_MAX_TOKENS=1200         →  OPENAI_MAX_TOKENS=4000
OPENAI_TEMPERATURE=0.2         →  OPENAI_TEMPERATURE=0.1

# 신규 추가
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ANTHROPIC_MAX_TOKENS=4000
LLM_PROVIDER=anthropic

실제 설정을 로드하는 Python 파일(config.py, settings.py, 또는 유사 파일)도 동일하게 수정하라.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 2: LLM 클라이언트 듀얼 지원 추가
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존 LLM 호출 코드를 찾아 Anthropic SDK를 추가 지원하도록 수정하라.
파일이 없으면 runtime/llm_client.py 를 신규 생성하라:

import os

class LLMClient:
    def __init__(self):
        self.provider = os.getenv('LLM_PROVIDER', 'anthropic')
        if self.provider == 'anthropic':
            import anthropic
            self.client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
            self.model = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
            self.max_tokens = int(os.getenv('ANTHROPIC_MAX_TOKENS', 4000))
        else:
            import openai
            self.client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            self.model = os.getenv('OPENAI_MODEL', 'gpt-4.1')
            self.max_tokens = int(os.getenv('OPENAI_MAX_TOKENS', 4000))

    def complete(self, system: str, user: str, temperature: float = 0.1) -> str:
        if self.provider == 'anthropic':
            msg = self.client.messages.create(
                model=self.model, max_tokens=self.max_tokens,
                temperature=temperature, system=system,
                messages=[{'role': 'user', 'content': user}]
            )
            return msg.content[0].text
        else:
            resp = self.client.chat.completions.create(
                model=self.model, max_tokens=self.max_tokens,
                temperature=temperature,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': user}
                ]
            )
            return resp.choices[0].message.content

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 3: 조항 파서 다국어화
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존 조항 파서 파일을 찾아 영문 NDA 조항 패턴을 추가하라.
파일이 없으면 runtime/review/clause_parser.py 를 신규 생성하라:

import re
from dataclasses import dataclass
from typing import List

@dataclass
class Clause:
    number: str
    title: str
    body: str
    language: str
    start_pos: int

KOREAN_RE = re.compile(
    r'제\s*(\d+)\s*조\s*(?:\(([^)]+)\))?\s*\n?([\s\S]+?)(?=제\s*\d+\s*조|\Z)',
    re.MULTILINE
)
ENGLISH_NUM_RE = re.compile(
    r'^(\d+)[.)]\s+(?:\[?([A-Z][^\n]{0,60})\]?\n)?([\s\S]+?)(?=^\d+[.)]\s|\Z)',
    re.MULTILINE
)
ARTICLE_RE = re.compile(
    r'(?:Article|Section|Clause)\s+(\d+)[.):]?\s*(?:\n?([^\n]{0,80})\n)?([\s\S]+?)'
    r'(?=(?:Article|Section|Clause)\s+\d+|\Z)',
    re.IGNORECASE | re.MULTILINE
)

def detect_language(text: str) -> str:
    ko = len(re.findall(r'[\uAC00-\uD7A3]', text))
    total = len(re.findall(r'[a-zA-Z\uAC00-\uD7A3]', text))
    return 'ko' if (total == 0 or ko / total > 0.3) else 'en'

def parse_clauses(text: str) -> List[Clause]:
    lang = detect_language(text)
    clauses = []
    if lang == 'ko':
        for m in KOREAN_RE.finditer(text):
            clauses.append(Clause(m.group(1), m.group(2) or '', m.group(3).strip(), 'ko', m.start()))
    else:
        matches = list(ARTICLE_RE.finditer(text)) or list(ENGLISH_NUM_RE.finditer(text))
        for m in matches:
            clauses.append(Clause(m.group(1), (m.group(2) or '').strip(), m.group(3).strip(), 'en', m.start()))
    if not clauses:
        clauses.append(Clause('0', '전문', text.strip(), lang, 0))
    return clauses

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 4: Domestic Filter 버그 수정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_apply_domestic_filter() 함수를 찾아 아래 로직으로 교체하라:

def _apply_domestic_filter(self, results: list, meta: dict) -> list:
    party_a_country = meta.get('party_a', {}).get('country', '')
    party_b_country = meta.get('party_b', {}).get('country', '')
    is_international = meta.get('is_international', False)

    KR_MARKERS = ['한국', 'Korea', 'KR', 'South Korea']
    non_kr = [
        c for c in [party_a_country, party_b_country]
        if c and not any(m in c for m in KR_MARKERS)
    ]
    # 어느 한쪽이라도 해외 법인이면 domestic filter 미적용
    if non_kr or is_international:
        return results

    BLOCK = ['다국가', '국제 관할', '해외 집행', 'cross-border', 'foreign jurisdiction']
    filtered = []
    for item in results:
        combined = (item.get('suggested_rewrite') or '') + (item.get('rewrite_reason') or '')
        if any(p.lower() in combined.lower() for p in BLOCK):
            item['suggested_rewrite'] = None
            item['guardrail_block'] = {'filter': 'domestic_filter_v2'}
            item['risk_tier'] = 'LOW'
            item['must_fix'] = False
        filtered.append(item)
    return filtered

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 5: 영문 NDA 전용 룰셋 추가
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

runtime/rules/en_nda_rules.yaml 파일을 신규 생성하라:

version: '2.0'
applies_to: ['NDA', 'Confidentiality Agreement', 'Non-Disclosure Agreement']
language: en

rules:
  - id: EN_NDA_001
    topic: jurisdiction
    risk_tier: HIGH
    must_fix: true
    approval_required: true
    triggers:
      any_of:
        - exclusive jurisdiction
        - court of exclusive jurisdiction
        - Stuttgart
        - München
        - Berlin
        - Frankfurt
        - exclusive venue
    suggested_rewrite: |
      Any disputes shall be finally settled by arbitration under ICC Rules
      by one arbitrator. Place of arbitration: Singapore. Language: English.
    rewrite_reason: 국제 중재로 대체하여 한국 당사자의 지리적 불이익 해소

  - id: EN_NDA_002
    topic: governing_law
    risk_tier: HIGH
    must_fix: false
    approval_required: true
    triggers:
      any_of:
        - German law shall apply
        - laws of Germany
        - Austrian law
        - laws of Austria
        - governed by the laws of
    negotiation_strategy: |
      1안: 싱가포르·영국 중립국 법으로 대체
      2안: 병행 관할 허용 조항 추가
      3안: 독일법 유지하되 ICC 중재로 관할 변경

  - id: EN_NDA_003
    topic: data_deletion
    risk_tier: MEDIUM
    must_fix: false
    triggers:
      any_of:
        - cannot be recovered
        - unrecoverable manner
        - deleted in such a manner
    suggested_rewrite: |
      Data shall be deleted per the receiving party's standard retention policy.
      Copies for DR/regulatory compliance remain subject to confidentiality obligations.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 6: LLM 기반 조항 분석 시스템 프롬프트 주입
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

runtime/review/clause_level.py 에서 LLM 호출 시스템 프롬프트를 아래로 교체하라.
기존 프롬프트가 없으면 조항별 LLM 호출 함수를 신규 생성하라:

CLAUSE_REVIEW_SYSTEM = '''
당신은 대한민국 대형 로펌 출신 기업법무 파트너 변호사입니다.
Fursys Inc.(퍼시스) 법무팀 내부 법률자문으로서 퍼시스의 이익을 최우선으로 검토합니다.

검토 원칙:
1. 상대방 표준 양식은 상대방에게 유리하게 설계되어 있다고 가정하고 시작하라.
2. 실제 분쟁 발생 시 퍼시스가 입을 최악의 시나리오를 먼저 상정하라.
3. 모든 위험은 금전적·운영적 영향으로 구체화하라.
4. 영문 계약서는 독일법·오스트리아법·EU법 맥락에서 해석하라.
5. 수정 제안은 반드시 대체 문안(원문 언어)을 제시하라.
6. 근거 없는 위험을 과장하지 말고 실재하는 위험만 정확히 지적하라.

출력: 반드시 아래 JSON 스키마만 출력하라. 다른 텍스트 절대 금지.
'''

CLAUSE_REVIEW_USER = '''
계약 맥락:
- 유형: {contract_type}
- 당사자: {party_a}({party_a_country}) vs {party_b}({party_b_country})
- 퍼시스 포지션: {fursys_position}
- 국제 거래: {is_international}
- 상대방 양식: {is_counterparty_form}
- 준거법: {governing_law}
- 관할: {jurisdiction}

분석 조항 #{clause_number} [{clause_title}]:
---
{clause_body}
---

아래 JSON으로만 응답하라:
{{
  "clause_number": "{clause_number}",
  "topic": "governing_law|jurisdiction|confidentiality|data_deletion|ip|payment|termination|liability|dispute|other",
  "risk_tier": "HIGH|MEDIUM|LOW|NONE",
  "must_fix": true|false,
  "approval_required": true|false,
  "risk_summary": "2~3문장으로 위험의 본질과 퍼시스 실질 영향 서술",
  "worst_case_scenario": "분쟁 발생 시 퍼시스가 직면할 최악 상황 1~2문장",
  "legal_basis": ["관련 법령 또는 법원칙"],
  "suggested_rewrite": "수정 제안 문안 또는 null",
  "rewrite_reason": "수정 이유 또는 null",
  "negotiation_strategy": "협상 전략 또는 null"
}}
'''

TOP3_RISK_SYSTEM = '''
당신은 기업법무 파트너 변호사입니다.
조항별 분석 결과를 종합하여 치명적 리스크 Top 3~5를 선정하라.
반드시 JSON만 출력하라.
'''

TOP3_RISK_USER = '''
계약 맥락: {meta_summary}

전체 조항 분석 결과:
{all_clause_summaries}

퍼시스에게 가장 치명적인 리스크 3~5개를 중요도 순으로 선정하라.
기준: 분쟁 시 금전 손실, 사업 중단, 평판 손상, 법적 불이익 중 하나 이상이 실질적으로 발생 가능한 것.

아래 JSON으로만 응답하라:
{{
  "top_risks": [
    {{
      "rank": 1,
      "clause_number": "조항 번호",
      "risk_title": "리스크 제목 20자 이내",
      "severity": "CRITICAL|HIGH",
      "one_line_summary": "경영진 보고용 1문장 요약",
      "financial_impact": "예상 금전적 영향 또는 정량화 불가",
      "recommended_action": "서명 전 반드시 취해야 할 조치",
      "deadline": "즉시|서명 전|계약 기간 중"
    }}
  ],
  "overall_recommendation": "SIGN_AS_IS|SIGN_WITH_MINOR_CHANGES|NEGOTIATE_BEFORE_SIGNING|DO_NOT_SIGN",
  "recommendation_reason": "2~3문장 종합 의견"
}}
'''

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 7: 파이프라인 통합
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

build_clause_level_result() 함수(또는 이에 해당하는 메인 검토 함수)를
아래 실행 순서로 재구성하라:

1. detect_language() 로 언어 탐지
2. parse_clauses() 로 조항 파싱 (다국어)
3. LLM으로 계약 메타데이터 추출 (당사자·준거법·관할 등)
4. 조항별 LLM 심층 분석 (CLAUSE_REVIEW_SYSTEM + CLAUSE_REVIEW_USER)
5. en_nda_rules.yaml 룰셋 결과로 LLM 결과 보완 (룰셋이 더 엄격하면 우선)
6. _apply_zero_hallucination_guardrail() 적용
7. _apply_domestic_filter() 적용 (수정된 버전)
8. _apply_clause_integrity_filter() 적용
9. _apply_global_sentence_dedup() 적용
10. TOP3_RISK_SYSTEM + TOP3_RISK_USER 로 치명적 리스크 Top 3~5 LLM 종합 판단
11. 최종 구조화된 결과 반환

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 8: DOCX 출력 개선
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

runtime/review/docx_writer.py 를 수정하여:

1. 치명적 리스크 Top 3~5 표를 문서 앞부분(표지 다음)에 배치
   - 컬럼: 순위 / 조항 / 리스크 제목 / 예상 영향 / 권고 조치
   - 기존의 '근거 부족' 공란을 LLM 생성 내용으로 교체

2. 조항별 상세 분석에 다음 항목 추가:
   - worst_case_scenario (최악 시나리오)
   - negotiation_strategy (협상 전략)
   - legal_basis (관련 법령)

3. 종합 서명 권고(SIGN_AS_IS / NEGOTIATE_BEFORE_SIGNING 등)를 표지에 표시

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 9: 의존성 설치 및 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

pip install anthropic openai python-docx pyyaml -q

아래 테스트를 tests/test_nda_review.py 로 생성하고 실행하라.
실패하면 코드를 수정하고 재실행하여 반드시 통과시켜라:

NDA_TEXT = '''
between
Porsche Design GmbH, Flugplatzstrasse 29, 5700 Zell am See, Austria
and
Fursys Inc., 05661 Seoul, 311 Ogeum-Ro, Songpa-Gu, South Korea
1. Both parties shall treat as strictly confidential all information disclosed.
6. Electronically stored data is to be deleted in such a manner that it cannot be recovered.
8. Stuttgart shall be the court of exclusive jurisdiction. German law shall apply.
'''

def test_clause_parsing():
    from runtime.review.clause_parser import parse_clauses
    clauses = parse_clauses(NDA_TEXT)
    numbers = [c.number for c in clauses]
    assert '8' in numbers, f'제8조 파싱 실패. 파싱된 조항: {numbers}'

def test_jurisdiction_detected():
    from runtime.review.clause_parser import parse_clauses
    from runtime.rules.rule_checker import check_en_nda_rules  # 룰 체커 함수 위치 확인 후 import 수정
    clauses = parse_clauses(NDA_TEXT)
    clause8 = next((c for c in clauses if c.number == '8'), None)
    assert clause8 is not None
    hit = check_en_nda_rules(clause8, {})
    assert hit and hit.get('risk_tier') == 'HIGH', f'EN_NDA_001 룰 미적용: {hit}'

def test_domestic_filter_not_applied():
    meta = {
        'party_a': {'country': 'Austria'},
        'party_b': {'country': 'South Korea'},
        'is_international': True
    }
    from runtime.review.clause_level import _apply_domestic_filter
    dummy = [{'risk_tier': 'HIGH', 'topic': 'jurisdiction', 'suggested_rewrite': 'cross-border arbitration'}]
    result = _apply_domestic_filter(None, dummy, meta)
    assert result[0]['risk_tier'] == 'HIGH', 'Domestic Filter 오작동: 국제 거래인데 LOW로 강제됨'

if __name__ == '__main__':
    test_clause_parsing()
    print('[테스트 1 통과] 영문 조항 파싱')
    test_jurisdiction_detected()
    print('[테스트 2 통과] EN_NDA_001 룰 탐지')
    test_domestic_filter_not_applied()
    print('[테스트 3 통과] Domestic Filter 버그 수정 확인')
    print('모든 테스트 통과')

python tests/test_nda_review.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Phase 10: 최종 완료 보고
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

모든 Phase 완료 후 아래 형식으로 최종 보고서를 출력하라:

=== 아우리봇 고도화 완료 보고 ===
완료 시각: (현재 시각)
수정된 파일 목록: (파일명 + 변경 요약)
신규 생성 파일 목록: (파일명)
테스트 결과: (통과/실패)
예상 개선 효과:
  - 제8조 준거법·관할 탐지: ❌→✅
  - 치명적 리스크 Top 3: ❌→✅
  - 수정 제안 문안: ❌→✅
  - Domestic Filter 버그: ❌→✅
  - 영문 조항 파싱: ❌→✅
"
