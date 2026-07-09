const DEFAULT_PARSE_WEBHOOK  = 'http://localhost:5678/webhook/resume-parse';
const DEFAULT_TAILOR_WEBHOOK = 'http://localhost:5678/webhook/resume-tailor';
const STORAGE_KEY_PROFILE    = 'resumeProfile';
const STORAGE_KEY_WEBHOOK    = 'webhookUrl';
const TIMEOUT_MS             = 120_000;

let jobData         = null;
let downloadHandler = null;
let siteKey         = null;

// Per-site storage key so each job site keeps its own tailor session
// instead of overwriting a single shared result.
function tailorKey() {
  return siteKey ? `tailorResult:${siteKey}` : 'tailorResult';
}

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

  // ── Generic fallbacks for title/company on unhandled sites ──
  // 1. schema.org JobPosting JSON-LD — embedded by most ATS/career pages.
  function fromJsonLd() {
    for (const el of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const data = JSON.parse(el.textContent);
        const nodes = Array.isArray(data) ? data : (data['@graph'] || [data]);
        for (const node of nodes) {
          const t = node && node['@type'];
          const isJob = t === 'JobPosting' || (Array.isArray(t) && t.includes('JobPosting'));
          if (isJob) {
            const org = node.hiringOrganization;
            return { title: node.title || '', company: (typeof org === 'string' ? org : org?.name) || '' };
          }
        }
      } catch { /* malformed JSON-LD — skip */ }
    }
    return null;
  }

  // 2. Split a page title like "Senior Software Engineer | Okta" into parts.
  function fromDocTitle() {
    const parts = (document.title || '').split(/\s+[|–—\-]\s+/);
    return parts.length >= 2
      ? { title: parts[0].trim(), company: parts[parts.length - 1].trim() }
      : { title: (document.title || '').trim(), company: '' };
  }

  const ld = fromJsonLd();
  if (ld) {
    if (!title)   title   = ld.title;
    if (!company) company = ld.company;
  }
  if (!company) company = document.querySelector('meta[property="og:site_name"]')?.content?.trim() || company;
  const dt = fromDocTitle();
  if (!title)   title   = dt.title;
  if (!company) company = dt.company;

  // Strip a trailing "| Company" / "- Company" the page title often glues on.
  if (company && title) {
    const esc = company.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    title = title.replace(new RegExp('\\s*[|\\u2013\\u2014\\-]\\s*' + esc + '\\s*$', 'i'), '').trim();
  }

  return {
    title:       title.replace(/\s+/g, ' ').trim(),
    company:     company.replace(/\s+/g, ' ').trim(),
    description: description.replace(/\s+/g, ' ').trim(),
    url:         window.location.href,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// Keep the char-count label in sync with whatever's in the editable JD field.
function syncJdChars() {
  const chars = (jobData?.description || '').length;
  document.getElementById('jd-chars').textContent =
    chars >= 100 ? `${chars.toLocaleString()} chars` : (chars ? `${chars} chars — looks short` : '');
}

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

// ── Match score (client-side heuristic) ───────────────────────────────────────
//
// Frequency-ranking the JD just surfaces boilerplate ("jobs", "experience",
// "team"). Instead we only ever consider terms that are recognized *skills* —
// the union of a built-in tech vocabulary and the user's own resume skills.
// Everything else in the page text is ignored, so generic words can't leak in.

// Built-in skill/technology vocabulary. Multi-word entries are matched as phrases.
const SKILL_VOCAB = [
  'javascript','typescript','python','java','c++','c#','c','go','golang','rust','ruby','php','scala','kotlin',
  'swift','objective-c','perl','r','matlab','dart','elixir','haskell','lua','bash','shell','powershell','sql',
  'html','css','sass','scss','tailwind','bootstrap',
  'react','react native','redux','next.js','nextjs','vue','vuejs','angular','svelte','jquery','ember','backbone',
  'node.js','nodejs','express','nestjs','deno','bun',
  'django','flask','fastapi','rails','ruby on rails','spring','spring boot','laravel','symfony','asp.net','.net','dotnet',
  'graphql','rest','grpc','websocket','soap','microservices','serverless','api',
  'postgresql','postgres','mysql','sqlite','mariadb','oracle','sql server','mongodb','dynamodb','cassandra','redis',
  'elasticsearch','neo4j','couchdb','firebase','supabase','snowflake','bigquery','redshift','databricks',
  'aws','amazon web services','azure','gcp','google cloud','heroku','digitalocean','cloudflare','vercel','netlify',
  'docker','kubernetes','k8s','terraform','ansible','pulumi','helm','vagrant','openshift','nomad',
  'jenkins','github actions','gitlab ci','circleci','travis','argocd','ci/cd','cicd',
  'git','github','gitlab','bitbucket','svn','mercurial',
  'kafka','rabbitmq','sqs','pubsub','nats','airflow','spark','hadoop','flink','dbt','etl',
  'linux','unix','windows','macos','nginx','apache','prometheus','grafana','datadog','splunk','sentry','elk',
  'pytorch','tensorflow','keras','scikit-learn','sklearn','pandas','numpy','opencv','huggingface','langchain',
  'machine learning','deep learning','nlp','computer vision','llm','generative ai','data science','data engineering',
  'tableau','power bi','looker','dbt',
  'jest','mocha','cypress','playwright','selenium','pytest','junit','vitest','testing','tdd',
  'figma','sketch','adobe xd','photoshop','illustrator',
  'jira','confluence','agile','scrum','kanban','devops','sre','observability',
  'webpack','vite','babel','rollup','esbuild','turbopack',
  'oauth','jwt','saml','sso','rbac','encryption','security',
];

const STOPWORDS = new Set(('a an the and or but for nor so yet of to in on at by with from as is are was ' +
  'were be been being have has had do does did will would shall should can could may might must this that ' +
  'these those it its their our your you we they he she them his her not no will able strong years').split(/\s+/));

// Normalize common synonyms so JS == JavaScript, k8s == kubernetes, etc.
const SYNONYMS = {
  js: 'javascript', ts: 'typescript', py: 'python', golang: 'go', k8s: 'kubernetes',
  postgres: 'postgresql', nextjs: 'next.js', nodejs: 'node.js', vuejs: 'vue',
  sklearn: 'scikit-learn', cicd: 'ci/cd', gcp: 'google cloud', dotnet: '.net', sre: 'devops',
};
const canon = (t) => SYNONYMS[t] || t;

const SKILL_SET    = new Set(SKILL_VOCAB.map(canon));
const SKILL_PHRASES = SKILL_VOCAB.filter(s => s.includes(' '));

function tokenize(text) {
  return (text || '')
    .toLowerCase()
    .replace(/[^a-z0-9+#./\s-]/g, ' ')
    .split(/\s+/)
    .map(w => w.replace(/^[.\-]+|[.\-]+$/g, ''))
    .filter(Boolean);
}

// Extract the set of recognized skills mentioned in a blob of text.
function skillsIn(text, extraVocab) {
  const lower = (text || '').toLowerCase();
  const found = new Set();

  // Multi-word skills: substring match on the raw text.
  for (const phrase of SKILL_PHRASES) {
    if (lower.includes(phrase)) found.add(canon(phrase));
  }
  // Single-word skills: token match against the known set.
  for (const tok of tokenize(text)) {
    const c = canon(tok);
    if (SKILL_SET.has(c) || extraVocab.has(c)) found.add(c);
  }
  return found;
}

// The resume's declared skills become part of the recognized vocabulary, so a
// JD term the user actually lists always counts even if it's niche.
function resumeSkillVocab(profile) {
  const vocab = new Set();
  for (const s of (profile.skills || [])) {
    const c = canon(String(s).toLowerCase().trim());
    if (c && !STOPWORDS.has(c)) vocab.add(c);
  }
  return vocab;
}

// Returns { score: 0-100, present: [...], missing: [...] }
function computeMatch(profile, jd) {
  const resumeText = [
    profile.summary,
    (profile.skills || []).join(' '),
    (profile.certifications || []).join(' '),
    (profile.experience || []).flatMap(e => [e.title, ...(e.bullets || [])]).join(' '),
    (profile.projects || []).flatMap(p => [p.name, p.description, ...(p.bullets || [])]).join(' '),
  ].join(' ');

  const resumeVocab  = resumeSkillVocab(profile);
  const resumeSkills = skillsIn(resumeText, resumeVocab);
  const jdSkills     = skillsIn(jd.description, resumeVocab);

  if (!jdSkills.size) return { score: 0, present: [], missing: [] };

  const present = [...jdSkills].filter(s => resumeSkills.has(s));
  const missing = [...jdSkills].filter(s => !resumeSkills.has(s));

  // Coverage of the role's required skills, lightly curved.
  const coverage = present.length / jdSkills.size;
  const score = Math.round(Math.min(100, Math.pow(coverage, 0.85) * 100));

  return { score, present, missing: missing.slice(0, 6) };
}

function renderMatch(profile) {
  const box = document.getElementById('match');
  if (!profile || !jobData || jobData.description.length < 100) {
    box.classList.remove('visible');
    return;
  }

  const { score, present, missing } = computeMatch(profile, jobData);

  // No recognized skills found (e.g. JD fell back to whole-page noise) — hide
  // rather than show a misleading 0%.
  if (!present.length && !missing.length) {
    box.classList.remove('visible');
    return;
  }

  const color = score >= 70 ? '#16a34a' : score >= 45 ? '#d97706' : '#dc2626';

  document.getElementById('match-pct').textContent   = `${score}%`;
  document.getElementById('match-pct').style.color   = color;
  document.getElementById('match-fill').style.width  = `${score}%`;
  document.getElementById('match-fill').style.background = color;
  document.getElementById('match-note').textContent = missing.length
    ? `Missing skills: ${missing.join(', ')}`
    : `Covers all ${present.length} detected skills.`;

  box.classList.add('visible');
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

  // Let the user manually fix/paste the JD if extraction came up short.
  document.getElementById('jd-preview').addEventListener('input', (e) => {
    if (!jobData) jobData = { title: '', company: '', description: '', url: '' };
    jobData.description = e.target.value.trim();
    syncJdChars();
    maybeEnableTailorBtn();
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
    try { siteKey = new URL(jobData.url).hostname; } catch { siteKey = null; }
    document.getElementById('jd-title').textContent   = jobData.title   || 'Unknown position';
    document.getElementById('jd-company').textContent = jobData.company || '';
    document.getElementById('jd-preview').value        = jobData.description;
    syncJdChars();

    if (jobData.description.length < 100) {
      setTailorStatus('Very little text found — edit or paste the job description above.', 'error');
    }

  } catch (err) {
    document.getElementById('jd-title').textContent = 'Could not read page';
    setTailorStatus(`Extraction failed: ${err.message}`, 'error');
  }

  maybeEnableTailorBtn();
}

function maybeEnableTailorBtn() {
  chrome.storage.local.get([STORAGE_KEY_PROFILE, tailorKey()], (stored) => {
    const hasProfile = !!stored[STORAGE_KEY_PROFILE];
    const hasJD      = jobData && jobData.description.length >= 100;
    const tr         = stored[tailorKey()];

    renderMatch(stored[STORAGE_KEY_PROFILE]);

    // Treat pending as stale if it's been running for over 3 minutes
    const isStuckPending = tr?.status === 'pending' &&
      tr.startedAt && (Date.now() - tr.startedAt) > 180_000;

    if (isStuckPending) {
      chrome.storage.local.remove(tailorKey());
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
      chrome.storage.local.remove(tailorKey());
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
  chrome.storage.local.remove(tailorKey());
  setTailorStatus('Running in background — you can close this popup.');

  // Delegate to background service worker so fetch survives popup close
  chrome.runtime.sendMessage({
    action:     'startTailor',
    webhookUrl,
    resultKey:  tailorKey(),
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
  const key = tailorKey();
  const poll = setInterval(async () => {
    const s = await chrome.storage.local.get(key);
    if (s[key]?.status === 'done') {
      clearInterval(poll);
      applyResult(s[key].result);
    } else if (s[key]?.status === 'error') {
      clearInterval(poll);
      setTailorStatus(`Error: ${s[key].error}`, 'error');
      btn.classList.remove('loading');
      btn.textContent = 'Retry';
      btn.disabled = false;
      chrome.storage.local.remove(key);
    }
  }, 3000);
});

init();
