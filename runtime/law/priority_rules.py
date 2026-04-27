from __future__ import annotations


ENTITY_PRIORITY_TOPICS: dict[str, list[str]] = {
    "퍼시스": ["대리점법", "하도급법", "공정거래", "중대재해처벌법", "산업안전보건법"],
    "시디즈": ["대리점법", "하도급법", "공정거래", "중대재해처벌법", "산업안전보건법", "제조물", "품질"],
    "일룸": ["대리점법", "표시광고", "소비자보호", "모델계약", "하도급법", "중대재해처벌법"],
    "바로스": ["특수관계인", "물류", "설치", "중대재해처벌법", "산업안전보건법", "하도급법"],
    "Fursys Vietnam": ["생산이관", "기술자료", "하도급법", "공정거래", "현지 생산 리스크"],
    "Sidiz America": ["현지 판매", "딜러", "소비자보호", "보증", "광고"],
    "Fursys America": ["현지 판매", "딜러", "소비자보호", "보증", "광고"],
    "Iloom Taiwan": ["현지 판매", "딜러", "소비자보호", "보증", "광고"],
}


def get_priority_topics(entity: str) -> list[str]:
    e = (entity or "").strip()
    if not e:
        return []
    if "Sidiz" in e and "America" in e:
        return list(ENTITY_PRIORITY_TOPICS["Sidiz America"])
    if "Fursys" in e and "America" in e:
        return list(ENTITY_PRIORITY_TOPICS["Fursys America"])
    if "Iloom" in e and "Taiwan" in e:
        return list(ENTITY_PRIORITY_TOPICS["Iloom Taiwan"])
    if "Vietnam" in e:
        return list(ENTITY_PRIORITY_TOPICS["Fursys Vietnam"])
    for k in ("퍼시스", "시디즈", "일룸", "바로스"):
        if k in e:
            return list(ENTITY_PRIORITY_TOPICS[k])
    return []


def get_priority_topics_with_context(*, entity: str, contract_type: str, text: str) -> list[str]:
    topics = get_priority_topics(entity)
    ct = contract_type or ""
    t = text or ""
    app_dev_hint = any(k in ct for k in ("앱개발", "소프트웨어개발", "SI", "유지보수", "SaaS", "API")) or any(
        k in t for k in ("앱 개발", "소프트웨어 개발", "시스템 개발", "개발 용역", "소스코드", "산출물", "SLA", "유지보수", "오픈소스", "API 연동")
    )
    dealer_hint = any(k in ct for k in ("대리점", "유통", "위탁")) or any(k in t for k in ("대리점", "위탁판매", "판매장려금", "판촉", "리베이트"))
    if app_dev_hint:
        topics = [x for x in topics if x not in ("표시광고", "소비자보호", "모델계약", "대리점법")]
        topics = ["민법 도급 손해배상", "저작권법", "부정경쟁방지법", "개인정보보호법"] + topics
    if not dealer_hint and "대리점법" in topics:
        topics = [x for x in topics if x != "대리점법"]
    return topics

