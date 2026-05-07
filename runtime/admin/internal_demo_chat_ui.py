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
    .analyzePanel { display:none; padding: 12px 14px; border-bottom: 1px solid var(--line); background: rgba(255,255,255,0.92); }
    .stepList { margin-top: 10px; display:flex; flex-direction:column; gap: 6px; }
    .stepItem { display:flex; align-items:center; justify-content:space-between; gap: 10px; padding: 9px 10px; border: 1px solid var(--line); border-radius: 12px; background: #fff; }
    .stepName { font-weight: 900; }
    .stepState { font-size: 12px; color: var(--muted); }
    .stepItem.active { border-color: rgba(31,122,224,0.55); background: rgba(31,122,224,0.05); }
    .stepItem.done { border-color: rgba(15,118,110,0.25); background: var(--okSoft); }
    .stepItem.delayed { border-color: rgba(180,83,9,0.25); background: var(--warnSoft); }
    .dots { display:inline-flex; gap: 2px; align-items:center; }
    .dots span { display:inline-block; width: 6px; text-align:center; animation: blink 1.1s infinite; }
    .dots span:nth-child(2) { animation-delay: .15s; }
    .dots span:nth-child(3) { animation-delay: .30s; }
    @keyframes blink { 0% { opacity: .2; } 35% { opacity: 1; } 100% { opacity: .2; } }

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
    .context { color: var(--muted); font-size: 12px; margin: 0 0 6px 0; white-space: pre-wrap; }
    .redline { white-space: pre-wrap; word-break: break-word; line-height: 1.55; }
    .redline .ins { color: var(--danger); font-weight: 900; }
    .redline .del { color: var(--danger); text-decoration: line-through; font-weight: 900; }
    .guidance { border: 1px solid rgba(31,122,224,0.25); background: rgba(31,122,224,0.07); border-radius: 12px; padding: 10px; color: #0c4a6e; white-space: pre-wrap; }
    .guidance .hintTitle { font-weight: 900; margin: 0 0 6px 0; }
    .tagHigh { background: var(--dangerSoft); color: var(--danger); border-color: rgba(214,69,69,0.25); }
    .tagGuide { background: rgba(31,122,224,0.10); color: #0c4a6e; border-color: rgba(31,122,224,0.25); }
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
                <div class="label">중점 검토 내용</div>
                <textarea id="reviewFocus" placeholder="예: 대리점법상 불이익 제공, 경영간섭, 비용전가, 계약해지 남용 등 (자유입력)"></textarea>
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

          <div class="analyzePanel" id="analyzePanel">
            <div class="row" style="justify-content:space-between; align-items:center;">
              <div class="row" style="gap:8px;">
                <span class="badge" id="analyzeStepBadge">진행 0/5</span>
                <span class="badge" id="analyzeStageBadge">대기</span>
                <span class="badge" id="analyzeEtaBadge">남은 시간: -</span>
                <span class="badge" id="analyzeElapsedBadge">경과: 0s</span>
              </div>
              <div class="row">
                <button class="btn btnGhost" id="btnCancelAnalyze" onclick="cancelAnalyze()" style="display:none;">취소</button>
                <button class="btn btnSecondary" id="btnRetryAnalyze" onclick="retryAnalyze()" style="display:none;">재시도</button>
              </div>
            </div>
            <div class="stepList" id="analyzeSteps"></div>
            <div class="meta" id="analyzeHint"></div>
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
            <div class="meta" id="phaseNote">-</div>
            <div class="meta" id="recommendedAction">-</div>
            <div class="meta" id="docxStatus">수정본: 미생성</div>
            <div class="analyzePanel" id="resultAnalyzePanel" style="margin-top:10px;">
              <div class="row" style="justify-content:space-between; align-items:center;">
                <div class="row" style="gap:8px;">
                  <span class="badge" id="resultAnalyzeStepBadge">진행 0/5</span>
                  <span class="badge" id="resultAnalyzeStageBadge">대기</span>
                  <span class="badge" id="resultAnalyzeEtaBadge">남은 시간: -</span>
                  <span class="badge" id="resultAnalyzeElapsedBadge">경과: 0s</span>
                </div>
                <div class="row">
                  <button class="btn btnGhost" id="btnCancelAnalyze2" onclick="cancelAnalyze()" style="display:none;">취소</button>
                  <button class="btn btnSecondary" id="btnRetryAnalyze2" onclick="retryAnalyze()" style="display:none;">재시도</button>
                </div>
              </div>
              <div class="stepList" id="resultAnalyzeSteps"></div>
              <div class="meta" id="resultAnalyzeHint"></div>
            </div>

            <div style="margin-top:12px;">
              <div class="badge" style="margin-bottom:8px;">사용자 요청 핵심 이슈 반영 결과</div>
              <div class="meta" id="focusSummary">-</div>
            </div>

            <div style="margin-top:12px;">
              <div class="badge" style="margin-bottom:8px;">질문 답변 반영 요약</div>
              <div class="meta" id="answerSummary">-</div>
            </div>

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
    let analyzeState = {
      active: false,
      startedAt: 0,
      expectedTotalSec: 40,
      stageIndex: 0,
      fastDone: false,
      deepDone: false,
      timer: null,
      t15: null,
      t30: null,
      t90: null,
      deepAbort: null,
      lastError: null,
      retryFn: null
    };

    const ANALYZE_STAGES = [
      { key: 'prepare', name: '업로드/텍스트 정리' },
      { key: 'rules', name: '규칙 분석' },
      { key: 'law', name: '법령/판례 확인' },
      { key: 'ai', name: 'AI 정밀 검토' },
      { key: 'summarize', name: '수정 제안 정리' },
    ];

    function showAnalyzePanel(show) {
      for (const id of ['analyzePanel', 'resultAnalyzePanel']) {
        const el = document.getElementById(id);
        if (el) el.style.display = show ? 'block' : 'none';
      }
    }

    function renderAnalyzeSteps() {
      function build(rootId, stepPrefix, statePrefix) {
        const root = document.getElementById(rootId);
        if (!root) return;
        root.innerHTML = '';
        for (let i = 0; i < ANALYZE_STAGES.length; i++) {
          const st = ANALYZE_STAGES[i];
          const row = document.createElement('div');
          row.className = 'stepItem';
          row.id = `${stepPrefix}_${i}`;
          const left = document.createElement('div');
          left.className = 'stepName';
          left.innerText = st.name;
          const right = document.createElement('div');
          right.className = 'stepState';
          right.id = `${statePrefix}_${i}`;
          right.innerText = '대기';
          row.appendChild(left);
          row.appendChild(right);
          root.appendChild(row);
        }
      }
      build('analyzeSteps', 'anStep', 'anState');
      build('resultAnalyzeSteps', 'rAnStep', 'rAnState');
    }

    function _sec(n) {
      const x = Math.max(0, Math.round(Number(n || 0)));
      return `${x}s`;
    }

    function _computeEtaSec() {
      const elapsed = (Date.now() - analyzeState.startedAt) / 1000.0;
      // expectedTotalSec이 실제 경과보다 작아지면 동적으로 연장
      if (elapsed > analyzeState.expectedTotalSec * 0.9 && !analyzeState.deepDone) {
        analyzeState.expectedTotalSec = Math.ceil(elapsed * 1.3 + 10);
      }
      const remain = Math.max(0, analyzeState.expectedTotalSec - elapsed);
      return Math.round(remain);
    }

    function updateAnalyzeHeader() {
      const elapsed = (Date.now() - analyzeState.startedAt) / 1000.0;
      const stepText = `진행 ${Math.min(analyzeState.stageIndex + 1, 5)}/5`;
      const etaSec = _computeEtaSec();
      // 남은 시간이 0이 되어도 완료 전이면 "처리 중..." 표시
      const etaText = (!analyzeState.deepDone && etaSec <= 0)
        ? '남은 시간: 처리 중...'
        : `남은 시간: 약 ${_sec(etaSec)}`;
      const elapsedText = `경과: ${_sec(elapsed)}`;
      for (const id of ['analyzeElapsedBadge', 'resultAnalyzeElapsedBadge']) {
        const el = document.getElementById(id);
        if (el) el.innerText = elapsedText;
      }
      for (const id of ['analyzeEtaBadge', 'resultAnalyzeEtaBadge']) {
        const el = document.getElementById(id);
        if (el) el.innerText = etaText;
      }
      for (const id of ['analyzeStepBadge', 'resultAnalyzeStepBadge']) {
        const el = document.getElementById(id);
        if (el) el.innerText = stepText;
      }
    }

    function setAnalyzeStage(index, state, label) {
      analyzeState.stageIndex = Math.max(0, Math.min(index, ANALYZE_STAGES.length - 1));
      for (let i = 0; i < ANALYZE_STAGES.length; i++) {
        for (const [stepPrefix, statePrefix] of [['anStep', 'anState'], ['rAnStep', 'rAnState']]) {
          const row = document.getElementById(`${stepPrefix}_${i}`);
          const st = document.getElementById(`${statePrefix}_${i}`);
          if (!row || !st) continue;
          row.className = 'stepItem';
          st.innerText = '대기';
          if (i < analyzeState.stageIndex) {
            row.className = 'stepItem done';
            st.innerText = '완료';
          } else if (i === analyzeState.stageIndex) {
            row.className = 'stepItem active';
            st.innerText = label || '진행 중';
          }
        }
      }
      const stageHtml = (state || '진행 중') + ' <span class="dots"><span>•</span><span>•</span><span>•</span></span>';
      for (const id of ['analyzeStageBadge', 'resultAnalyzeStageBadge']) {
        const el = document.getElementById(id);
        if (el) el.innerHTML = stageHtml;
      }
      updateAnalyzeHeader();
    }

    function startAnalyzeProgress(expectedTotalSec) {
      analyzeState.active = true;
      analyzeState.fastDone = false;
      analyzeState.deepDone = false;
      analyzeState.lastError = null;
      analyzeState.retryFn = null;
      analyzeState.startedAt = Date.now();
      analyzeState.expectedTotalSec = Math.max(20, Math.min(180, Number(expectedTotalSec || 60)));
      renderAnalyzeSteps();
      showAnalyzePanel(true);
      for (const id of ['btnCancelAnalyze', 'btnCancelAnalyze2']) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'inline-block';
      }
      for (const id of ['btnRetryAnalyze', 'btnRetryAnalyze2']) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
      }
      for (const id of ['analyzeHint', 'resultAnalyzeHint']) {
        const el = document.getElementById(id);
        if (el) el.innerText = '먼저 핵심 결과를 보여드리고, 조항별 수정안은 이어서 정리할게요.';
      }
      setAnalyzeStage(0, '계약서 읽는 중', '진행 중');

      if (analyzeState.timer) clearInterval(analyzeState.timer);
      analyzeState.timer = setInterval(() => {
        if (!analyzeState.active) return;
        updateAnalyzeHeader();
        const elapsed = (Date.now() - analyzeState.startedAt) / 1000.0;
        if (!analyzeState.deepDone && elapsed >= 90) {
          for (const prefix of ['anStep', 'rAnStep']) {
            const row = document.getElementById(`${prefix}_${analyzeState.stageIndex}`);
            if (row) row.className = 'stepItem delayed';
          }
        }
      }, 250);

      if (analyzeState.t15) clearTimeout(analyzeState.t15);
      if (analyzeState.t30) clearTimeout(analyzeState.t30);
      if (analyzeState.t90) clearTimeout(analyzeState.t90);
      analyzeState.t15 = setTimeout(() => {
        if (analyzeState.active && !analyzeState.deepDone) {
          addMsg('bot', '법령/판례와 AI 검토를 함께 진행 중이라 조금 더 걸리고 있어요.');
        }
      }, 15000);
      analyzeState.t30 = setTimeout(() => {
        if (analyzeState.active && !analyzeState.deepDone) {
          addMsg('bot', '조항별 검토를 계속 진행 중이에요. 창을 닫지 말고 조금만 기다려 주세요.');
        }
      }, 30000);
      analyzeState.t90 = setTimeout(() => {
        if (analyzeState.active && !analyzeState.deepDone) {
          addMsg('bot', '예상보다 지연되고 있어요. 네트워크 상태를 확인한 뒤, 필요하면 재시도해 주세요.');
          for (const prefix of ['anStep', 'rAnStep']) {
            const row = document.getElementById(`${prefix}_${analyzeState.stageIndex}`);
            if (row) row.className = 'stepItem delayed';
          }
        }
      }, 90000);
    }

    function finishAnalyzeProgress(ok) {
      analyzeState.active = false;
      if (analyzeState.timer) clearInterval(analyzeState.timer);
      analyzeState.timer = null;
      for (const id of ['btnCancelAnalyze', 'btnCancelAnalyze2']) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
      }
      for (const id of ['analyzeStageBadge', 'resultAnalyzeStageBadge']) {
        const el = document.getElementById(id);
        if (el) el.innerText = ok ? '완료' : '오류';
      }
      updateAnalyzeHeader();
    }

    function cancelAnalyze() {
      try {
        if (analyzeState.deepAbort) analyzeState.deepAbort.abort();
      } catch (_) {}
      analyzeState.active = false;
      finishAnalyzeProgress(false);
      addMsg('bot', '검토를 중단했어요. 필요하면 다시 시도해 주세요.');
      for (const id of ['btnRetryAnalyze', 'btnRetryAnalyze2']) {
        const el = document.getElementById(id);
        if (el) el.style.display = 'inline-block';
      }
    }

    function retryAnalyze() {
      if (typeof analyzeState.retryFn === 'function') {
        analyzeState.retryFn();
        return;
      }
      addMsg('bot', '재시도를 위해 “처음으로”에서 다시 검토를 시작해 주세요.');
    }

    async function startReview() {
      document.getElementById('startError').innerText = '';
      document.getElementById('btnStart').disabled = true;
      try {
        const entity = (document.getElementById('entity').value || '').trim();
        const contractType = (document.getElementById('contractType').value || '').trim();
        const text = (document.getElementById('text').value || '').trim();
        const reviewFocus = (document.getElementById('reviewFocus').value || '').trim();
        const file = document.getElementById('file').files[0];
        if (!file && text.length < 5) {
          document.getElementById('startError').innerText = '계약서 파일을 첨부하거나, 계약 내용을 입력해 주세요.';
          return;
        }
        ctx = { entity, contract_type: contractType, text, filename: null, session_id: null, review_focus: reviewFocus || null };
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
          if (reviewFocus) fd.append('review_focus', reviewFocus);
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
          const payload = { entity: entity || 'all', contract_type: contractType || 'all', filename: 'demo.txt', text: text, review_focus: reviewFocus || null };
          const res = await fetch('/api/questions/generate', { method:'POST', headers: {'Content-Type':'application/json; charset=utf-8'}, body: JSON.stringify(payload) });
          const data = await res.json();
          if (data.error) {
            document.getElementById('startError').innerText = data.error;
            return;
          }
          questions = data.questions || [];
          ctx.session_id = data.question_session_id || null;
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
        if (analyzeState && analyzeState.active) return;
        analyzeState.active = true;
        addMsg('bot', '좋아요. 이제 검토 결과를 정리해볼게요.');
        addMsg('bot', '계약 길이와 조항 수에 따라 20~60초 정도 걸릴 수 있어요.');

        startAnalyzeProgress(40);
        setAnalyzeStage(0, '질문 답변 반영 중', '진행 중');

        const analyzePayload = {
          entity: ctx.entity || 'all',
          contract_type: ctx.contract_type || 'all',
          filename: ctx.filename || 'demo.txt',
          text: (ctx.text || ''),
          answers: answers,
          review_focus: (ctx.review_focus || null)
        };

        const draftPromise = fetch(`/api/draft/suggest?contract_type=${encodeURIComponent(ctx.contract_type || '')}`)
          .then(r => r.json())
          .then(d => {
            draftSuggest = d;
            buildResult();
            return d;
          })
          .catch(() => null);

        if (ctx.session_id) {
          await fetch(`/api/question_sessions/${encodeURIComponent(ctx.session_id)}/answers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json; charset=utf-8' },
            body: JSON.stringify({ answers })
          });
        }

        setAnalyzeStage(1, '규칙 검토 중', '진행 중');

        let fastResult = null;
        try {
          if (ctx.session_id) {
            const res = await fetch(`/api/question_sessions/${encodeURIComponent(ctx.session_id)}/review_fast`, { method: 'POST' });
            const wrap = await res.json();
            fastResult = (wrap && wrap.review) ? wrap.review : wrap;
          } else {
            const res = await fetch('/api/review/analyze_fast', {
              method: 'POST',
              headers: {'Content-Type':'application/json; charset=utf-8'},
              body: JSON.stringify(analyzePayload)
            });
            fastResult = await res.json();
          }
        } catch (e) {
          fastResult = { error: String(e || 'fast review failed') };
        }

        if (fastResult && fastResult.error) {
          analyzeState.lastError = fastResult.error;
          finishAnalyzeProgress(false);
          document.getElementById('phaseNote').innerText = '1차 결과 생성 중 오류가 발생했어요. 잠시 후 재시도해 주세요.';
          for (const id of ['btnRetryAnalyze','btnRetryAnalyze2']) {
            const el = document.getElementById(id);
            if (el) el.style.display = 'inline-block';
          }
          showStage('stageResult');
          buildResult();
          return;
        }

        reviewResult = fastResult;
        analyzeState.fastDone = true;

        const meta = (reviewResult && reviewResult.clause_meta) ? reviewResult.clause_meta : {};
        const clauseCount = Number(meta.clause_count || 0) || (Array.isArray(reviewResult && reviewResult.clause_results) ? reviewResult.clause_results.length : 0);
        const textLen = Number(meta.text_length || 0) || (String(analyzePayload.text || '').length);
        const expected = Math.max(20, Math.min(180, 18 + Math.round(clauseCount * 2.1) + (textLen > 9000 ? 15 : 0)));
        analyzeState.expectedTotalSec = expected;

        showStage('stageResult');
        document.getElementById('resultTitle').innerText = '핵심 결과(1차)';
        document.getElementById('phaseNote').innerText = '먼저 핵심 결과를 보여드리고, 조항별 수정안은 이어서 정리할게요.';
        document.getElementById('docxStatus').innerText = '수정본: 정밀 검토 후 준비됩니다';
        document.getElementById('btnConfirmRevision').disabled = true;

        buildResult();
        renderSkeletonClauseList();

        const deepRun = async () => {
          analyzeState.deepAbort = new AbortController();
          const signal = analyzeState.deepAbort.signal;
          analyzeState.retryFn = deepRun;
          analyzeState.lastError = null;
          analyzeState.active = true;

          setAnalyzeStage(2, '법령/판례 확인 중', '진행 중');
          const tAi = setTimeout(() => {
            if (analyzeState.active && !analyzeState.deepDone) setAnalyzeStage(3, 'AI 정밀 검토 중', '진행 중');
          }, 7000);
          const tSum = setTimeout(() => {
            if (analyzeState.active && !analyzeState.deepDone) setAnalyzeStage(4, '수정 제안 정리 중', '진행 중');
          }, 14000);

          try {
            let deepResult = null;
            if (ctx.session_id) {
              const res = await fetch(`/api/question_sessions/${encodeURIComponent(ctx.session_id)}/review`, { method: 'POST', signal });
              const wrap = await res.json();
              deepResult = (wrap && wrap.review) ? wrap.review : wrap;
            } else {
              const res = await fetch('/api/review/analyze_deep', {
                method: 'POST',
                headers: {'Content-Type':'application/json; charset=utf-8'},
                body: JSON.stringify(analyzePayload),
                signal
              });
              deepResult = await res.json();
            }
            if (deepResult && deepResult.error) throw new Error(deepResult.error);

            reviewResult = deepResult;
            analyzeState.deepDone = true;
            // 실제 서버 소요 시간으로 expectedTotalSec 보정 (타이머 정확도 향상)
            if (deepResult && typeof deepResult.review_elapsed_sec === 'number') {
              const actualSec = deepResult.review_elapsed_sec;
              const elapsed = (Date.now() - analyzeState.startedAt) / 1000.0;
              analyzeState.expectedTotalSec = Math.ceil(Math.max(elapsed, actualSec) + 1);
            }
            revisionResult = {
              revision: { summary: { issue_clause_count: Number((deepResult.clause_meta || {}).issue_clause_count || 0) } },
              clause_results: Array.isArray(deepResult.clause_results) ? deepResult.clause_results : [],
              meta: deepResult.clause_meta || null
            };
            setAnalyzeStage(4, '정리 완료', '완료');
            finishAnalyzeProgress(true);
            for (const id of ['btnRetryAnalyze','btnRetryAnalyze2']) {
              const el = document.getElementById(id);
              if (el) el.style.display = 'none';
            }
            document.getElementById('phaseNote').innerText = '정밀 결과가 준비되었어요. 조항별 수정안을 확인해 주세요.';
            buildResult();
          } catch (e) {
            analyzeState.lastError = String(e || 'deep review failed');
            finishAnalyzeProgress(false);
            document.getElementById('phaseNote').innerText = '정밀 결과 로딩 중 오류가 발생했어요. 네트워크 확인 후 재시도해 주세요.';
            for (const id of ['btnRetryAnalyze','btnRetryAnalyze2']) {
              const el = document.getElementById(id);
              if (el) el.style.display = 'inline-block';
            }
          } finally {
            clearTimeout(tAi);
            clearTimeout(tSum);
          }
        };

        deepRun();
        await draftPromise;
      } finally {
        document.getElementById('btnNext').disabled = false;
      }
    }

    function renderSkeletonClauseList() {
      const root = document.getElementById('clauseList');
      if (!root) return;
      root.innerHTML = '';
      for (let i = 0; i < 4; i++) {
        const card = document.createElement('div');
        card.className = 'clauseCard';
        card.innerHTML = `<div class="meta">조항별 수정안을 정리 중입니다<span class="dots"><span>•</span><span>•</span><span>•</span></span></div>`;
        root.appendChild(card);
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

    function tokenizeForDiff(s) {
      const text = (s || '');
      const re = /(\\s+|[0-9A-Za-z가-힣]+|[^0-9A-Za-z가-힣\\s])/g;
      const out = [];
      let m;
      while ((m = re.exec(text)) !== null) {
        out.push(m[0]);
        if (out.length > 900) break;
      }
      return out;
    }

    function diffOps(aTokens, bTokens) {
      const a = aTokens || [];
      const b = bTokens || [];
      const n = a.length;
      const m = b.length;
      const dp = Array.from({ length: n + 1 }, () => Array(m + 1).fill(0));
      for (let i = n - 1; i >= 0; i--) {
        for (let j = m - 1; j >= 0; j--) {
          dp[i][j] = (a[i] === b[j]) ? (dp[i + 1][j + 1] + 1) : Math.max(dp[i + 1][j], dp[i][j + 1]);
        }
      }
      const ops = [];
      let i = 0, j = 0;
      while (i < n && j < m) {
        if (a[i] === b[j]) { ops.push({ op: 'eq', t: a[i] }); i++; j++; continue; }
        if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ op: 'del', t: a[i] }); i++; continue; }
        ops.push({ op: 'ins', t: b[j] }); j++;
      }
      while (i < n) { ops.push({ op: 'del', t: a[i++] }); }
      while (j < m) { ops.push({ op: 'ins', t: b[j++] }); }
      const merged = [];
      for (const x of ops) {
        const last = merged.length ? merged[merged.length - 1] : null;
        if (last && last.op === x.op) last.t += x.t;
        else merged.push({ op: x.op, t: x.t });
      }
      return merged;
    }

    function renderRedlineHtml(originalText, revisedText) {
      const a = tokenizeForDiff(originalText);
      const b = tokenizeForDiff(revisedText);
      const ops = diffOps(a, b);
      const parts = [];
      for (const x of ops) {
        if (!x.t) continue;
        if (x.op === 'eq') parts.push(escapeHtml(x.t));
        else if (x.op === 'ins') parts.push('<span class="ins">' + escapeHtml(x.t) + '</span>');
        else if (x.op === 'del') parts.push('<span class="del">' + escapeHtml(x.t) + '</span>');
      }
      return parts.join('');
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

    function clauseHierarchyLines(it) {
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
      return lines;
    }

    function _clauseDisplayScore(it) {
      if (!it) return 0;
      const tier = String(it.risk_tier || '').toUpperCase();
      const isRedline = !!it.has_rewrite_change && (tier === 'HIGH' || !!it.approval_required || !!it.high_risk);
      let s = 0;
      if (isRedline)                              s += 3000;
      else if (tier === 'HIGH')                   s += 2000;
      if (!!it.approval_required)                 s += 500;
      if (!!it.high_risk)                         s += 400;
      if (!!it.must_fix)                          s += 300;
      if (tier === 'MEDIUM')                      s += 200;
      if (!!it.user_focus_hit)                    s += 100;
      if (!!it.factual_hit)                       s += 50;
      return s;
    }

    function renderClauseList(items) {
      const root = document.getElementById('clauseList');
      root.innerHTML = '';
      if (!Array.isArray(items) || items.length === 0) {
        root.innerHTML = '<div class="meta">조항별 수정 제안이 없습니다.</div>';
        return;
      }
      const visible = items
        .filter(it => {
          if (!it) return false;
          if (it.dedup_suppressed || it.keep_as_is) return false;
          const tier = String(it.risk_tier || '').toUpperCase();
          const isHighRisk = tier === 'HIGH' || !!it.approval_required || !!it.high_risk;
          const isMedium   = tier === 'MEDIUM';
          // 실질 수정안이 없는 LOW 항목은 표시하지 않는다
          const hasSuggestedRewrite = !!(it.suggested_rewrite && String(it.suggested_rewrite).trim());
          if (!isHighRisk && !isMedium && !hasSuggestedRewrite) return false;
          return isHighRisk || isMedium || (!!it.user_focus_hit && hasSuggestedRewrite);
        })
        .sort((a, b) => _clauseDisplayScore(b) - _clauseDisplayScore(a));
      const list = (visible.length > 0 ? visible : items);
      for (const it of list.slice(0, 14)) {
        const card = document.createElement('div');
        card.className = 'clauseCard';
        const head = document.createElement('div');
        head.className = 'clauseHead';
        const title = document.createElement('div');
        title.className = 'clauseTitle';
        const lines = clauseHierarchyLines(it);
        title.innerHTML = lines.map((x, idx) => `<div style="margin-top:${idx===0?0:4}px; padding-left:${idx===0?0:12}px; color:${idx===0?'#102a43':'#5b7086'};">${escapeHtml(x)}</div>`).join('');
        const tag = document.createElement('div');
        tag.className = 'clauseTag';
        const appr = !!it.approval_required;
        const high = !!it.high_risk;
        const focus = !!it.user_focus_hit;
        const fact = !!it.factual_hit;
        const cr0 = (it && it.change_record) ? it.change_record : null;
        const ctype = cr0 && cr0.change_type ? String(cr0.change_type) : '';
        const changeBadge = (ctype === 'keep_as_is') ? '유지' : (it.has_rewrite_change ? '수정' : (ctype === 'suppressed' ? '중복생략' : '검토'));
        const priBadge = focus ? '중점' : (fact ? '답변' : '');
        tag.innerText = (priBadge ? (priBadge + ' · ') : '') + (appr ? '승인 필요' : (high ? '고위험' : '권장/참고')) + ' · ' + changeBadge;
        tag.className = 'clauseTag ' + (high || appr ? 'tagHigh' : 'tagGuide');
        head.appendChild(title);
        head.appendChild(tag);
        card.appendChild(head);

        const body = document.createElement('div');
        body.className = 'clauseBody';
        const left = document.createElement('div');
        left.className = 'clauseBox';
        const ctxText = (it.context_text || '');
        const ctxBlock = ctxText ? `<div class="context">${escapeHtml(ctxText.slice(0, 180))}${ctxText.length > 180 ? '…' : ''}</div>` : '';
        left.innerHTML = `<div class="label">원문</div>${ctxBlock}<div>${escapeHtml((it.original_text || '').slice(0, 320))}${(it.original_text || '').length > 320 ? '…' : ''}</div>`;
        const right = document.createElement('div');
        right.className = 'clauseBox';
        const rw = (it.suggested_rewrite || '');
        if ((high || appr) && rw) {
          const html = renderRedlineHtml(it.original_text || '', rw || '');
          right.innerHTML = `<div class="label">필수 수정(redline)</div><div class="redline">${html}</div>`;
        } else {
          const dirs = Array.isArray(it.suggested_direction) ? it.suggested_direction : [];
          const rr0 = (it.rewrite_reason || '');
          const lines = [];
          const mt = Array.isArray(it.user_focus_match_titles) ? it.user_focus_match_titles : [];
          const ft = Array.isArray(it.factual_match_titles) ? it.factual_match_titles : [];
          if (mt.length) lines.push('중점 이슈 연결: ' + mt.slice(0, 3).join(' / '));
          if (ft.length) lines.push('답변 반영 쟁점: ' + ft.slice(0, 3).join(' / '));
          if (dirs.length) lines.push('방향: ' + dirs.slice(0, 3).join(' / '));
          if (rr0) lines.push('사유: ' + rr0.slice(0, 240) + (rr0.length > 240 ? '…' : ''));
          if (rw) lines.push('참고 문안: ' + rw.slice(0, 240) + (rw.length > 240 ? '…' : ''));
          right.innerHTML = `<div class="label">권장/참고(guidance)</div><div class="guidance"><div class="hintTitle">보완 권고</div>${escapeHtml(lines.join('\\n'))}</div>`;
        }
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
      const issueTitles = matched
        .filter(x => x && !x.summary_suppress)
        .map(x => x.title || x.rule_id || 'rule')
        .slice(0, 6);

      const revSum = (revisionResult && revisionResult.revision && revisionResult.revision.summary) ? revisionResult.revision.summary : {};
      const meta0 = (reviewResult && reviewResult.clause_meta) ? reviewResult.clause_meta : {};
      const itemsAll = Array.isArray(revisionResult && revisionResult.clause_results) ? revisionResult.clause_results
                    : (Array.isArray(reviewResult && reviewResult.clause_results) ? reviewResult.clause_results : []);
      const issueClauseCount = Number(revSum.issue_clause_count || meta0.issue_clause_count || 0) || 0;
      const mustCount = itemsAll.filter(x => x && (x.approval_required || x.high_risk)).length;
      const medCount = itemsAll.filter(x => x && !x.approval_required && !x.high_risk && (String(x.risk_tier || '').toUpperCase() === 'MEDIUM')).length;
      const lowCount = itemsAll.filter(x => x && !x.approval_required && !x.high_risk && (String(x.risk_tier || '').toUpperCase() === 'LOW')).length;

      const suggested = (draftSuggest && Array.isArray(draftSuggest.suggested_template_ids)) ? draftSuggest.suggested_template_ids : [];

      document.getElementById('resultMeta').innerText = `${ctx.entity || '-'} / ${ctx.contract_type || '-'} · issues=${s.matched_rule_count || 0} · 필수수정=${mustCount} 권장=${medCount} 참고=${lowCount}`;

      try {
        const frc = meta0 && meta0.final_review_context ? meta0.final_review_context : null;
        const focus = (frc && Array.isArray(frc.user_focus_issues)) ? frc.user_focus_issues : [];
        const hits = itemsAll.filter(x => x && x.user_focus_hit);
        const lines = [];
        if (frc && frc.expert_mode) {
          const party = (frc.party_role && typeof frc.party_role === 'object') ? frc.party_role : {};
          const ourRole = String(party.our_role || '');
          const ourLabel = String(party.our_label || '');
          const roleKo = (ourRole === 'supplier') ? '공급업자' : (ourRole === 'contractor') ? '수급인' : (ourRole === 'buyer') ? '구매자/발주자' : (ourRole === 'ordering_party') ? '도급인/발주자' : '미확정';
          lines.push(`포지션: ${roleKo}${ourLabel ? ` (${ourLabel})` : ''}`);
          const strat = (Array.isArray(frc.expert_strategy)) ? frc.expert_strategy : [];
          for (const s of strat.slice(0, 2)) {
            if (s && String(s).trim() !== '') lines.push('- ' + String(s).trim());
          }
          const topicWeightSupplier = { dealer_unfair: 40, payment_settlement: 35, termination: 32, cost_burden: 28, personal_data: 18, dispute: 5 };
          const topicWeightContractor = { payment_settlement: 40, other: 34, safety: 28, termination: 22, cost_burden: 18, dispute: 6 };
          const tw = (ourRole === 'supplier') ? topicWeightSupplier : (ourRole === 'contractor') ? topicWeightContractor : {};
          const scored = itemsAll
            .filter(x => x && !x.dedup_suppressed && !x.keep_as_is && (String(x.risk_tier || '').toUpperCase() === 'HIGH' || String(x.risk_tier || '').toUpperCase() === 'MEDIUM' || x.high_risk || x.approval_required || x.user_focus_hit))
            .map(x => {
              const ct = String(x.clause_topic || '');
              let sc = 0;
              const rt = String(x.risk_tier || '').toUpperCase();
              if (rt === 'HIGH') sc += 110;
              else if (rt === 'MEDIUM') sc += 80;
              if (x.approval_required) sc += 50;
              if (x.high_risk) sc += 40;
              if (x.must_fix) sc += 30;
              if (x.user_focus_hit) sc += 25;
              sc += Number(tw[ct] || 0);
              if (String(ctx.contract_type || '').includes('대리점') && String((meta0.jurisdiction || {}).kind || '') === 'domestic_korea' && ct === 'dispute' && !x.user_focus_hit) sc -= 80;
              return { x, sc };
            })
            .sort((a, b) => b.sc - a.sc)
            .slice(0, 3)
            .map(z => z.x);
          if (scored.length > 0) {
            const pick = scored.map(x => String(x.display_path || x.clause_id || '')).filter(Boolean).join(' · ');
            lines.push('치명 리스크 Pick: ' + pick);
          }
        }
        if (focus.length === 0) lines.push('중점 검토 내용이 입력되지 않았습니다.');
        else lines.push('요청 이슈: ' + focus.map(x => x.title || x.code).slice(0, 6).join(' / '));
        if (hits.length === 0) {
          const dbg = (meta0 && Array.isArray(meta0.user_focus_mapping_debug)) ? meta0.user_focus_mapping_debug : [];
          const cands = [];
          for (const d of dbg) {
            if (d && Array.isArray(d.candidate_clause_ids) && d.candidate_clause_ids.length > 0) {
              const top = d.candidate_clause_ids.slice(0, 3).join(', ');
              cands.push(`${d.objective_title || d.objective_code}: 후보 ${top}`);
            }
          }
          if (cands.length > 0) {
            lines.push('관련 조항: (자동 탐지 약함) ' + cands.slice(0, 3).join(' · '));
          } else {
            lines.push('관련 조항: (탐지 없음) - 조항 토픽/키워드 신호가 약할 수 있어요. 조항 제목/조문 번호를 확인해 주세요.');
          }
        }
        else {
          const top = hits.slice(0, 3).map(x => (x.display_path || x.clause_id || '') + (x.clause_title ? ` [${cleanClauseTitle(x)}]` : '')).join(' · ');
          lines.push(`관련 조항: ${hits.length}개 (상위: ${top})`);
        }
        document.getElementById('focusSummary').innerText = lines.join('\\n');
      } catch (e) {
        document.getElementById('focusSummary').innerText = '-';
      }

      try {
        const a = (answers && typeof answers === 'object') ? answers : {};
        const keys = Object.keys(a || {}).filter(k => a[k] !== undefined && a[k] !== null && String(a[k]).trim() !== '');
        if (keys.length === 0) {
          document.getElementById('answerSummary').innerText = '답변: (없음)';
        } else {
          const lines = [];
          for (const k of keys.slice(0, 6)) {
            lines.push(`${k}: ${String(a[k]).slice(0, 80)}${String(a[k]).length > 80 ? '…' : ''}`);
          }
          document.getElementById('answerSummary').innerText = lines.join('\\n');
        }
      } catch (e) {
        document.getElementById('answerSummary').innerText = '-';
      }

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
      document.getElementById('detailLaw').innerText = JSON.stringify(itemsAll ? itemsAll.slice(0, 5).map(x => ({ clause_id: x.clause_id, clause_title: x.clause_title, related_laws: x.related_laws })) : null, null, 2);
      document.getElementById('detailRevision').innerText = JSON.stringify(itemsAll ? itemsAll.slice(0, 8).map(x => ({ clause_id: x.clause_id, clause_title: x.clause_title, suggested_rewrite: x.suggested_rewrite, rewrite_reason: x.rewrite_reason })) : null, null, 2);
      document.getElementById('detailDraft').innerText = JSON.stringify(draftSuggest, null, 2);

      document.getElementById('confirmNote').innerText = '';
      const btnRev = document.getElementById('btnConfirmRevision');
      const btnDraft = document.getElementById('btnConfirmDraft');
      const rec = document.getElementById('recommendedAction');
      const docxStatus = document.getElementById('docxStatus');
      const meta = (revisionResult && revisionResult.meta) ? revisionResult.meta : (reviewResult && reviewResult.clause_meta ? reviewResult.clause_meta : null);

      if (!analyzeState.deepDone) {
        btnRev.disabled = true;
        if (meta && meta.docx_allowed === false) docxStatus.innerText = '수정본: 생성 불가 (계약서 본문/조항 부족)';
        else docxStatus.innerText = '수정본: 정밀 검토 진행 중';
      } else {
        if (meta && meta.docx_allowed === false) {
          btnRev.disabled = true;
          docxStatus.innerText = '수정본: 생성 불가 (계약서 본문/조항 부족)';
        } else {
          btnRev.disabled = false;
          docxStatus.innerText = '수정본: 다운로드 가능';
        }
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

      renderClauseList(itemsAll);
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

