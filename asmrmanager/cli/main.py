# import os
import collections
import sys
from typing import Any

import click

from asmrmanager.cli.dl import dl
from asmrmanager.cli.file import file
from asmrmanager.cli.hold import hold
from asmrmanager.cli.info import info
from asmrmanager.cli.play import play
from asmrmanager.cli.query import query
from asmrmanager.cli.review import review
from asmrmanager.cli.show import show
from asmrmanager.cli.sql import sql
from asmrmanager.cli.view import view
from asmrmanager.logger import logger

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


# TODO 可能有的项目更新了汉化会被过滤不会下载，考虑对比has_subtitle
# TODO dry run，clear zip file
# TODO 全局search过滤条件
# TODO query web local local 条件可以简单一些
# TODO 测试各种功能
# catch oserror 然后提醒重试
class OrderedGroup(click.Group):
    def __init__(self, name=None, commands=None, **attrs):
        super(OrderedGroup, self).__init__(name, commands, **attrs)
        #: the registered subcommands by their exported names.
        self.commands: Any = commands or collections.OrderedDict()

    def list_commands(self, _):
        return self.commands


@click.group(context_settings=CONTEXT_SETTINGS, cls=OrderedGroup)
def main():
    logger.info(f'Run program with: {" ".join(sys.argv[1:])}')


try:
    from trogon import tui  # type: ignore

    main = tui()(main)  # type: ignore
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
main.add_command(show)
main.add_command(file)

if __name__ == "__main__":
    main()