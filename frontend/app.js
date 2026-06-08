const API_BASE = window.CHAM_API_BASE || "";

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function fmtDate(iso) {
  return iso ? new Date(iso).toLocaleDateString() : "";
}

function fmtDuration(secs) {
  if (!secs) return "";
  const m = Math.round(secs / 60);
  return m >= 1 ? `${m} min` : "<1 min";
}

function episodeCard(ep) {
  const a = document.createElement("a");
  a.href = `episode.html?id=${ep.id}`;
  a.className = "card";
  a.innerHTML = `
    <span class="category">${esc(ep.format || "episode")}</span>
    <h3>${esc(ep.title || "Untitled")}</h3>
    <p class="tagline">${esc(ep.description || "")}</p>
    <span class="date">${esc(fmtDate(ep.created_at))}</span>
  `;
  return a;
}

// --- Signup ---

const signupForm = document.getElementById("signup-form");
if (signupForm) {
  signupForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = signupForm.querySelector('input[type="email"]');
    const msg = document.getElementById("signup-message");
    const email = input.value.trim();
    if (!email) return;

    msg.textContent = "Subscribing...";
    msg.className = "signup-message";

    try {
      const res = await fetch(`${API_BASE}/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (res.ok) {
        msg.textContent =
          data.status === "already_subscribed"
            ? "You're already subscribed!"
            : "Check your email to confirm your subscription.";
        msg.className = "signup-message success";
        input.value = "";
      } else {
        msg.textContent = data.error || "Something went wrong.";
        msg.className = "signup-message error";
      }
    } catch {
      msg.textContent = "Network error. Please try again.";
      msg.className = "signup-message error";
    }
  });
}

// --- Archive ---

const archiveGrid = document.getElementById("archive-grid");
const loadMoreBtn = document.getElementById("load-more-btn");
let lastEpisodeId = null;

async function loadArchive(append = false) {
  if (!archiveGrid) return;

  let url = `${API_BASE}/episodes?limit=20`;
  if (append && lastEpisodeId) url += `&start_after=${lastEpisodeId}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    const episodes = data.episodes || [];

    if (!append) archiveGrid.innerHTML = "";
    for (const ep of episodes) archiveGrid.appendChild(episodeCard(ep));

    if (episodes.length > 0) lastEpisodeId = episodes[episodes.length - 1].id;
    if (loadMoreBtn) {
      loadMoreBtn.style.display = episodes.length < 20 ? "none" : "block";
    }
  } catch {
    archiveGrid.innerHTML = "<p>Failed to load episodes.</p>";
  }
}

if (loadMoreBtn) loadMoreBtn.addEventListener("click", () => loadArchive(true));
if (archiveGrid) loadArchive();

// --- Single Episode ---

const episodeContainer = document.getElementById("episode-container");

function transcriptHtml(ep) {
  const speakers = ep.speakers || [];
  const colorByName = {};
  speakers.forEach((s, i) => {
    colorByName[s.name] = `turn-c${(i % 6) + 1}`;
  });

  const rows = (ep.turns || [])
    .map((t) => {
      const cls = colorByName[t.speaker] || "turn-c1";
      return `
        <div class="turn ${cls}">
          <div class="turn-speaker">${esc(t.speaker)}</div>
          <div class="turn-text">${esc(t.text)}</div>
        </div>`;
    })
    .join("");

  const cast = speakers
    .map((s) => `<strong>${esc(s.name)}</strong> — ${esc(s.role || "")}`)
    .join("<br>");

  return `
    <div class="cast">${cast}</div>
    <div class="transcript">${rows}</div>`;
}

async function loadEpisode() {
  if (!episodeContainer) return;

  const id = new URLSearchParams(location.search).get("id");
  if (!id) {
    episodeContainer.innerHTML = "<p>No episode ID specified.</p>";
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/episodes/${id}`);
    if (!res.ok) {
      episodeContainer.innerHTML = "<p>Episode not found.</p>";
      return;
    }
    const ep = await res.json();
    document.title = `${ep.title || "Episode"} — ${window.CHAM_NAME || ""}`;

    const source = ep.source || {};
    const sourceLine = source.title
      ? source.url
        ? `Discussing: <a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.title)}</a>`
        : `Discussing: ${esc(source.title)}`
      : "";

    const meta = [ep.format, fmtDuration(ep.audio_duration_secs), fmtDate(ep.created_at)]
      .filter(Boolean)
      .map(esc)
      .join(" · ");

    episodeContainer.innerHTML = `
      <div class="report-header">
        <div class="container">
          <h2>${esc(ep.title || "Episode")}</h2>
          <p class="tagline">${esc(ep.description || "")}</p>
          <p class="report-meta">${meta}</p>
          ${sourceLine ? `<p class="source-line">${sourceLine}</p>` : ""}
          ${
            ep.audio_url
              ? `<div class="audio-player"><audio controls preload="none" src="${esc(ep.audio_url)}"></audio></div>`
              : ""
          }
        </div>
      </div>
      <div class="section">
        <div class="container">${transcriptHtml(ep)}</div>
      </div>`;
  } catch {
    episodeContainer.innerHTML = "<p>Failed to load episode.</p>";
  }
}

if (episodeContainer) loadEpisode();

// --- Latest episodes on index ---

const latestPreview = document.getElementById("latest-preview");

async function loadLatest() {
  if (!latestPreview) return;
  try {
    const res = await fetch(`${API_BASE}/episodes?limit=6`);
    const data = await res.json();
    const episodes = data.episodes || [];

    if (episodes.length === 0) {
      latestPreview.innerHTML =
        "<p>No episodes yet. Forward something to get the first one going!</p>";
      return;
    }
    latestPreview.innerHTML = "";
    for (const ep of episodes) latestPreview.appendChild(episodeCard(ep));
  } catch {
    latestPreview.innerHTML = "";
  }
}

if (latestPreview) loadLatest();

// --- Confirm Subscription ---

const confirmMessage = document.getElementById("confirm-result");

async function handleConfirm() {
  if (!confirmMessage) return;
  const token = new URLSearchParams(location.search).get("token");
  if (!token) {
    confirmMessage.textContent = "Invalid confirmation link.";
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/confirm?token=${token}`);
    confirmMessage.textContent = res.ok
      ? "You're confirmed! Welcome aboard — watch your inbox for new episodes."
      : "Confirmation link not found or already used.";
  } catch {
    confirmMessage.textContent = "Something went wrong. Please try again.";
  }
}

if (confirmMessage) handleConfirm();

// --- Unsubscribe ---

const unsubMessage = document.getElementById("unsub-result");

async function handleUnsubscribe() {
  if (!unsubMessage) return;
  const token = new URLSearchParams(location.search).get("token");
  if (!token) {
    unsubMessage.textContent = "Invalid unsubscribe link.";
    return;
  }
  try {
    const res = await fetch(`${API_BASE}/unsubscribe?token=${token}`);
    unsubMessage.textContent = res.ok
      ? "You've been unsubscribed. Sorry to see you go!"
      : "Unsubscribe link not found or already used.";
  } catch {
    unsubMessage.textContent = "Something went wrong. Please try again.";
  }
}

if (unsubMessage) handleUnsubscribe();
