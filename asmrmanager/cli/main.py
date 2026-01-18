# import os
import collections
import sys
from typing import Any

import click

from asmrmanager._version import __version__
from asmrmanager.cli.dl import dl
from asmrmanager.cli.file import file
from asmrmanager.cli.hold import hold
from asmrmanager.cli.info import info
from asmrmanager.cli.pl import pl
from asmrmanager.cli.play import play
from asmrmanager.cli.query import query
from asmrmanager.cli.review import review
from asmrmanager.cli.sql import sql
from asmrmanager.cli.utils import utils
from asmrmanager.cli.view import view
from asmrmanager.cli.vote import vote
from asmrmanager.cli.which import which
from asmrmanager.logger import logger

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
sys.stderr.reconfigure(encoding="utf-8")  # type: ignore


class OrderedGroup(click.Group):
    def __init__(self, name=None, commands=None, **attrs):
        super(OrderedGroup, self).__init__(name, commands, **attrs)
        #: the registered subcommands by their exported names.
        self.commands: Any = commands or collections.OrderedDict()

    def list_commands(self, ctx):
        return self.commands


@click.group(context_settings=CONTEXT_SETTINGS, cls=OrderedGroup)
@click.version_option(__version__, prog_name="ASMRManager")
def main():
    logger.info(f"Run program with: {' '.join(sys.argv[1:])}")


try:
    import importlib.util

    if importlib.util.find_spec("trogon"):
        @click.command("tui", help="Open Textual TUI.")
        @click.pass_context
        def tui(ctx: click.Context):
            from trogon import Trogon  # type: ignore
            if ctx.parent is not None:
                Trogon(ctx.parent.command, click_context=ctx).run()
        main.add_command(tui)
except ImportError:
    pass

main.add_command(dl)
main.add_command(info)
main.add_command(play)
main.add_command(review)
main.add_command(sql)
main.add_command(view)
main.add_command(hold)
main.add_command(query)
main.add_command(which)
main.add_command(file)
main.add_command(pl)
main.add_command(utils)
main.add_command(vote)

if __name__ == "__main__":
    main()
