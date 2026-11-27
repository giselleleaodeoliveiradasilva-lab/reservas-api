import { apiRequest, fetchAllPages } from "./api.js";
import {
  clearError,
  el,
  emptyRow,
  formatDateTime,
  isoToLocalInput,
  localInputToIso,
  renderPagination,
  showError,
  statusBadge,
} from "./ui.js";

const form = document.getElementById("filters");
const errorBox = document.getElementById("error");
const rows = document.getElementById("rows");
const pagination = document.getElementById("pagination");

const resourceNames = new Map();

// Os filtros ficam na URL (?status=...&page=...): voltar do detalhe preserva a busca.
function readStateFromUrl() {
  const query = new URLSearchParams(window.location.search);
  return {
    resource: query.get("resource") ?? "",
    status: query.get("status") ?? "",
    start_from: query.get("start_from") ?? "",
    start_to: query.get("start_to") ?? "",
    page: Number(query.get("page")) || 1,
  };
}

function writeStateToUrl(state) {
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(state)) if (v && !(k === "page" && v === 1)) query.set(k, v);
  const qs = query.toString();
  window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

function stateFromForm(page = 1) {
  const data = new FormData(form);
  return {
    resource: data.get("resource"),
    status: data.get("status"),
    start_from: localInputToIso(data.get("start_from")),
    start_to: localInputToIso(data.get("start_to")),
    page,
  };
}

function fillForm(state) {
  form.resource.value = state.resource;
  form.status.value = state.status;
  form.start_from.value = isoToLocalInput(state.start_from);
  form.start_to.value = isoToLocalInput(state.start_to);
}

async function loadResources() {
  const resources = await fetchAllPages("/resources/");
  for (const r of resources) {
    resourceNames.set(r.id, r.name);
    form.resource.append(el("option", { value: r.id }, r.name));
  }
}

async function load(state) {
  writeStateToUrl(state);
  clearError(errorBox);
  try {
    const { data } = await apiRequest("GET", "/reservations/", { params: state });
    renderRows(data.results);
    renderPagination(pagination, data, state.page, (page) => load({ ...state, page }));
  } catch (error) {
    rows.replaceChildren(emptyRow(6, "Não foi possível carregar as reservas."));
    pagination.replaceChildren();
    showError(errorBox, error);
  }
}

function renderRows(reservations) {
  if (!reservations.length) {
    rows.replaceChildren(emptyRow(6, "Nenhuma reserva encontrada."));
    return;
  }
  rows.replaceChildren(
    ...reservations.map((r) =>
      el(
        "tr",
        {},
        el("td", {}, el("a", { href: `/reservas/${r.id}/` }, `#${r.id}`)),
        el("td", {}, resourceNames.get(r.resource_id) ?? `#${r.resource_id}`),
        el("td", {}, r.customer_name),
        el("td", {}, formatDateTime(r.start_at)),
        el("td", {}, formatDateTime(r.end_at)),
        el("td", {}, statusBadge(r.status)),
      ),
    ),
  );
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  load(stateFromForm(1));
});

form.addEventListener("reset", () => {
  // Espera o navegador limpar os campos antes de recarregar.
  setTimeout(() => load(stateFromForm(1)));
});

async function init() {
  try {
    await loadResources();
  } catch (error) {
    showError(errorBox, error);
  }
  const state = readStateFromUrl();
  fillForm(state);
  await load(state);
}

init();
