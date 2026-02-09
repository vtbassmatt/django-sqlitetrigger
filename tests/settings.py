SECRET_KEY = "django-sqlitetrigger-tests"

INSTALLED_APPS = [
    "sqlitetrigger",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "tests",
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
USE_TZ = False
