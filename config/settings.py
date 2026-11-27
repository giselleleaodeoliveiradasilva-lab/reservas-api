"""
Configuração do projeto. Todo valor sensível ou dependente de ambiente vem de
variáveis de ambiente (opcionalmente carregadas de um arquivo .env).
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Variáveis já presentes no ambiente têm prioridade sobre o .env.
load_dotenv(BASE_DIR / ".env", override=False)


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def env_bool(name: str, default: bool = False) -> bool:
    return env(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Núcleo -------------------------------------------------------------------

DEBUG = env_bool("DJANGO_DEBUG", False)

# Em produção a chave é obrigatória; em DEBUG há um valor de conveniência.
SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key" if DEBUG else None)

ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "core.idempotency",
    "reservations",
    "web",
]

MIDDLEWARE = [
    # Primeiro da cadeia: tudo que for logado depois já tem request_id.
    "core.middleware.RequestIdMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Templates só para a interface web (o app `web`); a API responde JSON.
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # destino do `collectstatic` em produção

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Banco de dados -------------------------------------------------------------
# Um único conjunto de variáveis serve aos dois SGBDs; DB_ENGINE escolhe o backend.

_DB_BACKENDS = {
    "postgresql": ("django.db.backends.postgresql", "5432"),
    "mysql": ("django.db.backends.mysql", "3306"),
}

DB_ENGINE = env("DB_ENGINE", "postgresql").lower()
if DB_ENGINE not in _DB_BACKENDS:
    raise ImproperlyConfigured(f"DB_ENGINE deve ser um de {sorted(_DB_BACKENDS)}; recebido: {DB_ENGINE!r}")

_backend, _default_port = _DB_BACKENDS[DB_ENGINE]

_db_options: dict = {}
_db_test: dict = {}
if DB_ENGINE == "mysql":
    _db_options = {
        "charset": "utf8mb4",
        # Modo estrito: o MySQL rejeita (em vez de truncar) dados inválidos.
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        # O padrão do MySQL é REPEATABLE READ; usamos READ COMMITTED para ter
        # a mesma semântica do PostgreSQL nas leituras após um lock.
        "isolation_level": "read committed",
    }
    _db_test = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}

DATABASES = {
    "default": {
        "ENGINE": _backend,
        "NAME": env("DB_NAME", "reservas"),
        "USER": env("DB_USER", "reservas"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "127.0.0.1"),
        "PORT": env("DB_PORT", _default_port),
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "60")),
        "OPTIONS": _db_options,
        "TEST": _db_test,
    }
}

# --- Django REST Framework ------------------------------------------------------

REST_FRAMEWORK = {
    # Autenticação está fora do escopo deste projeto.
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "EXCEPTION_HANDLER": "core.exception_handler.api_exception_handler",
}

# --- Logging --------------------------------------------------------------------

LOG_LEVEL = env("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "core.logging.RequestIdFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s [request_id=%(request_id)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # O log de acesso é feito pelo RequestIdMiddleware; evita duplicidade.
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
}
