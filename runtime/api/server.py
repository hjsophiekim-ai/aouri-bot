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
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
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
            result["clause_results"] = _deep_cr
            result["clause_meta"] = bundle.meta
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
                        review_result = run_review_with_session(service, session_id)
                    else:
                        _json_response(
                            self,
                            HTTPStatus.BAD_REQUEST,
                            {"error": "missing canonical review_result in session (set rebuild=true to recompute)"},
                        )
                        return
                elif rebuild:
                    review_result = run_review_with_session(service, session_id)

                clause_meta = review_result.get("clause_meta") if isinstance(review_result, dict) else None
                if isinstance(clause_meta, dict) and clause_meta.get("docx_allowed") is False:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "insufficient contract text for docx generation", "meta": clause_meta},
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
                )
                try:
                    # ── legal-team pipeline: mandatory issues → severity → guardrail → new writer ──
                    _detailed_profile = _classify_detailed(
                        entity=entity,
                        contract_type=contract_type,
                        text=text,
                        filename=str(filename) if isinstance(filename, str) else None,
                    )
                    _ct_code = _detailed_profile.contract_type

                    # Combine regular + checklist results, inject mandatory issues
                    _all_results = list(clause_results_for_docx) + list(checklist_items_for_docx or [])
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
                                _cr["suggested_rewrite"] = "자동수정 보류: 조항 주제와 수정문안 불일치"
                                _cr["has_rewrite_change"] = False

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

                    _docx_final = _build_final_findings(_all_results, contract_type_code=_ct_code, include_low=False)
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
                    if _raw_total >= 5 and _docx_total <= max(1, _raw_total // 5):
                        _json_response(
                            self,
                            HTTPStatus.CONFLICT,
                            {
                                "error": "REVIEW_FAILED: final_findings_count(docx) collapsed relative to raw clause_results",
                                "review_status": "REVIEW_FAILED",
                                "raw_high_medium_count": _raw_total,
                                "final_findings_count_docx": {"high": _docx_high, "medium": _docx_medium},
                            },
                        )
                        return

                    _final_findings_clause_ids = {
                        str(i.get("clause_id") or "")
                        for i in (list(_docx_final.get("high_issues") or []) + list(_docx_final.get("medium_issues") or []))
                        if isinstance(i, dict)
                    }
                    _targets_ok, _missing_targets = _check_mandatory_targets(
                        _mandatory_target_status, final_findings_clause_ids=_final_findings_clause_ids,
                    )
                    if not _targets_ok:
                        _json_response(
                            self,
                            HTTPStatus.CONFLICT,
                            {
                                "error": "REVIEW_FAILED_USER_REQUEST_MISSING: user-cited clause(s) from review_focus missing from final output",
                                "review_status": "REVIEW_FAILED_USER_REQUEST_MISSING",
                                "missing_clause_citations": _missing_targets,
                            },
                        )
                        return

                    doc_bytes = _builder(
                        entity=entity,
                        contract_type=contract_type,
                        filename=str(filename) if isinstance(filename, str) else None,
                        clause_results=_all_results,
                        original_clauses=original_clauses,
                        detailed_contract_profile=_detailed_profile.to_dict(),
                        include_low=False,
                        contract_type_code=_ct_code,
                        is_counterparty_form=True,
                        top_risks_filtered=_docx_final.get("top_risks"),
                        high_issues_filtered=_docx_final.get("high_issues"),
                        medium_issues_filtered=_docx_final.get("medium_issues"),
                        mandatory_review_targets=_mandatory_target_status,
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
                            _cr2["suggested_rewrite"] = "자동수정 보류: 조항 주제와 수정문안 불일치"
                            _cr2["has_rewrite_change"] = False
                doc_bytes = _builder(
                    entity=entity, contract_type=contract_type,
                    filename=str(filename) if isinstance(filename, str) else None,
                    clause_results=_cr_list2, original_clauses=original_clauses,
                    detailed_contract_profile=_dp2.to_dict(),
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
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            {
                                "filename": filename,
                                "extraction": {
                                    "success": False,
                                    "method": extraction.method,
                                    "error": extraction.error,
                                },
                                "intake": intake_to_dict(intake),
                                "note": f"텍스트 추출 실패: {extraction.error}. 지원 형식: .txt, .docx, .xlsx, .pdf, .hwp (이미지 PDF OCR 포함)",
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
                        _json_response(
                            self,
                            HTTPStatus.OK,
                            {
                                "filename": filename,
                                "extraction": {
                                    "success": False,
                                    "method": extraction.method,
                                    "error": extraction.error,
                                },
                                "classification": {
                                    "entity": entity or "미상",
                                    "contract_type": contract_type or "기타/미분류",
                                    "entity_source": "user_input" if entity else "unavailable",
                                    "contract_type_source": "user_input" if contract_type else "unavailable",
                                },
                                "review": None,
                                "note": f"텍스트 추출 실패: {extraction.error}. 지원 형식: .txt, .docx, .xlsx, .pdf, .hwp (이미지 PDF OCR 포함)",
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

