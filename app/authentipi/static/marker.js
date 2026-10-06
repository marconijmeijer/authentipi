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

  // Same-origin, relative path -- the proxy addon intercepts anything
  // under this prefix and reverse-proxies it to the AuthentiPi backend
  // itself, regardless of which real site is being visited. This means
  // every request this script makes automatically inherits the current
  // page's own scheme (http/https) and host, which is required: fetching
  // an absolute http://<lan-ip> URL from an https:// page is "mixed
  // content" and gets silently blocked by the browser.
  var API_BASE = "/__authentipi";
  var BATCH_SIZE = 40;
  var badgedElements = new WeakSet();

  function absoluteUrl(img) {
    // currentSrc is the URL the browser actually picked/loaded -- for a
    // plain <img src="...">, that's the same as src; for <img srcset="...">
    // or an <img> inside <picture><source srcset="...">, it can differ from
    // the src attribute. The proxy only ever sees what really went over the
    // network, so checking src alone can miss a real match entirely.
    if (img.currentSrc) return img.currentSrc;
    try {
      return new URL(img.getAttribute("src"), document.baseURI).href;
    } catch (e) {
      return null;
    }
  }

  function addBadge(el, label, title, style, wrapperDisplay) {
    var wrapper = el.parentElement;
    if (!badgedElements.has(el)) {
      wrapper = document.createElement("span");
      wrapper.style.position = "relative";
      wrapper.style.display = wrapperDisplay || "inline-block";
      el.parentNode.insertBefore(wrapper, el);
      wrapper.appendChild(el);
      badgedElements.add(el);
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
    // Only URLs we've actually badged -- NOT "checked and got nothing yet".
    // The proxy classifies asynchronously (can take seconds, e.g. Fase 3's
    // classifier), so a scan can easily run before a mark exists yet. Not
    // caching misses means later (periodic/mutation-triggered) scans keep
    // retrying automatically until a mark shows up or the page closes.
    var badgedUrls = new Set();

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
        if (!url || badgedUrls.has(url)) return;
        if (byUrl[url] === undefined) {
          urls.push(url);
          byUrl[url] = [];
        }
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
              badgedUrls.add(mark.url);
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
    name: "c2pa",
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
    name: "heuristic",
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

  // Fase 3's experimental text classifier works differently from the image
  // sources above: images are checked by URL against marks the proxy
  // already created server-side, but text paragraphs have to be read from
  // the live, post-hydration DOM (some sites, e.g. React SPAs, render
  // article text from embedded JSON state -- any badge spliced into the
  // raw server HTML gets wiped out when that happens) and classified via a
  // single batched call per scan.
  var MIN_PARAGRAPH_CHARS = 60;
  var textConfig = {
    icon: "✐",
    text: "Mogelijk AI-tekst (experimenteel)",
    text_color: "#3a1f4d",
    bg_color: "#d9b8ff",
  };
  // Text already submitted for classification, keyed by its own content
  // (not the element) -- so a paragraph whose text actually changes later
  // gets re-checked, but repeated scans don't keep re-submitting the same
  // unchanged paragraph while it's still waiting on the classifier or sat
  // just under the threshold.
  var checkedTexts = new Set();

  fetch(API_BASE + "/api/text-settings")
    .then(function (resp) {
      return resp.ok ? resp.json() : null;
    })
    .then(function (cfg) {
      if (cfg) textConfig = cfg;
    })
    .catch(function () {
      /* keep defaults */
    });

  function renderTextBadge(result) {
    var pct = Math.round((result.score || 0) * 100);
    var debugRow = result.above_threshold === false;

    var label = debugRow
      ? "\u{1F41E} debug: " + pct + "% (onder drempel)"
      : (textConfig.icon ? textConfig.icon + " " : "") + textConfig.text + " · " + pct + "%";

    var title = debugRow
      ? "Debug-modus: score haalde de ingestelde drempel niet, normaal zou dit " +
        "geen badge krijgen. Alleen zichtbaar omdat debug-modus aanstaat."
      : "Experimentele, niet-geverifieerde schatting van een lokaal tekstmodel. " +
        "Kan fout zitten -- geen cryptografisch bewijs, en geen detectie van een " +
        "eventueel echt watermerk (zoals OpenAI's textGrain), alleen een " +
        "statistische gok op schrijfstijl.";

    var style = debugRow
      ? "background:rgba(120,120,120,0.85);color:#fff;border:1px dashed #fff;"
      : "background:" + textConfig.bg_color + ";color:" + textConfig.text_color + ";";

    return { label: label, title: title, style: style };
  }

  function sendTextBatch(slice) {
    var texts = slice.map(function (c) {
      return c.text;
    });
    fetch(API_BASE + "/api/text-marks/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: location.href, texts: texts }),
    })
      .then(function (resp) {
        return resp.ok ? resp.json() : null;
      })
      .then(function (data) {
        if (!data) {
          // Request failed server-side -- let these get retried on a
          // later scan instead of silently giving up on them forever.
          slice.forEach(function (c) {
            checkedTexts.delete(c.text);
          });
          return;
        }
        (data.results || []).forEach(function (result) {
          var candidate = slice[result.index];
          if (!candidate) return;
          var rendered = renderTextBadge(result);
          addBadge(candidate.el, rendered.label, rendered.title, "bottom:4px;right:4px;" + rendered.style, "block");
        });
      })
      .catch(function () {
        slice.forEach(function (c) {
          checkedTexts.delete(c.text);
        });
      });
  }

  function scanText() {
    var candidates = [];
    Array.prototype.slice.call(document.querySelectorAll("p")).forEach(function (p) {
      if (badgedElements.has(p)) return;
      var text = p.textContent.trim();
      if (text.length < MIN_PARAGRAPH_CHARS) return;
      if (checkedTexts.has(text)) return;
      checkedTexts.add(text);
      candidates.push({ el: p, text: text });
    });

    for (var i = 0; i < candidates.length; i += BATCH_SIZE) {
      sendTextBatch(candidates.slice(i, i + BATCH_SIZE));
    }
  }

  function scanAll() {
    scanC2pa();
    scanHeuristic();
    scanText();
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

  // Belt-and-braces alongside the mutation-triggered debounce above: a
  // page that keeps mutating (ads, trackers, infinite scroll -- nu.nl is a
  // good example) can keep resetting that debounce indefinitely, so it
  // never actually fires. A plain interval guarantees a scan still happens
  // periodically no matter how busy the page is, and also naturally
  // retries images whose async classification wasn't done yet on the
  // first pass.
  setInterval(scanAll, 3000);
})();
