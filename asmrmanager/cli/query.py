import click

from asmrmanager.cli.core import create_database


@click.command()
@click.argument("keyword", type=str)
@click.option("--limit", "-l", type=int, default=100, show_default=True)
@click.option(
    "--raw",
    "-r",
    is_flag=True,
    default=False,
    show_default=True,
    help="output raw json",
)
def query(keyword: str, limit: int, raw: bool):
    """
    simple keyword based query,
    it will match the input with name, circle_name and tag field.
    if you want to use more complex queries, please use `asmr sql` instead.

    set limit to 0 if you want to get all results.
    """
    from asmrmanager.common.output import print_table
    from asmrmanager.database.database import ASMR, ASMRs2Tags, Tag

    db = create_database()
    res_query = (
        db.query(
            ASMR.id,
            ASMR.title,
            ASMR.circle_name,
            ASMR.nsfw,
            ASMR.has_subtitle,
            ASMR.count,
            ASMR.star,
        )
        .join(ASMRs2Tags, ASMRs2Tags.asmr_id == ASMR.id)
        .join(Tag, Tag.id == ASMRs2Tags.tag_id)
        .filter(
            ASMR.circle_name.contains(keyword)
            | ASMR.title.contains(keyword)
            | Tag.name.contains(keyword)
        )
        .group_by(ASMR.id)
    )

    assert limit >= 0
    if limit == 0:
        res = res_query.all()
    else:
        res = res_query.limit(limit).all()

    titles = [
        "id",
        "title",
        "circle_name",
        "nsfw",
        "subtitle",
        "count",
        "star",
    ]

    print_table(titles=titles, rows=res, raw=raw)
