"""Management command for sqlitetrigger."""

import logging

from django.core.management.base import BaseCommand

from sqlitetrigger import installation, registry


def _setup_logging():
    installation.LOGGER.addHandler(logging.StreamHandler())
    if not installation.LOGGER.level:
        installation.LOGGER.setLevel(logging.INFO)


class Command(BaseCommand):
    help = "Manage SQLite triggers."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(title="sub-commands", required=True)

        ls_parser = subparsers.add_parser("ls", help="List triggers and their status.")
        ls_parser.add_argument("uris", nargs="*", type=str)
        ls_parser.add_argument("-d", "--database", help="The database alias")
        ls_parser.set_defaults(method=self.ls)

        install_parser = subparsers.add_parser("install", help="Install triggers.")
        install_parser.add_argument("uris", nargs="*", type=str)
        install_parser.add_argument("-d", "--database", help="The database alias")
        install_parser.set_defaults(method=self.install)

        uninstall_parser = subparsers.add_parser("uninstall", help="Uninstall triggers.")
        uninstall_parser.add_argument("uris", nargs="*", type=str)
        uninstall_parser.add_argument("-d", "--database", help="The database alias")
        uninstall_parser.set_defaults(method=self.uninstall)

    def handle(self, *args, **options):
        _setup_logging()
        return options["method"](*args, **options)

    def ls(self, *args, **options):
        database = options.get("database")
        uris = options.get("uris", [])

        results = installation.status(*uris, database=database)
        if not results:
            self.stdout.write("No triggers registered.")
            return

        for item in results:
            self.stdout.write(
                f"{item['uri']:50s} {item['trigger_name']:60s} "
                f"{item['table']:30s} {item['status']}"
            )

    def install(self, *args, **options):
        database = options.get("database")
        uris = options.get("uris", [])
        installation.install(*uris, database=database)
        self.stdout.write(self.style.SUCCESS("Triggers installed."))

    def uninstall(self, *args, **options):
        database = options.get("database")
        uris = options.get("uris", [])
        installation.uninstall(*uris, database=database)
        self.stdout.write(self.style.SUCCESS("Triggers uninstalled."))
