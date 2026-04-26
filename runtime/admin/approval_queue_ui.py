APPROVAL_QUEUE_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AouriBot Approval Queue (MVP)</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .muted { color: #666; margin-bottom: 16px; }
    .row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
    input, select, button { padding: 6px 8px; font-size: 14px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
    th { background: #f5f5f5; text-align: left; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .panel { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #111; color: #eee; padding: 12px; border-radius: 8px; }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 6px; background: #eee; margin-right: 6px; }
  </style>
</head>
<body>
  <h1>승인 대기함 (MVP)</h1>
  <div class="muted"><a href="/admin">Rules Admin</a> | <a href="/admin/reviews">Review Results</a> | <a href="/upload">Upload</a></div>

  <div class="row">
    <select id="fStatus">
      <option value="">(상태 전체)</option>
      <option value="new">new</option>
      <option value="in_review">in_review</option>
      <option value="approved">approved</option>
      <option value="rejected">rejected</option>
    </select>
    <input id="fEntity" placeholder="법인(entity) 필터" />
    <input id="fType" placeholder="계약유형(contract_type) 필터" />
    <label><input type="checkbox" id="fHighRisk" checked /> high risk 포함</label>
    <label><input type="checkbox" id="fApproval" checked /> approval required 포함</label>
    <button onclick="loadQueue()">조회</button>
  </div>

  <div class="grid">
    <div class="panel">
      <h2>Pending Approval 목록</h2>
      <div id="listMeta" class="muted"></div>
      <table>
        <thead>
          <tr>
            <th>status</th><th>entity</th><th>contract_type</th><th>risk</th><th>approval</th><th>updated_at</th>
          </tr>
        </thead>
        <tbody id="listBody"></tbody>
      </table>
    </div>
    <div class="panel">
      <h2>상세/상태 변경</h2>
      <div id="detailMeta" class="muted"></div>
      <div class="row">
        <span class="badge" id="badgeStatus"></span>
        <span class="badge" id="badgeCounts"></span>
      </div>
      <div class="row">
        <select id="newStatus">
          <option value="new">new</option>
          <option value="in_review">in_review</option>
          <option value="approved">approved</option>
          <option value="rejected">rejected</option>
        </select>
        <button onclick="updateStatus()">상태 변경</button>
      </div>
      <h3>Issues</h3>
      <table>
        <thead><tr><th>severity</th><th>title</th><th>related_rule_id</th></tr></thead>
        <tbody id="issuesBody"></tbody>
      </table>
      <h3>Applied Rules</h3>
      <table>
        <thead><tr><th>rule_id</th><th>status</th><th>risk</th><th>approval</th><th>title</th></tr></thead>
        <tbody id="rulesBody"></tbody>
      </table>
      <h3>Rules Version</h3>
      <pre id="rulesVersionOut"></pre>
    </div>
  </div>

  <script>
    let currentRequestId = null;

    async function loadQueue() {
      const status = encodeURIComponent(document.getElementById('fStatus').value || '');
      const entity = encodeURIComponent(document.getElementById('fEntity').value || '');
      const contract_type = encodeURIComponent(document.getElementById('fType').value || '');
      const high_risk_only = document.getElementById('fHighRisk').checked ? 'true' : 'false';
      const approval_required_only = document.getElementById('fApproval').checked ? 'true' : 'false';
      const url = `/api/approval_queue?limit=50&offset=0&status=${status}&entity=${entity}&contract_type=${contract_type}&high_risk_only=${high_risk_only}&approval_required_only=${approval_required_only}`;
      const res = await fetch(url);
      const data = await res.json();
      document.getElementById('listMeta').innerText = `count=${data.count}`;
      const tbody = document.getElementById('listBody');
      tbody.innerHTML = '';
      for (const it of data.items || []) {
        const tr = document.createElement('tr');
        tr.style.cursor = 'pointer';
        tr.onclick = () => loadDetail(it.request_id);
        tr.innerHTML = `
          <td>${it.status}</td>
          <td>${it.entity}</td>
          <td>${it.contract_type}</td>
          <td>${it.high_risk_count}</td>
          <td>${it.approval_required_count}</td>
          <td>${it.updated_at}</td>`;
        tbody.appendChild(tr);
      }
    }

    async function loadDetail(requestId) {
      currentRequestId = requestId;
      const res = await fetch(`/api/approval_queue/${requestId}`);
      const data = await res.json();
      document.getElementById('detailMeta').innerText = `request_id=${requestId} filename=${data.request.filename || ''}`;
      document.getElementById('badgeStatus').innerText = `status=${data.approval_queue ? data.approval_queue.status : 'n/a'}`;
      document.getElementById('badgeCounts').innerText = `high_risk=${data.result.high_risk_count} approval=${data.result.approval_required_count}`;
      document.getElementById('newStatus').value = data.approval_queue ? data.approval_queue.status : 'new';

      const issuesBody = document.getElementById('issuesBody');
      issuesBody.innerHTML = '';
      for (const it of data.issues || []) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${it.severity}</td><td>${it.title}</td><td>${it.related_rule_id || ''}</td>`;
        issuesBody.appendChild(tr);
      }

      const rulesBody = document.getElementById('rulesBody');
      rulesBody.innerHTML = '';
      for (const it of data.applied_rules || []) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${it.rule_id}</td><td>${it.rule_status}</td><td>${it.risk_level}</td><td>${it.approval_required}</td><td>${it.title}</td>`;
        rulesBody.appendChild(tr);
      }

      document.getElementById('rulesVersionOut').innerText = JSON.stringify(data.rules_version, null, 2);
    }

    async function updateStatus() {
      if (!currentRequestId) { alert('먼저 상세를 선택하세요'); return; }
      const status = document.getElementById('newStatus').value;
      const res = await fetch(`/api/approval_queue/${currentRequestId}/status`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      const data = await res.json();
      if (data.error) { alert(data.error); return; }
      await loadDetail(currentRequestId);
      await loadQueue();
    }

    loadQueue();
  </script>
</body>
</html>
"""

