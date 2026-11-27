"""수정 전·후 문구의 낱말 단위 차이 — 화면·검토의견서·변경추적본이 같은 차이를 쓴다.

2026-11-02 지시 4·6항: 원문 전체를 새로 쓴 것처럼 표시하지 말고 실제로 바뀐 부분만 표시한다.
종전 변경추적본은 단락 전체를 삭제하고 새 단락 전체를 삽입해, 한 단어를 고쳐도 조항 전체가 빨갛게 보였다.

segments 는 (op, text) 목록이고 op 는 "=" 유지 · "-" 삭제 · "+" 추가. 유지 조각을 이어 붙이면 수정 전, 삭제를 빼고
추가를 넣으면 수정 후가 된다(그대로 검증 가능한 불변식).
"""
from __future__ import annotations

import difflib
import re

_RX_TOKEN = re.compile(r"\s+|[A-Za-z0-9가-힣]+(?:[’'][A-Za-z]+)?|[^\sA-Za-z0-9가-힣]")

Segment = tuple[str, str]


def _tokens(text: str) -> list[str]:
    return _RX_TOKEN.findall(text or "")


def diff_segments(before: str, after: str) -> list[Segment]:
    """낱말 단위 차이. 바뀐 낱말 사이에 낀 공백·한 글자 유지 조각은 바뀐 덩어리에 합친다(읽기 쉽게)."""
    a, b = _tokens(before), _tokens(after)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    raw: list[Segment] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            raw.append(("=", "".join(a[i1:i2])))
        else:
            if i2 > i1:
                raw.append(("-", "".join(a[i1:i2])))
            if j2 > j1:
                raw.append(("+", "".join(b[j1:j2])))
    # 바뀐 덩어리 사이의 짧은 유지 조각(공백·구두점·낱말 하나)은 양쪽에 넣어 하나의 교체로 보이게 한다.
    merged: list[Segment] = []
    i = 0
    while i < len(raw):
        op, txt = raw[i]
        if (op == "=" and merged and merged[-1][0] != "=" and i + 1 < len(raw) and raw[i + 1][0] != "="
                and len(_tokens(txt)) <= 2 and len(txt) <= 12):
            # 앞뒤 변경에 끼운다: 삭제 쪽·추가 쪽 모두에 유지 조각을 넣는다.
            _absorb(merged, txt)
            i += 1
            continue
        merged.append((op, txt))
        i += 1
    return _coalesce(merged)


def _absorb(merged: list[Segment], txt: str) -> None:
    # 마지막 유지 조각 뒤의 변경 구간 안에서만 찾는다 — 그보다 앞의 변경에 붙이면 문장 순서가 뒤바뀐다.
    start = max((k for k in range(len(merged)) if merged[k][0] == "="), default=-1) + 1
    dels = [k for k in range(len(merged) - 1, start - 1, -1) if merged[k][0] == "-"]
    adds = [k for k in range(len(merged) - 1, start - 1, -1) if merged[k][0] == "+"]
    if dels:
        k = dels[0]
        merged[k] = ("-", merged[k][1] + txt)
    else:
        merged.append(("-", txt))
    if adds:
        k = adds[0]
        merged[k] = ("+", merged[k][1] + txt)
    else:
        merged.append(("+", txt))


def _coalesce(segs: list[Segment]) -> list[Segment]:
    """같은 종류가 이어지면 합치고, 한 변경 구간 안에서는 삭제를 추가보다 앞에 둔다."""
    out: list[Segment] = []
    run: list[Segment] = []

    def flush() -> None:
        if not run:
            return
        d = "".join(t for o, t in run if o == "-")
        p = "".join(t for o, t in run if o == "+")
        if d:
            out.append(("-", d))
        if p:
            out.append(("+", p))
        run.clear()

    for op, txt in segs:
        if not txt:
            continue
        if op == "=":
            flush()
            if out and out[-1][0] == "=":
                out[-1] = ("=", out[-1][1] + txt)
            else:
                out.append(("=", txt))
        else:
            run.append((op, txt))
    flush()
    return out


def before_text(segs: list[Segment]) -> str:
    return "".join(t for o, t in segs if o in ("=", "-"))


def after_text(segs: list[Segment]) -> str:
    return "".join(t for o, t in segs if o in ("=", "+"))


def changed_ratio(segs: list[Segment]) -> float:
    total = sum(len(t) for o, t in segs if o in ("=", "-")) or 1
    return sum(len(t) for o, t in segs if o == "-") / total


__all__ = ["Segment", "after_text", "before_text", "changed_ratio", "diff_segments"]
