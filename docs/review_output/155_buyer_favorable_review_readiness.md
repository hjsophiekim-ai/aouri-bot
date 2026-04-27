# 155) buyer_favorable Review Readiness 최종 판정

평가 기준:
1) 당사 보호 방향으로 검토하는가  
2) 계약유형별로 질문이 달라지는가  
3) 조항 매핑이 정확한가  
4) 적용 법령이 계약유형과 맞는가  
5) 수정문안이 clause-specific하고 실무적으로 타당한가  
6) Word redline이 실제 법무 검토용으로 쓸 만한가

---

## 현재 상태(코드/테스트 + LG 픽스처 재검증 기준)

1) 당사 보호 방향(POSTURE)
- 구매+설치/시운전 계약에서 `buyer_favorable`가 기본으로 설정됨
- `party_role.our_role=buyer`로 명시됨

2) 질문 다양성
- 설치/현장 작업 컨텍스트에서 `재위탁 사전 승인/안전 책임`, `검수/인수` 류 질문이 생성되도록 강화

3) 조항 매핑 정확성
- clause_id 중복 방지(disambiguate)
- clause_title mismatch 발견 시 출력 전에 block 처리
- article_number를 보존/표기하여 매핑 가독성 강화

4) 법령 정합성
- purchase_installation 프로파일에서 민법/상법/산안법/중대재해/제조물책임 중심 토픽 우선
- 대리점법 계열 토픽은 기본 억제

5) rewrite 정밀성
- buyer_favorable에서 “상호주의”보다 “당사 리스크 감소” 중심 문구로 분기
- 패턴 미매칭에도 최소 변경으로 clause-specific rewrite 생성 보장
- 이미 유리한 안전조항은 불필요 수정 방지

6) Word redline
- 토큰/구두점 단위 diff로 granularity 개선
- insert=빨강, delete=빨강+취소선, unchanged=기본색 유지

---

## 미검증(실제 LG 원본 docx 필요)

다음 항목은 “실제 LG 계약서 docx(Track Changes 포함)” 파일이 작업 디렉터리에 없어 end-to-end로 완결 검증하지 못했습니다.
- 실제 docx 업로드 → 추출 결과가 완전히 깨끗한지
- 실제 계약서 조항 구조가 충분히 잘 분해되는지(표/머리말/각주 포함)
- 실제 docx 생성본을 Word로 열었을 때 레이아웃/줄바꿈/표 너비가 적절한지

---

## 최종 판정

- 판정: **부분 도달**
  - 엔진 레벨에서 posture/identity/grounding/rewrite/redline 개선은 구현 및 자동 테스트로 검증됨
  - 다만, 실제 LG 원본 docx 기반 end-to-end 검증(업로드→추출→검토→다운로드) 결과가 없어서 “실사용 가능” 판정은 유보

