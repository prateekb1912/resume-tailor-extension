const DEFAULT_SERVER = 'http://localhost:8000';
const STORAGE_KEY_PROFILE = 'resumeProfile';
const STORAGE_KEY_SERVER = 'serverUrl';
const STORAGE_KEY_EMAIL = 'userEmail';
const STORAGE_KEY_PRINT = 'printProfile';
const TIMEOUT_MS = 120_000;

const parseUrl = (base) => `${(base || DEFAULT_SERVER).replace(/\/$/, '')}/resume/parse`;
const tailorUrl = (base) => `${(base || DEFAULT_SERVER).replace(/\/$/, '')}/resume/tailor`;

let jobData = null;
let downloadHandler = null;
let siteKey = null;

function tailorKey() {
  return siteKey ? `tailorResult:${siteKey}` : 'tailorResult';
}

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
    // LinkedIn ships two very different layouts — authenticated (…unified-top-card…,
    // #job-details) and the logged-out guest view (topcard…, show-more-less-html).
    // List both, most-specific first; #job-details is the most stable anchor.
    title = text([
      '.job-details-jobs-unified-top-card__job-title h1',
      '.job-details-jobs-unified-top-card__job-title',
      '.jobs-unified-top-card__job-title h1',
      '.top-card-layout__title',
      '.topcard__title',
    ].join(','));
    company = text([
      '.job-details-jobs-unified-top-card__company-name a',
      '.job-details-jobs-unified-top-card__company-name',
      '.jobs-unified-top-card__company-name',
      '.topcard__org-name-link',
      '.top-card-layout__second-subline a',
    ].join(','));
    description = text([
      '#job-details',
      '.jobs-description__content .jobs-box__html-content',
      '.jobs-description-content__text',
      '.jobs-description__content',
      '.show-more-less-html__markup',
      '.description__text',
    ].join(','));
  } else if (host.includes('greenhouse.io')) {
    title = text('h1.app-title, h1');
    company = text('.company-name, .custom-header h1');
    description = text('#content, .job-post, .application-form');
  } else if (host.includes('lever.co')) {
    title = text('.posting-headline h2, h2.posting-name');
    company = text('.posting-headline .team, .posting-category');
    description = text('.content, .posting-content, .section-wrapper');
  } else if (host.includes('indeed.com')) {
    title = text('[data-testid="jobsearch-JobInfoHeader-title"], h1.jobsearch-JobInfoHeader-title');
    company = text('[data-testid="inlineHeader-companyName"], .jobsearch-InlineCompanyRating');
    description = text('#jobDescriptionText, .jobsearch-jobDescriptionText');
  } else if (host.includes('glassdoor.com')) {
    title = text('[data-test="job-title"], .JobDetails_jobTitle__Rw_gn');
    company = text('[data-test="employer-name"], .JobDetails_companyName__t9aP0');
    description = text('[data-test="description"], .JobDetails_jobDescription__uW_fK');
  } else if (host.includes('myworkdayjobs.com') || host.includes('workday.com')) {
    title = text('[data-automation-id="jobPostingHeader"]');
    description = text('[data-automation-id="jobPostingDescription"]');
  } else if (host.includes('smartrecruiters.com')) {
    title = text('.job-title, h1');
    company = text('.hiring-company-name, .company-name');
    description = text('.job-description, .section-wrapper');
  } else if (host.includes('bamboohr.com')) {
    title = text('.BambooHR-ATS-Jobs-Item h2, h1');
    description = text('#content, .BambooHR-ATS-body');
  } else if (host.includes('ashbyhq.com') || host.includes('jobs.ashbyhq.com')) {
    title = text('h1');
    description = text('[class*="Description"], [class*="JobPosting"]');
  }

  if (!description) description = document.body.innerText.slice(0, 10000);

  // ── Generic fallbacks for title/company ──
  // Layered by reliability; each site uses whatever structured data it exposes,
  // falling back to document.title only as a last resort. All synchronous — no
  // network, no LLM.
  const meta = (sel) => document.querySelector(sel)?.getAttribute('content')?.trim() || '';

  // 1. schema.org JobPosting JSON-LD — the SEO-driven gold standard (career
  //    pages, Greenhouse boards, Indeed, Glassdoor).
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
    return {};
  }

  // 2. Microdata — same schema, inline itemprop encoding. Only trust it inside a
  //    JobPosting scope so unrelated microdata can't leak in.
  function fromMicrodata() {
    const scope = document.querySelector('[itemtype*="JobPosting"]');
    if (!scope) return {};
    const q = (sel) => scope.querySelector(sel)?.textContent?.trim().replace(/\s+/g, ' ') || '';
    return {
      title: q('[itemprop="title"]'),
      company: q('[itemprop="hiringOrganization"] [itemprop="name"]') || q('[itemprop="hiringOrganization"]'),
    };
  }

  // 3. Open Graph / social meta. LinkedIn's public view is a special, very
  //    parseable case: "<Company> hiring <Title> in <Location> | LinkedIn".
  function fromOg() {
    const ogTitle = meta('meta[property="og:title"], meta[name="og:title"], meta[name="title"]');
    const li = ogTitle.match(/^(.+?)\s+hiring\s+(.+?)\s+in\s+.+$/i);
    if (li) return { title: li[2].trim(), company: li[1].trim() };

    let t = ogTitle;
    let c = meta('meta[property="og:site_name"]');
    const m = ogTitle.match(/^(.*?)\s+(?:at|@|[|–—-])\s+(.+)$/i);   // "<Title> at <Company>"
    if (m) {
      t = m[1].trim();
      if (!c) c = m[2].trim();
    }
    return { title: t, company: c };
  }

  // 4. Company slug from a known ATS URL — the most reliable company source when
  //    present (the SPA sites that lack JSON-LD still put company in the URL).
  function fromUrl() {
    const h = window.location.hostname;
    const seg = window.location.pathname.split('/').filter(Boolean);
    const prettify = (s) => s.replace(/[-_]+/g, ' ').replace(/\b\w/g, (ch) => ch.toUpperCase()).trim();
    let slug = '';
    if (h.includes('greenhouse.io') || h.includes('lever.co') || h.includes('ashbyhq.com') || h.includes('smartrecruiters.com')) {
      slug = seg[0] || '';
    } else if (h.includes('myworkdayjobs.com') || h.endsWith('.bamboohr.com')) {
      slug = h.split('.')[0];
    }
    return slug ? prettify(slug) : '';
  }

  // 5. The most prominent heading — usually the job title.
  function fromHeading() {
    return document.querySelector('h1')?.innerText?.trim().replace(/\s+/g, ' ') || '';
  }

  // 6. Split a page title like "Senior Software Engineer | Okta" (last resort).
  function fromDocTitle() {
    const parts = (document.title || '').split(/\s+[|–—-]\s+/);
    return parts.length >= 2
      ? { title: parts[0].trim(), company: parts[parts.length - 1].trim() }
      : { title: (document.title || '').trim(), company: '' };
  }

  const ld = fromJsonLd();
  const micro = fromMicrodata();
  const og = fromOg();
  const dt = fromDocTitle();

  if (!title) title = ld.title || micro.title || og.title || fromHeading() || dt.title;
  if (!company) company = ld.company || micro.company || og.company || fromUrl() || dt.company;

  // Strip a trailing "| Company" / "- Company" the page title often glues on.
  if (company && title) {
    const esc = company.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    title = title.replace(new RegExp('\\s*[|\\u2013\\u2014\\-]\\s*' + esc + '\\s*$', 'i'), '').trim();
  }

  return {
    title: title.replace(/\s+/g, ' ').trim(),
    company: company.replace(/\s+/g, ' ').trim(),
    description: description.replace(/\s+/g, ' ').trim(),
    url: window.location.href,
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

function profileSummary(profile) {
  const parts = [];
  if (profile.experience?.length) parts.push(`${profile.experience.length} job${profile.experience.length > 1 ? 's' : ''}`);
  if (profile.skills?.length) parts.push(`${profile.skills.length} skills`);
  if (profile.education?.length) parts.push(profile.education[0].degree || profile.education[0].school || '');
  return parts.filter(Boolean).join(' · ');
}

// ── Fit assessment (from server) ──────────────────────────────────────────────
//
// The server returns a real fit assessment ({ match_score, reason,
// missing_skills }) alongside the tailored profile, so we render that instead of
// guessing a match client-side. The box only appears once a tailor run completes.

function renderFit(fit) {
  const box = document.getElementById('match');
  if (!fit) {
    box.classList.remove('visible');
    return;
  }

  const score = Math.max(0, Math.min(100, fit.match_score ?? 0));
  const color = score >= 70 ? '#16a34a' : score >= 45 ? '#d97706' : '#dc2626';

  box.querySelector('.match-label').textContent = 'Fit score';
  document.getElementById('match-pct').textContent = `${score}%`;
  document.getElementById('match-pct').style.color = color;
  document.getElementById('match-fill').style.width = `${score}%`;
  document.getElementById('match-fill').style.background = color;

  const parts = [];
  if (fit.reason) parts.push(fit.reason);
  if (fit.missing_skills?.length) parts.push(`Missing: ${fit.missing_skills.join(', ')}`);
  document.getElementById('match-note').textContent = parts.join(' · ');

  box.classList.add('visible');
}

// ── Resume profile card ───────────────────────────────────────────────────────

function showLoadedState(profile) {
  document.getElementById('resume-empty').style.display = 'none';
  document.getElementById('resume-loaded').classList.add('visible');
  document.getElementById('resume-name').textContent = profile.name || 'Resume loaded';
  document.getElementById('resume-stats').textContent = profileSummary(profile);
}

function showEmptyState() {
  document.getElementById('resume-empty').style.display = '';
  document.getElementById('resume-loaded').classList.remove('visible');
}

// ── Parse resume (one-time) ───────────────────────────────────────────────────

async function parseAndSave(file, email, serverBase) {
  const form = new FormData();
  form.append('resume', file, file.name);
  form.append('email', email);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  const response = await fetch(parseUrl(serverBase), {
    method: 'POST',
    signal: controller.signal,
    body: form,
  });
  clearTimeout(timer);

  if (!response.ok) {
    const body = await response.text().catch(() => '');
    throw new Error(`Server returned ${response.status}${body ? ': ' + body.slice(0, 120) : ''}`);
  }

  // Server wraps the profile as { data, name, email } — unwrap to the flat
  // profile the rest of the popup (and the PDF builder) expects.
  const envelope = await response.json();
  const profile = { ...envelope.data, email: envelope.email || email };

  await chrome.storage.local.set({
    [STORAGE_KEY_PROFILE]: { ...profile, _parsedAt: new Date().toISOString() },
  });

  return profile;
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  // File picker + account fields
  const filePickBtn = document.getElementById('file-pick-btn');
  const fileInput = document.getElementById('resume-file');
  const fileNameEl = document.getElementById('file-name');
  const parseBtn = document.getElementById('parse-btn');
  const emailInput = document.getElementById('user-email');
  const serverInput = document.getElementById('server-url');

  // Parsing needs both a file and an email — the server keys the profile on email.
  const syncParseBtn = () => {
    parseBtn.disabled = !(fileInput.files[0] && emailInput.value.trim());
  };

  filePickBtn.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) {
      fileNameEl.textContent = file.name;
      fileNameEl.className = 'file-name selected';
    }
    syncParseBtn();
  });

  parseBtn.addEventListener('click', async () => {
    const file = fileInput.files[0];
    const email = emailInput.value.trim();
    const serverBase = serverInput.value.trim() || DEFAULT_SERVER;
    if (!file || !email) return;

    parseBtn.disabled = true;
    parseBtn.textContent = 'Parsing…';
    setParseStatus('Parsing resume…');

    try {
      const profile = await parseAndSave(file, email, serverBase);
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

  // Let the user manually fix/paste any field if extraction came up short.
  const ensureJobData = () => (jobData ??= { title: '', company: '', description: '', url: '' });

  document.getElementById('jd-preview').addEventListener('input', (e) => {
    ensureJobData().description = e.target.value.trim();
    syncJdChars();
    maybeEnableTailorBtn();
  });

  document.getElementById('jd-title').addEventListener('input', (e) => {
    ensureJobData().title = e.target.value.trim();
  });

  document.getElementById('jd-company').addEventListener('input', (e) => {
    ensureJobData().company = e.target.value.trim();
  });

  // Load stored server URL + email
  const stored = await chrome.storage.local.get([STORAGE_KEY_SERVER, STORAGE_KEY_EMAIL, STORAGE_KEY_PROFILE]);
  serverInput.value = stored[STORAGE_KEY_SERVER] || DEFAULT_SERVER;
  serverInput.addEventListener('change', (e) => {
    chrome.storage.local.set({ [STORAGE_KEY_SERVER]: e.target.value.trim() });
  });

  emailInput.value = stored[STORAGE_KEY_EMAIL] || stored[STORAGE_KEY_PROFILE]?.email || '';
  emailInput.addEventListener('input', () => {
    chrome.storage.local.set({ [STORAGE_KEY_EMAIL]: emailInput.value.trim() });
    syncParseBtn();
  });
  syncParseBtn();

  // Show stored profile if it exists
  if (stored[STORAGE_KEY_PROFILE]) {
    showLoadedState(stored[STORAGE_KEY_PROFILE]);
  }

  // Extract JD from active tab
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractJobInfo,
    });

    jobData = result;
    try { siteKey = new URL(jobData.url).hostname; } catch { siteKey = null; }
    document.getElementById('jd-title').value = jobData.title || '';
    document.getElementById('jd-company').value = jobData.company || '';
    document.getElementById('jd-preview').value = jobData.description;
    syncJdChars();

    if (jobData.description.length < 100) {
      setTailorStatus('Very little text found — edit or paste the job description above.', 'error');
    }

  } catch (err) {
    document.getElementById('jd-title').placeholder = 'Enter job title manually';
    setTailorStatus(`Couldn't read the page — enter the details manually. (${err.message})`, 'error');
  }

  maybeEnableTailorBtn();
}

function maybeEnableTailorBtn() {
  chrome.storage.local.get([STORAGE_KEY_PROFILE, tailorKey()], (stored) => {
    const hasProfile = !!stored[STORAGE_KEY_PROFILE];
    const hasJD = jobData && jobData.description.length >= 100;
    const tr = stored[tailorKey()];

    // Treat pending as stale if it's been running for over 3 minutes
    const isStuckPending = tr?.status === 'pending' &&
      tr.startedAt && (Date.now() - tr.startedAt) > 180_000;

    if (isStuckPending) {
      chrome.storage.local.remove(tailorKey());
    }

    const pending = tr?.status === 'pending' && !isStuckPending;
    const btn = document.getElementById('tailor-btn');
    btn.disabled = !(hasProfile && hasJD) || pending;

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
  const btn = document.getElementById('tailor-btn');
  const dlBtn = document.getElementById('download-btn');

  btn.textContent = 'Tailor Again';
  btn.classList.remove('loading');
  btn.disabled = false;

  // Server returns { profile: <tailored>, fit: { match_score, reason, missing_skills } }
  const tailored = result?.profile;
  const fit = result?.fit;

  renderFit(fit);

  if (downloadHandler) dlBtn.removeEventListener('click', downloadHandler);
  downloadHandler = null;

  if (tailored) {
    // Open the tailored profile in a dedicated print page and let the browser's
    // native print → Save as PDF do the rendering (crisp text, clickable links).
    // Pass the job context too so the print page can name the file after it.
    downloadHandler = async () => {
      await chrome.storage.local.set({
        [STORAGE_KEY_PRINT]: {
          profile: tailored,
          company: jobData?.company || '',
          jobTitle: jobData?.title || '',
        },
      });
      chrome.tabs.create({ url: chrome.runtime.getURL('print.html') });
    };
    setTailorStatus('Résumé tailored — open it to save as PDF.', 'success');
    dlBtn.classList.add('visible');
    dlBtn.addEventListener('click', downloadHandler);
  } else {
    console.warn('[resume-tailor] no tailored profile in result:', result);
    setTailorStatus('Done, but no tailored resume returned.', 'error');
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

  const email = document.getElementById('user-email').value.trim() || profile.email;
  if (!email) {
    setTailorStatus('Enter your email first.', 'error');
    return;
  }

  const btn = document.getElementById('tailor-btn');
  const dlBtn = document.getElementById('download-btn');
  const serverBase = document.getElementById('server-url').value.trim() || DEFAULT_SERVER;

  btn.disabled = true;
  btn.classList.add('loading');
  dlBtn.classList.remove('visible');
  chrome.storage.local.remove(tailorKey());
  setTailorStatus('Running in background — you can close this popup.');

  chrome.runtime.sendMessage({
    action: 'startTailor',
    url: tailorUrl(serverBase),
    resultKey: tailorKey(),
    body: {
      email,
      job_title: jobData.title,
      company: jobData.company,
      job_description: jobData.description,
      job_url: jobData.url,
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
