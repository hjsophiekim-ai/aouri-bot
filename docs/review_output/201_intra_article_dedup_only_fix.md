# 201) 같은 조문군(조/항) 내부에서만 dedup 수행
 
## 의도(사용자 요구)
 
- 예: `제20조 제1/2/3항`처럼 같은 조문군에서 유사한 수정문안이 반복될 때만 1회 대표 반영
- `제2조 기본원칙` 같은 성격이 다른 조항을 다른 조항에 흡수하지 않기
 
## 적용
 
- dedup 그룹 키에 `article_number`(조 번호)를 포함시켜 **동일 조문군 내부에서만** 통합이 가능하도록 제한
- `article_number`가 없는 조항은 dedup 제외
- (가능한 경우) `paragraph_number`가 너무 멀면(±2 초과) dedup 제외하여 “인접한 유사 조항”에만 적용
- keep_as_is 조항은 dedup 대상에서 제외
 
## 구현 위치
 
- [clause_level.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/review/clause_level.py)
 
