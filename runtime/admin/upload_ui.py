UPLOAD_HTML = r"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>AouriBot — 법무 검토 시스템</title>
  <style>
    :root {
      --brand: #1a3a6b;
      --accent: #c0392b;
      --ok: #1a7a3e;
      --warn: #8a3b00;
      --bg: #f7f8fa;
      --card: #fff;
      --border: #d0d4db;
      --text: #1c1c1c;
      --muted: #5a6070;
    }
    * { box-sizing: border-box; }
    body { font-family: 'Malgun Gothic', '맑은 고딕', Arial, sans-serif; margin: 0; background: var(--bg); color: var(--text); font-size: 14px; }
    header { background: var(--brand); color: #fff; padding: 14px 24px; display: flex; align-items: center; gap: 12px; }
    header h1 { margin: 0; font-size: 18px; font-weight: 700; }
    header .sub { font-size: 12px; opacity: 0.75; }
    .container { max-width: 960px; margin: 0 auto; padding: 20px 16px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; margin-bottom: 18px; }
    .card h2 { margin: 0 0 14px; font-size: 15px; color: var(--brand); border-bottom: 2px solid var(--brand); padding-bottom: 6px; }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: flex-start; margin-bottom: 10px; }
    input[type=text], input[type=file], select, textarea {
      padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px;
      font-size: 13px; font-family: inherit; background: #fff;
    }
    textarea { width: 100%; min-height: 80px; resize: vertical; }
    input[type=text] { min-width: 200px; }
    button {
      padding: 8px 16px; border: none; border-radius: 6px; font-size: 13px;
      font-family: inherit; cursor: pointer; font-weight: 600; transition: opacity .15s;
    }
    button:hover { opacity: .85; }
    button:disabled { opacity: .4; cursor: not-allowed; }
    .btn-primary   { background: var(--brand); color: #fff; }
    .btn-danger    { background: var(--accent); color: #fff; }
    .btn-success   { background: var(--ok); color: #fff; }
    .btn-secondary { background: #e4e8ef; color: var(--text); }
    .btn-dl-group  { display: flex; gap: 8px; flex-wrap: wrap; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 700; }
    .badge-high   { background: #fde8e8; color: #900; }
    .badge-medium { background: #fff3cd; color: #7a4a00; }
    .badge-low    { background: #e8f5e9; color: #1a5e28; }
    .badge-crit   { background: #900; color: #fff; }
    .status { padding: 8px 12px; border-radius: 6px; font-size: 13px; margin-bottom: 10px; }
    .status-info  { background: #e8f0fe; color: #1a3a6b; }
    .status-ok    { background: #e8f5e9; color: #1a5e28; }
    .status-error { background: #fde8e8; color: #900; }
    .status-warn  { background: #fff3cd; color: #7a4a00; }
    table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
    th { background: #f0f3f8; text-align: left; padding: 8px 10px; font-weight: 600; border-bottom: 2px solid var(--border); }
    td { padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
    tr:hover td { background: #f7f8fa; }
    .orig { color: var(--accent); text-decoration: line-through; font-size: 12px; }
    .sugg { color: var(--ok); font-size: 12px; margin-top: 4px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #111; color: #eee; padding: 12px; border-radius: 8px; font-size: 12px; max-height: 400px; overflow: auto; }
    .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #ccc; border-top-color: var(--brand); border-radius: 50%; animation: spin .7s linear infinite; vertical-align: middle; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .hidden { display: none !important; }
    .section-num { color: var(--muted); font-size: 12px; margin-right: 4px; }
    .risk-bar { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
    .risk-chip { padding: 6px 14px; border-radius: 20px; font-size: 13px; font-weight: 700; }
  </style>
</head>
<body>
<header>
  <div>
    <h1>AouriBot 법무 검토 시스템</h1>
    <div class="sub">계약서 업로드 → AI 리스크 분석 → Redline DOCX 자동 생성</div>
  </div>
</header>

<div class="container">

<!-- STEP 1: 업로드 -->
<div class="card">
  <h2><span class="section-num">STEP 1</span> 계약서 업로드</h2>
  <div class="row">
    <input type="file" id="file" accept=".docx,.pdf,.txt,.hwp,.xlsx" onchange="onFileSelected()"/>
    <button class="btn-primary" onclick="doUpload()">업로드 &amp; 분석 시작</button>
  </div>
  <div class="row">
    <input type="text" id="entity" placeholder="의뢰인 (예: 퍼시스, 비우면 자동추정)"/>
    <input type="text" id="contractType" placeholder="계약 유형 (예: NDA, 비우면 자동추정)"/>
  </div>
  <div class="row">
    <textarea id="reviewFocus" placeholder="중점 검토 내용 (예: 대리점법 불이익제공 / 비용전가 / 해지 남용)"></textarea>
  </div>
  <div id="uploadStatus"></div>
</div>

<!-- STEP 2: 추가 질문 -->
<div class="card hidden" id="stepQ">
  <h2><span class="section-num">STEP 2</span> 추가 질문 (선택)</h2>
  <div id="qMeta" style="color:var(--muted);font-size:12px;margin-bottom:10px;"></div>
  <div id="qForm"></div>
  <div class="row" style="margin-top:8px;">
    <button class="btn-primary" onclick="doReview()">답변 저장 &amp; 심층 검토 실행</button>
    <button class="btn-secondary" onclick="doReview()">질문 건너뛰고 검토</button>
  </div>
</div>

<!-- STEP 3: 검토 결과 -->
<div class="card hidden" id="stepResult">
  <h2><span class="section-num">STEP 3</span> 법무 검토 결과</h2>
  <div id="riskBar" class="risk-bar"></div>
  <div id="resultStatus"></div>
  <div id="resultTable"></div>

  <!-- 다운로드 버튼 그룹 -->
  <div style="margin-top:16px;">
    <div style="font-weight:700;margin-bottom:8px;color:var(--brand);">📥 출력 파일 다운로드</div>
    <div class="btn-dl-group">
      <button class="btn-danger" id="btnRedline" onclick="downloadRedline()" disabled>
        📝 redline_검토본.docx<br><small>수정추적+코멘트</small>
      </button>
      <button class="btn-success" id="btnClean" onclick="downloadClean()" disabled>
        ✅ clean_최종본.docx<br><small>변경 수락 날인용</small>
      </button>
      <button class="btn-secondary" id="btnReport" onclick="downloadReport()" disabled>
        📋 검토보고서.docx<br><small>리스크 요약 결재용</small>
      </button>
    </div>
    <div id="dlStatus" style="margin-top:8px;font-size:12px;color:var(--muted);"></div>
    <div id="docxWarning" style="margin-top:6px;font-size:12px;color:var(--warn);"></div>
  </div>
</div>

<!-- 원시 JSON (접을 수 있음) -->
<div class="card hidden" id="stepRaw">
  <h2 style="cursor:pointer;" onclick="toggleRaw()">▶ 원시 JSON 응답 <span id="rawToggleHint" style="font-size:12px;font-weight:400;">(클릭하여 펼치기)</span></h2>
  <pre id="rawOut" class="hidden"></pre>
</div>

</div><!-- /container -->

<script>
let sessionId = null;
let questions = [];
let isDocx = false;  // 원본이 .docx이면 redline 활성화

/* ─── 유틸 ────────────────────────────────────────────────── */
function show(id)   { document.getElementById(id).classList.remove('hidden'); }
function hide(id)   { document.getElementById(id).classList.add('hidden'); }
function setStatus(id, msg, type='info') {
  const el = document.getElementById(id);
  el.innerHTML = `<div class="status status-${type}">${msg}</div>`;
}
function spin(label) { return `<span class="spinner"></span> ${label}`; }

function riskBadge(tier) {
  const t = (tier||'').toUpperCase();
  if (t==='CRITICAL') return '<span class="badge badge-crit">CRITICAL</span>';
  if (t==='HIGH')     return '<span class="badge badge-high">HIGH</span>';
  if (t==='MEDIUM')   return '<span class="badge badge-medium">MEDIUM</span>';
  return '<span class="badge badge-low">LOW</span>';
}

function toggleRaw() {
  const pre = document.getElementById('rawOut');
  const hint = document.getElementById('rawToggleHint');
  if (pre.classList.contains('hidden')) {
    pre.classList.remove('hidden');
    hint.textContent = '(클릭하여 접기)';
    document.querySelector('#stepRaw h2').textContent = '▼ 원시 JSON 응답 ';
    document.querySelector('#stepRaw h2').appendChild(hint);
  } else {
    pre.classList.add('hidden');
    hint.textContent = '(클릭하여 펼치기)';
    document.querySelector('#stepRaw h2').textContent = '▶ 원시 JSON 응답 ';
    document.querySelector('#stepRaw h2').appendChild(hint);
  }
}

/* ─── STEP 1: 업로드 ───────────────────────────────────────── */
function onFileSelected() {
  // 새 파일을 고르면 이전 문서용으로 입력했던 계약유형/중점검토 힌트를
  // 지운다 — 그대로 두면 새 문서에 이전 문서의 값이 그대로 제출된다
  // (2026-09-02 실사례: 전략적 파트너십 계약이 이전 NDA 리뷰의 "NDA
  // 비밀유지계약서" 값을 물려받아 0건으로 종료됨).
  const ctEl = document.getElementById('contractType');
  const rfEl = document.getElementById('reviewFocus');
  if (ctEl) ctEl.value = '';
  if (rfEl) rfEl.value = '';
}

async function doUpload() {
  const f = document.getElementById('file').files[0];
  if (!f) { alert('파일을 선택하세요'); return; }

  isDocx = f.name.toLowerCase().endsWith('.docx');
  setStatus('uploadStatus', spin('업로드 중...'), 'info');

  const fd = new FormData();
  fd.append('file', f);
  fd.append('entity', document.getElementById('entity').value.trim());
  fd.append('contract_type', document.getElementById('contractType').value.trim());
  fd.append('review_focus', document.getElementById('reviewFocus').value.trim());

  let data;
  try {
    const res = await fetch('/api/upload', { method: 'POST', body: fd });
    data = await res.json();
  } catch(e) {
    setStatus('uploadStatus', '업로드 오류: ' + e, 'error'); return;
  }

  if (!data.extraction || !data.extraction.success) {
    setStatus('uploadStatus', '추출 실패: ' + (data.extraction ? data.extraction.error : JSON.stringify(data)), 'error');
    return;
  }

  sessionId = data.question_session_id;
  questions = data.questions || [];

  setStatus('uploadStatus',
    `<b>업로드 완료</b> · entity: <b>${data.classification.entity}</b> · 계약유형: <b>${data.classification.contract_type}</b> · 텍스트: ${data.extraction.text_length}자`,
    'ok'
  );

  // 질문 렌더링
  renderQuestions(questions);
  show('stepQ');

  document.getElementById('rawOut').textContent = JSON.stringify(data, null, 2);
  show('stepRaw');
}

/* ─── STEP 2: 질문 렌더링 ──────────────────────────────────── */
function renderQuestions(qs) {
  const host = document.getElementById('qForm');
  host.innerHTML = '';
  document.getElementById('qMeta').textContent = `세션 ID: ${sessionId} · 질문: ${qs.length}개`;
  for (const q of qs) {
    const wrap = document.createElement('div');
    wrap.style.marginBottom = '10px';
    wrap.innerHTML = `<div><b>${q.title}</b> ${q.required ? '<span style="color:red">*</span>' : ''}</div>
      <div style="color:var(--muted);font-size:12px;margin-bottom:4px">${q.description}</div>`;
    const sel = document.createElement('select');
    sel.id = `ans_${q.question_id}`;
    sel.innerHTML = '<option value="">(선택 안함)</option>';
    for (const o of (q.options || [])) {
      const opt = document.createElement('option');
      opt.value = o.value; opt.textContent = o.label;
      sel.appendChild(opt);
    }
    wrap.appendChild(sel);
    host.appendChild(wrap);
  }
}

/* ─── STEP 3: 검토 실행 ────────────────────────────────────── */
async function doReview() {
  if (!sessionId) { alert('먼저 업로드를 진행하세요'); return; }

  setStatus('resultStatus', spin('심층 검토 실행 중...'), 'info');
  show('stepResult');

  // 답변 저장
  const answers = {};
  for (const q of questions) {
    const el = document.getElementById(`ans_${q.question_id}`);
    if (el && el.value) answers[q.question_id] = el.value;
  }
  await fetch(`/api/question_sessions/${sessionId}/answers`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ answers })
  });

  // 검토 실행
  let review;
  try {
    const r = await fetch(`/api/question_sessions/${sessionId}/review`, { method: 'POST' });
    review = await r.json();
  } catch(e) {
    setStatus('resultStatus', '검토 오류: ' + e, 'error'); return;
  }

  // revision suggest
  let revision = {};
  try {
    const r2 = await fetch('/api/revision/suggest', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ session_id: sessionId })
    });
    revision = await r2.json();
  } catch(e) {}

  renderResults(review, revision);
  document.getElementById('rawOut').textContent = JSON.stringify({ review, revision }, null, 2);
  show('stepRaw');
}

// === dealer_rental 렌더링 게이트 (upload_ui) ===
const _UPL_DLR_BLOCKED = new Set([
  'isr_accident_reporting','isr_pl_defect_liability','isr_installation_defect',
  'isr_user_safety','isr_safety_certification','isr_pl_insurance','isr_defect_sla',
  'isr_defect_correction',
  'sppc_inspection_standard','sppc_return_limit','sppc_payment_retention',
  'sppc_custom_cancel_limit',
  'pi_safety_responsibility','pi_safety_manager','pi_legal_compliance',
  'pi_subcontractor_safety','pi_work_stop_right','pi_risk_assessment',
  'pi_accident_reporting','pi_ppe_education','pi_access_control',
  'pi_commissioning_accident_liability'
]);
const _UPL_DLR_PREFIXES = ['isr_','sppc_','pi_'];
const _UPL_DLR_TITLE_KW = ['제조물검토','안전권고','산업안전보건법','중대재해처벌법','시운전','착공','하도급 안전','보호구','위험성 평가','안전관리자'];
const _UPL_DLR_KW = ['사고 발생 보고','검수 완료 간주','반품 제한','이행유보권','주문제작 취소 제한'];
const _UPL_DLR_GATE = [
  { tk:['해지','종료','해제'], fb:['소유권','채권추심','신용정보','개인정보'] },
  { tk:['양도','지위 이전','계약자 변경'], fb:['판촉비','광고비','반품비','원상회복비','비용분담'] },
  { tk:['비밀','기밀'], fb:['인력','채용','배치','평가','징계','경영간섭'] },
];
const _UPL_MISMATCH = '자동수정 보류: 조항 주제와 수정문안 불일치';

function _uplApplyDlrGate(items, contractType) {
  if (!String(contractType || '').includes('dealer_rental')) return items;
  return items.filter(it => {
    if (!it) return false;
    const cid = String(it.clause_id || it.rule_id || '');
    const title = String(it.issue_title || it.clause_title || '');
    return !(_UPL_DLR_BLOCKED.has(cid) || _UPL_DLR_PREFIXES.some(p => cid.startsWith(p)) || _UPL_DLR_TITLE_KW.some(k => title.includes(k)) || _UPL_DLR_KW.some(k => title.includes(k)));
  }).map(it => {
    const tlo = String(it.clause_title || '').toLowerCase();
    const rw = String(it.suggested_rewrite || '').trim();
    if (!rw || rw === _UPL_MISMATCH) return it;
    for (const g of _UPL_DLR_GATE) {
      if (g.tk.some(k => tlo.includes(k)) && g.fb.some(f => rw.includes(f))) {
        return Object.assign({}, it, { suggested_rewrite: _UPL_MISMATCH, has_rewrite_change: false });
      }
    }
    return it;
  });
}

function renderResults(review, revision) {
  const _contractType = (review.clause_meta && review.clause_meta.contract_type) || (review.classification && review.classification.contract_type) || '';
  const crs = _uplApplyDlrGate((review.clause_results || []), _contractType);
  const high = crs.filter(c => (c.risk_tier||'').toUpperCase() === 'HIGH').length;
  const med  = crs.filter(c => (c.risk_tier||'').toUpperCase() === 'MEDIUM').length;
  const crit = crs.filter(c => (c.risk_tier||'').toUpperCase() === 'CRITICAL').length;
  const total = crs.length;

  // 리스크 바
  document.getElementById('riskBar').innerHTML = `
    <div class="risk-chip" style="background:#fde8e8;color:#900;">${crit} CRITICAL</div>
    <div class="risk-chip" style="background:#f8d7d7;color:#900;">${high} HIGH</div>
    <div class="risk-chip" style="background:#fff3cd;color:#7a4a00;">${med} MEDIUM</div>
    <div class="risk-chip" style="background:#e8f0fe;color:#1a3a6b;">${total} 조항 검토</div>
  `;

  setStatus('resultStatus',
    `검토 완료 · CRITICAL: ${crit} · HIGH: ${high} · MEDIUM: ${med} · 전체 이슈 조항: ${total}`,
    high+crit > 0 ? 'error' : med > 0 ? 'warn' : 'ok'
  );

  // 검토 테이블
  const significant = crs.filter(c => {
    const t = (c.risk_tier||'').toUpperCase();
    return t === 'CRITICAL' || t === 'HIGH' || t === 'MEDIUM' || c.must_fix || c.approval_required;
  }).slice(0, 30);

  if (!significant.length) {
    document.getElementById('resultTable').innerHTML = '<div style="color:var(--muted)">검출된 주요 리스크 없음</div>';
  } else {
    let rows = '';
    for (const cr of significant) {
      const orig = (cr.original_text || '').slice(0, 120);
      const sugg = (cr.suggested_rewrite || '').slice(0, 120);
      const wcs  = (cr.worst_case_scenario || '').slice(0, 100);
      const neg  = (cr.negotiation_strategy || '').slice(0, 80);
      rows += `<tr>
        <td>${cr.display_path || cr.clause_id || ''}</td>
        <td>${riskBadge(cr.risk_tier)}${cr.must_fix ? ' <span style="color:#900;font-weight:700;">필수</span>':''}</td>
        <td>${(cr.rewrite_reason || '').slice(0, 120)}</td>
        <td>
          ${orig ? `<div class="orig">${escHtml(orig)}${orig.length===120?'…':''}</div>` : ''}
          ${sugg ? `<div class="sugg">→ ${escHtml(sugg)}${sugg.length===120?'…':''}</div>` : ''}
        </td>
        <td style="font-size:12px;">${escHtml(wcs)}</td>
        <td style="font-size:12px;">${escHtml(neg)}</td>
      </tr>`;
    }
    document.getElementById('resultTable').innerHTML = `
      <table>
        <thead><tr>
          <th style="width:90px">조항</th>
          <th style="width:80px">등급</th>
          <th style="width:200px">이슈</th>
          <th style="width:220px">원문 → 수정안</th>
          <th style="width:160px">최악 시나리오</th>
          <th style="width:130px">협상 전략</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // dealer_rental: 이미반영/별첨참고 섹션 추가
  const _allCrs = review.clause_results || [];
  _uplRenderReflectedSection(_allCrs, _contractType);

  // 다운로드 버튼 활성화
  document.getElementById('btnReport').disabled = false;
  if (isDocx) {
    document.getElementById('btnRedline').disabled = false;
    document.getElementById('btnClean').disabled = false;
    document.getElementById('docxWarning').textContent = '';
  } else {
    document.getElementById('docxWarning').textContent =
      '※ Redline DOCX는 원본 .docx 파일 업로드 시에만 생성됩니다.';
  }
}

function _uplRenderReflectedSection(items, contractType) {
  const tableEl = document.getElementById('resultTable');
  if (!tableEl || !String(contractType || '').includes('dealer_rental')) return;
  const reflected = (items || []).filter(it => it && String(it.display_bucket || '') === '이미반영');
  const custForm = (items || []).filter(it => it && String(it.display_bucket || '') === '별첨참고');
  if (reflected.length === 0 && custForm.length === 0) return;
  let html = '';
  if (reflected.length > 0) {
    html += '<div style="margin-top:20px;padding:14px;background:#f0fdf4;border-radius:8px;border:1px solid #bbf7d0;">';
    html += '<div style="font-weight:700;color:#166534;margin-bottom:10px;">이미 반영된 핵심 안전장치 (' + reflected.length + '건)</div>';
    for (const it of reflected) {
      html += '<div style="margin-bottom:8px;padding:8px 12px;background:#fff;border-radius:4px;border-left:3px solid #22c55e;">';
      html += '<div style="font-weight:600;color:#166534;">[반영됨] ' + escHtml(it.clause_title || it.rule_id || '') + '</div>';
      html += '<div style="color:#374151;font-size:13px;">' + escHtml(it.current_assessment_text || it.rewrite_reason || '') + '</div>';
      html += '</div>';
    }
    html += '</div>';
  }
  if (custForm.length > 0) {
    html += '<div style="margin-top:12px;padding:12px;background:#f8fafc;border-radius:8px;border:1px solid #cbd5e1;">';
    html += '<div style="font-weight:600;color:#475569;margin-bottom:6px;">별첨/고객계약 양식 참고</div>';
    for (const it of custForm) {
      html += '<div style="color:#64748b;font-size:13px;">' + escHtml(it.current_assessment_text || '') + '</div>';
    }
    html += '</div>';
  }
  tableEl.insertAdjacentHTML('afterend', html);
}

function escHtml(s) {
  return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

/* ─── 다운로드 핸들러 ───────────────────────────────────────── */
async function downloadFile(url, postBody, defaultFilename) {
  document.getElementById('dlStatus').textContent = '생성 중...';
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(postBody)
    });
    if (!res.ok) {
      const err = await res.json().catch(()=>({}));
      document.getElementById('dlStatus').textContent = '오류: ' + (err.error || res.status);
      return;
    }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename="?([^";]+)"?/);
    const fname = m ? m[1] : defaultFilename;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = fname;
    a.click();
    document.getElementById('dlStatus').textContent = `다운로드 완료: ${fname}`;
  } catch(e) {
    document.getElementById('dlStatus').textContent = '오류: ' + e;
  }
}

function downloadRedline() {
  downloadFile('/api/revision/download_redline', { session_id: sessionId }, 'redline_검토본.docx');
}
function downloadClean() {
  downloadFile('/api/revision/download_clean', { session_id: sessionId }, 'clean_최종본.docx');
}
function downloadReport() {
  downloadFile('/api/revision/download_docx', { session_id: sessionId, rebuild: false }, '검토보고서.docx');
}
</script>
</body>
</html>
"""
