import click
from asmrcli.dl import dl
from asmrcli.review import review
from asmrcli.query import query
from asmrcli.info import info
from asmrcli.hold import hold
# TODO 可能有的项目更新了汉化会被过滤不会下载，考虑对比has_subtitle
# TODO 添加一个专门的模块用来管理文件的移动，包括下载路径，储存路径，浏览路径，使用硬链接还是符号链接

@click.group()
def main():
    pass


if __name__ == '__main__':
    main.add_command(dl)
    main.add_command(review)
    main.add_command(query)
    main.add_command(info)
    main.add_command(hold)

    main()
