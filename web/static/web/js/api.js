/**
 * Cliente da API /api/v1.
 *
 * - Toda resposta de erro vira um ApiError com o contrato do backend:
 *   { status, code, message, details, requestId }.
 * - Nenhuma regra de negócio aqui: só transporte, cabeçalhos e normalização.
 */

const API_BASE = "/api/v1";
const TIMEOUT_MS = 15000;

export class ApiError extends Error {
  constructor({ status, code, message, details = {}, requestId = null }) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }

  /** Falha de rede/timeout: a requisição pode ou não ter sido processada. */
  get isNetworkError() {
    return this.status === 0;
  }
}

export async function apiRequest(method, path, { body, params, idempotencyKey } = {}) {
  const url = new URL(API_BASE + path, window.location.origin);
  for (const [name, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(name, value);
  }

  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch {
    throw new ApiError({
      status: 0,
      code: "network_error",
      message: "Não foi possível falar com o servidor (sem conexão ou tempo esgotado).",
    });
  }

  const requestId = response.headers.get("X-Request-Id");
  const data = await readJson(response);

  if (!response.ok) {
    const error = data?.error;
    throw new ApiError({
      status: response.status,
      code: error?.code ?? "unexpected_response",
      message: error?.message ?? `Resposta inesperada do servidor (HTTP ${response.status}).`,
      details: error?.details ?? {},
      requestId: error?.request_id ?? requestId,
    });
  }

  return { data, requestId, replayed: response.headers.get("Idempotent-Replayed") === "true" };
}

async function readJson(response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Percorre todas as páginas de um endpoint paginado. */
export async function fetchAllPages(path, params = {}) {
  const items = [];
  for (let page = 1; ; page += 1) {
    const { data } = await apiRequest("GET", path, { params: { ...params, page, page_size: 100 } });
    items.push(...data.results);
    if (!data.next) return items;
  }
}

/**
 * Gerencia a Idempotency-Key de UMA ação do usuário.
 *
 * - Mesma ação com o mesmo payload (ex.: reenvio após falha de rede) => mesma
 *   chave: o backend devolve o resultado original em vez de duplicar.
 * - Payload diferente => chave nova (reusar daria 422 no backend).
 * - Após sucesso, `reset()` garante que a próxima ação tenha chave nova.
 */
export class IdempotentAction {
  #key = null;
  #fingerprint = null;

  keyFor(payload) {
    const fingerprint = JSON.stringify(payload);
    if (this.#key === null || fingerprint !== this.#fingerprint) {
      this.#key = newKey();
      this.#fingerprint = fingerprint;
    }
    return this.#key;
  }

  reset() {
    this.#key = null;
    this.#fingerprint = null;
  }
}

function newKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  // randomUUID só existe em contexto seguro (HTTPS/localhost); fallback equivalente.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
