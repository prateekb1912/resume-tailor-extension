const TIMEOUT_MS = 120_000;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startTailor') {
    sendResponse({ started: true });
    runTailor(message.webhookUrl, message.body);
    return true;
  }
});

async function runTailor(webhookUrl, body) {
  await chrome.storage.local.set({
    tailorResult: { status: 'pending', startedAt: Date.now() },
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

    let result = await response.json();
    console.log('[resume-tailor] raw n8n response:', JSON.stringify(result).slice(0, 300));

    // Normalize n8n response — it can return arrays or wrap in { json: {...} }
    if (Array.isArray(result)) result = result[0];
    if (result?.json) result = result.json;

    console.log('[resume-tailor] normalized result keys:', Object.keys(result || {}));

    await chrome.storage.local.set({
      tailorResult: { status: 'done', result, timestamp: Date.now() },
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
      tailorResult: { status: 'error', error: msg, timestamp: Date.now() },
    });

    chrome.notifications.create('tailor-error', {
      type:    'basic',
      iconUrl: 'icon48.png',
      title:   'Resume Tailor',
      message: `Failed: ${msg}`,
    });
  }
}
