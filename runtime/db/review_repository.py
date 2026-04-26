from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime.db.migrations import apply_migrations
from runtime.db.sqlite import connection


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8", errors="replace")).hexdigest()


@dataclass
class ReviewPersistResult:
    request_id: str
    rules_sha256: str


class ReviewRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path

    def init_db(self) -> None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)

    def upsert_rules_version(self, rules_sha256: str, schema_version: str, source_path: str) -> None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            conn.execute(
                """
                INSERT INTO rules_version_log(rules_sha256, schema_version, loaded_at, source_path)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(rules_sha256) DO UPDATE SET
                  schema_version=excluded.schema_version,
                  loaded_at=excluded.loaded_at,
                  source_path=excluded.source_path
                """,
                (rules_sha256, schema_version, now, source_path),
            )
            conn.commit()

    def get_rules_version(self, rules_sha256: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            row = conn.execute(
                """
                SELECT rules_sha256, schema_version, loaded_at, source_path
                FROM rules_version_log
                WHERE rules_sha256 = ?
                """,
                (rules_sha256,),
            ).fetchone()
            return dict(row) if row else None

    def save_review(
        self,
        entity: str,
        contract_type: str,
        filename: str | None,
        source: str,
        question_session_id: str | None,
        rules_sha256: str,
        rules_schema_version: str,
        rules_source_path: str,
        review_result: dict[str, Any],
        text: str | None,
    ) -> ReviewPersistResult:
        self.upsert_rules_version(rules_sha256, rules_schema_version, rules_source_path)
        now = _utc_now_iso()
        request_id = uuid4().hex
        text_hash = _sha256_text(text) if isinstance(text, str) and text else None

        summary = review_result.get("summary") if isinstance(review_result.get("summary"), dict) else {}
        matched_rules = review_result.get("matched_rules") if isinstance(review_result.get("matched_rules"), list) else []
        approval_required_matches = (
            review_result.get("approval_required_matches")
            if isinstance(review_result.get("approval_required_matches"), list)
            else []
        )
        clause_results = (
            review_result.get("clause_results") if isinstance(review_result.get("clause_results"), list) else []
        )

        high_risk_count = 0
        approval_required_count = len(approval_required_matches)

        for r in matched_rules:
            if not isinstance(r, dict):
                continue
            if str(r.get("risk_level", "")).lower() in ("high", "very_high", "critical"):
                high_risk_count += 1

        raw_json = json.dumps(review_result, ensure_ascii=False)
        summary_json = json.dumps(summary, ensure_ascii=False)

        applied: list[tuple] = []
        for r in matched_rules:
            if not isinstance(r, dict):
                continue
            applied.append(
                (
                    request_id,
                    str(r.get("rule_id", "")),
                    str(r.get("rule_status", "")),
                    str(r.get("risk_level", "")),
                    1,
                    1 if (r.get("approval_required") is True or r.get("rule_status") == "approval_required") else 0,
                    1 if r.get("context_expanded_by_questions") else 0,
                    str(r.get("title", "")),
                )
            )

        issues: list[tuple] = []
        for r in matched_rules:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("rule_id", ""))
            title = str(r.get("title", ""))
            risk = str(r.get("risk_level", ""))
            is_approval = r.get("approval_required") is True or r.get("rule_status") == "approval_required"
            is_high = risk.lower() in ("high", "very_high", "critical")
            if not (is_approval or is_high):
                continue
            severity = "approval_required" if is_approval else "high_risk"
            issues.append(
                (
                    request_id,
                    f"ISSUE-{rid}",
                    title or rid,
                    severity,
                    f"matched rule: {rid} (risk={risk}, status={r.get('rule_status')})",
                    rid,
                )
            )

        clause_rows: list[tuple] = []
        for cr in clause_results:
            if not isinstance(cr, dict):
                continue
            clause_rows.append(
                (
                    request_id,
                    str(cr.get("clause_id") or ""),
                    str(cr.get("clause_title") or ""),
                    str(cr.get("original_text") or ""),
                    str(cr.get("suggested_rewrite") or ""),
                    str(cr.get("rewrite_reason") or ""),
                    1 if cr.get("approval_required") else 0,
                    1 if cr.get("high_risk") else 0,
                    json.dumps(cr, ensure_ascii=False),
                )
            )

        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            conn.execute(
                """
                INSERT INTO review_request(
                  request_id, created_at, entity, contract_type, filename, source, question_session_id,
                  rules_sha256, text_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    now,
                    entity,
                    contract_type,
                    filename,
                    source,
                    question_session_id,
                    rules_sha256,
                    text_hash,
                ),
            )
            conn.execute(
                """
                INSERT INTO review_result(
                  request_id, created_at, summary_json, raw_json, high_risk_count, approval_required_count
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    now,
                    summary_json,
                    raw_json,
                    int(high_risk_count),
                    int(approval_required_count),
                ),
            )
            if applied:
                conn.executemany(
                    """
                    INSERT INTO review_applied_rule(
                      request_id, rule_id, rule_status, risk_level, matched, approval_required,
                      context_expanded_by_questions, title
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    applied,
                )
            if issues:
                conn.executemany(
                    """
                    INSERT INTO review_issue(
                      request_id, issue_code, title, severity, description, related_rule_id
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    issues,
                )
            if clause_rows:
                conn.executemany(
                    """
                    INSERT INTO review_clause_result(
                      request_id, clause_id, clause_title, original_text, suggested_rewrite, rewrite_reason,
                      approval_required, high_risk, result_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    clause_rows,
                )

            if int(high_risk_count) > 0 or int(approval_required_count) > 0:
                conn.execute(
                    """
                    INSERT INTO approval_queue(request_id, status, created_at, updated_at)
                    VALUES(?, ?, ?, ?)
                    ON CONFLICT(request_id) DO UPDATE SET
                      updated_at=excluded.updated_at
                    """,
                    (request_id, "new", now, now),
                )
            conn.commit()

        return ReviewPersistResult(request_id=request_id, rules_sha256=rules_sha256)

    def list_approval_queue(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        entity: str | None = None,
        contract_type: str | None = None,
        risk_level: str | None = None,
        approval_required_only: bool = False,
        high_risk_only: bool = False,
    ) -> list[dict[str, Any]]:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)

            where = []
            params: list[Any] = []
            if status:
                where.append("q.status = ?")
                params.append(status)
            if entity:
                where.append("r.entity LIKE ?")
                params.append(f"%{entity}%")
            if contract_type:
                where.append("r.contract_type LIKE ?")
                params.append(f"%{contract_type}%")
            if approval_required_only:
                where.append("res.approval_required_count > 0")
            if high_risk_only:
                where.append("res.high_risk_count > 0")
            if risk_level:
                where.append("ar.risk_level = ?")
                params.append(risk_level)

            where_sql = (" WHERE " + " AND ".join(where)) if where else ""
            q = f"""
              SELECT q.request_id, q.status, q.created_at AS queued_at, q.updated_at,
                     r.created_at, r.entity, r.contract_type, r.filename, r.source, r.rules_sha256,
                     res.high_risk_count, res.approval_required_count
              FROM approval_queue q
              JOIN review_request r ON r.request_id = q.request_id
              JOIN review_result res ON res.request_id = r.request_id
              LEFT JOIN review_applied_rule ar ON ar.request_id = r.request_id
              {where_sql}
              GROUP BY q.request_id
              ORDER BY q.updated_at DESC
              LIMIT ? OFFSET ?
            """
            params.extend([int(limit), int(offset)])
            rows = conn.execute(q, params).fetchall()
            return [dict(row) for row in rows]

    def update_approval_status(self, request_id: str, status: str) -> None:
        if status not in ("new", "in_review", "approved", "rejected"):
            raise ValueError("invalid status")
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            row = conn.execute(
                "SELECT request_id FROM approval_queue WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if not row:
                raise KeyError("not found")
            conn.execute(
                "UPDATE approval_queue SET status = ?, updated_at = ? WHERE request_id = ?",
                (status, now, request_id),
            )
            conn.commit()

    def get_approval_detail(self, request_id: str) -> dict[str, Any] | None:
        detail = self.get_review_detail(request_id)
        if not detail:
            return None
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            q = conn.execute(
                "SELECT request_id, status, created_at, updated_at FROM approval_queue WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            detail["approval_queue"] = dict(q) if q else None
        return detail

    def list_requests(
        self,
        limit: int = 50,
        offset: int = 0,
        entity: str | None = None,
        contract_type: str | None = None,
        high_risk_only: bool = False,
        approval_required_only: bool = False,
    ) -> list[dict[str, Any]]:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)

            where = []
            params: list[Any] = []
            if entity:
                where.append("r.entity LIKE ?")
                params.append(f"%{entity}%")
            if contract_type:
                where.append("r.contract_type LIKE ?")
                params.append(f"%{contract_type}%")
            if high_risk_only:
                where.append("res.high_risk_count > 0")
            if approval_required_only:
                where.append("res.approval_required_count > 0")

            where_sql = (" WHERE " + " AND ".join(where)) if where else ""
            q = f"""
              SELECT r.request_id, r.created_at, r.entity, r.contract_type, r.filename, r.source, r.rules_sha256,
                     res.high_risk_count, res.approval_required_count
              FROM review_request r
              JOIN review_result res ON res.request_id = r.request_id
              {where_sql}
              ORDER BY r.created_at DESC
              LIMIT ? OFFSET ?
            """
            params.extend([int(limit), int(offset)])
            rows = conn.execute(q, params).fetchall()
            return [dict(row) for row in rows]

    def get_review_detail(self, request_id: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)

            req = conn.execute(
                """
                SELECT request_id, created_at, entity, contract_type, filename, source, question_session_id, rules_sha256
                FROM review_request WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            if not req:
                return None
            res = conn.execute(
                """
                SELECT created_at, summary_json, raw_json, high_risk_count, approval_required_count
                FROM review_result WHERE request_id = ?
                """,
                (request_id,),
            ).fetchone()
            rules_version = conn.execute(
                """
                SELECT rules_sha256, schema_version, loaded_at, source_path
                FROM rules_version_log WHERE rules_sha256 = ?
                """,
                (req["rules_sha256"],),
            ).fetchone()

            applied = conn.execute(
                """
                SELECT rule_id, rule_status, risk_level, matched, approval_required, context_expanded_by_questions, title
                FROM review_applied_rule WHERE request_id = ?
                ORDER BY approval_required DESC, risk_level DESC, rule_id ASC
                """,
                (request_id,),
            ).fetchall()
            issues = conn.execute(
                """
                SELECT issue_code, title, severity, description, related_rule_id
                FROM review_issue WHERE request_id = ?
                ORDER BY severity DESC, issue_code ASC
                """,
                (request_id,),
            ).fetchall()
            clause_rows = conn.execute(
                """
                SELECT clause_id, clause_title, original_text, suggested_rewrite, rewrite_reason,
                       approval_required, high_risk, result_json
                FROM review_clause_result
                WHERE request_id = ?
                ORDER BY approval_required DESC, high_risk DESC, clause_id ASC
                """,
                (request_id,),
            ).fetchall()

            raw_obj = json.loads(res["raw_json"]) if res and res["raw_json"] else {}
            summary_obj = json.loads(res["summary_json"]) if res and res["summary_json"] else {}

            return {
                "request": dict(req),
                "result": {
                    "created_at": res["created_at"] if res else None,
                    "high_risk_count": res["high_risk_count"] if res else 0,
                    "approval_required_count": res["approval_required_count"] if res else 0,
                    "summary": summary_obj,
                    "raw": raw_obj,
                },
                "applied_rules": [dict(r) for r in applied],
                "issues": [dict(r) for r in issues],
                "clauses": [dict(r) for r in clause_rows],
                "rules_version": dict(rules_version) if rules_version else None,
            }

    def upsert_ep_intake_session(
        self,
        session_id: str,
        ep_request_id: str | None,
        status: str,
        intake_json: dict[str, Any],
    ) -> None:
        if status not in (
            "draft",
            "aouribot_in_progress",
            "aouribot_completed",
            "legal_review_pending",
            "approval_pending",
            "completed",
            "error",
        ):
            raise ValueError("invalid status")
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            conn.execute(
                """
                INSERT INTO ep_intake_session(session_id, ep_request_id, status, created_at, updated_at, intake_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  ep_request_id=excluded.ep_request_id,
                  status=excluded.status,
                  updated_at=excluded.updated_at,
                  intake_json=excluded.intake_json
                """,
                (
                    session_id,
                    ep_request_id,
                    status,
                    now,
                    now,
                    json.dumps(intake_json, ensure_ascii=False),
                ),
            )
            conn.execute(
                """
                INSERT INTO ep_status_history(ep_request_id, session_id, status, changed_at, note)
                VALUES(?, ?, ?, ?, ?)
                """,
                (ep_request_id, session_id, status, now, None),
            )
            if ep_request_id:
                conn.execute(
                    """
                    INSERT INTO ep_request_link(ep_request_id, session_id, request_id, created_at, updated_at)
                    VALUES(?, ?, NULL, ?, ?)
                    ON CONFLICT(ep_request_id) DO UPDATE SET
                      session_id=excluded.session_id,
                      updated_at=excluded.updated_at
                    """,
                    (ep_request_id, session_id, now, now),
                )
            conn.commit()

    def link_ep_request_to_review(self, ep_request_id: str, session_id: str, request_id: str) -> None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            conn.execute(
                """
                INSERT INTO ep_request_link(ep_request_id, session_id, request_id, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(ep_request_id) DO UPDATE SET
                  request_id=excluded.request_id,
                  session_id=excluded.session_id,
                  updated_at=excluded.updated_at
                """,
                (ep_request_id, session_id, request_id, now, now),
            )
            conn.commit()

    def get_ep_link(self, ep_request_id: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            row = conn.execute(
                """
                SELECT ep_request_id, session_id, request_id, created_at, updated_at
                FROM ep_request_link WHERE ep_request_id = ?
                """,
                (ep_request_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def get_ep_session_status(self, session_id: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            row = conn.execute(
                """
                SELECT session_id, ep_request_id, status, created_at, updated_at, intake_json
                FROM ep_intake_session WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if not row:
                return None
            obj = dict(row)
            try:
                obj["intake"] = json.loads(obj.pop("intake_json") or "{}")
            except Exception:
                obj["intake"] = {}
                obj.pop("intake_json", None)
            return obj

    def get_latest_ep_status(self, ep_request_id: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            row = conn.execute(
                """
                SELECT ep_request_id, session_id, status, changed_at, note
                FROM ep_status_history
                WHERE ep_request_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ep_request_id,),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def update_ep_status(self, ep_request_id: str, session_id: str | None, status: str, note: str | None) -> None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            if session_id:
                row = conn.execute(
                    "SELECT session_id FROM ep_intake_session WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE ep_intake_session SET status = ?, updated_at = ? WHERE session_id = ?",
                        (status, now, session_id),
                    )
            conn.execute(
                """
                INSERT INTO ep_status_history(ep_request_id, session_id, status, changed_at, note)
                VALUES(?, ?, ?, ?, ?)
                """,
                (ep_request_id, session_id, status, now, note),
            )
            conn.commit()

    def get_approval_handoff_by_idempotency(self, ep_request_id: str, idempotency_key: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            row = conn.execute(
                """
                SELECT *
                FROM approval_handoff
                WHERE ep_request_id = ? AND idempotency_key = ?
                """,
                (ep_request_id, idempotency_key),
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def create_or_increment_approval_handoff(
        self,
        *,
        ep_request_id: str,
        request_id: str,
        handoff_id: str,
        idempotency_key: str,
        target_status: str,
        mode: str,
        payload_json: dict[str, Any],
        initial_status: str,
    ) -> dict[str, Any]:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            existing = conn.execute(
                """
                SELECT *
                FROM approval_handoff
                WHERE ep_request_id = ? AND idempotency_key = ?
                """,
                (ep_request_id, idempotency_key),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE approval_handoff
                    SET attempt_count = attempt_count + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, existing["id"]),
                )
                row = conn.execute(
                    "SELECT * FROM approval_handoff WHERE id = ?",
                    (existing["id"],),
                ).fetchone()
                conn.commit()
                return dict(row) if row else dict(existing)

            conn.execute(
                """
                INSERT INTO approval_handoff(
                  ep_request_id, request_id, handoff_id, idempotency_key,
                  target_status, mode, payload_json, status, attempt_count,
                  external_reference, error_message,
                  created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    ep_request_id,
                    request_id,
                    handoff_id,
                    idempotency_key,
                    target_status,
                    mode,
                    json.dumps(payload_json, ensure_ascii=False),
                    initial_status,
                    1,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                """
                SELECT *
                FROM approval_handoff
                WHERE ep_request_id = ? AND idempotency_key = ?
                """,
                (ep_request_id, idempotency_key),
            ).fetchone()
            conn.commit()
            return dict(row) if row else {}

    def update_approval_handoff_result(
        self,
        handoff_db_id: int,
        *,
        status: str,
        external_reference: str | None,
        error_message: str | None,
    ) -> None:
        now = _utc_now_iso()
        with connection(self.db_path) as conn:
            apply_migrations(conn, now)
            conn.execute(
                """
                UPDATE approval_handoff
                SET status = ?,
                    external_reference = ?,
                    error_message = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, external_reference, error_message, now, handoff_db_id),
            )
            conn.commit()

