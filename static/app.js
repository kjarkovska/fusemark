// app.js — ObsiNote frontend logic

let recording = false;
let timerInterval = null;
let timerSeconds = 0;
let jobsPollInterval = null;
let levelMeterInterval = null;
const METER_BARS = 14;

// ------------------------------------------------------------------
// Recording
// ------------------------------------------------------------------

async function toggleRecording() {
  if (recording) {
    await stopRecording();
  } else {
    await startRecording();
  }
}

async function startRecording() {
  const label = document.getElementById('label')?.value || '';
  const folder = document.getElementById('folder')?.value || 'Other';
  const template = document.getElementById('template')?.value || '';

  const res = await fetch('/start', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({label, folder, template}),
  });

  if (!res.ok) {
    const err = await res.json();
    alert('Chyba: ' + (err.error || res.status));
    return;
  }

  recording = true;
  setRecorderUI(true);
  startTimer();
  startLevelMeter();
}

async function stopRecording() {
  const scratch = document.getElementById('scratch')?.value || '';

  // Update UI immediately — ffmpeg encoding on the server can take several seconds
  recording = false;
  stopTimer();
  stopLevelMeter();
  setRecorderUI('stopping');
  if (document.getElementById('scratch')) {
    document.getElementById('scratch').value = '';
  }

  const res = await fetch('/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scratch_notes: scratch}),
  });

  setRecorderUI(false);

  if (!res.ok) {
    const err = await res.json();
    alert('Chyba: ' + (err.error || res.status));
    return;
  }

  refreshJobs();
}

function setRecorderUI(state) {
  const btn = document.getElementById('rec-btn');
  const panel = document.getElementById('recorder');
  if (!btn) return;
  if (state === true) {
    btn.textContent = 'Zastavit nahrávání';
    btn.className = 'btn-stop';
    btn.disabled = false;
    panel?.classList.add('is-recording');
  } else if (state === 'stopping') {
    btn.textContent = 'Ukládám...';
    btn.className = 'btn-stop';
    btn.disabled = true;
    panel?.classList.remove('is-recording');
  } else {
    btn.textContent = 'Spustit nahrávání';
    btn.className = 'btn-start';
    btn.disabled = false;
    panel?.classList.remove('is-recording');
  }
}

// ------------------------------------------------------------------
// Level meter
// ------------------------------------------------------------------

function startLevelMeter() {
  const meter = document.getElementById('level-meter');
  if (!meter) return;
  meter.innerHTML = Array(METER_BARS).fill(null)
    .map(() => '<span class="level-bar"></span>').join('');
  levelMeterInterval = setInterval(() => {
    meter.querySelectorAll('.level-bar').forEach(bar => {
      const l = 0.25 + Math.random() * 0.75;
      bar.style.height = `${Math.round(l * 16)}px`;
      bar.style.opacity = String(0.6 + l * 0.4);
    });
  }, 110);
}

function stopLevelMeter() {
  clearInterval(levelMeterInterval);
  levelMeterInterval = null;
  const meter = document.getElementById('level-meter');
  if (!meter) return;
  meter.querySelectorAll('.level-bar').forEach(bar => {
    bar.style.height = '3px';
    bar.style.opacity = '0.15';
  });
}

// ------------------------------------------------------------------
// Timer
// ------------------------------------------------------------------

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
  timerSeconds = 0;
  updateTimerDisplay();
}

function updateTimerDisplay() {
  const el = document.getElementById('timer');
  if (!el) return;
  const m = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
  const s = String(timerSeconds % 60).padStart(2, '0');
  el.textContent = `${m}:${s}`;
}

// ------------------------------------------------------------------
// Jobs panel
// ------------------------------------------------------------------

async function refreshJobs() {
  const el = document.getElementById('jobs-list');
  if (!el) return;

  const res = await fetch('/jobs');
  const jobs = await res.json();

  if (!jobs.length) {
    el.innerHTML = `
      <div class="jobs-empty-state">
        <img src="/static/img/logo-mark.svg" class="jobs-empty-logo" alt="">
        <div class="jobs-empty-title">Zatím žádné záznamy</div>
        <div class="jobs-empty-hint">Spusťte nahrávání nebo importujte přepis. Zpracované porady se objeví zde.</div>
      </div>`;
    return;
  }

  el.innerHTML = jobs.map(renderJob).join('');
}

function renderJob(job) {
  const date = formatLocalDate(job.created_at);
  const progress = progressFromJob(job);
  const isActive = job.status === 'transcribing' || job.status === 'generating';
  const isDeletable = job.status === 'done' || job.status === 'error';
  const isError = job.status === 'error';

  const pill = `<span class="job-status status-${job.status}">${statusLabel(job.status)}</span>`;

  const deleteBtn = isDeletable
    ? `<button class="btn-delete" onclick="deleteJob('${job.id}')" title="Smazat">&#10005;</button>`
    : '';

  const retryDisabled = isError && !job.audio_exists ? ' disabled title="Recording deleted"' : '';
  const retryBtn = isError
    ? `<button class="btn-secondary btn-retry" onclick="retryJob('${job.id}')"${retryDisabled}>Zkusit znovu</button>`
    : '';

  // done/error: header-row with pill+X on right; active: header-row pill only; queued: stacked
  const header = (isActive)
    ? `<div class="job-header-row">
         <div>
           <div class="job-label">${esc(job.label || 'Porada')}</div>
           <div class="job-date">${date}</div>
         </div>
         ${pill}
       </div>`
    : isDeletable
    ? `<div class="job-header-row">
         <div>
           <div class="job-label">${esc(job.label || 'Porada')}</div>
           <div class="job-date">${date}</div>
         </div>
         <div style="display:flex;align-items:center;gap:6px">${pill}${deleteBtn}</div>
       </div>`
    : `<div class="job-label">${esc(job.label || 'Porada')}</div>
       <div class="job-date">${date}</div>
       <div class="job-pill-bottom">${pill}</div>`;

  let progressLabel = '';
  if (job.status === 'transcribing') {
    if (job.extra_context === 'transcribing:uploading') {
      progressLabel = 'Uploading audio…';
    } else if (job.extra_context === 'transcribing:processing') {
      progressLabel = 'Transcribing via API…';
    } else {
      const eta = etaFromJob(job);
      progressLabel = eta ? `${progress}%, ${eta}` : `${progress}%`;
    }
  }

  const progressBar = isActive
    ? `<div class="job-progress-row">
         <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>
       </div>
       ${progressLabel ? `<div class="job-eta">${progressLabel}</div>` : ''}`
    : '';

  const errorCallout = isError && job.error_message
    ? `<div class="job-error">${esc(job.error_message)}</div>`
    : '';

  const errorActions = isError
    ? `<div class="job-error-actions">${retryBtn}</div>`
    : '';

  const contextField = (!isDeletable && !isActive)
    ? `<div class="job-context">
         <input type="text" id="ctx-${job.id}" value="${esc(job.extra_context || '')}" placeholder="Kontext, účastníci...">
         <button class="btn-secondary" onclick="saveContext('${job.id}')">Uložit</button>
       </div>`
    : '';

  const audioDecision = (job.status === 'done' && job.keep_audio === null)
    ? `<div class="job-audio">
         Audio:
         <button class="btn-secondary" onclick="audioDecision('${job.id}', true)">Archivovat</button>
         <button class="btn-secondary" onclick="audioDecision('${job.id}', false)">Smazat</button>
       </div>`
    : '';

  return `
    <div class="job">
      ${header}
      ${progressBar}
      ${errorCallout}
      ${errorActions}
      ${contextField}
      ${audioDecision}
    </div>`;
}

function progressFromJob(job) {
  if (!job.extra_context) return 0;
  const m = job.extra_context.match(/transcribing:(\d+)%/);
  return m ? parseInt(m[1]) : 0;
}

function etaFromJob(job) {
  if (!job.extra_context) return null;
  const m = job.extra_context.match(/transcribing:\d+%:eta:(\d+)s/);
  if (!m) return null;
  const secs = parseInt(m[1]);
  const mm = String(Math.floor(secs / 60)).padStart(2, '0');
  const ss = String(secs % 60).padStart(2, '0');
  return `${mm}:${ss}`;
}

function statusLabel(status) {
  const labels = {
    recording: 'Nahrávám',
    queued: 'Ve frontě',
    transcribing: 'Přepisuji',
    generating: 'Generuji',
    done: 'Hotovo',
    error: 'Chyba',
  };
  return labels[status] || status;
}

async function saveContext(jobId) {
  const val = document.getElementById(`ctx-${jobId}`)?.value || '';
  await fetch(`/jobs/${jobId}/context`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({context: val}),
  });
}

async function audioDecision(jobId, keep) {
  await fetch(`/jobs/${jobId}/audio`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keep}),
  });
  refreshJobs();
}

async function clearCompleted() {
  await fetch('/jobs', {method: 'DELETE'});
  refreshJobs();
}

async function deleteJob(jobId) {
  await fetch(`/jobs/${jobId}`, {method: 'DELETE'});
  refreshJobs();
}

async function retryJob(jobId) {
  const res = await fetch(`/jobs/${jobId}/retry`, {method: 'POST'});
  if (!res.ok) {
    const err = await res.json();
    alert(err.error || 'Retry failed');
    return;
  }
  refreshJobs();
}

function formatLocalDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ------------------------------------------------------------------
// Init
// ------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  // Restore recording state after page reload
  const status = await fetch('/status').then(r => r.json());
  if (status.recording) {
    recording = true;
    setRecorderUI(true);
    startTimer();
    startLevelMeter();
  }

  if (document.getElementById('jobs-list')) {
    refreshJobs();
    jobsPollInterval = setInterval(refreshJobs, 3000);
  }

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeImportModal();
  });
});

// ------------------------------------------------------------------
// Import Transcript Modal
// ------------------------------------------------------------------

function openImportModal() {
  const today = new Date().toISOString().slice(0, 10);
  document.getElementById('import-date').value = today;
  document.getElementById('import-modal').style.display = 'flex';
  document.getElementById('import-label').focus();
}

function closeImportModal(event) {
  if (event && event.target !== document.getElementById('import-modal')) return;
  document.getElementById('import-modal').style.display = 'none';
  document.getElementById('import-transcript').value = '';
  document.getElementById('import-label').value = '';
  document.getElementById('import-msg').textContent = '';
}

let _audioFile = null;

function openAudioModal() {
  document.getElementById('audio-modal').style.display = 'flex';
  document.getElementById('audio-label').focus();
}

function closeAudioModal(event) {
  if (event && event.target !== document.getElementById('audio-modal')) return;
  document.getElementById('audio-modal').style.display = 'none';
  _audioFile = null;
  document.getElementById('audio-file-hint').textContent =
    'Podporované formáty: .mp3, .wav, .m4a, .ogg, .flac';
  document.getElementById('audio-label').value = '';
  document.getElementById('audio-scratch').value = '';
  document.getElementById('audio-msg').textContent = '';
}

function handleAudioFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  _audioFile = file;
  document.getElementById('audio-file-hint').textContent = file.name;
  event.target.value = '';
}

async function submitAudioImport() {
  const msgEl = document.getElementById('audio-msg');
  if (!_audioFile) { msgEl.textContent = 'Vyberte audio soubor.'; return; }
  const fd = new FormData();
  fd.append('audio', _audioFile);
  fd.append('label', document.getElementById('audio-label').value || '');
  fd.append('folder', document.getElementById('audio-folder').value || 'Other');
  fd.append('template', document.getElementById('audio-template').value || '');
  fd.append('meeting_date', document.getElementById('audio-date').value || '');
  fd.append('scratch_notes', document.getElementById('audio-scratch').value.trim());
  const res = await fetch('/import-audio', {method: 'POST', body: fd});
  if (!res.ok) {
    const err = await res.json();
    msgEl.textContent = 'Chyba: ' + (err.error || res.status);
    return;
  }
  closeAudioModal();
}

function stripVtt(text) {
  return text
    .split('\n')
    .filter(l => !/^WEBVTT/.test(l) && !/^\d{2}:\d{2}/.test(l))
    .map(l => l.replace(/<v [^>]+>/g, '').replace(/<\/v>/g, '').trim())
    .filter((l, i, arr) => l || (arr[i - 1] && arr[i - 1] !== ''))
    .join('\n')
    .trim();
}

function handleImportFile(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    let text = e.target.result;
    if (file.name.endsWith('.vtt')) text = stripVtt(text);
    document.getElementById('import-transcript').value = text;
  };
  reader.readAsText(file, 'utf-8');
  event.target.value = '';
}

async function submitImport() {
  const transcript = document.getElementById('import-transcript').value.trim();
  if (!transcript) {
    document.getElementById('import-msg').textContent = 'Přepis je prázdný.';
    return;
  }
  const label = document.getElementById('import-label')?.value || '';
  const folder = document.getElementById('import-folder')?.value || 'Other';
  const template = document.getElementById('import-template')?.value || '';
  const meeting_date = document.getElementById('import-date')?.value || '';
  const res = await fetch('/import-transcript', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({transcript, label, folder, template, meeting_date}),
  });
  if (!res.ok) {
    const err = await res.json();
    document.getElementById('import-msg').textContent = 'Chyba: ' + (err.error || res.status);
    return;
  }
  document.getElementById('import-modal').style.display = 'none';
  document.getElementById('import-transcript').value = '';
  document.getElementById('import-label').value = '';
  document.getElementById('import-msg').textContent = '';
}
