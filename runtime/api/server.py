from __future__ import annotations

import json
import re
import tempfile
import time
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from runtime.ai.config import load_ai_config
from runtime.ai.enhance import polish_draft_text, polish_questions, polish_revision, prioritize_questions
from runtime.ai.factory import create_ai_provider, is_ai_enabled
from runtime.ai.provider import AIMessage, AIRequest
from runtime.ai.safe import sanitize_error_message
from runtime.admin.ui import ADMIN_HTML
from runtime.admin.upload_ui import UPLOAD_HTML
from runtime.admin.review_results_ui import REVIEW_RESULTS_HTML
from runtime.admin.approval_queue_ui import APPROVAL_QUEUE_HTML
from runtime.admin.ep_legal_request_ui import EP_LEGAL_REQUEST_HTML
from runtime.admin.internal_demo_ui import INTERNAL_DEMO_HTML
from runtime.admin.internal_demo_chat_ui import INTERNAL_DEMO_CHAT_HTML
from runtime.db.review_repository import ReviewRepository
from runtime.rules.loader import RuleLoader
from runtime.questions.storage import (
    create_session,
    create_text_session,
    save_session,
    load_session,
    run_review_with_session,
    run_review_with_session_fast,
    save_answers,
)
from runtime.review.minimal_edit import apply_minimal_edit as _apply_minimal_edit
from runtime.review.delivery_gate import (
    DeliveryReport,
    disclosure_rows as _delivery_disclosure_rows,
    is_advisory_only as _is_advisory_only,
    remediate_review_status as _remediate_review_status,
    withdraw_proposal as _withdraw_proposal,
)
from runtime.questions.contract_question_agent import (
    ContractQuestionPlan,
    plan_questions as _plan_questions_with_ai,
)
from runtime.questions.generator import generate_questions
from runtime.questions.model import question_to_dict
from runtime.ep.intake import intake_to_dict, validate_ep_intake
from runtime.ep.status import can_transition, is_valid_status
from runtime.ep.handoff import build_handoff_payload, payload_to_dict
from runtime.ep.approval_client import HttpApprovalClient, StubApprovalClient
from runtime.draft.service import generate_draft_text, list_standard_templates, suggest_template_ids
from runtime.review.classify import classify
from runtime.review.infer import update_cache
from runtime.review.revision import split_into_clauses, suggest_revisions
from runtime.review.clause_level import build_clause_level_result
from runtime.review.docx_writer import build_revision_docx
from runtime.review.legal_review_docx import build_legal_review_docx as _build_legal_review_docx
from runtime.review.legal_review_pdf import build_legal_review_pdf as _build_legal_review_pdf


class _StoredProfile:
    """검토 때 저장된 detailed_contract_profile 을 그대로 쓰기 위한 얇은 래퍼.

    다운로드 경로는 `_detailed_profile.contract_type` 과 `.to_dict()` 만 쓴다.
    분류기를 다시 돌리는 대신 저장된 dict 를 이 형태로 감싸면, 검토와 출력이
    같은 값을 본다(2026-09-09 3차 지시 6항).
    """

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data or {})

    @property
    def contract_type(self) -> str:
        return str(self._data.get("contract_type") or "")

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)
from runtime.review.mandatory_issues import inject_mandatory_issues as _inject_mandatory_issues
from runtime.review.output_filter import build_final_findings as _build_final_findings
from runtime.review.severity_reclassifier import reclassify_for_consignment_dealer as _reclassify_consignment
from runtime.review.hallucination_guard import check_revision_text as _hg_check_revision
from runtime.review.contract_classifier import classify_contract_detailed as _classify_detailed
from runtime.review.redline_builder import build_redline_from_analysis
from runtime.review.text_extract import extract_text_from_file
from runtime.review.clause_extraction import extract_clauses, is_real_segment_clause_id
from runtime.services.query_service import ReviewInput, RuleQueryService
from runtime.law.cache import JsonFileCache
from runtime.law.config import load_law_api_config
from runtime.law.search_service import LawSearchService
from runtime.env_debug import env_status
from runtime.project_paths import DOCS_REPO_ROOT as REPO_ROOT


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _html_response(handler: BaseHTTPRequestHandler, html: str) -> None:
    data = html.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _content_disposition(filename: str) -> str:
    """비ASCII 파일명을 안전하게 담은 Content-Disposition 값.

    [2026-09-10 지시 항목 2] 한글 파일명을 그대로 헤더에 넣으면 http.server 가
    헤더를 latin-1 로 인코딩하는 지점에서 UnicodeEncodeError 를 던지고, 응답을
    한 바이트도 보내지 못한 채 커넥션이 끊긴다(브라우저에는 원인 없는 "다운로드
    실패"로만 보인다). 실측: download_redline 이 500 도 아닌 RemoteDisconnected
    로 죽었다 — 한글 파일명이 그대로 헤더에 들어간 경우다.

    RFC 6266/5987 형식으로 ASCII fallback 과 UTF-8 파라미터를 함께 보낸다.
    """
    from urllib.parse import quote

    name = str(filename or "").replace('"', "").replace("\\", "").strip() or "download"
    ascii_name = name.encode("ascii", errors="ignore").decode("ascii").strip()
    # 한글만으로 된 이름은 ASCII 변환 후 확장자 조각("_.docx")만 남는다 —
    # 이름 부분에 영숫자가 하나도 없으면 쓸 수 있는 fallback 이 아니다.
    _stem = ascii_name.rsplit(".", 1)[0] if "." in ascii_name else ascii_name
    if not any(ch.isalnum() for ch in _stem):
        ext = name.rsplit(".", 1)[-1] if "." in name else "bin"
        ascii_name = f"download.{ext}"
    quoted = quote(name, safe="")
    return "attachment; filename=\"{0}\"; filename*=UTF-8''{1}".format(ascii_name, quoted)


def _text_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    text: str,
    *,
    filename: str | None = None,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    data = text.encode("utf-8", errors="replace")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    if filename:
        handler.send_header("Content-Disposition", _content_disposition(filename))
    handler.end_headers()
    handler.wfile.write(data)


def _binary_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    data: bytes,
    *,
    filename: str | None,
    content_type: str,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    if filename:
        handler.send_header("Content-Disposition", _content_disposition(filename))
    handler.end_headers()
    handler.wfile.write(data)


_WORD_XML_MARKERS = (
    "<w:",
    "</w:",
    "w:rPr",
    "w:pPr",
    "w:ins",
    "w:del",
    "w:delText",
    "<?xml",
    "xmlns:w=",
)


def _contains_wordprocessingml_markers(text: str) -> bool:
    s = text or ""
    if not s:
        return False
    return any(m in s for m in _WORD_XML_MARKERS)


def _transaction_type_for(clause_meta: dict | None, text: str) -> str:
    """거래 원형을 하나만 확정해 돌려준다.

    [2026-09-10 아키텍처 지시 항목 1] 검토가 이미 확정해 세션에 저장한
    `legal_state.transaction_type` 이 있으면 **재계산하지 않고** 그것을 쓴다.
    저장된 값이 없는 경로(업로드 직후 등)에서만 효과 프로파일로 계산한다.
    """
    if isinstance(clause_meta, dict):
        stored = clause_meta.get("legal_state")
        if isinstance(stored, dict) and str(stored.get("transaction_type") or "").strip():
            return str(stored["transaction_type"])
    try:
        from runtime.review.clause_effect import build_effect_profile
        from runtime.review.clause_extraction import extract_clauses

        body = str(text or "")
        if not body.strip():
            return ""
        return build_effect_profile(text=body, clauses=extract_clauses(body)[0] or []).archetype
    except Exception:
        return ""


def _statute_decisions_for(
    clause_meta: dict | None,
    *,
    entity: str,
    text: str,
    contract_type_code: str = "",
) -> list:
    """적용법률 판단을 하나만 확정해 돌려준다.

    [2026-09-11 지시] "상대방 역할·계약유형·적용법률은 한 번 확정한 canonical
    값만 사용하고, downstream 에서 다시 추론하지 말 것."

    검토가 확정해 세션에 저장한 `statute_applicability_gate.decisions` 가 있으면
    그것을 복원해 쓴다. 재평가하면 같은 계약에서 화면과 문서가 다른 법률 판단을
    근거로 삼게 된다 — 계약유형에서 이미 같은 사고가 났다("리포트 상단은 장비
    구매·설치, 본문 법률분석은 공사도급").

    저장된 값이 없는 옛 세션에서만 새로 판단한다.
    """
    from runtime.review.statute_applicability_gate import (
        StatuteDecision,
        assess_statutes,
    )

    stored = None
    if isinstance(clause_meta, dict):
        gate = clause_meta.get("statute_applicability_gate")
        if isinstance(gate, dict):
            rows = gate.get("decisions")
            if isinstance(rows, list) and rows:
                stored = rows
    if stored:
        restored: list = []
        for row in stored:
            if not isinstance(row, dict):
                continue
            try:
                restored.append(StatuteDecision(
                    statute=str(row.get("statute") or ""),
                    conclusion=str(row.get("conclusion") or ""),
                    reason=str(row.get("reason") or ""),
                    disabled_topics=[str(t) for t in (row.get("disabled_topics") or [])],
                    facts_needed=[str(f) for f in (row.get("facts_needed") or [])],
                ))
            except Exception:
                continue
        if restored:
            return restored
    return assess_statutes(
        entity=entity, text=text, contract_type_code=contract_type_code,
    )


def _build_question_plan(
    *,
    entity: str,
    contract_type: str,
    text: str,
    review_focus: str | None,
    max_questions: int,
    ai_mode: str = "auto",
) -> ContractQuestionPlan:
    """계약 전문을 AI에게 읽히고 이 계약에 맞는 사전 질문 계획을 세운다.

    [2026-09-10 지시 항목 1] 종전에는 키워드 트리거로 미리 써둔 질문 묶음을
    꺼낸 뒤 AI가 문장만 다듬었다(`enhance.polish_questions`). 그래서 대물교환
    계약에 위탁매매 질문이 통째로 나갔다. 이제 "무엇을 물을지"를 먼저 AI가
    계약을 읽고 판단하고, 정적 질문은 그 판단을 통과한 것만 남는다.

    AI가 꺼져 있거나 호출이 실패하면 빈 계획을 돌려주며, 그 경우 질문 생성은
    종전의 결정론적 경로를 그대로 탄다.
    """
    if str(ai_mode or "auto").strip().lower() == "off":
        return ContractQuestionPlan(status="skipped")
    try:
        cfg = load_ai_config()
        if not is_ai_enabled(cfg):
            return ContractQuestionPlan(status="skipped")
        return _plan_questions_with_ai(
            provider=create_ai_provider(cfg),
            model=cfg.model,
            entity=str(entity or ""),
            contract_type=str(contract_type or ""),
            contract_text=str(text or ""),
            review_focus=review_focus if isinstance(review_focus, str) else None,
            max_questions=int(max_questions),
            timeout_sec=cfg.timeout_sec,
            max_tokens=min(cfg.max_tokens, 2200),
            temperature=min(cfg.temperature, 0.1),
        )
    except Exception as exc:  # noqa: BLE001 - 질문 계획 실패가 업로드를 막지 않는다
        return ContractQuestionPlan(status="error", error=sanitize_error_message(str(exc)))


def _static_response(handler: BaseHTTPRequestHandler, file_path: Path) -> None:
    p = file_path
    if not p.exists() or not p.is_file():
        _json_response(handler, HTTPStatus.NOT_FOUND, {"error": "static file not found"})
        return
    ext = p.suffix.lower()
    if ext == ".png":
        ctype = "image/png"
    elif ext == ".jpg" or ext == ".jpeg":
        ctype = "image/jpeg"
    elif ext == ".svg":
        ctype = "image/svg+xml; charset=utf-8"
    elif ext == ".css":
        ctype = "text/css; charset=utf-8"
    elif ext == ".js":
        ctype = "application/javascript; charset=utf-8"
    else:
        ctype = "application/octet-stream"

    data = p.read_bytes()
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _parse_multipart_form_data(content_type: str, body: bytes) -> dict:
    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        raise ValueError("missing boundary in content-type")
    boundary = m.group(1).strip().strip('"')
    delimiter = ("--" + boundary).encode("utf-8")

    parts = body.split(delimiter)
    fields: dict[str, str] = {}
    file_info: dict | None = None

    for raw in parts:
        raw = raw.strip(b"\r\n")
        if not raw or raw == b"--":
            continue
        if raw.endswith(b"--"):
            raw = raw[:-2].strip(b"\r\n")
        header_blob, sep, content = raw.partition(b"\r\n\r\n")
        if not sep:
            continue

        header_lines = header_blob.decode("utf-8", errors="replace").split("\r\n")
        headers: dict[str, str] = {}
        for line in header_lines:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

        disp = headers.get("content-disposition", "")
        name_m = re.search(r'name="([^"]+)"', disp)
        if not name_m:
            continue
        name = name_m.group(1)
        filename_m = re.search(r'filename="([^"]*)"', disp)
        content = content.rstrip(b"\r\n")

        if filename_m is not None:
            file_info = {
                "field": name,
                "filename": filename_m.group(1) or "uploaded",
                "content_type": headers.get("content-type", "application/octet-stream"),
                "content": content,
            }
        else:
            fields[name] = content.decode("utf-8", errors="replace")

    return {"fields": fields, "file": file_info}


def create_handler(service: RuleQueryService):
    repo = ReviewRepository()
    repo.init_db()

    rules_doc = service.loader.load()
    rules_schema_version = str(rules_doc.get("schema_version", "unknown"))
    rules_source_path = str(service.loader.rules_path)
    rules_sha = sha256(Path(rules_source_path).read_bytes()).hexdigest()
    repo.upsert_rules_version(rules_sha, rules_schema_version, rules_source_path)

    static_map = {
        "aouribot.png": REPO_ROOT / "docs" / "아우리봇.png",
    }
    law_cache = JsonFileCache(path=REPO_ROOT / "aouri-bot" / "runtime" / "data" / "law_cache.json")
    analysis_cache: dict[str, tuple[float, dict]] = {}
    analysis_cache_ttl_sec = 600.0
    analysis_cache_max = 200
    fast_review_cache: dict[str, tuple[float, dict]] = {}
    fast_review_cache_ttl_sec = 600.0
    fast_review_cache_max = 120
    deep_review_cache: dict[str, tuple[float, dict]] = {}
    deep_review_cache_ttl_sec = 900.0
    deep_review_cache_max = 120

    def analyze_cached(review_input: ReviewInput) -> dict:
        payload = {
            "entity": str(review_input.entity or ""),
            "contract_type": str(review_input.contract_type or ""),
            "text": str(review_input.text or ""),
            "answers": (review_input.answers or {}),
        }
        key = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        now = time.time()
        hit = analysis_cache.get(key)
        if hit and (now - float(hit[0])) <= analysis_cache_ttl_sec:
            return hit[1]
        result = service.analyze(review_input)
        if isinstance(result, dict):
            analysis_cache[key] = (now, result)
            if len(analysis_cache) > analysis_cache_max:
                oldest_key = min(analysis_cache.items(), key=lambda kv: kv[1][0])[0]
                analysis_cache.pop(oldest_key, None)
        return result

    class RulesAPIHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path == "/":
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/admin")
                self.end_headers()
                return

            if path == "/health":
                _json_response(self, HTTPStatus.OK, {"status": "ok"})
                return

            if path.startswith("/static/"):
                key = path[len("/static/") :]
                p = static_map.get(key)
                if not p:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "unknown static resource"})
                    return
                _static_response(self, p)
                return

            if path == "/admin":
                _html_response(self, ADMIN_HTML)
                return

            if path == "/admin/reviews":
                _html_response(self, REVIEW_RESULTS_HTML)
                return

            if path == "/admin/approval":
                _html_response(self, APPROVAL_QUEUE_HTML)
                return

            if path == "/ep/mock/legal_request":
                _html_response(self, EP_LEGAL_REQUEST_HTML)
                return

            if path == "/demo":
                _html_response(self, INTERNAL_DEMO_CHAT_HTML)
                return

            if path == "/demo-v1":
                _html_response(self, INTERNAL_DEMO_HTML)
                return

            if path == "/upload":
                _html_response(self, UPLOAD_HTML)
                return

            if path == "/api/rules":
                status = qs.get("status", [""])[0] or None
                entity = qs.get("entity", [""])[0] or None
                contract_type = qs.get("contract_type", [""])[0] or None
                clause_type = qs.get("clause_type", [""])[0] or None
                risk_level = qs.get("risk_level", [""])[0] or None
                items = service.list_rules(
                    status=status,
                    entity=entity,
                    contract_type=contract_type,
                    clause_type=clause_type,
                    risk_level=risk_level,
                    include_backlog=False,
                )
                _json_response(self, HTTPStatus.OK, {"count": len(items), "items": items})
                return

            if path == "/api/rules/version":
                v = repo.get_rules_version(rules_sha) or {
                    "rules_sha256": rules_sha,
                    "schema_version": rules_schema_version,
                    "source_path": rules_source_path,
                    "loaded_at": None,
                }
                _json_response(self, HTTPStatus.OK, v)
                return

            if path == "/api/backlog":
                items = service.list_backlog()
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "count": len(items),
                        "mode": "reference_only",
                        "items": items,
                    },
                )
                return

            if path == "/api/ai/health":
                cfg = load_ai_config()
                enabled = is_ai_enabled(cfg)
                if not enabled:
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "enabled": False,
                            "provider": "mock",
                            "model": cfg.model,
                            "note": "OPENAI_API_KEY/ANTHROPIC_API_KEY not set; using mock provider",
                        },
                    )
                    return
                provider = create_ai_provider(cfg)
                req = AIRequest(
                    model=cfg.model,
                    messages=[AIMessage(role="user", content="ping")],
                    temperature=0.0,
                    max_tokens=16,
                    timeout_sec=cfg.timeout_sec,
                )
                t0 = time.perf_counter()
                try:
                    _ = provider.complete(req)
                    dt = time.perf_counter() - t0
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "enabled": True,
                            "provider": "openai",
                            "model": cfg.model,
                            "elapsed_sec": round(dt, 4),
                            "ok": True,
                        },
                    )
                except Exception as exc:
                    dt = time.perf_counter() - t0
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "enabled": True,
                            "provider": "openai",
                            "model": cfg.model,
                            "elapsed_sec": round(dt, 4),
                            "ok": False,
                            "error": sanitize_error_message(str(exc)),
                        },
                    )
                return

            if path == "/api/debug/env-status":
                _json_response(self, HTTPStatus.OK, env_status(repo_root=REPO_ROOT))
                return

            if path == "/api/reviews":
                limit = int(qs.get("limit", ["50"])[0] or 50)
                offset = int(qs.get("offset", ["0"])[0] or 0)
                entity = qs.get("entity", [""])[0] or None
                contract_type = qs.get("contract_type", [""])[0] or None
                high_risk_only = (qs.get("high_risk_only", ["false"])[0] or "false").lower() == "true"
                approval_required_only = (
                    (qs.get("approval_required_only", ["false"])[0] or "false").lower() == "true"
                )
                items = repo.list_requests(
                    limit=limit,
                    offset=offset,
                    entity=entity,
                    contract_type=contract_type,
                    high_risk_only=high_risk_only,
                    approval_required_only=approval_required_only,
                )
                _json_response(self, HTTPStatus.OK, {"count": len(items), "items": items})
                return

            if path == "/api/draft/templates":
                items = [
                    {
                        "template_id": t.template_id,
                        "filename": t.filename,
                        "supported": t.supported,
                    }
                    for t in list_standard_templates()
                ]
                _json_response(self, HTTPStatus.OK, {"count": len(items), "items": items})
                return

            if path == "/api/draft/suggest":
                contract_type = qs.get("contract_type", [""])[0] or ""
                suggested = suggest_template_ids(contract_type)
                all_items = [
                    {
                        "template_id": t.template_id,
                        "filename": t.filename,
                        "supported": t.supported,
                        "suggested": (t.template_id in suggested),
                    }
                    for t in list_standard_templates()
                ]
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "contract_type": contract_type,
                        "suggested_template_ids": suggested,
                        "items": all_items,
                        "no_match_message": ("적합한 표준 템플릿 없음" if not suggested else None),
                    },
                )
                return

            if path.startswith("/api/revision/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[1] == "revision" and parts[2] == "suggest":
                    _json_response(self, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "use POST"})
                    return

            if path.startswith("/api/reviews/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    request_id = parts[2]
                    detail = repo.get_review_detail(request_id)
                    if not detail:
                        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                    _json_response(self, HTTPStatus.OK, detail)
                    return
                if len(parts) == 4 and parts[3] == "applied_rules":
                    request_id = parts[2]
                    detail = repo.get_review_detail(request_id)
                    if not detail:
                        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                    _json_response(self, HTTPStatus.OK, {"items": detail["applied_rules"]})
                    return

            if path.startswith("/api/question_sessions/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    session_id = parts[2]
                    try:
                        doc = load_session(session_id)
                    except Exception as exc:
                        _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                        return
                    safe = dict(doc)
                    safe.pop("text", None)
                    _json_response(self, HTTPStatus.OK, safe)
                    return

            if path == "/api/ep/status":
                ep_request_id = qs.get("ep_request_id", [""])[0] or None
                session_id = qs.get("session_id", [""])[0] or None
                if session_id:
                    doc = repo.get_ep_session_status(session_id)
                    if not doc:
                        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                    _json_response(self, HTTPStatus.OK, doc)
                    return
                if ep_request_id:
                    link = repo.get_ep_link(ep_request_id)
                    doc = None
                    if link and link.get("session_id"):
                        doc = repo.get_ep_session_status(str(link.get("session_id") or ""))
                        if doc is not None:
                            doc["link"] = link
                            doc["request_id"] = link.get("request_id")
                    if doc is not None:
                        _json_response(self, HTTPStatus.OK, doc)
                        return
                    latest = repo.get_latest_ep_status(ep_request_id)
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "ep_request_id": ep_request_id,
                            "status": (latest.get("status") if latest else None),
                            "latest": latest,
                            "link": link,
                        },
                    )
                    return
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ep_request_id or session_id required"})
                return

            if path == "/api/approval_queue":
                limit = int(qs.get("limit", ["50"])[0] or 50)
                offset = int(qs.get("offset", ["0"])[0] or 0)
                status = qs.get("status", [""])[0] or None
                entity = qs.get("entity", [""])[0] or None
                contract_type = qs.get("contract_type", [""])[0] or None
                risk_level = qs.get("risk_level", [""])[0] or None
                high_risk_only = (qs.get("high_risk_only", ["false"])[0] or "false").lower() == "true"
                approval_required_only = (
                    (qs.get("approval_required_only", ["false"])[0] or "false").lower() == "true"
                )
                items = repo.list_approval_queue(
                    limit=limit,
                    offset=offset,
                    status=status,
                    entity=entity,
                    contract_type=contract_type,
                    risk_level=risk_level,
                    high_risk_only=high_risk_only,
                    approval_required_only=approval_required_only,
                )
                _json_response(self, HTTPStatus.OK, {"count": len(items), "items": items})
                return

            if path.startswith("/api/approval_queue/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3:
                    request_id = parts[2]
                    detail = repo.get_approval_detail(request_id)
                    if not detail:
                        _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
                        return
                    _json_response(self, HTTPStatus.OK, detail)
                    return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"unknown path: {path}"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/upload":
                self._handle_upload(service)
                return
            if parsed.path == "/api/ep/session_start":
                self._handle_ep_session_start(service)
                return
            if parsed.path == "/api/ep/status/update":
                self._handle_ep_status_update()
                return
            if parsed.path == "/api/ep/handoff":
                self._handle_ep_handoff()
                return
            if parsed.path.startswith("/api/approval_queue/"):
                self._handle_approval_post(parsed.path)
                return
            if parsed.path.startswith("/api/question_sessions/"):
                self._handle_question_session_post(service, parsed.path)
                return
            if parsed.path == "/api/draft/generate":
                self._handle_draft_generate(service)
                return
            if parsed.path == "/api/draft/download":
                self._handle_draft_download(service)
                return
            if parsed.path == "/api/revision/suggest":
                self._handle_revision_suggest(service)
                return
            if parsed.path == "/api/revision/suggest_text":
                self._handle_revision_suggest_text(service)
                return
            if parsed.path == "/api/revision/download_docx":
                self._handle_revision_download_docx(service)
                return
            if parsed.path == "/api/revision/download_pdf":
                self._handle_revision_download_docx(service, output_format="pdf")
                return
            if parsed.path in ("/api/revision/download_redline", "/api/revision/download_clean"):
                self._handle_revision_download_redline(service, parsed.path)
                return
            if parsed.path == "/api/questions/generate":
                self._handle_questions_generate(service)
                return
            if parsed.path in ("/api/review/analyze", "/api/review/analyze_fast", "/api/review/analyze_deep"):
                self._handle_review_analyze_api(service, parsed.path)
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "unknown path"})
            return

        def _handle_review_analyze_api(self, service: RuleQueryService, path: str) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            entity = body.get("entity", "all")
            contract_type = body.get("contract_type", "all")
            text = body.get("text", "")
            filename = body.get("filename")
            review_focus = body.get("review_focus")
            review_focus = body.get("review_focus")
            answers = body.get("answers") if isinstance(body.get("answers"), dict) else None
            review_focus = body.get("review_focus")
            persist = body.get("persist") is True
            session_id0 = body.get("session_id")
            create_session0 = body.get("create_session")
            ai_mode = str(body.get("ai_mode") or "auto").strip().lower()
            law_mode = str(body.get("law_mode") or "auto").strip().lower()

            review_mode = "deep"
            if path.endswith("_fast"):
                review_mode = "fast"
            elif path.endswith("_deep"):
                review_mode = "deep"
            else:
                m = str(body.get("review_mode") or body.get("mode") or "").strip().lower()
                if m in ("fast", "deep"):
                    review_mode = m
                if body.get("fast_mode") is True:
                    review_mode = "fast"

            if _contains_wordprocessingml_markers(str(text)):
                _json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "WordprocessingML markers detected in input text (docx markup must not be analyzed)"},
                )
                return

            cache_payload = {
                "entity": str(entity or ""),
                "contract_type": str(contract_type or ""),
                "filename": str(filename or ""),
                "text_sha256": sha256(str(text or "").encode("utf-8", errors="replace")).hexdigest(),
                "answers": answers or {},
                "review_focus": (review_focus if isinstance(review_focus, str) else None),
                "review_mode": review_mode,
                "ai_mode": ai_mode if review_mode == "deep" else "off",
                "law_mode": law_mode if review_mode == "deep" else "off",
                "rules_sha": rules_sha,
            }
            cache_key = sha256(json.dumps(cache_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            now = time.time()
            if review_mode == "fast":
                hit = fast_review_cache.get(cache_key)
                if hit and (now - float(hit[0])) <= fast_review_cache_ttl_sec:
                    _json_response(self, HTTPStatus.OK, hit[1])
                    return
            else:
                hit = deep_review_cache.get(cache_key)
                if hit and (now - float(hit[0])) <= deep_review_cache_ttl_sec:
                    _json_response(self, HTTPStatus.OK, hit[1])
                    return

            if review_mode == "fast":
                bundle = build_clause_level_result(
                    service=service,
                    entity=str(entity),
                    contract_type=str(contract_type),
                    text=str(text),
                    filename=str(filename) if isinstance(filename, str) else None,
                    answers=answers,
                    review_focus=(review_focus if isinstance(review_focus, str) else None),
                    law_service=None,
                    ai_provider=None,
                    ai_model=None,
                    ai_timeout_sec=None,
                    ai_max_tokens=None,
                    ai_temperature=None,
                    max_clause_law_items=0,
                )
                from runtime.review.clause_level import apply_dealer_rental_final_gate as _fast_gate
                result = dict(bundle.review)
                result["mode"] = "fast"
                result["clause_results"] = _fast_gate(bundle.clause_results, str(contract_type or ""))
                result["clause_meta"] = bundle.meta
                result["law_search"] = {
                    "enabled": False,
                    "note": "fast_mode",
                    "queries": [],
                    "results": {"laws": [], "precedents": [], "interpretations": [], "admin_rules": [], "local_ordinances": []},
                    "errors": [],
                }
                result["ai"] = {
                    "enabled": False,
                    "provider": "mock",
                    "model": None,
                    "used": False,
                    "detail": {"enabled": False, "used": False, "selected_clause_ids": [], "selected_count": 0},
                }
                use_session = (isinstance(session_id0, str) and session_id0.strip()) or (create_session0 is True)
                if use_session:
                    sid = str(session_id0).strip() if isinstance(session_id0, str) and session_id0.strip() else None
                    if sid is None:
                        doc = create_text_session(
                            entity=str(entity),
                            contract_type=str(contract_type),
                            filename=str(filename) if isinstance(filename, str) else None,
                            text=str(text or ""),
                            review_focus=(review_focus if isinstance(review_focus, str) else None),
                            extraction={"success": True, "method": "api_review_fast"},
                            classification={"entity": str(entity), "contract_type": str(contract_type)},
                            detected_rule_ids=[],
                            questions=[],
                            source="review_analyze_fast",
                        )
                        sid = str(doc.get("session_id") or "")
                    if sid:
                        _ = save_answers(sid, dict(answers or {}))
                        doc2 = load_session(sid)
                        doc2["review_result_fast"] = result
                        doc2["review_result_fast_sig"] = cache_key
                        if isinstance(result.get("original_clauses"), list):
                            doc2["original_clauses"] = result.get("original_clauses")
                        save_session(doc2)
                        result["question_session_id"] = sid
                fast_review_cache[cache_key] = (now, result)
                if len(fast_review_cache) > fast_review_cache_max:
                    oldest_key = min(fast_review_cache.items(), key=lambda kv: kv[1][0])[0]
                    fast_review_cache.pop(oldest_key, None)
                _json_response(self, HTTPStatus.OK, result)
                return

            law_cfg = load_law_api_config()
            law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if law_cfg.enabled and law_cfg.api_key else None
            if law_mode == "off":
                law_service = None
            elif law_mode == "on" and law_service is None:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "law_mode=on but LAW_API is not configured"})
                return
            cfg = load_ai_config()
            ai_provider = create_ai_provider(cfg) if is_ai_enabled(cfg) else None
            if ai_mode == "off":
                ai_provider = None
            elif ai_mode == "on" and ai_provider is None:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ai_mode=on but OPENAI_API_KEY is not configured"})
                return

            _deep_t0 = time.perf_counter()
            try:
                bundle = build_clause_level_result(
                    service=service,
                    entity=str(entity),
                    contract_type=str(contract_type),
                    text=str(text),
                    filename=str(filename) if isinstance(filename, str) else None,
                    answers=answers,
                    review_focus=(review_focus if isinstance(review_focus, str) else None),
                    law_service=law_service,
                    ai_provider=ai_provider,
                    ai_model=cfg.model if ai_provider else None,
                    ai_timeout_sec=min(cfg.timeout_sec, 45.0) if ai_provider else None,
                    ai_max_tokens=min(max(cfg.max_tokens, 2000), 3200) if ai_provider else None,
                    ai_temperature=cfg.temperature if ai_provider else None,
                    max_clause_law_items=1,
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": sanitize_error_message(str(exc))})
                return
            from runtime.review.clause_level import apply_dealer_rental_final_gate as _deep_gate
            _detailed_profile0 = bundle.meta.get("detailed_contract_profile") if isinstance(bundle.meta, dict) else None
            _ct_code0 = str(_detailed_profile0.get("contract_type") or "") if isinstance(_detailed_profile0, dict) else ""
            result = dict(bundle.review)
            result["mode"] = "deep"
            _deep_cr = _deep_gate(bundle.clause_results, _ct_code0)
            if _ct_code0 == "dealer_rental_service_contract" and text:
                try:
                    from runtime.review.professional_assessment import run_professional_assessment as _prof_assess
                    _prof = _prof_assess(text=str(text), entity=str(entity or "퍼시스"))
                    _deep_cr = _prof["clause_results"]
                    result["dealer_rental_role_matrix"] = _prof.get("role_matrix", {})
                    result["dealer_rental_already_reflected"] = [f["rule_id"] for f in _prof.get("already_reflected", [])]
                    result["dealer_rental_six_section"] = _prof.get("six_section", {})
                except Exception:
                    pass
            # [UI/DOCX 동일 final_findings 요구, 2026-09-03 지시] — 딜러/위탁판매
            # 필수이슈 주입(_inject_mandatory_issues)은 지금까지 DOCX 다운로드
            # 핸들러에서만 호출되어, UI가 보여주는 clause_results에는 없던
            # finding이 DOCX에만 나타나는 불일치가 있었다. 이 함수는 멱등하게
            # 고쳤으므로(이미 주입된 항목은 재삽입하지 않음) UI 저장 시점에도
            # 동일하게 호출해 두 경로가 같은 입력에서 출발하게 한다.
            try:
                _deep_cr = _inject_mandatory_issues(
                    full_text=str(text),
                    clause_results=_deep_cr,
                    contract_type_code=_ct_code0,
                    clauses=list(bundle.clauses or []),
                )
            except Exception:
                pass
            from runtime.review.output_finalize import ensure_finding_ids as _ensure_finding_ids
            _ensure_finding_ids(_deep_cr)
            result["clause_results"] = _deep_cr
            result["clause_meta"] = bundle.meta
            # bundle.meta["final_findings"]는 _deep_gate/_prof_assess/mandatory
            # 이슈 주입으로 clause_results가 바뀌기 전에 계산된 값이라 stale하다
            # — UI 자신이 실제로 보여주는 _deep_cr 기준으로 다시 계산해 덮어써서,
            # UI가 보고하는 카운트/finding 목록이 자기 자신의 clause_results와
            # 항상 일치하게 한다(이후 DOCX 경로도 같은 build_final_findings를
            # 같은 종류의 입력에 호출하므로 두 경로가 비교 가능해진다).
            result["clause_meta"]["final_findings"] = _build_final_findings(_deep_cr, contract_type_code=_ct_code0)
            # [False-negative 재확인, 2026-09-04 지시] — bundle.meta["self_check"]는
            # _deep_gate/mandatory 이슈 주입 이전에 계산돼, 그 사이 새로 생긴
            # finding을 반영하지 못한 채 "HIGH=0/MEDIUM=0인데 위험 키워드가
            # 있다"는 stale한 REVIEW_FAILED_LIKELY_FALSE_NEGATIVE를 남길 수 있다
            # — _deep_cr 기준으로 다시 계산해 이제 실제 finding이 있으면 상태를
            # 정정하고, 여전히 없으면 그대로 유지한다(server.py 다운로드 게이트가
            # 이 최신 상태를 사용).
            try:
                from runtime.review.self_check import _FALSE_NEGATIVE_RISK_GROUPS as _fn_groups
                _deep_high = sum(1 for cr in _deep_cr if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is") and str(cr.get("risk_tier") or "").upper() == "HIGH")
                _deep_medium = sum(1 for cr in _deep_cr if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is") and str(cr.get("risk_tier") or "").upper() == "MEDIUM")
                if _deep_high == 0 and _deep_medium == 0:
                    _deep_triggered = [g for g, kws in _fn_groups.items() if any(kw in str(text or "") for kw in kws)]
                    if isinstance(result.get("clause_meta"), dict) and isinstance(result["clause_meta"].get("self_check"), dict):
                        _sc = result["clause_meta"]["self_check"]
                        _sc["zero_findings_but_risk_language_present"] = bool(_deep_triggered)
                        _sc["zero_findings_triggered_risk_groups"] = _deep_triggered
                        if _deep_triggered and _sc.get("review_status") == "OK":
                            _sc["review_status"] = "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE"
                            _sc["passed"] = False
                elif isinstance(result.get("clause_meta"), dict) and isinstance(result["clause_meta"].get("self_check"), dict):
                    _sc = result["clause_meta"]["self_check"]
                    if _sc.get("review_status") == "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE":
                        # false-negative 사유만 정정한다 — passed는 다른 독립적
                        # 실패 사유(scope_violations/type_confidence_low/
                        # incomplete_high/mandatory_targets/language_quality/
                        # global_reasoning/hard_integrity)가 없을 때만 True로
                        # 되돌려, 다른 진짜 실패를 함께 지워버리지 않는다.
                        _sc["review_status"] = "OK"
                        _sc["zero_findings_but_risk_language_present"] = False
                        _sc["zero_findings_triggered_risk_groups"] = []
                        _sc["passed"] = (
                            not _sc.get("scope_violations_stripped")
                            and not _sc.get("type_confidence_low")
                            and not _sc.get("incomplete_high_findings")
                            and not _sc.get("mandatory_targets_missing")
                            and not _sc.get("language_quality_violations")
                            and bool(_sc.get("global_reasoning_ok", True))
                            and int(_sc.get("clause_id_missing_count") or 0) == 0
                            and not _sc.get("final_findings_count_mismatch")
                        )
            except Exception:
                pass
            result["review_elapsed_sec"] = round(time.perf_counter() - _deep_t0, 2)
            if law_service is not None:
                try:
                    result["law_search"] = law_service.search_for_review(
                        entity=str(entity),
                        contract_type=str(contract_type),
                        text=str(text),
                        matched_rules=(bundle.review.get("matched_rules") if isinstance(bundle.review, dict) else None),
                        scope="contract",
                        max_per_type=2,
                        time_budget_sec=2.0,
                        contract_type_code=_ct_code0,
                        context={
                            "review_posture": (bundle.meta.get("review_posture") if isinstance(bundle.meta, dict) else None),
                            "party_role": (bundle.meta.get("party_role") if isinstance(bundle.meta, dict) else None),
                        },
                    )
                except Exception as exc:
                    result["law_search"] = {
                        "enabled": False,
                        "note": "law search failed",
                        "error": sanitize_error_message(str(exc)),
                    }
            else:
                result["law_search"] = {
                    "enabled": False,
                    "note": "LAW_API_ENABLED=false 또는 LAW_API_KEY 미설정",
                    "queries": [],
                    "results": {"laws": [], "precedents": [], "interpretations": [], "admin_rules": [], "local_ordinances": []},
                    "errors": [],
                }
            ai_enabled = bool(ai_provider) and is_ai_enabled(cfg)
            meta_ai = (bundle.meta.get("ai") if isinstance(bundle.meta, dict) else None) if isinstance(bundle.meta, dict) else None
            ai_used = bool(isinstance(meta_ai, dict) and meta_ai.get("used"))
            result["ai"] = {
                "enabled": ai_enabled,
                "provider": "openai" if ai_enabled else "mock",
                "model": cfg.model,
                "used": ai_used,
                "detail": meta_ai,
            }
            if persist:
                repo.save_review(
                    entity=entity,
                    contract_type=contract_type,
                    filename=filename,
                    source="api",
                    question_session_id=None,
                    rules_sha256=rules_sha,
                    rules_schema_version=rules_schema_version,
                    rules_source_path=rules_source_path,
                    review_result=result,
                    text=text,
                )
            use_session = True
            if create_session0 is False:
                use_session = False
            if isinstance(session_id0, str) and session_id0.strip():
                use_session = True
            if use_session:
                sid = str(session_id0).strip() if isinstance(session_id0, str) and session_id0.strip() else None
                if sid is None:
                    doc = create_text_session(
                        entity=str(entity),
                        contract_type=str(contract_type),
                        filename=str(filename) if isinstance(filename, str) else None,
                        text=str(text or ""),
                        review_focus=(review_focus if isinstance(review_focus, str) else None),
                        extraction={"success": True, "method": "api_review_deep"},
                        classification={"entity": str(entity), "contract_type": str(contract_type)},
                        detected_rule_ids=[],
                        questions=[],
                        source="review_analyze_deep",
                    )
                    sid = str(doc.get("session_id") or "")
                if sid:
                    _ = save_answers(sid, dict(answers or {}))
                    doc2 = load_session(sid)
                    doc2["review_result"] = result
                    doc2["review_result_sig"] = cache_key
                    if isinstance(result.get("original_clauses"), list):
                        doc2["original_clauses"] = result.get("original_clauses")
                    save_session(doc2)
                    result["question_session_id"] = sid

            deep_review_cache[cache_key] = (now, result)
            if len(deep_review_cache) > deep_review_cache_max:
                oldest_key = min(deep_review_cache.items(), key=lambda kv: kv[1][0])[0]
                deep_review_cache.pop(oldest_key, None)
            _json_response(self, HTTPStatus.OK, result)
            return

        def _handle_ep_status_update(self) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            ep_request_id = body.get("ep_request_id")
            session_id = body.get("session_id")
            status = body.get("status")
            note = body.get("note")
            from_status = body.get("from_status")

            if not isinstance(ep_request_id, str) or not ep_request_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ep_request_id is required"})
                return
            if session_id is not None and not isinstance(session_id, str):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id must be string"})
                return
            if not isinstance(status, str) or not is_valid_status(status):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid status"})
                return
            current_status = None
            resolved_session_id = session_id if isinstance(session_id, str) and session_id else None
            if resolved_session_id:
                doc = repo.get_ep_session_status(resolved_session_id)
                if doc and isinstance(doc.get("status"), str):
                    current_status = str(doc["status"])
            if current_status is None:
                latest = repo.get_latest_ep_status(ep_request_id)
                if latest and isinstance(latest.get("status"), str):
                    current_status = str(latest["status"])
                    if not resolved_session_id and isinstance(latest.get("session_id"), str) and latest.get("session_id"):
                        resolved_session_id = str(latest.get("session_id"))
            if current_status is None:
                current_status = "draft"

            if from_status is not None and isinstance(from_status, str) and from_status:
                if from_status != current_status:
                    _json_response(
                        self,
                        HTTPStatus.CONFLICT,
                        {
                            "error": "status conflict",
                            "current_status": current_status,
                            "provided_from_status": from_status,
                        },
                    )
                    return
            if not can_transition(current_status, status):
                _json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"invalid transition: {current_status} -> {status}"},
                )
                return

            try:
                repo.update_ep_status(
                    ep_request_id,
                    resolved_session_id,
                    status,
                    note if isinstance(note, str) else None,
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            _json_response(
                self,
                HTTPStatus.OK,
                {"ep_request_id": ep_request_id, "session_id": resolved_session_id, "status": status},
            )

        def _handle_ep_handoff(self) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            ep_request_id = body.get("ep_request_id")
            if not isinstance(ep_request_id, str) or not ep_request_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ep_request_id is required"})
                return
            force_approval = body.get("force_approval") is True
            client_mode = str(body.get("mode") or "stub")
            idempotency_key = body.get("idempotency_key") if isinstance(body.get("idempotency_key"), str) else None

            link = repo.get_ep_link(ep_request_id)
            if not link or not link.get("request_id"):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "no linked review request_id"})
                return

            request_id = str(link["request_id"])
            detail = repo.get_review_detail(request_id)
            if not detail:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "review not found"})
                return

            current_status = None
            linked_session_id = str(link.get("session_id") or "")
            if linked_session_id:
                st = repo.get_ep_session_status(linked_session_id)
                if st and isinstance(st.get("status"), str):
                    current_status = str(st.get("status") or "")
            if current_status is None:
                latest = repo.get_latest_ep_status(ep_request_id)
                if latest and isinstance(latest.get("status"), str):
                    current_status = str(latest.get("status") or "")
            if not current_status:
                current_status = "draft"

            if current_status not in ("aouribot_completed", "legal_review_pending"):
                _json_response(
                    self,
                    HTTPStatus.CONFLICT,
                    {
                        "error": "handoff not allowed in current status",
                        "current_status": current_status,
                        "allowed_statuses": ["aouribot_completed", "legal_review_pending"],
                    },
                )
                return

            payload = build_handoff_payload(ep_request_id, detail)
            target_status = "approval_pending" if (payload.approval_required or payload.high_risk) else "legal_review_pending"
            if force_approval:
                if current_status != "legal_review_pending":
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "force_approval is only allowed from legal_review_pending"},
                    )
                    return
                target_status = "approval_pending"

            if not can_transition(current_status, target_status):
                _json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": f"invalid transition: {current_status} -> {target_status}"},
                )
                return

            if not idempotency_key:
                idempotency_key = f"{payload.idempotency_key}:{target_status}"
            existing = repo.get_approval_handoff_by_idempotency(ep_request_id, idempotency_key)
            if existing and str(existing.get("status") or "") in ("sent", "routed_to_legal"):
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "handoff_payload": payload_to_dict(payload),
                        "decision": {
                            "target_status": target_status,
                            "condition": {
                                "approval_required": payload.approval_required,
                                "high_risk": payload.high_risk,
                                "force_approval": force_approval,
                            },
                        },
                        "persistence": {
                            "idempotency_key": idempotency_key,
                            "handoff_status": str(existing.get("status") or ""),
                            "attempt_count": int(existing.get("attempt_count") or 1),
                            "external_reference": existing.get("external_reference"),
                        },
                        "integration": {"mode": str(existing.get("mode") or client_mode), "endpoint": None},
                        "recovery": "idempotent hit; no new handoff executed",
                    },
                )
                return

            handoff_rec = repo.create_or_increment_approval_handoff(
                ep_request_id=ep_request_id,
                request_id=request_id,
                handoff_id=payload.handoff_id,
                idempotency_key=idempotency_key,
                target_status=target_status,
                mode=client_mode,
                payload_json=payload_to_dict(payload),
                initial_status="created",
            )

            resolved_session_id = linked_session_id if linked_session_id else None
            if target_status == "legal_review_pending":
                try:
                    repo.update_ep_status(ep_request_id, resolved_session_id, target_status, "routed_to_legal")
                except Exception:
                    pass
                try:
                    repo.update_approval_handoff_result(
                        int(handoff_rec.get("id") or 0),
                        status="routed_to_legal",
                        external_reference=None,
                        error_message=None,
                    )
                except Exception:
                    pass
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "handoff_payload": payload_to_dict(payload),
                        "decision": {
                            "target_status": target_status,
                            "condition": {
                                "approval_required": payload.approval_required,
                                "high_risk": payload.high_risk,
                                "force_approval": force_approval,
                            },
                        },
                        "persistence": {
                            "idempotency_key": idempotency_key,
                            "handoff_status": "routed_to_legal",
                            "attempt_count": int(handoff_rec.get("attempt_count") or 1),
                            "external_reference": None,
                        },
                        "integration": {"mode": "none", "endpoint": None},
                        "recovery": "legal review pending; later call again with force_approval=true",
                    },
                )
                return

            endpoint = body.get("endpoint") if isinstance(body.get("endpoint"), str) else None
            bearer_token = body.get("bearer_token") if isinstance(body.get("bearer_token"), str) else None
            timeout_sec_raw = body.get("timeout_sec")
            timeout_sec = 5.0
            if isinstance(timeout_sec_raw, (int, float)) and float(timeout_sec_raw) > 0:
                timeout_sec = float(timeout_sec_raw)

            if client_mode == "http":
                if not endpoint:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "endpoint is required for mode=http"})
                    return
                client = HttpApprovalClient(endpoint=endpoint, bearer_token=bearer_token, timeout_sec=timeout_sec)
            else:
                client = StubApprovalClient()
            client_result = client.submit(payload_to_dict(payload))
            if client_result.ok:
                try:
                    repo.update_ep_status(ep_request_id, resolved_session_id, target_status, "handoff_ok")
                except Exception:
                    pass
                try:
                    repo.update_approval_handoff_result(
                        int(handoff_rec.get("id") or 0),
                        status="sent",
                        external_reference=client_result.external_reference,
                        error_message=None,
                    )
                except Exception:
                    pass
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "handoff_payload": payload_to_dict(payload),
                        "decision": {
                            "target_status": target_status,
                            "condition": {
                                "approval_required": payload.approval_required,
                                "high_risk": payload.high_risk,
                                "force_approval": force_approval,
                            },
                        },
                        "persistence": {
                            "idempotency_key": idempotency_key,
                            "handoff_status": "sent",
                            "attempt_count": int(handoff_rec.get("attempt_count") or 1),
                            "external_reference": client_result.external_reference,
                        },
                        "integration": {"mode": client_mode, "endpoint": endpoint},
                        "recovery": "n/a",
                    },
                )
                return

            try:
                repo.update_approval_handoff_result(
                    int(handoff_rec.get("id") or 0),
                    status="failed",
                    external_reference=None,
                    error_message=client_result.error_message,
                )
            except Exception:
                pass

            _json_response(
                self,
                HTTPStatus.BAD_GATEWAY,
                {
                    "handoff_payload": payload_to_dict(payload),
                    "decision": {
                        "target_status": target_status,
                        "condition": {
                            "approval_required": payload.approval_required,
                            "high_risk": payload.high_risk,
                            "force_approval": force_approval,
                        },
                    },
                    "persistence": {
                        "idempotency_key": idempotency_key,
                        "handoff_status": "failed",
                        "attempt_count": int(handoff_rec.get("attempt_count") or 1),
                        "external_reference": None,
                    },
                    "integration": {"mode": client_mode, "endpoint": None},
                    "recovery": "on failure, keep status unchanged; retry with same idempotency_key",
                },
            )

        def _handle_revision_suggest(self, service: RuleQueryService) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            session_id = body.get("session_id")
            if isinstance(session_id, str) and session_id:
                try:
                    doc = load_session(session_id)
                except Exception as exc:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                review_result = run_review_with_session(service, session_id)
                entity = str((review_result.get("input") or {}).get("entity") or doc.get("entity") or "all") if isinstance(review_result, dict) else str(doc.get("entity", "all"))
                contract_type = str((review_result.get("input") or {}).get("contract_type") or doc.get("contract_type") or "all") if isinstance(review_result, dict) else str(doc.get("contract_type", "all"))
                filename = (doc.get("input") or {}).get("filename")
                clause_results = review_result.get("clause_results") if isinstance(review_result, dict) else []
                clause_meta = review_result.get("clause_meta") if isinstance(review_result, dict) else None
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "session_id": session_id,
                        "input": {"entity": entity, "contract_type": contract_type, "filename": filename},
                        "review_summary": (review_result.get("summary") if isinstance(review_result, dict) else None),
                        "revision": {
                            "summary": {"issue_clause_count": len(clause_results) if isinstance(clause_results, list) else 0},
                            "items": [],
                        },
                        "clause_results": clause_results if isinstance(clause_results, list) else [],
                        "meta": clause_meta if isinstance(clause_meta, dict) else {},
                    },
                )
                return

            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id is required"})

        def _handle_revision_suggest_text(self, service: RuleQueryService) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            entity = body.get("entity", "all")
            contract_type = body.get("contract_type", "all")
            text = body.get("text", "")
            filename = body.get("filename")
            answers = body.get("answers") if isinstance(body.get("answers"), dict) else None
            ai_mode = str(body.get("ai_mode") or "auto").strip().lower()
            law_mode = str(body.get("law_mode") or "auto").strip().lower()

            law_cfg = load_law_api_config()
            law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if law_cfg.enabled and law_cfg.api_key else None
            if law_mode == "off":
                law_service = None
            elif law_mode == "on" and law_service is None:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "law_mode=on but LAW_API is not configured"})
                return
            cfg = load_ai_config()
            ai_provider = create_ai_provider(cfg) if is_ai_enabled(cfg) else None
            if ai_mode == "off":
                ai_provider = None
            elif ai_mode == "on" and ai_provider is None:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ai_mode=on but OPENAI_API_KEY is not configured"})
                return

            bundle = build_clause_level_result(
                service=service,
                entity=str(entity),
                contract_type=str(contract_type),
                text=str(text),
                filename=str(filename) if isinstance(filename, str) else None,
                answers=answers,
                law_service=law_service,
                ai_provider=ai_provider,
                ai_model=cfg.model if ai_provider else None,
                ai_timeout_sec=cfg.timeout_sec if ai_provider else None,
                ai_max_tokens=min(max(cfg.max_tokens, 4000), 8000) if ai_provider else None,
                ai_temperature=cfg.temperature if ai_provider else None,
                max_clause_law_items=2,
            )
            # dealer_rental: API 응답에도 최종 gate 적용 (UI가 raw clause_results를 직접 읽으므로)
            from runtime.review.clause_level import apply_dealer_rental_final_gate as _resp_gate
            _resp_cr = _resp_gate(bundle.clause_results, str(contract_type or ""))
            _resp_extra: dict = {}
            if str(contract_type or "") == "dealer_rental_service_contract" and text:
                try:
                    from runtime.review.professional_assessment import run_professional_assessment as _prof_assess2
                    _prof2 = _prof_assess2(text=str(text), entity=str(entity or "퍼시스"))
                    _resp_cr = _prof2["clause_results"]
                    _resp_extra["dealer_rental_role_matrix"] = _prof2.get("role_matrix", {})
                    _resp_extra["dealer_rental_already_reflected"] = [f["rule_id"] for f in _prof2.get("already_reflected", [])]
                except Exception:
                    pass
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "input": {"entity": entity, "contract_type": contract_type, "filename": filename},
                    "review_summary": bundle.review.get("summary"),
                    "revision": bundle.revision,
                    "clause_results": _resp_cr,
                    "meta": bundle.meta,
                    **_resp_extra,
                },
            )

        def _handle_revision_download_docx(self, service: RuleQueryService, output_format: str = "docx") -> None:
            _is_pdf = output_format == "pdf"
            _out_ext = "pdf" if _is_pdf else "docx"
            _out_content_type = (
                "application/pdf" if _is_pdf
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            _out_filename = f"aouribot_revision.{_out_ext}"
            _builder = _build_legal_review_pdf if _is_pdf else _build_legal_review_docx
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            session_id = body.get("session_id")
            if isinstance(session_id, str) and session_id:
                try:
                    doc = load_session(session_id)
                except Exception as exc:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                entity = str(doc.get("entity", "all"))
                contract_type = str(doc.get("contract_type", "all"))
                filename = (doc.get("input") or {}).get("filename")
                review_focus = (doc.get("input") or {}).get("review_focus")
                text = str(doc.get("text", "") or "")
                answers = doc.get("answers") if isinstance(doc.get("answers"), dict) else {}
                ai_mode = str(body.get("ai_mode") or "auto").strip().lower()
                law_mode = str(body.get("law_mode") or "auto").strip().lower()

                law_cfg = load_law_api_config()
                law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if law_cfg.enabled and law_cfg.api_key else None
                if law_mode == "off":
                    law_service = None
                elif law_mode == "on" and law_service is None:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "law_mode=on but LAW_API is not configured"})
                    return
                cfg = load_ai_config()
                ai_provider = create_ai_provider(cfg) if is_ai_enabled(cfg) else None
                if ai_mode == "off":
                    ai_provider = None
                elif ai_mode == "on" and ai_provider is None:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ai_mode=on but OPENAI_API_KEY is not configured"})
                    return

                rebuild = body.get("rebuild") is True
                review_result = doc.get("review_result")
                if not (isinstance(review_result, dict) and isinstance(review_result.get("clause_results"), list)):
                    if rebuild:
                        # force=True — rebuild 를 눌렀는데 캐시를 돌려주면
                        # "다시 눌러도 같은 실패"가 된다(2026-09-09 실측).
                        review_result = run_review_with_session(service, session_id, force=True)
                    else:
                        _json_response(
                            self,
                            HTTPStatus.BAD_REQUEST,
                            {"error": "missing canonical review_result in session (set rebuild=true to recompute)"},
                        )
                        return
                elif rebuild:
                    review_result = run_review_with_session(service, session_id, force=True)

                clause_meta = review_result.get("clause_meta") if isinstance(review_result, dict) else None
                if isinstance(clause_meta, dict) and clause_meta.get("docx_allowed") is False:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "insufficient contract text for docx generation", "meta": clause_meta},
                    )
                    return

                # [검토 상태 → 차단이 아니라 제거·기록, 2026-09-10 지시 항목 2]
                # 종전에는 meta["review_status"] 에 REVIEW_FAILED_* 가 서 있으면
                # 곧바로 409 로 막았다(2026-09-09 지시 항목 13). 그런데 그 상태를
                # 세우는 게이트 대부분은 결함을 **제거할 수단이 있는데도** 상태만
                # 세우고 있었고(예: semantic gate 는 whitelist 밖 계약유형에서
                # 수정문안을 회수하지 않은 채 status 만 세움), 그 결과 사용자가
                # 몇 번을 다시 눌러도 같은 409 가 반복됐다.
                #
                # 이제 결함을 제거·중화할 수 있는 상태는 여기서 해소하고, 무엇이
                # 왜 빠졌는지는 문서 말미의 "자동 검증에서 보류·제외된 항목" 표에
                # 명시한다. 제거할 수 없는 상태만 종전처럼 409 로 막는다.
                _delivery = DeliveryReport()
                _meta_status = _remediate_review_status(clause_meta, _delivery)
                if _meta_status.startswith("REVIEW_FAILED"):
                    _json_response(
                        self,
                        HTTPStatus.CONFLICT,
                        {
                            "error": _meta_status,
                            "review_status": _meta_status,
                            "detail": (
                                str(clause_meta.get("review_status_detail") or "")
                                if isinstance(clause_meta, dict) else ""
                            ),
                            "final_lawyer_self_check": (
                                clause_meta.get("final_lawyer_self_check")
                                if isinstance(clause_meta, dict) else None
                            ),
                        },
                    )
                    return
                original_clauses = None
                if isinstance(review_result, dict) and isinstance(review_result.get("original_clauses"), list):
                    original_clauses = review_result.get("original_clauses")
                if not isinstance(original_clauses, list):
                    original_clauses = doc.get("original_clauses") if isinstance(doc.get("original_clauses"), list) else None
                if not isinstance(original_clauses, list):
                    original_clauses = [
                        {
                            "clause_id": c.clause_id,
                            "article_number": c.article_number,
                            "paragraph_number": c.paragraph_number,
                            "item_number": c.item_number,
                            "subitem_number": c.subitem_number,
                            "display_path": c.display_path,
                            "parent_clause_id": c.parent_clause_id,
                            "context_text": c.context_text,
                            "clause_title": c.title,
                            "text": c.text,
                        }
                        for c in (extract_clauses(text)[0] or [])
                    ]
                clause_results_for_docx = [
                    cr for cr in (review_result.get("clause_results") or [])
                    if isinstance(cr, dict) and not cr.get("is_checklist_item")
                ]
                checklist_items_for_docx = [
                    cr for cr in (review_result.get("clause_results") or [])
                    if isinstance(cr, dict) and cr.get("is_checklist_item")
                ]
                orig_ids = {str(c.get("clause_id") or "") for c in original_clauses if isinstance(c, dict)}
                cr_ids = {str(c.get("clause_id") or "") for c in clause_results_for_docx if isinstance(c, dict)}
                # Only a genuine segmented-clause id (KR-/EN-/P-, see
                # clause_extraction.is_real_segment_clause_id) that vanished between
                # extraction and review is an actual bug. Every other clause_id is a
                # rule-engine-synthesized finding id (clr_*, tsr_*, MI-/MR-, DLR-*,
                # isr_/pi_/svc_/sppc_/mi_/CP-, ...) that was never meant to appear in
                # original_clauses, so it can never legitimately be "missing" from it.
                missing_in_original = sorted([
                    cid for cid in cr_ids
                    if cid and cid not in orig_ids
                    and is_real_segment_clause_id(cid)
                ])
                if missing_in_original:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "consistency_check_failed: clause_id missing in original_clauses", "missing_clause_ids": missing_in_original[:20]},
                    )
                    return
                # changed_clause_ids check skipped: new legal-team writer handles all issues directly

                def _risk_tier_from_clause_result(cr: dict[str, Any]) -> str:
                    if bool(cr.get("approval_required")) or bool(cr.get("high_risk")):
                        return "HIGH"
                    rt = cr.get("risk_tier")
                    if isinstance(rt, str) and rt.strip().upper() in ("HIGH", "MEDIUM", "LOW"):
                        return rt.strip().upper()
                    return "MEDIUM" if bool(cr.get("unfavorable_to_us")) else "LOW"

                def _ui_visible(cr: dict[str, Any]) -> bool:
                    tier = str(cr.get("risk_tier") or "").strip().upper()
                    if tier not in ("HIGH", "MEDIUM", "LOW"):
                        tier = _risk_tier_from_clause_result(cr)
                    return bool(
                        cr.get("user_focus_hit")
                        or cr.get("factual_hit")
                        or cr.get("approval_required")
                        or cr.get("high_risk")
                        or tier in ("HIGH", "MEDIUM")
                    )

                def _docx_should_show(cr: dict[str, Any]) -> bool:
                    tier = _risk_tier_from_clause_result(cr)
                    if str(cr.get("display_kind") or "") in ("redline", "guidance", "keep"):
                        return True
                    if bool(cr.get("user_focus_hit")) or bool(cr.get("factual_hit")):
                        return True
                    if bool(cr.get("approval_required")) or bool(cr.get("high_risk")):
                        return True
                    if tier in ("HIGH", "MEDIUM"):
                        return True
                    if bool(cr.get("has_rewrite_change")):
                        return True
                    sr = cr.get("suggested_rewrite")
                    if isinstance(sr, str) and sr.strip():
                        return True
                    return False

                # UI-visible / missing_rewrite checks skipped: new legal-team writer handles filtering internally
                detected_rule_ids = [
                    r.get("rule_id")
                    for r in (review_result.get("matched_rules") or [])
                    if isinstance(r, dict) and isinstance(r.get("rule_id"), str)
                ]
                contract_law_search = None
                law_topics = None
                if law_service is not None:
                    try:
                        _canonical_type_code_for_law = ""
                        if isinstance(clause_meta, dict) and isinstance(clause_meta.get("detailed_contract_profile"), dict):
                            _canonical_type_code_for_law = str(clause_meta["detailed_contract_profile"].get("contract_type") or "")
                        contract_law_search = law_service.search_for_review(
                            entity=entity,
                            contract_type=contract_type,
                            text=text,
                            matched_rules=review_result.get("matched_rules") if isinstance(review_result, dict) else None,
                            scope="contract",
                            max_per_type=2,
                            contract_type_code=_canonical_type_code_for_law,
                            context={
                                "review_posture": (clause_meta.get("review_posture") if isinstance(clause_meta, dict) else None),
                                "party_role": (clause_meta.get("party_role") if isinstance(clause_meta, dict) else None),
                            },
                        )
                    except Exception:
                        contract_law_search = None
                if isinstance(contract_law_search, dict) and isinstance(contract_law_search.get("queries"), list):
                    law_topics = [str(x) for x in contract_law_search.get("queries") if isinstance(x, str)]
                _canonical_type_code_for_q = ""
                if isinstance(clause_meta, dict) and isinstance(clause_meta.get("detailed_contract_profile"), dict):
                    _canonical_type_code_for_q = str(clause_meta["detailed_contract_profile"].get("contract_type") or "")
                qs = generate_questions(
                    entity,
                    contract_type,
                    detected_rule_ids=detected_rule_ids,
                    law_topics=law_topics,
                    contract_text=text,
                    clause_results=review_result.get("clause_results") if isinstance(review_result, dict) else None,
                    max_questions=5,
                    review_focus=(review_focus if isinstance(review_focus, str) else None),
                    contract_type_code=_canonical_type_code_for_q,
                    question_plan=_build_question_plan(
                        entity=entity, contract_type=contract_type, text=text,
                        review_focus=review_focus, max_questions=5,
                    ),
                    transaction_type=_transaction_type_for(clause_meta, text),
                )
                try:
                    # ── legal-team pipeline: mandatory issues → severity → guardrail → new writer ──
                    # [분류기 재호출 금지] (2026-09-09 3차 지시 1·6항)
                    # 이 경로가 _classify_detailed 를 다시 돌리면 검토 때와 다른
                    # 계약유형이 나올 수 있고, 실제로 그렇게 됐다 — 리포트 상단은
                    # "장비 구매·설치 계약", 본문 법률분석은 "공사도급계약"(실측).
                    # 검토에서 확정한 canonical 값을 그대로 쓴다. 저장된 값이
                    # 없는 옛 세션만 재분류로 되돌린다.
                    _canonical_state_docx = (
                        clause_meta.get("canonical_state")
                        if isinstance(clause_meta, dict) else None
                    )
                    if not isinstance(_canonical_state_docx, dict):
                        _canonical_state_docx = None
                    _stored_profile = (
                        clause_meta.get("detailed_contract_profile")
                        if isinstance(clause_meta, dict) else None
                    )
                    if isinstance(_stored_profile, dict) and _stored_profile:
                        _detailed_profile = _StoredProfile(_stored_profile)
                    else:
                        _detailed_profile = _classify_detailed(
                            entity=entity,
                            contract_type=contract_type,
                            text=text,
                            filename=str(filename) if isinstance(filename, str) else None,
                        )
                    _ct_code = str(
                        (_canonical_state_docx or {}).get("contract_type")
                        or _detailed_profile.contract_type
                    )

                    # ── [UI/DOCX 단일 결과 객체, 2026-09-10 지시 항목 11] ──────────
                    # "DOCX/PDF 생성 과정에서 findings 재계산·재분룬·재생성
                    # 금지. UI 에서 확정된 finding id/severity/clause/issue/rewrite 를
                    # 그대로 사용." 검토 파이프라인이 이밌 확정해 세션에 저장한
                    # final_findings 가 있으면 그것이 정본이다. 이 경로가 필수이슈를
                    # 다시 주입하면 UI 가 보지 못한 항목이 문서에만 들어가 둘이
                    # 어긋난다 — 그것이 REVIEW_FAILED_OUTPUT_MISMATCH 의 원인이었다.
                    _stored_final = (
                        clause_meta.get("final_findings") if isinstance(clause_meta, dict) else None
                    )
                    _use_stored_findings = bool(
                        isinstance(_stored_final, dict)
                        and any(
                            isinstance(i, dict) and str(i.get("finding_id") or "").strip()
                            for i in (
                                list(_stored_final.get("high_issues") or [])
                                + list(_stored_final.get("medium_issues") or [])
                            )
                        )
                    )

                    # Combine regular + checklist results, inject mandatory issues
                    _all_results = list(clause_results_for_docx) + list(checklist_items_for_docx or [])
                    if not _use_stored_findings:
                        # 구버전 세션(final_findings 미저장)만 이 경로를 한다.
                        _all_results = _inject_mandatory_issues(
                            full_text=text,
                            clause_results=_all_results,
                            contract_type_code=_ct_code,
                            is_counterparty_form=True,
                            clauses=original_clauses,
                        )

                    # Severity reclassification for dealer contracts
                    _DEALER_CODES = {
                        "consignment_sales_agency", "direct_customer_sales_support",
                        "dealer_agency", "dealer_rental_service_contract",
                    }
                    # isr_*/sppc_* 딜러 계약 hard gate: dealer_rental은 완전 제거, 나머지는 LOW 강제
                    # canonical 분류(_ct_code)만 신뢰한다 — raw contract_type
                    # 라벨의 부분 문자열 매칭은 stale 라벨에 오염될 수 있어
                    # 제거함(2026-09-01).
                    _SUPPRESS_PREFIXES = ("isr_", "sppc_", "pi_", "svc_")
                    if _ct_code in _DEALER_CODES:
                        from runtime.review.clause_level import (
                            apply_dealer_rental_final_gate as _dlr_gate,
                            _DEALER_RENTAL_HARD_BLOCKED_IDS as _DLR_BLOCKED,
                        )
                        if _ct_code == "dealer_rental_service_contract":
                            # dealer_rental: professional assessment replaces generic findings
                            _all_results = _dlr_gate(_all_results, _ct_code)
                            try:
                                from runtime.review.professional_assessment import run_professional_assessment as _prof_assess3
                                _prof3 = _prof_assess3(text=str(text or ""), entity=str(entity or "퍼시스"))
                                _all_results = _prof3["clause_results"]
                            except Exception:
                                pass
                        else:
                            for _cr in _all_results:
                                if not isinstance(_cr, dict):
                                    continue
                                _cid = str(_cr.get("clause_id") or "")
                                if any(_cid.startswith(p) for p in _SUPPRESS_PREFIXES):
                                    _cr["risk_tier"] = "LOW"
                                    _cr["severity"] = "LOW"
                                    _cr["approval_required"] = False
                                    _cr["high_risk"] = False
                                    _cr["must_fix"] = False
                                    continue  # 재분류 루프 건너뜀
                                if _cr.get("is_mandatory"):
                                    continue
                                if bool(_cr.get("dedup_suppressed")) or bool(_cr.get("keep_as_is")):
                                    continue
                                _cur = str(_cr.get("risk_tier") or "LOW").upper()
                                _new, _ = _reclassify_consignment(
                                    severity=_cur,
                                    clause_text=str(_cr.get("original_text") or ""),
                                    clause_title=str(_cr.get("clause_title") or ""),
                                )
                                if _new != _cur:
                                    _cr["risk_tier"] = _new
                                    _cr["severity"] = _new
                                    if _new == "HIGH":
                                        _cr["high_risk"] = True
                                        _cr["must_fix"] = True

                    # Hallucination guardrail — clause_title 기반 identity 추론 후 조항별 문안 차단
                    for _cr in _all_results:
                        if not isinstance(_cr, dict) or _cr.get("is_mandatory"):
                            continue
                        # common_legal_risk.py/sales_transaction_rules.py의
                        # 결정론적 Layer-1 rule은 원문에 실제로 등장하는 문구를
                        # 정규식으로 직접 확인해 만든 고정밀 finding이므로,
                        # contract_type_code 오분류 하나로 "조항 주제와 수정문안
                        # 불일치"라 단정해 수정문안을 "자동수정 보류"로 덮어쓰면
                        # 안 된다 — output_filter.is_valid_issue()/self_check
                        # 백스톱/mandatory_issues에 이미 적용된 것과 동일한
                        # 예외를 이 지점에도 적용한다(2026-09-04, 실무 Redline
                        # 회귀에서 발견 — 손수 만든 수정문안이 전부 "자동수정
                        # 보류"로 대체되고 있었다).
                        if _cr.get("is_common_legal_risk"):
                            continue
                        _sr = str(_cr.get("suggested_rewrite") or "").strip()
                        if _sr:
                            _clause_title_lo = str(_cr.get("clause_title") or "").lower()
                            _clause_id = str(_cr.get("clause_identity") or "")
                            if not _clause_id:
                                if any(k in _clause_title_lo for k in ["해지", "종료", "해제"]):
                                    _clause_id = "termination"
                                elif any(k in _clause_title_lo for k in ["비밀", "기밀"]):
                                    _clause_id = "confidentiality"
                                elif any(k in _clause_title_lo for k in ["양도", "지위 이전", "계약자 변경"]):
                                    _clause_id = "assignment_party_change"
                                else:
                                    _clause_id = str(_cr.get("clause_id") or "")
                            _guard = _hg_check_revision(
                                _sr,
                                contract_type_code=_ct_code,
                                clause_identity=_clause_id,
                            )
                            if not _guard.is_clean:
                                # [2026-09-10 지시 항목 7] 자리표시자를 남기지 않고
                                # 원문의 법률효과를 유지한 최소수정안으로 교체한다.
                                _apply_minimal_edit(
                                    _cr,
                                    reason="조항 주제와 자동 생성 문안의 주제가 달라 교체했습니다.",
                                )

                    # [REVIEW_FAILED gate] Compute the SAME canonical final-
                    # findings the DOCX/PDF will actually contain
                    # (build_final_findings, shared with clause_level.py) and
                    # sanity-check it against the raw HIGH/MEDIUM tier counts
                    # already present in this same _all_results. _all_results
                    # has gone through extra, legitimate post-processing
                    # (mandatory-issue injection, severity reclassification,
                    # dealer gate, hallucination guardrail) that the initial
                    # review never applied, so a moderate count difference
                    # from the initial review's own final_findings is expected
                    # and NOT a bug — but the output-quality filter dropping
                    # nearly everything (e.g. 17 raw HIGH/MEDIUM candidates
                    # collapsing to 1 in the final output) is a pipeline
                    # malfunction, not an editorial choice, and must block
                    # rather than silently hand back a gutted file.
                    # [Mandatory Review Targets] review_focus에서 사용자가 직접
                    # 인용한 조항번호(예: "제5조 제2항 제1호")는 이 다운로드 경로가
                    # _all_results를 독립적으로 재구성하므로 여기서 다시 태깅해야
                    # 한다 — clause_level.py의 초기 리뷰 단계 태깅만으로는 이 경로에
                    # 반영되지 않는다. See mandatory_review_target.py.
                    from runtime.review.mandatory_review_target import (
                        annotate_and_track_mandatory_targets as _annotate_mandatory_targets,
                        check_all_targets_addressed as _check_mandatory_targets,
                    )
                    _mandatory_target_status = _annotate_mandatory_targets(
                        clause_results=_all_results,
                        clauses=original_clauses,
                        review_focus=(review_focus if isinstance(review_focus, str) else None),
                    )

                    # [Article 8.2류 잔존 오탐 제거, 2026-09-03 지시] — 이 다운로드
                    # 경로는 _all_results를 독립적으로 재구성(mandatory_issues
                    # 재주입 등)하므로, clause_level.py에서 한 번 실행된
                    # GLOBAL_CROSS_CLAUSE_VALIDATION/조항 자체 적정성 판단을
                    # 여기서도 백스톱으로 다시 적용해야 새로 바뀐 finding까지
                    # 검증된다.
                    from runtime.review.global_cross_clause_validation import apply_global_cross_clause_validation as _apply_gccv
                    from runtime.review.severity_reclassifier import demote_adequate_governing_law_dispute_clause as _demote_adequate_gld
                    _apply_gccv(_all_results, str(text or ""))
                    for _cr_gld in _all_results:
                        if not isinstance(_cr_gld, dict):
                            continue
                        if bool(_cr_gld.get("dedup_suppressed")) or bool(_cr_gld.get("keep_as_is")) or bool(_cr_gld.get("is_common_legal_risk")):
                            continue
                        _cur_sev_gld = str(_cr_gld.get("risk_tier") or "LOW").upper()
                        _new_sev_gld, _demoted_gld = _demote_adequate_gld(
                            severity=_cur_sev_gld,
                            clause_text=str(_cr_gld.get("original_text") or ""),
                            clause_title=str(_cr_gld.get("clause_title") or ""),
                            rewrite_reason=str(_cr_gld.get("rewrite_reason") or ""),
                            legal_business_reason=str(_cr_gld.get("legal_business_reason") or ""),
                        )
                        if _demoted_gld and _new_sev_gld != _cur_sev_gld:
                            _cr_gld["risk_tier"] = _new_sev_gld
                            _cr_gld["severity"] = _new_sev_gld
                            _cr_gld["high_risk"] = False
                            _cr_gld["approval_required"] = False
                            _cr_gld["must_fix"] = False
                            _cr_gld["keep_as_is"] = True

                    # [관할/준거법/중재 리스크 과대평가 방지, 2026-09-04 지시] —
                    # clause_level.py의 초기 리뷰에서 한 번 계산되지만, 이 다운로드
                    # 경로가 _all_results를 독립적으로 재구성하므로 여기서도 다시
                    # 적용해야 새로 바뀐/재주입된 finding까지 반영된다.
                    from runtime.review.jurisdiction_risk_calibration import (
                        calibrate_jurisdiction_finding_severity as _calibrate_jurisdiction,
                    )
                    for _cr_jr in _all_results:
                        if not isinstance(_cr_jr, dict):
                            continue
                        if bool(_cr_jr.get("dedup_suppressed")) or bool(_cr_jr.get("keep_as_is")) or bool(_cr_jr.get("is_common_legal_risk")):
                            continue
                        _cur_sev_jr = str(_cr_jr.get("risk_tier") or "LOW").upper()
                        _new_sev_jr, _calibrated_jr, _reason_jr = _calibrate_jurisdiction(
                            severity=_cur_sev_jr,
                            clause_text=str(_cr_jr.get("original_text") or ""),
                            full_text=str(text or ""),
                            clause_title=str(_cr_jr.get("clause_title") or ""),
                            rewrite_reason=str(_cr_jr.get("rewrite_reason") or ""),
                            legal_business_reason=str(_cr_jr.get("legal_business_reason") or ""),
                        )
                        if _calibrated_jr and _new_sev_jr != _cur_sev_jr:
                            _cr_jr["risk_tier"] = _new_sev_jr
                            _cr_jr["severity"] = _new_sev_jr
                            _cr_jr["high_risk"] = _new_sev_jr == "HIGH"
                            _cr_jr["approval_required"] = _new_sev_jr == "HIGH"
                            _cr_jr["must_fix"] = _new_sev_jr == "HIGH"
                            if _new_sev_jr == "LOW":
                                _cr_jr["keep_as_is"] = True
                            _cr_jr["jurisdiction_risk_calibration"] = _reason_jr

                    # [canonical_transaction_facts 최종 안전망 + 게이트,
                    # 2026-09-04 지시] — 이 다운로드 경로도 _all_results를
                    # 독립적으로 재구성하므로, clause_level.py의 초기 리뷰와
                    # 동일하게 사용자 답변으로 확정된 판매자/소유자 사실관계로
                    # 남은 자리표시자를 치환하고, 그래도 남아있으면 정상
                    # 완료를 차단한다(요청 4/5/8).
                    from runtime.review.canonical_transaction_facts import (
                        build_canonical_transaction_facts_from_answers as _build_facts_from_answers,
                        find_unresolved_fact_placeholders as _find_unresolved_placeholders,
                        resolved_mandatory_fields as _resolved_mandatory_fields,
                        substitute_resolved_placeholders as _substitute_placeholders,
                    )
                    _canonical_facts_docx = _build_facts_from_answers(answers)
                    _substitute_placeholders(_all_results, _canonical_facts_docx)
                    _resolved_mandatory_docx = _resolved_mandatory_fields(_canonical_facts_docx)
                    _unresolved_placeholders_docx = (
                        _find_unresolved_placeholders(_all_results, _canonical_facts_docx)
                        if _resolved_mandatory_docx else []
                    )
                    if _resolved_mandatory_docx and _unresolved_placeholders_docx:
                        # [제거·기록으로 전환, 2026-09-10 지시 항목 2] 담당자가
                        # 이미 답한 사실관계가 반영되지 않은 자리표시자("[판매자]"
                        # 등)가 남은 finding은, 그 **문안**을 믿을 수 없다는 뜻이지
                        # 문서 전체를 못 내보낸다는 뜻이 아니다. 해당 finding의
                        # 문안만 회수하고 문서에 그 사실을 밝힌다.
                        _placeholder_ids = sorted({
                            str(p.get("clause_id") or "") for p in _unresolved_placeholders_docx
                        } - {""})
                        for _cr_ph in _all_results:
                            if isinstance(_cr_ph, dict) and str(_cr_ph.get("clause_id") or "") in _placeholder_ids:
                                _withdraw_proposal(_cr_ph, status="REVIEW_FAILED_USER_FACTS_NOT_APPLIED")
                        _delivery.add(
                            "REVIEW_FAILED_USER_FACTS_NOT_APPLIED",
                            clause_ids=_placeholder_ids,
                            detail="담당자 확인 답변으로 확정된 사실관계가 문안에 반영되지 않았습니다.",
                        )

                    # [finding_id, 2026-09-03 지시] — 세션에서 로드된 항목은 이미
                    # UI 저장 시점에 부여된 finding_id를 그대로 유지하고, 이
                    # 경로에서만 새로 생긴 항목(있다면)에도 안정적 ID를 부여한다.
                    from runtime.review.output_finalize import ensure_finding_ids as _ensure_finding_ids_docx
                    _ensure_finding_ids_docx(_all_results)

                    # [실무 Redline 고도화, 2026-09-04 지시] — 이 다운로드
                    # 경로는 _all_results를 독립적으로 재구성하므로, clause_
                    # level.py의 초기 리뷰에서 각 rule이 직접 만든
                    # redline_instruction(있는 경우)은 그대로 두고, 없는
                    # HIGH/MEDIUM finding에는 여기서도 동일한 방식으로
                    # 일반적인 구조를 채운다. 그 후 완성도를 검증해 미완성
                    # (자동수정 보류/placeholder/위치 불명확)이면 다운로드를
                    # 차단한다.
                    # ── [Contract Semantic Scope + Finding 무결성 HARD GATE] ──
                    # (2026-09-08 지시, 항목 1·3·4·9) 이 다운로드 경로는
                    # _all_results를 독립적으로 재구성(mandatory_issues 재주입
                    # 등)하므로, clause_level.py에서 이미 한 번 적용된 계약유형
                    # rule whitelist / semantic gate / 조항참조 검증을 여기서도
                    # 다시 적용해야 한다 — 그렇지 않으면 초기 검토에서 제거된
                    # 계약유형 무관 finding이 다운로드 파일에서 되살아난다.
                    from runtime.review.contract_scope_policy import enforce_contract_scope as _enforce_scope_docx
                    from runtime.review.finding_integrity_gates import (
                        enforce_clause_semantic_gate as _enforce_semantic_docx,
                        enforce_valid_clause_references as _enforce_clause_refs_docx,
                    )
                    _scope_report_docx = _enforce_scope_docx(_all_results, contract_type_code=_ct_code)
                    _semantic_report_docx = _enforce_semantic_docx(_all_results, contract_type_code=_ct_code)
                    _clause_ref_report_docx = _enforce_clause_refs_docx(
                        _all_results, original_clauses, contract_type_code=_ct_code,
                    )

                    from runtime.review.redline_instruction import (
                        build_redline_instruction as _build_redline_docx,
                        is_incomplete_redline as _is_incomplete_redline_docx,
                        normalize_redline_instruction as _normalize_redline_docx,
                    )
                    # [2026-09-08 지시 항목 10] 신설 조항 권고를 "위치 확인
                    # 필요"로 끝내지 않는다 — 확인된 조 구조의 마지막 번호
                    # 다음 조로 위치를 지정한다(clause_level.py와 동일 규칙).
                    _last_article_docx = 0
                    for _c_last_docx in (original_clauses or []):
                        _raw_last_docx = str(
                            (_c_last_docx.get("article_number") if isinstance(_c_last_docx, dict) else None) or ""
                        ).strip()
                        if _raw_last_docx.isdigit():
                            _last_article_docx = max(_last_article_docx, int(_raw_last_docx))
                    _new_clause_fallback_docx = (
                        f"제{_last_article_docx}조 뒤에 제{_last_article_docx + 1}조 신설"
                        if _last_article_docx else "신설 조항 추가 — 위치 확인 필요"
                    )
                    for _cr_rl_docx in _all_results:
                        if not isinstance(_cr_rl_docx, dict) or bool(_cr_rl_docx.get("dedup_suppressed")):
                            continue
                        if str(_cr_rl_docx.get("risk_tier") or "").upper() not in ("HIGH", "MEDIUM"):
                            continue
                        if isinstance(_cr_rl_docx.get("redline_instruction"), dict):
                            _cr_rl_docx["redline_instruction"]["finding_id"] = str(_cr_rl_docx.get("finding_id") or "")
                            continue
                        _display_path_rl_docx = str(_cr_rl_docx.get("display_path") or "").strip()
                        _original_rl_docx = str(_cr_rl_docx.get("original_text") or "").strip()
                        _rewrite_rl_docx = str(
                            _cr_rl_docx.get("suggested_rewrite") or _cr_rl_docx.get("proposed_revision")
                            or _cr_rl_docx.get("recommendation_text") or ""
                        ).strip()
                        if not _rewrite_rl_docx:
                            continue
                        _is_new_clause_rl_docx = bool(_cr_rl_docx.get("is_checklist_item")) or not _original_rl_docx
                        if _is_new_clause_rl_docx:
                            _edit_type_rl_docx = "new_clause"
                            _edit_location_rl_docx = f"{_display_path_rl_docx} 뒤에 신설" if _display_path_rl_docx else _new_clause_fallback_docx
                        else:
                            _edit_type_rl_docx = "replace"
                            _edit_location_rl_docx = f"{_display_path_rl_docx} 교체" if _display_path_rl_docx else "위치 확인 필요 — 원문에서 해당 조항을 특정하지 못함"
                        _cr_rl_docx["redline_instruction"] = _build_redline_docx(
                            finding_id=str(_cr_rl_docx.get("finding_id") or ""),
                            clause_id=str(_cr_rl_docx.get("clause_id") or ""),
                            severity=str(_cr_rl_docx.get("risk_tier") or ""),
                            edit_location=_edit_location_rl_docx,
                            edit_type=_edit_type_rl_docx,
                            target_text=_original_rl_docx,
                            replacement_text=_rewrite_rl_docx,
                            original_text=_original_rl_docx,
                            reason=str(_cr_rl_docx.get("rewrite_reason") or _cr_rl_docx.get("legal_business_reason") or "").strip(),
                        )
                    # 룰이 스스로 만든 instruction 은 위에서 보존되므로,
                    # 게이트 검증 직전에 정규화한다 — 대응 조항이 없는 계약
                    # 전반 권고를 "위치 미상 교체" 가 아니라 "말미에 신설" 로
                    # 바로잡는다(2026-09-09: clr_conditional_funding_unclear
                    # 하나 때문에 수정본 다운로드 전체가 막혔다).
                    for _cr_norm in _all_results:
                        if isinstance(_cr_norm, dict) and _cr_norm.get("redline_instruction"):
                            _cr_norm["redline_instruction"] = _normalize_redline_docx(
                                _cr_norm["redline_instruction"]
                            )
                    # advisory_only(무결성 게이트가 문안을 의도적으로 회수한
                    # finding)는 "수정문안 없음"이 정상이므로 검사 대상이 아니다.
                    _incomplete_redline_ids_docx = [
                        str(cr.get("clause_id") or "")
                        for cr in _all_results
                        if isinstance(cr, dict) and not bool(cr.get("dedup_suppressed"))
                        and not _is_advisory_only(cr)
                        and str(cr.get("risk_tier") or "").upper() in ("HIGH", "MEDIUM")
                        and _is_incomplete_redline_docx(cr.get("redline_instruction"))
                    ]
                    if _incomplete_redline_ids_docx:
                        # [제거·기록으로 전환, 2026-09-10 지시 항목 2] 수정 위치나
                        # 문구가 확정되지 않은 것은 그 항목의 **문안** 문제다.
                        # 불완전한 문안을 Word 에 넣지 않되, 문제 제기는 검토의견
                        # 으로 남기고 무엇이 보류됐는지 문서에 밝힌다.
                        for _cr_ir in _all_results:
                            if isinstance(_cr_ir, dict) and str(_cr_ir.get("clause_id") or "") in _incomplete_redline_ids_docx:
                                _withdraw_proposal(_cr_ir, status="REVIEW_FAILED_INCOMPLETE_REDLINE")
                        _delivery.add(
                            "REVIEW_FAILED_INCOMPLETE_REDLINE",
                            clause_ids=_incomplete_redline_ids_docx,
                            detail="수정 위치·방식·완성문구를 자동으로 확정하지 못했습니다.",
                        )

                    # ── [canonical 결과 재추론 금지, 2026-09-11 지시] ──────────
                    # "상대방 역할·계약유형·적용법률은 한 번 확정한 canonical 값만
                    # 사용하고 downstream 에서 다시 추론하지 말 것. 최종 UI/DOCX 는
                    # 동일한 canonical finding 만 사용."
                    #
                    # 아래 게이트들은 검토 파이프라인에서 이미 한 번 돌았다. UI 가
                    # 확정한 결과(`_use_stored_findings`)가 있는데 여기서 다시 돌리면
                    # 게이트가 finding 을 변형·회수해 문서 본문이 화면과 어긋난다 —
                    # 같은 게이트를 두 번 적용하는 것이 곧 재추론이다.
                    #
                    # 그래서 재적용 대상을 **final_findings 를 저장하지 않은 옛
                    # 세션**으로 한정한다. 그 경로는 여기서 _all_results 를
                    # 독립적으로 재구성하므로 게이트를 다시 걸어야 비적용 법률
                    # finding 등이 되살아나지 않는다. UI 확정본이 있으면 빈
                    # 리스트를 넘겨 게이트를 무효화한다 — 게이트를 지우는 것이
                    # 아니라 정본을 건드리지 않게 하는 것이다.
                    _gate_targets = [] if _use_stored_findings else _all_results

                    # [법률 적용요건 게이트 재적용, 2026-09-10 지시] 이 경로는
                    # _all_results 를 독립적으로 재구성(mandatory_issues 재주입 등)
                    # 하므로, 검토 단계에서 비적용으로 확정된 법률의 finding 이
                    # 다운로드 파일에서 되살아날 수 있다. 같은 게이트를 다시 건다.
                    # [2026-09-11 지시] "적용법률은 한 번 확정한 canonical 값만
                    # 사용하고 downstream 에서 다시 추론하지 말 것." 여기서
                    # assess_statutes 를 다시 돌리면 검토 화면과 문서가 서로 다른
                    # 법률 판단을 근거로 삼을 수 있다 — 계약유형·당사자 지위에서
                    # 이미 같은 사고가 났던 지점이다.
                    from runtime.review.statute_applicability_gate import (
                        deactivate_inapplicable_statute_findings as _deactivate_statute_docx,
                    )
                    _statute_decisions_docx = _statute_decisions_for(
                        clause_meta,
                        entity=str(entity or ""),
                        text=str(text or ""),
                        contract_type_code=_ct_code,
                    )
                    _statute_removed_docx = _deactivate_statute_docx(_gate_targets, _statute_decisions_docx)
                    if _statute_removed_docx:
                        _delivery.add(
                            "STATUTE_NOT_APPLICABLE",
                            clause_ids=[str(r.get("clause_id") or "") for r in _statute_removed_docx],
                            reason="법률 적용요건 미충족으로 해당 법률 관련 지적을 제외함",
                            detail=str(_statute_removed_docx[0].get("reason") or ""),
                        )

                    # [우리에게 유리한 조항 보호, 2026-09-10 지시] 이 경로도
                    # 문안을 재구성하므로 같은 보호를 다시 건다.
                    from runtime.review.our_side_protection import (
                        enforce_our_side_protection as _enforce_our_side_docx,
                    )
                    _our_side_withdrawn_docx = _enforce_our_side_docx(
                        _gate_targets,
                        statute_decisions=[d.to_dict() for d in _statute_decisions_docx],
                    )
                    if _our_side_withdrawn_docx:
                        _delivery.add(
                            "OUR_SIDE_RIGHT_WEAKENED",
                            clause_ids=[str(w.get("clause_id") or "") for w in _our_side_withdrawn_docx],
                            reason="우리 회사에 유리한 현행 조항을 약화시키는 수정안을 보류함",
                            detail="원문이 상대방의 청구를 차단하고 있는데 수정안이 예외를 신설했습니다.",
                        )

                    # [상대방 권리 신설 차단, 2026-09-11 지시] 위 보호가 "기존
                    # 차단이 풀리는" 경우를 본다면, 이것은 원문에 없던 이의권·
                    # 방어권·시정기간·책임제한이 상대방에게 새로 생기는 경우를
                    # 본다. 다운로드 경로도 문안을 재구성하므로 같이 건다.
                    from runtime.review.clause_direction import (
                        we_perform_first as _we_perform_first_docx,
                    )
                    from runtime.review.counterparty_grant_guard import (
                        enforce_no_new_counterparty_rights as _enforce_no_new_rights_docx,
                    )
                    from runtime.review.group_entities import (
                        our_side_labels as _group_labels_docx,
                    )
                    from runtime.review.transaction_consistency import (
                        CONSIDERATION_NON_MONETARY as _NON_MONETARY_DOCX,
                        classify_consideration_structure as _classify_consideration_docx,
                    )

                    _our_labels_docx = tuple(dict.fromkeys(
                        x for x in (
                            *(
                                str(y) for r in _all_results
                                if isinstance(r, dict) and isinstance(r.get("our_labels"), list)
                                for y in r["our_labels"]
                            ),
                            str(entity or ""),
                            *_group_labels_docx(str(text or ""), entity=str(entity or "")),
                        ) if str(x or "").strip()
                    ))
                    _grant_blocked_docx = _enforce_no_new_rights_docx(
                        _gate_targets,
                        statute_decisions=[d.to_dict() for d in _statute_decisions_docx],
                        our_labels=_our_labels_docx,
                        we_perform_first=_we_perform_first_docx(
                            str(text or ""),
                            is_non_monetary=(
                                _classify_consideration_docx(str(text or ""))
                                == _NON_MONETARY_DOCX
                            ),
                        ),
                    )
                    if _grant_blocked_docx:
                        _delivery.add(
                            "COUNTERPARTY_GRANT_BLOCKED",
                            clause_ids=[
                                str(b.get("clause_id") or "") for b in _grant_blocked_docx
                            ],
                            reason="상대방에게 없던 권리를 새로 부여하는 수정안을 보류함",
                            detail=str(
                                "; ".join(_grant_blocked_docx[0].get("reasons") or [])
                            ),
                        )

                    # [거래실질 정합성, 2026-09-10 지시] 현금 대가가 없는 교환
                    # 구조에 대금 지급 전제의 템플릿 문안이 들어가지 않게 한다.
                    from runtime.review.transaction_consistency import (
                        check_transaction_consistency as _check_txn_docx,
                    )
                    _txn_report_docx = _check_txn_docx(_gate_targets, contract_text=str(text or ""))
                    if _txn_report_docx.get("withdrawn"):
                        _delivery.add(
                            "TRANSACTION_STRUCTURE_MISMATCH",
                            clause_ids=[str(w.get("clause_id") or "") for w in _txn_report_docx["withdrawn"]],
                            reason="거래 구조(무현금 교환)와 모순되는 수정문안을 보류함",
                        )

                    # [에이전트 등급 복원, 2026-09-10 항목 3 — clause_level.py와
                    # 동일 원칙] 이 경로도 _all_results 를 독립적으로 재구성하며
                    # 그 과정에서 강등 로직을 다시 태우므로, 여기서도 인용 검증을
                    # 마친 사내변호사 논점의 등급을 에이전트 판단으로 되돌린다.
                    for _cr_cs in _all_results:
                        if not isinstance(_cr_cs, dict) or not _cr_cs.get("is_counsel_agent"):
                            continue
                        if bool(_cr_cs.get("dedup_suppressed")) or bool(_cr_cs.get("keep_as_is")):
                            continue
                        _want_cs = str(_cr_cs.get("counsel_severity") or "").upper()
                        if _want_cs in ("HIGH", "MEDIUM"):
                            _cr_cs["risk_tier"] = _want_cs
                            _cr_cs["severity"] = _want_cs

                    # [항목 11] UI 가 확정한 결과가 있으면 그것이 정본이다.
                    # 재계산본은 아래 검증에서 문서와 화면이 같은지 비교하는 데만 쓰고,
                    # 생성되는 문서에는 화면과 **같은** 객체를 넣는다.
                    _docx_final_recomputed = _build_final_findings(
                        _all_results, contract_type_code=_ct_code, include_low=False,
                    )
                    _docx_final = (
                        dict(_stored_final) if _use_stored_findings else _docx_final_recomputed
                    )
                    _docx_high = int(_docx_final.get("high_count") or 0)
                    _docx_medium = int(_docx_final.get("medium_count") or 0)
                    _raw_high = sum(
                        1 for cr in _all_results
                        if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
                        and str(cr.get("risk_tier") or "").upper() == "HIGH"
                    )
                    _raw_medium = sum(
                        1 for cr in _all_results
                        if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
                        and str(cr.get("risk_tier") or "").upper() == "MEDIUM"
                    )
                    _raw_total = _raw_high + _raw_medium
                    _docx_total = _docx_high + _docx_medium

                    # ── [전달 정합성 검증, 2026-09-10 아키텍처 지시 항목 11] ──────
                    # UI 확정본을 정본으로 삼는 대신, 그 항목들이 실제 조항
                    # 데이터에 대응하는지는 전달 직전에 확인해야 한다. 대응하는
                    # clause_result 의 원문·문제점이 비어 있으면 문서에는 빈
                    # 껍데기가 실린다 — 그런 항목은 내보내지 않고 그 사실을 밝힌다.
                    if _use_stored_findings:
                        _live_by_fid = {
                            str(cr.get("finding_id") or ""): cr
                            for cr in _all_results
                            if isinstance(cr, dict) and str(cr.get("finding_id") or "")
                        }

                        def _resolves(item: Any) -> bool:
                            if not isinstance(item, dict):
                                return False
                            src = _live_by_fid.get(str(item.get("finding_id") or ""))
                            if src is None:
                                # 대응 항목을 못 찾으면 UI 가 담고 있는 내용으로 판단한다.
                                return bool(
                                    str(item.get("original_text") or "").strip()
                                    and str(item.get("problem") or "").strip()
                                )
                            return bool(
                                str(src.get("original_text") or "").strip()
                                and str(
                                    src.get("problem") or src.get("rewrite_reason") or ""
                                ).strip()
                            )

                        _hollow: list[str] = []
                        for _sev_key in ("high_issues", "medium_issues"):
                            _kept_items = []
                            for _it in (_docx_final.get(_sev_key) or []):
                                if _resolves(_it):
                                    _kept_items.append(_it)
                                else:
                                    _hollow.append(
                                        str(
                                            (_it or {}).get("clause_id")
                                            or (_it or {}).get("finding_id")
                                            or ""
                                        )
                                    )
                            _docx_final[_sev_key] = _kept_items
                        if _hollow:
                            _docx_final["high_count"] = len(_docx_final.get("high_issues") or [])
                            _docx_final["medium_count"] = len(_docx_final.get("medium_issues") or [])
                            _docx_final["top_risks"] = [
                                t for t in (_docx_final.get("top_risks") or []) if _resolves(t)
                            ]
                            _docx_high = int(_docx_final.get("high_count") or 0)
                            _docx_medium = int(_docx_final.get("medium_count") or 0)
                            _docx_total = _docx_high + _docx_medium
                            _delivery.add(
                                "REVIEW_FAILED_OUTPUT_MISMATCH",
                                clause_ids=[c for c in _hollow if c][:10],
                                reason="원문·문제점이 비어 있어 문서에 실을 수 없는 항목을 제외함",
                                detail=(
                                    f"화면 확정본의 {len(_hollow)}건이 대응 조항 데이터를 갖고 있지 "
                                    "않아 문서에서 제외했습니다. 검토를 다시 실행해 주십시오."
                                ),
                            )

                    if _raw_total >= 5 and _docx_total <= max(1, _raw_total // 5):
                        # [collapse 는 차단이 아니라 복구로 처리, 2026-09-10 지시 항목 2]
                        # collapse 는 "출력 필터가 정상 finding 을 대량으로 떨어뜨렸다"는
                        # **탐지 누락**의 증상이다. 여기서 409 를 내면 사용자는 아무것도
                        # 못 받고, 떨어뜨린 원인도 그대로 남는다. 그래서 계약유형 기반
                        # 금지문구 필터(is_valid_issue Gate 4)를 끄고 한 번 더 만들어,
                        # 유형 오분류 때문에 걸러진 항목을 되살린다. 그래도 회복되지
                        # 않으면 최소한 되살린 쪽을 내보내고 그 사실을 문서에 밝힌다.
                        _docx_final_recovered = _build_final_findings(
                            _all_results, contract_type_code="", include_low=False,
                        )
                        _rec_total = (
                            int(_docx_final_recovered.get("high_count") or 0)
                            + int(_docx_final_recovered.get("medium_count") or 0)
                        )
                        if _rec_total > _docx_total:
                            _docx_final = _docx_final_recovered
                            _docx_high = int(_docx_final.get("high_count") or 0)
                            _docx_medium = int(_docx_final.get("medium_count") or 0)
                            _docx_total = _docx_high + _docx_medium
                        _delivery.add(
                            "REVIEW_FAILED",
                            detail=(
                                f"출력 필터가 검토항목 대부분을 제외했습니다"
                                f"(원본 HIGH/MEDIUM {_raw_total}건 → 문서 {_docx_total}건). "
                                "계약유형 기반 문구 필터를 해제하고 복구했습니다."
                            ),
                            reason="검토항목 다수가 자동 필터에서 제외되어 복구 후 문서를 생성함",
                        )

                    # [REVIEW_FAILED_OUTPUT_MISMATCH gate, 2026-09-03 지시] — UI가
                    # 저장한 clause_meta.final_findings(Phase 1에서 이제 UI 자신의
                    # clause_results 기준으로 신선하게 재계산됨)와 이 다운로드
                    # 경로가 방금 만든 _docx_final을 finding_id/severity/count
                    # 기준으로 비교한다. 세션이 이 기능 도입 이전에 생성돼
                    # final_findings이 없거나 finding_id가 없는 구버전 데이터는
                    # 비교 대상에서 제외한다(하위호환 — 새로 생성된 리뷰부터 적용).
                    _ui_final = clause_meta.get("final_findings") if isinstance(clause_meta, dict) else None
                    if isinstance(_ui_final, dict):
                        def _fid_severity_map(final_findings: dict[str, Any]) -> dict[str, str]:
                            out_map: dict[str, str] = {}
                            for _sev_key, _sev_label in (("high_issues", "HIGH"), ("medium_issues", "MEDIUM")):
                                for _i in (final_findings.get(_sev_key) or []):
                                    if isinstance(_i, dict):
                                        _fid = str(_i.get("finding_id") or "")
                                        if _fid:
                                            out_map[_fid] = _sev_label
                            return out_map
                        _ui_map = _fid_severity_map(_ui_final)
                        _docx_map = _fid_severity_map(_docx_final)
                        # finding_id가 하나도 없는 쪽(구버전 데이터)은 비교 불가 —
                        # 새로 부여된 리뷰만 이 게이트의 대상이 된다.
                        if _ui_map and _docx_map:
                            _ui_count = int(_ui_final.get("high_count") or 0) + int(_ui_final.get("medium_count") or 0)
                            _docx_count = _docx_total
                            _severity_mismatches = {
                                fid: (sev, _docx_map[fid])
                                for fid, sev in _ui_map.items()
                                if fid in _docx_map and _docx_map[fid] != sev
                            }
                            if set(_ui_map) != set(_docx_map) or _ui_count != _docx_count or _severity_mismatches:
                                # [항목 11 — UI 가 정본, 2026-09-10 아키텍처 지시]
                                # "UI 에서 확정된 finding id/severity/clause/issue/
                                # rewrite 를 그대로 사용." 다운로드 경로의 재계산이
                                # 다르더라도 담당자가 검토하고 확정한 것은 화면이므로
                                # 화면을 정본으로 삼는다. 종전에는 반대로 문서 쪽
                                # 재계산을 정본으로 삼았는데, 그러면 담당자가 보지
                                # 못한 항목이 문서에만 들어가거나 확인한 항목이
                                # 문서에서 빠지는 일이 생긴다.
                                #
                                # 재계산본이 달라졌다는 사실 자체가 파이프라인
                                # 불안정 지표이므로 그것도 문서에 남긴다.
                                _docx_final = dict(_ui_final)
                                _delivery.add(
                                    "REVIEW_FAILED_OUTPUT_MISMATCH",
                                    detail=(
                                        f"화면 {_ui_count}건 / 문서 재계산 {_docx_count}건으로 달라 "
                                        "화면에서 확정된 결과를 기준으로 통일했습니다."
                                    ),
                                )

                    # [REVIEW_FAILED_OUTPUT_FACT_MISMATCH gate, 2026-09-04
                    # 지시, 요청 9] — UI가 저장한 canonical_transaction_facts
                    # (사용자가 답변한 seller/owner_of_goods 등)와 이 다운로드
                    # 경로가 answers로부터 직접 재구성한 facts가 서로 다르면,
                    # Word에 표시될 계약구조가 UI에서 확인한 사실관계와
                    # 어긋난다는 뜻이므로 다운로드를 차단한다.
                    _ui_facts = clause_meta.get("canonical_transaction_facts") if isinstance(clause_meta, dict) else None
                    if isinstance(_ui_facts, dict) and _ui_facts:
                        _fact_mismatches = {
                            k: (_ui_facts.get(k), _canonical_facts_docx.get(k))
                            for k in set(_ui_facts) | set(_canonical_facts_docx)
                            if _ui_facts.get(k) and _canonical_facts_docx.get(k) and _ui_facts.get(k) != _canonical_facts_docx.get(k)
                        }
                        if _fact_mismatches:
                            # [제거·기록으로 전환, 2026-09-10 지시 항목 2]
                            # 담당자가 UI에서 확인한 사실관계가 정본이다. 문서를
                            # 그 값으로 맞추고(재구성본이 아니라), 차이가 있었다는
                            # 사실을 문서에 남긴다.
                            _canonical_facts_docx = {**_canonical_facts_docx, **{
                                k: v for k, v in _ui_facts.items() if v
                            }}
                            _substitute_placeholders(_all_results, _canonical_facts_docx)
                            _delivery.add(
                                "REVIEW_FAILED_OUTPUT_FACT_MISMATCH",
                                detail=(
                                    "화면에서 확인된 거래 사실관계와 문서 재구성 값이 달라 "
                                    "화면 확인값을 기준으로 통일했습니다: "
                                    + ", ".join(sorted(_fact_mismatches)[:5])
                                ),
                            )

                    _final_findings_clause_ids = {
                        str(i.get("clause_id") or "")
                        for i in (list(_docx_final.get("high_issues") or []) + list(_docx_final.get("medium_issues") or []))
                        if isinstance(i, dict)
                    }
                    _targets_ok, _missing_targets = _check_mandatory_targets(
                        _mandatory_target_status, final_findings_clause_ids=_final_findings_clause_ids,
                    )
                    if not _targets_ok:
                        # [제거·기록으로 전환, 2026-09-10 지시 항목 2] 담당자가
                        # 인용한 조항이 최종 결과에 없다는 것은 문서를 못 만든다는
                        # 뜻이 아니라, 그 조항에 대해 "검토했지만 별도 지적사항
                        # 없음"인지 "놓쳤는지"를 담당자가 알아야 한다는 뜻이다.
                        # 문서 말미에 그 조항들을 명시한다.
                        _delivery.add(
                            "REVIEW_FAILED_USER_REQUEST_MISSING",
                            clause_ids=[str(x) for x in (_missing_targets or [])][:10],
                            detail=(
                                "담당자가 인용한 조항이 최종 검토항목에 포함되지 않았습니다 — "
                                "지적사항이 없어 제외된 것인지 직접 확인이 필요합니다."
                            ),
                        )

                    # [REVIEW_FAILED_USER_SCOPE_NOT_COVERED gate, 2026-09-08 지시 항목 2]
                    # 사용자가 제시한 검토 쟁점(및 계약유형별 기본 이슈맵)은 각각
                    # 적정/수정 필요/별도계약 필요 중 하나로 반드시 답변되어야
                    # 한다. 위 _check_mandatory_targets는 "조항번호"를 인용한
                    # 요청만 검증하므로, "쟁점"을 서술한 요청은 여기서 별도로
                    # 검증한다.
                    from runtime.review.mandatory_review_issues import (
                        REVIEW_FAILED_USER_SCOPE_NOT_COVERED as _USER_SCOPE_FAIL,
                        answer_mandatory_review_issues as _answer_issues_docx,
                        check_all_issues_answered as _check_issues_docx,
                        derive_mandatory_review_issues as _derive_issues_docx,
                    )
                    _issue_answers_docx = _answer_issues_docx(
                        _derive_issues_docx(
                            contract_type_code=_ct_code,
                            review_focus=(review_focus if isinstance(review_focus, str) else None),
                        ),
                        clause_results=_all_results,
                        full_text=str(text or ""),
                    )
                    # [사용자 자유서술 요청 coverage, 2026-09-08 지시]
                    # 최초 검토에서 이미 의미 파싱해 둔 쟁점을 복원해, 이
                    # 경로가 재구성한 _all_results에 대해 다시 답변한다 —
                    # LLM을 다시 호출하지 않으면서도 UI와 다운로드 파일의
                    # 판단이 어긋나지 않게 한다.
                    from runtime.review.user_review_request import (
                        build_user_request_coverage as _build_user_coverage_docx,
                        check_user_request_coverage as _check_user_coverage_docx,
                        issues_from_meta as _user_issues_from_meta,
                        link_clauses_to_issues as _link_user_issues_docx,
                    )
                    _user_parse_meta_docx = (
                        clause_meta.get("user_review_request_parse") if isinstance(clause_meta, dict) else None
                    )
                    _user_issues_docx = _user_issues_from_meta(_user_parse_meta_docx)
                    if _user_issues_docx:
                        _link_user_issues_docx(_user_issues_docx, original_clauses)
                    _user_coverage_docx = _build_user_coverage_docx(
                        _user_issues_docx,
                        clause_results=_all_results,
                        clauses=original_clauses,
                        catalog_answers=_issue_answers_docx,
                        # 이 경로도 적용요건 게이트를 다시 돌리므로 그 결론을
                        # 사용자 법률 질문의 답으로 그대로 쓴다(2026-09-10).
                        statute_decisions=[d.to_dict() for d in _statute_decisions_docx],
                    )
                    _user_parse_notice_docx = str(
                        (_user_parse_meta_docx or {}).get("degraded_notice") or ""
                    )
                    _unanswered_issues_docx = (
                        _check_issues_docx(_issue_answers_docx)
                        + _check_user_coverage_docx(_user_coverage_docx)
                    )
                    if _unanswered_issues_docx:
                        # [제거·기록으로 전환, 2026-09-10 지시 항목 2] 담당자가
                        # 요청한 쟁점에 답이 없다면, 문서를 막을 것이 아니라
                        # "이 쟁점은 아직 답하지 못했습니다"를 문서에 그대로
                        # 적어 내보내는 것이 실무적으로 맞다 — 담당자는 나머지
                        # 검토 결과를 즉시 쓸 수 있고, 빠진 쟁점도 놓치지 않는다.
                        _delivery.add(
                            _USER_SCOPE_FAIL,
                            detail="미답변 검토요청: " + "; ".join(
                                str(
                                    x.get("normalized_issue") or x.get("issue") or x.get("code") or x
                                )[:120]
                                for x in _unanswered_issues_docx[:6]
                            ),
                        )

                    # [REVIEW_FAILED_GLOBAL_REASONING gate] (2026-09-03 지시, 요구 11)
                    # — 이 다운로드 경로는 _all_results를 독립적으로 재구성하므로
                    # self_check.py의 전체 판단축을 여기서 다시 돌릴 수는 없지만,
                    # 구조적으로 계산 가능한 핵심 두 축(금전리스크 미탐지, 제3자
                    # 귀책을 우리가 떠안는데 HIGH가 아님)만은 여기서도 반드시
                    # 재확인한다 — 그 외 항목은 초기 리뷰 단계의 self_check가 이미
                    # meta.self_check에 기록해 둔다.
                    from runtime.review.self_check import (
                        _RX_MONETARY_PENALTY_LANGUAGE as _rx_monetary_penalty,
                    )
                    _active_docx_results = [
                        cr for cr in _all_results
                        if isinstance(cr, dict) and not cr.get("dedup_suppressed") and not cr.get("keep_as_is")
                    ]
                    _has_penalty_finding_docx = any(
                        str(cr.get("clause_id") or "") == "clr_late_penalty_rate_uncapped"
                        or "%" in str(cr.get("legal_business_reason") or "")
                        for cr in _active_docx_results
                    )
                    _monetary_risk_unconfirmed_docx = bool(
                        _rx_monetary_penalty.search(str(text or "")) and not _has_penalty_finding_docx
                    )
                    _third_party_fault_not_high_docx = [
                        str(cr.get("clause_id") or "")
                        for cr in _active_docx_results
                        if isinstance(cr.get("indemnity_direction"), dict)
                        and cr["indemnity_direction"].get("fault_source") in ("counterparty_own", "third_party_shifted_to_us")
                        and str(cr.get("risk_tier") or "").upper() != "HIGH"
                    ]
                    if _monetary_risk_unconfirmed_docx or _third_party_fault_not_high_docx:
                        # [제거·기록 대신 **상향 보정**, 2026-09-10 지시 항목 2]
                        # 이 게이트가 잡는 것은 "위험이 과소평가됐다"는 신호다.
                        # 차단하면 담당자는 아무것도 못 받고 과소평가도 그대로
                        # 남는다. 제3자 귀책을 우리가 떠안는 조항은 여기서 HIGH로
                        # 올려 문서에 반영하고, 금전리스크 미탐지는 문서에 명시한다.
                        for _cr_tp in _all_results:
                            if isinstance(_cr_tp, dict) and str(_cr_tp.get("clause_id") or "") in _third_party_fault_not_high_docx:
                                _cr_tp["risk_tier"] = "HIGH"
                                _cr_tp["severity"] = "HIGH"
                        _delivery.add(
                            "REVIEW_FAILED_GLOBAL_REASONING",
                            clause_ids=_third_party_fault_not_high_docx,
                            reason="위험도 과소평가가 확인되어 자동 상향 보정함",
                            detail=(
                                ("원문에 금전 제재(지연손해금·위약벌 등) 문언이 있으나 대응 검토항목이 없습니다. "
                                 if _monetary_risk_unconfirmed_docx else "")
                                + ("제3자 귀책을 우리가 부담하는 조항을 HIGH로 상향했습니다."
                                   if _third_party_fault_not_high_docx else "")
                            ).strip(),
                        )
                        if _third_party_fault_not_high_docx:
                            _docx_final = _build_final_findings(
                                _all_results, contract_type_code=_ct_code, include_low=False,
                            )

                    # [REVIEW_FAILED_GLOBAL_CROSS_CLAUSE gate, 2026-09-04 지시] —
                    # 다른 조항에 이미 있는 답(예: Article 9의 준거법·중재)을
                    # "부재"로 다시 지적하는 잔존 사례를 self_check.py와 동일한
                    # 백스톱(apply_global_cross_clause_validation 재실행)으로
                    # 이 다운로드 경로에서도 확인한다.
                    from runtime.review.global_cross_clause_validation import (
                        apply_global_cross_clause_validation as _apply_gccv_docx,
                    )
                    _pre_suppressed_ids_docx = {
                        str(cr.get("clause_id") or id(cr)) for cr in _all_results
                        if isinstance(cr, dict) and bool(cr.get("dedup_suppressed"))
                    }
                    _apply_gccv_docx(_all_results, str(text or ""))
                    _newly_suppressed_docx = [
                        str(cr.get("clause_id") or "")
                        for cr in _all_results
                        if isinstance(cr, dict) and bool(cr.get("dedup_suppressed"))
                        and str(cr.get("clause_id") or id(cr)) not in _pre_suppressed_ids_docx
                    ]
                    if _newly_suppressed_docx:
                        # [제거·기록으로 전환, 2026-09-10 지시 항목 2] 이 게이트는
                        # 이미 `_apply_gccv_docx()` 가 해당 finding 을 억제(suppress)
                        # 한 **뒤에** 돈다 — 즉 결함은 이미 제거된 상태다. 그런데도
                        # 409 를 내던 것은 "고쳐놓고 실패로 처리"하는 셈이었다.
                        # 제거 사실만 문서에 남기고 진행한다.
                        _delivery.add(
                            "REVIEW_FAILED_GLOBAL_CROSS_CLAUSE",
                            clause_ids=_newly_suppressed_docx,
                            reason="다른 조항에 이미 규정된 사항을 중복 지적해 제외함",
                        )
                        _docx_final = _build_final_findings(
                            _all_results, contract_type_code=_ct_code, include_low=False,
                        )

                    # [REVIEW_FAILED_LIKELY_FALSE_NEGATIVE 다운로드 차단, 2026-09-04
                    # 지시] — self_check.py는 HIGH=0/MEDIUM=0인데 위험 언어가
                    # 원문에 있으면 이 status를 올바르게 계산하지만, 지금까지는
                    # 이 다운로드 경로가 그 결과를 무시하고 그대로 "정상" 문서를
                    # 내보냈다. _all_results(이 경로가 독립적으로 재구성한 최종
                    # 목록) 기준으로 다시 확인해 차단한다.
                    from runtime.review.self_check import _FALSE_NEGATIVE_RISK_GROUPS as _fn_groups_docx
                    _docx_high_for_fn = sum(1 for cr in _active_docx_results if str(cr.get("risk_tier") or "").upper() == "HIGH")
                    _docx_medium_for_fn = sum(1 for cr in _active_docx_results if str(cr.get("risk_tier") or "").upper() == "MEDIUM")
                    if _docx_high_for_fn == 0 and _docx_medium_for_fn == 0:
                        _fn_triggered_docx = [g for g, kws in _fn_groups_docx.items() if any(kw in str(text or "") for kw in kws)]
                        if _fn_triggered_docx:
                            # [제거·기록으로 전환, 2026-09-10 지시 항목 2]
                            # HIGH/MEDIUM 이 0건인데 위험 언어가 있는 것은 "검토가
                            # 놓쳤을 수 있다"는 경고이지 문서를 못 만든다는 뜻이
                            # 아니다. 어느 축이 비어 있는지를 문서 첫머리에 명시해
                            # 담당자가 그 부분만 직접 보게 한다.
                            _delivery.add(
                                "REVIEW_FAILED_LIKELY_FALSE_NEGATIVE",
                                detail=(
                                    "원문에 위험 문언이 있으나 HIGH/MEDIUM 검토항목이 0건입니다 — "
                                    "직접 확인이 필요한 영역: " + ", ".join(_fn_triggered_docx[:8])
                                ),
                            )

                    # [REVIEW_FAILED_LANGUAGE_QUALITY gate, 2026-09-03 지시] —
                    # 문장이 중간에서 잘리거나 원문 일부가 앞에서 잘린("ayment",
                    # "icle") 채로 DOCX/PDF를 생성하지 않는다.
                    from runtime.review.language_quality_gate import detect_language_quality_issues as _detect_lang_quality
                    _lang_violations = _detect_lang_quality(_all_results)
                    if _lang_violations:
                        # [제거·기록으로 전환, 2026-09-10 지시 항목 2] 잘린 문장이
                        # 문서에 들어가지 않게 하는 것이 목적이므로, 해당 항목의
                        # 문안만 회수하고 무엇이 빠졌는지 문서에 밝힌다.
                        _lang_ids = sorted({str(v.get("clause_id") or "") for v in _lang_violations} - {""})
                        for _cr_lq in _all_results:
                            if isinstance(_cr_lq, dict) and str(_cr_lq.get("clause_id") or "") in _lang_ids:
                                _withdraw_proposal(_cr_lq, status="REVIEW_FAILED_LANGUAGE_QUALITY")
                        _delivery.add(
                            "REVIEW_FAILED_LANGUAGE_QUALITY",
                            clause_ids=_lang_ids,
                            detail="문장이 중간에서 잘렸거나 원문 추출이 손상된 항목입니다.",
                        )
                        _docx_final = _build_final_findings(
                            _all_results, contract_type_code=_ct_code, include_low=False,
                        )

                    doc_bytes = _builder(
                        entity=entity,
                        contract_type=contract_type,
                        filename=str(filename) if isinstance(filename, str) else None,
                        clause_results=_all_results,
                        original_clauses=original_clauses,
                        detailed_contract_profile=_detailed_profile.to_dict(),
                        canonical_state=_canonical_state_docx,
                        include_low=False,
                        contract_type_code=_ct_code,
                        is_counterparty_form=True,
                        top_risks_filtered=_docx_final.get("top_risks"),
                        high_issues_filtered=_docx_final.get("high_issues"),
                        medium_issues_filtered=_docx_final.get("medium_issues"),
                        mandatory_review_targets=_mandatory_target_status,
                        mandatory_review_issues=_issue_answers_docx,
                        user_review_coverage=_user_coverage_docx,
                        user_review_parse_degraded_notice=_user_parse_notice_docx,
                        legal_applicability_review=(clause_meta.get("legal_applicability_review") if isinstance(clause_meta, dict) else None),
                        delivery_remediations=_delivery_disclosure_rows(_delivery),
                        statute_gate_decisions=(
                            (clause_meta.get("statute_applicability_gate") or {}).get("decisions")
                            if isinstance(clause_meta, dict) else None
                        ),
                    )
                except Exception as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"{_out_ext} generation failed", "detail": sanitize_error_message(str(exc))})
                    return
                _binary_response(
                    self,
                    HTTPStatus.OK,
                    doc_bytes,
                    filename=_out_filename,
                    content_type=_out_content_type,
                )
                return

            clause_results = body.get("clause_results")
            original_clauses = body.get("original_clauses")
            meta = body.get("input") if isinstance(body.get("input"), dict) else {}
            if not isinstance(clause_results, list):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id is required for docx (or provide clause_results+original_clauses explicitly)"})
                return
            if not isinstance(original_clauses, list):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "original_clauses is required when session_id is not provided"})
                return
            approx_text_len = sum(len(str(c.get("text") or "")) for c in original_clauses if isinstance(c, dict))
            if approx_text_len < 120:
                _json_response(
                    self,
                    HTTPStatus.BAD_REQUEST,
                    {"error": "insufficient contract text for docx generation", "text_length": approx_text_len},
                )
                return
            entity = str(meta.get("entity") or "all")
            contract_type = str(meta.get("contract_type") or "all")
            filename = meta.get("filename")
            contract_text = "\n".join(str(c.get("text") or "") for c in original_clauses if isinstance(c, dict))
            try:
                # 여기서도 분류기를 다시 돌리지 않는다 — 저장된 값이 먼저다.
                _stored_dp2 = (
                    clause_meta.get("detailed_contract_profile")
                    if isinstance(clause_meta, dict) else None
                )
                if isinstance(_stored_dp2, dict) and _stored_dp2:
                    _dp2 = _StoredProfile(_stored_dp2)
                else:
                    _dp2 = _classify_detailed(entity=entity, contract_type=contract_type, text=contract_text)
            except Exception:
                _dp2 = None
            _ct_code_for_this_block = _dp2.contract_type if _dp2 is not None else ""
            review = service.analyze(
                ReviewInput(
                    entity=entity,
                    contract_type=contract_type,
                    text=contract_text,
                    filename=filename,
                    answers=None,
                    contract_type_code=_ct_code_for_this_block,
                )
            )
            detected_rule_ids = [
                r.get("rule_id")
                for r in (review.get("matched_rules") or [])
                if isinstance(r, dict) and isinstance(r.get("rule_id"), str)
            ]
            contract_law_search = None
            law_topics = None
            try:
                law_cfg = load_law_api_config()
                law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if law_cfg.enabled and law_cfg.api_key else None
                if law_service is not None:
                    contract_law_search = law_service.search_for_review(
                        entity=entity,
                        contract_type=contract_type,
                        text=contract_text,
                        matched_rules=review.get("matched_rules") if isinstance(review, dict) else None,
                        scope="contract",
                        max_per_type=2,
                        contract_type_code=_ct_code_for_this_block,
                    )
            except Exception:
                contract_law_search = None
            if isinstance(contract_law_search, dict) and isinstance(contract_law_search.get("queries"), list):
                law_topics = [str(x) for x in contract_law_search.get("queries") if isinstance(x, str)]
            qs = generate_questions(
                entity,
                contract_type,
                detected_rule_ids=detected_rule_ids,
                law_topics=law_topics,
                contract_text=contract_text,
                clause_results=clause_results,
                max_questions=7,
                contract_type_code=_ct_code_for_this_block,
                question_plan=_build_question_plan(
                    entity=entity, contract_type=contract_type, text=contract_text,
                    review_focus=None, max_questions=7,
                ),
                transaction_type=_transaction_type_for(
                    clause_meta if isinstance(clause_meta, dict) else None, contract_text,
                ),
            )
            try:
                _ct2 = _ct_code_for_this_block
                _cr_list2 = _inject_mandatory_issues(
                    full_text=contract_text, clause_results=list(clause_results),
                    contract_type_code=_ct2, is_counterparty_form=True,
                    clauses=original_clauses,
                )
                _DEALER_CODES2 = {"consignment_sales_agency", "direct_customer_sales_support", "dealer_agency", "dealer_rental_service_contract"}
                _SUPPRESS2 = ("isr_", "sppc_", "pi_", "svc_")
                # canonical 분류(_ct2)만 신뢰한다 — raw contract_type 라벨의
                # "대리점"/"위탁판매" 부분 문자열 매칭은 stale 라벨에 오염될
                # 수 있어 제거함(2026-09-01, priority_map.py와 동일 원칙).
                if _ct2 in _DEALER_CODES2:
                    from runtime.review.clause_level import apply_dealer_rental_final_gate as _dlr_gate2
                    if _ct2 == "dealer_rental_service_contract":
                        _cr_list2 = _dlr_gate2(_cr_list2, _ct2)
                    else:
                        for _cr2 in _cr_list2:
                            if not isinstance(_cr2, dict):
                                continue
                            _cid2 = str(_cr2.get("clause_id") or "")
                            if any(_cid2.startswith(p) for p in _SUPPRESS2):
                                _cr2["risk_tier"] = "LOW"
                                _cr2["severity"] = "LOW"
                                _cr2["approval_required"] = False
                                _cr2["high_risk"] = False
                                _cr2["must_fix"] = False
                                continue
                            if _cr2.get("is_mandatory"):
                                continue
                            _cur2 = str(_cr2.get("risk_tier") or "LOW").upper()
                            _new2, _ = _reclassify_consignment(
                                severity=_cur2, clause_text=str(_cr2.get("original_text") or ""),
                            )
                            if _new2 != _cur2:
                                _cr2["risk_tier"] = _new2
                                _cr2["severity"] = _new2
                for _cr2 in _cr_list2:
                    if not isinstance(_cr2, dict) or _cr2.get("is_mandatory"):
                        continue
                    # (위 다운로드 경로와 동일 — 결정론적 Layer-1 rule 예외)
                    if _cr2.get("is_common_legal_risk"):
                        continue
                    _sr2 = str(_cr2.get("suggested_rewrite") or "").strip()
                    if _sr2:
                        _title2_lo = str(_cr2.get("clause_title") or "").lower()
                        _cid2 = str(_cr2.get("clause_identity") or "")
                        if not _cid2:
                            if any(k in _title2_lo for k in ["해지", "종료", "해제"]):
                                _cid2 = "termination"
                            elif any(k in _title2_lo for k in ["비밀", "기밀"]):
                                _cid2 = "confidentiality"
                            elif any(k in _title2_lo for k in ["양도", "지위 이전", "계약자 변경"]):
                                _cid2 = "assignment_party_change"
                            else:
                                _cid2 = str(_cr2.get("clause_id") or "")
                        _g2 = _hg_check_revision(_sr2, contract_type_code=_ct2, clause_identity=_cid2)
                        if not _g2.is_clean:
                            _apply_minimal_edit(
                                _cr2,
                                reason="조항 주제와 자동 생성 문안의 주제가 달라 교체했습니다.",
                            )

                # [REVIEW_FAILED_LANGUAGE_QUALITY gate, 2026-09-03 지시]
                from runtime.review.language_quality_gate import detect_language_quality_issues as _detect_lang_quality2
                _lang_violations2 = _detect_lang_quality2(_cr_list2)
                if _lang_violations2:
                    # [제거·기록으로 전환, 2026-09-10 지시 항목 2 — 위 다운로드
                    # 경로와 동일 원칙] 잘린 문안만 회수하고 문서는 생성한다.
                    _lang_ids2 = sorted({str(v.get("clause_id") or "") for v in _lang_violations2} - {""})
                    for _cr_lq2 in _cr_list2:
                        if isinstance(_cr_lq2, dict) and str(_cr_lq2.get("clause_id") or "") in _lang_ids2:
                            _withdraw_proposal(_cr_lq2, status="REVIEW_FAILED_LANGUAGE_QUALITY")

                doc_bytes = _builder(
                    entity=entity, contract_type=contract_type,
                    filename=str(filename) if isinstance(filename, str) else None,
                    clause_results=_cr_list2, original_clauses=original_clauses,
                    detailed_contract_profile=_dp2.to_dict(),
                    canonical_state=(
                        clause_meta.get("canonical_state")
                        if isinstance(clause_meta, dict) else None
                    ),
                    include_low=False, contract_type_code=_ct2, is_counterparty_form=True,
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"{_out_ext} generation failed", "detail": sanitize_error_message(str(exc))})
                return
            _binary_response(
                self,
                HTTPStatus.OK,
                doc_bytes,
                filename=_out_filename,
                content_type=_out_content_type,
            )

        def _handle_revision_download_redline(self, service: RuleQueryService, path: str) -> None:
            import base64
            want_clean = path.endswith("/download_clean")
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON: {exc}"})
                return

            session_id = body.get("session_id")
            if not (isinstance(session_id, str) and session_id):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id required"})
                return
            try:
                doc = load_session(session_id)
            except Exception as exc:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return

            # 원본 DOCX bytes 확인
            orig_b64 = doc.get("original_docx_b64")
            if not orig_b64:
                _json_response(self, HTTPStatus.BAD_REQUEST, {
                    "error": "원본 DOCX가 세션에 없습니다. DOCX 파일로 업로드한 세션만 지원합니다.",
                    "hint": "Upload a .docx file (not txt/pdf) to enable redline generation."
                })
                return
            original_bytes = base64.b64decode(orig_b64)

            # 검토 결과 확인 (없으면 빠른 재실행)
            review_result = doc.get("review_result")
            if not (isinstance(review_result, dict) and isinstance(review_result.get("clause_results"), list)):
                review_result = run_review_with_session(service, session_id)

            clause_results = review_result.get("clause_results") or []
            entity = str(doc.get("entity") or "퍼시스")
            filename_base = (doc.get("input") or {}).get("filename") or "contract"
            stem = filename_base.rsplit(".", 1)[0] if "." in filename_base else filename_base

            # original_clauses 세션에서 조회 (정확한 단락 매칭용)
            original_clauses: list[dict] = []
            if isinstance(review_result, dict) and isinstance(review_result.get("original_clauses"), list):
                original_clauses = review_result.get("original_clauses") or []
            if not original_clauses and isinstance(doc.get("original_clauses"), list):
                original_clauses = doc.get("original_clauses") or []

            try:
                author = body.get("author") or "퍼시스법무"
                from datetime import datetime, timezone
                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                # docx_redline 엔진 우선 사용 (위치 기반 정확한 추적 변경)
                if original_clauses:
                    from runtime.review.docx_redline import build_redline_docx as _build_rdl
                    redline_bytes, clean_bytes = _build_rdl(
                        docx_bytes=original_bytes,
                        original_clauses=original_clauses,
                        clause_results=clause_results,
                        author=author,
                        date=date_str,
                    )
                else:
                    # fallback: 패턴 기반 (original_clauses 없을 때)
                    redline_bytes, clean_bytes = build_redline_from_analysis(
                        original_bytes=original_bytes,
                        clause_results=clause_results,
                        author=author,
                        date=date_str,
                    )
            except Exception as exc:
                from runtime.ai.safe import sanitize_error_message
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {
                    "error": "redline generation failed",
                    "detail": sanitize_error_message(str(exc))
                })
                return

            if want_clean:
                out_bytes = clean_bytes
                out_name = f"clean_{stem}.docx"
            else:
                out_bytes = redline_bytes
                out_name = f"redline_{stem}.docx"

            _binary_response(
                self,
                HTTPStatus.OK,
                out_bytes,
                filename=out_name,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        def _handle_questions_generate(self, service: RuleQueryService) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            entity = body.get("entity", "all")
            contract_type = body.get("contract_type", "all")
            text = body.get("text", "")
            filename = body.get("filename")
            review_focus = body.get("review_focus")

            # canonical 분류를 이 핸들러 전체(rule 매칭·법령검색·사전질문
            # 생성)에서 단일 source of truth로 공유한다 — UI가 넘긴 raw
            # contract_type 라벨은 stale할 수 있어 이 값 하나만 믿지 않는다
            # (2026-09-01).
            try:
                _canonical_type_code = _classify_detailed(entity=str(entity), contract_type=str(contract_type), text=str(text)).contract_type
            except Exception:
                _canonical_type_code = ""

            try:
                review = service.analyze(
                    ReviewInput(
                        entity=entity,
                        contract_type=contract_type,
                        text=text,
                        filename=filename,
                        answers=None,
                        review_focus=(review_focus if isinstance(review_focus, str) else None),
                        contract_type_code=_canonical_type_code,
                    )
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": sanitize_error_message(str(exc))})
                return
            law_search = None
            try:
                law_cfg = load_law_api_config()
                law_service = LawSearchService(cfg=law_cfg, cache=law_cache)
                law_search = law_service.search_for_review(
                    entity=str(entity),
                    contract_type=str(contract_type),
                    text=str(text),
                    matched_rules=review.get("matched_rules") if isinstance(review, dict) else None,
                    scope="contract",
                    max_per_type=3,
                    contract_type_code=_canonical_type_code,
                )
            except Exception as exc:
                law_search = {"enabled": False, "note": "law search failed", "error": sanitize_error_message(str(exc))}
            detected_rule_ids = [
                r.get("rule_id")
                for r in (review.get("matched_rules") or [])
                if isinstance(r, dict) and isinstance(r.get("rule_id"), str)
            ]
            law_topics = None
            if isinstance(law_search, dict) and isinstance(law_search.get("queries"), list):
                law_topics = [str(x) for x in law_search.get("queries") if isinstance(x, str)]
            try:
                clause_bundle = build_clause_level_result(
                    service=service,
                    entity=str(entity),
                    contract_type=str(contract_type),
                    text=str(text),
                    filename=str(filename) if isinstance(filename, str) else None,
                    answers=None,
                    review_focus=(review_focus if isinstance(review_focus, str) else None),
                    law_service=None,
                    ai_provider=None,
                    ai_model=None,
                    ai_timeout_sec=None,
                    ai_max_tokens=None,
                    ai_temperature=None,
                    max_clause_law_items=0,
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": sanitize_error_message(str(exc))})
                return
            try:
                questions = generate_questions(
                    str(entity),
                    str(contract_type),
                    detected_rule_ids=detected_rule_ids,
                    law_topics=law_topics,
                    contract_text=str(text),
                    clause_results=clause_bundle.clause_results,
                    max_questions=5,
                    review_focus=(review_focus if isinstance(review_focus, str) else None),
                    contract_type_code=_canonical_type_code,
                    question_plan=_build_question_plan(
                        entity=entity, contract_type=contract_type, text=text,
                        review_focus=review_focus, max_questions=5,
                    ),
                    transaction_type=_transaction_type_for(
                        clause_bundle.meta if isinstance(clause_bundle.meta, dict) else None,
                        str(text),
                    ),
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": sanitize_error_message(str(exc))})
                return
            q_items = [question_to_dict(q) for q in questions]
            ai_meta: dict[str, Any] | None = None
            cfg = load_ai_config()
            if is_ai_enabled(cfg) and q_items:
                try:
                    provider = create_ai_provider(cfg)
                    # raw contract_type 라벨 substring 매칭 제거 — 실제 본문
                    # 신호(text) + canonical 분류 기준 양립가능 여부로 판단
                    # (2026-09-01, questions/generator.py와 동일 원칙).
                    from runtime.questions.generator import _APP_DEV_INCOMPATIBLE_TYPE_CODES as _APP_DEV_BAD_CODES
                    app_dev_hint = any(
                        k in str(text or "") for k in ("앱 개발", "소프트웨어 개발", "시스템 개발", "SLA", "소스코드", "산출물")
                    ) and _canonical_type_code not in _APP_DEV_BAD_CODES
                    if app_dev_hint and clause_bundle.clauses:
                        headings = [str(c.title or "") for c in clause_bundle.clauses if str(c.title or "").strip()][:18]
                    else:
                        headings = None
                    pri_meta = None
                    if app_dev_hint:
                        q_items, pri_meta = prioritize_questions(
                            provider=provider,
                            model=cfg.model,
                            questions=q_items,
                            entity=str(entity),
                            contract_type=str(contract_type),
                            contract_text=str(text),
                            clause_headings=headings,
                            timeout_sec=cfg.timeout_sec,
                            max_tokens=min(cfg.max_tokens, 600),
                            temperature=cfg.temperature,
                            max_questions=5,
                        )
                    q_items, pol_meta = polish_questions(
                        provider=provider,
                        model=cfg.model,
                        questions=q_items,
                        entity=str(entity),
                        contract_type=str(contract_type),
                        timeout_sec=cfg.timeout_sec,
                        max_tokens=min(cfg.max_tokens, 700),
                        temperature=cfg.temperature,
                    )
                    ai_meta = {"prioritize": pri_meta, "polish": pol_meta}
                except Exception:
                    pass
            if isinstance(q_items, list):
                q_items = q_items[:5]
            try:
                session_doc = create_text_session(
                    entity=str(entity),
                    contract_type=str(contract_type),
                    filename=str(filename) if isinstance(filename, str) else None,
                    text=str(text or ""),
                    review_focus=(review_focus if isinstance(review_focus, str) else None),
                    extraction={"success": True, "method": "api_text"},
                    classification={"entity": str(entity), "contract_type": str(contract_type)},
                    detected_rule_ids=[str(x) for x in detected_rule_ids if isinstance(x, str)],
                    questions=list(q_items) if isinstance(q_items, list) else [],
                    source="questions_generate",
                )
            except Exception:
                session_doc = {}
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "input": {"entity": entity, "contract_type": contract_type, "filename": filename, "review_focus": (review_focus if isinstance(review_focus, str) else None)},
                    "question_session_id": session_doc.get("session_id") if isinstance(session_doc, dict) else None,
                    "detected_rule_ids": detected_rule_ids,
                    "count": len(q_items) if isinstance(q_items, list) else 0,
                    "questions": q_items,
                    "law_search": law_search,
                    "ai": ai_meta,
                },
            )

        def _handle_draft_generate(self, service: RuleQueryService) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            template_id = body.get("template_id")
            entity = body.get("entity") or "미상"
            contract_type = body.get("contract_type") or "기타/미분류"
            party_a = body.get("party_a") or entity
            party_b = body.get("party_b") or "상대방"
            purpose = body.get("purpose")

            if not isinstance(template_id, str) or not template_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "template_id is required"})
                return
            try:
                result = generate_draft_text(
                    service=service,
                    template_id=template_id,
                    entity=str(entity),
                    contract_type=str(contract_type),
                    party_a=str(party_a),
                    party_b=str(party_b),
                    purpose=str(purpose) if isinstance(purpose, str) else None,
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            cfg = load_ai_config()
            ai_meta = None
            if is_ai_enabled(cfg) and isinstance(result.get("draft_text"), str):
                provider = create_ai_provider(cfg)
                new_text, meta = polish_draft_text(
                    provider=provider,
                    model=cfg.model,
                    draft_text=str(result.get("draft_text") or ""),
                    entity=str(entity),
                    contract_type=str(contract_type),
                    timeout_sec=cfg.timeout_sec,
                    max_tokens=min(cfg.max_tokens, 900),
                    temperature=cfg.temperature,
                )
                result["draft_text"] = new_text
                ai_meta = meta
            if ai_meta:
                result["ai"] = ai_meta
            _json_response(self, HTTPStatus.OK, result)

        def _handle_draft_download(self, service: RuleQueryService) -> None:
            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_len)
                body = json.loads(raw.decode("utf-8")) if raw else {}
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                return

            template_id = body.get("template_id")
            entity = body.get("entity") or "미상"
            contract_type = body.get("contract_type") or "기타/미분류"
            party_a = body.get("party_a") or entity
            party_b = body.get("party_b") or "상대방"
            purpose = body.get("purpose")

            if not isinstance(template_id, str) or not template_id:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "template_id is required"})
                return
            try:
                result = generate_draft_text(
                    service=service,
                    template_id=template_id,
                    entity=str(entity),
                    contract_type=str(contract_type),
                    party_a=str(party_a),
                    party_b=str(party_b),
                    purpose=str(purpose) if isinstance(purpose, str) else None,
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return

            draft_text = str(result.get("draft_text") or "")
            fname = str(template_id).rsplit(".", 1)[0]
            _text_response(self, HTTPStatus.OK, draft_text, filename=f"draft_{fname}.txt")

        def _handle_approval_post(self, path: str) -> None:
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[3] == "status":
                request_id = parts[2]
                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_len)
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except Exception as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                    return
                status = body.get("status")
                if not isinstance(status, str):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "status must be string"})
                    return
                try:
                    repo.update_approval_status(request_id, status)
                except KeyError:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
                except Exception as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                    return
                _json_response(self, HTTPStatus.OK, {"request_id": request_id, "status": status})
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "unknown path"})

        def _handle_ep_session_start(self, service: RuleQueryService) -> None:
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "multipart/form-data required"})
                return

            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_len) if content_len > 0 else b""
                parsed = _parse_multipart_form_data(content_type, body)
                fields = parsed.get("fields") or {}
                file_item = parsed.get("file")
                if not file_item:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "file is required"})
                    return

                intake_raw = fields.get("intake_json") or "{}"
                intake_obj = json.loads(intake_raw)
                intake, errors = validate_ep_intake(intake_obj)
                if errors:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid intake", "details": errors})
                    return

                filename = file_item.get("filename") or "uploaded"
                suffix = ""
                if "." in filename:
                    suffix = "." + filename.rsplit(".", 1)[-1]

                with tempfile.TemporaryDirectory() as td:
                    tmp_path = str(Path(td) / ("uploaded" + suffix))
                    with open(tmp_path, "wb") as out:
                        out.write(file_item.get("content") or b"")

                    p = Path(tmp_path)
                    extraction = extract_text_from_file(p)
                    if not extraction.success:
                        _is_quality_failure = extraction.quality is not None and extraction.quality.verdict == "low_quality"
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            {
                                "filename": filename,
                                "status": "REVIEW_FAILED_TEXT_EXTRACTION",
                                "extraction": {
                                    "success": False,
                                    "method": extraction.method,
                                    "error": extraction.error,
                                    "quality": extraction.quality.to_dict() if extraction.quality else None,
                                },
                                "intake": intake_to_dict(intake),
                                "note": (
                                    "이 문서는 이미지 기반이거나 텍스트 인코딩이 손상되어 있어 native 추출과 OCR 모두 "
                                    "내용을 읽지 못했습니다. 계약 유형을 임의로 추정하지 않고 검토를 중단합니다."
                                    if _is_quality_failure
                                    else f"텍스트 추출 실패: {extraction.error}. 지원 형식: .txt, .docx, .xlsx, .pdf, .hwp (이미지 PDF OCR 포함)"
                                ),
                            },
                        )
                        return

                    cls = classify(intake.entity, intake.contract_type, extraction.text, filename)
                    session = create_session(
                        service=service,
                        entity=cls.entity,
                        contract_type=cls.contract_type,
                        filename=filename,
                        extraction={
                            "success": True,
                            "method": extraction.method,
                            "text_length": len(extraction.text),
                        },
                        text=extraction.text,
                        classification={
                            "entity": cls.entity,
                            "contract_type": cls.contract_type,
                            "entity_source": cls.entity_source,
                            "contract_type_source": cls.contract_type_source,
                            "is_inferred": cls.is_inferred,
                        },
                        intake=intake_to_dict(intake),
                        source="ep",
                    )
                    if cls.is_inferred:
                        update_cache(filename, cls.entity, cls.contract_type)
                    try:
                        repo.upsert_ep_intake_session(
                            session_id=session["session_id"],
                            ep_request_id=intake.ep_request_id,
                            status="aouribot_in_progress",
                            intake_json=intake_to_dict(intake),
                        )
                    except Exception:
                        pass

                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "filename": filename,
                            "intake": intake_to_dict(intake),
                            "extraction": {
                                "success": True,
                                "method": extraction.method,
                                "text_length": len(extraction.text),
                            },
                            "classification": {
                                "entity": cls.entity,
                                "contract_type": cls.contract_type,
                                "entity_source": cls.entity_source,
                                "contract_type_source": cls.contract_type_source,
                                "is_inferred": cls.is_inferred,
                            },
                            "question_session_id": session["session_id"],
                            "detected_rule_ids": session["detected_rule_ids"],
                            "questions": session["questions"],
                        },
                    )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def _handle_question_session_post(self, service: RuleQueryService, path: str) -> None:
            parts = path.strip("/").split("/")
            if len(parts) < 4:
                _json_response(self, HTTPStatus.NOT_FOUND, {"error": "unknown path"})
                return
            session_id = parts[2]
            action = parts[3]

            if action == "answers":
                try:
                    content_len = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(content_len)
                    body = json.loads(raw.decode("utf-8")) if raw else {}
                except Exception as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid JSON body: {exc}"})
                    return
                answers = body.get("answers")
                if not isinstance(answers, dict):
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "answers must be an object"})
                    return
                try:
                    doc = save_answers(session_id, answers)
                except Exception as exc:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                safe = dict(doc)
                safe.pop("text", None)
                _json_response(self, HTTPStatus.OK, safe)
                return

            if action == "review":
                try:
                    result = run_review_with_session(service, session_id)
                except Exception as exc:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                request_id = None
                try:
                    doc = load_session(session_id)
                    source = "ep_session" if doc.get("source") == "ep" else "upload_session"
                    persisted = repo.save_review(
                        entity=str(doc.get("entity", "all")),
                        contract_type=str(doc.get("contract_type", "all")),
                        filename=(doc.get("input") or {}).get("filename"),
                        source=source,
                        question_session_id=session_id,
                        rules_sha256=str(doc.get("rules_sha256", rules_sha)),
                        rules_schema_version=rules_schema_version,
                        rules_source_path=rules_source_path,
                        review_result=result,
                        text=str(doc.get("text", "")),
                    )
                    request_id = persisted.request_id
                    if doc.get("source") == "ep":
                        intake = doc.get("intake") if isinstance(doc.get("intake"), dict) else {}
                        ep_request_id = intake.get("ep_request_id") if isinstance(intake.get("ep_request_id"), str) else None
                        if ep_request_id:
                            repo.link_ep_request_to_review(ep_request_id, session_id, request_id)
                        try:
                            repo.upsert_ep_intake_session(
                                session_id=session_id,
                                ep_request_id=ep_request_id,
                                status="aouribot_completed",
                                intake_json=intake if isinstance(intake, dict) else {},
                            )
                        except Exception:
                            pass
                except Exception:
                    pass
                _json_response(self, HTTPStatus.OK, {"request_id": request_id, "review": result})
                return

            if action == "review_fast":
                try:
                    result = run_review_with_session_fast(service, session_id)
                except Exception as exc:
                    _json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
                    return
                _json_response(self, HTTPStatus.OK, {"review": result})
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "unknown path"})

        def _handle_upload(self, service: RuleQueryService) -> None:
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "multipart/form-data required"})
                return

            try:
                content_len = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_len) if content_len > 0 else b""
                parsed = _parse_multipart_form_data(content_type, body)
                fields = parsed.get("fields") or {}
                file_item = parsed.get("file")
                if not file_item:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "file is required"})
                    return

                filename = file_item.get("filename") or "uploaded"
                entity = (fields.get("entity") or "").strip() or None
                contract_type = (fields.get("contract_type") or "").strip() or None
                review_focus = (fields.get("review_focus") or "").strip() or None

                suffix = ""
                if "." in filename:
                    suffix = "." + filename.rsplit(".", 1)[-1]

                with tempfile.TemporaryDirectory() as td:
                    from pathlib import Path

                    tmp_path = str(Path(td) / ("uploaded" + suffix))
                    with open(tmp_path, "wb") as out:
                        out.write(file_item.get("content") or b"")

                    p = Path(tmp_path)
                    extraction = extract_text_from_file(p)

                    if not extraction.success:
                        _is_quality_failure = extraction.quality is not None and extraction.quality.verdict == "low_quality"
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            {
                                "filename": filename,
                                "status": "REVIEW_FAILED_TEXT_EXTRACTION",
                                "extraction": {
                                    "success": False,
                                    "method": extraction.method,
                                    "error": extraction.error,
                                    "quality": extraction.quality.to_dict() if extraction.quality else None,
                                },
                                # 추출 실패 시 raw contract_type/entity 입력값을 "classification"
                                # 이라는 이름으로 되돌려주지 않는다 — 이전 문서에서 남은 stale
                                # 값이 마치 유효한 분류 결과처럼 클라이언트에 보일 위험이 있다
                                # (2026-09-02 실사례). extraction이 실패하면 분류 자체가 없다.
                                "classification": None,
                                "review": None,
                                "note": (
                                    "이 문서는 이미지 기반이거나 텍스트 인코딩이 손상되어 있어 native 추출과 OCR 모두 "
                                    "내용을 읽지 못했습니다. 계약 유형을 임의로 추정하지 않고 검토를 중단합니다."
                                    if _is_quality_failure
                                    else f"텍스트 추출 실패: {extraction.error}. 지원 형식: .txt, .docx, .xlsx, .pdf, .hwp (이미지 PDF OCR 포함)"
                                ),
                            },
                        )
                        return

                    cls = classify(entity, contract_type, extraction.text, filename)
                    session = create_session(
                        service=service,
                        entity=cls.entity,
                        contract_type=cls.contract_type,
                        filename=filename,
                        extraction={
                            "success": True,
                            "method": extraction.method,
                            "text_length": len(extraction.text),
                        },
                        text=extraction.text,
                        classification={
                            "entity": cls.entity,
                            "contract_type": cls.contract_type,
                            "entity_source": cls.entity_source,
                            "contract_type_source": cls.contract_type_source,
                            "is_inferred": cls.is_inferred,
                        },
                        review_focus=review_focus,
                        intake={},
                        source="upload",
                    )
                    # DOCX 원본이면 redline 생성용 bytes를 세션에 저장
                    if suffix.lower() == ".docx":
                        import base64
                        session["original_docx_b64"] = base64.b64encode(
                            file_item.get("content") or b""
                        ).decode("ascii")
                        save_session(session)
                    if cls.is_inferred:
                        update_cache(filename, cls.entity, cls.contract_type)
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "filename": filename,
                            "extraction": {
                                "success": True,
                                "method": extraction.method,
                                "text_length": len(extraction.text),
                                "text_sha256": sha256(extraction.text.encode("utf-8", errors="replace")).hexdigest(),
                                "preview": (extraction.text[:200] + ("…" if len(extraction.text) > 200 else "")),
                            },
                            "classification": {
                                "entity": cls.entity,
                                "contract_type": cls.contract_type,
                                "entity_source": cls.entity_source,
                                "contract_type_source": cls.contract_type_source,
                                "is_inferred": cls.is_inferred,
                            },
                            "question_session_id": session["session_id"],
                            "detected_rule_ids": session["detected_rule_ids"],
                            "questions": session["questions"],
                            "review_focus": (review_focus or None),
                        },
                    )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            try:
                import datetime as _dt
                with open("C:/Users/FURSYS/Desktop/aouribot/access.log", "a", encoding="utf-8") as _f:
                    _f.write(f"{_dt.datetime.now().strftime('%H:%M:%S')} {format % args}\n")
            except Exception:
                pass

    return RulesAPIHandler


def build_httpd(host: str, port: int, service: RuleQueryService) -> ThreadingHTTPServer:
    handler = create_handler(service)
    return ThreadingHTTPServer((host, port), handler)


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    loader = RuleLoader()
    loader.load()
    service = RuleQueryService(loader)
    httpd = build_httpd(host, port, service)
    print(f"[AouriBot MVP] rules API started: http://{host}:{port}/admin")
    print(f"[AouriBot MVP] upload & review: http://{host}:{port}/upload")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()

