/**
 * Utilitários de apresentação. Todo texto vindo da API entra no DOM via
 * textContent (nunca innerHTML), o que evita XSS com dados digitados por usuários.
 */

// Rótulos de exibição. Os valores e as regras vêm sempre da API.
export const STATUS_LABELS = {
  PENDENTE: "Pendente",
  CONFIRMADA: "Confirmada",
  CANCELADA: "Cancelada",
  CONCLUIDA: "Concluída",
};

export const TRANSITION_LABELS = {
  CONFIRMADA: "Confirmar",
  CANCELADA: "Cancelar",
  CONCLUIDA: "Concluir",
};

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (name === "className") node.className = value;
    else if (name.startsWith("on")) node.addEventListener(name.slice(2).toLowerCase(), value);
    else node.setAttribute(name, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function statusBadge(status) {
  return el("span", { className: `badge badge-${String(status).toLowerCase()}` }, STATUS_LABELS[status] ?? status);
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

/** Valor de <input type="datetime-local"> (hora local) -> ISO 8601 em UTC. */
export function localInputToIso(value) {
  return value ? new Date(value).toISOString() : "";
}

/** ISO 8601 -> valor aceito por <input type="datetime-local">, no fuso local. */
export function isoToLocalInput(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

// --- Mensagens -----------------------------------------------------------------

export function flash(message) {
  const box = document.getElementById("flash");
  box.textContent = message;
  box.hidden = false;
}

export function clearError(box, form) {
  box.hidden = true;
  box.replaceChildren();
  form?.querySelectorAll(".field-error").forEach((span) => (span.textContent = ""));
  form?.querySelectorAll("[data-field].invalid").forEach((label) => label.classList.remove("invalid"));
}

/**
 * Exibe um ApiError: mensagem do backend, detalhes, dicas específicas por
 * `code` e o request_id para suporte. Erros de campo (400) vão para o lado do
 * campo correspondente quando o formulário é informado.
 */
export function showError(box, error, { form } = {}) {
  clearError(box, form);

  const details = { ...(error.details ?? {}) };
  if (form && error.code === "validation_error") {
    for (const [field, messages] of Object.entries(details)) {
      const label = form.querySelector(`[data-field="${CSS.escape(field)}"]`);
      if (!label) continue;
      label.classList.add("invalid");
      label.querySelector(".field-error").textContent = [].concat(messages).join(" ");
      delete details[field];
    }
  }

  const parts = [el("strong", {}, error.message ?? "Erro inesperado.")];

  const hint = hintFor(error);
  if (hint) parts.push(el("p", {}, hint));

  const remaining = Object.entries(details);
  if (remaining.length) {
    parts.push(
      el("ul", { className: "details-list" }, remaining.map(([k, v]) => el("li", {}, describeDetail(k, v)))),
    );
  }

  if (error.requestId) {
    parts.push(el("p", { className: "small muted" }, "Código para suporte (request_id): ", el("code", {}, error.requestId)));
  }

  box.append(...parts);
  box.hidden = false;
}

function hintFor(error) {
  if (error.isNetworkError) {
    return "Se você reenviar a mesma operação, ela não será duplicada (a mesma Idempotency-Key é reutilizada).";
  }
  if (error.code === "idempotency_key_reused") {
    return "Os dados mudaram em relação ao envio anterior. Envie novamente para gerar uma nova operação.";
  }
  if (error.code === "invalid_status_transition") {
    return "O status da reserva pode ter sido alterado por outra pessoa. A tela foi atualizada com os dados atuais.";
  }
  return null;
}

function describeDetail(key, value) {
  if (key === "conflicting_reservation_id") {
    return el("span", {}, "Reserva em conflito: ", el("a", { href: `/reservas/${value}/` }, `#${value}`));
  }
  if (key === "allowed_to_status") {
    const labels = [].concat(value).map((s) => STATUS_LABELS[s] ?? s);
    return `Status permitidos a partir do atual: ${labels.length ? labels.join(", ") : "nenhum"}`;
  }
  if (key.endsWith("_at") && typeof value === "string") return `${key}: ${formatDateTime(value)}`;
  const text = Array.isArray(value) ? value.join(" ") : typeof value === "object" ? JSON.stringify(value) : value;
  return `${key}: ${text}`;
}

// --- Componentes ----------------------------------------------------------------

/** Liga/desliga o estado "ocupado" de um botão (evita cliques repetidos). */
export async function withBusy(button, fn) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

/** Paginação baseada nos campos `next`/`previous` da resposta da API. */
export function renderPagination(container, data, page, onChange) {
  container.replaceChildren();
  if (!data || (!data.next && !data.previous)) return;
  container.append(
    el("button", { className: "button", disabled: !data.previous, onClick: () => onChange(page - 1) }, "‹ Anterior"),
    el("span", { className: "muted" }, `Página ${page} · ${data.count} itens`),
    el("button", { className: "button", disabled: !data.next, onClick: () => onChange(page + 1) }, "Próxima ›"),
  );
}

export function emptyRow(colspan, text) {
  return el("tr", {}, el("td", { colspan, className: "muted" }, text));
}
