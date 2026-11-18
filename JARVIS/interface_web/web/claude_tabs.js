/* Conversas paralelas do Claude Max — controle independente da UI JARVIS. */
(() => {
  "use strict";
  const el = (id) => document.getElementById(id);
  const ui = {
    page: el("page-claude"),
    tabs: el("claude-tabs"),
    messages: el("claude-messages"),
    input: el("claude-input"),
    send: el("claude-send"),
    create: el("claude-create"),
    model: el("claude-new-model"),
    status: el("claude-status"),
    tip: el("claude-tip"),
    metrics: el("claude-metrics"),
    cancel: el("claude-cancel"),
  };
  if (!ui.page) return;

  let selected = null;
  let refreshPending = false;
  let lastMessagesKey = "";
  let lastUsageKey = "";
  let initialized = false;

  const api = () => (window.pywebview && window.pywebview.api) || null;
  function error(message) {
    ui.status.textContent = message || "Falha ao comunicar com o JARVIS.";
    ui.status.classList.add("error");
  }
  function notice(message) {
    ui.status.textContent = message || "";
    ui.status.classList.remove("error");
  }
  function button(label, className, onclick, title) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = className;
    b.textContent = label;
    if (title) b.title = title;
    b.addEventListener("click", onclick);
    return b;
  }

  function renderTabs(tabs, activeId, maxTabs) {
    ui.tabs.replaceChildren();
    tabs.forEach((tab) => {
      const group = document.createElement("div");
      group.className = "ct-tab" + (tab.id === activeId ? " active" : "");
      const caption = (tab.busy ? "● " : "") + tab.title;
      const pick = button(caption, "ct-tab-pick", () => {
        selected = tab.id;
        lastMessagesKey = "";
        refresh();
      }, "Alternar para " + tab.title);
      pick.setAttribute("role", "tab");
      pick.setAttribute("aria-selected", String(tab.id === activeId));
      pick.title = tab.title + " · " + (tab.model === "default" ? "Modelo padrão" : tab.model);
      group.appendChild(pick);

      const rename = button("✎", "ct-mini", async () => {
        const next = window.prompt("Nome da aba:", tab.title);
        if (!next || !next.trim()) return;
        try {
          const result = await api().claude_tabs_rename(tab.id, next);
          if (!result.ok) error(result.error);
          else refresh();
        } catch (_err) { error("Não foi possível renomear a aba."); }
      }, "Renomear");
      group.appendChild(rename);

      const remove = button("×", "ct-mini", async () => {
        if (!window.confirm("Excluir a conversa e o histórico local desta aba?")) return;
        try {
          const result = await api().claude_tabs_delete(tab.id);
          if (!result.ok) { error(result.error); return; }
          if (selected === tab.id) selected = null;
          lastMessagesKey = "";
          refresh();
        } catch (_err) { error("Não foi possível excluir a aba."); }
      }, "Excluir conversa");
      group.appendChild(remove);
      ui.tabs.appendChild(group);
    });
    ui.create.disabled = tabs.length >= maxTabs;
    ui.create.title = tabs.length >= maxTabs ? "Limite de " + maxTabs + " abas" : "Nova conversa Claude";
  }

  function renderMessages(items, activeId) {
    const last = items.length ? items[items.length - 1].id : 0;
    const first = items.length ? items[0].id : 0;
    const key = activeId + ":" + items.length + ":" + first + ":" + last;
    if (key === lastMessagesKey) return;
    lastMessagesKey = key;
    const autoScroll = ui.messages.scrollTop + ui.messages.clientHeight >= ui.messages.scrollHeight - 75;
    ui.messages.replaceChildren();
    if (!activeId) {
      const placeholder = document.createElement("div");
      placeholder.className = "ct-empty";
      placeholder.textContent = "Crie uma aba para começar uma conversa independente com Claude.";
      ui.messages.appendChild(placeholder);
    } else if (!items.length) {
      const placeholder = document.createElement("div");
      placeholder.className = "ct-empty";
      placeholder.textContent = "Envie uma mensagem. Cada aba mantém seu próprio contexto, mesmo após reiniciar o JARVIS.";
      ui.messages.appendChild(placeholder);
    } else {
      items.forEach((msg) => {
        const item = document.createElement("div");
        item.className = "ct-message " + msg.role;
        const label = document.createElement("div");
        label.className = "ct-role";
        label.textContent = msg.role === "user" ? "VOCÊ" : msg.role === "error" ? "ERRO" : "CLAUDE";
        const content = document.createElement("div");
        content.className = "ct-content";
        // textContent impede executar HTML/JS gerado pelo modelo.
        content.textContent = msg.content;
        item.append(label, content);
        ui.messages.appendChild(item);
      });
    }
    if (autoScroll || !first) ui.messages.scrollTop = ui.messages.scrollHeight;
  }

  function renderUsage(usage) {
    if (!ui.metrics) return;
    const panels = [
      ["ESTA ABA", usage.selected],
      ["HOJE (UTC)", usage.today],
      ["ÚLTIMOS 7 DIAS", usage.last_7_days],
      ["TOTAL REGISTRADO", usage.all_time],
    ];
    const signature = JSON.stringify(panels);
    if (signature === lastUsageKey) return;
    lastUsageKey = signature;
    ui.metrics.replaceChildren();
    const fmt = (value) => Number(value || 0).toLocaleString("pt-BR");
    panels.forEach(([label, data]) => {
      const stats = data || {};
      const tokenCount = (stats.input_tokens || 0) + (stats.output_tokens || 0)
        + (stats.cache_read_tokens || 0) + (stats.cache_creation_tokens || 0);
      const cell = document.createElement("div");
      cell.className = "ct-metric";
      const heading = document.createElement("div");
      heading.className = "ct-metric-label";
      heading.textContent = label;
      const value = document.createElement("div");
      value.className = "ct-metric-value";
      value.textContent = fmt(tokenCount) + " tokens";
      const detail = document.createElement("div");
      detail.className = "ct-metric-detail";
      detail.textContent = fmt(stats.requests) + " consultas · entrada "
        + fmt(stats.input_tokens) + " · saída " + fmt(stats.output_tokens)
        + " · cache L/E " + fmt(stats.cache_read_tokens)
        + "/" + fmt(stats.cache_creation_tokens);
      cell.append(heading, value, detail);
      ui.metrics.appendChild(cell);
    });
    const info = document.createElement("div");
    info.className = "ct-metric-note";
    info.textContent = "Consumo registrado neste JARVIS. A cota restante diária/semanal do Claude Max não é fornecida por esta integração.";
    ui.metrics.appendChild(info);
  }

  async function refresh() {
    if (!api() || refreshPending || !ui.page.classList.contains("active")) return;
    refreshPending = true;
    try {
      const snap = await api().claude_tabs_snapshot(selected);
      if (!snap.ok) { error(snap.error); return; }
      selected = snap.selected_id;
      renderTabs(snap.tabs, selected, snap.max_tabs);
      renderMessages(snap.messages, selected);
      renderUsage(snap.usage || {});
      const tab = snap.tabs.find((t) => t.id === selected);
      ui.send.disabled = !snap.installed || !selected || !!(tab && tab.busy);
      ui.cancel.disabled = !selected || !(tab && tab.busy);
      ui.input.disabled = !snap.installed || !selected;
      ui.tip.textContent = snap.installed
        ? "Claude Code detectado. Use o login da assinatura Max no terminal; as abas não usam ANTHROPIC_API_KEY."
        : "Claude Code não encontrado. Instale-o e execute claude auth login no terminal.";
      if (tab && tab.busy) {
        notice("Claude está respondendo nesta aba. Outras abas continuam disponíveis.");
      } else if (!ui.status.classList.contains("error")) {
        notice("Sessões persistentes · Modo conversa (sem execução de ferramentas)");
      }
    } catch (_err) {
      error("Falha ao consultar sessões do Claude.");
    } finally {
      refreshPending = false;
    }
  }

  ui.create.addEventListener("click", async () => {
    if (!api()) return;
    try {
      const result = await api().claude_tabs_create("Nova conversa", ui.model.value);
      if (!result.ok) { error(result.error); return; }
      selected = result.id;
      lastMessagesKey = "";
      notice("Nova aba criada.");
      refresh();
    } catch (_err) { error("Não foi possível criar a aba."); }
  });

  async function send() {
    if (!api() || !selected) return;
    const text = ui.input.value.trim();
    if (!text) return;
    ui.send.disabled = true;
    try {
      const result = await api().claude_tabs_send(selected, text);
      if (!result.ok) { error(result.error); return; }
      ui.input.value = "";
      lastMessagesKey = "";
      notice("Mensagem enviada. Claude está processando...");
      refresh();
    } catch (_err) {
      error("Falha ao enviar mensagem ao Claude.");
    } finally {
      // refresh() sincroniza o estado real da aba (busy).
      setTimeout(refresh, 100);
    }
  }
  ui.send.addEventListener("click", send);
  ui.cancel.addEventListener("click", async () => {
    if (!api() || !selected) return;
    ui.cancel.disabled = true;
    try {
      const result = await api().claude_tabs_cancel(selected);
      if (!result.ok) error(result.error);
      else notice("Cancelamento solicitado. Aguardando encerramento do processo...");
      refresh();
    } catch (_err) {
      error("Não foi possível cancelar a execução.");
    }
  });
  ui.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  });

  function init() {
    if (initialized) return;
    initialized = true;
    refresh();
    setInterval(() => {
      if (ui.page.classList.contains("active")) refresh();
    }, 1200);
  }
  if (api()) init();
  else window.addEventListener("pywebviewready", init);
})();
