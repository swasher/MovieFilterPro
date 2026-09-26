"""
Django settings for moviefilterpro project.

Adopted by SWASHER for using Django 5.1.5.

"""

import os
import tomllib
from pathlib import Path
from decouple import config
from django.contrib import messages


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', cast=bool)

ENABLE_DEBUG_TOOLBAR = config('ENABLE_DEBUG_TOOLBAR', cast=bool)
ENABLE_BROWSER_RELOAD = config('ENABLE_BROWSER_RELOAD', cast=bool)
ENABLE_SAAS_COMPILER = False

KINOZAL_SCAN_PRINT = False  # Выводить ли логи сканирования kinozal в консоль.

SECURE_CROSS_ORIGIN_OPENER_POLICY = None

INFINITE_PAGINATION_BY = 4

# ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.fly.dev']
ALLOWED_HOSTS = ['*']
# CSRF_TRUSTED_ORIGINS = ['https://*.fly.dev']
# CSRF_TRUSTED_ORIGINS = ['*']

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = 'core:login'
LOGOUT_REDIRECT_URL = 'core:login'

DEBUG_LOG = os.path.join(BASE_DIR, 'logs', 'debug.log')
ERROR_LOG = os.path.join(BASE_DIR, 'logs', 'error.log')
SCAN_LOG = os.path.join(BASE_DIR, 'logs', 'scan.log')

with open("pyproject.toml", "rb") as f:
    pyproject = tomllib.load(f)
    VERSION = pyproject["project"]["version"]

INTERNAL_IPS = [
    "127.0.0.1",
]

#
# Priority constants
#
HIGH = 0
LOW = 1
DEFER = 2
SKIP = 3
WAIT_TRANS = 4
TRANS_FOUND = 5

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.postgres',
    'core',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_htmx',
    'widget_tweaks',
    'channels',
    'moviefilter',
    'tmdb_adapter',
    'plex',
    'tmdb',
    'kinorium',
    'vault',
    'kinozal_scan',
    'web_logger',
]
if ENABLE_BROWSER_RELOAD:
    INSTALLED_APPS.append('django_browser_reload')
    INSTALLED_APPS.append('django_watchfiles')
if ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS.append('debug_toolbar')


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'moviefilter.middleware.toast_middleware.HtmxMessageMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]
if ENABLE_DEBUG_TOOLBAR:
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')
if ENABLE_BROWSER_RELOAD:
    MIDDLEWARE.append('django_browser_reload.middleware.BrowserReloadMiddleware')

ROOT_URLCONF = 'movie_filter_pro.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "core.context_processors.version_processor",
                "core.context_processors.dev_banner_processor",
            ],
        },
    },
]

WSGI_APPLICATION = 'movie_filter_pro.wsgi.application'


#
# Database
#

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('POSTGRES_DB'),
        'USER': config('POSTGRES_USER'),
        'PASSWORD': config('POSTGRES_PASSWORD'),
        'HOST': config('POSTGRES_HOST'),
        'PORT': config('POSTGRES_PORT', default='5432'),
        'CONN_MAX_AGE': 60,
        'CONN_HEALTH_CHECKS': True,
    }
}

# if not os.getenv('IN_DOCKER'):
#     database_path = config('DATABASE_URL').split('///')[-1]
#     if not os.path.exists(database_path):
#         print(f"Database file not found at {database_path}")
#         raise FileNotFoundError(f"Database file not found at {database_path}")
#     else:
#         print(f"Database file found at {database_path}")


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True



#
# FRONTEND (Svelte static build, отдаём через WhiteNoise с корня домена)
#
FRONT_BUILD_DIR = BASE_DIR / 'front' / 'build'
if not DEBUG and FRONT_BUILD_DIR.exists():
    WHITENOISE_ROOT = str(FRONT_BUILD_DIR)
    WHITENOISE_INDEX_FILE = True

#
# STATIC
#
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'collectstatic')
STATICFILES_DIRS = []
static_dir = BASE_DIR / 'static'
if static_dir.exists():
    STATICFILES_DIRS.append(str(static_dir))

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]


if ENABLE_SAAS_COMPILER:
    COMPRESS_PRECOMPILERS = (
        ('text/x-scss', 'django_libsass.SassCompiler'),
    )

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

CACHE_ROOT = MEDIA_ROOT / "cached_images"
CACHE_URL = MEDIA_URL + "cached_images/"


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

#
# CRISPY
#
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"


#
# HTMX Toasts
#
MESSAGE_TAGS = {
    messages.DEBUG: "bg-light",
    messages.INFO: "text-white bg-primary",
    messages.SUCCESS: "text-white bg-success",
    messages.WARNING: "text-dark bg-warning",
    messages.ERROR: "text-white bg-danger",
}

#
# LOGGING
#
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,

    'filters': {
        'require_scan_debug': {
            '()': 'django.utils.log.CallbackFilter',
            'callback': lambda record: KINOZAL_SCAN_PRINT,
        },
    },

    'handlers': {
        'error_log': {  # Django errors
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': ERROR_LOG,
        },
        'console': {  # New handler for console output
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
        },
        'debug_log': {  # Use as 'print' for debugging info
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': DEBUG_LOG,
        },
        'scan_log': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': SCAN_LOG,
        },
        'kinozal_console': {  # use as: kinozal_logger = logging.getLogger('kinozal'); kinozal_logger.debug("Сообщение") или любой уровень. Выключается/включается переменной KINOZAL_SCAN_PRINT
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'filters': ['require_scan_debug'],
            'formatter': 'simple',
        },
    },

    'formatters': {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },

    'loggers': {
        'django': {  # django errors logger
            'handlers': ['console', 'error_log'] if DEBUG else ['error_log'],
            'level': 'ERROR',
            'propagate': True,
        },
        'debug_logger': {
            'handlers': ['debug_log'],
            'level': 'DEBUG',
            'propagate': False,  # it needs to stop double logging
        },
        'scan_logger': {
            'handlers': ['scan_log'],
            'level': 'INFO',
            'propagate': False,
        },
        'kinozal': {   # use as kinozal_logger = logging.getLogger('kinozal'); kinozal_logger.debug("Сообщение") или любой уровень. Выключается/включается переменной KINOZAL_SCAN_PRINT
            'handlers': ['kinozal_console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'vault.tmdb_writeback': {
            'handlers': ['debug_log', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'vault.tmdb_sync': {
            'handlers': ['debug_log', 'console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',  # Для разработки
    },
}

SOURCE_MIRRORS = {
    "kinozal.tv": "kinozal.guru",
    # можно добавить другие источники при необходимости
}

# TMDB
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/"  # Но по феншую эта строка берется из /configuration эндпоинта TMDB API

# OMDB
# Legacy fallback: основной источник — UserPreferences.omdb_api_key (см. OMDBService.get_api_key).
OMDB_API_KEY = config("OMDB_API_KEY", default="")

# Tavily
# Legacy/dev fallback: основной источник — UserPreferences.tavily_api_key (см. TavilyService.get_api_key).
TAVILY_API_KEY = config("TAVILY_API_KEY", default="")
