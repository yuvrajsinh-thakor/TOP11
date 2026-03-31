from .base import *

DEBUG = True

# In development, print emails to console instead of sending
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Allow all CORS in development
CORS_ALLOW_ALL_ORIGINS = True

# Show detailed errors
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}