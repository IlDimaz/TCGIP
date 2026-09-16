"""
Django settings for config project.

Configuration 12-factor: le variabili sensibili arrivano dall'ambiente
(file .env in locale, variabili d'ambiente sul deploy). In sviluppo si usano
i default; in produzione basta impostare le variabili documentate in .env.example.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carica .env in sviluppo (se presente). Le deploy le iniettano da sole.
load_dotenv(BASE_DIR / '.env')


def env_flag(name, default=False):
    return os.environ.get(name, 'true' if default else 'false').strip().lower() in (
        '1', 'true', 'yes', 'on'
    )


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-!-%=6y+=sdtz3j#g_#hty^2xv*x1ctskbgej2q36!w%5s)s=*w',
)

# SECURITY WARNING: don't run with debug turned on in production!
# Default "safety-first": se esiste DATABASE_URL (quindi siamo su un deploy)
# e DJANGO_DEBUG non è impostata, DEBUG parte a False. In locale resta True.
DEBUG = env_flag(
    'DJANGO_DEBUG',
    default=not bool(os.environ.get('DATABASE_URL')),
)

_APP_DOMAIN = os.environ.get('DJANGO_APP_DOMAIN', '')  # es. tcgip.onrender.com
_allowed = os.environ.get('DJANGO_ALLOWED_HOSTS')
if _allowed:
    ALLOWED_HOSTS = [h.strip() for h in _allowed.split(',') if h.strip()]
else:
    host_list = ['localhost', '127.0.0.1', '[::1]']
    if not DEBUG:
        host_list.append(_APP_DOMAIN)
    ALLOWED_HOSTS = host_list if not DEBUG else ['*']

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if o.strip()
]

# Sicurezza HTTPS: attive solo in produzione (DEBUG=False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_flag('DJANGO_SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "cards",
    "users",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],  # per template condivisi: base.html, home.html, registration/
        'APP_DIRS': True,                    # per template di ogni app, cercati automaticamente
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

# In produzione imposta DATABASE_URL (es. postgres://...). In locale si usa sqlite.
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# Raccolta statica: serve nella build di produzione (collectstatic)
STATIC_ROOT = BASE_DIR / 'staticfiles'

# In produzione WhiteNoise serve gli static con cache e compressione;
# in sviluppo restano i file diritti di Django.
if not DEBUG:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
        },
    }

MEDIA_URL = "/media/"
MEDIA_ROOT = os.environ.get('DJANGO_MEDIA_ROOT', BASE_DIR / 'media')
AUTH_USER_MODEL = "users.User"

LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'
LOGIN_URL = 'login'

# Logging minimo per produzione
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
    },
}