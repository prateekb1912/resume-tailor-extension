const DEFAULT_PARSE_WEBHOOK  = 'http://localhost:5678/webhook/resume-parse';
const DEFAULT_TAILOR_WEBHOOK = 'http://localhost:5678/webhook/resume-tailor';
const STORAGE_KEY_PROFILE    = 'resumeProfile';
const STORAGE_KEY_WEBHOOK    = 'webhookUrl';
const TIMEOUT_MS             = 120_000;

let jobData        = null;
let downloadHandler = null;

// ── JD extraction (runs in page context) ─────────────────────────────────────

function extractJobInfo() {
  const host = window.location.hostname;

  function text(selectors) {
    for (const sel of selectors.split(',')) {
      const el = document.querySelector(sel.trim());
      if (el?.innerText?.trim()) return el.innerText.trim();
    }
    return '';
  }

  let title = '', company = '', description = '';

  if (host.includes('linkedin.com')) {
    title       = text('.job-details-jobs-unified-top-card__job-title h1, .jobs-unified-top-card__job-title h1');
    company     = text('.job-details-jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name');
    description = text('.jobs-description__content, .job-view-layout, #job-details');
  } else if (host.includes('greenhouse.io')) {
    title       = text('h1.app-title, h1');
    company     = text('.company-name, .custom-header h1');
    description = text('#content, .job-post, .application-form');
  } else if (host.includes('lever.co')) {
    title       = text('.posting-headline h2, h2.posting-name');
    company     = text('.posting-headline .team, .posting-category');
    description = text('.content, .posting-content, .section-wrapper');
  } else if (host.includes('indeed.com')) {
    title       = text('[data-testid="jobsearch-JobInfoHeader-title"], h1.jobsearch-JobInfoHeader-title');
    company     = text('[data-testid="inlineHeader-companyName"], .jobsearch-InlineCompanyRating');
    description = text('#jobDescriptionText, .jobsearch-jobDescriptionText');
  } else if (host.includes('glassdoor.com')) {
    title       = text('[data-test="job-title"], .JobDetails_jobTitle__Rw_gn');
    company     = text('[data-test="employer-name"], .JobDetails_companyName__t9aP0');
    description = text('[data-test="description"], .JobDetails_jobDescription__uW_fK');
  } else if (host.includes('myworkdayjobs.com') || host.includes('workday.com')) {
    title       = text('[data-automation-id="jobPostingHeader"]');
    description = text('[data-automation-id="jobPostingDescription"]');
  } else if (host.includes('smartrecruiters.com')) {
    title       = text('.job-title, h1');
    company     = text('.hiring-company-name, .company-name');
    description = text('.job-description, .section-wrapper');
  } else if (host.includes('bamboohr.com')) {
    title       = text('.BambooHR-ATS-Jobs-Item h2, h1');
    description = text('#content, .BambooHR-ATS-body');
  } else if (host.includes('ashbyhq.com') || host.includes('jobs.ashbyhq.com')) {
    title       = text('h1');
    description = text('[class*="Description"], [class*="JobPosting"]');
  }

  if (!description) description = document.body.innerText.slice(0, 10000);
  if (!title)       title       = document.title;

  return {
    title:       title.replace(/\s+/g, ' ').trim(),
    company:     company.replace(/\s+/g, ' ').trim(),
    description: description.replace(/\s+/g, ' ').trim(),
    url:         window.location.href,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setParseStatus(msg, type = '') {
  const el = document.getElementById('parse-status');
  el.textContent = msg;
  el.className = `parse-status ${type}`;
}

function setTailorStatus(msg, type = '') {
  const el = document.getElementById('tailor-status');
  el.textContent = msg;
  el.className = `tailor-status ${type}`;
}

function base64ToBlob(b64, mime) {
  const bytes = atob(b64);
  const arr = new Uint8Array(bytes.length);
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
  return new Blob([arr], { type: mime });
}

function profileSummary(profile) {
  const parts = [];
  if (profile.experience?.length) parts.push(`${profile.experience.length} job${profile.experience.length > 1 ? 's' : ''}`);
  if (profile.skills?.length)     parts.push(`${profile.skills.length} skills`);
  if (profile.education?.length)  parts.push(profile.education[0].degree || profile.education[0].school || '');
  return parts.filter(Boolean).join(' · ');
}

// ── Resume profile card ───────────────────────────────────────────────────────

function showLoadedState(profile) {
  document.getElementById('resume-empty').style.display  = 'none';
  document.getElementById('resume-loaded').classList.add('visible');
  document.getElementById('resume-name').textContent  = profile.name || 'Resume loaded';
  document.getElementById('resume-stats').textContent = profileSummary(profile);
}

function showEmptyState() {
  document.getElementById('resume-empty').style.display  = '';
  document.getElementById('resume-loaded').classList.remove('visible');
}

// ── Parse resume (one-time) ───────────────────────────────────────────────────

async function parseAndSave(file) {
  const parseWebhook = DEFAULT_PARSE_WEBHOOK;

  const form = new FormData();
  form.append('resume', file, file.name);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const response = await fetch(parseWebhook, {
    method: 'POST',
    signal: controller.signal,
    body:   form,
  });
  clearTimeout(timer);

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`n8n returned ${response.status}${body ? ': ' + body.slice(0, 120) : ''}`);
  }

  const profile = await response.json();

  // Persist to chrome.storage
  await chrome.storage.local.set({
    [STORAGE_KEY_PROFILE]: { ...profile, _parsedAt: new Date().toISOString() },
  });

  return profile;
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  // File picker
  const filePickBtn = document.getElementById('file-pick-btn');
  const fileInput   = document.getElementById('resume-file');
  const fileNameEl  = document.getElementById('file-name');
  const parseBtn    = document.getElementById('parse-btn');

  filePickBtn.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) {
      fileNameEl.textContent = file.name;
      fileNameEl.className = 'file-name selected';
      parseBtn.disabled = false;
    }
  });

  parseBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    if (!file) return;

    parseBtn.disabled = true;
    parseBtn.textContent = 'Parsing…';
    setParseStatus('Sending to n8n…');

    try {
      const profile = await parseAndSave(file);
      setParseStatus('Saved!', 'success');
      showLoadedState(profile);
      maybeEnableTailorBtn();
    } catch (err) {
      const msg = err.name === 'AbortError' ? 'Timed out.' : err.message;
      setParseStatus(`Error: ${msg}`, 'error');
      parseBtn.disabled = false;
      parseBtn.textContent = 'Parse & Save Resume';
    }
  });

  // "Update" link resets to empty state
  document.getElementById('resume-update').addEventListener('click', () => {
    chrome.storage.local.remove(STORAGE_KEY_PROFILE);
    showEmptyState();
    parseBtn.textContent = 'Parse & Save Resume';
    setParseStatus('');
    document.getElementById('tailor-btn').disabled = true;
  });

  // Load stored webhook URL
  const stored = await chrome.storage.local.get([STORAGE_KEY_WEBHOOK, STORAGE_KEY_PROFILE]);
  document.getElementById('webhook-url').value = stored[STORAGE_KEY_WEBHOOK] || DEFAULT_TAILOR_WEBHOOK;
  document.getElementById('webhook-url').addEventListener('change', (e) => {
    chrome.storage.local.set({ [STORAGE_KEY_WEBHOOK]: e.target.value.trim() });
  });

  // Show stored profile if it exists
  if (stored[STORAGE_KEY_PROFILE]) {
    showLoadedState(stored[STORAGE_KEY_PROFILE]);
  }

  // Extract JD from active tab
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func:   extractJobInfo,
    });

    jobData = result;
    document.getElementById('jd-title').textContent   = jobData.title   || 'Unknown position';
    document.getElementById('jd-company').textContent = jobData.company || '';
    document.getElementById('jd-preview').textContent = jobData.description;

    const chars = jobData.description.length;
    document.getElementById('jd-chars').textContent =
      chars >= 100 ? `${chars.toLocaleString()} chars extracted` : '';

    if (chars < 100) setTailorStatus('Very little text found — open a job posting first.', 'error');

  } catch (err) {
    document.getElementById('jd-title').textContent = 'Could not read page';
    setTailorStatus(`Extraction failed: ${err.message}`, 'error');
  }

  maybeEnableTailorBtn();
}

function maybeEnableTailorBtn() {
  chrome.storage.local.get([STORAGE_KEY_PROFILE, 'tailorResult'], (stored) => {
    const hasProfile = !!stored[STORAGE_KEY_PROFILE];
    const hasJD      = jobData && jobData.description.length >= 100;
    const tr         = stored.tailorResult;

    // Treat pending as stale if it's been running for over 3 minutes
    const isStuckPending = tr?.status === 'pending' &&
      tr.startedAt && (Date.now() - tr.startedAt) > 180_000;

    if (isStuckPending) {
      chrome.storage.local.remove('tailorResult');
    }

    const pending = tr?.status === 'pending' && !isStuckPending;
    const btn     = document.getElementById('tailor-btn');
    btn.disabled  = !(hasProfile && hasJD) || pending;

    if (pending) {
      btn.classList.add('loading');
      setTailorStatus('Processing in background…');
    } else if (tr?.status === 'done') {
      applyResult(tr.result);
    } else if (tr?.status === 'error') {
      setTailorStatus(`Error: ${tr.error}`, 'error');
      btn.textContent = 'Retry';
      chrome.storage.local.remove('tailorResult');
    } else if (hasProfile && hasJD) {
      setTailorStatus('Ready to tailor.');
    }
  });
}

function applyResult(result) {
  console.log('[resume-tailor] applyResult received:', JSON.stringify(result).slice(0, 200));

  const btn   = document.getElementById('tailor-btn');
  const dlBtn = document.getElementById('download-btn');

  btn.textContent = 'Tailor Again';
  btn.classList.remove('loading');
  btn.disabled = false;

  if (downloadHandler) dlBtn.removeEventListener('click', downloadHandler);
  downloadHandler = null;

  if (result?.downloadUrl) {
    downloadHandler = () => chrome.tabs.create({ url: result.downloadUrl });
  } else if (result?.fileData) {
    const mime     = result.mimeType || 'application/pdf';
    const ext      = mime.includes('pdf') ? 'pdf' : mime.includes('html') ? 'html' : 'docx';
    const fileName = result.fileName || `resume_tailored.${ext}`;
    downloadHandler = () => {
      const blob = base64ToBlob(result.fileData, mime);
      const url  = URL.createObjectURL(blob);
      chrome.downloads.download({ url, filename: fileName });
    };
  }

  if (downloadHandler) {
    setTailorStatus('Resume tailored — ready to download.', 'success');
    dlBtn.classList.add('visible');
    dlBtn.addEventListener('click', downloadHandler);
  } else {
    console.warn('[resume-tailor] no downloadable field in result:', result);
    setTailorStatus('Done, but no file returned. Check the service worker console.', 'error');
  }
}

// ── Tailor button ─────────────────────────────────────────────────────────────

document.getElementById('tailor-btn').addEventListener('click', async () => {
  if (!jobData) return;

  const stored = await chrome.storage.local.get(STORAGE_KEY_PROFILE);
  const profile = stored[STORAGE_KEY_PROFILE];
  if (!profile) {
    setTailorStatus('No resume profile found. Parse your resume first.', 'error');
    return;
  }

  const btn        = document.getElementById('tailor-btn');
  const dlBtn      = document.getElementById('download-btn');
  const webhookUrl = document.getElementById('webhook-url').value.trim() || DEFAULT_TAILOR_WEBHOOK;

  btn.disabled = true;
  btn.classList.add('loading');
  dlBtn.classList.remove('visible');
  chrome.storage.local.remove('tailorResult');
  setTailorStatus('Running in background — you can close this popup.');

  // Delegate to background service worker so fetch survives popup close
  chrome.runtime.sendMessage({
    action:     'startTailor',
    webhookUrl,
    body: {
      resumeProfile:  profile,
      jobTitle:       jobData.title,
      company:        jobData.company,
      jobDescription: jobData.description,
      jobUrl:         jobData.url,
      timestamp:      new Date().toISOString(),
    },
  });

  // Poll storage every 3s while popup is open
  const poll = setInterval(async () => {
    const s = await chrome.storage.local.get('tailorResult');
    if (s.tailorResult?.status === 'done') {
      clearInterval(poll);
      applyResult(s.tailorResult.result);
    } else if (s.tailorResult?.status === 'error') {
      clearInterval(poll);
      setTailorStatus(`Error: ${s.tailorResult.error}`, 'error');
      btn.classList.remove('loading');
      btn.textContent = 'Retry';
      btn.disabled = false;
      chrome.storage.local.remove('tailorResult');
    }
  }, 3000);
});

init();
