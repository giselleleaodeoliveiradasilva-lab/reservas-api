import { apiRequest, IdempotentAction } from "./api.js";
import {
  clearError,
  el,
  emptyRow,
  flash,
  formatDateTime,
  renderPagination,
  showError,
  STATUS_LABELS,
  statusBadge,
  TRANSITION_LABELS,
  withBusy,
} from "./ui.js";

const reservationId = Number(document.querySelector("main").dataset.reservationId);
const errorBox = document.getElementById("error");
const section = document.getElementById("reservation");
const actions = document.getElementById("actions");
const historyRows = document.getElementById("history-rows");
const historyPagination = document.getElementById("history-pagination");

// Uma ação idempotente para as transições desta reserva. Como o payload
// ({to_status}) entra no fingerprint, clicar em outro botão gera chave nova;
// repetir o mesmo clique após falha de rede reaproveita a chave.
const transitionAction = new IdempotentAction();

let historyPage = 1;

async function loadReservation() {
  const { data: reservation } = await apiRequest("GET", `/reservations/${reservationId}/`);
  let resourceName = `#${reservation.resource_id}`;
  try {
    const { data: resource } = await apiRequest("GET", `/resources/${reservation.resource_id}/`);
    resourceName = resource.name;
  } catch {
    // Nome do recurso é só complemento visual; mantém o id.
  }
  renderReservation(reservation, resourceName);
}

function renderReservation(r, resourceName) {
  document.getElementById("r-status").replaceChildren(statusBadge(r.status));
  document.getElementById("r-resource").textContent = resourceName;
  document.getElementById("r-customer").textContent = r.customer_name;
  document.getElementById("r-start").textContent = formatDateTime(r.start_at);
  document.getElementById("r-end").textContent = formatDateTime(r.end_at);
  document.getElementById("r-updated").textContent = formatDateTime(r.updated_at);
  renderActions(r.allowed_transitions);
  section.hidden = false;
}

// Os botões vêm de `allowed_transitions` (calculado pela API). Nada de
// "if status == ..." aqui: mudar a máquina de estados no backend muda a tela.
function renderActions(allowed) {
  if (!allowed.length) {
    actions.replaceChildren(el("p", { className: "muted" }, "Nenhuma ação disponível para o status atual."));
    return;
  }
  actions.replaceChildren(
    ...allowed.map((toStatus) =>
      el(
        "button",
        {
          className: `button ${toStatus === "CANCELADA" ? "danger" : "primary"}`,
          onClick: (event) => transition(event.currentTarget, toStatus),
        },
        TRANSITION_LABELS[toStatus] ?? STATUS_LABELS[toStatus] ?? toStatus,
      ),
    ),
  );
}

async function transition(button, toStatus) {
  const label = STATUS_LABELS[toStatus] ?? toStatus;
  if (!window.confirm(`Mudar o status da reserva para "${label}"?`)) return;

  clearError(errorBox);
  const payload = { to_status: toStatus };
  const idempotencyKey = transitionAction.keyFor(payload);

  let networkFailure = false;
  await withBusy(button, async () => {
    try {
      await apiRequest("POST", `/reservations/${reservationId}/transitions/`, { body: payload, idempotencyKey });
      transitionAction.reset();
      flash(`Status alterado para "${label}".`);
    } catch (error) {
      showError(errorBox, error);
      networkFailure = error.isNetworkError;
    }
  });
  // Falha de rede: mantém a tela como está, para o usuário reenviar com a mesma chave.
  if (networkFailure) return;
  // Sucesso ou erro da API (ex.: 409): o estado oficial é o do servidor, então recarrega.
  await refresh();
}

async function loadHistory(page = historyPage) {
  historyPage = page;
  const { data } = await apiRequest("GET", `/reservations/${reservationId}/history/`, { params: { page } });
  if (!data.results.length) {
    historyRows.replaceChildren(emptyRow(5, "Sem registros."));
  } else {
    historyRows.replaceChildren(
      ...data.results.map((h) =>
        el(
          "tr",
          {},
          el("td", {}, formatDateTime(h.changed_at)),
          el("td", {}, h.from_status ? statusBadge(h.from_status) : "— (criação)"),
          el("td", {}, statusBadge(h.to_status)),
          el("td", {}, el("code", { className: "small" }, h.idempotency_key || "—")),
          el("td", {}, el("code", { className: "small" }, h.request_id || "—")),
        ),
      ),
    );
  }
  renderPagination(historyPagination, data, page, (p) => loadHistory(p).catch((e) => showError(errorBox, e)));
}

async function refresh() {
  try {
    await Promise.all([loadReservation(), loadHistory()]);
  } catch (error) {
    if (error.status === 404) {
      section.hidden = true;
      historyRows.replaceChildren(emptyRow(5, "—"));
    }
    showError(errorBox, error);
  }
}

if (new URLSearchParams(window.location.search).has("criada")) {
  flash("Reserva criada com sucesso.");
  window.history.replaceState(null, "", window.location.pathname);
}

refresh();
