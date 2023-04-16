import os

os.chdir(os.path.split(os.path.abspath(__file__))[0])
import sys

import click
from asmrcli.dl import dl
from asmrcli.review import review
from asmrcli.query import query
from asmrcli.info import info
from asmrcli.hold import hold
from asmrcli.view import view

from logger import logger


# TODO 可能有的项目更新了汉化会被过滤不会下载，考虑对比has_subtitle

@click.group()
def main():
    logger.info(f'Run program with: {" ".join(sys.argv[1:])}')


if __name__ == '__main__':
    main.add_command(dl)
    main.add_command(review)
    main.add_command(query)
    main.add_command(info)
    main.add_command(hold)
    main.add_command(view)

    main()
