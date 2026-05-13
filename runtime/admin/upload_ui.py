UPLOAD_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AouriBot Upload & Review (MVP)</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 24px; }
    .muted { color: #666; margin-bottom: 16px; }
    .row { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
    input, select, button, textarea { padding: 6px 8px; font-size: 14px; }
    textarea { width: 100%; min-height: 120px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #111; color: #eee; padding: 12px; border-radius: 8px; }
    .box { border: 1px solid #ddd; border-radius: 8px; padding: 12px; margin-bottom: 16px; }
    .warn { color: #8a3b00; }
  </style>
</head>
<body>
  <h1>Upload & Review (MVP)</h1>
  <div class="muted">지원: .txt, .docx, .xlsx, .pdf, .hwp</div>

  <div class="box">
    <h2>1) 업로드</h2>
    <div class="row">
      <input type="file" id="file" />
      <button onclick="uploadStart()">업로드</button>
    </div>
    <div class="row">
      <input id="entity" placeholder="entity (비우면 자동추정)" />
      <input id="contractType" placeholder="contract_type (비우면 자동추정)" />
    </div>
    <div class="row">
      <textarea id="reviewFocus" placeholder="중점 검토 내용(예: 대리점법상 불이익제공/경영간섭/비용전가/해지 남용 등)"></textarea>
    </div>
    <div class="muted warn">entity/contract_type을 비우면 텍스트+파일명 기반으로 추정합니다(정확도 제한).</div>
  </div>

  <div class="box">
    <h2>2) 추가 질문</h2>
    <div id="qMeta" class="muted"></div>
    <div id="qForm"></div>
    <div class="row">
      <button onclick="submitAnswersAndReview()">답변 저장 & 검토 실행</button>
    </div>
  </div>

  <div class="box">
    <h2>3) 검토 결과</h2>
    <div id="meta" class="muted"></div>
    <pre id="out"></pre>
  </div>

  <script>
    let sessionId = null;
    let questions = [];

    function renderQuestions() {
      const host = document.getElementById('qForm');
      host.innerHTML = '';
      if (!questions.length) return;
      for (const q of questions) {
        const box = document.createElement('div');
        box.className = 'box';
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
      }
    }

    async function uploadStart() {
      const f = document.getElementById('file').files[0];
      if (!f) { alert('파일을 선택하세요'); return; }
      const fd = new FormData();
      fd.append('file', f);
      fd.append('entity', document.getElementById('entity').value || '');
      fd.append('contract_type', document.getElementById('contractType').value || '');
      fd.append('review_focus', document.getElementById('reviewFocus').value || '');

      const res = await fetch('/api/upload', { method: 'POST', body: fd });
      const data = await res.json();
      if (!data.extraction || !data.extraction.success) {
        document.getElementById('meta').innerText = `추출 실패: ${data.extraction ? data.extraction.error : ''}`;
        document.getElementById('out').innerText = JSON.stringify(data, null, 2);
        return;
      }

      sessionId = data.question_session_id;
      questions = data.questions || [];
      document.getElementById('qMeta').innerText =
        `session_id=${sessionId} detected_rules=${(data.detected_rule_ids || []).length} questions=${questions.length}`;
      renderQuestions();
      document.getElementById('meta').innerText =
        `extract_success=${data.extraction.success} method=${data.extraction.method} entity=${data.classification.entity} contract_type=${data.classification.contract_type}`;
      document.getElementById('out').innerText = JSON.stringify(data, null, 2);
    }

    async function submitAnswersAndReview() {
      if (!sessionId) { alert('먼저 업로드를 진행하세요'); return; }
      const answers = {};
      for (const q of questions) {
        const v = document.getElementById(`ans_${q.question_id}`).value;
        if (v) answers[q.question_id] = v;
      }
      const res1 = await fetch(`/api/question_sessions/${sessionId}/answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
      });
      const saved = await res1.json();

      const res2 = await fetch(`/api/question_sessions/${sessionId}/review`, { method: 'POST' });
      const review = await res2.json();

      const res3 = await fetch('/api/revision/suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8' },
        body: JSON.stringify({ session_id: sessionId })
      });
      const revision = await res3.json();

      document.getElementById('out').innerText = JSON.stringify({ saved_session: saved, review, revision }, null, 2);
    }
  </script>
</body>
</html>
"""

