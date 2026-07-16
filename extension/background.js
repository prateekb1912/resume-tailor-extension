const TIMEOUT_MS = 120_000;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startTailor') {
    sendResponse({ started: true });
    runTailor(message.url, message.body, message.resultKey || 'tailorResult');
    return true;
  }
});

async function runTailor(url, body, resultKey = 'tailorResult') {
  await chrome.storage.local.set({
    [resultKey]: { status: 'pending', startedAt: Date.now() },
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      body: JSON.stringify(body),
    });

    clearTimeout(timer);

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      throw new Error(`Server returned ${response.status}${text ? ': ' + text.slice(0, 100) : ''}`);
    }

    // Server responds with { profile: <tailored>, fit: { match_score, ... } }
    const result = await response.json();
    console.log('[resume-tailor] tailor result keys:', Object.keys(result || {}));

    await chrome.storage.local.set({
      [resultKey]: { status: 'done', result, timestamp: Date.now() },
    });

    chrome.notifications.create('tailor-done', {
      type: 'basic',
      iconUrl: 'icon48.png',
      title: 'Tailr',
      message: 'Your tailored resume is ready. Click the extension to download.',
    });

  } catch (err) {
    clearTimeout(timer);
    const msg = err.name === 'AbortError' ? 'Timed out after 2 minutes.' : err.message;
    console.error('[resume-tailor] error:', msg);

    await chrome.storage.local.set({
      [resultKey]: { status: 'error', error: msg, timestamp: Date.now() },
    });

    chrome.notifications.create('tailor-error', {
      type: 'basic',
      iconUrl: 'icon48.png',
      title: 'Tailr',
      message: `Failed: ${msg}`,
    });
  }
}
