EP_LEGAL_REQUEST_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>EP 법무검토신청 (Mock) + AouriBot</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .muted { color: #666; margin-bottom: 16px; }
    .row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; align-items: center; }
    input, select, button, textarea { padding: 6px 8px; font-size: 14px; }
    textarea { width: 100%; min-height: 100px; }
    .tabs { display: flex; gap: 8px; margin: 12px 0; }
    .tab { padding: 8px 10px; border: 1px solid #ddd; border-radius: 8px; cursor: pointer; }
    .tab.active { background: #f5f5f5; }
    .panel { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
    .hidden { display: none; }
    pre { white-space: pre-wrap; word-break: break-word; background: #111; color: #eee; padding: 12px; border-radius: 8px; }
    .qbox { border: 1px solid #eee; border-radius: 8px; padding: 10px; margin: 8px 0; }
    .chat { border: 1px solid #eee; border-radius: 8px; padding: 10px; height: 220px; overflow: auto; background: #fafafa; }
    .msg { margin: 8px 0; display: flex; }
    .msg.bot { justify-content: flex-start; }
    .msg.user { justify-content: flex-end; }
    .bubble { max-width: 80%; padding: 8px 10px; border-radius: 12px; border: 1px solid #ddd; background: #fff; }
    .msg.user .bubble { background: #eef6ff; }
    .badge { display: inline-block; padding: 2px 6px; border-radius: 6px; background: #eee; margin-right: 6px; }
    .small { font-size: 12px; }
    .layout { display: flex; gap: 16px; align-items: flex-start; }
    .left { flex: 1; min-width: 520px; }
    .right { width: 540px; position: sticky; top: 16px; }
  </style>
</head>
<body>
  <h1>EP 법무검토신청 (Mock)</h1>
  <div class="muted">이 레포에는 EP 실코드가 없어서, EP 화면 연동을 검증하기 위한 Mock 화면을 제공합니다.</div>
  <div class="muted"><a href="/admin">AouriBot Admin</a> | <a href="/admin/reviews">Review Results</a> | <a href="/admin/approval">Approval Queue</a></div>

  <div class="layout">
    <div class="left">
      <div class="panel">
        <h2>신청 정보(EP 입력값)</h2>
        <div class="row">
          <input id="epRequestId" placeholder="EP 신청 ID(권장)" />
          <input id="entity" placeholder="법인(entity)" />
          <input id="contractType" placeholder="계약유형(contract_type)" />
        </div>
        <div class="row">
          <input id="counterparty" placeholder="상대방" style="flex:1" />
          <input id="purpose" placeholder="거래 목적" style="flex:1" />
        </div>
        <div class="row">
          <input id="amount" placeholder="금액(옵션)" />
          <input id="termStart" placeholder="기간 시작(YYYY-MM-DD, 옵션)" />
          <input id="termEnd" placeholder="기간 종료(YYYY-MM-DD, 옵션)" />
        </div>
        <div class="row">
          <input type="file" id="file" />
          <button onclick="openAouriBot()" id="openBtn" disabled>아우리봇 패널 열기</button>
        </div>
        <div class="muted">파일 선택 후 “아우리봇 패널 열기” 버튼이 활성화됩니다.</div>
      </div>
    </div>

    <div class="right">
      <div class="tabs">
        <div class="tab active" id="tabReview" onclick="switchTab('review')">아우리봇 검토</div>
        <div class="tab" id="tabDraft" onclick="switchTab('draft')">계약서 초안</div>
        <div class="tab" id="tabRevision" onclick="switchTab('revision')">수정 제안</div>
      </div>

      <div class="panel" id="panelReview">
    <h2>아우리봇 검토</h2>
    <div class="row">
      <button onclick="startSession()" id="startBtn" disabled>검토 시작</button>
      <button onclick="submitAnswersAndRunReview()" id="runBtn" disabled>답변 저장 & 검토 실행</button>
      <select id="handoffSelect" class="small">
        <option value="auto">다음단계: 자동</option>
        <option value="force_approval">다음단계: 결재(법무확인 완료)</option>
      </select>
      <button onclick="handoffToApproval()" id="handoffBtn" disabled>다음 단계로 넘기기</button>
    </div>
    <div class="row">
      <span class="badge" id="statusBadge">status=draft</span>
      <span class="badge" id="issueBadge">issues=0</span>
      <span class="badge" id="approvalBadge">approval_required=0</span>
      <button onclick="refreshStatus()" class="small">상태 새로고침</button>
      <select id="statusSelect" class="small">
        <option value="draft">draft</option>
        <option value="aouribot_in_progress">aouribot_in_progress</option>
        <option value="aouribot_completed">aouribot_completed</option>
        <option value="legal_review_pending">legal_review_pending</option>
        <option value="approval_pending">approval_pending</option>
        <option value="completed">completed</option>
      </select>
      <button onclick="updateStatus()" class="small">상태 변경</button>
    </div>

    <h3>대화/질문</h3>
    <div class="chat" id="chatLog"></div>
    <div class="row">
      <input id="chatInput" placeholder="메모/질문 입력(LLM 없음, 기록용)" style="flex:1" />
      <button onclick="sendChat()">전송</button>
    </div>
    <div class="row small">
      <button onclick="quickAsk('개인정보 처리 있나요?')">추천: 개인정보</button>
      <button onclick="quickAsk('현장 작업(설치/공장) 있나요?')">추천: 현장작업</button>
      <button onclick="quickAsk('대리점/판촉비/비용전가 이슈 있나요?')">추천: 대리점</button>
      <button onclick="quickAsk('기술자료/원가자료 제공 요구 있나요?')">추천: 기술자료</button>
    </div>

    <div id="sessionMeta" class="muted"></div>
    <div id="questionArea"></div>
    <h3>결과</h3>
    <pre id="reviewOut"></pre>
      </div>

      <div class="panel hidden" id="panelDraft">
    <h2>계약서 초안 작성(템플릿 기반, MVP)</h2>
    <div class="row">
      <select id="template"></select>
      <button onclick="loadTemplates()">템플릿 새로고침</button>
      <button onclick="generateDraft()">초안 생성</button>
      <button onclick="downloadDraft()">다운로드(.txt)</button>
    </div>
    <div class="row">
      <input id="partyA" placeholder="당사(예: 퍼시스 주식회사)" style="flex:1" />
      <input id="partyB" placeholder="상대방" style="flex:1" />
    </div>
    <div class="muted">MVP: docx/txt 템플릿만 지원하며, 생성 결과는 텍스트로 표시됩니다.</div>
    <pre id="draftOut"></pre>
      </div>

      <div class="panel hidden" id="panelRevision">
    <h2>계약서 수정 제안(뷰, MVP)</h2>
    <div class="muted">검토 완료 후 session_id 기준으로 조항별 이슈/대체 문안을 표시합니다(실제 redline 제외).</div>
    <div class="row">
      <button onclick="loadRevision()">수정 제안 불러오기</button>
    </div>
    <div id="revisionOut"></div>
      </div>
    </div>
  </div>

  <script>
    let sessionId = null;
    let questions = [];
    let lastUploadPayload = null;

    document.getElementById('file').addEventListener('change', () => {
      document.getElementById('openBtn').disabled = !document.getElementById('file').files[0];
    });

    function switchTab(name) {
      document.getElementById('tabReview').classList.remove('active');
      document.getElementById('tabDraft').classList.remove('active');
      document.getElementById('tabRevision').classList.remove('active');
      document.getElementById('panelReview').classList.add('hidden');
      document.getElementById('panelDraft').classList.add('hidden');
      document.getElementById('panelRevision').classList.add('hidden');
      if (name === 'review') {
        document.getElementById('tabReview').classList.add('active');
        document.getElementById('panelReview').classList.remove('hidden');
      } else if (name === 'draft') {
        document.getElementById('tabDraft').classList.add('active');
        document.getElementById('panelDraft').classList.remove('hidden');
      } else {
        document.getElementById('tabRevision').classList.add('active');
        document.getElementById('panelRevision').classList.remove('hidden');
      }
    }

    function openAouriBot() {
      switchTab('review');
      document.getElementById('startBtn').disabled = false;
      document.getElementById('runBtn').disabled = true;
      document.getElementById('handoffBtn').disabled = true;
      document.getElementById('reviewOut').innerText = '';
      document.getElementById('questionArea').innerHTML = '';
      document.getElementById('sessionMeta').innerText = '준비됨: 검토 시작을 누르세요.';
      resetChat();
    }

    function buildIntake() {
      const f = document.getElementById('file').files[0];
      const intake = {
        ep_request_id: document.getElementById('epRequestId').value || null,
        entity: document.getElementById('entity').value || null,
        contract_type: document.getElementById('contractType').value || null,
        counterparty: document.getElementById('counterparty').value || null,
        purpose: document.getElementById('purpose').value || null,
        amount: document.getElementById('amount').value || null,
        term_start: document.getElementById('termStart').value || null,
        term_end: document.getElementById('termEnd').value || null,
        attachment_names: [f ? f.name : '']
      };
      return intake;
    }

    function renderQuestions() {
      const host = document.getElementById('questionArea');
      host.innerHTML = '';
      for (const q of questions) {
        const box = document.createElement('div');
        box.className = 'qbox';
        box.innerHTML = `<div><b>${q.title}</b> ${q.required ? '(필수)' : ''}</div><div class="muted">${q.description}</div>`;
        const sel = document.createElement('select');
        sel.id = `ans_${q.question_id}`;
        const opt0 = document.createElement('option');
        opt0.value = '';
        opt0.textContent = '(선택)';
        sel.appendChild(opt0);
        for (const o of q.options || []) {
          const opt = document.createElement('option');
          opt.value = o.value;
          opt.textContent = o.label;
          sel.appendChild(opt);
        }
        box.appendChild(sel);
        host.appendChild(box);

        addBot(`질문: ${q.title}`);
      }
    }

    function addBot(text) {
      const host = document.getElementById('chatLog');
      const row = document.createElement('div');
      row.className = 'msg bot';
      row.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
      host.appendChild(row);
      host.scrollTop = host.scrollHeight;
    }

    function addUser(text) {
      const host = document.getElementById('chatLog');
      const row = document.createElement('div');
      row.className = 'msg user';
      row.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
      host.appendChild(row);
      host.scrollTop = host.scrollHeight;
    }

    function resetChat() {
      const host = document.getElementById('chatLog');
      host.innerHTML = '';
      addBot('계약서를 업로드한 뒤 검토 시작을 누르면, 사전 질문이 생성됩니다.');
    }

    function escapeHtml(s) {
      return (s || '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
    }

    function sendChat() {
      const v = document.getElementById('chatInput').value || '';
      if (!v.trim()) return;
      addUser(v.trim());
      document.getElementById('chatInput').value = '';
      addBot('MVP: 메시지는 기록용이며, 질문 답변은 아래 “질문” 영역에서 선택 후 검토 실행합니다.');
    }

    function quickAsk(text) {
      addBot(text);
    }

    async function startSession() {
      const f = document.getElementById('file').files[0];
      if (!f) { alert('파일을 선택하세요'); return; }
      const fd = new FormData();
      fd.append('file', f);
      fd.append('intake_json', JSON.stringify(buildIntake()));

      const res = await fetch('/api/ep/session_start', { method: 'POST', body: fd });
      const data = await res.json();
      lastUploadPayload = data;
      if (data.error) {
        document.getElementById('sessionMeta').innerText = `오류: ${data.error}`;
        document.getElementById('reviewOut').innerText = JSON.stringify(data, null, 2);
        return;
      }
      sessionId = data.question_session_id;
      questions = data.questions || [];
      document.getElementById('sessionMeta').innerText =
        `session_id=${sessionId} inferred=${data.classification && data.classification.is_inferred}`;
      renderQuestions();
      document.getElementById('runBtn').disabled = false;
      document.getElementById('reviewOut').innerText = JSON.stringify(data, null, 2);
      addBot(`세션 생성 완료: ${sessionId}`);
      await refreshStatus();
    }

    async function submitAnswersAndRunReview() {
      if (!sessionId) { alert('먼저 검토 시작을 실행하세요'); return; }
      const answers = {};
      for (const q of questions) {
        const v = document.getElementById(`ans_${q.question_id}`).value;
        if (v) answers[q.question_id] = v;
      }
      addUser('답변 저장 & 검토 실행');
      await fetch(`/api/question_sessions/${sessionId}/answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
      });
      const res2 = await fetch(`/api/question_sessions/${sessionId}/review`, { method: 'POST' });
      const wrap = await res2.json();
      document.getElementById('reviewOut').innerText = JSON.stringify(wrap, null, 2);
      document.getElementById('handoffBtn').disabled = false;
      try {
        const s = wrap.review && wrap.review.summary ? wrap.review.summary : null;
        if (s) {
          document.getElementById('issueBadge').innerText = `issues=${s.matched_rule_count || 0}`;
          document.getElementById('approvalBadge').innerText = `approval_required=${s.approval_required_match_count || 0}`;
        }
      } catch (_) {}
      addBot('검토 완료. 수정 제안 탭 또는 초안 작성 탭을 확인한 뒤 결재로 넘길 수 있습니다.');
      await refreshStatus();
    }

    async function loadRevision() {
      if (!sessionId) { alert('먼저 검토 세션을 시작하세요'); return; }
      const res = await fetch('/api/revision/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId })
      });
      const data = await res.json();
      renderRevision(data);
    }

    function renderRevision(data) {
      const host = document.getElementById('revisionOut');
      host.innerHTML = '';
      if (data.error) {
        host.innerHTML = `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
        return;
      }
      const items = (data.revision && data.revision.items) ? data.revision.items : [];
      const sum = (data.revision && data.revision.summary) ? data.revision.summary : {};
      const head = document.createElement('div');
      head.className = 'muted';
      head.innerText = `issue_clause_count=${sum.issue_clause_count || 0} high_risk_clause_count=${sum.high_risk_clause_count || 0} approval_required_clause_count=${sum.approval_required_clause_count || 0}`;
      host.appendChild(head);

      for (const it of items) {
        const box = document.createElement('div');
        box.className = 'qbox';
        const tags = [];
        if (it.high_risk) tags.push('HIGH_RISK');
        if (it.approval_required) tags.push('APPROVAL_REQUIRED');
        box.innerHTML = `<div><b>${escapeHtml(it.clause_title || it.clause_id)}</b> <span class="muted">${tags.join(' ')}</span></div>`;
        const pre = document.createElement('pre');
        pre.innerText = it.original_clause || '';
        box.appendChild(pre);

        const issues = document.createElement('div');
        const di = it.detected_issues || [];
        issues.innerHTML = `<div><b>검출 이슈</b></div>` + di.map(x => `<div class="small">- ${escapeHtml(x.issue_title)} (risk=${escapeHtml(x.risk_level)} approval=${x.approval_required})</div>`).join('');
        box.appendChild(issues);

        const rules = document.createElement('div');
        const ar = it.applied_rules || [];
        rules.innerHTML = `<div><b>적용 rule</b></div>` + ar.map(x => `<div class="small">- ${escapeHtml(x.rule_id)} (status=${escapeHtml(x.rule_status)} risk=${escapeHtml(x.risk_level)})</div>`).join('');
        box.appendChild(rules);

        const dir = document.createElement('div');
        const sd = it.suggested_direction || [];
        dir.innerHTML = `<div><b>추천 수정 방향</b></div>` + sd.map(x => `<div class="small">- ${escapeHtml(x)}</div>`).join('');
        box.appendChild(dir);

        const fb = document.createElement('div');
        const ft = it.fallback_text || [];
        fb.innerHTML = `<div><b>대체 문안</b></div>` + ft.map(x => `<div class="small">- ${escapeHtml(x)}</div>`).join('');
        box.appendChild(fb);

        host.appendChild(box);
      }
    }

    async function refreshStatus() {
      const epId = document.getElementById('epRequestId').value || null;
      if (!sessionId && !epId) return;
      const url = sessionId ? `/api/ep/status?session_id=${encodeURIComponent(sessionId)}` : `/api/ep/status?ep_request_id=${encodeURIComponent(epId)}`;
      const res = await fetch(url);
      const data = await res.json();
      if (data && data.status) {
        document.getElementById('statusBadge').innerText = `status=${data.status}`;
        document.getElementById('statusSelect').value = data.status;
      }
    }

    async function updateStatus() {
      const epId = document.getElementById('epRequestId').value || null;
      if (!epId) { alert('EP 신청 ID를 입력하세요(상태 연결용)'); return; }
      const status = document.getElementById('statusSelect').value;
      const fromStatus = (document.getElementById('statusBadge').innerText || '').replace('status=', '');
      const res = await fetch('/api/ep/status/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ep_request_id: epId, session_id: sessionId, from_status: fromStatus, status })
      });
      const data = await res.json();
      if (data.error) { alert(data.error); return; }
      await refreshStatus();
      addBot(`상태 변경: ${fromStatus} -> ${status}`);
    }

    async function handoffToApproval() {
      const epId = document.getElementById('epRequestId').value || null;
      if (!epId) { alert('EP 신청 ID를 입력하세요(결재 전환용)'); return; }
      const currentStatus = (document.getElementById('statusBadge').innerText || '').replace('status=', '');
      if (currentStatus !== 'aouribot_completed' && currentStatus !== 'legal_review_pending') {
        alert('결재 전환은 aouribot_completed(또는 legal_review_pending) 이후에 가능합니다.');
        return;
      }
      const sel = document.getElementById('handoffSelect').value || 'auto';
      const force_approval = (sel === 'force_approval');
      const res = await fetch('/api/ep/handoff', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ep_request_id: epId, force_approval })
      });
      const data = await res.json();
      document.getElementById('reviewOut').innerText = JSON.stringify(data, null, 2);
      await refreshStatus();
      try {
        const t = data && data.decision ? data.decision.target_status : null;
        if (t === 'legal_review_pending') addBot('다음 단계: 법무검토 대기 상태로 전환되었습니다.');
        else addBot('다음 단계: 결재 전환 요청을 생성했습니다(현재는 stub).');
      } catch (_) {
        addBot('다음 단계로 넘기기 요청을 처리했습니다.');
      }
    }

    async function loadTemplates() {
      const res = await fetch('/api/draft/templates');
      const data = await res.json();
      const sel = document.getElementById('template');
      sel.innerHTML = '';
      for (const t of data.items || []) {
        const opt = document.createElement('option');
        opt.value = t.template_id;
        opt.textContent = t.supported ? t.filename : `${t.filename} (MVP 미지원)`;
        opt.disabled = !t.supported;
        sel.appendChild(opt);
      }
    }

    async function generateDraft() {
      const template_id = document.getElementById('template').value;
      const entity = document.getElementById('entity').value || '미상';
      const contract_type = document.getElementById('contractType').value || '기타/미분류';
      const party_a = document.getElementById('partyA').value || entity;
      const party_b = document.getElementById('partyB').value || document.getElementById('counterparty').value || '상대방';
      const purpose = document.getElementById('purpose').value || null;
      const payload = { template_id, entity, contract_type, party_a, party_b, purpose };
      const res = await fetch('/api/draft/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      document.getElementById('draftOut').innerText = JSON.stringify(data, null, 2);
    }

    async function downloadDraft() {
      const template_id = document.getElementById('template').value;
      const entity = document.getElementById('entity').value || '미상';
      const contract_type = document.getElementById('contractType').value || '기타/미분류';
      const party_a = document.getElementById('partyA').value || entity;
      const party_b = document.getElementById('partyB').value || document.getElementById('counterparty').value || '상대방';
      const purpose = document.getElementById('purpose').value || null;
      const payload = { template_id, entity, contract_type, party_a, party_b, purpose };
      const res = await fetch('/api/draft/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        const data = await res.json();
        alert(data.error || '다운로드 실패');
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'draft.txt';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }

    loadTemplates();
    resetChat();
  </script>
</body>
</html>
"""

