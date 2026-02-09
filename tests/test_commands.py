import pytest
from django.core.management import call_command
from io import StringIO

from sqlitetrigger import installation


@pytest.fixture(autouse=True)
def _install_triggers(db):
    installation.install()
    yield
    installation.uninstall()


@pytest.mark.django_db
def test_ls():
    out = StringIO()
    call_command("sqlitetrigger", "ls", stdout=out)
    output = out.getvalue()
    assert "protect_deletes" in output
    assert "INSTALLED" in output


@pytest.mark.django_db
def test_install_command():
    out = StringIO()
    call_command("sqlitetrigger", "install", stdout=out)
    assert "installed" in out.getvalue().lower()


@pytest.mark.django_db
def test_uninstall_command():
    out = StringIO()
    call_command("sqlitetrigger", "uninstall", stdout=out)
    assert "uninstalled" in out.getvalue().lower()
