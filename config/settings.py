"""
Django settings for config project.

Configurado para rodar tanto localmente (SQLite, DEBUG=True por padrão)
quanto em produção no DigitalOcean App Platform (PostgreSQL, Spaces,
variáveis de ambiente). Nada sensível fica escrito neste arquivo: tudo
vem do .env (local) ou das variáveis de ambiente configuradas no painel
do App Platform (produção).
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Em produção (App Platform), as variáveis de ambiente já vêm configuradas
# pelo painel, então não existe (nem é preciso) um arquivo .env. Local:
# copie .env.example para .env e preencha os valores.
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------
# Segurança básica
# ------------------------------------------------------------------

# Em produção, defina DJANGO_SECRET_KEY no painel do App Platform
# (marcado como "Encrypt"). O valor abaixo só serve para rodar local.
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-troque-esta-chave-antes-de-ir-para-producao",
)

# DEBUG=True por padrão localmente. Em produção, defina DJANGO_DEBUG=False.
DEBUG = env_bool("DJANGO_DEBUG", default=True)

# Em produção, defina DJANGO_ALLOWED_HOSTS com os domínios separados por
# vírgula, por exemplo: "questoes.seucursinho.com.br,minha-app.ondigitalocean.app"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# Necessário para o Django aceitar POSTs (login, formulários) vindos do
# seu domínio em HTTPS. Preencha com o(s) domínio(s) finais, incluindo
# "https://", separados por vírgula.
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# App Platform faz o TLS termination antes de chegar no app, então o
# Django precisa saber que a conexão original era HTTPS.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", default=True)


# ------------------------------------------------------------------
# Aplicações
# ------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "questoes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.ManutencaoMiddleware",
    "core.middleware.ForcarTrocaSenhaMiddleware",
]

# Meta de questões por aula (usada no card "Metas" da página inicial).
META_QUESTOES_POR_AULA = 13

# Modo manutenção: com MODO_MANUTENCAO=True, só a coordenação (superusuário)
# usa o site; todos os outros veem a página de manutenção (HTTP 503).
MODO_MANUTENCAO = env_bool("MODO_MANUTENCAO", default=False)

# Login por usuário (coordenação) OU por telefone cadastrado no perfil
# (professores) — os dois backends são tentados nessa ordem.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "core.backends.TelefoneBackend",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.menu_lateral",
                "core.context_processors.nome_usuario",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# ------------------------------------------------------------------
# Banco de dados
# ------------------------------------------------------------------
# Local (sem DATABASE_URL definida): usa SQLite, sem precisar de nada
# instalado além do Django. Produção: defina DATABASE_URL com a string
# de conexão do PostgreSQL gerenciado (o App Platform preenche isso
# automaticamente quando você vincula o banco ao app).

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# ------------------------------------------------------------------
# Senhas
# ------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ------------------------------------------------------------------
# Internacionalização
# ------------------------------------------------------------------

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# ------------------------------------------------------------------
# Arquivos estáticos (CSS/JS do próprio site) via WhiteNoise
# ------------------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


# ------------------------------------------------------------------
# Arquivos enviados pelos professores (imagens das questões) via
# DigitalOcean Spaces (compatível com S3), usando django-storages.
# Só é ativado quando as variáveis do Spaces estão definidas — local,
# sem elas, os uploads caem na pasta media/ do próprio projeto.
# ------------------------------------------------------------------

AWS_ACCESS_KEY_ID = os.environ.get("SPACES_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("SPACES_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.environ.get("SPACES_BUCKET_NAME")
AWS_S3_REGION_NAME = os.environ.get("SPACES_REGION", "nyc3")
AWS_S3_ENDPOINT_URL = os.environ.get(
    "SPACES_ENDPOINT_URL",
    f"https://{AWS_S3_REGION_NAME}.digitaloceanspaces.com" if AWS_S3_REGION_NAME else None,
)

USE_SPACES = bool(AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME)

if USE_SPACES:
    AWS_DEFAULT_ACL = "private"
    AWS_QUERYSTRING_AUTH = True
    # URLs assinadas expiram depois de um tempo — ajuste conforme a
    # necessidade (em segundos). 3600 = 1 hora.
    AWS_QUERYSTRING_EXPIRE = int(os.environ.get("SPACES_URL_EXPIRE_SECONDS", "3600"))
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_CUSTOM_DOMAIN = os.environ.get("SPACES_CDN_DOMAIN")  # opcional, se usar CDN

    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
    }
    MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.{AWS_S3_REGION_NAME}.digitaloceanspaces.com/"
else:
    # Precisa começar com "/" — sem isso, o navegador resolve a URL da
    # imagem relativa à página atual (ex: /painel/questoes/media/...)
    # em vez da raiz do site, e a imagem não carrega.
    MEDIA_URL = "/media/"
    MEDIA_ROOT = BASE_DIR / "media"
    STORAGES["default"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Para onde vai o professor depois de logar / deslogar.
LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "core:painel"
LOGOUT_REDIRECT_URL = "core:login"
