const TIMEOUT_MS = 120_000;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startTailor') {
    sendResponse({ started: true });
    runTailor(message.webhookUrl, message.body, message.resultKey || 'tailorResult');
    return true;
  }
});

function arrayBufferToBase64(buf) {
  const bytes = new Uint8Array(buf);
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

async function runTailor(webhookUrl, body, resultKey = 'tailorResult') {
  await chrome.storage.local.set({
    [resultKey]: { status: 'pending', startedAt: Date.now() },
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(webhookUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      signal:  controller.signal,
      body:    JSON.stringify(body),
    });

    clearTimeout(timer);

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`n8n returned ${response.status}${text ? ': ' + text.slice(0, 100) : ''}`);
    }

    const contentType = response.headers.get('content-type') || '';
    let result;

    // Read raw bytes once, then sniff — don't trust the content-type header,
    // since n8n's binary webhook response may mislabel or omit it.
    const buf  = await response.arrayBuffer();
    const head = new Uint8Array(buf.slice(0, 5));
    const isPdf    = head[0] === 0x25 && head[1] === 0x50 && head[2] === 0x44 && head[3] === 0x46; // %PDF
    const looksJson = contentType.includes('application/json') && !isPdf;

    if (looksJson) {
      result = JSON.parse(new TextDecoder().decode(buf));
      console.log('[resume-tailor] raw n8n response:', JSON.stringify(result).slice(0, 300));

      // Normalize n8n response — it can return arrays or wrap in { json: {...} }
      if (Array.isArray(result)) result = result[0];
      if (result?.json) result = result.json;

      console.log('[resume-tailor] normalized result keys:', Object.keys(result || {}));
    } else {
      // Binary response (e.g. Gotenberg PDF returned directly by the webhook)
      const fileData = arrayBufferToBase64(buf);
      const mimeType = isPdf ? 'application/pdf' : (contentType.split(';')[0].trim() || 'application/pdf');

      // Derive a filename from Content-Disposition if present
      const disposition = response.headers.get('content-disposition') || '';
      const match = disposition.match(/filename\*?=(?:UTF-8''|")?([^";]+)/i);
      const fileName = match ? decodeURIComponent(match[1].replace(/"/g, '')) : undefined;

      result = { fileData, mimeType, ...(fileName ? { fileName } : {}) };
      console.log('[resume-tailor] binary n8n response:', mimeType, `${buf.byteLength} bytes`);
    }

    await chrome.storage.local.set({
      [resultKey]: { status: 'done', result, timestamp: Date.now() },
    });

    chrome.notifications.create('tailor-done', {
      type:    'basic',
      iconUrl: 'icon48.png',
      title:   'Resume Tailor',
      message: 'Your tailored resume is ready — click the extension to download.',
    });

  } catch (err) {
    clearTimeout(timer);
    const msg = err.name === 'AbortError' ? 'Timed out after 2 minutes.' : err.message;
    console.error('[resume-tailor] error:', msg);

    await chrome.storage.local.set({
      [resultKey]: { status: 'error', error: msg, timestamp: Date.now() },
    });

    chrome.notifications.create('tailor-error', {
      type:    'basic',
      iconUrl: 'icon48.png',
      title:   'Resume Tailor',
      message: `Failed: ${msg}`,
    });
  }
}
