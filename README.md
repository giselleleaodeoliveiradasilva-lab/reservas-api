# Reservas API

API REST em **Python 3 + Django + Django REST Framework** para reserva de recursos (salas, equipamentos) com regras de conflito de horário, máquina de estados, idempotência, trilha de auditoria e rastreio por `request_id`. Funciona com **PostgreSQL** e **MySQL**, usando as mesmas migrations.

O foco é confiabilidade: integridade garantida no banco, operações críticas atômicas, concorrência tratada explicitamente e um formato de erro único.

---

## Funcionalidades

1. **Cadastro e consulta** de recursos e reservas. Um recurso não pode ter duas reservas *ativas* com horários sobrepostos.
2. **Mudança de estado** com regras explícitas:

   ```
   PENDENTE   ──► CONFIRMADA ──► CONCLUIDA
      │              │
      └──────────────┴──────► CANCELADA
   ```
   `CANCELADA` e `CONCLUIDA` são estados finais. Só `PENDENTE` e `CONFIRMADA` ocupam horário.
3. **Listagem paginada com filtros**, **histórico** de cada reserva e tratamento de **conflito e duplicidade**.

## Arquitetura

```
config/                 settings (via variáveis de ambiente), urls, wsgi
core/                   código transversal, sem regra de negócio
  middleware.py         RequestIdMiddleware: X-Request-Id + log de acesso
  logging.py            request_id em contextvars, injetado em todo log
  exceptions.py         DomainError e categorias (validação, não encontrado, conflito...)
  exception_handler.py  handler central do DRF: formato de erro único
  idempotency/          modelo IdempotencyKey, execução idempotente, helpers HTTP
reservations/
  models.py             Resource, Reservation, ReservationStatusHistory + constraints
  state_machine.py      transições permitidas (funções puras)
  exceptions.py         exceções de domínio de reservas
  selectors.py          consultas de leitura
  services.py           casos de uso de escrita: transação, locks, auditoria
  api/                  serializers, filtros, views finas, urls
  tests/unit            máquina de estados, idempotência, services
  tests/integration     endpoints, erros, idempotência, concorrência real
web/                    interface web: templates + JS que consome a API (sem regra de negócio)
```

As dependências vão sempre de cima para baixo: **HTTP → services → domínio**.

- **Views** validam o formato da entrada, chamam um service ou selector e serializam a saída. Não têm regra de negócio nem controle de transação.
- **Services** orquestram o caso de uso dentro de `transaction.atomic()`, aplicam locks e gravam a auditoria.
- **Domínio** (modelos, máquina de estados, exceções) guarda as invariantes. As exceções de domínio não conhecem HTTP: o mapeamento para status HTTP fica no `exception_handler`.

## Decisões técnicas

### Conflito de horário sem recurso exclusivo de um banco
O PostgreSQL resolveria isso com `ExclusionConstraint`, mas ela não existe no MySQL. A solução portável é um **lock pessimista na linha do recurso** (`select_for_update()`) antes de checar a sobreposição e inserir. Assim, criações concorrentes para o *mesmo* recurso esperam a vez umas das outras, enquanto recursos diferentes não se bloqueiam. O teste `test_concurrency.py` dispara 5 requisições simultâneas e verifica que exatamente uma vence.

Os intervalos são **semiabertos** `[início, fim)`: uma reserva até 10h e outra a partir das 10h não conflitam.

### Transições concorrentes
A transição também trava a linha da reserva. Sem isso, "concluir" e "cancelar" enviados ao mesmo tempo poderiam ler o mesmo estado `CONFIRMADA` e os dois seriam aplicados. Com o lock, o segundo vê o estado já alterado e recebe 409.

### Isolamento no MySQL
O padrão do MySQL é `REPEATABLE READ`. Configuramos `READ COMMITTED`, que é o padrão do PostgreSQL, para que a leitura feita depois de obter o lock enxergue o que outras transações já gravaram. O comportamento fica igual nos dois bancos.

### Idempotência
Os endpoints `POST /reservations/` e `POST /reservations/{id}/transitions/` exigem o cabeçalho `Idempotency-Key`. A chave é **inserida antes** de executar a operação, na mesma transação, e protegida por `UniqueConstraint(scope, key)`:

- **Reenvio com o mesmo payload**: devolve a resposta original salva, com o cabeçalho `Idempotent-Replayed: true`, sem executar nada de novo. Um "cancelar" reenviado devolve 200, não 409.
- **Mesma chave com payload diferente**: **422** `idempotency_key_reused`. O payload é comparado por um hash SHA-256 canônico.
- **Duas requisições simultâneas com a mesma chave**: a segunda fica bloqueada no índice único até a primeira terminar e então devolve a mesma resposta. Inserir a chave *depois* da operação seria um erro: a segunda requisição veria a reserva da primeira e devolveria 409 em vez de repetir a resposta.
- **Só respostas de sucesso ficam salvas.** Um erro de negócio desfaz a transação inteira, chave incluída, e o cliente pode corrigir e tentar de novo.

### Unicidade de nome portável
A collation padrão do MySQL ignora maiúsculas e minúsculas; a do PostgreSQL não. Para que "Sala Azul" e "sala  azul" sejam tratados como duplicados nos dois bancos, o modelo grava `normalized_name` (espaços colapsados + `casefold`) com `UniqueConstraint`. A duplicidade é detectada pelo banco, sem SELECT prévio (que teria condição de corrida), e traduzida para 409.

### Integridade no banco
`CheckConstraint(end_at > start_at)`, `CheckConstraint(status válido)`, `UniqueConstraint` nos nomes e nas chaves de idempotência, e FKs com `PROTECT` (histórico de auditoria não é apagado em cascata). No MySQL, os `CheckConstraint` só são respeitados a partir da **versão 8.0.16**.

### Serializers de entrada simples
Os serializers de entrada são `Serializer` comuns, não `ModelSerializer`. Assim o DRF não gera validadores automáticos de unicidade: duplicidade é sempre 409 vinda do domínio, e nunca um 400 diferente dependendo de quem detectou.

### Observabilidade
- `RequestIdMiddleware` reaproveita o `X-Request-Id` recebido, se for seguro (até 64 caracteres entre `[A-Za-z0-9._-]`, o que evita injeção nos logs), ou gera um UUID. Devolve o valor no cabeçalho da resposta e registra uma linha de acesso com status e duração.
- O `request_id` fica num `contextvar` e aparece em **toda** linha de log.
- Cada mudança de estado grava `from_status`, `to_status`, `changed_at`, `idempotency_key` e `request_id`.

## Formato de erro

Todo erro, de domínio, de validação ou inesperado, sai assim:

```json
{
  "error": {
    "code": "reservation_conflict",
    "message": "O recurso já possui uma reserva ativa que se sobrepõe a este período.",
    "details": {"conflicting_reservation_id": 12, "conflicting_start_at": "...", "conflicting_end_at": "..."},
    "request_id": "9f2c1b..."
  }
}
```

| HTTP | `code` (exemplos) |
|---|---|
| 400 | `validation_error`, `malformed_request`, `invalid_reservation_period`, `idempotency_key_required`, `idempotency_key_invalid` |
| 404 | `not_found`, `resource_not_found`, `reservation_not_found` |
| 405 | `method_not_allowed` |
| 409 | `reservation_conflict`, `invalid_status_transition`, `resource_already_exists` |
| 422 | `idempotency_key_reused` |
| 500 | `internal_error`: mensagem genérica, sem traceback; o detalhe vai só para o log, com o `request_id` |

## Endpoints (`/api/v1`)

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/resources/` | Cria recurso |
| `GET` | `/resources/` | Lista recursos (paginada) |
| `GET` | `/resources/{id}/` | Detalha recurso |
| `POST` | `/reservations/` | Cria reserva (**exige `Idempotency-Key`**) |
| `GET` | `/reservations/` | Lista reservas. Filtros: `resource`, `status`, `start_from`, `start_to`; paginação: `page`, `page_size` (máx. 100) |
| `GET` | `/reservations/{id}/` | Detalha reserva (inclui `allowed_transitions`) |
| `POST` | `/reservations/{id}/transitions/` | Muda o status: `{"to_status": "CONFIRMADA"}` (**exige `Idempotency-Key`**) |
| `GET` | `/reservations/{id}/history/` | Histórico de estados (paginado) |

Os filtros `start_from` e `start_to` definem a janela `start_from <= start_at < start_to`, com datas em ISO 8601.

Toda reserva retornada traz `allowed_transitions`: a lista de status para os quais ela pode ir agora, calculada pela própria máquina de estados (ex.: `["CANCELADA", "CONFIRMADA"]` para uma pendente). Assim os clientes não precisam copiar a regra. O campo é **informativo**: entre a leitura e a ação o estado pode mudar, e a transição continua sendo validada pelo service, que responde 409 se não for mais permitida.

### Exemplo

```bash
curl -X POST localhost:8000/api/v1/resources/ \
  -H "Content-Type: application/json" -d '{"name": "Sala Azul"}'

curl -X POST localhost:8000/api/v1/reservations/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 6f1d0c3e-reserva-ana" \
  -d '{"resource_id": 1, "customer_name": "Ana", "start_at": "2030-01-10T10:00:00Z", "end_at": "2030-01-10T11:00:00Z"}'

curl -X POST localhost:8000/api/v1/reservations/1/transitions/ \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: 6f1d0c3e-confirma-1" \
  -d '{"to_status": "CONFIRMADA"}'

curl localhost:8000/api/v1/reservations/1/history/
```

## Interface web

Há uma interface simples em `/`, feita com templates Django, CSS e JavaScript puro (módulos ES), sem build e sem dependências novas. É servida pelo mesmo Django da API, então não precisa de CORS.

| Página | Rota | API consumida |
|---|---|---|
| Reservas (lista, filtros, paginação) | `/` | `GET /reservations/`, `GET /resources/` |
| Nova reserva | `/reservas/nova/` | `POST /reservations/` |
| Detalhe, ações e histórico | `/reservas/<id>/` | `GET /reservations/{id}/`, `POST .../transitions/`, `GET .../history/` |
| Recursos | `/recursos/` | `GET` e `POST /resources/` |

**Princípio: o backend decide, o front apresenta.**
- As views do app `web` só entregam o HTML, sem consultar o banco. Todos os dados vêm da API pública, então a interface é um cliente como qualquer outro.
- O front não tem regra de negócio. Conflito, período, reserva no passado e duplicidade são decididos pela API, e a tela mostra `error.message`, os detalhes (ex.: link para a reserva em conflito) e o `request_id`. Os erros de campo (400) aparecem ao lado do campo correspondente.
- Os botões de ação são gerados a partir de `allowed_transitions`. Não existe `if status == ...` no JavaScript. Depois de uma ação (sucesso ou 409), a tela recarrega reserva e histórico da API.
- **Idempotency-Key**: cada ação recebe uma chave (`crypto.randomUUID()`). Reenviar a mesma ação com o mesmo payload, por exemplo depois de uma falha de rede, reaproveita a chave, e o backend devolve o resultado original sem duplicar. Se o payload mudar, ou depois de um sucesso, a chave é trocada.
- Os dados da API são inseridos no DOM apenas via `textContent`, o que evita XSS.
- Horários são digitados no fuso do navegador e enviados à API em ISO 8601 UTC.

Em produção (`DJANGO_DEBUG=false`), rode `python manage.py collectstatic` e sirva a pasta `staticfiles/` pelo servidor web (ex.: Nginx).

## Como executar

### Requisitos
- Python 3.11+
- PostgreSQL 13+ **ou** MySQL 8.0.16+
- No Linux, o driver `mysqlclient` precisa dos headers do MySQL (`libmysqlclient-dev` / `mysql-devel`) e de `pkg-config`. No Windows e no macOS, o pip instala a versão pré-compilada.

### Instalação

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # e edite
```

### Configuração do banco

Todas as configurações vêm de variáveis de ambiente, opcionalmente lidas de um arquivo `.env`. Variáveis já definidas no ambiente têm prioridade sobre o `.env`.

| Variável | Padrão | Descrição |
|---|---|---|
| `DB_ENGINE` | `postgresql` | `postgresql` ou `mysql` |
| `DB_NAME` | `reservas` | Nome do banco |
| `DB_USER` | `reservas` | Usuário |
| `DB_PASSWORD` | *(vazio)* | Senha |
| `DB_HOST` | `127.0.0.1` | Host |
| `DB_PORT` | `5432` / `3306` | Porta (o padrão depende do engine) |
| `DB_CONN_MAX_AGE` | `60` | Tempo, em segundos, que uma conexão é reaproveitada |
| `DJANGO_SECRET_KEY` | obrigatória se `DEBUG=false` | Chave secreta |
| `DJANGO_DEBUG` | `false` | Modo debug |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts aceitos (separados por vírgula) |
| `LOG_LEVEL` | `INFO` | Nível de log |

**PostgreSQL**: criar usuário e banco (no `psql`, como superusuário):

```sql
CREATE USER reservas WITH PASSWORD 'reservas' CREATEDB;  -- CREATEDB: os testes criam o banco test_reservas
CREATE DATABASE reservas OWNER reservas;
```

```env
DB_ENGINE=postgresql
DB_PORT=5432
```

**MySQL**: criar usuário e banco (no cliente `mysql`, como root):

```sql
CREATE DATABASE reservas CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'reservas'@'localhost' IDENTIFIED BY 'reservas';
GRANT ALL PRIVILEGES ON reservas.* TO 'reservas'@'localhost';
GRANT ALL PRIVILEGES ON test_reservas.* TO 'reservas'@'localhost';  -- banco usado pelos testes
```

```env
DB_ENGINE=mysql
DB_PORT=3306
```

### Migrations e servidor

```bash
python manage.py migrate
python manage.py runserver
```

Interface: http://localhost:8000/ · API: http://localhost:8000/api/v1/

### Testes

Os testes rodam no banco configurado em `DB_ENGINE`, e o Django cria e apaga o banco `test_<DB_NAME>` automaticamente. **Não usamos SQLite nos testes**: ele ignora `SELECT ... FOR UPDATE`, então os testes de concorrência passariam sem provar nada.

```bash
pytest                                   # tudo
pytest reservations/tests/unit           # só unitários
pytest reservations/tests/integration    # só integração
pytest web                               # páginas da interface (não usam banco)
```

Para validar nos dois bancos, troque `DB_ENGINE` e rode de novo:

```bash
DB_ENGINE=postgresql pytest
DB_ENGINE=mysql DB_PORT=3306 pytest
```

No PowerShell: `$env:DB_ENGINE="mysql"; $env:DB_PORT="3306"; pytest`.

O que é coberto:
- **Unitários**: todas as combinações de transição (permitidas e proibidas), hash e fluxo de idempotência, regras dos services (período, passado, sobreposição, intervalos adjacentes, liberação de horário após cancelamento ou conclusão, duplicidade de nome, `CheckConstraint` do banco).
- **Integração**: todos os endpoints, formato de erro, 400/404/405/409/422/500 (sem vazar detalhes), filtros e paginação, replay idempotente, chave reutilizada com outro payload, histórico e propagação do `X-Request-Id`.
- **Concorrência** (threads com conexões próprias e commits reais): 5 reservas sobrepostas simultâneas resultam em 1 criada e 4 recusadas com 409; 5 reenvios simultâneos com a mesma chave criam 1 reserva só; transições conflitantes simultâneas têm exatamente uma aplicada.

## Limitações e próximos passos (fora do escopo atual)

- Autenticação e autorização (hoje a API é aberta).
- Expiração das chaves de idempotência (ex.: job que apaga chaves com mais de 24h).
- Exportar métricas e traces (Prometheus/OpenTelemetry) além dos logs.
