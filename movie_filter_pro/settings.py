"""
Django settings for moviefilterpro project.

Adopted by SWASHER for using Django 5.1.5.

"""

from pathlib import Path
import os
from decouple import config
import dj_database_url


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')

DEBUG = config('DEBUG', cast=bool)

ENABLE_DEBUG_TOOLBAR = config('ENABLE_DEBUG_TOOLBAR', cast=bool)
ENABLE_BROWSER_RELOAD = config('ENABLE_BROWSER_RELOAD', cast=bool)
ENABLE_SAAS_COMPILER = False

INFINITE_PAGINATION_BY = 4

# ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.fly.dev']
ALLOWED_HOSTS = ['*']
# CSRF_TRUSTED_ORIGINS = ['https://*.fly.dev']
# CSRF_TRUSTED_ORIGINS = ['*']

LOGIN_REDIRECT_URL = "/"
LOGIN_URL = 'login'

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
    'crispy_forms',
    'crispy_bootstrap5',
    'compressor',
    'django_htmx',
    'widget_tweaks',
    'moviefilter',
]
if DEBUG and ENABLE_BROWSER_RELOAD:
    INSTALLED_APPS.append('django_browser_reload')
if DEBUG and ENABLE_DEBUG_TOOLBAR:
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
if DEBUG and ENABLE_DEBUG_TOOLBAR:
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')
if DEBUG and ENABLE_BROWSER_RELOAD:
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
            ],
        },
    },
]

WSGI_APPLICATION = 'movie_filter_pro.wsgi.application'


#
# Database
#
# got DATABASE_URL from environment variable, i.e. Doppler. In case local dev, it's just `sqlite:///db.sqlite3`


DATABASES = {
    # 'default': dj_database_url.config(
    #     conn_max_age=600,
    #     conn_health_checks=True,
    # ),
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': BASE_DIR / 'db.sqlite3',
    # }
    'default': dj_database_url.config(
        default=config('DATABASE_URL')
    )
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
# STATIC
#
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'collectstatic')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'compressor.finders.CompressorFinder',
]

if ENABLE_SAAS_COMPILER:
    COMPRESS_PRECOMPILERS = (
        ('text/x-scss', 'django_libsass.SassCompiler'),
    )

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
    }
}

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_ROOT = BASE_DIR / 'media'

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
from django.contrib import messages
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
    'handlers': {
        'full_log': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'full.log'),
        },
        'short_log': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'short.log'),
        },
        'error_log': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
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
        'my_logger': {
            'handlers': ['full_log', 'short_log', 'error_log'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
