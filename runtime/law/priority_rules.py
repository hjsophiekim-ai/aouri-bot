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

