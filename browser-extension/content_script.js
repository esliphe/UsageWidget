function metaContent(selector) {
  const node = document.querySelector(selector);
  return node && node.content ? String(node.content).trim() : "";
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
    const h1 = document.querySelector("h1");
    chrome.runtime.sendMessage({
      type: "usage-widget-page-signal",
      payload: {
        title: document.title || "",
        url: location.href,
        description:
          metaContent('meta[name="description"]') ||
          metaContent('meta[property="og:description"]') ||
          metaContent('meta[name="twitter:description"]'),
        h1: h1 ? h1.textContent.trim() : "",
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
