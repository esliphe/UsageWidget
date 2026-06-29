const ENDPOINT = "http://127.0.0.1:47621/active-tab";
const AUDIBLE_ENDPOINT = "http://127.0.0.1:47621/audible-tabs";
const PAGE_SIGNAL_ENDPOINT = "http://127.0.0.1:47621/page-signal";
const SESSION_ENDPOINT = "http://127.0.0.1:47621/session";

let authToken = "";

async function refreshAuthToken() {
  const response = await fetch(SESSION_ENDPOINT, {
    method: "GET",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`session failed: ${response.status}`);
  }
  const payload = await response.json();
  authToken = String(payload.token || "");
  if (!authToken) {
    throw new Error("empty session token");
  }
  return authToken;
}

async function postJson(endpoint, payload) {
  if (!authToken) {
    await refreshAuthToken();
  }
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-UsageWidget-Token": authToken },
    body: JSON.stringify(payload)
  });
  if (response.status === 401 || response.status === 403) {
    await refreshAuthToken();
    await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-UsageWidget-Token": authToken },
      body: JSON.stringify(payload)
    });
  }
}

async function sendActiveTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) {
      return;
    }
    if (!/^https?:\/\//i.test(tab.url)) {
      return;
    }
    await postJson(ENDPOINT, {
        title: tab.title || "",
        url: tab.url || "",
        browser: "browser-extension",
        audible: Boolean(tab.audible),
        tabId: tab.id,
        windowId: tab.windowId,
        active: Boolean(tab.active),
        muted: Boolean(tab.mutedInfo && tab.mutedInfo.muted),
        favIconUrl: tab.favIconUrl || ""
    });
  } catch (_error) {
    // The desktop app may not be running. Stay quiet.
  }
}

async function sendAudibleTabs() {
  try {
    const tabs = await chrome.tabs.query({ audible: true });
    const payload = tabs
      .filter((tab) => tab.url && /^https?:\/\//i.test(tab.url))
      .map((tab) => ({
        title: tab.title || "",
        url: tab.url || "",
        browser: "browser-extension",
        tabId: tab.id,
        windowId: tab.windowId,
        active: Boolean(tab.active),
        muted: Boolean(tab.mutedInfo && tab.mutedInfo.muted),
        favIconUrl: tab.favIconUrl || ""
      }));
    await postJson(AUDIBLE_ENDPOINT, { tabs: payload });
  } catch (_error) {
    // The desktop app may not be running. Stay quiet.
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "usage-widget-page-signal" || !message.payload) {
    return false;
  }
  postJson(PAGE_SIGNAL_ENDPOINT, message.payload)
    .then(() => sendResponse({ ok: true }))
    .catch(() => sendResponse({ ok: false }));
  return true;
});

chrome.tabs.onActivated.addListener(() => {
  sendActiveTab();
  sendAudibleTabs();
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.active) {
    sendActiveTab();
  }
  if (Object.prototype.hasOwnProperty.call(changeInfo, "audible")) {
    sendAudibleTabs();
  }
});

chrome.windows.onFocusChanged.addListener(() => {
  sendActiveTab();
  sendAudibleTabs();
});

chrome.runtime.onInstalled.addListener(() => {
  sendActiveTab();
  sendAudibleTabs();
});

setInterval(sendAudibleTabs, 5000);
