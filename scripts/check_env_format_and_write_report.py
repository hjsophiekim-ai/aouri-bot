from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KeyCheck:
    key: str
    line_present: bool
    value_nonempty: bool
    has_quotes: bool
    has_inline_comment: bool
    raw_has_leading_bom: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_bytes(p: Path) -> bytes:
    try:
        return p.read_bytes()
    except Exception:
        return b""


def _detect_line_endings(b: bytes) -> str:
    if b"\r\n" in b:
        if b"\n" in b.replace(b"\r\n", b""):
            return "mixed"
        return "crlf"
    if b"\n" in b:
        return "lf"
    return "unknown"


def _decode_text(b: bytes) -> tuple[str, bool, bool]:
    has_bom = b.startswith(b"\xef\xbb\xbf")
    try:
        text = b.decode("utf-8-sig")
        return text, has_bom, True
    except Exception:
        try:
            text = b.decode("utf-8", errors="replace")
            return text, has_bom, False
        except Exception:
            return "", has_bom, False


def _check_key(text: str, key: str) -> KeyCheck:
    pat = re.compile(rf"^\s*(export\s+)?(?P<k>\ufeff?{re.escape(key)})\s*=\s*(?P<v>.*)\s*$", re.MULTILINE)
    m = pat.search(text)
    if not m:
        return KeyCheck(key=key, line_present=False, value_nonempty=False, has_quotes=False, has_inline_comment=False, raw_has_leading_bom=False)
    raw_k = m.group("k") or ""
    raw_v = m.group("v") or ""
    raw_has_leading_bom = raw_k.startswith("\ufeff")
    v = raw_v.strip()
    has_quotes = (len(v) >= 2) and ((v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")))
    if has_quotes:
        v2 = v[1:-1].strip()
    else:
        v2 = v.split("#", 1)[0].strip() if "#" in v else v
    has_inline_comment = ("#" in v) and not has_quotes
    value_nonempty = bool(v2)
    return KeyCheck(
        key=key,
        line_present=True,
        value_nonempty=value_nonempty,
        has_quotes=has_quotes,
        has_inline_comment=has_inline_comment,
        raw_has_leading_bom=raw_has_leading_bom,
    )


def main() -> None:
    root = _repo_root()
    env_path = root / ".env"
    env_local_path = root / ".env.local"

    b = _read_bytes(env_path)
    text, has_bom, utf8_ok = _decode_text(b)
    endings = _detect_line_endings(b)

    openai = _check_key(text, "OPENAI_API_KEY")
    law_key = _check_key(text, "LAW_API_KEY")
    law_enabled = _check_key(text, "LAW_API_ENABLED")

    local_exists = env_local_path.exists()
    local_b = _read_bytes(env_local_path) if local_exists else b""
    local_text, local_has_bom, local_utf8_ok = _decode_text(local_b) if local_exists else ("", False, True)
    local_openai = _check_key(local_text, "OPENAI_API_KEY") if local_exists else None
    local_law_key = _check_key(local_text, "LAW_API_KEY") if local_exists else None

    lines: list[str] = []
    lines.append("# .env 형식 자동 점검(117)")
    lines.append("")
    lines.append("## 1) .env 파일 존재 여부")
    lines.append(f"- `.env` exists: `{str(bool(env_path.exists())).lower()}`")
    lines.append(f"- `.env.local` exists: `{str(bool(local_exists)).lower()}`")
    lines.append("")
    lines.append("## 2)~5) 키 라인/값 점검(값 미출력)")
    for ck in (openai, law_key, law_enabled):
        lines.append(f"- `{ck.key}` in .env: line_present=`{str(bool(ck.line_present)).lower()}`, value_nonempty=`{str(bool(ck.value_nonempty)).lower()}`")
    if local_exists and local_openai and local_law_key:
        lines.append(f"- `OPENAI_API_KEY` in .env.local: line_present=`{str(bool(local_openai.line_present)).lower()}`, value_nonempty=`{str(bool(local_openai.value_nonempty)).lower()}`")
        lines.append(f"- `LAW_API_KEY` in .env.local: line_present=`{str(bool(local_law_key.line_present)).lower()}`, value_nonempty=`{str(bool(local_law_key.value_nonempty)).lower()}`")
    lines.append("")
    lines.append("## 형식/인코딩 이슈 점검")
    lines.append(f"- .env utf-8 decode ok: `{str(bool(utf8_ok)).lower()}`")
    lines.append(f"- .env BOM detected: `{str(bool(has_bom)).lower()}`")
    lines.append(f"- .env line endings: `{endings}`")
    lines.append(f"- OPENAI_API_KEY key has leading BOM: `{str(bool(openai.raw_has_leading_bom)).lower()}`")
    lines.append(f"- LAW_API_KEY key has leading BOM: `{str(bool(law_key.raw_has_leading_bom)).lower()}`")
    lines.append(f"- OPENAI_API_KEY has quotes: `{str(bool(openai.has_quotes)).lower()}` / has inline comment: `{str(bool(openai.has_inline_comment)).lower()}`")
    lines.append(f"- LAW_API_KEY has quotes: `{str(bool(law_key.has_quotes)).lower()}` / has inline comment: `{str(bool(law_key.has_inline_comment)).lower()}`")
    if local_exists:
        lines.append("")
        lines.append("## .env.local 형식/인코딩 이슈 점검")
        lines.append(f"- .env.local utf-8 decode ok: `{str(bool(local_utf8_ok)).lower()}`")
        lines.append(f"- .env.local BOM detected: `{str(bool(local_has_bom)).lower()}`")
    lines.append("")
    lines.append("## 자동 수정 제안(값은 예시로만 표기)")
    lines.append("- 파일 시작에 BOM이 있으면 제거(UTF-8 without BOM 저장 권장)")
    lines.append("- 키 라인을 아래 형태로 맞추기(공백 최소화)")
    lines.append("  - `OPENAI_API_KEY=<YOUR_KEY>`")
    lines.append("  - `LAW_API_ENABLED=true`")
    lines.append("  - `LAW_API_KEY=<YOUR_KEY>`")
    lines.append("")

    out_path = root / "docs" / "review_output" / "117_env_format_check.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

