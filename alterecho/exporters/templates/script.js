(() => {
  const body = document.body;
  const themeButton = document.getElementById("theme-toggle");
  const search = document.getElementById("search");
  const count = document.getElementById("search-count");
  const noResults = document.getElementById("no-results");
  const messages = [...document.querySelectorAll(".message:not(.partial)")];

  function setTheme(theme) {
    body.dataset.theme = theme;
    themeButton.textContent = theme === "dark" ? "Tema chiaro" : "Tema scuro";
    try { localStorage.setItem("alterecho-theme", theme); } catch (_) {}
  }
  try { setTheme(localStorage.getItem("alterecho-theme") || "dark"); } catch (_) { setTheme("dark"); }
  themeButton.addEventListener("click", () => setTheme(body.dataset.theme === "dark" ? "light" : "dark"));

  function clearHighlights(root) {
    root.querySelectorAll("mark.search-hit").forEach((mark) => mark.replaceWith(document.createTextNode(mark.textContent || "")));
    root.normalize();
  }
  function highlightText(root, query) {
    if (!query) return 0;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (!node.nodeValue || !node.nodeValue.toLocaleLowerCase().includes(query)) return NodeFilter.FILTER_REJECT;
        if (node.parentElement?.closest("button,script,style,mark,.sr-only")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    let matches = 0;
    for (const node of nodes) {
      const value = node.nodeValue;
      const lower = value.toLocaleLowerCase();
      const fragment = document.createDocumentFragment();
      let from = 0;
      let at;
      while ((at = lower.indexOf(query, from)) !== -1) {
        fragment.append(document.createTextNode(value.slice(from, at)));
        const mark = document.createElement("mark");
        mark.className = "search-hit";
        mark.textContent = value.slice(at, at + query.length);
        fragment.append(mark);
        from = at + query.length;
        matches += 1;
      }
      fragment.append(document.createTextNode(value.slice(from)));
      node.replaceWith(fragment);
    }
    return matches;
  }
  function runSearch() {
    const query = search.value.trim().toLocaleLowerCase();
    let found = 0;
    for (const message of messages) {
      const content = message.querySelector(".message-content");
      clearHighlights(content);
      const hits = highlightText(content, query);
      found += hits;
      message.hidden = Boolean(query) && hits === 0;
    }
    count.textContent = query ? `${found} risultati` : "";
    noResults.hidden = !query || messages.some((message) => !message.hidden);
  }
  search.addEventListener("input", runSearch);

  async function copyText(text, button) {
    const previous = button.textContent;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const area = document.createElement("textarea");
        area.value = text;
        area.className = "clipboard-fallback";
        document.body.append(area);
        area.select();
        const copied = document.execCommand("copy");
        area.remove();
        if (!copied) throw new Error("Copia non disponibile");
      }
      button.textContent = "Copiato";
    } catch (_) { button.textContent = "Copia non riuscita"; }
    window.setTimeout(() => { button.textContent = previous; }, 1600);
  }
  document.querySelectorAll(".copy-message").forEach((button) => {
    button.addEventListener("click", () => copyText(button.closest(".message").querySelector(".message-content").innerText, button));
  });
  document.querySelectorAll(".copy-code").forEach((button) => {
    button.addEventListener("click", () => copyText(button.closest(".code-block").querySelector("pre").textContent, button));
  });
  document.getElementById("to-top").addEventListener("click", () => window.scrollTo({top: 0, behavior: "smooth"}));
  document.getElementById("to-bottom").addEventListener("click", () => window.scrollTo({top: document.body.scrollHeight, behavior: "smooth"}));
})();
