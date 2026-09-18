(function () {
  "use strict";

  // Injected by the AuthentiPi mitmproxy addon into every HTML page. Finds
  // <img> elements and asks the AuthentiPi backend whether their URL is
  // flagged by either detection source, overlaying a badge on the ones
  // that are:
  //  - "c2pa": a verified/signed C2PA Content Credentials manifest.
  //  - "heuristic": Fase 3's experimental local AI-image classifier (a
  //    statistical guess, not a verified claim -- kept visually distinct
  //    from the c2pa badge on purpose).

  var currentScript = document.currentScript;
  if (!currentScript) return;

  var API_BASE = new URL(currentScript.src).origin;
  var BATCH_SIZE = 40;
  var badgedElements = new WeakSet();

  function absoluteUrl(img) {
    try {
      return new URL(img.getAttribute("src"), document.baseURI).href;
    } catch (e) {
      return null;
    }
  }

  function addBadge(img, label, title, style) {
    var wrapper = img.parentElement;
    if (!badgedElements.has(img)) {
      wrapper = document.createElement("span");
      wrapper.style.position = "relative";
      wrapper.style.display = "inline-block";
      img.parentNode.insertBefore(wrapper, img);
      wrapper.appendChild(img);
      badgedElements.add(img);
    }

    var badge = document.createElement("div");
    badge.textContent = label;
    badge.title = title;
    badge.style.cssText =
      "position:absolute;z-index:2147483647;" +
      "font:600 11px/1.4 -apple-system,BlinkMacSystemFont,sans-serif;" +
      "padding:2px 6px;border-radius:999px;pointer-events:none;" +
      "box-shadow:0 1px 3px rgba(0,0,0,0.4);" +
      style;
    wrapper.appendChild(badge);
  }

  function makeSource(opts) {
    // opts: { configUrl, checkUrl, defaultConfig, position, render(mark, config) -> {label, title} }
    var config = opts.defaultConfig;
    var checkedUrls = new Set();

    fetch(API_BASE + opts.configUrl)
      .then(function (resp) {
        return resp.ok ? resp.json() : null;
      })
      .then(function (cfg) {
        if (cfg) config = cfg;
      })
      .catch(function () {
        /* keep defaults */
      });

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
        fetch(API_BASE + opts.checkUrl + qs)
          .then(function (resp) {
            return resp.ok ? resp.json() : [];
          })
          .then(function (marks) {
            marks.forEach(function (mark) {
              var rendered = opts.render(mark, config);
              (byUrl[mark.url] || []).forEach(function (img) {
                addBadge(img, rendered.label, rendered.title, opts.position + rendered.style);
              });
            });
          })
          .catch(function () {
            /* best-effort; a failed check should never break the page */
          });
      }
    }

    return function scan() {
      checkBatch(Array.prototype.slice.call(document.images));
    };
  }

  var scanC2pa = makeSource({
    configUrl: "/api/marker-settings",
    checkUrl: "/api/marks/check?urls=",
    position: "top:4px;right:4px;",
    defaultConfig: {
      icon: "✓",
      text: "Content Credentials",
      text_color: "#111111",
      bg_color: "#ffd400",
    },
    render: function (mark, config) {
      var label = (config.icon ? config.icon + " " : "") + config.text;
      if (mark.source_type) label += " · " + mark.source_type;
      if (mark.trusted === false) label += " · ongeverifieerd";

      var titleParts = [];
      if (mark.source_type) titleParts.push("Type: " + mark.source_type);
      titleParts.push(
        mark.trusted === true
          ? "Ondertekenaar: vertrouwd"
          : mark.trusted === false
          ? "Ondertekenaar: niet vertrouwd (bv. zelf-ondertekend)"
          : "Vertrouwensstatus: onbekend"
      );
      if (mark.claim_generator) titleParts.push("Bron: " + mark.claim_generator);

      return {
        label: label,
        title: titleParts.join(" | "),
        style: "background:" + config.bg_color + ";color:" + config.text_color + ";",
      };
    },
  });

  var scanHeuristic = makeSource({
    configUrl: "/api/heuristic-settings",
    checkUrl: "/api/heuristic-marks/check?urls=",
    position: "bottom:4px;right:4px;",
    defaultConfig: {
      icon: "?",
      text: "Mogelijk AI (experimenteel)",
      text_color: "#3a2a00",
      bg_color: "#ffb84d",
    },
    render: function (mark, config) {
      var pct = Math.round((mark.score || 0) * 100);
      var debugRow = mark.above_threshold === false;

      var label = debugRow
        ? "\u{1F41E} debug: " + pct + "% (onder drempel)"
        : (config.icon ? config.icon + " " : "") + config.text + " · " + pct + "%";

      var title = debugRow
        ? "Debug-modus: score haalde de ingestelde drempel niet, normaal zou dit " +
          "geen badge krijgen. Alleen zichtbaar omdat debug-modus aanstaat."
        : "Experimentele, niet-geverifieerde schatting van een lokaal AI-model (" +
          (mark.model_name || "onbekend model") +
          "). Kan fout zitten -- geen cryptografisch bewijs zoals bij C2PA.";

      var style = debugRow
        ? "background:rgba(120,120,120,0.85);color:#fff;border:1px dashed #fff;"
        : "background:" + config.bg_color + ";color:" + config.text_color + ";";

      return { label: label, title: title, style: style };
    },
  });

  function scanAll() {
    scanC2pa();
    scanHeuristic();
  }

  var debounceTimer = null;
  function scheduleScan() {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(scanAll, 400);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scanAll);
  } else {
    scanAll();
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
