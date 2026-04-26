import csv
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_DIR = Path(__file__).resolve().parent
EXTRACT_DIR = REVIEW_DIR / "02_extracted_texts"
LOG_CSV = REVIEW_DIR / "02_extraction_log.csv"

OUT_02A = REVIEW_DIR / "02a_contract_text_extraction_status.md"
OUT_02B = REVIEW_DIR / "02b_contract_text_samples.md"
OUT_VERIFIED = REVIEW_DIR / "02_contract_common_patterns_verified.md"
OUT_STD_SUMMARY = REVIEW_DIR / "01_standard_contract_summary.md"


def norm_ws(s: str) -> str:
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def korean_ratio(s: str) -> float:
    if not s:
        return 0.0
    ko = len(re.findall(r"[\uAC00-\uD7A3]", s))
    en = len(re.findall(r"[A-Za-z]", s))
    return ko / max(1, ko + en)


def text_quality(text: str) -> tuple[str, str]:
    t = text or ""
    length = len(t)
    if length < 50:
        return "FAILED", "text_too_short"
    if length < 300:
        return "UNCONFIRMED", "very_short"
    if length < 1200:
        return "UNCONFIRMED", "short"
    if re.search(r"<w:t|</w:t|<[^>]+>", t):
        return "UNCONFIRMED", "xml_artifacts"
    return "CONFIRMED", "ok"


def load_log_rows() -> list[dict]:
    rows = []
    with LOG_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def safe_read_text(path: Path) -> str:
    return norm_ws(path.read_text(encoding="utf-8", errors="replace"))


def is_standard_rel(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").startswith("docs/Standard Contract/")


def is_contract_rel(rel_path: str) -> bool:
    return rel_path.replace("\\", "/").startswith("docs/Contract/")


CONTRACT_TYPE_RULES = [
    ("NDA/비밀유지", [r"\bNDA\b", r"Non[- ]Disclosure", r"비밀유지", r"confidentiality"]),
    ("개인정보/처리위탁(DPA)", [r"개인정보", r"처리위탁", r"privacy", r"data processing", r"\bDPA\b"]),
    ("임대차/전대차", [r"임대차", r"전대차", r"\blease\b", r"\bsublease\b"]),
    ("물품공급/구매/매매", [r"물품공급", r"구매", r"매매", r"\bsupply\b", r"\bpurchase\b", r"\bsales contract\b"]),
    ("대리점/위탁/유통", [r"대리점", r"위탁", r"위탁거래", r"\bdealer\b", r"\bdistributor\b", r"\bconsignment\b"]),
    ("용역/자문/SOW", [r"용역", r"자문", r"컨설팅", r"\bSOW\b", r"Statement of Work", r"\bengagement\b", r"\bservice agreement\b"]),
    ("광고/마케팅/협찬", [r"광고", r"마케팅", r"대행", r"협찬", r"sponsorship", r"advertising", r"marketing"]),
    ("라이선스/로열티", [r"라이선스", r"\blicense\b", r"로열티", r"\broyalt"]),
    ("공사/도급/하도급", [r"공사", r"시공", r"도급", r"하도급", r"\bconstruction\b", r"\bsubcontract"]),
    ("근로/고용", [r"근로계약", r"고용", r"\bemployment\b", r"\blabor\b"]),
    ("합의/정산/해지", [r"합의서", r"정산", r"해지", r"종료 합의", r"\bsettlement\b", r"\btermination\b"]),
    ("공문/의견/확인", [r"공문", r"의견", r"검토의견", r"확인서", r"notice", r"letter"]),
]


def classify_contract_type(text: str, filename: str) -> tuple[str, str]:
    t = (text or "").lower()
    f = (filename or "").lower()
    for typ, pats in CONTRACT_TYPE_RULES:
        for p in pats:
            if re.search(p.lower(), t, re.IGNORECASE) or re.search(p.lower(), f, re.IGNORECASE):
                return typ, "text+filename"
    return "기타/미분류", "text+filename"


ENTITY_PATTERNS = [
    ("퍼시스", [r"(주\.)?\s*퍼시스", r"\bfursys\b"]),
    ("시디즈", [r"시디즈", r"\bsidiz\b"]),
    ("일룸/데스커", [r"일룸", r"데스커", r"\biloom\b", r"\bdesker\b"]),
    ("퍼시스홀딩스", [r"퍼시스홀딩스", r"\bfursys holdings\b"]),
    ("해외법인(미국/베트남 등)", [r"Fursys America", r"Vietnam", r"\bLLC\b", r"\bInc\.\b"]),
]


def detect_entities(text: str, filename: str) -> set[str]:
    s = (text or "") + "\n" + (filename or "")
    out = set()
    for name, pats in ENTITY_PATTERNS:
        for p in pats:
            if re.search(p, s, re.IGNORECASE):
                out.add(name)
                break
    if not out:
        out.add("미상")
    return out


CLAUSE_TOPICS = {
    "당사자/정의": [r"당사자", r"\bhereinafter\b", r"\bdefinitions?\b", r"갑\s*[:：]|을\s*[:：]"],
    "목적/범위": [r"목적", r"범위", r"\bscope\b", r"\bpurpose\b", r"업무범위", r"용역범위"],
    "기간/갱신": [r"기간", r"유효기간", r"계약기간", r"\bterm\b", r"renew"],
    "대금/지급/정산": [r"대금", r"지급", r"정산", r"수수료", r"\bfee\b", r"\bpayment\b", r"invoice"],
    "비밀유지": [r"비밀", r"confidential"],
    "개인정보": [r"개인정보", r"처리위탁", r"privacy", r"data processing"],
    "지재권/IP": [r"지식재산", r"저작권", r"\bintellectual property\b", r"\bIP\b", r"\blicense\b"],
    "품질/검수/하자": [r"검수", r"하자", r"품질", r"warranty", r"inspection", r"acceptance"],
    "손해배상/면책/배상": [r"손해배상", r"배상", r"면책", r"\bindemnif", r"hold harmless", r"\bliable\b"],
    "책임제한/한도": [r"책임.{0,20}(제한|한도)", r"한도", r"limitation of liability", r"\bcap\b", r"no event shall"],
    "해지/종료": [r"해지", r"종료", r"terminate", r"termination"],
    "준거법/관할/분쟁": [r"준거법", r"관할", r"분쟁", r"governing law", r"jurisdiction", r"arbitration"],
    "불가항력": [r"불가항력", r"force majeure"],
    "양도/하도급/재위탁": [r"양도", r"승계", r"assignment", r"subcontract", r"재위탁"],
    "안전/산안법/중대재해": [r"안전", r"산업안전", r"중대재해", r"safety", r"\bEHS\b"],
    "기술자료/자료요구": [r"기술자료", r"도면", r"설계", r"\bBOM\b", r"원가자료", r"자료\s*제출", r"source code"],
    "독점/경업": [r"독점", r"exclusive", r"경업", r"non[- ]compete"],
    "위약금/지체상금": [r"위약금", r"지체상금", r"penalty", r"liquidated damages"],
}


HIGH_RISK_PATTERNS = {
    "무제한 책임(또는 사실상 무한대)": [
        r"무제한\s*책임",
        r"제한\s*없이\s*책임",
        r"한도\s*없이\s*책임",
        r"unlimited\s+liabilit",
        r"without\s+limitation",
    ],
    "일방 면책/일방 배상(후보)": [
        r"일체\s*책임\s*없",
        r"전혀\s*책임\s*없",
        r"면책한다",
        r"shall\s+not\s+be\s+liable",
        r"hold\s+harmless",
        r"\bindemnif",
    ],
    "안전책임 공백(후보: 안전 조항 부재)": [
        r"__CHECK_ABSENCE__SAFETY__"
    ],
    "기술자료 요구": [
        r"기술자료",
        r"도면\s*제공",
        r"원가자료",
        r"자료\s*제출",
        r"source\s+code",
    ],
    "하도급 단가감액": [
        r"__AND__",
        r"(하도급|subcontract)",
        r"(단가\s*(감액|인하)|unit\s+price\s+(reduction|decrease|reduc)|price\s+reduction)",
    ],
    "대리점 비용전가": [
        r"__AND__",
        r"(대리점|dealer|distributor)",
        r"(비용\s*부담|판촉비|프로모션\s*비용|광고비\s*부담|반품\s*비용|인테리어\s*비용|시설\s*투자|매장\s*비용)",
    ],
}


NEGOTIATION_PHRASES = {
    "상호협의/별도협의": [r"상호\s*협의", r"별도\s*협의", r"협의하여", r"mutual agreement"],
    "사전 서면동의": [r"사전\s*서면\s*동의", r"prior\s+written\s+consent"],
    "요청 시/요구 시": [r"요청\s*시", r"요구\s*시", r"upon request"],
    "추후 정함/추후 협의": [r"추후\s*정", r"추후\s*협의", r"to be determined"],
    "불리한 일방표현(갑 중심)": [r"갑의\s*(요구|지시|승인)", r"at\s+the\s+request\s+of\s+Party\s+A"],
}


def find_snippets(text: str, patterns: list[str], window: int = 140, limit: int = 3) -> list[str]:
    out = []
    for pat in patterns:
        if pat.startswith("__CHECK_ABSENCE__"):
            continue
        for m in re.finditer(pat, text, re.IGNORECASE):
            s = max(0, m.start() - window)
            e = min(len(text), m.end() + window)
            snippet = text[s:e]
            snippet = snippet.replace("\n", " ")
            snippet = re.sub(r"\s+", " ", snippet).strip()
            out.append(snippet)
            if len(out) >= limit:
                return out
    return out


NON_STANDARD_CLAUSE_PATTERNS = {
    "공정거래/대리점법 준수(반복 고지)": [r"대리점거래의 공정화", r"독점규제 및 공정거래", r"약관의 규제"],
    "기술자료/원가자료 제출 요구": [r"기술자료", r"원가자료", r"자료\s*제출", r"source\s+code"],
    "중대재해/산안법 직접 언급": [r"중대재해", r"산업안전", r"산업안전보건법"],
    "지체상금/손해액 예정(금전 페널티)": [r"지체상금", r"손해액의 예정", r"liquidated damages"],
    "사전 서면동의(양도/재위탁/변경)": [r"사전\s*서면\s*동의", r"prior\s+written\s+consent"],
    "일방 지시/승인 구조(갑 중심)": [r"갑의\s*(요구|지시|승인)", r"at\s+the\s+request\s+of\s+Party\s+A"],
}


@dataclass
class FileRecord:
    file_name: str
    rel_path: str
    ext: str
    size_bytes: int
    method: str
    success: bool
    output_txt: str
    text_length: int
    word_count: int
    error: str
    scope: str
    status: str
    quality_reason: str
    contract_type: str | None = None
    entities: set[str] | None = None


def build_records() -> list[FileRecord]:
    rows = load_log_rows()
    recs: list[FileRecord] = []
    for r in rows:
        success = str(r["success"]).lower() == "true"
        text_len = int(r["text_length"] or "0")
        wc = int(r["word_count"] or "0")
        size = int(r["size_bytes"] or "0")
        rel = r["rel_path"]
        scope = "standard" if is_standard_rel(rel) else "contract"
        status = "FAILED"
        q_reason = ""
        if success:
            out_path = EXTRACT_DIR / r["output_txt"]
            try:
                text = safe_read_text(out_path)
            except Exception:
                text = ""
            status, q_reason = text_quality(text)
        else:
            q_reason = (r.get("error") or "").strip()
            status = "FAILED"
        recs.append(
            FileRecord(
                file_name=r["file_name"],
                rel_path=rel.replace("\\", "/"),
                ext=r["ext"],
                size_bytes=size,
                method=r["method"],
                success=success,
                output_txt=r["output_txt"],
                text_length=text_len,
                word_count=wc,
                error=(r.get("error") or "").strip(),
                scope=scope,
                status=status,
                quality_reason=q_reason,
            )
        )
    return recs


def summarize_standard_contracts(confirmed_std: list[FileRecord]) -> str:
    topic_counts = Counter()
    sample_map = {}
    for rec in confirmed_std:
        text = safe_read_text(EXTRACT_DIR / rec.output_txt)
        for topic, pats in CLAUSE_TOPICS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in pats):
                topic_counts[topic] += 1
                if topic not in sample_map:
                    sn = find_snippets(text, pats, window=120, limit=1)
                    if sn:
                        sample_map[topic] = (rec.file_name, sn[0])
    lines = []
    lines.append("# 표준계약서 요약(본문 추출 기반)")
    lines.append("")
    lines.append(f"- 기준 파일: docs/Standard Contract 내 CONFIRMED {len(confirmed_std)}건")
    lines.append("- 주의: 표준계약서 폴더 구성(유형/수량)에 따라 '없음' 판단은 제한적일 수 있음")
    lines.append("")
    lines.append("## 표준계약서에 포함된 주요 조항 토픽(파일 기준 빈도)")
    lines.append("")
    lines.append("| 토픽 | 포함 파일 수 | 대표 문구(예시) | 근거 파일 |")
    lines.append("|---|---:|---|---|")
    for topic, cnt in topic_counts.most_common():
        fn, ex = sample_map.get(topic, ("-", "-"))
        ex = (ex[:180] + "…") if len(ex) > 180 else ex
        lines.append(f"| {topic} | {cnt} | {ex} | {fn} |")
    lines.append("")
    return "\n".join(lines)


def generate_02a(recs: list[FileRecord]) -> str:
    all_contract = [r for r in recs if r.scope == "contract"]
    all_std = [r for r in recs if r.scope == "standard"]

    def by_ext(items: list[FileRecord]) -> Counter:
        c = Counter()
        for r in items:
            c[r.ext] += 1
        return c

    def status_counts(items: list[FileRecord]) -> Counter:
        c = Counter()
        for r in items:
            c[r.status] += 1
        return c

    fail_reasons = Counter()
    for r in all_contract:
        if r.status == "FAILED":
            msg = r.error or r.quality_reason or ""
            msg_l = msg.lower()
            if "ocr required" in msg_l or "text layer" in msg_l:
                fail_reasons["PDF: OCR 필요(텍스트 레이어 없음)"] += 1
            elif "unsupported format" in msg_l:
                fail_reasons["미지원 포맷(hwp 등)"] += 1
            elif "document.xml not found" in msg_l or "word directory not found" in msg_l:
                fail_reasons["DOCX 구조 이상"] += 1
            elif "xml" in msg_l:
                fail_reasons["DOCX XML 파싱 실패"] += 1
            elif "com" in msg_l or "word" in msg_l or "excel" in msg_l:
                fail_reasons["Office COM 변환 실패"] += 1
            elif "too short" in msg_l:
                fail_reasons["추출 텍스트 너무 짧음"] += 1
            else:
                fail_reasons["기타/미분류"] += 1

    lines = []
    lines.append("# 계약서 본문 텍스트 추출 상태(02a)")
    lines.append("")
    lines.append("## 요약")
    lines.append("")
    lines.append(f"- 대상 폴더: docs/Contract, docs/Standard Contract")
    lines.append(f"- 전체 파일(Contract): {len(all_contract)}")
    lines.append(f"- 전체 파일(Standard): {len(all_std)}")
    lines.append("")
    c_status = status_counts(all_contract)
    lines.append("### Contract 상태 분포")
    lines.append("")
    lines.append("| 상태 | 파일 수 | 정의 |")
    lines.append("|---|---:|---|")
    lines.append(f"| CONFIRMED | {c_status.get('CONFIRMED',0)} | 본문 추출 성공 + 길이/품질 기준 통과 |")
    lines.append(f"| UNCONFIRMED | {c_status.get('UNCONFIRMED',0)} | 추출은 되었으나 짧거나 품질 이슈(통계 제외 권장) |")
    lines.append(f"| FAILED | {c_status.get('FAILED',0)} | 본문 추출 실패(분석 제외 또는 ESTIMATED로만 사용) |")
    lines.append("")
    lines.append("### 파일 형식 분포(Contract)")
    lines.append("")
    lines.append("| 확장자 | 개수 |")
    lines.append("|---|---:|")
    for ext, cnt in by_ext(all_contract).most_common():
        lines.append(f"| {ext} | {cnt} |")
    lines.append("")
    lines.append("### 추출 실패 원인(Contract, FAILED 기준)")
    lines.append("")
    lines.append("| 실패 원인 분류 | 건수 |")
    lines.append("|---|---:|")
    for k, v in fail_reasons.most_common():
        lines.append(f"| {k} | {v} |")
    lines.append("")
    lines.append("## 상세 목록(Contract)")
    lines.append("")
    lines.append("| 파일명 | 형식 | 상태 | 방법 | 텍스트 길이 | 실패 사유 |")
    lines.append("|---|---|---|---|---:|---|")
    for r in sorted(all_contract, key=lambda x: (x.status != "FAILED", x.ext, x.file_name)):
        reason = r.error if r.status == "FAILED" else r.quality_reason
        reason = (reason[:140] + "…") if reason and len(reason) > 140 else (reason or "")
        lines.append(f"| {r.file_name} | {r.ext} | {r.status} | {r.method} | {r.text_length} | {reason} |")
    lines.append("")
    return "\n".join(lines)


def build_confirmed_corpus(recs: list[FileRecord], scope: str) -> list[FileRecord]:
    out = []
    for r in recs:
        if r.scope != scope:
            continue
        if r.status != "CONFIRMED":
            continue
        out.append(r)
    return out


def analyze_confirmed(recs: list[FileRecord], confirmed_std: list[FileRecord]) -> dict:
    confirmed_contract = build_confirmed_corpus(recs, "contract")

    std_texts = []
    for r in confirmed_std:
        std_texts.append(safe_read_text(EXTRACT_DIR / r.output_txt))

    std_topic_present = {t: False for t in CLAUSE_TOPICS}
    for t in CLAUSE_TOPICS:
        for st in std_texts:
            if any(re.search(p, st, re.IGNORECASE) for p in CLAUSE_TOPICS[t]):
                std_topic_present[t] = True
                break

    by_type = defaultdict(list)
    clause_presence = Counter()
    clause_files = defaultdict(list)
    neg_presence = Counter()
    neg_files = defaultdict(list)
    risk_files = defaultdict(list)
    risk_snippets = defaultdict(lambda: defaultdict(list))
    entity_topic_counts = defaultdict(lambda: Counter())
    non_std_presence = Counter()
    non_std_files = defaultdict(list)

    for r in confirmed_contract:
        text = safe_read_text(EXTRACT_DIR / r.output_txt)
        ctype, _src = classify_contract_type(text, r.file_name)
        r.contract_type = ctype
        r.entities = detect_entities(text, r.file_name)
        by_type[ctype].append(r)

        for topic, pats in CLAUSE_TOPICS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in pats):
                clause_presence[topic] += 1
                clause_files[topic].append(r.file_name)
                for e in r.entities:
                    entity_topic_counts[e][topic] += 1

        for k, pats in NEGOTIATION_PHRASES.items():
            if any(re.search(p, text, re.IGNORECASE) for p in pats):
                neg_presence[k] += 1
                neg_files[k].append(r.file_name)

        for risk, pats in HIGH_RISK_PATTERNS.items():
            if risk.startswith("안전책임 공백"):
                if ctype in {"공사/도급/하도급", "물품공급/구매/매매", "대리점/위탁/유통", "용역/자문/SOW"}:
                    if not any(re.search(p, text, re.IGNORECASE) for p in CLAUSE_TOPICS["안전/산안법/중대재해"]):
                        risk_files[risk].append(r.file_name)
                continue
            if pats and pats[0] == "__AND__":
                must1 = pats[1]
                must2 = pats[2]
                if re.search(must1, text, re.IGNORECASE) and re.search(must2, text, re.IGNORECASE):
                    risk_files[risk].append(r.file_name)
                    snips = find_snippets(text, [must1, must2], window=160, limit=2)
                    if snips:
                        for s in snips:
                            risk_snippets[risk][r.file_name].append(s)
                continue
            if any(re.search(p, text, re.IGNORECASE) for p in pats):
                risk_files[risk].append(r.file_name)
                snips = find_snippets(text, pats, window=160, limit=2)
                if snips:
                    for s in snips:
                        risk_snippets[risk][r.file_name].append(s)

        for k, pats in NON_STANDARD_CLAUSE_PATTERNS.items():
            if any(re.search(p, text, re.IGNORECASE) for p in pats):
                non_std_presence[k] += 1
                non_std_files[k].append(r.file_name)

    missing_in_std = []
    for topic, cnt in clause_presence.items():
        if cnt == 0:
            continue
        if not std_topic_present.get(topic, False):
            missing_in_std.append((topic, cnt))
    missing_in_std.sort(key=lambda x: x[1], reverse=True)

    return {
        "confirmed_contract": confirmed_contract,
        "by_type": by_type,
        "clause_presence": clause_presence,
        "clause_files": clause_files,
        "missing_in_std": missing_in_std,
        "neg_presence": neg_presence,
        "neg_files": neg_files,
        "risk_files": risk_files,
        "risk_snippets": risk_snippets,
        "entity_topic_counts": entity_topic_counts,
        "std_topic_present": std_topic_present,
        "non_std_presence": non_std_presence,
        "non_std_files": non_std_files,
    }


def freq_level(count: int, total: int) -> str:
    if total <= 0:
        return "-"
    r = count / total
    if r >= 0.35:
        return "HIGH"
    if r >= 0.15:
        return "MEDIUM"
    return "LOW"


def generate_02b(analysis: dict) -> str:
    by_type = analysis["by_type"]
    confirmed_contract = analysis["confirmed_contract"]
    lines = []
    lines.append("# 계약유형별 대표 본문 샘플(02b, CONFIRMED 기반)")
    lines.append("")
    lines.append(f"- CONFIRMED 표본 수: {len(confirmed_contract)}")
    lines.append("- 샘플은 본문 초반부 일부 발췌(길이 제한)이며, 전체 문맥 확인이 필요함")
    lines.append("")

    for ctype, items in sorted(by_type.items(), key=lambda kv: len(kv[1]), reverse=True):
        if not items:
            continue
        pick = sorted(items, key=lambda r: r.text_length, reverse=True)[:2]
        lines.append(f"## {ctype} (CONFIRMED {len(items)}건)")
        lines.append("")
        for r in pick:
            text = safe_read_text(EXTRACT_DIR / r.output_txt)
            excerpt = "\n".join(text.splitlines()[:18])
            excerpt = excerpt.strip()
            lines.append(f"### {r.file_name}")
            lines.append("")
            lines.append("```")
            lines.append(excerpt[:2200])
            lines.append("```")
            lines.append("")
    return "\n".join(lines)


def generate_verified_md(recs: list[FileRecord], analysis: dict) -> str:
    confirmed_contract = analysis["confirmed_contract"]
    by_type = analysis["by_type"]
    clause_presence = analysis["clause_presence"]
    clause_files = analysis["clause_files"]
    missing_in_std = analysis["missing_in_std"]
    neg_presence = analysis["neg_presence"]
    neg_files = analysis["neg_files"]
    risk_files = analysis["risk_files"]
    risk_snippets = analysis["risk_snippets"]
    entity_topic_counts = analysis["entity_topic_counts"]
    non_std_presence = analysis["non_std_presence"]
    non_std_files = analysis["non_std_files"]
    std_texts = []
    for r in build_confirmed_corpus(recs, "standard"):
        std_texts.append(safe_read_text(EXTRACT_DIR / r.output_txt))

    total = len(confirmed_contract)
    lines = []
    lines.append("# 실제 계약서 공통 패턴(검증본, CONFIRMED/ESTIMATED 분리)")
    lines.append("")
    lines.append("## 전제/원칙")
    lines.append("")
    lines.append("- CONFIRMED: 실제 본문 텍스트 추출 성공 + 품질 기준 통과한 문서만 반영")
    lines.append("- ESTIMATED: 파일명 기반 추정(본문 미확인)으로, 패턴/리스크 확정에 사용하지 않음")
    lines.append("- FAILED: 본문 추출 실패(분석 제외 또는 ESTIMATED로만 유지)")
    lines.append("")
    lines.append(f"## CONFIRMED 커버리지")
    lines.append("")
    contract_total = len([r for r in recs if r.scope == 'contract'])
    confirmed_cnt = total
    unconfirmed_cnt = len([r for r in recs if r.scope == "contract" and r.status == "UNCONFIRMED"])
    failed_cnt = len([r for r in recs if r.scope == "contract" and r.status == "FAILED"])
    lines.append(f"- docs/Contract 전체: {contract_total}")
    lines.append(f"- CONFIRMED(분석 포함): {confirmed_cnt}")
    lines.append(f"- UNCONFIRMED(통계 제외 권장): {unconfirmed_cnt}")
    lines.append(f"- FAILED(본문 미확인): {failed_cnt}")
    lines.append("")

    lines.append("## 1) 계약유형 분류(CONFIRMED 기반)")
    lines.append("")
    lines.append("| 계약유형 | CONFIRMED 건수 | 대표 파일 |")
    lines.append("|---|---:|---|")
    for ctype, items in sorted(by_type.items(), key=lambda kv: len(kv[1]), reverse=True):
        if not items:
            continue
        rep = sorted(items, key=lambda r: r.text_length, reverse=True)[:2]
        rep_names = ", ".join([x.file_name for x in rep])
        lines.append(f"| {ctype} | {len(items)} | {rep_names} |")
    lines.append("")

    if total < 30:
        lines.append("## 진행 보류 권고")
        lines.append("")
        lines.append("- CONFIRMED 표본이 적어 통계적으로 안정적인 '공통 rule' 확정은 보류 권장")
        lines.append("")

    lines.append("## 2) 반복 조항 토픽(CONFIRMED 기반, 파일 기준 빈도)")
    lines.append("")
    lines.append("| 토픽 | 빈도 | 수준 | 대표 문구 예시 | 근거 파일(예시) |")
    lines.append("|---|---:|---|---|---|")
    for topic, cnt in clause_presence.most_common():
        lvl = freq_level(cnt, total)
        sample_file = clause_files[topic][0] if clause_files[topic] else "-"
        sample_text = "-"
        if sample_file != "-":
            rec = next((r for r in confirmed_contract if r.file_name == sample_file), None)
            if rec:
                txt = safe_read_text(EXTRACT_DIR / rec.output_txt)
                sn = find_snippets(txt, CLAUSE_TOPICS[topic], window=120, limit=1)
                if sn:
                    sample_text = sn[0]
        sample_text = (sample_text[:180] + "…") if len(sample_text) > 180 else sample_text
        ex_files = ", ".join(clause_files[topic][:3])
        lines.append(f"| {topic} | {cnt}/{total} | {lvl} | {sample_text} | {ex_files} |")
    lines.append("")

    lines.append("## 3) 표준계약서에는 없지만 반복적으로 등장한 토픽(추출 기반 비교)")
    lines.append("")
    lines.append("- 비교 기준: docs/review_output/01_standard_contract_summary.md(동일 추출 로직으로 재생성)")
    lines.append("")
    lines.append("| 항목(패턴) | 빈도 | 수준 | 대표 문구 예시 | 근거 파일(예시) |")
    lines.append("|---|---:|---|---|---|")

    added = 0
    for name, cnt in non_std_presence.most_common():
        present_in_std = False
        for st in std_texts:
            if any(re.search(p, st, re.IGNORECASE) for p in NON_STANDARD_CLAUSE_PATTERNS[name]):
                present_in_std = True
                break
        if present_in_std:
            continue
        lvl = freq_level(cnt, total)
        sample_file = non_std_files[name][0] if non_std_files[name] else "-"
        sample_text = "-"
        if sample_file != "-":
            rec = next((r for r in confirmed_contract if r.file_name == sample_file), None)
            if rec:
                txt = safe_read_text(EXTRACT_DIR / rec.output_txt)
                sn = find_snippets(txt, NON_STANDARD_CLAUSE_PATTERNS[name], window=120, limit=1)
                if sn:
                    sample_text = sn[0]
        sample_text = (sample_text[:180] + "…") if len(sample_text) > 180 else sample_text
        ex_files = ", ".join(non_std_files[name][:3])
        lines.append(f"| {name} | {cnt}/{total} | {lvl} | {sample_text} | {ex_files} |")
        added += 1
    if added == 0:
        lines.append(f"| (없음) | 0/{total} | - | 표준계약서(현재 폴더 구성)에서도 동일/유사 패턴이 발견되어 '표준에 없음'으로 확정 불가 | - |")
    lines.append("")

    lines.append("## 4) 자주 협상/수정 흔적 문구(CONFIRMED 기반)")
    lines.append("")
    lines.append("| 패턴 | 빈도 | 수준 | 근거 파일(예시) |")
    lines.append("|---|---:|---|---|")
    for k, cnt in neg_presence.most_common():
        lvl = freq_level(cnt, total)
        ex_files = ", ".join(neg_files[k][:5])
        lines.append(f"| {k} | {cnt}/{total} | {lvl} | {ex_files} |")
    lines.append("")

    lines.append("## 5) 고위험 조항 후보(CONFIRMED 기반)")
    lines.append("")
    lines.append("- 아래 항목은 규칙 기반 키워드 탐지 결과이며, 실제 의미(상호/일방, 한도 유무 등)는 원문 맥락 검토가 필요함")
    lines.append("")
    lines.append("| 고위험 항목 | CONFIRMED 탐지 파일 수 | 파일명(예시) | 대표 문구 예시 |")
    lines.append("|---|---:|---|---|")
    for risk, files in sorted(risk_files.items(), key=lambda kv: len(kv[1]), reverse=True):
        if not files:
            continue
        ex_files = ", ".join(files[:3])
        ex_phrase = "-"
        for fn in files[:3]:
            snips = risk_snippets.get(risk, {}).get(fn)
            if snips:
                ex_phrase = snips[0]
                break
        ex_phrase = (ex_phrase[:180] + "…") if len(ex_phrase) > 180 else ex_phrase
        lines.append(f"| {risk} | {len(files)} | {ex_files} | {ex_phrase} |")
    lines.append("")

    lines.append("## 6) 법인별로 다르게 적용될 가능성이 있는 토픽(편중 징후)")
    lines.append("")
    lines.append("- 기준: 특정 법인 그룹에서 토픽 출현 비중이 상대적으로 높은 경우(탐지 기반)")
    lines.append("")
    lines.append("| 법인 그룹 | 편중 토픽(상위 5) |")
    lines.append("|---|---|")
    for ent, c in sorted(entity_topic_counts.items(), key=lambda kv: sum(kv[1].values()), reverse=True):
        top = [f"{t}({n})" for t, n in c.most_common(5)]
        lines.append(f"| {ent} | {', '.join(top) if top else '-'} |")
    lines.append("")

    lines.append("## 7) Rule 후보(초안, CONFIRMED 기반)")
    lines.append("")
    lines.append("| Rule ID | 트리거(키워드/조건) | 설명 | 조치(리뷰 포인트) | 근거(빈도/파일) |")
    lines.append("|---|---|---|---|---|")
    rules = [
        ("R-HIGH-001", "무제한/without limitation/unlimited liability", "책임한도 부재 또는 무제한 책임 후보", "책임제한/손해범위/간접손해 제외/총액 캡 협상", "무제한 책임 탐지 결과 참조"),
        ("R-HIGH-002", "hold harmless/indemnify/면책/일체 책임 없음", "일방 면책/일방 배상 후보", "상호성·범위·절차(방어/통지)·보험 연계 확인", "일방 면책/배상 탐지 결과 참조"),
        ("R-HIGH-003", "기술자료/원가자료/도면/소스코드", "기술자료 요구 조항", "제공 범위·목적·비밀유지·반환/폐기·하도급법 이슈 점검", "기술자료 요구 탐지 결과 참조"),
        ("R-HIGH-004", "하도급 + 단가 감액/인하", "하도급 단가감액 후보", "감액 사유/절차/서면/소급 여부·하도급법 리스크 확인", "하도급 단가감액 탐지 결과 참조"),
        ("R-HIGH-005", "대리점 + 비용부담/판촉비/반품비/광고비", "대리점 비용전가 후보", "공정거래/대리점 정책 일관성·증빙·상한 확인", "대리점 비용전가 탐지 결과 참조"),
    ]
    for rid, trig, desc, act, basis in rules:
        lines.append(f"| {rid} | {trig} | {desc} | {act} | {basis} |")
    lines.append("")

    lines.append("## 8) ESTIMATED(파일명 기반) 섹션")
    lines.append("")
    lines.append("- 아래는 본문 미확인(FAILED/UNCONFIRMED)로, 패턴 확정/고위험 확정에 포함하지 않음")
    lines.append("")
    est_items = []
    for r in recs:
        if r.scope != "contract":
            continue
        if r.status == "CONFIRMED":
            continue
        est_type, _ = classify_contract_type("", r.file_name)
        est_items.append((est_type, r))
    by_est = defaultdict(list)
    for t, r in est_items:
        by_est[t].append(r)
    lines.append("| ESTIMATED 계약유형 | 건수 | 예시 파일 | 상태 구성 |")
    lines.append("|---|---:|---|---|")
    for t, items in sorted(by_est.items(), key=lambda kv: len(kv[1]), reverse=True):
        ex = ", ".join([x.file_name for x in items[:3]])
        sc = Counter([x.status for x in items])
        lines.append(f"| {t} | {len(items)} | {ex} | {', '.join([f'{k}:{v}' for k,v in sc.items()])} |")
    lines.append("")

    lines.append("## 9) 아직 본문 확인이 안 되어 3번 프롬프트에 반영하면 안 되는 항목")
    lines.append("")
    lines.append("- 조건: CONFIRMED에서 0건이거나(미탐지), 안전책임 공백처럼 '부재' 판단이 불확실한 항목")
    lines.append("")
    blocked = []
    for risk in HIGH_RISK_PATTERNS:
        if risk.startswith("안전책임 공백"):
            blocked.append((risk, "부재 판정은 계약유형/원문 구조에 따라 오탐 가능"))
        else:
            if len(risk_files.get(risk, [])) == 0:
                blocked.append((risk, "CONFIRMED에서 근거 문구 미확인"))
    lines.append("| 항목 | 사유 |")
    lines.append("|---|---|")
    for k, v in blocked:
        lines.append(f"| {k} | {v} |")
    lines.append("")

    return "\n".join(lines)


def main():
    recs = build_records()
    confirmed_std = build_confirmed_corpus(recs, "standard")

    OUT_02A.write_text(generate_02a(recs), encoding="utf-8")
    OUT_STD_SUMMARY.write_text(summarize_standard_contracts(confirmed_std), encoding="utf-8")

    analysis = analyze_confirmed(recs, confirmed_std)
    OUT_02B.write_text(generate_02b(analysis), encoding="utf-8")
    OUT_VERIFIED.write_text(generate_verified_md(recs, analysis), encoding="utf-8")

    meta = {
        "contract_total": len([r for r in recs if r.scope == "contract"]),
        "contract_confirmed": len([r for r in recs if r.scope == "contract" and r.status == "CONFIRMED"]),
        "contract_unconfirmed": len([r for r in recs if r.scope == "contract" and r.status == "UNCONFIRMED"]),
        "contract_failed": len([r for r in recs if r.scope == "contract" and r.status == "FAILED"]),
        "by_type_confirmed": {k: len(v) for k, v in analysis["by_type"].items()},
        "risk_confirmed_files": {k: v for k, v in analysis["risk_files"].items()},
    }
    (REVIEW_DIR / "02_verified_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

