function metaContent(selector) {
  const node = document.querySelector(selector);
  return node && node.content ? String(node.content).trim() : "";
}

function textContent(selector) {
  const node = document.querySelector(selector);
  return node && node.textContent ? String(node.textContent).trim() : "";
}

function firstText(selectors) {
  for (const selector of selectors) {
    const value = textContent(selector);
    if (value) {
      return value;
    }
  }
  return "";
}

function meaningfulTitle() {
  const host = location.hostname.toLowerCase();
  const bilibiliTitle = host.endsWith("bilibili.com")
    ? firstText([
        "h1.video-title",
        ".video-title",
        ".video-title .tit",
        ".left-container h1",
        ".video-info-title",
        ".bpx-player-video-title"
      ])
    : "";
  return (
    bilibiliTitle ||
    metaContent('meta[property="og:title"]') ||
    metaContent('meta[name="twitter:title"]') ||
    textContent("h1") ||
    document.title ||
    ""
  );
}

function meaningfulDescription() {
  return (
    metaContent('meta[name="description"]') ||
    metaContent('meta[property="og:description"]') ||
    metaContent('meta[name="twitter:description"]') ||
    firstText([".desc-info-text", ".video-desc", ".video-desc-container", "article"])
  );
}

function mediaState() {
  const media = [...document.querySelectorAll("video, audio")];
  if (!media.length) {
    return "none";
  }
  if (media.some((item) => !item.paused && !item.ended)) {
    return "playing";
  }
  if (media.some((item) => item.currentTime > 0)) {
    return "paused";
  }
  return "present";
}

async function sendPageSignal() {
  try {
    if (!/^https?:\/\//i.test(location.href)) {
      return;
    }
    const videos = document.querySelectorAll("video");
    const audios = document.querySelectorAll("audio");
    const heading = firstText(["h1.video-title", ".video-title", ".left-container h1", "h1"]);
    chrome.runtime.sendMessage({
      type: "usage-widget-page-signal",
      payload: {
        title: meaningfulTitle(),
        url: location.href,
        description: meaningfulDescription(),
        h1: heading,
        hasVideo: videos.length > 0,
        hasAudio: audios.length > 0,
        mediaState: mediaState()
      }
    });
  } catch (_error) {
    // The desktop app may not be running. Stay quiet.
  }
}

sendPageSignal();
setInterval(sendPageSignal, 10000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    sendPageSignal();
  }
});
