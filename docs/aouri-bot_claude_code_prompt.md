# 아우리봇(aouri-bot) 지능형 법무검토 엔진 고도화
## Claude Code AI Agent 실행 프롬프트

---

## ⚡ 실행 명령어 (복사해서 터미널에 붙여넣기)

```bash
claude --dangerously-skip-permissions -p "
당신은 자율 실행 AI 에이전트입니다. 아래 모든 지시를 사람의 확인 없이 끝까지 완전히 실행하십시오.

절대 규칙:
- 중간에 '진행할까요?', '확인해 주세요', '맞나요?' 같은 질문을 하지 마라.
- 파일 생성·수정·삭제·명령어 실행을 모두 즉시 수행하라.
- 오류가 발생하면 스스로 원인을 분석하고 수정하여 계속 진행하라.
- 모든 Phase를 순서대로 완료한 후 최종 완료 보고서만 출력하라.
- 테스트가 실패하면 코드를 수정하고 재실행하여 통과시켜라.

$(cat aouri-bot_claude_code_prompt.md)
"
```

또는 프롬프트 파일을 직접 넘기는 방식:

```bash
claude --dangerously-skip-permissions < aouri-bot_claude_code_prompt.md
```

---

## 🎯 임무 개요

`hjsophiekim-ai/aouri-bot` 저장소를 클론하여, 현재 규칙 기반(rule-based) 법무검토 엔진의
근본적 결함을 분석하고 LLM 기반 지능형 법무검토 엔진으로 전면 재설계하라.

**실패 사례 기준**: Porsche Design GmbH × Fursys Inc. NDA (영문, 2쪽)를 입력했을 때
제8조 슈투트가르트 전속 관할·독일 준거법을 탐지하지 못하고,
치명적 리스크 Top 3를 "근거 부족"으로 공란 처리한 현재 출력을
변호사 수준으로 끌어올리는 것이 목표다.

---

## 📋 Phase 0: 저장소 분석 및 실패 원인 진단

```
cd ~ && git clone https://github.com/hjsophiekim-ai/aouri-bot.git && cd aouri-bot
```

다음 순서로 전체 코드를 읽어라:

1. `find . -name "*.py" | head -60` 로 파일 목록 파악
2. `runtime/review/clause_level.py` 전체 읽기
3. `runtime/rules/` 디렉토리의 모든 YAML 룰셋 읽기
4. `runtime/` 하위 모든 Python 파일 읽기
5. `scripts/` 하위 파일 읽기

분석 후 다음 6가지 결함을 코드에서 직접 확인하고 파일·라인 번호를 기록하라:

### 결함 #1: 영문 계약서 키워드 미지원
- `runtime/rules/*.yaml` 에서 영문 트리거 키워드(exclusive jurisdiction, governing law,
  Stuttgart, arbitration 등)가 존재하는지 확인
- 없으면: **영문 NDA 전용 룰셋 부재** 확진

### 결함 #2: Domestic Filter 오작동
- `_apply_domestic_filter()` 로직 확인
- 한국 법인이 당사자에 포함되면 국제 관할 이슈를 `LOW`로 강제하는지 확인
- 상대방이 오스트리아 법인(해외)인데도 domestic으로 분류되는 버그 여부 확인

### 결함 #3: Top 3 리스크 자동선정 로직 부재
- `치명적 리스크 Top 3` 또는 유사 함수가 존재하는지 grep
- 없거나 형식적으로만 존재하면: **실질 구현 부재** 확진

### 결함 #4: 모델 설정의 구조적 한계
- `.env.example` 확인: `OPENAI_MODEL=gpt-4.1-mini`, `OPENAI_MAX_TOKENS=1200`
- 법적 추론에 1200 토큰은 치명적으로 부족함을 코드에서 확인

### 결함 #5: 조항 파싱의 영문 NDA 처리 실패
- 조항 파서(clause splitter)가 "1.", "2." 등 영문 번호 체계를 처리하는지 확인
- 한국어 "제X조" 패턴에만 의존하는지 확인

### 결함 #6: 준거법·관할 조항 탐지 룰 부재
- `dispute`, `jurisdiction`, `governing_law` 관련 영문 키워드가 룰셋에 있는지 확인
- `_apply_domestic_filter`가 해외 거래임에도 LOW로 강제하는 경로가 있는지 추적

---

## 📋 Phase 1: 핵심 엔진 교체 — LLM 기반 조항 분석기

### 1-1. 모델 설정 업그레이드

`.env.example` 및 실제 설정 파일을 수정하라:

```
# 변경 전
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_TOKENS=1200
OPENAI_TEMPERATURE=0.2

# 변경 후
OPENAI_MODEL=gpt-4.1          # mini → full (법적 추론 품질)
OPENAI_MAX_TOKENS=4000         # 1200 → 4000 (충분한 분석 공간)
OPENAI_TEMPERATURE=0.1         # 낮게 유지 (일관성)

# Anthropic Claude 추가 (fallback 또는 primary)
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ANTHROPIC_MAX_TOKENS=4000
```

`runtime/` 의 LLM 클라이언트 코드를 찾아 Anthropic SDK도 지원하도록 추가하라:

```python
# runtime/llm_client.py (신규 또는 기존 파일 수정)

import os
import anthropic
import openai

class LLMClient:
    """OpenAI / Anthropic 듀얼 지원 클라이언트"""

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "anthropic")  # default: anthropic
        if self.provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self.model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
            self.max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", 4000))
        else:
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv("OPENAI_MODEL", "gpt-4.1")
            self.max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", 4000))

    def complete(self, system: str, user: str, temperature: float = 0.1) -> str:
        if self.provider == "anthropic":
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}]
            )
            return msg.content[0].text
        else:
            resp = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
            )
            return resp.choices[0].message.content
```

### 1-2. 조항 파서 다국어화

기존 조항 파서를 찾아 영문 NDA 패턴을 추가하라:

```python
# runtime/review/clause_parser.py (기존 파일 수정)

import re
from dataclasses import dataclass
from typing import List

@dataclass
class Clause:
    number: str          # "1", "제1조", "Article 1" 등
    title: str           # 조항 제목 (없으면 빈 문자열)
    body: str            # 조항 본문
    language: str        # "ko" | "en"
    start_pos: int       # 원문 내 시작 위치

KOREAN_CLAUSE_RE = re.compile(
    r'제\s*(\d+)\s*조\s*(?:\(([^)]+)\))?\s*\n?([\s\S]+?)(?=제\s*\d+\s*조|\Z)',
    re.MULTILINE
)

# 영문 NDA 패턴: "1.", "1)", "Article 1", "Section 1" 등
ENGLISH_CLAUSE_RE = re.compile(
    r'^(\d+)[.)]\s+(?:\[?([A-Z][^\n]{0,60})\]?\n)?([\s\S]+?)(?=^\d+[.)]\s|\Z)',
    re.MULTILINE
)

ARTICLE_CLAUSE_RE = re.compile(
    r'(?:Article|Section|Clause)\s+(\d+)[.):]?\s*(?:\n?([^\n]{0,80})\n)?([\s\S]+?)'
    r'(?=(?:Article|Section|Clause)\s+\d+|\Z)',
    re.IGNORECASE | re.MULTILINE
)

def detect_language(text: str) -> str:
    korean_chars = len(re.findall(r'[\uAC00-\uD7A3]', text))
    total_alpha = len(re.findall(r'[a-zA-Z\uAC00-\uD7A3]', text))
    if total_alpha == 0:
        return "ko"
    return "ko" if korean_chars / total_alpha > 0.3 else "en"

def parse_clauses(full_text: str) -> List[Clause]:
    lang = detect_language(full_text)
    clauses = []

    if lang == "ko":
        for m in KOREAN_CLAUSE_RE.finditer(full_text):
            clauses.append(Clause(
                number=m.group(1),
                title=m.group(2) or "",
                body=m.group(3).strip(),
                language="ko",
                start_pos=m.start()
            ))
    else:
        # Article/Section 패턴 먼저 시도
        matches = list(ARTICLE_CLAUSE_RE.finditer(full_text))
        if not matches:
            matches = list(ENGLISH_CLAUSE_RE.finditer(full_text))

        for m in matches:
            clauses.append(Clause(
                number=m.group(1),
                title=(m.group(2) or "").strip(),
                body=m.group(3).strip(),
                language="en",
                start_pos=m.start()
            ))

    # 파싱 실패 시 전체를 단일 블록으로
    if not clauses:
        clauses.append(Clause(
            number="0",
            title="전문",
            body=full_text.strip(),
            language=lang,
            start_pos=0
        ))

    return clauses
```

---

## 📋 Phase 2: 지능형 법무검토 시스템 프롬프트 설계

### 2-1. 계약 메타데이터 추출기

```python
# runtime/review/meta_extractor.py (신규 생성)

META_EXTRACTION_SYSTEM = """
당신은 기업 법무팀의 선임 계약 검토 변호사입니다.
계약서 전문을 읽고 아래 메타데이터를 JSON으로 추출하십시오.

반드시 JSON만 출력하고 다른 텍스트는 없어야 합니다.
"""

META_EXTRACTION_USER_TEMPLATE = """
계약서 전문:
---
{full_text}
---

다음 JSON 스키마로 정확히 추출하라:
{{
  "contract_type": "NDA|용역|물품공급|대리점|렌탈|기타",
  "language": "ko|en|mixed",
  "party_a": {{
    "name": "...",
    "country": "...",
    "role": "갑|을|공동|위탁자|수탁자|불명"
  }},
  "party_b": {{
    "name": "...",
    "country": "...",
    "role": "갑|을|공동|위탁자|수탁자|불명"
  }},
  "fursys_position": "갑|을|공동|불명",
  "is_international": true|false,
  "governing_law_country": "국가명 또는 null",
  "jurisdiction_city": "도시명 또는 null",
  "has_arbitration": true|false,
  "contract_value_krw": 숫자 또는 null,
  "effective_date": "YYYY-MM-DD 또는 null",
  "duration_months": 숫자 또는 null,
  "signed_date": "YYYY-MM-DD 또는 null"
}}
"""
```

### 2-2. 핵심 조항별 LLM 분석기

아래 시스템 프롬프트를 `runtime/review/clause_level.py`의
LLM 호출 부분에 교체 또는 신규 추가하라.
기존 키워드 매칭 루프는 `_is_en_nda` 플래그가 True일 때 **완전히 건너뛰고**
아래 LLM 분석으로 대체한다:

```python
# runtime/review/clause_level.py 에 추가할 핵심 프롬프트

CLAUSE_REVIEW_SYSTEM = """
당신은 대한민국 대형 로펌 출신의 기업법무 파트너 변호사입니다.
Fursys Inc.(퍼시스) 법무팀의 내부 법률자문으로서, 퍼시스의 이익을 최우선으로 검토합니다.

검토 원칙:
1. 상대방 표준 계약서는 상대방에게 유리하게 설계되어 있다고 가정하고 시작하라.
2. 실제 분쟁이 발생했을 때 퍼시스가 입을 수 있는 최악의 시나리오를 먼저 상정하라.
3. 모든 위험은 금전적·운영적·평판적 영향으로 구체화하여 서술하라.
4. 영문 계약서의 경우 영미법·독일법·오스트리아법·EU법의 맥락에서 해석하라.
5. 수정 제안은 반드시 대체 문안(영문 또는 국문)을 제시하라.
6. 근거 없는 위험을 과장하지 말고, 실재하는 위험만 정확히 지적하라.

출력 형식: 반드시 아래 JSON 스키마를 준수하라. 다른 텍스트는 절대 출력하지 마라.
"""

CLAUSE_REVIEW_USER_TEMPLATE = """
## 계약 전체 맥락
- 계약 유형: {contract_type}
- 당사자: {party_a}({party_a_country}) vs {party_b}({party_b_country})
- 퍼시스 포지션: {fursys_position}
- 국제 거래 여부: {is_international}
- 상대방 양식 여부: {is_counterparty_form}
- 준거법: {governing_law}
- 관할: {jurisdiction}

## 분석 대상 조항
조항 번호: {clause_number}
조항 제목: {clause_title}
조항 원문:
---
{clause_body}
---

## 요청
위 조항을 퍼시스 법무팀 변호사 관점에서 분석하고 아래 JSON으로만 응답하라:

{{
  "clause_number": "{clause_number}",
  "clause_title": "{clause_title}",
  "topic": "governing_law|jurisdiction|confidentiality|data_deletion|ip|payment|termination|liability|dispute|personal_data|기타",
  "risk_tier": "HIGH|MEDIUM|LOW|NONE",
  "must_fix": true|false,
  "approval_required": true|false,
  "risk_summary": "2~3문장으로 위험의 본질과 퍼시스에 미치는 실질적 영향 서술",
  "worst_case_scenario": "분쟁 발생 시 퍼시스가 직면할 최악의 구체적 상황 1~2문장",
  "legal_basis": ["관련 법령 또는 법원칙 목록"],
  "suggested_rewrite": "수정 제안 문안 (원문 언어와 동일하게 작성, 수정 불필요 시 null)",
  "rewrite_reason": "수정 이유 1~2문장 (suggested_rewrite가 있을 때만)",
  "negotiation_strategy": "PDG와 협상 시 구체적 전략 (선택사항, 없으면 null)"
}}
"""

TOP3_RISK_SYSTEM = """
당신은 기업법무 파트너 변호사입니다.
아래 조항별 분석 결과를 바탕으로 치명적 리스크 Top 3~5를 선정하라.
반드시 JSON만 출력하라.
"""

TOP3_RISK_USER_TEMPLATE = """
## 계약 전체 맥락
{meta_summary}

## 전체 조항 분석 결과 (요약)
{all_clause_summaries}

## 요청
퍼시스에게 가장 치명적인 리스크 3~5개를 중요도 순으로 선정하고 아래 JSON으로만 응답하라.
"치명적"의 기준: 분쟁 발생 시 금전적 손실, 사업 중단, 평판 손상, 법적 불이익 중 하나 이상이
실질적으로 발생할 가능성이 있는 것.

{{
  "top_risks": [
    {{
      "rank": 1,
      "clause_number": "조항 번호",
      "risk_title": "리스크 제목 (20자 이내)",
      "severity": "CRITICAL|HIGH",
      "one_line_summary": "경영진에게 보고하는 수준의 1문장 요약",
      "financial_impact": "예상 금전적 영향 또는 '정량화 불가'",
      "recommended_action": "서명 전 반드시 취해야 할 조치",
      "deadline": "즉시|서명 전|계약 기간 중"
    }}
  ],
  "overall_recommendation": "SIGN_AS_IS|SIGN_WITH_MINOR_CHANGES|NEGOTIATE_BEFORE_SIGNING|DO_NOT_SIGN",
  "recommendation_reason": "2~3문장 종합 의견"
}}
"""
```

---

## 📋 Phase 3: Domestic Filter 버그 수정

`_apply_domestic_filter()` 함수를 찾아 아래 로직으로 교체하라:

```python
def _apply_domestic_filter(self, results: list, meta: dict) -> list:
    """
    [수정] 퍼시스가 한국 법인이더라도 상대방이 해외 법인이면 국제 거래로 처리.
    기존 로직은 퍼시스가 한국 법인이라는 이유만으로 domestic으로 분류하는 버그가 있었음.
    """
    is_international = meta.get("is_international", False)
    party_a_country = meta.get("party_a", {}).get("country", "")
    party_b_country = meta.get("party_b", {}).get("country", "")

    # 어느 한 쪽이라도 한국이 아니면 국제 거래
    non_kr_parties = [
        c for c in [party_a_country, party_b_country]
        if c and "한국" not in c and "Korea" not in c and "KR" not in c
    ]

    if non_kr_parties or is_international:
        # 국제 거래: domestic filter 적용 안 함
        return results

    # 국내 거래만 domestic filter 적용
    filtered = []
    DOMESTIC_BLOCK_PATTERNS = [
        "다국가 거래", "국제 관할", "해외 집행", "cross-border",
        "foreign jurisdiction", "international arbitration"
    ]
    for item in results:
        rewrite = item.get("suggested_rewrite") or ""
        reason = item.get("rewrite_reason") or ""
        combined = rewrite + reason
        if any(p.lower() in combined.lower() for p in DOMESTIC_BLOCK_PATTERNS):
            item["suggested_rewrite"] = None
            item["guardrail_block"] = {"filter": "domestic_filter_v2"}
            item["risk_tier"] = "LOW"
            item["must_fix"] = False
        filtered.append(item)
    return filtered
```

---

## 📋 Phase 4: 영문 NDA 전용 고위험 조항 룰셋 추가

`runtime/rules/` 디렉토리에 `en_nda_rules.yaml` 파일을 신규 생성하라:

```yaml
# runtime/rules/en_nda_rules.yaml
# 영문 NDA 전용 고위험 조항 탐지 룰셋

version: "2.0"
applies_to: ["NDA", "Confidentiality Agreement", "Non-Disclosure Agreement"]
language: "en"

rules:
  - id: EN_NDA_001
    topic: jurisdiction
    risk_tier: HIGH
    must_fix: true
    approval_required: true
    triggers:
      any_of:
        - "exclusive jurisdiction"
        - "court of exclusive jurisdiction"
        - "Stuttgart"
        - "München"
        - "Berlin"
        - "Frankfurt"
        - "Düsseldorf"
        - "Hamburg"
        - "exclusive venue"
    exclude_if_present:
      - "arbitration"
      - "ICC"
      - "KCAB"
      - "AAA"
    comment: |
      외국 법원의 전속 관할 조항은 퍼시스가 분쟁 시 해당 국가에서
      소송을 수행해야 하는 막대한 비용과 불편을 초래한다.
    suggested_rewrite: |
      Any disputes arising out of or in connection with this Agreement
      shall be finally settled by arbitration under the Rules of the
      International Chamber of Commerce (ICC) by one arbitrator
      appointed in accordance with said Rules. The place of arbitration
      shall be Singapore. The language of the arbitration shall be English.
    rewrite_reason: "국제 중재로 대체하여 한국 당사자의 지리적 불이익 해소"

  - id: EN_NDA_002
    topic: governing_law
    risk_tier: HIGH
    must_fix: false
    approval_required: true
    triggers:
      any_of:
        - "German law shall apply"
        - "laws of Germany"
        - "law of Germany"
        - "Austrian law"
        - "laws of Austria"
        - "governed by the laws of"
    comment: |
      독일법/오스트리아법 적용은 한국 법무팀의 해석 역량을 벗어나며,
      독일 현지 법무법인 자문이 필요하여 비용이 급증한다.
      또한 독일 BGB의 비밀유지 관련 조항은 한국 부정경쟁방지법과 상이하다.
    negotiation_strategy: |
      1안: 중립국(싱가포르, 영국) 법으로 대체
      2안: 각 당사자 본국 법원에서 집행 가능한 병행 관할 허용
      3안: 독일법 유지하되 ICC 중재로 관할 변경

  - id: EN_NDA_003
    topic: data_deletion
    risk_tier: MEDIUM
    must_fix: false
    triggers:
      any_of:
        - "cannot be recovered"
        - "irrecoverable"
        - "permanently delete"
        - "unrecoverable manner"
        - "deleted in such a manner"
    comment: |
      전자 데이터의 복구 불가능한 삭제 의무는 기업 IT 백업/DR 시스템과
      충돌하며, 회계·세무 목적의 법정 보존 의무와도 상충할 수 있다.
    suggested_rewrite: |
      Electronically stored data shall be deleted in accordance with the
      receiving party's standard data retention policy, provided that any
      copies retained for disaster recovery or regulatory compliance purposes
      shall remain subject to the confidentiality obligations herein and
      shall be deleted upon the expiration of the applicable retention period.

  - id: EN_NDA_004
    topic: confidentiality_scope
    risk_tier: LOW
    must_fix: false
    triggers:
      any_of:
        - "agreed purpose"
    check_absence_of:
      - definition of "agreed purpose"
    comment: |
      'agreed purpose'가 계약서 내에 명시적으로 정의되어 있지 않으면
      향후 목적 범위에 대한 해석 분쟁이 발생할 수 있다.
      단, 전문에서 협업 목적이 특정되어 있으면 LOW로 유지.

  - id: EN_NDA_005
    topic: no_license
    risk_tier: LOW
    must_fix: false
    triggers:
      any_of:
        - "no license"
        - "shall not claim ownership"
        - "no right or an obligation to conclude"
    positive_flag: true
    comment: |
      NDA 체결 자체가 라이선스나 계약 체결 의무를 부여하지 않음을 명시.
      퍼시스에게 유리한 조항이므로 수정 불필요.
```

---

## 📋 Phase 5: 메인 리뷰 파이프라인 통합

`runtime/review/clause_level.py`의 `build_clause_level_result()` 함수를
아래 구조로 재설계하라. 기존 함수를 완전히 교체하되,
기존 필터 체인(`_apply_zero_hallucination_guardrail` 등)은 유지하고
LLM 분석을 중심으로 재배치하라:

```python
def build_clause_level_result(full_text: str, meta: dict, user_requests: list = None) -> dict:
    """
    [v2.0] LLM 기반 지능형 조항 분석 파이프라인

    실행 순서:
    1. 계약서 언어·유형 탐지
    2. 조항 파싱 (다국어)
    3. [영문 NDA] 룰셋 기반 1차 스크리닝
    4. LLM 기반 조항별 심층 분석 (조항당 1 API 호출)
    5. 필터 체인 적용 (Zero-Hallucination → Domestic → 기타)
    6. Top 3~5 리스크 LLM 종합 판단
    7. 최종 리포트 구조화
    """
    from .clause_parser import parse_clauses, detect_language
    from .meta_extractor import extract_meta
    from ..llm_client import LLMClient
    import json

    llm = LLMClient()
    lang = detect_language(full_text)
    clauses = parse_clauses(full_text)

    # Step 1: 메타데이터 추출
    if not meta or not meta.get("governing_law_country"):
        meta = extract_meta(full_text, llm)

    # Step 2: 조항별 LLM 분석
    clause_results = []
    for clause in clauses:
        # 영문 NDA 룰셋 1차 스크리닝
        rule_hit = _check_en_nda_rules(clause, meta) if lang == "en" else None

        # LLM 심층 분석
        prompt_user = CLAUSE_REVIEW_USER_TEMPLATE.format(
            contract_type=meta.get("contract_type", "NDA"),
            party_a=meta.get("party_a", {}).get("name", ""),
            party_a_country=meta.get("party_a", {}).get("country", ""),
            party_b=meta.get("party_b", {}).get("name", ""),
            party_b_country=meta.get("party_b", {}).get("country", ""),
            fursys_position=meta.get("fursys_position", ""),
            is_international=meta.get("is_international", False),
            is_counterparty_form=meta.get("is_counterparty_form", True),
            governing_law=meta.get("governing_law_country", "불명"),
            jurisdiction=meta.get("jurisdiction_city", "불명"),
            clause_number=clause.number,
            clause_title=clause.title,
            clause_body=clause.body
        )

        raw = llm.complete(CLAUSE_REVIEW_SYSTEM, prompt_user)
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # JSON 파싱 실패 시 재시도
            result = _parse_llm_fallback(raw, clause)

        # 룰셋 결과로 LLM 결과를 보완 (룰셋이 더 엄격한 경우 우선)
        if rule_hit and rule_hit.get("risk_tier") == "HIGH" and result.get("risk_tier") != "HIGH":
            result["risk_tier"] = "HIGH"
            result["rule_override"] = rule_hit.get("id")

        clause_results.append(result)

    # Step 3: 필터 체인
    clause_results = _apply_zero_hallucination_guardrail(clause_results, meta)
    clause_results = _apply_domestic_filter(clause_results, meta)
    clause_results = _apply_clause_integrity_filter(clause_results)
    clause_results = _apply_global_sentence_dedup(clause_results)

    # Step 4: Top 3~5 리스크 LLM 종합 판단
    meta_summary = _format_meta_summary(meta)
    clause_summaries = _format_clause_summaries(clause_results)

    top_risks_raw = llm.complete(
        TOP3_RISK_SYSTEM,
        TOP3_RISK_USER_TEMPLATE.format(
            meta_summary=meta_summary,
            all_clause_summaries=clause_summaries
        )
    )
    try:
        top_risks = json.loads(top_risks_raw)
    except:
        top_risks = {"top_risks": [], "overall_recommendation": "NEGOTIATE_BEFORE_SIGNING"}

    return {
        "meta": meta,
        "clause_results": clause_results,
        "top_risks": top_risks.get("top_risks", []),
        "overall_recommendation": top_risks.get("overall_recommendation"),
        "recommendation_reason": top_risks.get("recommendation_reason"),
        "change_record": _build_change_record(clause_results)
    }
```

---

## 📋 Phase 6: DOCX 출력 포맷 개선

`runtime/review/docx_writer.py`를 찾아 아래 섹션을 추가/수정하라:

### 6-1. 치명적 리스크 Top 3 섹션을 문서 앞부분에 배치

```python
def write_top_risks_section(doc, top_risks: list, overall_recommendation: str):
    """
    치명적 리스크 Top 3~5를 경영진 보고 수준으로 표지 다음에 배치.
    기존 로직: 없거나 형식적 문자열만 출력
    수정 로직: LLM이 생성한 구체적 내용을 표 형태로 출력
    """
    from docx.shared import RGBColor, Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    if not top_risks:
        doc.add_paragraph("치명적 리스크를 자동 선정할 근거가 부족합니다.")
        return

    # 색상 매핑
    severity_colors = {
        "CRITICAL": RGBColor(0xC0, 0x00, 0x00),
        "HIGH": RGBColor(0xE3, 0x6C, 0x09),
    }

    recommendation_labels = {
        "SIGN_AS_IS": "✔ 현행대로 서명 가능",
        "SIGN_WITH_MINOR_CHANGES": "△ 경미한 수정 후 서명",
        "NEGOTIATE_BEFORE_SIGNING": "⚠ 협상 후 서명",
        "DO_NOT_SIGN": "✗ 서명 불가"
    }

    # 종합 권고 헤더
    rec_label = recommendation_labels.get(overall_recommendation, overall_recommendation)
    p = doc.add_paragraph()
    p.add_run(f"종합 권고: {rec_label}").bold = True

    # Top Risk 표
    table = doc.add_table(rows=1, cols=5)
    _set_table_borders(table)
    hdr = table.rows[0].cells
    for i, h in enumerate(["순위", "조항", "리스크 제목", "예상 영향", "권고 조치"]):
        hdr[i].text = h
        hdr[i].paragraphs[0].runs[0].bold = True

    for risk in top_risks:
        row = table.add_row().cells
        row[0].text = str(risk.get("rank", ""))
        row[1].text = str(risk.get("clause_number", ""))
        row[2].text = risk.get("risk_title", "")
        row[3].text = risk.get("financial_impact", "")
        row[4].text = risk.get("recommended_action", "")
```

### 6-2. 조항별 상세 분석 섹션 개선

```python
def write_clause_detail(doc, result: dict):
    """
    조항별 상세 분석을 구조화된 형태로 출력.
    기존: 단순 텍스트 또는 빈 섹션
    수정: worst_case_scenario, negotiation_strategy 포함
    """
    risk_tier = result.get("risk_tier", "NONE")
    if risk_tier == "NONE" or risk_tier == "LOW":
        return  # LOW 이하는 부록에만 표시

    doc.add_heading(
        f"제{result['clause_number']}조 {result.get('clause_title', '')} "
        f"[{risk_tier}]",
        level=3
    )

    # 위험 요약
    doc.add_paragraph(f"【위험 요약】 {result.get('risk_summary', '')}")

    # 최악 시나리오
    worst = result.get("worst_case_scenario")
    if worst:
        doc.add_paragraph(f"【최악 시나리오】 {worst}")

    # 수정안
    rewrite = result.get("suggested_rewrite")
    if rewrite:
        doc.add_paragraph(f"【수정 제안】")
        p = doc.add_paragraph(rewrite)
        p.style = "Quote"

    # 협상 전략
    strategy = result.get("negotiation_strategy")
    if strategy:
        doc.add_paragraph(f"【협상 전략】 {strategy}")
```

---

## 📋 Phase 7: 통합 테스트

### 7-1. 테스트 케이스 파일 생성

```python
# tests/test_nda_review.py (신규 생성)

"""
테스트 케이스: Porsche Design GmbH × Fursys NDA
기대 결과: 아우리봇이 이전에 탐지 실패한 항목들을 정확히 탐지해야 함
"""

NDA_TEXT = """
between
Porsche Design GmbH, Flugplatzstraße 29, 5700 Zell am See, Austria
and
Fursys Inc., 05661 Seoul, 311 Ogeum-Ro, Songpa-Gu, South Korea
...
8. For any disputes arising from or in connection with this confidentiality agreement,
Stuttgart shall be the court of exclusive jurisdiction. German law shall apply.
"""

def test_jurisdiction_detected():
    from runtime.review.clause_level import build_clause_level_result
    result = build_clause_level_result(NDA_TEXT, meta={})
    risks = result["top_risks"]

    # 제8조가 HIGH로 탐지되어야 함
    clause8 = next((r for r in result["clause_results"] if r["clause_number"] == "8"), None)
    assert clause8 is not None, "제8조 파싱 실패"
    assert clause8["risk_tier"] in ("HIGH", "CRITICAL"), f"제8조 리스크 과소평가: {clause8['risk_tier']}"
    assert clause8["topic"] in ("jurisdiction", "governing_law"), f"토픽 오분류: {clause8['topic']}"

def test_top3_not_empty():
    from runtime.review.clause_level import build_clause_level_result
    result = build_clause_level_result(NDA_TEXT, meta={})
    assert len(result["top_risks"]) >= 1, "치명적 리스크 Top 3 선정 실패"
    assert result["top_risks"][0]["risk_title"] != "", "리스크 제목 공란"

def test_domestic_filter_not_applied_for_international():
    from runtime.review.clause_level import build_clause_level_result
    result = build_clause_level_result(NDA_TEXT, meta={})
    # 오스트리아 법인이 상대방이므로 domestic filter가 적용되어서는 안 됨
    clause8 = next((r for r in result["clause_results"] if r["clause_number"] == "8"), None)
    assert clause8 and clause8.get("risk_tier") != "LOW", \
        "국제 거래인데 Domestic Filter가 오작동하여 LOW로 강제됨"

if __name__ == "__main__":
    test_jurisdiction_detected()
    test_top3_not_empty()
    test_domestic_filter_not_applied_for_international()
    print("모든 테스트 통과")
```

### 7-2. 실행 및 검증

```bash
# 환경 설정
cp .env.example .env
# .env에 ANTHROPIC_API_KEY 또는 OPENAI_API_KEY 입력
# LLM_PROVIDER=anthropic 설정

# 의존성 설치
pip install anthropic openai python-docx pyyaml

# 테스트 실행
python -m pytest tests/test_nda_review.py -v

# 실제 NDA로 검토 실행 (CLI가 있는 경우)
python -m runtime.main --input "NDA_Porsche_Fursys.pdf" --output "review_output.docx"
```

---

## ✅ 완료 기준 (Definition of Done)

모든 Phase 완료 후 아래 기준을 만족해야 한다:

| 항목 | 기존 출력 | 목표 출력 |
|------|----------|----------|
| 제8조 준거법·관할 탐지 | ❌ 탐지 없음 | ✅ HIGH 리스크로 탐지 |
| 치명적 리스크 Top 3 | ❌ "근거 부족" 공란 | ✅ 최소 2개 이상 구체적 내용 |
| 수정 제안 문안 | ❌ 없음 | ✅ 영문 대체 문안 제시 |
| 최악 시나리오 | ❌ 없음 | ✅ 구체적 분쟁 시나리오 기술 |
| 협상 전략 | ❌ 없음 | ✅ 3단계 협상 전략 제시 |
| Domestic Filter 오작동 | ❌ 국제 거래 LOW 강제 | ✅ 해외 법인 감지 후 필터 미적용 |
| 영문 조항 파싱 | ❌ "문단 1~4" 형식 탐지 | ✅ "1." 형식 조항 번호 정확 파싱 |
| 종합 서명 권고 | ❌ 없음 | ✅ NEGOTIATE_BEFORE_SIGNING |

---

## 📌 추가 참고사항

**모델 선택 근거:**
- `claude-sonnet-4-20250514`: 법적 추론 능력, 긴 문서 처리, 구조화된 JSON 출력에서
  `gpt-4.1-mini` 대비 월등히 우수. 특히 영문 계약서의 법리 해석에서 차이가 큼.
- `max_tokens=4000`: 조항당 충분한 분석 공간 확보. 기존 1200은 긴 조항 하나도 제대로 처리 불가.

**LLM_PROVIDER 우선순위:**
1. Anthropic Claude (권장) — 법적 추론 품질 최우수
2. OpenAI GPT-4.1 (대안) — Anthropic 키 없을 때 fallback

**비용 추정 (NDA 2쪽, 8개 조항 기준):**
- 조항별 분석 8회 + 메타 추출 1회 + Top3 종합 1회 = 총 10회 API 호출
- Claude Sonnet 기준: 약 $0.05~0.10 / 건 (입력 3만 토큰, 출력 4만 토큰 상한)
