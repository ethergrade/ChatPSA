const conversation = document.querySelector("#conversation");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const clearButton = document.querySelector("#clear-chat");
const imageInput = document.querySelector("#image-input");
const attachmentList = document.querySelector("#attachment-list");
const historyList = document.querySelector("#history-list");
const newConversationButton = document.querySelector("#new-conversation");
const initialConversation = conversation.innerHTML;
let selectedImages = [];
let accessToken = sessionStorage.getItem("chatpsaAccessToken") || "";
let accessRole = sessionStorage.getItem("chatpsaAccessRole") || "";
let agentName = sessionStorage.getItem("chatpsaAgentName") || "";
let agentEmail = sessionStorage.getItem("chatpsaAgentEmail") || "";
let activeConversationId = null;
const loginOverlay = document.querySelector("#login-overlay");
const loginForm = document.querySelector("#login-form");
const tokenInput = document.querySelector("#access-token");
const agentFields = document.querySelector("#agent-fields");
const agentNameInput = document.querySelector("#agent-name");
const agentEmailInput = document.querySelector("#agent-email");
const roleActions = document.querySelector("#role-actions");
const submitActions = document.querySelector("#submit-actions");
const loginError = document.querySelector("#login-error");
const approvalsNav = document.querySelector("#approvals-nav");

function syncRoleUi() {
  approvalsNav.hidden = accessRole !== "admin";
}

function showLogin(message = "") {
  loginError.textContent = message;
  loginOverlay.hidden = false;
}

function chooseRole(role) {
  accessRole = role;
  agentFields.hidden = role !== "agent";
  roleActions.hidden = true;
  submitActions.hidden = false;
  document.querySelector("#login-title").textContent = role === "agent" ? "Accesso ServiceDesk Agent" : "Accesso amministratore";
  document.querySelector("#login-copy").textContent = role === "agent"
    ? "Inserisci email aziendale e token. Solo un token personale configurato associa lo storico alla tua identità; il token condiviso usa lo storico ServiceDesk."
    : "Inserisci il token amministratore. Questo accesso è riservato agli approvatori configurati.";
  (role === "agent" ? agentNameInput : tokenInput).focus();
}

document.querySelector("#agent-role").addEventListener("click", () => chooseRole("agent"));
document.querySelector("#admin-role").addEventListener("click", () => chooseRole("admin"));
document.querySelector("#back-role").addEventListener("click", () => {
  accessRole = "";
  agentFields.hidden = true;
  roleActions.hidden = false;
  submitActions.hidden = true;
  document.querySelector("#login-title").textContent = "Chi sta entrando in ChatPSA?";
  document.querySelector("#login-copy").textContent = "Scegli il tuo profilo. Gli storici personali richiedono un token personale o il login aziendale verificato.";
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = tokenInput.value.trim();
  const name = agentNameInput.value.trim();
  const email = agentEmailInput.value.trim();
  if (!token || (accessRole === "agent" && (!name || !email))) {
    loginError.textContent = "Compila tutti i campi richiesti.";
    return;
  }
  accessToken = token;
  agentName = name;
  agentEmail = email;
  const response = await authenticatedFetch("/api/conversations", {}, false);
  if (!response.ok) {
    accessToken = "";
    loginError.textContent = "Credenziali non valide o accesso non configurato.";
    return;
  }
  sessionStorage.setItem("chatpsaAccessToken", token);
  sessionStorage.setItem("chatpsaAccessRole", accessRole);
  if (accessRole === "agent") {
    sessionStorage.setItem("chatpsaAgentName", name);
    sessionStorage.setItem("chatpsaAgentEmail", email);
  }
  loginOverlay.hidden = true;
  syncRoleUi();
  await loadConversations();
});

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function scrollToLatest() {
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
}

function addUserMessage(message) {
  const article = element("article", "message user-message");
  article.append(element("div", "user-bubble", message));
  conversation.append(article);
}

function addTyping() {
  const article = element("article", "message assistant-message");
  article.id = "typing-message";
  article.append(element("div", "avatar", "C"));
  const body = element("div", "message-body");
  body.append(element("div", "message-meta", "ChatPSA"));
  const typing = element("div", "answer-card typing");
  typing.append(element("span"), element("span"), element("span"));
  body.append(typing);
  article.append(body);
  conversation.append(article);
}

function appendSection(card, title, content) {
  card.append(element("h3", "section-title", title));
  card.append(content);
}

function addAssistantResponse(payload) {
  document.querySelector("#typing-message")?.remove();
  const article = element("article", "message assistant-message");
  article.append(element("div", "avatar", "C"));
  const body = element("div", "message-body");
  const meta = element("div", "message-meta", "ChatPSA ");
  meta.append(element("span", "", "• adesso"));
  body.append(meta);

  const card = element("div", "answer-card");
  card.append(element("p", "answer-kicker", String(payload.mode || "risposta").replaceAll("_", " ")));
  card.append(element("h2", "", payload.title || "Risposta ChatPSA"));
  card.append(element("p", payload.answer ? "answer-text" : "", payload.answer || payload.summary || "Analisi completata."));

  if (Array.isArray(payload.evidence) && payload.evidence.length) {
    const list = element("dl", "evidence-grid");
    payload.evidence.forEach((item) => {
      const wrapper = element("div", "evidence-item");
      wrapper.append(element("dt", "", item.label), element("dd", "", item.value));
      list.append(wrapper);
    });
    appendSection(card, "Evidenze", list);
  }

  if (Array.isArray(payload.findings) && payload.findings.length) {
    const list = element("ul", "finding-list");
    payload.findings.forEach((item) => {
      const severity = ["error", "warning", "info"].includes(item.severity) ? item.severity : "info";
      list.append(element("li", `finding ${severity}`, item.message || item.code || "Evidenza rilevata"));
    });
    appendSection(card, "Cosa ho trovato", list);
  }

  if (Array.isArray(payload.next_steps) && payload.next_steps.length) {
    const list = element("ul", "next-list");
    payload.next_steps.forEach((step) => list.append(element("li", "", step)));
    appendSection(card, "Prossimi passi", list);
  }

  if (Array.isArray(payload.sources) && payload.sources.length) {
    const list = element("div", "source-list");
    payload.sources.forEach((source) => list.append(element("span", "source-chip", `${source.type}: ${source.label}`)));
    appendSection(card, "Fonti usate", list);
  }

  if (payload.approval) {
    const notification = payload.approval.email_notified
      ? "Gli approvatori configurati sono stati notificati."
      : "Richiesta registrata; notifiche email non ancora configurate.";
    card.append(element("div", "approval-card", `Modifica non applicata. Richiesta ${payload.approval.id.slice(0, 8)} in attesa di approvazione. ${notification}`));
  }

  if (payload.read_only) card.append(element("span", "read-only-badge", "● Solo lettura"));
  body.append(card);
  article.append(body);
  conversation.append(article);
  scrollToLatest();
}

function addError(message) {
  addAssistantResponse({
    mode: "errore",
    title: "Non ho completato l’indagine",
    summary: message,
    findings: [],
    next_steps: ["Controlla l’ID e verifica la connessione HaloPSA."],
    read_only: true,
  });
}

async function submitQuestion(message) {
  const clean = message.trim();
  if (!clean || sendButton.disabled) return;
  addUserMessage(clean);
  addTyping();
  input.value = "";
  input.style.height = "auto";
  sendButton.disabled = true;
  scrollToLatest();
  try {
    const body = new FormData();
    body.append("message", clean);
    if (activeConversationId) body.append("conversation_id", activeConversationId);
    selectedImages.forEach((file) => body.append("images", file));
    const response = await authenticatedFetch("/api/assist", {
      method: "POST",
      body,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Richiesta non riuscita");
    addAssistantResponse(payload);
    activeConversationId = payload.conversation?.id || activeConversationId;
    await loadConversations();
    selectedImages = [];
    imageInput.value = "";
    renderAttachments();
  } catch (error) {
    document.querySelector("#typing-message")?.remove();
    addError(error.message || "Errore di connessione");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

async function authenticatedFetch(url, options = {}, promptOnFailure = true) {
  const headers = new Headers(options.headers || {});
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  if (accessRole) headers.set("X-ChatPSA-Access-Role", accessRole);
  if (accessRole === "agent") {
    headers.set("X-ChatPSA-Agent-Name", agentName);
    headers.set("X-ChatPSA-Agent-Email", agentEmail);
  }
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401) {
    sessionStorage.removeItem("chatpsaAccessToken");
    accessToken = "";
    if (promptOnFailure) showLogin("La sessione è scaduta. Accedi di nuovo.");
  }
  return response;
}

async function loadConversations() {
  try {
    const response = await authenticatedFetch("/api/conversations");
    if (!response.ok) return;
    const payload = await response.json();
    historyList.replaceChildren();
    payload.conversations.forEach((item) => {
      const row = element("div", "history-item");
      const open = element("button", `history-open${item.id === activeConversationId ? " active" : ""}`, item.title);
      open.type = "button";
      open.addEventListener("click", () => openConversation(item.id));
      const rename = element("button", "history-rename", "✎");
      rename.type = "button";
      rename.title = "Rinomina chat";
      rename.addEventListener("click", () => renameConversation(item));
      row.append(open, rename);
      historyList.append(row);
    });
  } catch (_) {
    // The health indicator already communicates backend availability.
  }
}

async function openConversation(id) {
  const response = await authenticatedFetch(`/api/conversations/${encodeURIComponent(id)}/messages`);
  const payload = await response.json();
  if (!response.ok) return addError(payload.error || "Impossibile aprire la chat");
  activeConversationId = id;
  conversation.innerHTML = "";
  payload.messages.forEach((message) => {
    if (message.role === "user") addUserMessage(message.content);
    else addAssistantResponse({ ...(message.metadata || {}), answer: message.content });
  });
  await loadConversations();
}

async function renameConversation(item) {
  const title = window.prompt("Nuovo titolo della chat", item.title);
  if (!title || title.trim() === item.title) return;
  const response = await authenticatedFetch(`/api/conversations/${encodeURIComponent(item.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title.trim() }),
  });
  if (response.ok) await loadConversations();
}

async function loadApprovals() {
  const response = await authenticatedFetch("/api/approvals");
  const payload = await response.json();
  if (!response.ok) return addError(payload.error || "Impossibile caricare le approvazioni");
  activeConversationId = null;
  conversation.innerHTML = "";
  const article = element("article", "message assistant-message");
  article.append(element("div", "avatar", "C"));
  const body = element("div", "message-body");
  body.append(element("div", "message-meta", "ChatPSA • centro approvazioni"));
  const card = element("div", "answer-card");
  card.append(element("p", "answer-kicker", "GOVERNANCE"));
  card.append(element("h2", "", "Richieste da approvare"));
  const list = element("div", "approval-list");
  if (!payload.requests.length) list.append(element("p", "login-copy", "Non ci sono richieste."));
  payload.requests.forEach((item) => {
    const row = element("section", "approval-row");
    const heading = element("div", "approval-row-heading");
    heading.append(
      element("strong", "", item.action_type || "Proposta non eseguibile"),
      element("span", `approval-status ${item.status}`, item.status)
    );
    row.append(heading);
    row.append(element("p", "", item.question));
    row.append(element("small", "", `${item.requester_name} • ${item.created_at}`));
    if (item.error_message) row.append(element("div", "approval-error", item.error_message));
    if (item.status === "completed" && item.result) {
      row.append(element("div", "approval-success", "Azione completata e riletta da HaloPSA."));
    }
    if (item.status === "pending") {
      const approve = element(
        "button",
        "approve-button",
        item.execution_enabled ? "Approva ed esegui" : "In attesa di dati/serializer"
      );
      approve.type = "button";
      approve.disabled = !item.execution_enabled;
      approve.addEventListener("click", () => approveRequest(item.id, approve));
      row.append(approve);
    }
    list.append(row);
  });
  card.append(list);
  body.append(card);
  article.append(body);
  conversation.append(article);
  scrollToLatest();
}

async function approveRequest(id, button) {
  button.disabled = true;
  button.textContent = "ChatPSA sta eseguendo…";
  const response = await authenticatedFetch(`/api/approvals/${encodeURIComponent(id)}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  const payload = await response.json();
  if (!response.ok) addError(payload.error || "Azione non riuscita");
  await loadApprovals();
}

approvalsNav.addEventListener("click", loadApprovals);

function renderAttachments() {
  attachmentList.replaceChildren();
  selectedImages.forEach((file) => attachmentList.append(element("span", "attachment-chip", `Immagine: ${file.name}`)));
}

imageInput.addEventListener("change", () => {
  selectedImages = Array.from(imageInput.files || []).slice(0, 4);
  renderAttachments();
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitQuestion(input.value);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 130)}px`;
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-prompt]");
  if (button) submitQuestion(button.dataset.prompt);
  const draftButton = event.target.closest("[data-draft]");
  if (draftButton) {
    input.value = draftButton.dataset.draft;
    input.focus();
  }
});

clearButton.addEventListener("click", () => {
  conversation.innerHTML = initialConversation;
  input.focus();
});

newConversationButton.addEventListener("click", () => {
  activeConversationId = null;
  conversation.innerHTML = initialConversation;
  loadConversations();
  input.focus();
});

fetch("/api/health")
  .then((response) => {
    if (!response.ok) throw new Error("offline");
    return response.json();
  })
  .then((health) => {
    if (health.tenant_name) document.querySelector("#tenant-workspace").textContent = `${health.tenant_name} workspace`;
    document.querySelector("#status-dot").classList.add("online");
    document.querySelector("#connection-label").textContent = health.writes_enabled
      ? "Connesso • scritture abilitate"
      : "Connesso • sola lettura";
    if (health.auth_required && !accessToken) showLogin();
  })
  .catch(() => {
    document.querySelector("#status-dot").classList.add("offline");
    document.querySelector("#connection-label").textContent = "Backend non disponibile";
  });

if (accessToken) loadConversations();
syncRoleUi();
