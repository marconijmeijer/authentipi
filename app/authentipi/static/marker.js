(function () {
  "use strict";

  // Injected by the AuthentiPi mitmproxy addon into every HTML page. Finds
  // <img> elements, asks the AuthentiPi backend whether their URL carries a
  // known C2PA Content Credentials manifest, and overlays a small badge on
  // the ones that do.

  var currentScript = document.currentScript;
  if (!currentScript) return;

  var API_BASE = new URL(currentScript.src).origin;
  var BATCH_SIZE = 40;
  var checkedUrls = new Set();
  var badgedElements = new WeakSet();
  var debounceTimer = null;

  // Configurable via the AuthentiPi settings page (Instellingen). These
  // defaults apply until (if) the real config loads.
  var badgeConfig = {
    icon: "✓",
    text: "Content Credentials",
    text_color: "#111111",
    bg_color: "#ffd400",
  };
  fetch(API_BASE + "/api/marker-settings")
    .then(function (resp) {
      return resp.ok ? resp.json() : null;
    })
    .then(function (cfg) {
      if (cfg) badgeConfig = cfg;
    })
    .catch(function () {
      /* keep defaults */
    });

  function absoluteUrl(img) {
    try {
      return new URL(img.getAttribute("src"), document.baseURI).href;
    } catch (e) {
      return null;
    }
  }

  function addBadge(img, mark) {
    if (badgedElements.has(img)) return;
    badgedElements.add(img);

    var wrapper = document.createElement("span");
    wrapper.style.position = "relative";
    wrapper.style.display = "inline-block";
    img.parentNode.insertBefore(wrapper, img);
    wrapper.appendChild(img);

    var badge = document.createElement("div");
    badge.textContent = (badgeConfig.icon ? badgeConfig.icon + " " : "") + badgeConfig.text;
    badge.title = mark.claim_generator
      ? "Bron: " + mark.claim_generator
      : "C2PA Content Credentials gevonden";
    badge.style.cssText =
      "position:absolute;top:4px;right:4px;z-index:2147483647;" +
      "background:" + badgeConfig.bg_color + ";color:" + badgeConfig.text_color + ";" +
      "font:600 11px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;" +
      "padding:2px 6px;border-radius:999px;pointer-events:none;" +
      "box-shadow:0 1px 3px rgba(0,0,0,0.4);";
    wrapper.appendChild(badge);
  }

  function checkBatch(images) {
    var urls = [];
    var byUrl = {};
    images.forEach(function (img) {
      var url = absoluteUrl(img);
      if (!url || checkedUrls.has(url)) return;
      checkedUrls.add(url);
      urls.push(url);
      byUrl[url] = byUrl[url] || [];
      byUrl[url].push(img);
    });

    if (urls.length === 0) return;

    for (var i = 0; i < urls.length; i += BATCH_SIZE) {
      var slice = urls.slice(i, i + BATCH_SIZE);
      var qs = encodeURIComponent(slice.join(","));
      fetch(API_BASE + "/api/marks/check?urls=" + qs)
        .then(function (resp) {
          return resp.ok ? resp.json() : [];
        })
        .then(function (marks) {
          marks.forEach(function (mark) {
            (byUrl[mark.url] || []).forEach(function (img) {
              addBadge(img, mark);
            });
          });
        })
        .catch(function () {
          /* best-effort; a failed check should never break the page */
        });
    }
  }

  function scan() {
    checkBatch(Array.prototype.slice.call(document.images));
  }

  function scheduleScan() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scan, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scan);
  } else {
    scan();
  }

  var observer = new MutationObserver(function () {
    scheduleScan();
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["src"],
  });
})();
