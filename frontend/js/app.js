/**
 * Meeting Minutes Agent — frontend JS
 *
 * Features:
 *  - Tab switching (record / upload)
 *  - Browser MediaRecorder-based audio recording with live timer
 *  - File upload with drag-and-drop
 *  - Job submission and polling (/api/v1/audio/upload, /api/v1/audio/jobs/:id)
 *  - Pipeline step progress visualization
 *  - Markdown rendering for the minutes result
 *  - Copy-to-clipboard and Markdown download
 */

'use strict';

// ── Constants ────────────────────────────────────────────────────────────────
const API_BASE    = '/api/v1';
const POLL_MS     = 3000;   // polling interval in milliseconds
const MAX_SIZE_MB = 100;

// ── State ────────────────────────────────────────────────────────────────────
let mediaRecorder    = null;
let recordedChunks   = [];
let recordedBlob     = null;
let uploadedFile     = null;
let timerInterval    = null;
let timerSeconds     = 0;
let pollingInterval  = null;
let activeJobId      = null;
let activeTab        = 'record';  // 'record' | 'upload'

// ── DOM helpers ──────────────────────────────────────────────────────────────
const $  = id => document.getElementById(id);
const $$ = sel => document.querySelectorAll(sel);

// ── Initialization ───────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  setupInputTabs();
  setupResultTabs();
  setupRecording();
  setupUpload();
  setupSubmit();
  setupResultActions();
});

// ── Tab switching (input) ────────────────────────────────────────────────────
function setupInputTabs() {
  $$('.tab[data-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      activeTab = tab;
      $$('.tab[data-tab]').forEach(b => {
        b.classList.toggle('active', b === btn);
        b.setAttribute('aria-selected', b === btn);
      });
      $$('.tab-panel').forEach(p => p.classList.remove('active'));
      $(`panel-${tab}`).classList.add('active');
      updateSubmitButton();
    });
  });
}

// ── Tab switching (result) ───────────────────────────────────────────────────
function setupResultTabs() {
  $$('.tab[data-result-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      $$('.tab[data-result-tab]').forEach(b => b.classList.toggle('active', b === btn));
      $$('.result-panel').forEach(p => p.classList.remove('active'));
      $(`rpanel-${btn.dataset.resultTab}`).classList.add('active');
    });
  });
}

// ── Recording ────────────────────────────────────────────────────────────────
function setupRecording() {
  $('btn-record-start').addEventListener('click', startRecording);
  $('btn-record-stop').addEventListener('click', stopRecording);
  $('btn-discard-recording').addEventListener('click', discardRecording);
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recordedChunks = [];
    recordedBlob   = null;

    const mimeType = getSupportedMimeType();
    mediaRecorder  = new MediaRecorder(stream, mimeType ? { mimeType } : {});
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) recordedChunks.push(e.data); };
    mediaRecorder.onstop = onRecordingStop;
    mediaRecorder.start(250);

    // UI
    $('btn-record-start').disabled = true;
    $('btn-record-stop').disabled  = false;
    $('btn-record-start').classList.add('recording');
    setStatusDot('recording', '録音中...');
    startTimer();
  } catch (err) {
    alert(`マイクへのアクセスに失敗しました: ${err.message}`);
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
  }
  $('btn-record-stop').disabled = true;
  stopTimer();
}

function onRecordingStop() {
  const mimeType = mediaRecorder.mimeType || 'audio/webm';
  recordedBlob   = new Blob(recordedChunks, { type: mimeType });
  const url      = URL.createObjectURL(recordedBlob);

  $('recorded-audio').src = url;
  $('recorded-preview').classList.remove('hidden');
  $('btn-record-start').disabled = false;
  $('btn-record-start').classList.remove('recording');
  setStatusDot('done', '録音完了');
  updateSubmitButton();
}

function discardRecording() {
  recordedBlob = null;
  $('recorded-audio').src = '';
  $('recorded-preview').classList.add('hidden');
  setStatusDot('idle', '録音待機中');
  $('record-timer').textContent = '00:00';
  timerSeconds = 0;
  updateSubmitButton();
}

function setStatusDot(state, text) {
  const dot = $('status-dot');
  dot.className = `status-dot ${state}`;
  $('status-text').textContent = text;
}

function startTimer() {
  timerSeconds = 0;
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timerSeconds++;
    updateTimerDisplay();
  }, 1000);
}
function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
}
function updateTimerDisplay() {
  const m = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
  const s = String(timerSeconds % 60).padStart(2, '0');
  $('record-timer').textContent = `${m}:${s}`;
}

function getSupportedMimeType() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  return types.find(t => MediaRecorder.isTypeSupported(t)) || '';
}

// ── Upload ────────────────────────────────────────────────────────────────────
function setupUpload() {
  const zone  = $('upload-drop-zone');
  const input = $('file-input');

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    handleFile(e.dataTransfer.files[0]);
  });
  input.addEventListener('change', () => handleFile(input.files[0]));
  $('btn-discard-upload').addEventListener('click', discardUpload);
}

function handleFile(file) {
  if (!file) return;
  const allowedTypes = ['audio/wav', 'audio/mpeg', 'audio/mp4', 'audio/ogg',
                        'audio/webm', 'audio/flac', 'audio/x-flac',
                        'video/webm', 'application/octet-stream'];
  const ext = file.name.split('.').pop().toLowerCase();
  const allowedExts = ['wav','mp3','mp4','m4a','ogg','webm','flac'];
  if (!allowedExts.includes(ext)) {
    alert(`対応していないファイル形式です: .${ext}`);
    return;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    alert(`ファイルサイズが上限（${MAX_SIZE_MB} MB）を超えています。`);
    return;
  }
  uploadedFile = file;
  const url = URL.createObjectURL(file);
  $('upload-audio').src = url;
  $('upload-filename').textContent = `${file.name} (${formatBytes(file.size)})`;
  $('upload-preview').classList.remove('hidden');
  updateSubmitButton();
}

function discardUpload() {
  uploadedFile = null;
  $('upload-audio').src = '';
  $('upload-preview').classList.add('hidden');
  $('file-input').value = '';
  updateSubmitButton();
}

function formatBytes(bytes) {
  if (bytes < 1024)       return `${bytes} B`;
  if (bytes < 1024**2)    return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1024**2).toFixed(1)} MB`;
}

// ── Submit ────────────────────────────────────────────────────────────────────
function setupSubmit() {
  $('btn-submit').addEventListener('click', submitAudio);
}

function updateSubmitButton() {
  const hasAudio = (activeTab === 'record' && recordedBlob) ||
                   (activeTab === 'upload' && uploadedFile);
  $('btn-submit').disabled = !hasAudio;
}

async function submitAudio() {
  const blob = activeTab === 'record' ? recordedBlob : uploadedFile;
  if (!blob) return;

  const filename = activeTab === 'record'
    ? `recording_${Date.now()}.webm`
    : uploadedFile.name;

  const formData = new FormData();
  formData.append('file', blob, filename);

  // Show progress section
  showSection('progress-section');
  hideSection('result-section');
  hideSection('error-section');
  resetPipelineSteps();
  $('progress-message').textContent = '音声ファイルを送信中...';
  $('btn-submit').disabled = true;

  try {
    const resp = await fetch(`${API_BASE}/audio/upload`, {
      method: 'POST',
      body: formData,
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: resp.statusText }));
      throw new Error(err.detail || resp.statusText);
    }
    const data = await resp.json();
    activeJobId = data.job_id;
    startPolling(activeJobId);
  } catch (err) {
    showError(`送信に失敗しました: ${err.message}`);
  }
}

// ── Polling ──────────────────────────────────────────────────────────────────
function startPolling(jobId) {
  clearInterval(pollingInterval);
  pollingInterval = setInterval(() => pollJob(jobId), POLL_MS);
  pollJob(jobId);
}

async function pollJob(jobId) {
  try {
    const resp = await fetch(`${API_BASE}/audio/jobs/${jobId}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();
    updateProgress(data);
    if (data.status === 'done' || data.status === 'error') {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
  } catch (err) {
    clearInterval(pollingInterval);
    showError(`ステータスの取得に失敗しました: ${err.message}`);
  }
}

function updateProgress(data) {
  $('progress-message').textContent = data.message || '処理中...';

  // Determine which steps are complete based on available fields
  const hasCU      = !!data.content_analysis;
  const hasScript  = !!data.script;
  const hasMinutes = !!data.minutes;
  const hasFinal   = !!data.final_minutes;
  const isDone     = data.status === 'done';
  const isError    = data.status === 'error';

  setStepState('step-cu',     hasCU,     !hasCU && data.status === 'processing',  isError && !hasCU,     '音声解析完了', '解析中...');
  setStepState('step-script', hasScript, !hasScript && hasCU,                     isError && !hasScript, 'スクリプト生成完了', '生成中...');
  setStepState('step-minutes',hasMinutes,!hasMinutes && hasScript,                isError && !hasMinutes,'議事録作成完了', '作成中...');
  setStepState('step-term',   hasFinal,  !hasFinal && hasMinutes,                 isError && !hasFinal,  '用語補足完了', '補足中...');

  if (isDone && data.final_minutes) {
    renderResults(data);
  } else if (isError) {
    showError(data.message || 'エラーが発生しました');
  }
}

function setStepState(stepId, done, active, error, doneText, activeText) {
  const el     = $(stepId);
  const status = $(`${stepId}-status`);
  el.classList.remove('active', 'complete', 'error-step');
  if (done) {
    el.classList.add('complete');
    status.textContent = `✓ ${doneText}`;
  } else if (active) {
    el.classList.add('active');
    status.textContent = activeText;
  } else if (error) {
    el.classList.add('error-step');
    status.textContent = '✗ エラー';
  } else {
    status.textContent = '待機中';
  }
}

function resetPipelineSteps() {
  ['step-cu','step-script','step-minutes','step-term'].forEach(id => {
    const el = $(id);
    el.classList.remove('active','complete','error-step');
    $(`${id}-status`).textContent = '待機中';
  });
}

// ── Results rendering ────────────────────────────────────────────────────────
function renderResults(data) {
  // Minutes (Markdown → HTML)
  const minutesMd = data.final_minutes?.markdown || data.minutes?.raw_markdown || '';
  $('minutes-content').innerHTML = markdownToHtml(minutesMd);

  // Script
  $('script-content').textContent = data.script?.script || '';

  // Transcript
  $('transcript-content').textContent = data.content_analysis?.raw_transcript || '';

  // Glossary
  const glossary = data.final_minutes?.glossary || [];
  renderGlossary(glossary);

  showSection('result-section');
  hideSection('progress-section');
  $('btn-submit').disabled = false;

  // Store markdown for download
  $('result-section').dataset.markdown = minutesMd;
}

function renderGlossary(glossary) {
  const el = $('glossary-content');
  if (!glossary.length) {
    el.innerHTML = '<p style="color:var(--text-muted)">使用された専門用語は検出されませんでした。</p>';
    return;
  }
  const rows = glossary.map(g =>
    `<tr><td><strong>${escHtml(g.term)}</strong></td><td>${escHtml(g.definition)}</td></tr>`
  ).join('');
  el.innerHTML = `
    <table>
      <thead><tr><th>用語</th><th>定義</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Result actions ────────────────────────────────────────────────────────────
function setupResultActions() {
  $('btn-copy').addEventListener('click', copyMinutes);
  $('btn-download').addEventListener('click', downloadMinutes);
  $('btn-reset').addEventListener('click', resetAll);
  $('btn-error-reset').addEventListener('click', resetAll);
}

async function copyMinutes() {
  const md = $('result-section').dataset.markdown || '';
  try {
    await navigator.clipboard.writeText(md);
    $('btn-copy').textContent = '✓ コピーしました';
    setTimeout(() => { $('btn-copy').textContent = '📋 コピー'; }, 2000);
  } catch { alert('コピーに失敗しました'); }
}

function downloadMinutes() {
  const md   = $('result-section').dataset.markdown || '';
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `meeting-minutes_${new Date().toISOString().slice(0,10)}.md`;
  a.click();
  URL.revokeObjectURL(url);
}

function resetAll() {
  discardRecording();
  discardUpload();
  hideSection('progress-section');
  hideSection('result-section');
  hideSection('error-section');
  resetPipelineSteps();
  activeJobId = null;
  clearInterval(pollingInterval);
  pollingInterval = null;
  updateSubmitButton();
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function showSection(id) { $(id).classList.remove('hidden'); }
function hideSection(id) { $(id).classList.add('hidden'); }

function showError(message) {
  $('error-message').textContent = message;
  showSection('error-section');
  hideSection('progress-section');
  $('btn-submit').disabled = false;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Minimal Markdown → HTML renderer (enough for the minutes format).
 * Handles: # headings, **bold**, tables, unordered lists, paragraphs.
 */
function markdownToHtml(md) {
  if (!md) return '';
  let html = '';
  const lines = md.split('\n');
  let inTable  = false;
  let inList   = false;

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];

    // Headings
    if (/^### (.+)/.test(line)) {
      closeList(); html += `<h3>${escHtml(line.slice(4))}</h3>`; continue;
    }
    if (/^## (.+)/.test(line)) {
      closeList(); html += `<h2>${escHtml(line.slice(3))}</h2>`; continue;
    }
    if (/^# (.+)/.test(line)) {
      closeList(); html += `<h1>${escHtml(line.slice(2))}</h1>`; continue;
    }

    // Table rows
    if (/^\|/.test(line)) {
      if (!inTable) { html += '<table>'; inTable = true; }
      // Separator row: |---|---|
      if (/^\|[-| :]+\|$/.test(line)) continue;
      const isFirstRow = html.endsWith('<table>') || html.endsWith('</thead>');
      const cells = line.split('|').filter((_, j, a) => j > 0 && j < a.length - 1);
      const tag = (i === 0 || !html.endsWith('</tr>')) && isFirstRow ? 'th' : 'td';
      html += `<tr>${cells.map(c => `<${tag}>${inlineFormat(c.trim())}</${tag}>`).join('')}</tr>`;
      continue;
    }
    if (inTable) { html += '</table>'; inTable = false; }

    // Unordered list
    if (/^[-*] (.+)/.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inlineFormat(line.replace(/^[-*] /, ''))}</li>`;
      continue;
    }
    closeList();

    // Blank line → paragraph break
    if (line.trim() === '') { html += '<br>'; continue; }

    // Plain line
    html += `<p>${inlineFormat(line)}</p>`;
  }
  if (inTable) html += '</table>';
  closeList();
  return html;

  function closeList() {
    if (inList) { html += '</ul>'; inList = false; }
  }
}

function inlineFormat(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,     '<em>$1</em>');
}
