"""Installation API for managing SQLite triggers."""

from __future__ import annotations

import logging
from typing import Union

from django.db import DEFAULT_DB_ALIAS, connections

from sqlitetrigger import registry

LOGGER = logging.getLogger("sqlitetrigger")


def _get_installed_triggers(database: str = DEFAULT_DB_ALIAS) -> dict[str, str]:
    """Get all sqlitetrigger-managed triggers from the database.

    Returns a dict of {trigger_name: sql}.
    """
    connection = connections[database]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'trigger' AND name LIKE 'sqlitetrigger_%'"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


def install(*uris: str, database: Union[str, None] = None) -> None:
    """Install triggers.

    Args:
        *uris: URIs of triggers to install. If none, all registered triggers are installed.
        database: The database alias. Defaults to "default".
    """
    db = database or DEFAULT_DB_ALIAS
    for model, trigger in registry.registered(*uris):
        LOGGER.info(
            "sqlitetrigger: Installing %s trigger for %s table.",
            trigger.name,
            model._meta.db_table,
        )
        trigger.install(model, database=db)

    if not uris:
        prune(database=db)


def uninstall(*uris: str, database: Union[str, None] = None) -> None:
    """Uninstall triggers.

    Args:
        *uris: URIs of triggers to uninstall. If none, all registered triggers are uninstalled.
        database: The database alias. Defaults to "default".
    """
    db = database or DEFAULT_DB_ALIAS
    for model, trigger in registry.registered(*uris):
        LOGGER.info(
            "sqlitetrigger: Uninstalling %s trigger for %s table.",
            trigger.name,
            model._meta.db_table,
        )
        trigger.uninstall(model, database=db)


def prune(database: Union[str, None] = None) -> list[str]:
    """Remove orphaned sqlitetrigger-managed triggers not in the registry.

    Returns the names of pruned triggers.
    """
    db = database or DEFAULT_DB_ALIAS
    installed = _get_installed_triggers(db)

    # Build set of expected trigger names from registry
    expected = set()
    for model, trigger in registry.registered():
        for stmt in trigger.compile(model):
            # Extract trigger name from CREATE TRIGGER statement
            # Format: "CREATE TRIGGER trigger_name\n..."
            trigger_name = stmt.split("\n")[0].replace("CREATE TRIGGER ", "")
            expected.add(trigger_name)

    pruned = []
    connection = connections[db]
    with connection.cursor() as cursor:
        for name in installed:
            if name not in expected:
                LOGGER.info("sqlitetrigger: Pruning orphaned trigger %s.", name)
                cursor.execute(f"DROP TRIGGER IF EXISTS {name}")
                pruned.append(name)

    return pruned


def status(*uris: str, database: Union[str, None] = None) -> list[dict]:
    """Get the installation status of triggers.

    Returns a list of dicts with keys: uri, trigger_name, table, status.
    Status is one of: INSTALLED, UNINSTALLED, OUTDATED.
    """
    db = database or DEFAULT_DB_ALIAS
    installed = _get_installed_triggers(db)
    results = []

    for model, trigger in registry.registered(*uris):
        uri = f"{model._meta.label}:{trigger.name}"
        expected_stmts = trigger.compile(model)

        for stmt in expected_stmts:
            trigger_name = stmt.split("\n")[0].replace("CREATE TRIGGER ", "")
            if trigger_name in installed:
                # Compare SQL to detect outdated triggers
                # Normalize whitespace for comparison
                installed_sql = " ".join(installed[trigger_name].split())
                expected_sql = " ".join(stmt.rstrip(";").split())
                if installed_sql == expected_sql:
                    trigger_status = "INSTALLED"
                else:
                    trigger_status = "OUTDATED"
            else:
                trigger_status = "UNINSTALLED"

            results.append({
                "uri": uri,
                "trigger_name": trigger_name,
                "table": model._meta.db_table,
                "status": trigger_status,
            })

    return results
