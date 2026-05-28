/**
 * BDC Researcher — site freshness banner + Refresh-data button.
 *
 * Reads dashboards/data/build_info.json (written by GitHub Actions on
 * each refresh) and shows: when SOI/BS were last refreshed, when market
 * prices were last refreshed, and a clickable "Refresh data" button
 * that opens the GitHub Actions workflow.
 *
 * The REPO_SLUG constant below is replaced by GitHub Actions at deploy
 * time. If you fork this repo, change REPO_SLUG to point at your fork.
 */
(function () {
  const REPO_SLUG = window.__REPO_SLUG__ || "vandi/BDC-Scalable";  // owner/repo
  const REFRESH_WORKFLOW = "refresh-all.yml";

  function fmtAgo(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const now = new Date();
    const sec = Math.floor((now - d) / 1000);
    if (sec < 60) return `${sec}s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
    if (sec < 86400) return `${Math.floor(sec / 3600)} hr ago`;
    return `${Math.floor(sec / 86400)} d ago`;
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("en-US", {
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit",
      timeZoneName: "short",
    });
  }

  function render(info) {
    // If this is a per-BDC dashboard page, the JSON is one directory up
    const banner = document.createElement("div");
    banner.id = "freshness-banner";
    banner.style.cssText = `
      position:fixed;bottom:0;left:0;right:0;
      background:#f5f6f8;border-top:1px solid #d1d5de;
      padding:6px 16px;font-family:'DM Mono',monospace;font-size:11px;
      color:#5a6172;display:flex;gap:16px;align-items:center;
      justify-content:flex-end;z-index:50;
    `;

    const fullAgo = fmtAgo(info.last_full_refresh_utc);
    const marketAgo = fmtAgo(info.last_market_refresh_utc);
    const fullDate = fmtDate(info.last_full_refresh_utc);
    const marketDate = fmtDate(info.last_market_refresh_utc);

    const status = document.createElement("span");
    status.innerHTML = `
      <span title="${fullDate}">Filings · ${fullAgo}</span>
      &nbsp;·&nbsp;
      <span title="${marketDate}">Prices · ${marketAgo}</span>
    `;

    const btn = document.createElement("a");
    const wfUrl =
      `https://github.com/${REPO_SLUG}/actions/workflows/${REFRESH_WORKFLOW}`;
    btn.href = wfUrl;
    btn.target = "_blank";
    btn.rel = "noopener";
    btn.textContent = "↻ Refresh data";
    btn.title = "Opens GitHub Actions — click 'Run workflow' to rebuild";
    btn.style.cssText = `
      background:#1a6ef5;color:#fff;text-decoration:none;
      padding:4px 10px;border-radius:5px;font-family:'DM Sans',sans-serif;
      font-size:11px;font-weight:500;
    `;

    banner.appendChild(status);
    banner.appendChild(btn);
    document.body.appendChild(banner);

    // Pad body so banner doesn't cover content
    document.body.style.paddingBottom = "32px";
  }

  function load() {
    // Two possible paths: top-level pages → "dashboards/data/..."
    //                    per-BDC dashboards → "data/..."
    const paths = [
      "dashboards/data/build_info.json",
      "data/build_info.json",
    ];
    let i = 0;
    function tryNext() {
      if (i >= paths.length) {
        render({});  // Render banner with "—" placeholders
        return;
      }
      fetch(paths[i] + "?ts=" + Date.now())
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(render)
        .catch(() => { i++; tryNext(); });
    }
    tryNext();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
