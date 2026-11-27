import { apiRequest } from "./api.js";
import { clearError, el, emptyRow, flash, formatDateTime, renderPagination, showError, withBusy } from "./ui.js";

const form = document.getElementById("resource-form");
const formError = document.getElementById("form-error");
const errorBox = document.getElementById("error");
const rows = document.getElementById("rows");
const pagination = document.getElementById("pagination");
const submitButton = form.querySelector("button[type=submit]");

let currentPage = 1;

async function load(page = currentPage) {
  currentPage = page;
  clearError(errorBox);
  try {
    const { data } = await apiRequest("GET", "/resources/", { params: { page } });
    rows.replaceChildren(
      ...(data.results.length
        ? data.results.map((r) =>
            el(
              "tr",
              {},
              el("td", {}, `#${r.id}`),
              el("td", {}, r.name),
              el("td", {}, r.description || "—"),
              el("td", {}, formatDateTime(r.created_at)),
            ),
          )
        : [emptyRow(4, "Nenhum recurso cadastrado.")]),
    );
    renderPagination(pagination, data, page, load);
  } catch (error) {
    rows.replaceChildren(emptyRow(4, "Não foi possível carregar os recursos."));
    showError(errorBox, error);
  }
}

// A API não exige Idempotency-Key aqui: a duplicidade é barrada pela
// unicidade do nome no banco (409), que a tela apenas exibe.
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError(formError, form);
  if (!form.reportValidity()) return;

  const data = new FormData(form);
  const payload = { name: data.get("name"), description: data.get("description") };

  await withBusy(submitButton, async () => {
    try {
      const { data: resource } = await apiRequest("POST", "/resources/", { body: payload });
      form.reset();
      flash(`Recurso "${resource.name}" cadastrado.`);
      await load(1);
    } catch (error) {
      showError(formError, error, { form });
    }
  });
});

load();
