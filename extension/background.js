const TIMEOUT_MS = 120_000;
const STORAGE_KEY_TOKEN = 'accessToken';

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'startTailor') {
    sendResponse({ started: true });
    runTailor(message.url, message.body, message.resultKey || 'tailorResult');
    return true;
  }
});

async function runTailor(url, body, resultKey = 'tailorResult') {
  const stored = await chrome.storage.local.get(STORAGE_KEY_TOKEN);
  const accessToken = stored[STORAGE_KEY_TOKEN];

  if (!accessToken) {
    await chrome.storage.local.set({
      [resultKey]: {
        status: 'error',
        error: 'Sign in to Tailr first.',
        authRequired: true,
        timestamp: Date.now(),
      },
    });
    return;
  }

  await chrome.storage.local.set({
    [resultKey]: { status: 'pending', startedAt: Date.now() },
  });

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  // A bounded API call can outlive Chrome's normal MV3 idle window (especially
  // while Render wakes up). Touching an extension API keeps this user-started
  // service-worker task alive until it finishes or reaches our two-minute cap.
  const keepAlive = setInterval(() => {
    chrome.storage.local.get(STORAGE_KEY_TOKEN);
  }, 20_000);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      signal: controller.signal,
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      const error = new Error(
        response.status === 401
          ? 'Your session expired. Sign in again.'
          : `Server returned ${response.status}${text ? ': ' + text.slice(0, 100) : ''}`,
      );
      error.authRequired = response.status === 401;
      throw error;
    }

    // Server responds with { profile: <tailored>, fit: { match_score, ... } }
    const result = await response.json();
    console.log('[resume-tailor] tailor result keys:', Object.keys(result || {}));

    // Do not expose a result after the user signs out or changes accounts while
    // this service-worker request is still running.
    const current = await chrome.storage.local.get(STORAGE_KEY_TOKEN);
    if (current[STORAGE_KEY_TOKEN] !== accessToken) return;

    await chrome.storage.local.set({
      [resultKey]: { status: 'done', result, timestamp: Date.now() },
    });

    chrome.notifications.create('tailor-done', {
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Tailr',
      message: 'Your tailored resume is ready. Click the extension to download.',
    });

  } catch (err) {
    const msg = err.name === 'AbortError' ? 'Timed out after 2 minutes.' : err.message;
    console.error('[resume-tailor] error:', msg);

    const current = await chrome.storage.local.get(STORAGE_KEY_TOKEN);
    if (current[STORAGE_KEY_TOKEN] !== accessToken) return;

    await chrome.storage.local.set({
      [resultKey]: {
        status: 'error',
        error: msg,
        authRequired: !!err.authRequired,
        timestamp: Date.now(),
      },
    });

    chrome.notifications.create('tailor-error', {
      type: 'basic',
      iconUrl: 'icons/icon48.png',
      title: 'Tailr',
      message: `Failed: ${msg}`,
    });
  } finally {
    clearTimeout(timer);
    clearInterval(keepAlive);
  }
}
