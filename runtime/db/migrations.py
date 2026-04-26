from __future__ import annotations

import sqlite3


MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS rules_version_log (
          rules_sha256 TEXT PRIMARY KEY,
          schema_version TEXT NOT NULL,
          loaded_at TEXT NOT NULL,
          source_path TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS review_request (
          request_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          entity TEXT NOT NULL,
          contract_type TEXT NOT NULL,
          filename TEXT,
          source TEXT NOT NULL,
          question_session_id TEXT,
          rules_sha256 TEXT NOT NULL,
          text_sha256 TEXT,
          FOREIGN KEY (rules_sha256) REFERENCES rules_version_log(rules_sha256)
        );

        CREATE TABLE IF NOT EXISTS review_result (
          request_id TEXT PRIMARY KEY,
          created_at TEXT NOT NULL,
          summary_json TEXT NOT NULL,
          raw_json TEXT NOT NULL,
          high_risk_count INTEGER NOT NULL,
          approval_required_count INTEGER NOT NULL,
          FOREIGN KEY (request_id) REFERENCES review_request(request_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_applied_rule (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT NOT NULL,
          rule_id TEXT NOT NULL,
          rule_status TEXT NOT NULL,
          risk_level TEXT NOT NULL,
          matched INTEGER NOT NULL,
          approval_required INTEGER NOT NULL,
          context_expanded_by_questions INTEGER NOT NULL,
          title TEXT NOT NULL,
          FOREIGN KEY (request_id) REFERENCES review_request(request_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS review_issue (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT NOT NULL,
          issue_code TEXT NOT NULL,
          title TEXT NOT NULL,
          severity TEXT NOT NULL,
          description TEXT NOT NULL,
          related_rule_id TEXT,
          FOREIGN KEY (request_id) REFERENCES review_request(request_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_review_request_created_at ON review_request(created_at);
        CREATE INDEX IF NOT EXISTS idx_review_request_entity ON review_request(entity);
        CREATE INDEX IF NOT EXISTS idx_review_request_contract_type ON review_request(contract_type);
        CREATE INDEX IF NOT EXISTS idx_review_result_counts ON review_result(high_risk_count, approval_required_count);
        CREATE INDEX IF NOT EXISTS idx_applied_rule_request ON review_applied_rule(request_id);
        CREATE INDEX IF NOT EXISTS idx_issue_request ON review_issue(request_id);
        """,
    )
    ,
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS approval_queue (
          request_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          FOREIGN KEY (request_id) REFERENCES review_request(request_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_approval_queue_status ON approval_queue(status);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS ep_intake_session (
          session_id TEXT PRIMARY KEY,
          ep_request_id TEXT,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          intake_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ep_intake_session_ep_request_id ON ep_intake_session(ep_request_id);

        CREATE TABLE IF NOT EXISTS ep_request_link (
          ep_request_id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          request_id TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ep_request_link_request_id ON ep_request_link(request_id);
        """,
    ),
    (
        4,
        """
        CREATE TABLE IF NOT EXISTS ep_status_history (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ep_request_id TEXT,
          session_id TEXT,
          status TEXT NOT NULL,
          changed_at TEXT NOT NULL,
          note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_ep_status_history_ep_request_id ON ep_status_history(ep_request_id);
        """,
    ),
    (
        5,
        """
        CREATE TABLE IF NOT EXISTS approval_handoff (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ep_request_id TEXT NOT NULL,
          request_id TEXT NOT NULL,
          handoff_id TEXT NOT NULL,
          idempotency_key TEXT NOT NULL,
          target_status TEXT NOT NULL,
          mode TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          status TEXT NOT NULL,
          attempt_count INTEGER NOT NULL,
          external_reference TEXT,
          error_message TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          UNIQUE(ep_request_id, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_approval_handoff_ep_request_id ON approval_handoff(ep_request_id);
        CREATE INDEX IF NOT EXISTS idx_approval_handoff_request_id ON approval_handoff(request_id);
        """,
    ),
    (
        6,
        """
        CREATE TABLE IF NOT EXISTS review_clause_result (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          request_id TEXT NOT NULL,
          clause_id TEXT NOT NULL,
          clause_title TEXT,
          original_text TEXT,
          suggested_rewrite TEXT,
          rewrite_reason TEXT,
          approval_required INTEGER NOT NULL,
          high_risk INTEGER NOT NULL,
          result_json TEXT NOT NULL,
          FOREIGN KEY (request_id) REFERENCES review_request(request_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_review_clause_request ON review_clause_result(request_id);
        CREATE INDEX IF NOT EXISTS idx_review_clause_clause_id ON review_clause_result(request_id, clause_id);
        """,
    ),
]


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    row = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    return int(row["v"]) if row else 0


def apply_migrations(conn: sqlite3.Connection, now_iso: str) -> None:
    v = current_version(conn)
    for ver, sql in MIGRATIONS:
        if ver <= v:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES(?, ?)",
            (ver, now_iso),
        )
        conn.commit()

