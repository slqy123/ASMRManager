from json import dumps as json_dumps

import click

from asmrmanager.cli.core import (
    browse_param_options,
    commit_download_results,
    create_database,
    create_downloader_and_database,
    download_param_options,
    fm,
    interval_preprocess_cb,
    multi_rj_argument,
    time_interval_preprocess_cb,
)
from asmrmanager.common.browse_params import BrowseParams
from asmrmanager.common.download_params import DownloadParams
from asmrmanager.common.output import print_table, support_image
from asmrmanager.common.rj_parse import id2source_name
from asmrmanager.common.select import select_multiple
from asmrmanager.common.types import LocalSourceID, RemoteSourceID
from asmrmanager.logger import logger


@click.group(help="download ASMR")
def dl():
    pass


@click.command()
@multi_rj_argument("remote")
@download_param_options
def get(source_ids: list[RemoteSourceID], download_params: DownloadParams):
    """get ASMR by RJ/VJ/BJ ids"""
    if not source_ids:
        logger.error("You must give at least one source id!")
        return
    spider, db = create_downloader_and_database(download_params)
    (failed_ids,) = spider.run(spider.get(source_ids))
    commit_download_results(db, failed_ids)


@click.command()
@multi_rj_argument("remote")
def update(source_ids: list[RemoteSourceID]):
    """update metadata, including recover file and description file"""
    if not source_ids:
        logger.error("You must give at least one source id!")
        return
    spider, db = create_downloader_and_database(
        DownloadParams(False, False, True, True)
    )
    (failed_ids,) = spider.run(spider.update(source_ids))
    commit_download_results(db, failed_ids)


@click.command()
@multi_rj_argument("local")
def check(source_ids: list[LocalSourceID]):
    """check for existence of the file and its store field"""
    db = create_database()
    dl_queue = []
    for source_id in source_ids:
        source_name = id2source_name(source_id)

        asmr = db.check_exists(source_id)
        if asmr is None:
            logger.warning(
                f"Not found In Database: {source_name}, please manually download it"
            )
            continue

        src = fm.get_location(source_id)
        if src is None:
            logger.warning("%s not found, add to download", source_name)
            dl_queue.append(source_name)
            continue

        if src == "download" and asmr.stored:
            logger.info("move %s to storage (already stored)", source_name)
            fm.store(source_id)
            continue

        if src == "storage" and not asmr.stored:
            logger.info("update database for %s (already in storage)", source_name)
            asmr.stored = True
            continue

        logger.info(f"No need to update {source_name}")
    db.commit()
    logger.info("Update succesfully.")
    if dl_queue:
        logger.info(
            "Please check the item to download and get theme manually:"
        )
        logger.info(" ".join(dl_queue))


@click.command()
@click.argument(
    "keywords",
    type=str,
    nargs=-1,
)
@click.option(
    "--tags", "-t", type=str, multiple=True, help="tags to include[multiple]"
)
@click.option(
    "--no-tags",
    "-nt",
    type=str,
    multiple=True,
    help="tags to exclude[multiple]",
)
@click.option(
    "--vas",
    "-v",
    type=str,
    multiple=True,
    help="voice actor(cv) to include[multiple]",
)
@click.option(
    "--no-vas",
    "-nv",
    type=str,
    multiple=True,
    help="voice actor(cv) to exclude[multiple]",
)
@click.option(
    "--circle", "-c", type=str, default=None, help="circle(社团) to include"
)
@click.option(
    "--no-circle",
    "-nc",
    type=str,
    multiple=True,
    help="circle(社团) to exclude[multiple]",
)
@click.option(
    "--age",
    "-a",
    help="age limitation to include[multiple]",
    default=None,
    type=click.Choice(["general", "r15", "adult"]),
)
@click.option(
    "--no-age",
    "-na",
    help="age limitation to exclude[multiple]",
    multiple=True,
    type=click.Choice(["general", "r15", "adult"]),
)
@click.option(
    "--lang",
    "-l",
    help="language to include[multiple]",
    default=None,
    type=click.Choice(
        [
            "JPN",
            "ENG",
            "CHI_HANS",
            "CHI_HANT",
            "CHI",
            "KO_KR",
            "SPA",
            "ITA",
            "GER",
            "FRE",
        ]
    ),
)
@click.option(
    "--no-lang",
    "-nl",
    help="language to exclude[multiple]",
    multiple=True,
    type=click.Choice(
        [
            "JPN",
            "ENG",
            "CHI_HANS",
            "CHI_HANT",
            "CHI",
            "KO_KR",
            "SPA",
            "ITA",
            "GER",
            "FRE",
        ]
    ),
)
@click.option(
    "--rate", "-r", help="rating interval", callback=interval_preprocess_cb
)
@click.option(
    "--sell", "-s", help="selling interval", callback=interval_preprocess_cb
)
@click.option(
    "--price", "-pr", help="pirce interval", callback=interval_preprocess_cb
)
@click.option(
    "--duration",
    "-d",
    help="duration interval",
    callback=time_interval_preprocess_cb,
)
@click.option(
    "all_",
    "--all/--select",
    type=bool,
    is_flag=True,
    default=False,
    show_default=True,
    help="download all RJs",
)
@click.option(
    "--preview",
    type=bool,
    is_flag=True,
    default=False,
    help="preview search results without downloading",
)
@click.option(
    "--json",
    type=bool,
    is_flag=True,
    default=False,
    help="export search results to json without downloading",
)
@browse_param_options
@download_param_options
def search(
    keywords: tuple[str],
    tags: tuple[str],
    vas: tuple[str],
    circle: str | None,
    age: str | None,
    lang: str | None,
    no_tags: tuple[str],
    no_vas: tuple[str],
    no_circle: tuple[str],
    no_age: tuple[str],
    no_lang: tuple[str],
    rate: tuple[float | None, float | None],
    sell: tuple[int | None, int | None],
    price: tuple[int | None, int | None],
    duration: tuple[str | None, str | None],
    browse_params: BrowseParams,
    download_params: DownloadParams,
    all_: bool,
    preview: bool,
    json: bool,
):
    """
    search and download ASMR

    The arguments passed to this command will be used as keywords to search.
    if you pass a keyword starts with `!`, this will
    exclude works containing such keyword, eg: `!中文版`

    the [multiple] option means you can add multiple same options such as:

        --tags tag1 --tags tag2 --no-tags tag3

    for options like --rate, --sell, --price, --duration you should give an interval like:

        --rate 3.9:4.7 --sell 1000: --price :200 --duration 10:60

    the interval a:b means a <= x < b, if a or b is not given
    i.e. a: or :b, it means no lower or upper limit

    for --duration, expressions like `1.5h(1.5 hours)`, `10m(10 minutes)` are allowed,
    or by default, the unit is `minute`.
    """
    if (preview or json) and browse_params.page == 0:
        logger.error(
            "--preview and --json can not be used together with --page=0"
        )
        return

    spider, db = create_downloader_and_database(
        download_params=download_params
    )
    text = " ".join(
        "-" + k[1:] if (k := t.strip()).startswith("!") else k
        for t in keywords
    )

    async def process_pages() -> list[RemoteSourceID]:
        failed_ids: list[RemoteSourceID] = []
        total_pages_to_download = None
        download_all_pages = browse_params.page == 0
        if download_all_pages:
            browse_params.page = 1

        while True:
            search_result = await spider.search(
                text,
                tags=tags,
                vas=vas,
                circle=circle,
                age=age,
                lang=lang,
                no_tags=no_tags,
                no_vas=no_vas,
                no_circle=no_circle,
                no_age=no_age,
                no_lang=no_lang,
                rate=rate,
                sell=sell,
                price=price,
                duration=duration,
                params=browse_params,
            )
            works = search_result["works"]
            indexes: list[int] | range
            if all_:
                indexes = range(len(works))
            else:
                indexes = select_multiple(
                    [f"{work['source_id']} | {work['title']}" for work in works]
                )
                if not indexes:
                    logger.warning("Nothing was selected.")

            if indexes:
                selected_works = [works[i] for i in indexes]
                if json:
                    click.echo(json_dumps(selected_works, ensure_ascii=False))
                elif preview:
                    cover_paths = (
                        await spider.gather(
                            *(spider.get_cover_path(work) for work in selected_works)
                        )
                        if support_image()
                        else None
                    )
                    print_table(
                        titles=["id", "title", "circle_name"],
                        rows=[
                            (work["id"], work["title"], work["name"])
                            for work in selected_works
                        ],
                        image_paths=cover_paths,
                    )
                else:
                    failed_ids.extend(
                        await spider.get([work["id"] for work in selected_works])
                    )

            if not download_all_pages:
                break
            if total_pages_to_download is None:
                total_pages_to_download = (
                    int(search_result["pagination"]["totalCount"])
                    // int(search_result["pagination"]["pageSize"])
                    + 1
                )
                logger.info(f"Total pages to download: {total_pages_to_download}")
            assert search_result["pagination"]["currentPage"] == browse_params.page
            if browse_params.page >= total_pages_to_download:
                logger.info("All pages downloaded.")
                break
            logger.info(
                f"Downloading progress: {browse_params.page}/{total_pages_to_download}"
            )
            browse_params.page += 1
        return failed_ids

    (failed_ids,) = spider.run(process_pages())
    commit_download_results(db, failed_ids)


@click.command()
@download_param_options
def rec(download_params: DownloadParams):
    """download recommendations of the current account"""
    spider, db = create_downloader_and_database(download_params)
    (failed_ids,) = spider.run(spider.get_recommendations())
    commit_download_results(db, failed_ids)


@click.command()
@download_param_options
def popular(download_params: DownloadParams):
    """download current popular ASMRs"""
    spider, db = create_downloader_and_database(download_params)
    (failed_ids,) = spider.run(spider.get_popular())
    commit_download_results(db, failed_ids)


dl.add_command(get)
dl.add_command(check)
dl.add_command(search)
dl.add_command(update)
dl.add_command(rec)
dl.add_command(popular)
