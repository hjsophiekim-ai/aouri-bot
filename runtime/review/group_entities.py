"""퍼시스그룹 계열사 registry — 계약 당사자 중 **어느 쪽이 우리인가**의 단일 출처.

2026-09-11 지시 — 아래 회사를 퍼시스그룹 계열사이자 검토의 "우리 회사 측"으로
인식할 것. 바로스는 **레터스**로 상호가 변경되었으므로 현재 법인명은 레터스이되,
체결 당시 법인명이 바로스였던 문서는 그 명칭을 보존하고 동일성 여부를 확인한다.

왜 데이터로 두는가
────────────────
회사명을 검토 로직 곳곳에 흩어 두면 계열사가 늘거나 상호가 바뀔 때마다 여러
모듈이 어긋난다. 실제로 `statute_applicability_gate` 는 "바로스"를, `classify`
는 또 다른 표기를 각자 들고 있었다. 상호 변경은 **앞으로도 일어날 일**이므로
표 하나만 고치면 끝나는 구조로 모은다.

이름을 안다고 법인격을 아는 것은 아니다
──────────────────────────────────
이 표는 "우리 편인가"를 판단할 뿐, 계약 당사자의 **법적 명칭**을 단정하지
않는다. 세 가지는 반드시 사실확인으로 넘긴다.

  · 레터스/바로스 — 같은 법인의 변경 전·후 명칭인지 문서 일자·등기로 가린다.
  · 해외법인 — 정확한 영문 법인명과 당사자성을 별도로 확인한다.

계열사 간 계약과 외부 제3자 계약도 구분한다. 양쪽 모두 우리 그룹이면 협상
기준을 기계적으로 적용하지 않고 이해상충 관점으로 본다.

브랜드·그룹명은 계약 당사자가 될 수 없다 (2026-09-29 지시)
─────────────────────────────────────────────────
  · 알로소는 주식회사 시디즈의 브랜드다 — "주식회사 알로소"는 틀린 표현이다.
  · 슬로우는 주식회사 일룸의 브랜드다 — "주식회사 슬로우"는 틀린 표현이다.
  · 데스커도 주식회사 일룸의 브랜드다 — "주식회사 데스커"는 틀린 표현이다.
    (그래서 데스커는 별도 계열사가 아니라 일룸 항목의 브랜드로 둔다.)
  · 퍼시스그룹(FURSYS GROUP)은 법적 엔터티가 아니다 — 당사자로 쓰였으면
    실제 계약 주체 법인(기본: 주식회사 퍼시스)으로 고친다.
브랜드명 자체(상품·매장 표기)는 틀린 것이 아니다. 법인격 표기가 붙거나
당사자 자리에 쓰였을 때만 고친다 — 그 판단은 `entity_name_correction` 이 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: 계열사의 성격. 협상기준과 사실확인 항목이 달라진다.
KIND_OPERATING = "operating"
KIND_HOLDING = "holding"
KIND_OVERSEAS = "overseas"

#: 그룹 기본 업(業) 도메인. `statute_applicability_gate.DOMAIN_LABELS` 의 키와
#: 같은 어휘를 쓴다(문자열로만 참조해 순환 import 를 피한다).
_FURNITURE = frozenset({
    "manufacturing", "furniture_manufacturing", "furniture_sales",
    "installation_service", "logistics",
})
_LOGISTICS_INSTALL = frozenset({"installation_service", "logistics"})


@dataclass(frozen=True)
class GroupEntity:
    """계열사 한 곳."""

    key: str
    name: str
    aliases: tuple[str, ...] = ()
    former_names: tuple[str, ...] = ()
    kind: str = KIND_OPERATING
    business_domains: frozenset[str] = field(default_factory=lambda: _FURNITURE)
    #: 계약서상 법적 당사자 명칭을 별도로 확인해야 하는가.
    verify_legal_name: bool = False
    note: str = ""
    #: 계약서에 적어야 하는 법적 당사자 명칭. 모르면 비워 둔다(추측 금지).
    legal_name_ko: str = ""
    legal_name_en: str = ""
    #: 이 법인의 브랜드. 브랜드는 법인이 아니므로 "주식회사 <브랜드>" 는 틀린
    #: 표현이다 — `entity_name_correction` 이 이 법인명으로 고친다.
    brands: tuple[str, ...] = ()
    brands_en: tuple[str, ...] = ()

    def all_names(self) -> tuple[str, ...]:
        # 영문 브랜드("SLOU")는 넣지 않는다 — 정규화 후 부분일치라 "slouch" 같은
        # 일반 단어에 걸린다. 한글 브랜드는 우리 편 인식에 쓴다.
        return (
            (self.name,) + tuple(self.aliases) + tuple(self.former_names)
            + tuple(self.brands)
        )


#: 퍼시스그룹 계열사. 상호가 바뀌면 **이 표만** 고친다.
GROUP_ENTITIES: tuple[GroupEntity, ...] = (
    GroupEntity(
        key="fursys", name="퍼시스",
        aliases=("퍼시스 주식회사", "주식회사 퍼시스", "Fursys", "FURSYS"),
        legal_name_ko="주식회사 퍼시스", legal_name_en="Fursys Inc.",
    ),
    GroupEntity(
        key="iloom", name="일룸",
        # 영문 "Desker" 는 일반 단어와 겹치지 않아 우리 편 인식에 그대로 쓴다.
        aliases=("일룸 주식회사", "주식회사 일룸", "iloom", "ILOOM", "Desker", "DESKER"),
        legal_name_ko="주식회사 일룸", legal_name_en="Iloom Inc.",
        brands=("슬로우", "데스커"), brands_en=("SLOU", "DESKER"),
    ),
    GroupEntity(
        key="sidiz", name="시디즈",
        aliases=("시디즈 주식회사", "주식회사 시디즈", "SIDIZ", "Sidiz"),
        legal_name_ko="주식회사 시디즈", legal_name_en="Sidiz Inc.",
        brands=("알로소",), brands_en=("ALLOSO",),
    ),
    GroupEntity(
        key="letus", name="레터스",
        aliases=("레터스 주식회사", "주식회사 레터스", "Letus", "LETUS"),
        former_names=("바로스", "주식회사 바로스", "Baros", "BAROS"),
        business_domains=_LOGISTICS_INSTALL,
        verify_legal_name=True,
        note="구 상호 '바로스'. 체결일 기준 명칭을 보존하고 법인 동일성을 확인한다.",
    ),
    GroupEntity(
        key="purple6", name="퍼플식스",
        aliases=("퍼플식스 주식회사", "주식회사 퍼플식스",
                 "퍼플6", "Purple6", "PURPLE6", "Purple Six"),
        verify_legal_name=True,
        note="영위 업종이 확인되지 않았다. 하도급법 업(業) 판단 전 사실확인이 필요하다.",
    ),
    GroupEntity(
        key="fursys_holdings", name="퍼시스 지주",
        aliases=("퍼시스지주", "퍼시스홀딩스", "퍼시스 홀딩스", "Fursys Holdings"),
        kind=KIND_HOLDING,
    ),
    GroupEntity(
        key="iloom_holdings", name="일룸 지주",
        aliases=("일룸지주", "일룸홀딩스", "일룸 홀딩스", "iloom Holdings"),
        kind=KIND_HOLDING,
    ),
    GroupEntity(
        key="fursys_vietnam", name="퍼시스 베트남",
        aliases=("퍼시스베트남", "Fursys Vietnam", "FURSYS VIETNAM"),
        kind=KIND_OVERSEAS, verify_legal_name=True,
        note="해외법인. 정확한 영문 법인명과 당사자성을 별도로 확인한다.",
    ),
    GroupEntity(
        key="sidiz_america", name="시디즈 아메리카",
        aliases=("시디즈아메리카", "SIDIZ America", "Sidiz America"),
        kind=KIND_OVERSEAS, verify_legal_name=True,
        note="해외법인. 정확한 영문 법인명과 당사자성을 별도로 확인한다.",
    ),
    GroupEntity(
        key="fursys_america", name="퍼시스 아메리카",
        aliases=("퍼시스아메리카", "Fursys America", "FURSYS AMERICA"),
        kind=KIND_OVERSEAS, verify_legal_name=True,
        note="해외법인. 정확한 영문 법인명과 당사자성을 별도로 확인한다.",
    ),
    GroupEntity(
        key="iloom_taiwan", name="일룸 타이완",
        aliases=("일룸타이완", "일룸 대만", "iloom Taiwan", "ILOOM TAIWAN"),
        kind=KIND_OVERSEAS, verify_legal_name=True,
        note="해외법인. 정확한 영문 법인명과 당사자성을 별도로 확인한다.",
    ),
)

_BY_KEY: dict[str, GroupEntity] = {e.key: e for e in GROUP_ENTITIES}

#: 그룹 자체의 명칭. 법적 엔터티가 아니므로 계약 당사자가 될 수 없다.
GROUP_NAMES_KO: tuple[str, ...] = ("퍼시스그룹", "퍼시스 그룹")
GROUP_NAMES_EN: tuple[str, ...] = ("FURSYS GROUP", "Fursys Group")
#: 그룹명이 당사자로 쓰였는데 실제 계약 주체를 특정할 수 없을 때의 기본값.
DEFAULT_GROUP_PARTY_KEY = "fursys"


def entity_by_key(key: str) -> GroupEntity | None:
    return _BY_KEY.get(key)

#: 공백·괄호·법인격 표기를 지운 형태로 맞춘다("(주) 퍼시스" == "퍼시스").
_RX_NOISE = re.compile(
    r"주식회사|㈜|\(\s*주\s*\)|Co\.|Ltd\.?|Inc\.?|[\s()（）.,\-_·ㆍ]",
    re.IGNORECASE,
)


def _norm(value: str | None) -> str:
    return _RX_NOISE.sub("", str(value or "")).lower()


#: 긴 이름부터 맞춘다 — "퍼시스지주"가 "퍼시스"로 먼저 잡히면 안 된다.
_NORM_INDEX: tuple[tuple[str, GroupEntity], ...] = tuple(
    sorted(
        {
            (_norm(n), e)
            for e in GROUP_ENTITIES
            for n in e.all_names()
            if len(_norm(n)) >= 2
        },
        key=lambda pair: -len(pair[0]),
    )
)


def resolve_entity(name: str | None) -> GroupEntity | None:
    """회사명(현재명·구명·영문·브랜드 무관)을 계열사로 해석한다."""
    norm = _norm(name)
    if not norm:
        return None
    # 정방향(입력이 등록명을 포함)만 본다. 역방향까지 허용하면 "퍼시스"가
    # 더 긴 "퍼시스아메리카"에 먼저 걸려 해외법인으로 잘못 해석된다.
    for key, entity in _NORM_INDEX:
        if key in norm:
            return entity
    return None


def is_group_entity(name: str | None) -> bool:
    """이 이름이 우리 그룹 계열사인가."""
    return resolve_entity(name) is not None


def entity_business_domains(name: str | None) -> frozenset[str] | None:
    """그 계열사가 업으로 영위하는 도메인. 계열사가 아니면 None."""
    entity = resolve_entity(name)
    return entity.business_domains if entity else None


def find_group_entities(text: str | None) -> list[GroupEntity]:
    """계약 본문에 등장하는 계열사를 긴 이름 우선으로 뽑는다."""
    norm_body = _norm(text)
    if not norm_body:
        return []
    found: list[GroupEntity] = []
    seen: set[str] = set()
    for key, entity in _NORM_INDEX:
        if entity.key in seen or not key:
            continue
        if key in norm_body:
            seen.add(entity.key)
            found.append(entity)
    return found


def our_side_labels(
    text: str | None = None, *, entity: str | None = None
) -> tuple[str, ...]:
    """우리 쪽을 가리키는 호칭 — 방향 판단(`clause_direction`)에 넘긴다.

    계약서는 당사자를 회사명·브랜드·구 상호로 부른다. 본문에 등장하는 계열사의
    **모든 표기**를 우리 호칭으로 인정해야 "갑/을"이 없는 계약에서도 방향이
    나온다.
    """
    labels: list[str] = []
    seen: set[str] = set()

    def _add(item: GroupEntity) -> None:
        for name in item.all_names():
            if len(name) >= 2 and name not in seen:
                seen.add(name)
                labels.append(name)

    named = resolve_entity(entity)
    if named is not None:
        _add(named)
    for found in find_group_entities(text):
        if named is None or found.key != named.key:
            _add(found)
    return tuple(labels)


def is_intra_group(text: str | None, *, entity: str | None = None) -> bool:
    """계열사 **간** 계약인가 — 서로 다른 계열사 둘 이상이 당사자로 보이는가.

    계열사 간 거래는 외부 제3자 거래와 협상기준이 다르다(이해상충·내부거래).
    자동으로 판단을 바꾸지는 않고, 사실확인 항목으로만 올린다.
    """
    keys = {e.key for e in find_group_entities(text)}
    named = resolve_entity(entity)
    if named is not None:
        keys.add(named.key)
    return len(keys) >= 2


def entity_advisories(
    text: str | None = None, *, entity: str | None = None
) -> list[dict[str, str]]:
    """법인격·명칭에 관해 사람이 확인해야 할 항목."""
    entities: list[GroupEntity] = []
    seen: set[str] = set()
    named = resolve_entity(entity)
    if named is not None:
        entities.append(named)
        seen.add(named.key)
    for found in find_group_entities(text):
        if found.key not in seen:
            seen.add(found.key)
            entities.append(found)

    body = str(text or "")
    advisories: list[dict[str, str]] = []
    for item in entities:
        # 브랜드는 법인이 아니다. 본문에 브랜드가 보이면 계약 당사자 법인을
        # 알려 둔다 — 법인격 표기가 붙은 오기 자체는 `entity_name_correction`
        # 이 finding 으로 고친다 (2026-09-29 지시).
        for brand in item.brands:
            if brand in body and item.legal_name_ko:
                _last = item.legal_name_ko[-1]
                _code = ord(_last) - 0xAC00 if "가" <= _last <= "힣" else 0
                # 받침이 없거나 ㄹ 받침이면 "로", 그 밖의 받침이면 "으로".
                _ro = "로" if _code % 28 in (0, 8) else "으로"
                advisories.append({
                    "entity": brand,
                    "kind": "brand",
                    "detail": (
                        f"{brand}는 {item.legal_name_ko}의 브랜드이며 법인이 아닙니다. "
                        f"계약 당사자 법인명은 {item.legal_name_ko}{_ro} 적어야 합니다."
                    ),
                })
        if not item.verify_legal_name:
            continue
        detail = item.note
        if item.former_names and any(fn in body for fn in item.former_names):
            detail = (
                f"본문에 구 상호({item.former_names[0]})가 등장합니다. 현재 법인명은 "
                f"{item.name}입니다. 체결 당시 명칭은 그대로 보존하되, 등기부상 "
                "법인 동일성(상호 변경인지 별개 법인인지)을 확인하십시오."
            )
        advisories.append({
            "entity": item.name,
            "kind": item.kind,
            "detail": detail,
        })
    if is_intra_group(text, entity=entity):
        advisories.append({
            "entity": "계열사 간 거래",
            "kind": "intra_group",
            "detail": (
                "양 당사자가 모두 퍼시스그룹 계열사로 보입니다. 외부 제3자 거래와 "
                "동일한 협상기준을 기계적으로 적용하지 말고, 내부거래·이해상충 "
                "관점(거래조건의 정상성, 지원행위 해당 여부)에서 확인하십시오."
            ),
        })
    return advisories
