from typing import Literal


class BrowseParams:
    def __init__(
        self,
        page: int,
        page_size: int,
        subtitle: bool,
        order: Literal[
            "create_date",
            "rating",
            "release",
            "dl_count",
            "price",
            "rate_average_2dp",
            "review_count",
            "id",
            "nsfw",
            "random",
        ],
        asc: bool,
    ):
        self.page = page
        self.page_size = page_size
        self.subtitle = subtitle
        self.order = order
        self.sort = "asc" if asc else "desc"

    @property
    def params(self):
        return {
            "page": str(self.page),
            "pageSize": str(self.page_size),
            "subtitle": str(int(self.subtitle)),
            "order": self.order,
            "sort": self.sort,
        }

    def __str__(self):
        return str(self.params)
