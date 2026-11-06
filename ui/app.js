/* QuickSwitch 控制台 —— 前端只渲染 /api/status、/api/config、/api/events 里真实存在的数据。
   读不到的字段一律显示「读取不到」或「—」，不猜测、不补样例值。 */
"use strict";

const LABEL = { mac: "Mac", win: "Windows" };
const DASH = "—";

const params = new URLSearchParams(location.search);
const token = params.get("t") || sessionStorage.getItem("quickswitch-token") || "";
if (token) sessionStorage.setItem("quickswitch-token", token);

const $ = (id) => document.getElementById(id);

function text(value) {
  if (value === null || value === undefined || value === "") return DASH;
  return String(value);
}

function block(value) {
  if (value === null || value === undefined || value === "") return "读取不到";
  return String(value);
}

function yesNo(value) {
  if (value === null || value === undefined) return DASH;
  return value ? "是" : "否";
}

function authText(auth) {
  if (!auth) return DASH;
  if (!auth.enabled) return "未启用（配置里没设 auth.secret，同网段任何程序都能发切换请求）";
  if (auth.authenticated) return "已通过（hmac-sha256）";
  if (!auth.peer) return "未通过（对端没声明校验：旧版本，或没配 auth.secret）";
  return "未通过（两端 auth.secret 不一致，对端发来的切换请求会被丢弃）";
}

function clock(iso) {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  return date.toTimeString().slice(0, 8);
}

let noticeTimer = null;

function notify(message, tone) {
  const box = $("notice");
  box.textContent = message;
  box.dataset.tone = tone || "info";
  box.hidden = false;
  if (noticeTimer) clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { box.hidden = true; }, 6000);
}

async function api(path, options) {
  const opts = Object.assign({ headers: {} }, options || {});
  opts.headers["X-QuickSwitch-Token"] = token;
  if (opts.body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const response = await fetch(path, opts);
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401) {
    throw new Error("令牌无效：请用启动日志里带 ?t= 的完整地址打开控制台");
  }
  if (!response.ok) {
    throw new Error(payload.error || ("HTTP " + response.status));
  }
  return payload;
}

/* ---------------------------------------------------------------- 配置向导 */
const SETUP_STEP_COUNT = 4;

const setupState = {
  open: false,
  step: 0,
  maxVisited: 0,
  busy: false,
  completed: false,
  persistedCompleted: false,
  currentInput: null,
};

function setupRoleFor(status) {
  const platformName = String((status && status.host && status.host.platform) || "").toLowerCase();
  if (platformName === "darwin" || platformName === "macos" || platformName === "mac") return "client";
  if (platformName === "windows" || platformName === "win") return "server";
  return (status && status.role) || "server";
}

function setupRoleText(role) {
  return role === "client" ? "client · macOS 侧" : "server · Windows 侧";
}

function setupRoleExplanation(role, platformName) {
  if (role === "client") return "macOS 自动使用 client";
  if (role === "server") return "Windows 自动使用 server";
  return "当前系统自动使用 " + text(role) + "（" + text(platformName) + "）";
}

function setSetupMessage(id, message, tone) {
  const node = $(id);
  node.textContent = message || "";
  if (tone) node.dataset.tone = tone;
  else delete node.dataset.tone;
}

function setupPeerMode() {
  const checked = document.querySelector('input[name="setupPeerMode"]:checked');
  return checked ? checked.value : "auto";
}

function syncSetupDevice(status) {
  const role = setupRoleFor(status);
  const platformName = text(status.host && status.host.platform);
  const ips = (status.host && status.host.ips) || [];
  const ipText = ips.length ? ips.join(" / ") : DASH;
  $("setupHostName").textContent = text(status.host && status.host.name);
  $("setupRoleLabel").textContent = setupRoleText(role);
  $("setupLocalIps").textContent = ipText;
  $("setupFactHost").textContent = text(status.host && status.host.name);
  $("setupFactRole").textContent = setupRoleExplanation(role, platformName);
  $("setupFactIps").textContent = ipText;
}

function renderSetupTool(status) {
  const ddc = (status && status.ddc) || {};
  const available = Boolean(ddc.tool_ok);
  $("setupToolDot").dataset.on = available ? "true" : "error";
  $("setupToolTitle").textContent = available ? "DDC 工具可用" : "DDC 工具不可用";
  $("setupToolDetail").textContent = text(ddc.tool_detail) + (ddc.tool_path ? " ｜ " + ddc.tool_path : "");
}

function renderSetupCurrent(value, meta) {
  setupState.currentInput = value === null || value === undefined ? null : Number(value);
  $("setupCurrentValue").textContent = setupState.currentInput === null ? DASH : String(setupState.currentInput);
  $("setupCurrentMeta").textContent = meta || (setupState.currentInput === null ? "尚未读取" : "未标记归属");
  updateSetupControls();
}

function syncSetupFromStatus(status) {
  if (!setupState.open || !status) return;
  syncSetupDevice(status);
  renderSetupTool(status);
  const input = status.input || {};
  if (!setupState.busy && input.value !== null && input.value !== undefined) {
    const when = input.read_at ? "上次读取 " + clock(input.read_at) : "从运行状态读取";
    renderSetupCurrent(input.value, when);
  }
}

function updateSetupControls() {
  const completed = setupState.completed;
  for (const button of document.querySelectorAll("#setupSteps .setup-step")) {
    const index = Number(button.dataset.step);
    button.disabled = setupState.busy || index > setupState.maxVisited || (completed && index !== 3);
  }
  const hasCurrent = setupState.currentInput !== null && setupState.currentInput !== undefined;
  $("setupReadInput").disabled = setupState.busy;
  $("setupProbeInputs").disabled = setupState.busy;
  $("setupAssignMac").disabled = setupState.busy || !hasCurrent;
  $("setupAssignWin").disabled = setupState.busy || !hasCurrent;
  $("setupBack").disabled = setupState.busy;
  $("setupNext").disabled = setupState.busy;
}

function setSetupBusy(on) {
  setupState.busy = Boolean(on);
  updateSetupControls();
}

function goToSetupStep(index) {
  if (setupState.busy) return;
  const next = Math.max(0, Math.min(SETUP_STEP_COUNT - 1, Number(index) || 0));
  setupState.step = next;
  setupState.maxVisited = Math.max(setupState.maxVisited, next);

  document.querySelectorAll("#setupOverlay .setup-panel").forEach((panel) => {
    panel.hidden = Number(panel.dataset.panel) !== next;
  });
  document.querySelectorAll("#setupSteps .setup-step").forEach((button) => {
    const step = Number(button.dataset.step);
    if (step === next) button.setAttribute("aria-current", "step");
    else button.removeAttribute("aria-current");
    button.dataset.state = step < setupState.maxVisited ? "done" : "todo";
  });

  $("setupProgress").textContent = String(next + 1).padStart(2, "0") + " / " +
    String(SETUP_STEP_COUNT).padStart(2, "0");
  $("setupBack").hidden = next === 0 || setupState.completed;
  $("setupNext").textContent = setupState.completed
    ? "关闭设置窗口"
    : (next === SETUP_STEP_COUNT - 1 ? "完成配置" : "继续");
  setSetupMessage("setupStepState", "");

  const activePanel = document.querySelector('#setupOverlay .setup-panel[data-panel="' + next + '"]');
  const title = activePanel && activePanel.querySelector("h2");
  if (title) {
    title.tabIndex = -1;
    document.querySelector("#setupOverlay .setup-dialog").setAttribute("aria-labelledby", title.id);
  }
  const scroll = document.querySelector("#setupOverlay .setup-scroll");
  if (scroll) scroll.scrollTop = 0;
  if (next === 3) renderSetupReview();
  updateSetupControls();
  if (title) requestAnimationFrame(() => title.focus({ preventScroll: true }));
}

function renderSetupReview() {
  const mode = setupPeerMode();
  const peer = mode === "auto"
    ? "自动发现（UDP " + text((configBase.discovery || {}).port) + "）"
    : ($("setupPeerHost").value.trim() || "尚未填写");
  const secret = $("setupSecret").value.trim();
  const macValue = $("setupMacInput").value.trim();
  const winValue = $("setupWinInput").value.trim();
  rows($("setupReview"), [
    ["本机角色", setupRoleText(setupRoleFor(lastStatus))],
    ["连接方式", peer],
    ["预共享密钥", secret ? "已设置（" + secret.length + " 个字符）" : "未设置"],
    ["Mac 输入源", macValue || DASH],
    ["Windows 输入源", winValue || DASH],
    ["DDC 工具", lastStatus && lastStatus.ddc && lastStatus.ddc.tool_ok ? "可用" : "不可用"],
  ]);
  $("setupSecretWarning").hidden = Boolean(secret);
}

function openSetupWizard() {
  if (!lastStatus || !configBase) {
    notify("运行状态或配置尚未读取完成，暂时无法打开配置向导。", "error");
    return;
  }
  const cfg = configBase;
  const peer = String(cfg.peer_host || "").trim();
  const firstRun = !(lastStatus.setup && lastStatus.setup.completed);
  const auto = firstRun || peer.toLowerCase() === "auto" ||
    Boolean((cfg.discovery || {}).enabled);

  setupState.open = true;
  setupState.step = 0;
  setupState.maxVisited = 0;
  setupState.busy = false;
  setupState.completed = false;
  setupState.persistedCompleted = Boolean(lastStatus.setup && lastStatus.setup.completed);
  setupState.currentInput = null;

  document.querySelector('input[name="setupPeerMode"][value="' + (auto ? "auto" : "manual") + '"]').checked = true;
  syncSetupChoices();
  $("setupPeerHost").value = peer && peer.toLowerCase() !== "auto" ? peer : "";
  $("setupManualField").hidden = auto;
  $("setupSecret").value = String((cfg.auth || {}).secret || "");
  $("setupSecret").type = "password";
  $("setupToggleSecret").textContent = "显示";
  $("setupMacInput").value = text((cfg.ddc || {}).mac_input) === DASH ? "" : String(cfg.ddc.mac_input);
  $("setupWinInput").value = text((cfg.ddc || {}).win_input) === DASH ? "" : String(cfg.ddc.win_input);
  $("setupDdcState").textContent = "";
  delete $("setupDdcState").dataset.tone;
  $("setupFinishState").textContent = "";
  delete $("setupFinishState").dataset.tone;
  $("setupSecretWarning").hidden = true;

  syncSetupDevice(lastStatus);
  renderSetupTool(lastStatus);
  const input = lastStatus.input || {};
  const inputMeta = input.value === null || input.value === undefined
    ? (input.error || "尚未读取")
    : (input.read_at ? "上次读取 " + clock(input.read_at) : "从运行状态读取");
  renderSetupCurrent(input.value, inputMeta);
  updateSecretState();

  $("setupOverlay").hidden = false;
  document.body.dataset.setupOpen = "true";
  goToSetupStep(0);
}

function closeSetupWizard() {
  if (setupState.busy) return;
  const wasCompleted = setupState.completed;
  setupState.open = false;
  $("setupOverlay").hidden = true;
  delete document.body.dataset.setupOpen;
  if (!wasCompleted && !setupState.persistedCompleted) {
    notify("配置尚未完成，下次启动 QuickSwitch 时会再次打开向导。", "info");
  }
}

function validateSetupStep(index) {
  setSetupMessage("setupStepState", "");
  if (index === 0 && setupPeerMode() === "manual") {
    const host = $("setupPeerHost").value.trim();
    if (!host) {
      setSetupMessage("setupStepState", "请填写另一台电脑的 IP 或主机名，或改用自动发现。", "error");
      $("setupPeerHost").focus();
      return false;
    }
  }
  if (index === 2) {
    const mac = Number($("setupMacInput").value);
    const win = Number($("setupWinInput").value);
    if (!Number.isInteger(mac) || mac < 0 || mac > 255 ||
        !Number.isInteger(win) || win < 0 || win > 255) {
      setSetupMessage("setupStepState", "Mac 与 Windows 输入源都必须是 0–255 的整数。", "error");
      return false;
    }
    if (mac === win) {
      setSetupMessage("setupStepState", "Mac 与 Windows 输入源不能相同，否则切换后画面不会变化。", "error");
      return false;
    }
  }
  return true;
}

function updateSetupPeerMode() {
  const manual = setupPeerMode() === "manual";
  syncSetupChoices();
  $("setupManualField").hidden = !manual;
  if (manual) $("setupPeerHost").focus();
}

function syncSetupChoices() {
  document.querySelectorAll("#setupOverlay .setup-choice").forEach((choice) => {
    const input = choice.querySelector('input[type="radio"]');
    choice.dataset.selected = input && input.checked ? "true" : "false";
  });
}

function updateSecretState() {
  const value = $("setupSecret").value.trim();
  const state = $("setupSecretState");
  if (!value) {
    state.textContent = "尚未设置密钥。可以生成后复制到另一台电脑。";
    state.dataset.tone = "error";
  } else if (value.length < 16) {
    state.textContent = "当前只有 " + value.length + " 个字符；建议至少 16 个，或直接点「生成」。";
    state.dataset.tone = "error";
  } else {
    state.textContent = "已填写 " + value.length + " 个字符。请把同一个值填到另一台电脑。";
    state.dataset.tone = "ok";
  }
}

function generateSetupSecret() {
  if (!window.crypto || typeof window.crypto.getRandomValues !== "function") {
    notify("当前窗口无法安全生成随机密钥，请使用命令行 --gen-secret。", "error");
    return;
  }
  const bytes = new Uint8Array(32);
  window.crypto.getRandomValues(bytes);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const secret = window.btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  $("setupSecret").value = secret;
  $("setupSecret").type = "text";
  $("setupToggleSecret").textContent = "隐藏";
  updateSecretState();
  $("setupSecret").focus();
  $("setupSecret").select();
}

async function copyText(value) {
  if (!value) return false;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch (error) {
    /* WebView 未授予剪贴板权限时走下面的兼容路径 */
  }
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  let copied = false;
  try { copied = document.execCommand("copy"); } catch (error) { copied = false; }
  field.remove();
  return copied;
}

async function copySetupSecret() {
  const value = $("setupSecret").value.trim();
  if (!value) {
    notify("密钥为空，请先生成。", "error");
    return;
  }
  const copied = await copyText(value);
  notify(copied ? "密钥已复制，请粘贴到另一台电脑的同一位置。" : "复制失败，请手动选中密钥复制。", copied ? "info" : "error");
}

async function readSetupInput() {
  if (setupState.busy) return;
  setSetupBusy(true);
  setSetupMessage("setupDdcState", "读取中：正在执行 DDC 回读 …");
  try {
    const result = await api("/api/read-input", { method: "POST", body: {} });
    if (result.value === null || result.value === undefined) {
      renderSetupCurrent(null, "工具不支持回读，或显示器没有响应");
      setSetupMessage("setupDdcState", "读取不到当前输入源；可直接填写已知的输入源数值。", "error");
    } else {
      renderSetupCurrent(result.value, "刚刚读取 · " + (result.target ? LABEL[result.target] + " 当前配置值" : "尚未标记归属"));
      setSetupMessage("setupDdcState", "已读到当前输入源 " + result.value + "，请选择它属于 Mac 还是 Windows。", "ok");
    }
  } catch (error) {
    setSetupMessage("setupDdcState", "读取失败：" + error.message, "error");
  } finally {
    setSetupBusy(false);
  }
  await refreshStatus();
}

async function probeSetupInputs() {
  if (setupState.busy) return;
  const started = Date.now();
  setSetupBusy(true);
  setSetupMessage("setupDdcState", "探测中：显示器会短暂切换几次 …");
  const ticker = setInterval(() => {
    if (!setupState.busy) return;
    setSetupMessage("setupDdcState", "探测中：已用 " + Math.round((Date.now() - started) / 1000) + " 秒，请等显示器稳定 …");
  }, 1000);
  try {
    const result = await api("/api/probe-inputs", { method: "POST", body: {} });
    const found = result.available || [];
    setSetupMessage("setupDdcState", found.length
      ? "显示器接受这些取值：" + found.join("、") + "。可读取当前值或手动填写。"
      : "没有探测到可用取值。请确认显示器已开启 DDC/CI，或手动填写已知值。",
      found.length ? "ok" : "error");
  } catch (error) {
    setSetupMessage("setupDdcState", "探测失败：" + error.message, "error");
  } finally {
    clearInterval(ticker);
    setSetupBusy(false);
  }
  await refreshStatus();
}

function assignSetupInput(target) {
  if (setupState.currentInput === null || setupState.currentInput === undefined) return;
  const field = target === "mac" ? $("setupMacInput") : $("setupWinInput");
  field.value = String(setupState.currentInput);
  setSetupMessage("setupDdcState", "已把当前值 " + setupState.currentInput + " 标记为 " + LABEL[target] + " 输入源。", "ok");
}

async function finishSetup() {
  if (!validateSetupStep(0)) {
    goToSetupStep(0);
    return;
  }
  if (!validateSetupStep(2)) {
    goToSetupStep(2);
    return;
  }
  const mode = setupPeerMode();
  const peerHost = mode === "auto" ? "auto" : $("setupPeerHost").value.trim();
  const values = {
    role: setupRoleFor(lastStatus),
    peer_host: peerHost,
    discovery: { enabled: mode === "auto" },
    auth: { secret: $("setupSecret").value.trim() },
    ddc: {
      mac_input: Number($("setupMacInput").value),
      win_input: Number($("setupWinInput").value),
    },
    setup: { completed: true },
  };

  setSetupBusy(true);
  setSetupMessage("setupFinishState", "保存中 …");
  try {
    const result = await api("/api/config", { method: "POST", body: { values } });
    setupState.completed = true;
    setupState.maxVisited = SETUP_STEP_COUNT - 1;
    renderConfig({ values: result.values, restart_prefixes: restartPrefixes });
    await refreshStatus();
    renderSetupReview();

    let message = "配置已保存。";
    if (result.restart_required) {
      message += " 需要重启生效：" + result.restart_keys.join("、") + "。";
    }
    setSetupMessage("setupFinishState", message, "ok");
    $("setupFinishNote").querySelector("strong").textContent = "下一步";
    $("setupFinishNote").querySelector("span").textContent =
      "关闭设置窗口，从菜单栏或托盘菜单选择「退出」，再重新打开 QuickSwitch。";
    $("setupBack").hidden = true;
    $("setupNext").textContent = "关闭设置窗口";
    $("setupNext").disabled = false;
    notify("配置已保存。" + (result.restart_required ? " 请重启 QuickSwitch 使连接配置生效。" : ""), "info");
  } catch (error) {
    setSetupMessage("setupFinishState", "保存失败：" + error.message, "error");
  } finally {
    setSetupBusy(false);
    updateSetupControls();
  }
}

async function handleSetupNext() {
  if (setupState.completed) {
    closeSetupWizard();
    window.setTimeout(() => {
      window.close();
      window.setTimeout(() => {
        if (!window.closed) notify("配置已保存，可以直接关闭这个设置窗口。", "info");
      }, 300);
    }, 60);
    return;
  }
  if (!validateSetupStep(setupState.step)) return;
  if (setupState.step < SETUP_STEP_COUNT - 1) {
    goToSetupStep(setupState.step + 1);
    return;
  }
  await finishSetup();
}

function bindSetupWizard() {
  $("btnSetupWizard").addEventListener("click", openSetupWizard);
  $("setupClose").addEventListener("click", closeSetupWizard);
  $("setupBack").addEventListener("click", () => goToSetupStep(setupState.step - 1));
  $("setupNext").addEventListener("click", handleSetupNext);
  $("setupSteps").addEventListener("click", (event) => {
    const button = event.target.closest(".setup-step");
    if (!button || button.disabled) return;
    goToSetupStep(Number(button.dataset.step));
  });
  document.querySelectorAll('input[name="setupPeerMode"]').forEach((input) => {
    input.addEventListener("change", updateSetupPeerMode);
  });
  $("setupSecret").addEventListener("input", updateSecretState);
  $("setupToggleSecret").addEventListener("click", () => {
    const secret = $("setupSecret");
    const showing = secret.type === "text";
    secret.type = showing ? "password" : "text";
    $("setupToggleSecret").textContent = showing ? "显示" : "隐藏";
  });
  $("setupGenerateSecret").addEventListener("click", generateSetupSecret);
  $("setupCopySecret").addEventListener("click", copySetupSecret);
  $("setupReadInput").addEventListener("click", readSetupInput);
  $("setupProbeInputs").addEventListener("click", probeSetupInputs);
  $("setupAssignMac").addEventListener("click", () => assignSetupInput("mac"));
  $("setupAssignWin").addEventListener("click", () => assignSetupInput("win"));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && setupState.open && !setupState.busy) closeSetupWizard();
  });
}

/* ---------------------------------------------------------------- 状态渲染 */
function rows(target, entries) {
  target.textContent = "";
  for (const [label, value] of entries) {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (value instanceof Node) dd.appendChild(value);
    else dd.textContent = value;
    row.append(dt, dd);
    target.appendChild(row);
  }
}

function dot(on) {
  const span = document.createElement("span");
  span.className = "dot";
  span.dataset.on = on ? "true" : "false";
  return span;
}

function flag(text, on) {
  const wrap = document.createElement("span");
  wrap.append(dot(on), document.createTextNode(text));
  return wrap;
}

let lastStatus = null;
let pendingTarget = null;

function renderOwnership(status) {
  const local = status.role === "server" ? "win" : "mac";
  const peerInfo = (status.peer && status.peer.info) || null;
  const input = status.input || {};
  const owner = input.target || null;

  const names = {};
  const platforms = {};
  for (const side of ["mac", "win"]) {
    const isLocal = side === local;
    names[side] = isLocal ? status.host.name : (peerInfo && peerInfo.name) || null;
    platforms[side] = isLocal ? status.host.platform : (peerInfo && peerInfo.platform) || null;
  }

  $("ownerMacHost").textContent = block(names.mac) + " · " + text(platforms.mac);
  $("ownerWinHost").textContent = block(names.win) + " · " + text(platforms.win);
  $("ownerMacValue").textContent = text(status.ddc.mac_input);
  $("ownerWinValue").textContent = text(status.ddc.win_input);
  $("ownerMac").dataset.owner = owner === "mac" && !pendingTarget ? "true" : "false";
  $("ownerWin").dataset.owner = owner === "win" && !pendingTarget ? "true" : "false";

  const rail = $("rail");
  const target = pendingTarget || owner || "mac";
  rail.dataset.target = target === "win" ? "win" : "mac";
  rail.dataset.live = pendingTarget || owner ? "true" : "false";
  rail.dataset.pending = pendingTarget ? "true" : "false";

  const state = $("ownershipState");
  if (pendingTarget) {
    state.textContent = "切换中：正在切到 " + LABEL[pendingTarget] + "（等待本机 DDC 与对端确认）";
  } else if (owner) {
    state.textContent =
      "当前持有：" + LABEL[owner] + " ｜ 显示器输入源 " + text(input.value) +
      " ｜ 读取于 " + clock(input.read_at);
  } else if (input.error) {
    state.textContent = "读取不到当前输入源（" + input.error + "）";
  } else if (input.read_at) {
    state.textContent = "读取不到当前输入源 ｜ 上次读取于 " + clock(input.read_at) +
      " ｜ 该工具或显示器不支持回读 VCP 0x60，可配置 ddc.read_template";
  } else {
    state.textContent = "读取不到当前输入源（尚未执行过回读，点「读取当前输入源」或用 --status 核对）";
  }
}

function switchSummary(status, target) {
  const owner = status.input && status.input.target;
  const parts = [owner ? "当前：" + LABEL[owner] : "当前输入源未知"];
  if (status.peer) parts.push(status.peer.connected ? "对端已连接" : "对端未连接");
  if (status.auth) {
    if (!status.auth.enabled) parts.push("未设置预共享密钥");
    else if (!status.auth.authenticated) parts.push("密钥校验未通过");
  }
  if (status.ddc && !status.ddc.tool_ok) parts.push("DDC 工具不可用");
  const hotkey = status.hotkeys &&
    status.hotkeys[target === "mac" ? "switch_to_mac" : "switch_to_win"];
  if (hotkey) parts.push("快捷键 " + hotkey);
  return "切到 " + LABEL[target] + "\n" + parts.join(" · ");
}

function renderSwitchboard(status) {
  const owner = status.input && status.input.target;
  for (const target of ["mac", "win"]) {
    const button = $(target === "mac" ? "btnMac" : "btnWin");
    const summary = switchSummary(status, target);
    const hotkeys = status.hotkeys || {};
    const combo = String(hotkeys[target === "mac" ? "switch_to_mac" : "switch_to_win"] || "").trim();
    const shortcut = $(target === "mac" ? "hotkeyMac" : "hotkeyWin");
    shortcut.textContent = "";
    shortcut.hidden = !combo;
    shortcut.dataset.registered = hotkeys.registered ? "true" : "false";
    shortcut.title = combo
      ? "切换热键：" + combo + (hotkeys.registered ? "（本机已注册）" : "（本机未注册，Windows server 端生效）")
      : "";
    shortcut.setAttribute("aria-label", combo ? "切换热键 " + combo : "");
    if (combo) {
      for (const part of combo.split("+")) {
        if (!part.trim()) continue;
        const key = document.createElement("kbd");
        key.textContent = part.trim();
        shortcut.appendChild(key);
      }
    }
    button.title = summary;
    button.setAttribute("aria-label", summary.replace(/\n/g, "，"));
    button.dataset.current = owner === target && !pendingTarget ? "true" : "false";
  }
}

function renderStatus(status) {
  lastStatus = status;
  renderSwitchboard(status);
  $("metaHost").textContent = text(status.host.name);
  $("metaPlatform").textContent = text(status.host.platform);
  $("metaVersion").textContent = text(status.version);
  $("metaSampled").textContent = clock(status.generated_at);

  const discovery = status.discovery || {};
  const peers = discovery.peers || {};
  const peerNames = Object.keys(peers);

  rows($("kvLink"), [
    ["角色", text(status.role) + (status.role === "server" ? "（本机为 Windows 侧）" : "（本机为 macOS 侧）")],
    ["监听端口", text(status.listen_port)],
    ["本机 IP", (status.host.ips && status.host.ips.length)
      ? status.host.ips.join(" / ") + "（填到另一台电脑的「对端地址」里）" : block(null)],
    ["最近切换目标", status.state ? LABEL[status.state] : DASH],
    ["dry-run", yesNo(status.dry_run)],
    ["对端地址", text(status.peer.host) + ":" + text(status.peer.port)],
    ["对端连接", flag(status.peer.connected ? "已连接" : "未连接", status.peer.connected)],
    ["对端出站连接", yesNo(status.peer.outbound)],
    ["对端身份", status.peer.info
      ? text(status.peer.info.name) + " · " + text(status.peer.info.platform) +
        " · v" + text(status.peer.info.version)
      : block(null)],
    ["对端密钥校验", authText(status.auth)],
    ["自动发现", discovery.enabled
      ? "已启用，发现 " + peerNames.length + " 台：" +
        (peerNames.length ? peerNames.join("、") : block(null))
      : "未启用"],
  ]);

  rows($("kvFiles"), [
    ["配置文件", text(status.config_path)],
    ["日志文件", text(status.log_file)],
    ["采样时间", clock(status.generated_at)],
    ["事件序号", text(status.events_seq)],
  ]);

  const ddc = status.ddc;
  rows($("kvDdc"), [
    ["工具", text(ddc.tool_path)],
    ["工具可用", flag(ddc.tool_ok ? "可用" : "不可用", ddc.tool_ok)],
    ["工具说明", text(ddc.tool_detail)],
    ["显示器 id", text(ddc.monitor_id)],
    ["display_index", text(ddc.display_index)],
    ["Mac 输入源", text(ddc.mac_input)],
    ["Windows 输入源", text(ddc.win_input)],
    ["稳定等待", text(ddc.settle) + " 秒"],
    ["当前输入源", status.input.value === null || status.input.value === undefined
      ? block(status.input.error) : text(status.input.value)],
    ["上次读取", clock(status.input.read_at)],
  ]);

  const commands = $("cmds");
  commands.textContent = "";
  const commandRows = [
    ["切换到 Mac", ddc.cmd_mac],
    ["切换到 Windows", ddc.cmd_win],
    ["读取当前输入源", ddc.read_command],
  ];
  for (const [label, value] of commandRows) {
    const row = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    if (Array.isArray(value) && value.length) {
      dd.textContent = value.join(" ");
    } else {
      dd.textContent = "该平台无内置命令，可用 ddc.command_template / ddc.read_template 指定";
      dd.className = "empty";
    }
    row.append(dt, dd);
    commands.appendChild(row);
  }

  rows($("kvHotkeys"), [
    ["切到 Mac", text(status.hotkeys.switch_to_mac)],
    ["切到 Windows", text(status.hotkeys.switch_to_win)],
    ["注册状态", flag(status.hotkeys.registered ? "已注册" : "未注册", status.hotkeys.registered)],
    ["说明", text(status.hotkeys.reason)],
  ]);

  $("probeDefault").textContent = (status.probe_candidates || []).join(", ") || DASH;
  renderOwnership(status);
  syncSetupFromStatus(status);
}

/* ---------------------------------------------------------------- 操作 */
function busy(on, message, stateId = "runState") {
  for (const id of ["btnMac", "btnWin", "btnRead", "btnProbe", "btnSave"]) {
    $(id).disabled = on;
  }
  const state = $(stateId);
  state.dataset.busy = on ? "true" : "false";
  if (message !== undefined) state.textContent = message;
}

async function switchTo(target) {
  pendingTarget = target;
  if (lastStatus) {
    renderOwnership(lastStatus);
    renderSwitchboard(lastStatus);
  }
  busy(true, "切换中：→ " + LABEL[target] + " …", "runState");
  try {
    const result = await api("/api/switch", { method: "POST", body: { target } });
    busy(false, result.ok
      ? "已完成：→ " + LABEL[target] + "（本机 DDC 或对端 DDC 至少一侧确认成功）"
      : "未确认：→ " + LABEL[target] + "，详见事件日志", "runState");
  } catch (error) {
    busy(false, "切换失败：" + error.message, "runState");
    notify(String(error.message), "error");
  } finally {
    pendingTarget = null;
    await refreshStatus();
    refreshEvents();
  }
}

async function readInput() {
  busy(true, "读取中：正在执行读取命令 …", "toolState");
  try {
    const result = await api("/api/read-input", { method: "POST", body: {} });
    busy(false, result.value === null || result.value === undefined
      ? "读取不到当前输入源（工具不支持回读，或显示器未响应）"
      : "当前输入源：" + result.value + "（" + (LABEL[result.target] || "未匹配 mac_input / win_input") + "）",
      "toolState");
  } catch (error) {
    busy(false, "读取失败：" + error.message, "toolState");
  }
  await refreshStatus();
}

async function probeInputs() {
  const raw = $("probeCandidates").value.trim();
  const body = {};
  if (raw) {
    const values = raw.split(/[,\s]+/).filter(Boolean).map(Number);
    if (values.some((value) => !Number.isInteger(value) || value < 0 || value > 255)) {
      notify("候选值必须是 0-255 的整数，用逗号分隔", "error");
      return;
    }
    body.candidates = values;
  }
  const started = Date.now();
  busy(true, "探测中：逐个试探候选值并回读确认，显示器会闪几次 …", "toolState");
  const ticker = setInterval(() => {
    $("toolState").textContent =
      "探测中：已用 " + Math.round((Date.now() - started) / 1000) + " 秒，请等显示器稳定 …";
  }, 1000);
  try {
    const result = await api("/api/probe-inputs", { method: "POST", body });
    const found = result.available || [];
    busy(false, "探测完成：接受 " + found.length + " 个取值" +
      (found.length ? "（" + found.join(", ") + "）" : "") + "，已恢复原输入源",
      "toolState");
  } catch (error) {
    busy(false, "探测失败：" + error.message, "toolState");
  } finally {
    clearInterval(ticker);
  }
  await refreshStatus();
}

/* ---------------------------------------------------------------- 配置 */
const CONFIG_FIELDS = [
  { group: "基础", fields: [
    { path: "role", type: "select", options: ["server", "client"] },
    { path: "peer_host", type: "text" },
    { path: "peer_port", type: "number", min: 1, max: 65535 },
    { path: "listen_port", type: "number", min: 1, max: 65535 },
    { path: "debounce", type: "number", min: 0, step: 0.1 },
    { path: "log_level", type: "select", options: ["DEBUG", "INFO", "WARNING", "ERROR"] },
  ] },
  { group: "热键", fields: [
    { path: "hotkeys.switch_to_mac", type: "text" },
    { path: "hotkeys.switch_to_win", type: "text" },
  ] },
  { group: "网络", fields: [
    { path: "network.ack_timeout", type: "number", min: 0.1, step: 0.5 },
    { path: "network.ping_interval", type: "number", min: 0.1, step: 0.5 },
    { path: "network.reconnect_interval", type: "number", min: 0.1, step: 0.5 },
    { path: "network.reconnect_max_interval", type: "number", min: 0.1, step: 0.5 },
    { path: "network.connect_wait", type: "number", min: 0.1, step: 0.5 },
  ] },
  { group: "自动发现", fields: [
    { path: "discovery.enabled", type: "checkbox" },
    { path: "discovery.port", type: "number", min: 1, max: 65535 },
    { path: "discovery.interval", type: "number", min: 0.1, step: 0.5 },
    { path: "discovery.ttl", type: "number", min: 1, step: 0.5 },
    { path: "discovery.broadcast", type: "text" },
  ] },
  { group: "安全", fields: [
    { path: "auth.secret", type: "password" },
  ] },
  { group: "显示器 DDC", fields: [
    { path: "ddc.monitor_id", type: "text" },
    { path: "ddc.display_index", type: "number", min: 0 },
    { path: "ddc.mac_input", type: "number", min: 0, max: 255 },
    { path: "ddc.win_input", type: "number", min: 0, max: 255 },
    { path: "ddc.vcp_code", type: "text" },
    { path: "ddc.settle", type: "number", min: 0, step: 0.1 },
    { path: "ddc.timeout", type: "number", min: 0.1, step: 0.5 },
    { path: "ddc.retries", type: "number", min: 0 },
    { path: "ddc.retry_delay", type: "number", min: 0, step: 0.1 },
    { path: "ddc.controlmyMonitor_path", type: "text" },
    { path: "ddc.m1ddc_path", type: "text" },
    { path: "ddc.ddcutil_path", type: "text" },
    { path: "ddc.command_template", type: "textarea" },
    { path: "ddc.read_template", type: "textarea" },
    { path: "ddc.read_regex", type: "text" },
  ] },
];

const INPUTS = new Map();

function getPath(object, path) {
  return path.split(".").reduce((node, key) => (node == null ? undefined : node[key]), object);
}

function setPath(object, path, value) {
  const keys = path.split(".");
  let node = object;
  for (const key of keys.slice(0, -1)) {
    if (typeof node[key] !== "object" || node[key] === null) node[key] = {};
    node = node[key];
  }
  node[keys[keys.length - 1]] = value;
}

function needsRestart(path) {
  return restartPrefixes.some((prefix) =>
    path === prefix.replace(/\.$/, "") || path.startsWith(prefix));
}

function configValue(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "number") {
    if (input.value.trim() === "") return null;
    return Number(input.value);
  }
  return input.value === "" ? null : input.value;
}

let configBase = null;
let restartPrefixes = [];

function renderConfig(view) {
  configBase = view.values;
  restartPrefixes = view.restart_prefixes || [];
  INPUTS.clear();
  const host = $("configGroups");
  host.textContent = "";
  for (const group of CONFIG_FIELDS) {
    const section = document.createElement("div");
    section.className = "config-group";
    const title = document.createElement("h3");
    title.textContent = group.group;
    const fields = document.createElement("div");
    fields.className = "config-fields";
    for (const field of group.fields) {
      const value = getPath(configBase, field.path);
      const wrap = document.createElement("div");
      wrap.className = "config-field";
      wrap.dataset.path = field.path;
      const label = document.createElement("label");
      label.setAttribute("for", "cfg-" + field.path);
      label.textContent = field.path;
      if (needsRestart(field.path)) {
        const mark = document.createElement("span");
        mark.className = "flag";
        mark.textContent = " 需重启";
        label.appendChild(mark);
      }
      let input;
      if (field.type === "select") {
        input = document.createElement("select");
        for (const option of field.options) {
          const el = document.createElement("option");
          el.value = option;
          el.textContent = option;
          input.appendChild(el);
        }
        input.value = value == null ? "" : String(value);
      } else if (field.type === "textarea") {
        input = document.createElement("textarea");
        input.value = value == null ? "" : (Array.isArray(value) ? value.join("\n") : String(value));
      } else {
        input = document.createElement("input");
        input.type = field.type;
        if (field.min !== undefined) input.min = field.min;
        if (field.max !== undefined) input.max = field.max;
        if (field.step !== undefined) input.step = field.step;
        if (field.type === "checkbox") input.checked = Boolean(value);
        else input.value = value == null ? "" : String(value);
      }
      input.id = "cfg-" + field.path;
      input.addEventListener("input", () => markDirty(field.path));
      input.addEventListener("change", () => markDirty(field.path));
      wrap.append(label, input);
      fields.appendChild(wrap);
      INPUTS.set(field.path, input);
    }
    section.append(title, fields);
    host.appendChild(section);
  }
}

function markDirty(path) {
  const wrap = $("configGroups").querySelector('[data-path="' + path + '"]');
  const input = INPUTS.get(path);
  const original = getPath(configBase, path);
  const current = configValue(input);
  const same = typeof original === "number" && typeof current === "number"
    ? original === current
    : String(original == null ? "" : original) === String(current == null ? "" : current);
  if (wrap) wrap.dataset.dirty = same ? "false" : "true";
}

function collectChanges() {
  const patch = {};
  for (const [path, input] of INPUTS) {
    const original = getPath(configBase, path);
    const current = configValue(input);
    const before = original == null ? "" : (Array.isArray(original) ? original.join("\n") : String(original));
    const after = current == null ? "" : (Array.isArray(current) ? current.join("\n") : String(current));
    if (before === after) continue;
    let value = current;
    if (input.tagName === "TEXTAREA" && typeof value === "string") {
      value = value.split("\n").map((line) => line.trim()).filter(Boolean);
      value = value.length === 1 ? value[0] : (value.length === 0 ? null : value);
    }
    setPath(patch, path, value);
  }
  return patch;
}

async function saveConfig() {
  const values = collectChanges();
  if (!Object.keys(values).length) {
    $("configState").textContent = "没有改动，未提交。";
    return;
  }
  $("configState").textContent = "保存中 …";
  try {
    const result = await api("/api/config", { method: "POST", body: { values } });
    let message = "已保存 " + result.changed.length + " 项：" + result.changed.join("、");
    if (result.restart_required) {
      message += " ｜ 需重启生效：" + result.restart_keys.join("、");
    }
    $("configState").textContent = message;
    renderConfig({ values: result.values, restart_prefixes: restartPrefixes });
    await refreshStatus();
  } catch (error) {
    $("configState").textContent = "保存失败：" + error.message;
    notify("配置未保存：" + error.message, "error");
  }
}

/* ---------------------------------------------------------------- 事件 */
let lastSeq = 0;

function renderEvents(records) {
  const body = $("eventRows");
  if (!records.length) {
    if (!body.rows.length) {
      const row = body.insertRow();
      const cell = row.insertCell();
      cell.colSpan = 4;
      cell.className = "empty";
      cell.textContent = "还没有事件；切换、读取与连接都会写到这里。";
    }
    return;
  }
  const placeholder = body.querySelector(".empty");
  if (placeholder) placeholder.parentNode.remove();
  for (const record of records.slice().reverse()) {
    const row = body.insertRow(0);
    const time = row.insertCell();
    time.className = "num";
    time.textContent = clock(record.ts);
    const level = row.insertCell();
    level.className = "lvl-" + record.level;
    level.textContent = record.level;
    const logger = row.insertCell();
    logger.textContent = record.logger;
    const message = row.insertCell();
    message.textContent = record.message;
  }
  while (body.rows.length > 200) body.deleteRow(body.rows.length - 1);
}

async function refreshEvents() {
  try {
    const payload = await api("/api/events?since=" + lastSeq);
    lastSeq = Math.max(lastSeq, payload.last_seq || 0);
    if (payload.events && payload.events.length) renderEvents(payload.events);
  } catch (error) {
    /* 事件流短暂失败不打断页面，下一轮继续 */
  }
}

/* ---------------------------------------------------------------- 轮询 */
async function refreshStatus() {
  try {
    const status = await api("/api/status");
    renderStatus(status);
    $("footerState").textContent = "最近一次采样 " + clock(status.generated_at) +
      " ｜ 主机 " + text(status.host.name) + " ｜ 角色 " + text(status.role);
    return status;
  } catch (error) {
    $("footerState").textContent = "状态读取失败：" + error.message;
    return null;
  }
}

async function bootstrap() {
  if (!token) {
    notify("地址里没有令牌。请用启动日志里带 ?t= 的完整地址打开：http://127.0.0.1:<端口>/?t=<令牌>", "error");
    return;
  }
  $("btnMac").addEventListener("click", () => switchTo("mac"));
  $("btnWin").addEventListener("click", () => switchTo("win"));
  $("btnRead").addEventListener("click", readInput);
  $("btnProbe").addEventListener("click", probeInputs);
  $("btnSave").addEventListener("click", saveConfig);
  $("btnRevert").addEventListener("click", () => api("/api/config").then(renderConfig));
  bindSetupWizard();

  const initialStatus = await refreshStatus();
  try {
    renderConfig(await api("/api/config"));
  } catch (error) {
    $("configState").textContent = "配置读取失败：" + error.message;
  }
  await refreshEvents();

  if (initialStatus && !(initialStatus.setup && initialStatus.setup.completed)) {
    openSetupWizard();
  }

  setInterval(() => { if (!document.hidden) refreshStatus(); }, 2000);
  setInterval(() => { if (!document.hidden) refreshEvents(); }, 3000);
}

bootstrap();
