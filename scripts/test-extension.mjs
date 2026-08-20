import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import vm from 'node:vm';

const repoDir = new URL('../', import.meta.url);
const extensionDir = new URL('extension/', repoDir);
const backgroundSource = readFileSync(new URL('background.js', extensionDir), 'utf8');
const popupHtml = readFileSync(new URL('popup.html', extensionDir), 'utf8');
const popupSource = readFileSync(new URL('popup.js', extensionDir), 'utf8');

function storageArea(state) {
  return {
    async get(keys) {
      if (keys == null) return { ...state };
      const requested = Array.isArray(keys) ? keys : [keys];
      return Object.fromEntries(requested.filter((key) => key in state).map((key) => [key, state[key]]));
    },
    async set(values) {
      Object.assign(state, values);
    },
    async remove(keys) {
      for (const key of (Array.isArray(keys) ? keys : [keys])) delete state[key];
    },
  };
}

function backgroundHarness(initialState, fetchImpl) {
  const state = { ...initialState };
  const notifications = [];
  let messageListener;
  const context = {
    AbortController,
    clearInterval,
    clearTimeout,
    console: { error() {}, log() {} },
    fetch: fetchImpl,
    setInterval,
    setTimeout,
    chrome: {
      notifications: { create: (...args) => notifications.push(args) },
      runtime: { onMessage: { addListener: (listener) => { messageListener = listener; } } },
      storage: { local: storageArea(state) },
    },
  };
  vm.runInNewContext(backgroundSource, context, { filename: 'background.js' });
  const sendMessage = (message) => {
    let response;
    messageListener(message, {}, (value) => { response = value; });
    return response;
  };
  return { context, notifications, sendMessage, state };
}

const manifest = JSON.parse(readFileSync(new URL('manifest.json', extensionDir), 'utf8'));
assert.equal(manifest.version, '1.1.1');
assert(manifest.host_permissions.includes('https://tailr-api.onrender.com/*'));

for (const path of [
  manifest.background.service_worker,
  manifest.action.default_popup,
  ...Object.values(manifest.icons),
  ...Object.values(manifest.action.default_icon),
]) {
  assert(existsSync(new URL(path, extensionDir)), `Manifest asset is missing: ${path}`);
}

const htmlIds = new Set([...popupHtml.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));
const referencedIds = new Set(
  [...popupSource.matchAll(/getElementById\(['"]([^'"]+)['"]\)/g)].map((match) => match[1]),
);
for (const id of referencedIds) {
  assert(htmlIds.has(id), `popup.js references a missing element: #${id}`);
}
assert(popupSource.includes("const DEFAULT_SERVER = 'https://tailr-api.onrender.com'"));
assert(popupSource.includes("'Authorization': `Bearer ${token}`"));
assert(popupSource.includes("action: 'getWorkerVersion'"));
assert(popupHtml.includes('id="auth-view"'));
assert(popupHtml.includes('id="app-view"'));
assert(popupHtml.includes('class="screen app-screen hidden"'));

{
  const { context, sendMessage, state } = backgroundHarness({}, async () => {
    throw new Error('fetch should not run without a token');
  });
  assert.equal(sendMessage({ action: 'getWorkerVersion' }).version, manifest.version);
  await context.runTailor('https://tailr-api.onrender.com/resume/tailor', {}, 'missing-token');
  assert.equal(state['missing-token'].status, 'error');
  assert.equal(state['missing-token'].authRequired, true);
}

{
  let request;
  const { context, state } = backgroundHarness({ accessToken: 'test-token' }, async (url, options) => {
    request = { url, options };
    return {
      ok: true,
      status: 200,
      async json() { return { profile: { name: 'Test' }, fit: { match_score: 80 } }; },
    };
  });
  const body = { job_title: 'Engineer', job_description: 'x'.repeat(120) };
  await context.runTailor('https://tailr-api.onrender.com/resume/tailor', body, 'success');

  assert.equal(request.options.headers.Authorization, 'Bearer test-token');
  assert.deepEqual(JSON.parse(request.options.body), body);
  assert.equal(state.success.status, 'done');
}

{
  const { context, state } = backgroundHarness({ accessToken: 'expired-token' }, async () => ({
    ok: false,
    status: 401,
    async text() { return '{"detail":"Could not validate credentials"}'; },
  }));
  await context.runTailor('https://tailr-api.onrender.com/resume/tailor', {}, 'expired');
  assert.equal(state.expired.status, 'error');
  assert.equal(state.expired.authRequired, true);
}

console.log('Extension checks passed.');
