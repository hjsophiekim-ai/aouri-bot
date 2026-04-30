INTERNAL_DEMO_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>아우리봇 데모 | 계약 검토</title>
  <link rel="icon" href="/static/aouribot.png" />
  <link rel="apple-touch-icon" href="/static/aouribot.png" />
  <style>
    :root{
      --bg: #f6fbff;
      --card: #ffffff;
      --line: #d8ecff;
      --shadow: 0 10px 30px rgba(0, 87, 170, 0.08);
      --text: #102a43;
      --muted: #5b7086;
      --primary: #1f7ae0;
      --primary2: #2aa8ff;
      --primarySoft: #e7f4ff;
      --primarySoft2: #d8efff;
      --danger: #d64545;
      --dangerSoft: #ffe8e8;
      --warn: #b45309;
      --warnSoft: #fff2db;
      --ok: #0f766e;
      --okSoft: #e7fbf8;
    }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; background: radial-gradient(1200px 600px at 15% 0%, #e8f5ff, var(--bg)); color: var(--text); }
    a { color: var(--primary); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .page { padding: 18px; max-width: 1260px; margin: 0 auto; }
    .header { display:flex; align-items:center; justify-content:space-between; padding: 14px 16px; background: linear-gradient(90deg, rgba(31,122,224,0.08), rgba(42,168,255,0.04)); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow); }
    .brand { display:flex; align-items:center; gap: 10px; }
    .brand img { width: 36px; height: 36px; border-radius: 12px; border: 1px solid var(--line); background: #fff; }
    .brand .title { font-weight: 800; letter-spacing: -0.2px; }
    .brand .subtitle { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .nav { display:flex; gap: 10px; flex-wrap: wrap; }
    .pill { padding: 8px 10px; border-radius: 999px; background: rgba(255,255,255,0.7); border: 1px solid var(--line); color: var(--text); font-size: 13px; }
    .pill:hover { background: #fff; }

    .layout { display: grid; grid-template-columns: 1fr 560px; gap: 16px; align-items: start; margin-top: 14px; }
    .left { min-width: 0; }
    .right { position: sticky; top: 14px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 16px; box-shadow: var(--shadow); padding: 14px; }
    .muted { color: var(--muted); }
    .row { display:flex; gap: 10px; align-items:center; flex-wrap: wrap; }
    .stack { display:flex; flex-direction:column; gap: 12px; }
    .h1 { font-size: 26px; margin: 0; letter-spacing: -0.4px; }
    .h2 { font-size: 16px; margin: 0 0 8px 0; }
    .hero { display:flex; align-items:center; justify-content:space-between; gap: 14px; background: linear-gradient(135deg, rgba(31,122,224,0.10), rgba(42,168,255,0.06)); }
    .hero .copy { min-width: 0; }
    .hero .copy p { margin: 6px 0 0 0; }
    .hero img { width: 120px; height: 120px; object-fit: contain; filter: drop-shadow(0 12px 22px rgba(31,122,224,0.18)); }

    input, select, button, textarea { font-size: 14px; }
    input, select, textarea { width: 100%; padding: 10px 10px; border-radius: 12px; border: 1px solid var(--line); background: #fff; outline: none; }
    textarea { min-height: 220px; resize: vertical; }
    input:focus, select:focus, textarea:focus { border-color: rgba(31,122,224,0.55); box-shadow: 0 0 0 4px rgba(31,122,224,0.12); }
    .fieldGrid { display:grid; grid-template-columns: 180px 1fr; gap: 10px; }
    .fieldGrid2 { display:grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .label { font-size: 12px; color: var(--muted); margin-bottom: 6px; }

    .btn { padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line); background: #fff; cursor:pointer; font-weight: 700; }
    .btnPrimary { background: linear-gradient(90deg, var(--primary), var(--primary2)); border: 0; color: #fff; }
    .btnSoft { background: var(--primarySoft); border: 1px solid var(--line); color: #0c4a6e; }
    .btnGhost { background: transparent; }
    .btn:disabled { opacity: .55; cursor: not-allowed; }

    .tabs { display:flex; gap: 10px; align-items:center; margin: 0 0 10px 0; }
    .tab { padding: 10px 12px; border: 1px solid var(--line); border-radius: 999px; cursor:pointer; font-weight: 800; background: rgba(255,255,255,0.75); }
    .tab.active { background: var(--primarySoft); border-color: rgba(31,122,224,0.3); }
    .hidden { display:none; }

    .badge { display:inline-flex; align-items:center; gap: 6px; padding: 6px 10px; border-radius: 999px; border: 1px solid var(--line); background: #fff; font-weight: 800; font-size: 12px; }
    .badgeBlue { background: var(--primarySoft); color: #0c4a6e; }
    .badgeDanger { background: var(--dangerSoft); color: var(--danger); border-color: rgba(214,69,69,0.25); }
    .badgeWarn { background: var(--warnSoft); color: var(--warn); border-color: rgba(180,83,9,0.25); }
    .badgeOk { background: var(--okSoft); color: var(--ok); border-color: rgba(15,118,110,0.25); }
    .avatarSm { width: 22px; height: 22px; border-radius: 8px; border: 1px solid var(--line); background: #fff; }

    .qbox { border: 1px solid var(--line); border-radius: 14px; padding: 12px; background: #fff; }
    .qtitle { font-weight: 900; white-space: pre-line; }
    .qdesc { margin-top: 4px; font-size: 12px; color: var(--muted); }

    .cards { display:grid; grid-template-columns: 1fr; gap: 10px; }
    .mini { border: 1px dashed rgba(31,122,224,0.25); background: rgba(231,244,255,0.55); }
    .list { margin: 8px 0 0 0; padding-left: 18px; }
    .list li { margin: 4px 0; }
    .kv { display:grid; grid-template-columns: 140px 1fr; gap: 8px; margin-top: 8px; }
    .kv div { font-size: 13px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }

    details { margin-top: 10px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0b1a2a; color: #e8f5ff; padding: 12px; border-radius: 12px; border: 1px solid rgba(216,236,255,0.25); }

    @media (max-width: 1100px) {
      .layout { grid-template-columns: 1fr; }
      .right { position: static; width: auto; }
    }
  </style>
</head>
<body>
  <div class="page">
    <div class="header">
      <div class="brand">
        <img src="/static/aouribot.png" alt="아우리봇" />
        <div>
          <div class="title">아우리봇</div>
          <div class="subtitle">계약 검토 포인트를 먼저 찾아드리는 법무 AI 비서 (MVP)</div>
        </div>
      </div>
      <div class="nav">
        <a class="pill" href="/admin">Admin</a>
        <a class="pill" href="/upload">Upload</a>
        <a class="pill" href="/ep/mock/legal_request">EP Mock</a>
      </div>
    </div>

    <div class="layout">
      <div class="left stack">
        <div class="card hero">
          <div class="copy">
            <h1 class="h1">무슨 계약을 검토하고 싶으세요?</h1>
            <p class="muted">계약서를 붙여넣거나 업로드하면 아우리봇이 먼저 검토 포인트를 찾아드릴게요.</p>
          </div>
          <img src="/static/aouribot.png" alt="아우리봇 캐릭터" />
        </div>

        <div class="card">
          <div class="row" style="justify-content:space-between;">
            <h2 class="h2">계약 정보</h2>
            <span class="badge badgeBlue"><img class="avatarSm" src="/static/aouribot.png" alt="aouribot" />시연용</span>
          </div>
          <div class="fieldGrid">
            <div>
              <div class="label">법인(entity)</div>
              <input id="entity" placeholder="예: 퍼시스 / 시디즈 / 일룸 / 바로스" value="퍼시스" />
            </div>
            <div>
              <div class="label">계약유형(contract_type)</div>
              <input id="contractType" placeholder="예: 물품공급/구매/매매, NDA/비밀유지" value="물품공급/구매/매매" />
            </div>
          </div>
          <div style="margin-top:10px;">
            <div class="label">계약 내용(텍스트)</div>
            <textarea id="text"></textarea>
          </div>
          <div class="row" style="margin-top:10px;">
            <button class="btn btnSoft" onclick="generateQuestions()">질문 생성</button>
            <button class="btn btnPrimary" onclick="runAnalyze()">검토 실행</button>
            <button class="btn btnGhost" onclick="switchTab('revision')">수정 제안 보기</button>
            <button class="btn btnGhost" onclick="switchTab('draft')">초안 작성 보기</button>
          </div>
          <div class="row" style="margin-top:10px;">
            <span class="badge badgeOk" id="sumMatched">detected_issues=0</span>
            <span class="badge badgeWarn" id="sumApproval">approval_required=false</span>
            <span class="badge badgeDanger" id="sumHigh">high_risk=false</span>
          </div>
        </div>

        <div class="card">
          <div class="row" style="justify-content:space-between;">
            <h2 class="h2">질문/답변</h2>
            <span class="muted" style="font-size:12px;">답변을 반영하면 적용 rule 범위가 달라질 수 있어요.</span>
          </div>
          <div id="questionArea" class="stack"></div>
          <div class="row" style="margin-top:10px;">
            <button class="btn btnPrimary" onclick="applyAnswersAndReAnalyze()">답변 반영해서 재검토</button>
          </div>
        </div>
      </div>

      <div class="right">
        <div class="tabs">
          <div class="tab active" id="tabSummary" onclick="switchTab('summary')">결과</div>
          <div class="tab" id="tabRevision" onclick="switchTab('revision')">수정 제안</div>
          <div class="tab" id="tabDraft" onclick="switchTab('draft')">초안 작성</div>
        </div>

        <div class="card" id="panelSummary">
          <div class="row" style="justify-content:space-between;">
            <h2 class="h2">검토 결과</h2>
            <span class="badge badgeBlue"><img class="avatarSm" src="/static/aouribot.png" alt="aouribot" /><span id="resultCopy">아직 검토 전이에요</span></span>
          </div>
          <div class="row" id="progressRow" style="margin-top:10px; display:none;">
            <span class="badge badgeBlue" id="progressStage">진행: -</span>
            <span class="badge" id="progressEta">남은 시간: -</span>
            <span class="badge" id="progressElapsed">경과: 0s</span>
          </div>
          <div class="cards">
            <div class="card mini">
              <div class="row" style="justify-content:space-between;">
                <div style="font-weight:900;">검토 요약</div>
                <span class="badge badgeBlue mono" id="metaEntity">-</span>
              </div>
              <div class="kv">
                <div class="muted">적용 rule</div><div id="kvApplicable">-</div>
                <div class="muted">검출 이슈</div><div id="kvMatched">-</div>
                <div class="muted">체크리스트</div><div id="kvChecklist">-</div>
              </div>
            </div>

            <div class="card mini">
              <div style="font-weight:900;">high risk / approval required</div>
              <div class="row" style="margin-top:8px;">
                <span class="badge badgeDanger" id="badgeHigh">HIGH RISK</span>
                <span class="badge badgeWarn" id="badgeApproval">APPROVAL REQUIRED</span>
              </div>
              <div class="muted" style="margin-top:8px; font-size:12px;">업무 라우팅 신호로만 사용하고, 최종 판단은 사람이 확인하세요.</div>
            </div>

            <div class="card mini">
              <div style="font-weight:900;">detected issues</div>
              <ul class="list" id="issueList"></ul>
            </div>

            <div class="card mini">
              <div style="font-weight:900;">질문 답변 요약</div>
              <div class="muted" style="font-size:12px; margin-top:6px;">선택한 답변이 없으면 비어있을 수 있어요.</div>
              <ul class="list" id="answerList"></ul>
            </div>

            <div class="card mini">
              <div class="row" style="justify-content:space-between;">
                <div style="font-weight:900;">수정 제안</div>
                <button class="btn btnSoft" onclick="switchTab('revision')">열기</button>
              </div>
              <div class="muted" style="margin-top:6px;" id="revisionMeta">아직 생성 전</div>
            </div>

            <div class="card mini">
              <div class="row" style="justify-content:space-between;">
                <div style="font-weight:900;">초안 추천</div>
                <button class="btn btnSoft" onclick="switchTab('draft')">열기</button>
              </div>
              <div class="muted" style="margin-top:6px;" id="draftMeta">아직 추천 전</div>
            </div>
          </div>

          <details>
            <summary class="muted">원본 JSON 보기</summary>
            <pre id="out"></pre>
          </details>
        </div>

        <div class="card hidden" id="panelRevision">
          <div class="row" style="justify-content:space-between;">
            <h2 class="h2">조항별 수정 제안</h2>
            <span class="badge badgeBlue"><img class="avatarSm" src="/static/aouribot.png" alt="aouribot" />설명 가능한 뷰</span>
          </div>
          <div class="row">
            <button class="btn btnPrimary" onclick="loadRevision()">수정 제안 생성</button>
          </div>
          <div id="revisionOut" class="stack" style="margin-top:10px;"></div>
        </div>

        <div class="card hidden" id="panelDraft">
          <div class="row" style="justify-content:space-between;">
            <h2 class="h2">템플릿형 초안 작성</h2>
            <span class="badge badgeBlue"><img class="avatarSm" src="/static/aouribot.png" alt="aouribot" />템플릿 기반</span>
          </div>
          <div class="row">
            <select id="template" style="flex:1"></select>
            <button class="btn btnSoft" onclick="loadTemplates()">목록</button>
            <button class="btn btnSoft" onclick="suggestTemplates()">추천</button>
          </div>
          <div class="fieldGrid2" style="margin-top:10px;">
            <div>
              <div class="label">당사</div>
              <input id="partyA" placeholder="당사" value="퍼시스 주식회사" />
            </div>
            <div>
              <div class="label">상대방</div>
              <input id="partyB" placeholder="상대방" value="상대방" />
            </div>
          </div>
          <div style="margin-top:10px;">
            <div class="label">거래 목적(옵션)</div>
            <input id="purpose" placeholder="예: 물품 공급, 공동마케팅 등" />
          </div>
          <div class="row" style="margin-top:10px;">
            <button class="btn btnPrimary" onclick="generateDraft()">초안 생성</button>
            <button class="btn btnSoft" onclick="downloadDraft()">다운로드(.txt)</button>
          </div>
          <details style="margin-top:10px;">
            <summary class="muted">초안 결과(JSON)</summary>
            <pre id="draftOut"></pre>
          </details>
        </div>
      </div>
    </div>
  </div>

  <script>
    let lastReview = null;
    let lastQuestions = [];
    let analyzeState = { active:false, startedAt:0, expectedTotalSec:40, timer:null };

    function showProgress(show) {
      document.getElementById('progressRow').style.display = show ? 'flex' : 'none';
    }

    function _sec(n) {
      const x = Math.max(0, Math.round(Number(n || 0)));
      return `${x}s`;
    }

    function startProgress(stage, expectedTotalSec) {
      analyzeState.active = true;
      analyzeState.startedAt = Date.now();
      analyzeState.expectedTotalSec = Math.max(20, Math.min(60, Number(expectedTotalSec || 40)));
      showProgress(true);
      document.getElementById('progressStage').innerText = `진행: ${stage || '-'}`;
      if (analyzeState.timer) clearInterval(analyzeState.timer);
      analyzeState.timer = setInterval(() => {
        if (!analyzeState.active) return;
        const elapsed = (Date.now() - analyzeState.startedAt) / 1000.0;
        const remain = Math.max(0, analyzeState.expectedTotalSec - elapsed);
        document.getElementById('progressElapsed').innerText = `경과: ${_sec(elapsed)}`;
        document.getElementById('progressEta').innerText = `남은 시간: 약 ${_sec(remain)}`;
      }, 250);
    }

    function setProgressStage(stage) {
      document.getElementById('progressStage').innerText = `진행: ${stage || '-'}`;
    }

    function stopProgress() {
      analyzeState.active = false;
      if (analyzeState.timer) clearInterval(analyzeState.timer);
      analyzeState.timer = null;
    }

    function switchTab(name) {
      for (const id of ['Summary','Revision','Draft']) {
        document.getElementById('tab'+id).classList.remove('active');
        document.getElementById('panel'+id).classList.add('hidden');
      }
      if (name === 'summary') { document.getElementById('tabSummary').classList.add('active'); document.getElementById('panelSummary').classList.remove('hidden'); }
      if (name === 'revision') { document.getElementById('tabRevision').classList.add('active'); document.getElementById('panelRevision').classList.remove('hidden'); }
      if (name === 'draft') { document.getElementById('tabDraft').classList.add('active'); document.getElementById('panelDraft').classList.remove('hidden'); }
    }

    function escapeHtml(s) {
      return (s || '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
    }

    function cleanClauseTitle(it) {
      const dp0 = String((it && (it.display_path || it.clause_id)) || '').trim();
      let t0 = String((it && it.clause_title) || '').trim();
      if (dp0 && t0 && t0.startsWith(dp0 + ' ')) t0 = t0.slice(dp0.length).trim();
      if (dp0 && t0 && t0.startsWith(dp0)) t0 = t0.slice(dp0.length).trim();
      if (dp0 && t0) {
        const first = t0.split(' ')[0] || '';
        const isKrTok = (/^제\\s*\\d{1,4}\\s*조$/.test(first) || /^제\\s*\\d{1,4}\\s*항$/.test(first) || /^\\d{1,4}\\s*호$/.test(first) || /^[가-하]\\s*목$/.test(first));
        if (isKrTok && dp0.includes(first)) t0 = t0.slice(first.length).trim();
      }
      if (t0.startsWith('[') && t0.endsWith(']')) t0 = t0.slice(1, -1).trim();
      return t0;
    }

    function formatClauseLabel(it) {
      const title = cleanClauseTitle(it);
      const a = String((it && it.article_number) || '').trim();
      const p = String((it && it.paragraph_number) || '').trim();
      const i = String((it && it.item_number) || '').trim();
      const s = String((it && it.subitem_number) || '').trim();
      const lines = [];
      if (a) lines.push(`제${a}조${title ? ` [${title}]` : ''}`);
      else {
        const dp0 = String((it && (it.display_path || it.clause_id)) || '').trim();
        lines.push((dp0 ? (dp0 + (title ? ` [${title}]` : '')) : (title || '조항')).trim());
      }
      if (p) lines.push(`제${p}항`);
      if (i) lines.push(`제${i}호`);
      if (s) lines.push(`${s}목`);
      return lines.join('\\n');
    }

    function getBasePayload() {
      return {
        entity: document.getElementById('entity').value || 'all',
        contract_type: document.getElementById('contractType').value || 'all',
        filename: 'internal_demo.txt',
        text: document.getElementById('text').value || ''
      };
    }

    function renderSummary(review) {
      const s = review && review.summary ? review.summary : {};
      const entity = review && review.input ? (review.input.entity || '-') : '-';
      const ct = review && review.input ? (review.input.contract_type || '-') : '-';
      document.getElementById('metaEntity').innerText = `${entity} / ${ct}`;

      document.getElementById('sumHigh').innerText = `high_risk=${!!s.high_risk}`;
      document.getElementById('sumApproval').innerText = `approval_required=${!!s.approval_required}`;
      document.getElementById('sumMatched').innerText = `detected_issues=${s.matched_rule_count || 0}`;

      document.getElementById('kvApplicable').innerText = `${s.applicable_rule_count || 0}개`;
      document.getElementById('kvMatched').innerText = `${s.matched_rule_count || 0}개`;
      document.getElementById('kvChecklist').innerText = `${s.checklist_rule_count || 0}개`;

      document.getElementById('badgeHigh').className = 'badge ' + ((s.high_risk) ? 'badgeDanger' : 'badgeOk');
      document.getElementById('badgeHigh').innerText = (s.high_risk) ? 'HIGH RISK 있음' : 'HIGH RISK 없음';
      document.getElementById('badgeApproval').className = 'badge ' + ((s.approval_required) ? 'badgeWarn' : 'badgeOk');
      document.getElementById('badgeApproval').innerText = (s.approval_required) ? 'APPROVAL REQUIRED' : '결재 필요 없음';

      const issueList = document.getElementById('issueList');
      issueList.innerHTML = '';
      const matched = review && Array.isArray(review.matched_rules) ? review.matched_rules : [];
      if (matched.length === 0) {
        const li = document.createElement('li');
        li.innerText = '검출된 이슈가 없어요. (체크리스트를 확인해 주세요)';
        issueList.appendChild(li);
      } else {
        for (const r of matched.slice(0, 12)) {
          const li = document.createElement('li');
          const title = r.title || r.rule_id || 'rule';
          li.innerText = `${title} (${r.rule_id || '-'} / risk=${r.risk_level || '-'})`;
          issueList.appendChild(li);
        }
      }

      const answerList = document.getElementById('answerList');
      answerList.innerHTML = '';
      const ans = review && review.question_answers ? review.question_answers : {};
      const keys = Object.keys(ans || {});
      if (keys.length === 0) {
        const li = document.createElement('li');
        li.innerText = '선택한 답변이 아직 없어요.';
        answerList.appendChild(li);
      } else {
        for (const k of keys) {
          const li = document.createElement('li');
          li.innerText = `${k}: ${ans[k]}`;
          answerList.appendChild(li);
        }
      }

      document.getElementById('resultCopy').innerText = '검토가 완료되었어요';
    }

    function renderQuestions(qs) {
      lastQuestions = qs || [];
      const host = document.getElementById('questionArea');
      host.innerHTML = '';
      for (const q of lastQuestions) {
        const box = document.createElement('div');
        box.className = 'qbox';
        box.innerHTML = `<div class="qtitle">${escapeHtml(q.title || q.question_id)} ${q.required ? '<span class="muted">(필수)</span>' : ''}</div><div class="qdesc">${escapeHtml(q.description || '')}</div>`;
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
      }
    }

    async function runAnalyzeWithAnswers(answers) {
      const payload = getBasePayload();
      payload.answers = answers || {};
      document.getElementById('resultCopy').innerText = '좋아요. 이제 검토 결과를 정리해볼게요.';
      startProgress('규칙 분석', 40);

      const fastRes = await fetch('/api/review/analyze_fast', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
      const fast = await fastRes.json();
      lastReview = fast;
      document.getElementById('out').innerText = JSON.stringify(fast, null, 2);
      renderSummary(fast);

      const meta = (fast && fast.clause_meta) ? fast.clause_meta : {};
      const clauseCount = Number(meta.clause_count || 0) || (Array.isArray(fast && fast.clause_results) ? fast.clause_results.length : 0);
      const textLen = Number(meta.text_length || 0) || (String(payload.text || '').length);
      analyzeState.expectedTotalSec = Math.max(20, Math.min(60, 18 + Math.round(clauseCount * 2.1) + (textLen > 9000 ? 10 : 0)));

      setProgressStage('법령/AI 정밀 검토');
      fetch('/api/review/analyze_deep', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) })
        .then(r => r.json())
        .then(deep => {
          lastReview = deep;
          document.getElementById('out').innerText = JSON.stringify(deep, null, 2);
          renderSummary(deep);
          document.getElementById('resultCopy').innerText = '검토가 완료되었어요';
          setProgressStage('완료');
          stopProgress();
        })
        .catch(() => {
          document.getElementById('resultCopy').innerText = '정밀 검토 중 오류가 발생했어요. 재시도해 주세요.';
          setProgressStage('오류');
          stopProgress();
        });

      return fast;
    }

    async function runAnalyze() {
      await runAnalyzeWithAnswers({});
    }

    async function generateQuestions() {
      const payload = getBasePayload();
      const res = await fetch('/api/questions/generate', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
      const data = await res.json();
      if (data.error) { alert(data.error); return; }
      renderQuestions(data.questions || []);
      document.getElementById('out').innerText = JSON.stringify(data, null, 2);
      document.getElementById('resultCopy').innerText = '질문을 준비했어요';
    }

    async function applyAnswersAndReAnalyze() {
      const answers = {};
      for (const q of lastQuestions) {
        const v = document.getElementById(`ans_${q.question_id}`).value;
        if (v) answers[q.question_id] = v;
      }
      await runAnalyzeWithAnswers(answers);
    }

    async function loadRevision() {
      const payload = getBasePayload();
      payload.answers = (lastReview && lastReview.question_answers) ? lastReview.question_answers : {};
      const res = await fetch('/api/revision/suggest_text', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
      const data = await res.json();
      renderRevision(data);
    }

    function renderRevision(data) {
      const host = document.getElementById('revisionOut');
      host.innerHTML = '';
      if (data.error) { host.innerHTML = `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`; return; }
      const items = (data.revision && data.revision.items) ? data.revision.items : [];
      const sum = (data.revision && data.revision.summary) ? data.revision.summary : {};
      document.getElementById('revisionMeta').innerText = `이슈 조항 ${sum.issue_clause_count || 0}개 · high risk ${sum.high_risk_clause_count || 0}개 · approval ${sum.approval_required_clause_count || 0}개`;
      document.getElementById('resultCopy').innerText = '수정 제안을 정리했어요';
      for (const it of items) {
        const box = document.createElement('div');
        box.className = 'qbox';
        const tags = [];
        if (it.high_risk) tags.push('HIGH_RISK');
        if (it.approval_required) tags.push('APPROVAL_REQUIRED');
        box.innerHTML = `<div class="row" style="justify-content:space-between;"><div class="qtitle">${escapeHtml(formatClauseLabel(it))}</div><div class="muted small">${tags.join(' ')}</div></div>`;
        const pre = document.createElement('pre');
        pre.innerText = it.original_clause || '';
        box.appendChild(pre);

        const rules = document.createElement('div');
        const ar = it.applied_rules || [];
        rules.innerHTML = `<div style="font-weight:900; margin-top:10px;">적용 rule</div>` + ar.map(x => `<div class="mono" style="margin-top:6px;">- ${escapeHtml(x.rule_id)} / risk=${escapeHtml(x.risk_level)} / approval=${x.approval_required} / keywords=${escapeHtml((x.matched_keywords||[]).join(', '))}</div>`).join('');
        box.appendChild(rules);

        const dir = document.createElement('div');
        const sd = it.suggested_direction || [];
        dir.innerHTML = `<div style="font-weight:900; margin-top:10px;">추천 수정 방향</div>` + sd.map(x => `<div style="margin-top:6px; font-size:13px;">- ${escapeHtml(x)}</div>`).join('');
        box.appendChild(dir);

        if (it.recommended_rewrite) {
          const rw = document.createElement('div');
          rw.innerHTML = `<div style="font-weight:900; margin-top:10px;">추천 수정문안</div><div style="margin-top:6px; font-size:13px;">${escapeHtml(it.recommended_rewrite)}</div>`;
          box.appendChild(rw);
        }

        const fb = document.createElement('div');
        const ft = it.fallback_text || [];
        fb.innerHTML = `<div style="font-weight:900; margin-top:10px;">대체 문안(후보)</div>` + ft.map(x => `<div style="margin-top:6px; font-size:13px;">- ${escapeHtml(x)}</div>`).join('');
        box.appendChild(fb);

        host.appendChild(box);
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

    async function suggestTemplates() {
      const ct = document.getElementById('contractType').value || '';
      const res = await fetch(`/api/draft/suggest?contract_type=${encodeURIComponent(ct)}`);
      const data = await res.json();
      if (data.error) { alert(data.error); return; }
      if (data.suggested_template_ids && data.suggested_template_ids.length > 0) {
        document.getElementById('template').value = data.suggested_template_ids[0];
      }
      document.getElementById('draftOut').innerText = JSON.stringify(data, null, 2);
      const sug = data.suggested_template_ids || [];
      document.getElementById('draftMeta').innerText = (sug.length > 0) ? (`추천 템플릿: ` + sug.slice(0,3).join(', ')) : '추천 템플릿이 없어요';
      document.getElementById('resultCopy').innerText = '초안 템플릿을 추천했어요';
    }

    async function generateDraft() {
      const payload = {
        template_id: document.getElementById('template').value,
        entity: document.getElementById('entity').value || '미상',
        contract_type: document.getElementById('contractType').value || '기타/미분류',
        party_a: document.getElementById('partyA').value || '당사',
        party_b: document.getElementById('partyB').value || '상대방',
        purpose: document.getElementById('purpose').value || null
      };
      const res = await fetch('/api/draft/generate', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
      const data = await res.json();
      document.getElementById('draftOut').innerText = JSON.stringify(data, null, 2);
    }

    async function downloadDraft() {
      const payload = {
        template_id: document.getElementById('template').value,
        entity: document.getElementById('entity').value || '미상',
        contract_type: document.getElementById('contractType').value || '기타/미분류',
        party_a: document.getElementById('partyA').value || '당사',
        party_b: document.getElementById('partyB').value || '상대방',
        purpose: document.getElementById('purpose').value || null
      };
      const res = await fetch('/api/draft/download', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
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

    document.getElementById('text').value =
`제10조(손해배상) 당사는 본 계약과 관련하여 발생하는 모든 손해에 대하여 책임 한도 없이(without limitation) 손해배상 책임을 부담한다.
제11조(면책) 상대방은 어떠한 경우에도 당사에 대하여 책임을 부담하지 아니하며, 당사는 상대방을 indemnify 한다.
제12조(기술자료 제출) 당사는 상대방의 요청 시 기술자료, 원가자료, 설계도면 및 소스코드 등 일체 자료를 제출하여야 한다.
제13조(해지) 상대방은 사전 통지 없이 언제든지 본 계약을 즉시 해지할 수 있다.`;

    loadTemplates();
  </script>
</body>
</html>
"""

