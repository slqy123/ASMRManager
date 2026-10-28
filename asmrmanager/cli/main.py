import collections
import sys
from importlib import import_module
from typing import Any

import click

from asmrmanager._version import __version__
from asmrmanager.logger import logger

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
sys.stderr.reconfigure(encoding="utf-8")  # type: ignore


class OrderedGroup(click.Group):
    def __init__(self, name=None, commands=None, **attrs):
        super().__init__(name, commands, **attrs)
        self.commands: Any = commands or collections.OrderedDict()

    def list_commands(self, ctx):
        return self.commands

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
        if command is not None and cmd_name in LAZY_COMMANDS:
            command = getattr(
                import_module(f"asmrmanager.cli.{cmd_name}"), cmd_name
            )
            self.commands[cmd_name] = command
        return command

    def format_commands(self, ctx, formatter):
        commands = [
            (name, cmd)
            for name, cmd in self.commands.items()
            if not cmd.hidden
        ]
        if commands:
            limit = (
                formatter.width - 6 - max(len(name) for name, _ in commands)
            )
            with formatter.section("Commands"):
                formatter.write_dl(
                    [
                        (name, cmd.get_short_help_str(limit))
                        for name, cmd in commands
                    ]
                )

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.Abort):
            raise
        except Exception as exc:
            from asmrmanager.spider.asmrapi import APIError
            from asmrmanager.spider.auth import AuthenticationError
            from asmrmanager.spider.downloader import DownloadError
            from asmrmanager.sync import SyncError

            if isinstance(
                exc, (APIError, AuthenticationError, DownloadError, SyncError)
            ):
                raise click.ClickException(str(exc)) from exc
            raise


@click.group(context_settings=CONTEXT_SETTINGS, cls=OrderedGroup)
@click.version_option(__version__, prog_name="ASMRManager")
@click.pass_context
def main(ctx):
    logger.info("Running command: %s", ctx.invoked_subcommand)


try:
    import importlib.util

    if importlib.util.find_spec("trogon"):

        @click.command("tui", help="Open Textual TUI.")
        @click.pass_context
        def tui(ctx: click.Context):
            from trogon import Trogon  # type: ignore

            if ctx.parent is not None:
                for name in LAZY_COMMANDS:
                    main.get_command(ctx.parent, name)
                Trogon(ctx.parent.command, click_context=ctx).run()

        main.add_command(tui)
except ImportError:
    pass

LAZY_COMMANDS = {
    "dl": "download ASMR",
    "info": "show info of the ASMR by id",
    "play": "play asmr with a simple TUI",
    "review": "Set a work's current rating, comment or listening status.",
    "sql": "\n    execute a sql statement by sql file name in `sqls` directory\n    and print the results on your terminal\n\n    for cover support, you must name the first column as `id`\n    ",
    "view": "some operation about view_path",
    "hold": "Hold a work and save the reason as a local note.",
    "query": "\n    simple keyword based query,\n    it will match the input with name, circle_name and tag field.\n    if you want to use more complex queries, please use `asmr sql` instead.\n\n    set limit to 0 if you want to get all results.\n    ",
    "which": "Get the path from the given source_id",
    "file": "file management",
    "pl": "Manage local playlists.",
    "utils": "\n    Some useful utilities\n    ",
    "vote": "vote tags for a work",
    "sync": "Explicitly push local reviews or pull cloud changes.",
}

for name, help_text in LAZY_COMMANDS.items():
    main.add_command(click.Command(name, help=help_text))

if __name__ == "__main__":
    main()
