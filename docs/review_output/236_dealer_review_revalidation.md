# 236. Dealer review 재검증(시디즈 대리점 계약)

- 입력 DOCX: C:\Users\FURSYS\Downloads\☆ 시디즈 26년 대리점(권역) 계약서 검토(법무팀).docx
- review_focus: 대리점법상 불이익 제공 / 거래상 지위 남용 / 경영간섭(영업자율 침해) / 계약해지(물량축소·공급중단·불이익조치) 남용
- 실행 시간: 0.073s

## 체크 결과
- 사용자 요청 이슈 매핑 존재: OK
- 핵심 조항이 제27보다 우선 노출: OK
- 핵심 조항 redline candidate 생성(제21/23/14/11/17): OK
- UI/Word canonical set(변경 조항 집합 일치): OK

## 핵심 조항 포함 여부
- 제21조 포함: OK (index=0)
- 제23조 포함: OK (index=31)
- 제14조 포함: OK (index=22)
- 제11조 포함: OK (index=50)
- 제17조 포함: OK (index=56)
- 제8조 포함: OK (index=72)
- 제9조 포함: OK (index=51)
- 제10조 포함: OK (index=71)
- 제27조 포함: OK (index=87)

## user_focus 매핑 요약(code → clause_ids)
- dealer_management_interference: KR-21-p11, KR-21-p2, KR-21-p3, KR-21-p6, KR-21-p8, KR-21-p9, KR-2-p1, KR-2-p3, KR-2-p4, KR-3-p1-i1…
- dealer_unfair_disadvantage: KR-21-p11, KR-21-p2, KR-21-p3, KR-21-p4, KR-21-p6, KR-21-p7, KR-21-p8, KR-21-p9, KR-21-p1, KR-21-p10…
- termination_abuse: KR-21-p11, KR-21-p2, KR-21-p3, KR-21-p4, KR-21-p6, KR-21-p8, KR-21-p9, KR-21-p12, KR-21-p5, KR-2-p1…

## 변경 조항 집합(일관성)
- expected_changed_count(meta): 63
- actual_changed_count(has_rewrite_change): 63
