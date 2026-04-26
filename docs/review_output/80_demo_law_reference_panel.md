# /demo 화면: 법령/판례 검색 결과 노출

요구사항:
- 결과 화면에서 관련 법령/판례/해석례를 볼 수 있게
- 너무 복잡하지 않게
- 대표 3~5개 요약 노출 + 더보기(접기/펼치기)

---

## 구현 방식(MVP)

- `/api/review/analyze`가 반환하는 `law_search`를 `/demo` 결과 상세(접기/펼치기) 영역에 포함했습니다.
- UI 위치: 결과 화면 “상세 보기” 내부에 `관련 법령/판례/해석례` 섹션을 추가하고 JSON을 노출합니다.

코드 위치:
- UI: [internal_demo_chat_ui.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/admin/internal_demo_chat_ui.py)
- API: [server.py](file:///c:/Users/FURSYS/Desktop/aouribot/aouri-bot/runtime/api/server.py)

---

## 향후 개선(후순위)

- 현재는 JSON 노출 형태(빠른 시연 목적)
- 다음 단계에서 카드형 “대표 3~5개” 요약 UI를 추가하고, `drf_detail_url` 링크를 버튼으로 제공 가능

