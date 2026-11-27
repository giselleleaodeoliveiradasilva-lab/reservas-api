import { apiRequest, fetchAllPages, IdempotentAction } from "./api.js";
import { clearError, el, localInputToIso, showError, withBusy } from "./ui.js";

const form = document.getElementById("reservation-form");
const errorBox = document.getElementById("error");
const noResources = document.getElementById("no-resources");
const submitButton = form.querySelector("button[type=submit]");

// Uma ação "criar reserva" por formulário. A chave só muda se o payload mudar
// ou após sucesso; reenvio após falha de rede reaproveita a mesma chave.
const createAction = new IdempotentAction();

async function loadResources() {
  const select = form.resource_id;
  try {
    const resources = await fetchAllPages("/resources/");
    select.replaceChildren(
      el("option", { value: "" }, "Selecione…"),
      ...resources.map((r) => el("option", { value: r.id }, r.name)),
    );
    if (!resources.length) {
      noResources.hidden = false;
      form.hidden = true;
    }
  } catch (error) {
    showError(errorBox, error);
  }
}

function buildPayload() {
  const data = new FormData(form);
  return {
    resource_id: Number(data.get("resource_id")),
    customer_name: data.get("customer_name"),
    start_at: localInputToIso(data.get("start_at")),
    end_at: localInputToIso(data.get("end_at")),
  };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError(errorBox, form);

  // Só obrigatoriedade/formato (HTML). Regras de período e conflito ficam na API.
  if (!form.reportValidity()) return;

  const payload = buildPayload();
  const idempotencyKey = createAction.keyFor(payload);

  await withBusy(submitButton, async () => {
    try {
      const { data } = await apiRequest("POST", "/reservations/", { body: payload, idempotencyKey });
      createAction.reset();
      window.location.assign(`/reservas/${data.id}/?criada=1`);
    } catch (error) {
      showError(errorBox, error, { form });
      errorBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });
});

loadResources();
