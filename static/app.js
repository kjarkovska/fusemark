// app.js — ObsiNote frontend logic

let recording = false;
let timerInterval = null;
let timerSeconds = 0;
let jobsPollInterval = null;

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
}

async function stopRecording() {
  const scratch = document.getElementById('scratch')?.value || '';

  const res = await fetch('/stop', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scratch_notes: scratch}),
  });

  if (!res.ok) {
    const err = await res.json();
    alert('Chyba: ' + (err.error || res.status));
    return;
  }

  recording = false;
  setRecorderUI(false);
  stopTimer();
  if (document.getElementById('scratch')) {
    document.getElementById('scratch').value = '';
  }
  refreshJobs();
}

function setRecorderUI(isRecording) {
  const btn = document.getElementById('rec-btn');
  if (!btn) return;
  if (isRecording) {
    btn.textContent = 'Zastavit nahrávání';
    btn.className = 'btn-stop';
    if (document.getElementById('recorder')) {
      document.getElementById('recorder').classList.add('is-recording');
    }
  } else {
    btn.textContent = 'Spustit nahrávání';
    btn.className = 'btn-start';
    if (document.getElementById('recorder')) {
      document.getElementById('recorder').classList.remove('is-recording');
    }
  }
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
    el.innerHTML = '<p style="color:#666; font-size:13px;">Zatím žádné záznamy.</p>';
    return;
  }

  el.innerHTML = jobs.map(renderJob).join('');
}

function renderJob(job) {
  const date = formatLocalDate(job.created_at);
  const progress = progressFromJob(job);
  const isActive = job.status === 'transcribing' || job.status === 'generating';
  const isDeletable = job.status === 'done' || job.status === 'error';

  const errorTitle = (job.status === 'error' && job.error_message && !job.error_message.startsWith('['))
    ? ` title="${esc(job.error_message)}"` : '';
  const pill = `<span class="job-status status-${job.status}"${errorTitle}>${statusLabel(job.status)}</span>`;

  const deleteBtn = isDeletable
    ? `<button class="btn-delete" onclick="deleteJob('${job.id}')" title="Smazat">&#10005;</button>`
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

  const progressBar = isActive
    ? `<div class="job-progress-row">
         <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>
         <span class="progress-pct">${progress}%</span>
       </div>`
    : '';

  const contextField = !isDeletable
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
      ${contextField}
      ${audioDecision}
    </div>`;
}

function progressFromJob(job) {
  if (!job.extra_context) return 0;
  const m = job.extra_context.match(/transcribing:(\d+)%/);
  return m ? parseInt(m[1]) : 0;
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
  }

  if (document.getElementById('jobs-list')) {
    refreshJobs();
    jobsPollInterval = setInterval(refreshJobs, 3000);
  }
});
