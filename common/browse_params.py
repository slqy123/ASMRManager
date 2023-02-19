from typing import Literal


class BrowseParams:
    def __init__(self, page: int, subtitle: bool,
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
                     "random"
                 ], sort: Literal['asc', 'desc']):
        self.page = page
        self.subtitle = subtitle
        self.order = order
        self.sort = sort

    @property
    def params(self):
        return {
            'page': str(self.page),
            'subtitle': str(int(self.subtitle)),
            'order': self.order,
            'sort': self.sort
        }
