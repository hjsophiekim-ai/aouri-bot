ADMIN_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AouriBot Rules Admin (Read-only)</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    h1 { margin-bottom: 8px; }
    .muted { color: #666; margin-bottom: 16px; }
    .row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    input, select, button, textarea { padding: 6px 8px; font-size: 14px; }
    textarea { width: 100%; min-height: 120px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
    th { background: #f5f5f5; text-align: left; }
    .tag { display: inline-block; background: #eee; border-radius: 6px; padding: 2px 6px; margin-right: 4px; margin-bottom: 4px; }
    .section { margin-top: 24px; }
    .mono { font-family: Consolas, monospace; font-size: 12px; }
  </style>
</head>
<body>
  <h1>AouriBot Rules Admin</h1>
  <div class="muted">Read-only MVP: confirmed 기반 rule 조회 + backlog 참고 조회</div>
  <div class="muted"><a href="/demo">Internal Demo</a> | <a href="/upload">Upload & Review (MVP)</a> | <a href="/admin/reviews">Review Results</a> | <a href="/admin/approval">Approval Queue</a> | <a href="/ep/mock/legal_request">EP Mock</a></div>

  <div class="section">
    <h2>Rules 조회</h2>
    <div class="row">
      <select id="status">
        <option value="">(전체 status)</option>
        <option value="confirmed_standard">confirmed_standard</option>
        <option value="confirmed_pattern">confirmed_pattern</option>
        <option value="exception_possible">exception_possible</option>
        <option value="approval_required">approval_required</option>
      </select>
      <select id="riskLevel">
        <option value="">(전체 risk_level)</option>
        <option value="high">high</option>
        <option value="medium">medium</option>
        <option value="low">low</option>
      </select>
      <input id="entity" placeholder="entity (예: 퍼시스, 시디즈, all)" />
      <input id="contractType" placeholder="contract_type (예: NDA/비밀유지)" />
      <input id="clauseType" placeholder="clause_type (예: liability/ip/termination)" />
      <button onclick="loadRules()">조회</button>
    </div>
    <div id="versionMeta" class="muted"></div>
    <div id="rulesMeta" class="muted"></div>
    <table id="rulesTable">
      <thead>
        <tr>
          <th>rule_id</th><th>status</th><th>entity</th><th>contract_type</th><th>title</th><th>risk</th><th>approval</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="section">
    <h2>Backlog 참고 조회</h2>
    <button onclick="loadBacklog()">Backlog 조회</button>
    <div id="backlogMeta" class="muted"></div>
    <table id="backlogTable">
      <thead>
        <tr><th>rule_id</th><th>title</th><th>description</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>

  <div class="section">
    <h2>Review Analyze 테스트</h2>
    <div class="row">
      <input id="aEntity" placeholder="entity" value="퍼시스" />
      <input id="aType" placeholder="contract_type" value="물품공급/구매/매매" />
    </div>
    <textarea id="aText">본 계약에서 상대방은 without limitation 책임을 부담한다. 또한 대리점 비용부담을 요구한다.</textarea>
    <div class="row">
      <button onclick="analyze()">Analyze</button>
    </div>
    <pre id="analyzeOut" class="mono"></pre>
  </div>

  <script>
    async function loadRulesVersion() {
      const res = await fetch('/api/rules/version');
      const v = await res.json();
      const sha = (v.rules_sha256 || '').slice(0, 12);
      document.getElementById('versionMeta').innerText =
        `rules_version sha=${sha} schema=${v.schema_version || 'unknown'} loaded_at=${v.loaded_at || '-'} source=${v.source_path || '-'}`;
    }

    async function loadRules() {
      const status = encodeURIComponent(document.getElementById('status').value);
      const riskLevel = encodeURIComponent(document.getElementById('riskLevel').value);
      const entity = encodeURIComponent(document.getElementById('entity').value);
      const contractType = encodeURIComponent(document.getElementById('contractType').value);
      const clauseType = encodeURIComponent(document.getElementById('clauseType').value);
      const url = `/api/rules?status=${status}&risk_level=${riskLevel}&entity=${entity}&contract_type=${contractType}&clause_type=${clauseType}`;
      const res = await fetch(url);
      const data = await res.json();
      document.getElementById('rulesMeta').innerText = `count=${data.count}`;
      const tbody = document.querySelector('#rulesTable tbody');
      tbody.innerHTML = '';
      for (const r of data.items) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${r.rule_id}</td>
          <td>${r.rule_status}</td>
          <td>${r.entity}</td>
          <td>${(r.contract_type || []).join(', ')}</td>
          <td>${r.title}</td>
          <td>${r.risk_level}</td>
          <td>${r.approval_required}</td>`;
        tbody.appendChild(tr);
      }
    }

    async function loadBacklog() {
      const res = await fetch('/api/backlog');
      const data = await res.json();
      document.getElementById('backlogMeta').innerText = `count=${data.count} (참고용)`;
      const tbody = document.querySelector('#backlogTable tbody');
      tbody.innerHTML = '';
      for (const r of data.items) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${r.rule_id}</td><td>${r.title}</td><td>${r.description}</td>`;
        tbody.appendChild(tr);
      }
    }

    async function analyze() {
      const payload = {
        entity: document.getElementById('aEntity').value,
        contract_type: document.getElementById('aType').value,
        text: document.getElementById('aText').value
      };
      const res = await fetch('/api/review/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      document.getElementById('analyzeOut').innerText = JSON.stringify(data, null, 2);
    }

    loadRulesVersion();
    loadRules();
  </script>
</body>
</html>
"""

