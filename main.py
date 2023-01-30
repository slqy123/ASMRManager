import click
from asmrcli.dl import dl
from asmrcli.review import review
from asmrcli.query import query


@click.group()
def main():
    pass


if __name__ == '__main__':
    main.add_command(dl)
    main.add_command(review)
    main.add_command(query)

    main()
