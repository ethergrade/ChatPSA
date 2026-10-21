const conversation = document.querySelector("#conversation");
const form = document.querySelector("#chat-form");
const input = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const clearButton = document.querySelector("#clear-chat");
const initialConversation = conversation.innerHTML;

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
  card.append(element("p", "", payload.summary || "Analisi completata."));

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
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: clean }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Richiesta non riuscita");
    addAssistantResponse(payload);
  } catch (error) {
    document.querySelector("#typing-message")?.remove();
    addError(error.message || "Errore di connessione");
  } finally {
    sendButton.disabled = false;
    input.focus();
  }
}

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

fetch("/api/health")
  .then((response) => {
    if (!response.ok) throw new Error("offline");
    return response.json();
  })
  .then((health) => {
    document.querySelector("#status-dot").classList.add("online");
    document.querySelector("#connection-label").textContent = health.writes_enabled
      ? "Connesso • scritture abilitate"
      : "Connesso • sola lettura";
  })
  .catch(() => {
    document.querySelector("#status-dot").classList.add("offline");
    document.querySelector("#connection-label").textContent = "Backend non disponibile";
  });
