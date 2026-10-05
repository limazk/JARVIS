/*
 * Lógica da interface web do Jarvis — fala com o Python só através de
 * `window.pywebview.api.*` (injetado pelo pywebview depois que a
 * página carrega — ver o listener de "pywebviewready" no fim deste
 * arquivo), com um modelo de POLLING: a cada ~1s chama
 * `get_snapshot()`/`get_messages()` e atualiza a tela, em vez de
 * esperar o Python "empurrar" dados (mais simples e robusto do que
 * `window.evaluate_js()` chamado de threads em segundo plano — ver o
 * comentário no topo de interface_web/bridge.py).
 */
(() => {
  "use strict";

  const STATE_LABELS = {
    OFFLINE: "OFFLINE",
    ONLINE: "ONLINE",
    LISTENING: "OUVINDO",
    PROCESSING: "PROCESSANDO",
    EXECUTING: "EXECUTANDO",
    SPEAKING: "FALANDO",
    ERROR: "ERRO",
  };

  const COLOR_PURPLE = "#6232DD";
  const COLOR_PURPLE_LIGHT = "#B891F8";
  const COLOR_TEXT_DIM = "#8B84A3";
  const COLOR_ERROR = "#EF4444";

  const STATE_COLORS = {
    OFFLINE: COLOR_TEXT_DIM,
    ONLINE: COLOR_PURPLE_LIGHT,
    LISTENING: COLOR_PURPLE,
    PROCESSING: COLOR_PURPLE,
    EXECUTING: COLOR_PURPLE,
    SPEAKING: COLOR_PURPLE_LIGHT,
    ERROR: COLOR_ERROR,
  };

  const SPEED_BY_STATE = {
    PROCESSING: 3.2,
    EXECUTING: 2.6,
    SPEAKING: 4.0,
    LISTENING: 2.0,
  };

  const POLL_MS = 1000;
  const HISTORY_POINTS = 45;

  // ==================================================================
  // Orbe central — "esfera neural" inspirada de perto na referência
  // visual do usuário: uma esfera de partículas conectadas (rede
  // neural) rotacionando em 3D (projeção simples, sem biblioteca),
  // atravessada por 4 grandes anéis (círculos máximos, tipo esfera
  // armilar) e por dois "raios" horizontal/vertical em forma de
  // estrela de difração (o traço mais característico da referência),
  // com um núcleo brilhante no centro. Brilho de verdade via
  // shadowBlur — o motivo original de abandonar o CustomTkinter, que
  // nunca desenhou nada disso.
  // ==================================================================
  class Orb {
    constructor(canvas) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.tick = 0;
      this.state = "ONLINE";
      this._raf = null;
      this._loop = this._loop.bind(this);

      // Partículas distribuídas uniformemente numa esfera (coordenadas
      // esféricas fixas) — a rotação é só o ângulo `theta` avançando
      // com o tempo, então a "rede" gira em bloco, rígida, em vez de
      // recalcular posições aleatórias a cada quadro.
      const COUNT = 110;
      this._particles = Array.from({ length: COUNT }, () => ({
        phi: Math.acos(2 * Math.random() - 1), // 0..PI (latitude)
        theta0: Math.random() * Math.PI * 2, // longitude inicial
      }));

      // Conecta cada partícula às mais próximas (por distância no vetor
      // 3D unitário inicial) — fixo, pra parecer uma malha geodésica
      // densa de verdade (como na referência) em vez de linhas
      // aleatórias piscando.
      this._edges = [];
      const vec3 = (p) => [Math.sin(p.phi) * Math.cos(p.theta0), Math.cos(p.phi), Math.sin(p.phi) * Math.sin(p.theta0)];
      const vectors = this._particles.map(vec3);
      for (let i = 0; i < COUNT; i++) {
        const dists = [];
        for (let j = 0; j < COUNT; j++) {
          if (i === j) continue;
          const dx = vectors[i][0] - vectors[j][0];
          const dy = vectors[i][1] - vectors[j][1];
          const dz = vectors[i][2] - vectors[j][2];
          dists.push([j, dx * dx + dy * dy + dz * dz]);
        }
        dists.sort((a, b) => a[1] - b[1]);
        for (let k = 0; k < 4; k++) {
          const pair = [i, dists[k][0]].sort((a, b) => a - b);
          if (!this._edges.some((e) => e[0] === pair[0] && e[1] === pair[1])) {
            this._edges.push(pair);
          }
        }
      }

      // Buffer fora da tela onde a cena é desenhada nítida antes de
      // virar a base do "bloom" (ver _loop) — criado sob demanda no
      // tamanho certo porque o canvas real só sabe seu tamanho no CSS
      // depois de estar no DOM.
      this._buf = null;
    }

    setState(state) {
      this.state = state;
    }

    start() {
      this._loop();
    }

    stop() {
      if (this._raf) cancelAnimationFrame(this._raf);
    }

    _loop(now) {
      this._raf = requestAnimationFrame(this._loop);

      // Em Chromium headless (sem vsync) requestAnimationFrame pode
      // disparar muito acima de 60fps, o que só desperdiça CPU numa
      // esfera que gira devagar — limita o redesenho a ~30fps de verdade.
      const ts = now || performance.now();
      if (this._lastDraw != null && ts - this._lastDraw < 33) return;
      this._lastDraw = ts;
      this.tick += 1;

      const { ctx, canvas } = this;
      const size = Math.min(canvas.clientWidth || canvas.width, canvas.clientHeight || canvas.height);
      if (canvas.width !== size || canvas.height !== size) {
        canvas.width = size;
        canvas.height = size;
      }
      const cx = size / 2;
      const cy = size / 2;
      const baseR = size * 0.34;
      const speed = SPEED_BY_STATE[this.state] || 1.0;
      const color = STATE_COLORS[this.state] || COLOR_PURPLE;
      const t = this.tick / 30;

      ctx.clearRect(0, 0, size, size);
      this._drawScene(ctx, size, cx, cy, baseR, speed, color, t);
    }

    _drawScene(ctx, size, cx, cy, baseR, speed, color, t) {
      // Halo geral bem suave delimitando o volume da esfera.
      const halo = ctx.createRadialGradient(cx, cy, baseR * 0.2, cx, cy, baseR * 1.1);
      halo.addColorStop(0, hexToRgba(color, 0.1));
      halo.addColorStop(1, hexToRgba(color, 0));
      ctx.fillStyle = halo;
      ctx.beginPath();
      ctx.arc(cx, cy, baseR * 1.1, 0, Math.PI * 2);
      ctx.fill();

      // A partir daqui, mistura aditiva ("lighter"): onde vários anéis,
      // linhas da malha e os raios se cruzam, a luz se acumula em vez
      // de sobrepor — é o que dá o efeito de brilho/bloom denso da
      // referência em vez de linhas planas por cima umas das outras.
      ctx.save();
      ctx.globalCompositeOperation = "lighter";

      // 9 grandes anéis (círculos máximos) tipo esfera armilar — cada
      // um é um círculo de raio `baseR` visto de um ângulo diferente
      // (achatado no eixo Y pelo cosseno da inclinação), girando devagar
      // em velocidades levemente diferentes pra nunca ficarem alinhados
      // — quantidade pensada pra cobrir a esfera de fios finos como na
      // referência, sem virar um círculo sólido.
      const ringTilts = [0, Math.PI / 2, Math.PI / 4, -Math.PI / 4, Math.PI / 3, -Math.PI / 6, Math.PI / 6, -Math.PI / 3, (5 * Math.PI) / 12];
      ringTilts.forEach((tilt, i) => {
        const rot = t * speed * (0.09 + i * 0.02) * (i % 2 === 0 ? 1 : -1);
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(rot);
        ctx.strokeStyle = hexToRgba(color, 0.26);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.ellipse(0, 0, baseR, baseR * Math.abs(Math.cos(tilt)) + baseR * 0.05, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      });

      // Rede de partículas — projeção 3D->2D simples (ortográfica,
      // rotação em torno do eixo vertical), com profundidade (z)
      // controlando brilho/tamanho pra dar sensação de esfera de verdade.
      const projected = this._particles.map((p) => {
        const theta = p.theta0 + t * speed * 0.12;
        const x3 = Math.sin(p.phi) * Math.cos(theta);
        const y3 = Math.cos(p.phi);
        const z3 = Math.sin(p.phi) * Math.sin(theta);
        return {
          x: cx + x3 * baseR,
          y: cy + y3 * baseR,
          depth: (z3 + 1) / 2, // 0 (atrás) .. 1 (na frente)
        };
      });

      ctx.lineWidth = 0.6;
      this._edges.forEach(([i, j]) => {
        const a = projected[i];
        const b = projected[j];
        const alpha = 0.05 + 0.24 * ((a.depth + b.depth) / 2);
        ctx.strokeStyle = hexToRgba(color, alpha);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
      });

      projected.forEach((p) => {
        const r = size * (0.0025 + p.depth * 0.0055);
        ctx.fillStyle = hexToRgba("#ffffff", 0.2 + p.depth * 0.55);
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
      });

      // Os dois "raios" — estrela de difração horizontal/vertical
      // cruzando o núcleo, o traço mais reconhecível da referência.
      // Duas camadas por eixo: um brilho largo suave por baixo e um
      // filete fino e muito brilhante por cima, pra dar a ponta afiada
      // em losango que a referência tem (em vez de uma linha só).
      [0, Math.PI / 2].forEach((axis) => {
        const len = baseR * 2.7;
        const dx = Math.cos(axis);
        const dy = Math.sin(axis);
        const x0 = cx - dx * len;
        const y0 = cy - dy * len;
        const x1 = cx + dx * len;
        const y1 = cy + dy * len;

        [
          { width: size * 0.02, blur: size * 0.09, peak: 0.35 },
          { width: size * 0.004, blur: size * 0.05, peak: 1 },
        ].forEach(({ width, blur, peak }) => {
          const grad = ctx.createLinearGradient(x0, y0, x1, y1);
          grad.addColorStop(0, hexToRgba(color, 0));
          grad.addColorStop(0.43, hexToRgba(color, 0));
          grad.addColorStop(0.5, hexToRgba("#ffffff", peak));
          grad.addColorStop(0.57, hexToRgba(color, 0));
          grad.addColorStop(1, hexToRgba(color, 0));
          ctx.save();
          ctx.strokeStyle = grad;
          ctx.lineWidth = width;
          ctx.shadowColor = color;
          ctx.shadowBlur = blur;
          ctx.beginPath();
          ctx.moveTo(x0, y0);
          ctx.lineTo(x1, y1);
          ctx.stroke();
          ctx.restore();
        });
      });

      // Núcleo: anéis concêntricos finos + glow real (shadowBlur),
      // pulsando conforme o estado do agente.
      const pulse = Math.sin(t * speed * 3) * (size * 0.01);
      const coreR = Math.max(4, baseR * 0.22 + pulse);

      [2.3, 1.9, 1.4].forEach((mult, i) => {
        ctx.save();
        ctx.strokeStyle = hexToRgba(color, 0.45 - i * 0.1);
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(cx, cy, coreR * mult, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      });

      const gradient = ctx.createRadialGradient(cx, cy, coreR * 0.05, cx, cy, coreR * 1.3);
      gradient.addColorStop(0, "#ffffff");
      gradient.addColorStop(0.4, color);
      gradient.addColorStop(1, "rgba(0,0,0,0)");

      ctx.save();
      ctx.shadowColor = color;
      ctx.shadowBlur = size * 0.18;
      ctx.beginPath();
      ctx.fillStyle = gradient;
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      ctx.restore(); // fecha o globalCompositeOperation = "lighter"

      this._raf = requestAnimationFrame(this._loop);
    }
  }

  function hexToRgba(hex, alpha) {
    const h = hex.replace("#", "");
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  // ==================================================================
  // Gráfico multi-série (histórico curto de CPU/RAM/disco) — os
  // valores em si vêm sempre do backend (psutil); este objeto só
  // guarda os últimos N pontos em memória no front-end pra desenhar.
  // ==================================================================
  class MultiLineChart {
    constructor(canvas, series) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.series = series; // [{key, color}]
      this.history = {};
      series.forEach((s) => (this.history[s.key] = []));
    }

    push(values) {
      this.series.forEach((s) => {
        const v = values[s.key];
        const arr = this.history[s.key];
        arr.push(v == null ? null : v);
        if (arr.length > HISTORY_POINTS) arr.shift();
      });
      this._draw();
    }

    _draw() {
      const canvas = this.canvas;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 200;
      const h = canvas.clientHeight || 84;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      const ctx = this.ctx;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      // grade horizontal discreta
      ctx.strokeStyle = "rgba(255,255,255,0.05)";
      ctx.lineWidth = 1;
      [0.25, 0.5, 0.75].forEach((f) => {
        ctx.beginPath();
        ctx.moveTo(0, h * f);
        ctx.lineTo(w, h * f);
        ctx.stroke();
      });

      const step = w / (HISTORY_POINTS - 1);

      this.series.forEach((s) => {
        const values = this.history[s.key];
        if (values.length < 2) return;
        const offset = HISTORY_POINTS - values.length;

        ctx.beginPath();
        let started = false;
        values.forEach((v, i) => {
          if (v == null) return;
          const x = (offset + i) * step;
          const y = h - (v / 100) * h;
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        });
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 1.4;
        ctx.shadowColor = s.color;
        ctx.shadowBlur = 4;
        ctx.stroke();
        ctx.shadowBlur = 0;
      });
    }
  }

  // ==================================================================
  // Ondinha simples (histórico de RAM) — estilo "waveform" da referência.
  // ==================================================================
  class Waveform {
    constructor(canvas, color) {
      this.canvas = canvas;
      this.ctx = canvas.getContext("2d");
      this.color = color;
      this.values = [];
    }

    push(v) {
      if (v == null) return;
      this.values.push(v);
      if (this.values.length > 60) this.values.shift();
      this._draw();
    }

    _draw() {
      const canvas = this.canvas;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth || 200;
      const h = canvas.clientHeight || 34;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      const ctx = this.ctx;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      if (!this.values.length) return;

      const barW = w / 60;
      const offset = 60 - this.values.length;
      this.values.forEach((v, i) => {
        const barH = Math.max(2, (v / 100) * h);
        const x = (offset + i) * barW;
        ctx.fillStyle = this.color;
        ctx.globalAlpha = 0.35 + (i / this.values.length) * 0.5;
        ctx.fillRect(x, h - barH, barW * 0.6, barH);
      });
      ctx.globalAlpha = 1;
    }
  }

  // ==================================================================
  // Estado da aplicação / referências de DOM
  // ==================================================================
  const el = (id) => document.getElementById(id);

  const dom = {
    hudDate: el("hud-date"),
    hudTime: el("hud-time"),
    hudBreadcrumb: el("hud-breadcrumb"),
    statusDot: el("status-dot"),
    statusLabel: el("status-label"),
    footerStatus: el("footer-status"),
    mCpu: el("m-cpu"),
    mRam: el("m-ram"),
    mDisco: el("m-disco"),
    segCpu: el("seg-cpu"),
    segRam: el("seg-ram"),
    segDisco: el("seg-disco"),
    memUsed: el("mem-used"),
    memTotal: el("mem-total"),
    memPct: el("mem-pct"),
    memBar: el("mem-bar"),
    memBUsed: el("mem-b-used"),
    memBAvail: el("mem-b-avail"),
    memBTotal: el("mem-b-total"),
    procTbody: el("proc-tbody"),
    coreSub: el("core-sub"),
    coreTagline: el("core-tagline"),
    coreStatModules: el("core-stat-modules"),
    coreStatUptime: el("core-stat-uptime"),
    coreStatMsgs: el("core-stat-msgs"),
    coreStatClock: el("core-stat-clock"),
    healthList: el("health-list"),
    moduleList: el("module-list"),
    activityList: el("activity-list"),
    chatBadge: el("chat-badge"),
    voiceToggle: el("voice-toggle"),
    autostartRow: el("autostart-row"),
    autostartToggle: el("autostart-toggle"),
    trayNote: el("tray-note"),
    wakeWordSub: el("wake-word-sub"),
    netRecv: el("net-recv"),
    netSent: el("net-sent"),
    storageUsed: el("storage-used"),
    storageTotal: el("storage-total"),
    storagePct: el("storage-pct"),
    storageRowUsed: el("storage-row-used"),
    storageRowFree: el("storage-row-free"),
    chatMessages: el("chat-messages"),
    chatInput: el("chat-input"),
    sendBtn: el("send-btn"),
    micBtn: el("mic-btn"),
    chatStateLabel: el("chat-state-label"),
    confirmOverlay: el("confirm-overlay"),
    confirmMessage: el("confirm-message"),
    confirmOk: el("confirm-ok"),
    confirmCancel: el("confirm-cancel"),
    settingsOverlay: el("settings-overlay"),
    providerList: el("provider-list"),
    providerHint: el("provider-hint"),
    apiKeyInput: el("api-key-input"),
    settingsStatus: el("settings-status"),
    settingsSave: el("settings-save"),
    settingsCancel: el("settings-cancel"),
    settingsBtn: el("settings-btn"),
  };

  const orbOverview = new Orb(el("orb-overview"));
  const orbChat = new Orb(el("orb-chat"));
  const metricsChart = new MultiLineChart(el("chart-metrics"), [
    { key: "cpu", color: COLOR_PURPLE_LIGHT },
    { key: "ram", color: COLOR_PURPLE },
    { key: "disco", color: COLOR_TEXT_DIM },
  ]);
  const memWave = new Waveform(el("mem-wave"), COLOR_PURPLE_LIGHT);
  const netChart = new MultiLineChart(el("net-chart"), [
    { key: "recv", color: COLOR_PURPLE_LIGHT },
    { key: "sent", color: COLOR_TEXT_DIM },
  ]);

  let currentPage = "overview";
  let lastMessageId = 0;
  let currentConfirmationId = null;
  let llmConfigCache = null;
  let hasAutoOpenedSettings = false;
  let voiceTogglePending = false;
  let autostartTogglePending = false;
  let maxNetKbps = 20; // escala dinâmica do gráfico de rede (cresce conforme o uso real)

  // ------------------------------------------------------------------
  // Relógio local (não depende do polling — atualiza a cada segundo)
  // ------------------------------------------------------------------
  function tickClock() {
    const now = new Date();
    dom.hudDate.textContent = now.toLocaleDateString("pt-BR", { day: "2-digit", month: "short", year: "numeric" });
    dom.hudTime.textContent = now.toLocaleTimeString("pt-BR", { hour12: false });
    if (dom.coreStatClock) dom.coreStatClock.textContent = now.toLocaleTimeString("pt-BR", { hour12: false, hour: "2-digit", minute: "2-digit" });
  }
  setInterval(tickClock, 1000);
  tickClock();

  // ------------------------------------------------------------------
  // Navegação entre páginas
  // ------------------------------------------------------------------
  const BREADCRUMBS = {
    overview: '<span>PAINEL</span><span class="sep">///</span><span>DIAGNÓSTICO DO SISTEMA</span><span class="sep">|</span><span class="step now">OBSERVAR</span><span class="sep">&gt;</span><span class="step">ANALISAR</span><span class="sep">&gt;</span><span class="step">OTIMIZAR</span><span class="sep">&gt;</span><span class="step">EVOLUIR</span>',
    chat: '<span>PAINEL</span><span class="sep">///</span><span>CANAL DE COMUNICAÇÃO</span><span class="sep">|</span><span class="step">TEXTO</span><span class="sep">&gt;</span><span class="step now">VOZ</span><span class="sep">&gt;</span><span class="step">RESPOSTA</span>',
  };

  function showPage(key) {
    currentPage = key;
    document.querySelectorAll(".nav-item[data-page]").forEach((n) => {
      n.classList.toggle("active", n.dataset.page === key);
    });
    document.querySelectorAll(".page").forEach((p) => {
      p.classList.toggle("active", p.id === `page-${key}`);
    });
    dom.hudBreadcrumb.innerHTML = BREADCRUMBS[key] || BREADCRUMBS.overview;
    window.pywebview.api.set_page(key);
    if (key === "chat") {
      dom.chatBadge.classList.remove("show");
      scrollChatToBottom();
    }
  }

  document.querySelectorAll(".nav-item[data-page]").forEach((n) => {
    n.addEventListener("click", () => showPage(n.dataset.page));
  });

  // ------------------------------------------------------------------
  // Barras segmentadas (CPU/RAM/disco)
  // ------------------------------------------------------------------
  const SEGMENTS = 16;
  function buildSegbar(container) {
    container.innerHTML = "";
    for (let i = 0; i < SEGMENTS; i++) {
      const seg = document.createElement("span");
      seg.className = "seg";
      container.appendChild(seg);
    }
  }
  [dom.segCpu, dom.segRam, dom.segDisco].forEach(buildSegbar);

  function fillSegbar(container, percent) {
    const filled = Math.round(((percent || 0) / 100) * SEGMENTS);
    Array.from(container.children).forEach((seg, i) => {
      seg.classList.toggle("filled", i < filled);
    });
  }

  // ------------------------------------------------------------------
  // Snapshot (estado geral) — polling
  // ------------------------------------------------------------------
  function formatUptime(seconds) {
    const s = Math.floor(seconds || 0);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h${String(m).padStart(2, "0")}m`;
    return `${m}m`;
  }

  function applySnapshot(snap) {
    const label = STATE_LABELS[snap.state] || snap.state;
    dom.statusLabel.textContent = label;
    const color = STATE_COLORS[snap.state] || COLOR_PURPLE;
    dom.statusDot.style.background = color;
    dom.statusDot.style.boxShadow = `0 0 10px ${color}`;
    orbOverview.setState(snap.state);
    orbChat.setState(snap.state);
    dom.chatStateLabel.textContent = label;
    dom.coreSub.textContent = snap.state === "ERROR" ? "ERRO DETECTADO" : "ARQUITETURA NEURAL ONLINE";
    dom.footerStatus.textContent = snap.state === "ERROR" ? "FALHA EM UM COMPONENTE" : "TODOS OS SISTEMAS OPERACIONAIS";

    const stats = snap.stats || {};
    dom.mCpu.textContent = stats.cpu != null ? `${Math.round(stats.cpu)}%` : "--%";
    dom.mRam.textContent = stats.ram != null ? `${Math.round(stats.ram)}%` : "--%";
    dom.mDisco.textContent = stats.disco != null ? `${Math.round(stats.disco)}%` : "--%";
    fillSegbar(dom.segCpu, stats.cpu);
    fillSegbar(dom.segRam, stats.ram);
    fillSegbar(dom.segDisco, stats.disco);
    metricsChart.push({ cpu: stats.cpu, ram: stats.ram, disco: stats.disco });

    if (stats.ram_used_gb != null) {
      dom.memUsed.textContent = `${stats.ram_used_gb} GB`;
      dom.memTotal.textContent = `${stats.ram_total_gb} GB`;
      dom.memPct.textContent = `${Math.round(stats.ram)}%`;
      dom.memBar.style.width = `${Math.min(100, stats.ram)}%`;
      dom.memBUsed.textContent = `${stats.ram_used_gb} GB`;
      dom.memBAvail.textContent = `${(stats.ram_total_gb - stats.ram_used_gb).toFixed(1)} GB`;
      dom.memBTotal.textContent = `${stats.ram_total_gb} GB`;
      memWave.push(stats.ram);
    }

    if (stats.disco_used_gb != null) {
      dom.storageUsed.textContent = `${stats.disco_used_gb} GB`;
      dom.storageTotal.textContent = `${stats.disco_total_gb} GB`;
      dom.storagePct.textContent = `${Math.round(stats.disco)}%`;
      dom.storageRowUsed.textContent = `${stats.disco_used_gb} GB`;
      dom.storageRowFree.textContent = `${(stats.disco_total_gb - stats.disco_used_gb).toFixed(1)} GB`;
      drawDonut(stats.disco);
    }

    if (stats.net_recv_kbps != null) {
      dom.netRecv.textContent = formatKbps(stats.net_recv_kbps);
      dom.netSent.textContent = formatKbps(stats.net_sent_kbps);
      maxNetKbps = Math.max(maxNetKbps, stats.net_recv_kbps, stats.net_sent_kbps);
      netChart.push({
        recv: (stats.net_recv_kbps / maxNetKbps) * 100,
        sent: (stats.net_sent_kbps / maxNetKbps) * 100,
      });
    }

    renderProcesses(snap.process_rows || []);
    renderModulesSplit(snap.module_rows || []);
    renderActivity(snap.activity_rows || []);

    const okCount = (snap.module_rows || []).filter((r) => r.ok).length;
    dom.coreStatModules.textContent = `${okCount}/${(snap.module_rows || []).length}`;
    dom.coreStatUptime.textContent = formatUptime(snap.uptime_seconds);
    dom.coreStatMsgs.textContent = snap.message_count != null ? String(snap.message_count) : "--";

    dom.chatBadge.classList.toggle("show", !!snap.chat_unread && currentPage !== "chat");

    if (!voiceTogglePending) dom.voiceToggle.checked = !!snap.voice_enabled;
    dom.wakeWordSub.textContent = snap.voice_enabled
      ? `ouvindo por "${snap.wake_word}"`
      : `diga "${snap.wake_word}" a qualquer momento`;

    dom.autostartRow.style.display = snap.autostart_supported ? "flex" : "none";
    if (snap.autostart_supported && !autostartTogglePending) {
      dom.autostartToggle.checked = !!snap.autostart_enabled;
    }

    dom.trayNote.textContent = snap.tray_active
      ? "Ícone na bandeja ativo — fechar a janela só minimiza."
      : "Ícone na bandeja indisponível — fechar a janela encerra o Jarvis.";

    handleConfirmation(snap.pending_confirmation);

    if (!hasAutoOpenedSettings && snap.llm_available === false) {
      hasAutoOpenedSettings = true;
      openSettings();
    }
  }

  function formatKbps(v) {
    if (v >= 1024) return `${(v / 1024).toFixed(1)} MB/s`;
    return `${v.toFixed(1)} KB/s`;
  }

  function renderProcesses(rows) {
    if (!rows.length) {
      dom.procTbody.innerHTML = '<tr><td colspan="4" class="activity-empty">Sem dados de processos.</td></tr>';
      return;
    }
    dom.procTbody.innerHTML = rows
      .map((r) => {
        const dotClass = r.status === "running" ? "running" : "sleeping";
        return `<tr>
          <td><span class="proc-dot ${dotClass}"></span>${escapeHtml(r.name)}</td>
          <td class="num">${r.cpu.toFixed(1)}%</td>
          <td class="num">${r.mem.toFixed(1)}%</td>
          <td>${escapeHtml(r.status)}</td>
        </tr>`;
      })
      .join("");
  }

  function renderModulesSplit(rows) {
    const core = rows.filter((r) => r.category !== "integration");
    const integration = rows.filter((r) => r.category === "integration");

    dom.healthList.innerHTML = core
      .map(
        (r) => `
        <div class="health-row">
          <span class="name">${escapeHtml(r.label)}</span>
          <div class="bar"><div class="fill ${r.ok ? "ok" : "off"}" style="width:${r.ok ? 100 : 10}%"></div></div>
          <span class="pct">${r.ok ? "ON" : "OFF"}</span>
        </div>`
      )
      .join("");

    dom.moduleList.innerHTML = integration
      .map(
        (r) => `
        <div class="module-row">
          <span class="module-dot ${r.ok ? "ok" : "off"}"></span>
          <span class="name">${escapeHtml(r.label)}</span>
          <span class="state ${r.ok ? "ok" : "off"} uc">${r.ok ? "ONLINE" : "OFFLINE"}</span>
        </div>`
      )
      .join("");
  }

  function renderActivity(rows) {
    if (!rows.length) {
      dom.activityList.innerHTML = '<div class="activity-empty">Nenhuma atividade registrada ainda.</div>';
      return;
    }
    dom.activityList.innerHTML = rows
      .map(
        (r) => `<div><span class="activity-time">${escapeHtml(r.time)}</span>${escapeHtml(r.description)}</div>`
      )
      .join("");
    dom.activityList.scrollTop = dom.activityList.scrollHeight;
  }

  function drawDonut(percentUsed) {
    const canvas = el("storage-donut");
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const size = 92;
    if (canvas.width !== size * dpr) {
      canvas.width = size * dpr;
      canvas.height = size * dpr;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);

    const cx = size / 2;
    const cy = size / 2;
    const r = size * 0.38;
    const lineWidth = size * 0.16;
    const usedFraction = Math.max(0, Math.min(1, (percentUsed || 0) / 100));

    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";

    ctx.beginPath();
    ctx.strokeStyle = "#1e1e28";
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    ctx.beginPath();
    ctx.strokeStyle = COLOR_PURPLE_LIGHT;
    ctx.shadowColor = COLOR_PURPLE_LIGHT;
    ctx.shadowBlur = 8;
    const start = -Math.PI / 2;
    ctx.arc(cx, cy, r, start, start + usedFraction * Math.PI * 2);
    ctx.stroke();
    ctx.shadowBlur = 0;

    ctx.fillStyle = "#f2f1f6";
    ctx.font = "600 13px 'Segoe UI', sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${Math.round(percentUsed || 0)}%`, cx, cy);
  }

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  // ------------------------------------------------------------------
  // Chat
  // ------------------------------------------------------------------
  function scrollChatToBottom() {
    dom.chatMessages.scrollTop = dom.chatMessages.scrollHeight;
  }

  function appendMessages(messages) {
    if (!messages.length) return;
    messages.forEach((m) => {
      const div = document.createElement("div");
      div.className = `msg ${m.speaker === "Você" ? "msg-user" : "msg-jarvis"}`;
      div.textContent = m.text;
      dom.chatMessages.appendChild(div);
      lastMessageId = Math.max(lastMessageId, m.id);
    });
    scrollChatToBottom();
  }

  function sendChatMessage() {
    const text = dom.chatInput.value.trim();
    if (!text) return;
    dom.chatInput.value = "";
    window.pywebview.api.send_text(text);
  }

  dom.sendBtn.addEventListener("click", sendChatMessage);
  dom.chatInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") sendChatMessage();
  });

  let micRecording = false;
  dom.micBtn.addEventListener("click", () => {
    if (micRecording) return;
    micRecording = true;
    dom.micBtn.classList.add("recording");
    window.pywebview.api.request_mic().finally(() => {
      setTimeout(() => {
        micRecording = false;
        dom.micBtn.classList.remove("recording");
      }, 4000);
    });
  });

  // ------------------------------------------------------------------
  // Automação (voz contínua / início automático)
  // ------------------------------------------------------------------
  dom.voiceToggle.addEventListener("change", () => {
    voiceTogglePending = true;
    const enabled = dom.voiceToggle.checked;
    window.pywebview.api.toggle_voice(enabled).then((result) => {
      dom.voiceToggle.checked = !!(result && result.enabled);
      voiceTogglePending = false;
    });
  });

  dom.autostartToggle.addEventListener("change", () => {
    autostartTogglePending = true;
    const enabled = dom.autostartToggle.checked;
    window.pywebview.api.toggle_autostart(enabled).then((result) => {
      dom.autostartToggle.checked = !!(result && result.enabled);
      autostartTogglePending = false;
    });
  });

  // ------------------------------------------------------------------
  // Confirmação de ações MEDIUM/HIGH/CRITICAL
  // ------------------------------------------------------------------
  function handleConfirmation(pending) {
    if (pending) {
      if (currentConfirmationId !== pending.id) {
        currentConfirmationId = pending.id;
        dom.confirmMessage.textContent = pending.message;
        dom.confirmOverlay.classList.add("show");
      }
    } else if (currentConfirmationId !== null) {
      currentConfirmationId = null;
      dom.confirmOverlay.classList.remove("show");
    }
  }

  function answerConfirmation(value) {
    if (currentConfirmationId === null) return;
    window.pywebview.api.answer_confirmation(currentConfirmationId, value);
    dom.confirmOverlay.classList.remove("show");
    currentConfirmationId = null;
  }

  dom.confirmOk.addEventListener("click", () => answerConfirmation(true));
  dom.confirmCancel.addEventListener("click", () => answerConfirmation(false));

  // ------------------------------------------------------------------
  // Configurar IA
  // ------------------------------------------------------------------
  function openSettings() {
    window.pywebview.api.get_llm_config().then((config) => {
      llmConfigCache = config;
      dom.providerList.innerHTML = config.providers
        .map(
          (p) => `
          <label class="provider-option">
            <input type="radio" name="provider" value="${p.value}" ${p.value === config.current_provider ? "checked" : ""} />
            <span>${escapeHtml(p.label)}</span>
          </label>`
        )
        .join("");
      dom.providerList.querySelectorAll('input[name="provider"]').forEach((input) => {
        input.addEventListener("change", updateProviderHint);
      });
      updateProviderHint();
      dom.apiKeyInput.value = "";
      dom.settingsStatus.textContent = "";
      dom.settingsStatus.className = "modal-status";
      dom.settingsOverlay.classList.add("show");
    });
  }

  function currentProviderEntry() {
    const value = document.querySelector('input[name="provider"]:checked');
    if (!value || !llmConfigCache) return null;
    return llmConfigCache.providers.find((p) => p.value === value.value) || null;
  }

  function updateProviderHint() {
    const entry = currentProviderEntry();
    if (!entry) return;
    if (!entry.needs_key) {
      dom.providerHint.textContent = `Não precisa de chave — instale o Ollama em ${entry.key_url} e baixe um modelo antes de usar.`;
      dom.apiKeyInput.style.display = "none";
    } else {
      dom.providerHint.textContent = `Gere sua chave (sem custo pra testar) em ${entry.key_url}`;
      dom.apiKeyInput.style.display = "block";
    }
  }

  dom.settingsBtn.addEventListener("click", openSettings);
  dom.settingsCancel.addEventListener("click", () => dom.settingsOverlay.classList.remove("show"));

  dom.settingsSave.addEventListener("click", () => {
    const entry = currentProviderEntry();
    if (!entry) return;
    window.pywebview.api.save_llm_config(entry.value, dom.apiKeyInput.value).then((result) => {
      if (result.ok) {
        dom.settingsStatus.textContent = "Salvo! Configuração recarregada.";
        dom.settingsStatus.className = "modal-status ok";
        setTimeout(() => dom.settingsOverlay.classList.remove("show"), 700);
      } else {
        dom.settingsStatus.textContent = result.error || "Não consegui salvar.";
        dom.settingsStatus.className = "modal-status error";
      }
    });
  });

  // ------------------------------------------------------------------
  // Loop de polling
  // ------------------------------------------------------------------
  function poll() {
    window.pywebview.api
      .get_snapshot()
      .then(applySnapshot)
      .catch(() => {});
    window.pywebview.api
      .get_messages(lastMessageId)
      .then(appendMessages)
      .catch(() => {});
  }

  function init() {
    orbOverview.start();
    orbChat.start();
    poll();
    setInterval(poll, POLL_MS);
  }

  if (window.pywebview && window.pywebview.api) {
    init();
  } else {
    window.addEventListener("pywebviewready", init);
  }
})();
