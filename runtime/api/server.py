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
from runtime.ai.factory import create_ai_provider
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
from runtime.questions.storage import create_session, load_session, run_review_with_session, run_review_with_session_fast, save_answers
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
from runtime.review.text_extract import extract_text_from_file
from runtime.services.query_service import ReviewInput, RuleQueryService
from runtime.law.cache import JsonFileCache
from runtime.law.config import load_law_api_config
from runtime.law.search_service import LawSearchService
from runtime.env_debug import env_status


REPO_ROOT = Path(__file__).resolve().parents[3]


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
                enabled = bool(cfg.api_key) and cfg.provider == "openai"
                if not enabled:
                    _json_response(
                        self,
                        HTTPStatus.OK,
                        {
                            "enabled": False,
                            "provider": "mock",
                            "model": cfg.model,
                            "note": "OPENAI_API_KEY not set; using mock provider",
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
                    {"contract_type": contract_type, "suggested_template_ids": suggested, "items": all_items},
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
            answers = body.get("answers") if isinstance(body.get("answers"), dict) else None
            persist = body.get("persist") is True
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
                    law_service=None,
                    ai_provider=None,
                    ai_model=None,
                    ai_timeout_sec=None,
                    ai_max_tokens=None,
                    ai_temperature=None,
                    max_clause_law_items=0,
                )
                result = dict(bundle.review)
                result["mode"] = "fast"
                result["clause_results"] = bundle.clause_results
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
            ai_provider = create_ai_provider(cfg) if cfg.provider == "openai" and cfg.api_key else None
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
                ai_max_tokens=min(max(cfg.max_tokens, 1800), 2800) if ai_provider else None,
                ai_temperature=cfg.temperature if ai_provider else None,
                max_clause_law_items=2,
            )
            result = dict(bundle.review)
            result["mode"] = "deep"
            result["clause_results"] = bundle.clause_results
            result["clause_meta"] = bundle.meta
            if law_service is not None:
                try:
                    result["law_search"] = law_service.search_for_review(
                        entity=str(entity),
                        contract_type=str(contract_type),
                        text=str(text),
                        matched_rules=(bundle.review.get("matched_rules") if isinstance(bundle.review, dict) else None),
                        scope="contract",
                        max_per_type=2,
                        time_budget_sec=3.0,
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
            ai_enabled = bool(ai_provider) and cfg.provider == "openai"
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
                text = str(doc.get("text", "") or "")
                entity = str(doc.get("entity", "all"))
                contract_type = str(doc.get("contract_type", "all"))
                filename = (doc.get("input") or {}).get("filename")
                answers = doc.get("answers") if isinstance(doc.get("answers"), dict) else {}
                law_cfg = load_law_api_config()
                law_service = LawSearchService(cfg=law_cfg, cache=law_cache) if law_cfg.enabled and law_cfg.api_key else None
                cfg = load_ai_config()
                ai_provider = create_ai_provider(cfg) if cfg.provider == "openai" and cfg.api_key else None

                bundle = build_clause_level_result(
                    service=service,
                    entity=entity,
                    contract_type=contract_type,
                    text=text,
                    filename=str(filename) if isinstance(filename, str) else None,
                    answers=answers,
                    law_service=law_service,
                    ai_provider=ai_provider,
                    ai_model=cfg.model if ai_provider else None,
                    ai_timeout_sec=cfg.timeout_sec if ai_provider else None,
                    ai_max_tokens=min(max(cfg.max_tokens, 2400), 3600) if ai_provider else None,
                    ai_temperature=cfg.temperature if ai_provider else None,
                    max_clause_law_items=2,
                )
                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "session_id": session_id,
                        "input": {"entity": entity, "contract_type": contract_type, "filename": filename},
                        "review_summary": bundle.review.get("summary"),
                        "revision": bundle.revision,
                        "clause_results": bundle.clause_results,
                        "meta": bundle.meta,
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
            ai_provider = create_ai_provider(cfg) if cfg.provider == "openai" and cfg.api_key else None
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
                ai_max_tokens=min(max(cfg.max_tokens, 2400), 3600) if ai_provider else None,
                ai_temperature=cfg.temperature if ai_provider else None,
                max_clause_law_items=2,
            )
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "input": {"entity": entity, "contract_type": contract_type, "filename": filename},
                    "review_summary": bundle.review.get("summary"),
                    "revision": bundle.revision,
                    "clause_results": bundle.clause_results,
                    "meta": bundle.meta,
                },
            )

        def _handle_revision_download_docx(self, service: RuleQueryService) -> None:
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
                ai_provider = create_ai_provider(cfg) if cfg.provider == "openai" and cfg.api_key else None
                if ai_mode == "off":
                    ai_provider = None
                elif ai_mode == "on" and ai_provider is None:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "ai_mode=on but OPENAI_API_KEY is not configured"})
                    return

                bundle = build_clause_level_result(
                    service=service,
                    entity=entity,
                    contract_type=contract_type,
                    text=text,
                    filename=str(filename) if isinstance(filename, str) else None,
                    answers=answers,
                    law_service=law_service,
                    ai_provider=ai_provider,
                    ai_model=cfg.model if ai_provider else None,
                    ai_timeout_sec=cfg.timeout_sec if ai_provider else None,
                    ai_max_tokens=min(max(cfg.max_tokens, 2400), 3600) if ai_provider else None,
                    ai_temperature=cfg.temperature if ai_provider else None,
                    max_clause_law_items=2,
                )
                if isinstance(bundle.meta, dict) and bundle.meta.get("docx_allowed") is False:
                    _json_response(
                        self,
                        HTTPStatus.BAD_REQUEST,
                        {"error": "insufficient contract text for docx generation", "meta": bundle.meta},
                    )
                    return
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
                    for c in (bundle.clauses or [])
                ]
                detected_rule_ids = [
                    r.get("rule_id")
                    for r in (bundle.review.get("matched_rules") or [])
                    if isinstance(r, dict) and isinstance(r.get("rule_id"), str)
                ]
                contract_law_search = None
                law_topics = None
                if law_service is not None:
                    try:
                        contract_law_search = law_service.search_for_review(
                            entity=entity,
                            contract_type=contract_type,
                            text=text,
                            matched_rules=bundle.review.get("matched_rules") if isinstance(bundle.review, dict) else None,
                            scope="contract",
                            max_per_type=2,
                            context={
                                "review_posture": (bundle.meta.get("review_posture") if isinstance(bundle.meta, dict) else None),
                                "party_role": (bundle.meta.get("party_role") if isinstance(bundle.meta, dict) else None),
                            },
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
                    contract_text=text,
                    clause_results=bundle.clause_results,
                    max_questions=7,
                )
                try:
                    docx_bytes = build_revision_docx(
                        entity=entity,
                        contract_type=contract_type,
                        filename=str(filename) if isinstance(filename, str) else None,
                        original_clauses=original_clauses,
                        clause_results=bundle.clause_results,
                        review_summary=(bundle.review.get("summary") if isinstance(bundle.review, dict) and isinstance(bundle.review.get("summary"), dict) else None),
                        law_search=(contract_law_search if isinstance(contract_law_search, dict) else None),
                        questions=[question_to_dict(q) for q in qs],
                    )
                except Exception as exc:
                    _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "docx generation failed", "detail": sanitize_error_message(str(exc))})
                    return
                _binary_response(
                    self,
                    HTTPStatus.OK,
                    docx_bytes,
                    filename="aouribot_revision.docx",
                    content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
                return

            clause_results = body.get("clause_results")
            original_clauses = body.get("original_clauses")
            meta = body.get("input") if isinstance(body.get("input"), dict) else {}
            if not isinstance(clause_results, list):
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "session_id or clause_results required"})
                return
            if not isinstance(original_clauses, list):
                if clause_results:
                    original_clauses = [
                        {
                            "clause_id": str(cr.get("clause_id") or ""),
                            "clause_title": str(cr.get("clause_title") or ""),
                            "text": str(cr.get("original_text") or ""),
                        }
                        for cr in clause_results
                        if isinstance(cr, dict)
                    ]
                else:
                    contract_text = body.get("contract_text") or body.get("text") or ""
                    if isinstance(contract_text, str) and contract_text.strip():
                        original_clauses = [{"clause_id": "KR-000", "article_number": "", "clause_title": "(전체)", "text": contract_text}]
                    else:
                        original_clauses = []
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
            review = service.analyze(
                ReviewInput(
                    entity=entity,
                    contract_type=contract_type,
                    text=contract_text,
                    filename=filename,
                    answers=None,
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
            )
            try:
                docx_bytes = build_revision_docx(
                    entity=entity,
                    contract_type=contract_type,
                    filename=str(filename) if isinstance(filename, str) else None,
                    original_clauses=original_clauses,
                    clause_results=clause_results,
                    review_summary=(review.get("summary") if isinstance(review, dict) and isinstance(review.get("summary"), dict) else None),
                    law_search=(contract_law_search if isinstance(contract_law_search, dict) else None),
                    questions=[question_to_dict(q) for q in qs],
                )
            except Exception as exc:
                _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "docx generation failed", "detail": sanitize_error_message(str(exc))})
                return
            _binary_response(
                self,
                HTTPStatus.OK,
                docx_bytes,
                filename="aouribot_revision.docx",
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

            review = service.analyze(
                ReviewInput(
                    entity=entity,
                    contract_type=contract_type,
                    text=text,
                    filename=filename,
                    answers=None,
                )
            )
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
            clause_bundle = build_clause_level_result(
                service=service,
                entity=str(entity),
                contract_type=str(contract_type),
                text=str(text),
                filename=str(filename) if isinstance(filename, str) else None,
                answers=None,
                law_service=None,
                ai_provider=None,
                ai_model=None,
                ai_timeout_sec=None,
                ai_max_tokens=None,
                ai_temperature=None,
                max_clause_law_items=0,
            )
            questions = generate_questions(
                str(entity),
                str(contract_type),
                detected_rule_ids=detected_rule_ids,
                law_topics=law_topics,
                contract_text=str(text),
                clause_results=clause_bundle.clause_results,
                max_questions=7,
            )
            q_items = [question_to_dict(q) for q in questions]
            ai_meta: dict[str, Any] | None = None
            cfg = load_ai_config()
            if cfg.provider == "openai" and cfg.api_key and q_items:
                provider = create_ai_provider(cfg)
                app_dev_hint = any(
                    k in str(contract_type or "")
                    for k in (
                        "앱개발",
                        "소프트웨어개발",
                        "SI",
                        "유지보수",
                        "SaaS",
                        "API",
                    )
                ) or any(k in str(text or "") for k in ("앱 개발", "소프트웨어 개발", "시스템 개발", "SLA", "소스코드", "산출물"))
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
                        max_questions=7,
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
            _json_response(
                self,
                HTTPStatus.OK,
                {
                    "input": {"entity": entity, "contract_type": contract_type, "filename": filename},
                    "detected_rule_ids": detected_rule_ids,
                    "count": len(questions),
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
            if cfg.provider == "openai" and cfg.api_key and isinstance(result.get("draft_text"), str):
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
                                "note": "MVP에서 지원하지 않는 포맷이거나 텍스트 추출 실패(OCR/hwp/pdflayer 등 backlog).",
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
                                "note": "MVP에서 지원하지 않는 포맷이거나 텍스트 추출 실패(OCR/hwp/pdflayer 등 backlog).",
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
                        intake={},
                        source="upload",
                    )
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
                        },
                    )
            except Exception as exc:
                _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

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

