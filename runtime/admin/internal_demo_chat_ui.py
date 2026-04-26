from __future__ import annotations


INTERNAL_DEMO_CHAT_HTML = """<!doctype html>
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
      --danger: #d64545;
      --dangerSoft: #ffe8e8;
      --warn: #b45309;
      --warnSoft: #fff2db;
      --ok: #0f766e;
      --okSoft: #e7fbf8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      color: var(--text);
      background: radial-gradient(1200px 600px at 15% 0%, #e8f5ff, var(--bg));
    }
    a { color: var(--primary); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .page { max-width: 980px; margin: 0 auto; padding: 18px; }
    .header {
      display:flex; align-items:center; justify-content:space-between;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: linear-gradient(90deg, rgba(31,122,224,0.08), rgba(42,168,255,0.04));
      box-shadow: var(--shadow);
    }
    .brand { display:flex; align-items:center; gap: 10px; }
    .brand img { width: 34px; height: 34px; border-radius: 12px; border: 1px solid var(--line); background: #fff; }
    .brand .title { font-weight: 900; letter-spacing: -0.2px; }
    .brand .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
    .nav { display:none; }

    .wrap { margin-top: 14px; }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }
    .center {
      min-height: calc(100vh - 120px);
      display:flex;
      align-items:center;
      justify-content:center;
      padding: 10px;
    }
    .start {
      width: 100%;
      max-width: 780px;
      padding: 18px;
      background: linear-gradient(135deg, rgba(31,122,224,0.10), rgba(42,168,255,0.06));
    }
    .hero {
      display:flex;
      align-items:center;
      justify-content:center;
      flex-direction:column;
      text-align:center;
      padding: 12px 10px;
    }
    .hero img {
      width: 130px;
      height: 130px;
      object-fit: contain;
      filter: drop-shadow(0 12px 22px rgba(31,122,224,0.18));
    }
    .h1 { font-size: 28px; margin: 12px 0 0 0; letter-spacing: -0.6px; }
    .sub { margin-top: 8px; color: var(--muted); }

    .form { margin-top: 14px; padding: 14px; background: rgba(255,255,255,0.92); border: 1px solid var(--line); border-radius: 16px; }
    .grid { display:grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .label { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    input, textarea {
      width: 100%;
      padding: 10px 10px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      font-size: 14px;
      outline: none;
    }
    textarea { min-height: 200px; resize: vertical; }
    input:focus, textarea:focus {
      border-color: rgba(31,122,224,0.55);
      box-shadow: 0 0 0 4px rgba(31,122,224,0.12);
    }
    .row { display:flex; gap: 10px; align-items:center; flex-wrap: wrap; }
    .btn {
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      cursor:pointer;
      font-weight: 900;
    }
    .btnPrimary { background: linear-gradient(90deg, var(--primary), var(--primary2)); border: 0; color: #fff; }
    .btnSoft { background: var(--primarySoft); border: 1px solid var(--line); color: #0c4a6e; }
    .btnGhost { background: transparent; }
    .btn:disabled { opacity: .55; cursor: not-allowed; }
    .btnSecondary { background: #fff; border: 1px solid rgba(31,122,224,0.25); color: #0c4a6e; }

    .stage { display:none; }
    .stage.active { display:block; }

    .chatShell { padding: 14px; }
    .progress { display:flex; align-items:center; justify-content:space-between; gap: 10px; padding: 12px 14px; border-bottom: 1px solid var(--line); }
    .progress .left { display:flex; align-items:center; gap: 8px; }
    .badge { display:inline-flex; align-items:center; gap: 6px; padding: 6px 10px; border-radius: 999px; border: 1px solid var(--line); background: #fff; font-weight: 900; font-size: 12px; }
    .badgeOk { background: var(--okSoft); color: var(--ok); border-color: rgba(15,118,110,0.25); }
    .badgeWarn { background: var(--warnSoft); color: var(--warn); border-color: rgba(180,83,9,0.25); }
    .badgeDanger { background: var(--dangerSoft); color: var(--danger); border-color: rgba(214,69,69,0.25); }
    .avatar { width: 26px; height: 26px; border-radius: 10px; border: 1px solid var(--line); background: #fff; }

    .chat { padding: 14px; display:flex; flex-direction:column; gap: 10px; min-height: 420px; }
    .msgRow { display:flex; gap: 10px; align-items:flex-start; }
    .msgRow.me { flex-direction: row-reverse; }
    .bubble {
      max-width: 78%;
      padding: 10px 12px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: #fff;
      box-shadow: 0 6px 18px rgba(16,42,67,0.06);
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
      font-size: 14px;
    }
    .bubble.bot { background: rgba(255,255,255,0.9); }
    .bubble.me { background: var(--primarySoft); border-color: rgba(31,122,224,0.25); }
    .meta { color: var(--muted); font-size: 12px; margin-top: 6px; }
    .clauseCard { border: 1px solid var(--line); border-radius: 14px; padding: 12px; background: rgba(255,255,255,0.9); margin-bottom: 10px; }
    .clauseHead { display:flex; align-items:center; justify-content:space-between; gap: 10px; }
    .clauseTitle { font-weight: 900; }
    .clauseTag { font-size: 12px; padding: 4px 8px; border-radius: 999px; border: 1px solid var(--line); background: #fff; color: var(--muted); }
    .clauseBody { margin-top: 8px; display:grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .clauseBox { border: 1px solid rgba(216,236,255,0.6); border-radius: 12px; padding: 10px; background: #fff; }
    .clauseBox .label { margin: 0 0 6px 0; }
    .rewrite { color: var(--danger); font-weight: 900; text-decoration: underline; }
    .lawList { margin-top: 8px; color: var(--muted); font-size: 12px; }

    .composer {
      padding: 12px 14px;
      border-top: 1px solid var(--line);
      display:flex;
      gap: 10px;
      align-items:flex-end;
      background: rgba(255,255,255,0.9);
      border-radius: 0 0 18px 18px;
    }
    .composer textarea { min-height: 44px; max-height: 140px; }

    details { margin-top: 10px; }
    summary { color: var(--muted); cursor: pointer; font-weight: 900; }
    pre { white-space: pre-wrap; word-break: break-word; background: #0b1a2a; color: #e8f5ff; padding: 12px; border-radius: 12px; border: 1px solid rgba(216,236,255,0.25); }

    @media (max-width: 820px) {
      .grid { grid-template-columns: 1fr; }
      .bubble { max-width: 100%; }
      .clauseBody { grid-template-columns: 1fr; }
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
          <div class="sub">EP 탑재 전 시연용 · 대화형 계약 검토 (MVP)</div>
        </div>
      </div>
    </div>

    <div class="wrap">
      <div class="stage active" id="stageStart">
        <div class="center">
          <div class="card start">
            <div class="hero">
              <img src="/static/aouribot.png" alt="아우리봇" />
              <div class="h1">무슨 계약을 검토하고 싶으세요?</div>
              <div class="sub">계약서를 첨부하거나 내용을 입력하면 아우리봇이 먼저 검토 방향을 잡아드릴게요.</div>
            </div>

            <div class="form">
              <div class="grid">
                <div>
                  <div class="label">법인</div>
                  <input id="entity" placeholder="예: 퍼시스 / 시디즈 / 일룸 / 바로스" />
                </div>
                <div>
                  <div class="label">계약유형</div>
                  <input id="contractType" placeholder="예: 물품공급/구매/매매, NDA/비밀유지" />
                </div>
              </div>

              <div style="margin-top:10px;">
                <div class="label">계약서 첨부</div>
                <input id="file" type="file" />
              </div>

              <div style="margin-top:10px;">
                <div class="label">계약 내용 입력</div>
                <textarea id="text" placeholder="계약서 내용을 여기에 붙여넣어 주세요."></textarea>
              </div>

              <div class="row" style="margin-top:12px; justify-content:flex-end;">
                <button class="btn btnPrimary" id="btnStart" onclick="startReview()">검토 시작</button>
              </div>
              <div class="meta" id="startError"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="stage" id="stageChat">
        <div class="card">
          <div class="progress">
            <div class="left">
              <img class="avatar" src="/static/aouribot.png" alt="aouribot" />
              <span class="badge" id="progressBadge">질문 0/0</span>
              <span class="badge" id="contextBadge">-</span>
            </div>
            <div class="row">
              <button class="btn btnGhost" onclick="goStart()">처음으로</button>
            </div>
          </div>

          <div class="chat" id="chat"></div>

          <div class="composer">
            <textarea id="answerInput" placeholder="답변을 입력해 주세요"></textarea>
            <button class="btn btnPrimary" id="btnNext" onclick="submitAnswer()">다음</button>
          </div>
        </div>
      </div>

      <div class="stage" id="stageResult">
        <div class="card chatShell">
          <div class="progress" style="border-bottom:0;">
            <div class="left">
              <img class="avatar" src="/static/aouribot.png" alt="aouribot" />
              <span class="badge badgeOk" id="resultTitle">검토가 완료되었어요</span>
              <span class="badge" id="resultMeta">-</span>
            </div>
            <div class="row">
              <button class="btn btnGhost" onclick="goChat()">다시 질문 보기</button>
              <button class="btn btnGhost" onclick="goStart()">처음으로 돌아가기</button>
            </div>
          </div>

          <div style="padding: 0 14px 14px 14px;">
            <div class="h1" style="font-size:18px; margin-top:0;" id="conclusionTitle">-</div>
            <div class="sub" id="conclusionBody">-</div>
            <div class="meta" id="recommendedAction">-</div>
            <div class="meta" id="docxStatus">수정본: 미생성</div>

            <div style="margin-top:12px;">
              <div class="badge" style="margin-bottom:8px;">조항별 수정 제안</div>
              <div id="clauseList"></div>
            </div>

            <div class="row" style="margin-top:12px; justify-content:flex-end;">
              <button class="btn btnPrimary" id="btnConfirmRevision" onclick="confirmRevision()">최종 수정본 다운로드(.docx)</button>
              <button class="btn btnSecondary" id="btnConfirmDraft" onclick="confirmDraft()">초안 작성 확정</button>
            </div>
            <div class="meta" id="confirmNote"></div>

            <details>
              <summary>상세 보기</summary>
              <div style="margin-top:10px;">
                <div class="badge" style="margin-bottom:8px;">검출 issue</div>
                <pre id="detailIssues"></pre>
                <div class="badge" style="margin:12px 0 8px 0;">적용 rule</div>
                <pre id="detailRules"></pre>
                <div class="badge" style="margin:12px 0 8px 0;">관련 법령/판례/해석례</div>
                <pre id="detailLaw"></pre>
                <div class="badge" style="margin:12px 0 8px 0;">수정 제안 조항</div>
                <pre id="detailRevision"></pre>
                <div class="badge" style="margin:12px 0 8px 0;">추천 초안 템플릿</div>
                <pre id="detailDraft"></pre>
              </div>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    function escapeHtml(s) {
      return (s || '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;');
    }
    function showStage(name) {
      for (const id of ['stageStart','stageChat','stageResult']) {
        const el = document.getElementById(id);
        el.className = 'stage' + (id === name ? ' active' : '');
      }
    }
    function addMsg(role, text) {
      const chat = document.getElementById('chat');
      const row = document.createElement('div');
      row.className = 'msgRow' + (role === 'me' ? ' me' : '');
      const avatar = document.createElement('img');
      avatar.className = 'avatar';
      avatar.src = '/static/aouribot.png';
      avatar.alt = 'aouribot';
      const bubble = document.createElement('div');
      bubble.className = 'bubble ' + (role === 'me' ? 'me' : 'bot');
      bubble.innerText = text;
      if (role === 'me') {
        row.appendChild(bubble);
        row.appendChild(document.createElement('div'));
      } else {
        row.appendChild(avatar);
        row.appendChild(bubble);
      }
      chat.appendChild(row);
      chat.scrollTop = chat.scrollHeight;
    }

    let ctx = { entity:'', contract_type:'', text:'', filename:null, session_id:null, extraction_preview:null };
    let questions = [];
    let qIndex = 0;
    let answers = {};
    let reviewResult = null;
    let revisionResult = null;
    let draftSuggest = null;

    async function startReview() {
      document.getElementById('startError').innerText = '';
      document.getElementById('btnStart').disabled = true;
      try {
        const entity = (document.getElementById('entity').value || '').trim();
        const contractType = (document.getElementById('contractType').value || '').trim();
        const text = (document.getElementById('text').value || '').trim();
        const file = document.getElementById('file').files[0];
        if (!file && text.length < 5) {
          document.getElementById('startError').innerText = '계약서 파일을 첨부하거나, 계약 내용을 입력해 주세요.';
          return;
        }
        ctx = { entity, contract_type: contractType, text, filename: null, session_id: null };
        questions = [];
        qIndex = 0;
        answers = {};
        reviewResult = null;
        revisionResult = null;
        draftSuggest = null;

        if (file) {
          const fd = new FormData();
          fd.append('file', file, file.name);
          if (entity) fd.append('entity', entity);
          if (contractType) fd.append('contract_type', contractType);
          const res = await fetch('/api/upload', { method: 'POST', body: fd });
          const data = await res.json();
          if (data && data.extraction && data.extraction.success === false) {
            document.getElementById('startError').innerText = (data.extraction.error || '텍스트 추출 실패') + ' (MVP: OCR/hwp/pdf는 backlog)';
            return;
          }
          ctx.entity = (data.classification && data.classification.entity) ? data.classification.entity : (entity || 'all');
          ctx.contract_type = (data.classification && data.classification.contract_type) ? data.classification.contract_type : (contractType || 'all');
          ctx.session_id = data.question_session_id || null;
          ctx.filename = data.filename || file.name;
          questions = data.questions || [];
          ctx.extraction_preview = (data.extraction && data.extraction.preview) ? data.extraction.preview : null;
          if (!text) {
            ctx.text = '(업로드 기반: 텍스트는 서버에서 추출되어 질문/검토에 사용됩니다)';
          }
        } else {
          const payload = { entity: entity || 'all', contract_type: contractType || 'all', filename: 'demo.txt', text: text };
          const res = await fetch('/api/questions/generate', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
          const data = await res.json();
          if (data.error) {
            document.getElementById('startError').innerText = data.error;
            return;
          }
          questions = data.questions || [];
          ctx.entity = entity || 'all';
          ctx.contract_type = contractType || 'all';
          ctx.filename = payload.filename;
          ctx.text = text;
        }

        document.getElementById('contextBadge').innerText = `${ctx.entity || '-'} / ${ctx.contract_type || '-'}`;

        showStage('stageChat');
        document.getElementById('chat').innerHTML = '';
        addMsg('bot', '좋아요. 먼저 몇 가지 확인 질문을 드릴게요.');
        if (questions.length === 0) {
          addMsg('bot', '추가 질문이 많지 않은 계약으로 보이네요. 바로 검토를 진행할게요.');
          await finishAndAnalyze();
          return;
        }
        askCurrentQuestion();
      } finally {
        document.getElementById('btnStart').disabled = false;
      }
    }

    function askCurrentQuestion() {
      const q = questions[qIndex];
      const badge = document.getElementById('progressBadge');
      badge.innerText = `${Math.min(qIndex + 1, questions.length)}/${questions.length}`;
      if (!q) {
        finishAndAnalyze();
        return;
      }
      const title = q.title || q.question_id || '질문';
      const required = q.required ? ' (필수)' : '';
      const desc = q.description ? ('\\n' + q.description) : '';
      addMsg('bot', `${title}${required}${desc}`);
      document.getElementById('answerInput').value = '';
      document.getElementById('answerInput').focus();
    }

    async function submitAnswer() {
      const q = questions[qIndex];
      if (!q) {
        await finishAndAnalyze();
        return;
      }
      const raw = (document.getElementById('answerInput').value || '').trim();
      if (!raw) return;
      addMsg('me', raw);
      answers[q.question_id] = raw;
      qIndex += 1;
      if (qIndex >= questions.length) {
        await finishAndAnalyze();
        return;
      }
      askCurrentQuestion();
    }

    async function finishAndAnalyze() {
      document.getElementById('btnNext').disabled = true;
      try {
        addMsg('bot', '좋아요. 이제 검토 결과를 정리해볼게요.');

        if (ctx.session_id) {
          await fetch(`/api/question_sessions/${encodeURIComponent(ctx.session_id)}/answers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json; charset=utf-8' },
            body: JSON.stringify({ answers })
          });
          const res1 = await fetch(`/api/question_sessions/${encodeURIComponent(ctx.session_id)}/review`, { method:'POST' });
          const reviewWrap = await res1.json();
          reviewResult = (reviewWrap && reviewWrap.review) ? reviewWrap.review : reviewWrap;

          const res2 = await fetch('/api/revision/suggest', {
            method:'POST',
            headers: { 'Content-Type':'application/json; charset=utf-8' },
            body: JSON.stringify({ session_id: ctx.session_id })
          });
          revisionResult = await res2.json();
        } else {
          const analyzePayload = {
            entity: ctx.entity || 'all',
            contract_type: ctx.contract_type || 'all',
            filename: ctx.filename || 'demo.txt',
            text: (ctx.text || ''),
            answers: answers
          };
          const res1 = await fetch('/api/review/analyze', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(analyzePayload) });
          reviewResult = await res1.json();

          const res2 = await fetch('/api/revision/suggest_text', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(analyzePayload) });
          revisionResult = await res2.json();
        }

        const res3 = await fetch(`/api/draft/suggest?contract_type=${encodeURIComponent(ctx.contract_type || '')}`);
        draftSuggest = await res3.json();

        buildResult();
        showStage('stageResult');
      } finally {
        document.getElementById('btnNext').disabled = false;
      }
    }

    function firstLines(arr, n) {
      const out = [];
      for (const x of (arr || []).slice(0, n)) out.push('- ' + x);
      return out.join('\\n');
    }

    function pickLawTitles(relatedLaws) {
      const out = [];
      const results = relatedLaws && relatedLaws.results ? relatedLaws.results : null;
      if (!results) return out;
      for (const k of ['laws','precedents','interpretations']) {
        const arr = results[k];
        if (!Array.isArray(arr)) continue;
        for (const it of arr.slice(0, 3)) {
          if (it && it.title) out.push(it.title);
        }
      }
      return out.slice(0, 6);
    }

    function renderClauseList(items) {
      const root = document.getElementById('clauseList');
      root.innerHTML = '';
      if (!Array.isArray(items) || items.length === 0) {
        root.innerHTML = '<div class="meta">조항별 수정 제안이 없습니다.</div>';
        return;
      }
      for (const it of items.slice(0, 12)) {
        const card = document.createElement('div');
        card.className = 'clauseCard';
        const head = document.createElement('div');
        head.className = 'clauseHead';
        const title = document.createElement('div');
        title.className = 'clauseTitle';
        title.innerText = `${it.clause_id || ''} ${it.clause_title || ''}`.trim() || '조항';
        const tag = document.createElement('div');
        tag.className = 'clauseTag';
        const appr = !!it.approval_required;
        const high = !!it.high_risk;
        tag.innerText = appr ? '승인 필요' : (high ? '고위험' : '검토');
        head.appendChild(title);
        head.appendChild(tag);
        card.appendChild(head);

        const body = document.createElement('div');
        body.className = 'clauseBody';
        const left = document.createElement('div');
        left.className = 'clauseBox';
        left.innerHTML = `<div class="label">원문</div><div>${escapeHtml((it.original_text || '').slice(0, 320))}${(it.original_text || '').length > 320 ? '…' : ''}</div>`;
        const right = document.createElement('div');
        right.className = 'clauseBox';
        const rw = (it.suggested_rewrite || '');
        right.innerHTML = `<div class="label">추천 수정문안</div><div class="rewrite">${escapeHtml((rw || '').slice(0, 320))}${(rw || '').length > 320 ? '…' : ''}</div>`;
        body.appendChild(left);
        body.appendChild(right);
        card.appendChild(body);

        const reason = document.createElement('div');
        reason.className = 'lawList';
        const rr = (it.rewrite_reason || '');
        reason.innerText = rr ? ('수정 이유: ' + rr.slice(0, 220) + (rr.length > 220 ? '…' : '')) : '수정 이유: (없음)';
        card.appendChild(reason);

        const laws = pickLawTitles(it.related_laws);
        if (laws.length > 0) {
          const lawDiv = document.createElement('div');
          lawDiv.className = 'lawList';
          lawDiv.innerText = '관련 법령/판례: ' + laws.join(', ');
          card.appendChild(lawDiv);
        }
        root.appendChild(card);
      }
    }

    function buildResult() {
      const s = (reviewResult && reviewResult.summary) ? reviewResult.summary : {};
      const matched = Array.isArray(reviewResult && reviewResult.matched_rules) ? reviewResult.matched_rules : [];
      const issueTitles = matched.map(x => x.title || x.rule_id || 'rule').slice(0, 6);

      const revSum = (revisionResult && revisionResult.revision && revisionResult.revision.summary) ? revisionResult.revision.summary : {};
      const issueClauseCount = revSum.issue_clause_count || 0;

      const suggested = (draftSuggest && Array.isArray(draftSuggest.suggested_template_ids)) ? draftSuggest.suggested_template_ids : [];

      document.getElementById('resultMeta').innerText = `${ctx.entity || '-'} / ${ctx.contract_type || '-'} · issues=${s.matched_rule_count || 0}`;

      let action = 'revision';
      if (s.high_risk || s.approval_required) action = 'legal';
      else if (suggested.length > 0 && issueClauseCount === 0) action = 'draft';
      else if (suggested.length > 0 && (s.matched_rule_count || 0) <= 1) action = 'draft';

      const conclusionTitle = document.getElementById('conclusionTitle');
      const conclusionBody = document.getElementById('conclusionBody');

      if (action === 'legal') {
        conclusionTitle.innerText = '위험도가 높아 법무 검토가 필요합니다';
        const reasons = [];
        reasons.push('high risk 또는 결재/승인 필요 신호가 있어요.');
        if (issueTitles.length > 0) reasons.push('주요 이슈: ' + issueTitles.join(', '));
        reasons.push('먼저 수정 제안을 확인한 뒤, 법무 검토로 이어가는 흐름이 안전해요.');
        conclusionBody.innerText = reasons.slice(0, 5).join('\\n');
      } else if (action === 'draft') {
        conclusionTitle.innerText = '이 유형은 템플릿 기반 초안 작성을 추천해요';
        const reasons = [];
        reasons.push('대부분 정형 계약으로 보여 템플릿 초안이 빠른 시작점이 될 수 있어요.');
        if (suggested.length > 0) reasons.push('추천 템플릿: ' + suggested.slice(0, 3).join(', '));
        if (issueTitles.length > 0) reasons.push('검토 포인트: ' + issueTitles.join(', '));
        conclusionBody.innerText = reasons.slice(0, 5).join('\\n');
      } else {
        conclusionTitle.innerText = '이 조항은 수정 제안을 권장합니다';
        const reasons = [];
        reasons.push('계약서에서 바로 조정하면 좋은 표현/조항이 발견됐어요.');
        if (issueTitles.length > 0) reasons.push('주요 이슈: ' + issueTitles.join(', '));
        reasons.push('수정 제안은 “설명 가능한 뷰”로 정리되어 있어요(자동 redline 아님).');
        conclusionBody.innerText = reasons.slice(0, 5).join('\\n');
      }

      const high = !!s.high_risk;
      const appr = !!s.approval_required;
      document.getElementById('resultTitle').className = 'badge ' + (high ? 'badgeDanger' : (appr ? 'badgeWarn' : 'badgeOk'));

      const issuesOut = [];
      for (const r of matched.slice(0, 50)) {
        issuesOut.push({ rule_id: r.rule_id, title: r.title, risk_level: r.risk_level, approval_required: r.approval_required });
      }
      document.getElementById('detailIssues').innerText = JSON.stringify(issuesOut, null, 2);
      document.getElementById('detailRules').innerText = JSON.stringify(matched.slice(0, 80), null, 2);
      document.getElementById('detailLaw').innerText = JSON.stringify(revisionResult && revisionResult.clause_results ? revisionResult.clause_results.slice(0, 5).map(x => ({ clause_id: x.clause_id, clause_title: x.clause_title, related_laws: x.related_laws })) : null, null, 2);
      document.getElementById('detailRevision').innerText = JSON.stringify(revisionResult && revisionResult.clause_results ? revisionResult.clause_results.slice(0, 8).map(x => ({ clause_id: x.clause_id, clause_title: x.clause_title, suggested_rewrite: x.suggested_rewrite, rewrite_reason: x.rewrite_reason })) : (revisionResult && revisionResult.revision ? revisionResult.revision : revisionResult), null, 2);
      document.getElementById('detailDraft').innerText = JSON.stringify(draftSuggest, null, 2);

      document.getElementById('confirmNote').innerText = '';
      const btnRev = document.getElementById('btnConfirmRevision');
      const btnDraft = document.getElementById('btnConfirmDraft');
      const rec = document.getElementById('recommendedAction');
      const docxStatus = document.getElementById('docxStatus');
      const meta = (revisionResult && revisionResult.meta) ? revisionResult.meta : (reviewResult && reviewResult.clause_meta ? reviewResult.clause_meta : null);

      if (meta && meta.docx_allowed === false) {
        btnRev.disabled = true;
        docxStatus.innerText = '수정본: 생성 불가 (계약서 본문/조항 부족)';
      } else {
        btnRev.disabled = false;
        docxStatus.innerText = '수정본: 다운로드 가능';
      }
      btnDraft.dataset.templateId = (suggested.length > 0 ? suggested[0] : '');
      btnDraft.disabled = (suggested.length === 0);

      if (action === 'draft') {
        rec.innerText = '대표 추천 액션: 초안 작성 확정';
        btnDraft.className = 'btn btnPrimary';
        btnRev.className = 'btn btnSecondary';
      } else {
        rec.innerText = '대표 추천 액션: 최종 수정본 다운로드';
        btnRev.className = 'btn btnPrimary';
        btnDraft.className = 'btn btnSecondary';
      }

      const items = (revisionResult && Array.isArray(revisionResult.clause_results)) ? revisionResult.clause_results
                  : ((reviewResult && Array.isArray(reviewResult.clause_results)) ? reviewResult.clause_results : []);
      renderClauseList(items);
    }

    async function confirmRevision() {
      document.getElementById('confirmNote').innerText = '수정본 파일(.docx)을 생성하는 중입니다...';
      try {
        let payload = null;
        if (ctx.session_id) {
          payload = { session_id: ctx.session_id };
        } else if (revisionResult && revisionResult.clause_results) {
          payload = { input: { entity: ctx.entity || 'all', contract_type: ctx.contract_type || 'all', filename: ctx.filename || 'demo.txt' }, clause_results: revisionResult.clause_results };
        } else {
          document.getElementById('confirmNote').innerText = '수정본 생성에 필요한 데이터가 없습니다.';
          return;
        }
        const res = await fetch('/api/revision/download_docx', { method:'POST', headers:{'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
        if (!res.ok) {
          document.getElementById('confirmNote').innerText = '수정본 생성 실패';
          return;
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'aouribot_revision.docx';
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
        document.getElementById('confirmNote').innerText = '수정본 파일 다운로드를 시작했어요.';
        document.getElementById('docxStatus').innerText = '수정본: 생성 완료';
      } catch (e) {
        document.getElementById('confirmNote').innerText = '수정본 생성 실패';
      }
    }

    async function confirmDraft() {
      const templateId = document.getElementById('btnConfirmDraft').dataset.templateId || '';
      if (!templateId) {
        document.getElementById('confirmNote').innerText = '추천 템플릿이 없어 초안 확정이 어려워요. (기준 템플릿이 필요)';
        return;
      }
      document.getElementById('confirmNote').innerText = '초안 생성을 시작했어요. (데모: 기본값으로 생성)';
      const payload = {
        template_id: templateId,
        entity: ctx.entity || '미상',
        contract_type: ctx.contract_type || '기타/미분류',
        party_a: (ctx.entity ? (ctx.entity + ' 주식회사') : '당사'),
        party_b: '상대방',
        purpose: ''
      };
      const res = await fetch('/api/draft/generate', { method:'POST', headers:{'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
      const data = await res.json();
      if (data.error) {
        document.getElementById('confirmNote').innerText = '초안 생성 실패: ' + data.error;
        return;
      }
      document.getElementById('confirmNote').innerText = '초안 생성이 완료되었어요. 상세 보기에서 결과를 확인할 수 있어요.';
      document.getElementById('detailDraft').innerText = JSON.stringify({ suggested: draftSuggest, generated: data }, null, 2);
    }

    function goStart() {
      showStage('stageStart');
    }
    function goChat() {
      showStage('stageChat');
    }

    document.addEventListener('keydown', (e) => {
      if (document.getElementById('stageChat').className.includes('active')) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          submitAnswer();
        }
      }
    });
  </script>
</body>
</html>
"""

