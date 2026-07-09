chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'ping') sendResponse({ alive: true });
});
