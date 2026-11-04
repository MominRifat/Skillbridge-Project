import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

_env_file = BASE_DIR / '.env'
if _env_file.exists():
    with open(_env_file, encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and (not _line.startswith('#')) and ('=' in _line):
                _k, _v = _line.split('=', 1)
                os.environ.setdefault(_k.strip(), _v.strip().strip('\'"'))

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-local-development-only-change-before-deploying')

DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver', '.onrender.com']
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
_extra_hosts = os.getenv('ALLOWED_HOSTS', '')
if _extra_hosts:
    ALLOWED_HOSTS.extend([h.strip() for h in _extra_hosts.split(',') if h.strip()])

CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000', 'https://*.onrender.com']
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')
_extra_csrf = os.getenv('CSRF_TRUSTED_ORIGINS', '')
if _extra_csrf:
    CSRF_TRUSTED_ORIGINS.extend([c.strip() for c in _extra_csrf.split(',') if c.strip()])

DJANGO_APPS = [
    'apps.core.admin_config.SkillbridgeAdminConfig',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize'
]

SKILLBRIDGE_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.profiles',
    'apps.portfolios',
    'apps.wallets',
    'apps.marketplace',
    'apps.proposals',
    'apps.negotiations',
    'apps.agreements',
    'apps.messaging',
    'apps.notifications',
    'apps.projects',
    'apps.tasks'
]

INSTALLED_APPS = DJANGO_APPS + SKILLBRIDGE_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.RequestActorMiddleware',
    'apps.core.middleware.DomainErrorMiddleware'
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site',
                'apps.wallets.context_processors.wallet',
                'apps.notifications.context_processors.unread'
            ],
            'builtins': ['apps.core.templatetags.skillbridge']
        }
    }
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database configuration: uses Render PostgreSQL if DATABASE_URL is set, otherwise falls back to SQLite3
_database_url = os.getenv('DATABASE_URL')
if _database_url:
    DATABASES = {
        'default': dj_database_url.config(
            default=_database_url,
            conn_max_age=600,
            conn_health_checks=True
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {'timeout': 20}
        }
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['apps.accounts.backends.EmailOrUsernameBackend']

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}
]

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'
WHITENOISE_USE_FINDERS = True

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

_smtp_user = os.getenv('EMAIL_HOST_USER', 'trexrifat8@gmail.com').strip()
_smtp_pass = os.getenv('EMAIL_HOST_PASSWORD', 'tukb wszr wvtg usxr').strip()
if not _smtp_user or _smtp_user == 'your_email@gmail.com':
    _smtp_user = 'trexrifat8@gmail.com'
if not _smtp_pass:
    _smtp_pass = 'tukb wszr wvtg usxr'

EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'config.http_email_backend.HybridEmailBackend')
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '').strip()
BREVO_API_KEY = os.getenv('BREVO_API_KEY', '').strip()
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_USE_SSL = os.getenv('EMAIL_USE_SSL', 'False').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = _smtp_user
EMAIL_HOST_PASSWORD = _smtp_pass
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', 15))
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', f"SkillBridge <{_smtp_user}>")

_default_site_url = f"https://{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else 'http://127.0.0.1:8000'
SITE_URL = os.getenv('SITE_URL', _default_site_url)
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = 'DENY'

# Production Security Headers (Active when DEBUG is False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'False').lower() in ('true', '1', 'yes')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

SKILLCOIN = {'CODE': 'SKC', 'SYMBOL': '৳ ', 'NAME': 'SkillCoin', 'BDT_RATE': 1, 'DECIMAL_PLACES': 2}
BUSINESS_RULES = {
    'TASK_REVIEW_WINDOW_HOURS': 48,
    'PROJECT_REVIEW_WINDOW_HOURS': 48,
    'OFFER_EXPIRY_HOURS': 72,
    'TEAM_INVITE_EXPIRY_HOURS': 168,
    'EMAIL_TOKEN_EXPIRY_HOURS': 48,
    'MIN_DEPOSIT': 100,
    'MIN_WITHDRAWAL': 500,
    'MIN_JOB_BUDGET': 0,
    'MAX_PORTFOLIO_REFERENCES': 5,
    'DEFAULT_REVISION_LIMIT': 2,
    'MAX_UPLOAD_MB': 25,
    'PAGE_SIZE': 20
}

ALLOWED_UPLOAD_EXTENSIONS = [
    'pdf', 'doc', 'docx', 'odt', 'rtf', 'txt', 'md', 'csv', 'xls', 'xlsx',
    'ppt', 'pptx', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'zip', 'tar',
    'gz', 'json', 'xml', 'psd', 'fig', 'sketch'
]

PAYMENT_CHANNELS = {
    'BKASH': {'label': 'bKash', 'number': '01700000000', 'type': 'Merchant'},
    'NAGAD': {'label': 'Nagad', 'number': '01800000000', 'type': 'Merchant'}
}

AI = {'ENABLED': True, 'PROVIDER': None}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} [{name}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

