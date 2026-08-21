// Renders the tailored profile (saved to chrome.storage by the popup) into a
// clean single-column résumé, then opens the browser's print dialog so the user
// can Save as PDF — native, selectable text with clickable links, no server.

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

// Turn a profile field into an absolute href, or null if it isn't linkable.
function urlify(v) {
  if (!v) return null;
  const s = String(v).trim();
  if (/^https?:\/\//i.test(s)) return s;
  if (/^[\w.+-]+@[\w-]+\.[\w.-]+$/.test(s)) return `mailto:${s}`;
  return `https://${s.replace(/^\/+/, '')}`;
}

// Strip the scheme so link text reads "linkedin.com/in/x" rather than the full URL.
const display = (v) => String(v).replace(/^https?:\/\//i, '').replace(/\/$/, '');

// Phone numbers pulled from a PDF often carry a leading icon-glyph artifact
// (e.g. "/ne8766300037") because the résumé's phone icon has no Unicode
// mapping. Drop anything before the first digit, + or ( so the number reads clean.
const cleanPhone = (v) => String(v).replace(/^[^\d+(]+/, '').trim();

function formatMonth(v) {
  const value = String(v || '').trim();
  const match = value.match(/^(\d{4})-(\d{2})(?:-\d{2})?$/);
  if (!match) return value;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function link(text, url) {
  return url ? `<a href="${esc(url)}">${esc(text)}</a>` : esc(text);
}

function section(title, inner) {
  return `<div class="section"><h2>${esc(title)}</h2>${inner}</div>`;
}

function buildResumeHtml(p) {
  const out = [];

  // ── Header: name + centered contact line ──
  out.push(`<div class="name">${esc(p.name || 'Your Name')}</div>`);

  const contact = [];
  if (p.email) contact.push(link(p.email, `mailto:${p.email}`));
  if (p.phone) contact.push(esc(cleanPhone(p.phone)));
  if (p.location) contact.push(esc(p.location));

  const seen = new Set();
  const addLink = (v) => {
    if (!v) return;
    const url = urlify(v);
    const key = (url || '').toLowerCase().replace(/\/+$/, '');
    if (key && seen.has(key)) return;
    if (key) seen.add(key);
    contact.push(link(display(v), url));
  };
  addLink(p.linkedin);
  addLink(p.github);
  for (const l of (p.links || [])) addLink(l);

  if (contact.length) {
    out.push(`<div class="contact">${contact.join('<span class="sep">|</span>')}</div>`);
  }

  // ── Summary ──
  if (p.summary) out.push(section('Summary', `<p>${esc(p.summary)}</p>`));

  // ── Experience ──
  if (p.experience?.length) {
    const body = p.experience.map((e) => {
      const dates = [formatMonth(e.startDate), e.current ? 'Present' : formatMonth(e.endDate)]
        .filter(Boolean).map(esc).join(' – ');
      const bullets = (e.bullets || []).map((b) => `<li>${esc(b)}</li>`).join('');
      return `<div class="entry">
        <div class="entry-row"><span class="left">${esc(e.title || '')}</span><span class="right">${dates}</span></div>
        ${e.company ? `<div class="entry-sub">${esc(e.company)}</div>` : ''}
        ${bullets ? `<ul class="bullets">${bullets}</ul>` : ''}
      </div>`;
    }).join('');
    out.push(section('Experience', body));
  }

  // ── Projects ──
  if (p.projects?.length) {
    const body = p.projects.map((pr) => {
      const bullets = (pr.bullets || []).map((b) => `<li>${esc(b)}</li>`).join('');
      const head = pr.description
        ? `<span class="left">${esc(pr.name || '')}</span> <span class="proj-desc">| ${esc(pr.description)}</span>`
        : `<span class="left">${esc(pr.name || '')}</span>`;
      return `<div class="entry">
        <div class="entry-row"><span>${head}</span></div>
        ${bullets ? `<ul class="bullets">${bullets}</ul>` : ''}
      </div>`;
    }).join('');
    out.push(section('Projects', body));
  }

  // ── Education ──
  if (p.education?.length) {
    const body = p.education.map((ed) => {
      const sub = [ed.degree, ed.gpa && `GPA ${ed.gpa}`].filter(Boolean).map(esc).join(' · ');
      const dates = [
        formatMonth(ed.startDate),
        ed.current ? 'Present' : formatMonth(ed.endDate || ed.year),
      ].filter(Boolean).map(esc).join(' – ');
      return `<div class="entry">
        <div class="entry-row"><span class="left">${esc(ed.school || '')}</span><span class="right">${dates}</span></div>
        ${sub ? `<div class="entry-sub">${sub}</div>` : ''}
      </div>`;
    }).join('');
    out.push(section('Education', body));
  }

  // ── Skills ──
  if (p.skills?.length) {
    out.push(section('Skills', `<div class="skills">${esc(p.skills.join(', '))}</div>`));
  }

  // ── Certifications / Achievements ──
  const bulletList = (arr) => `<ul class="bullets">${arr.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
  if (p.certifications?.length) out.push(section('Certifications', bulletList(p.certifications)));
  if (p.achievements?.length) out.push(section('Achievements', bulletList(p.achievements)));

  return out.join('\n');
}

function fileName(profile, jobTitle, company) {
  const bits = [profile.name || 'Resume'];
  if (jobTitle && jobTitle.length <= 35) bits.push(jobTitle);
  if (company) bits.push(company);
  if (bits.length === 1) bits.push('Resume');
  return bits.join('_').replace(/[^\p{L}\p{N}]+/gu, '_').replace(/^_+|_+$/g, '');
}

async function main() {
  const mount = document.getElementById('resume');
  const stored = (await chrome.storage.local.get('printProfile')).printProfile;

  if (!stored) {
    mount.innerHTML = '<p>No résumé found. Run Tailor in the extension, then open the résumé again.</p>';
    return;
  }

  // Payload is { profile, company, jobTitle }; tolerate an older bare-profile shape.
  const profile = stored.profile || stored;
  const company = stored.company || '';
  const jobTitle = stored.jobTitle || '';

  document.title = fileName(profile, jobTitle, company);
  mount.innerHTML = buildResumeHtml(profile);

  document.getElementById('print-btn').addEventListener('click', () => window.print());

  // Give the layout a beat to settle, then open the print dialog automatically.
  setTimeout(() => window.print(), 350);
}

main();
