import uuid
from copy import deepcopy

from asmrmanager.spider.asmrapi import ASMRAPI, APIError


class FakeCloud(ASMRAPI):
    def __init__(self, works=()):
        super().__init__(
            "test-user",
            "unused-password",
            None,
            1,
            base_url="https://test.example/api/",
        )
        self.works = {work["id"]: deepcopy(work) for work in works}
        self.reviews = {}
        self.playlists = {}
        self.members = {}
        self.events = []
        self.failures = {}
        self.hook = None
        self.user = "test-user"

    async def __aenter__(self):
        self.events.append(("open",))
        return self

    async def __aexit__(self, *_):
        self.events.append(("close",))

    def event(self, method, route, payload):
        self.events.append((method, route, deepcopy(payload)))
        if self.hook:
            self.hook(method, route, payload)
        if (method, route) in self.failures:
            raise self.failures[method, route]

    def playlist(self, name="Cloud", members=(), **metadata):
        identifier = str(metadata.pop("id", uuid.uuid4()))
        self.playlists[identifier] = {
            "id": identifier,
            "user_name": self.user,
            "name": name,
            "description": "",
            "privacy": 0,
            "works_count": len(members),
            **metadata,
        }
        self.members[identifier] = list(members)
        return uuid.UUID(identifier)

    def page(self, rows, params, page_key, key):
        page, size = params["page"], params["pageSize"]
        return {
            key: deepcopy(rows[(page - 1) * size : page * size]),
            "pagination": {
                page_key: page,
                "pageSize": size,
                "totalCount": len(rows),
            },
        }

    async def get(self, route, params=None):
        self.event("GET", route, params)
        if route == "auth/me":
            return {
                "user": {
                    "name": self.user,
                    "loggedIn": True,
                    "recommenderUuid": "synthetic-user-id",
                }
            }
        if route.startswith("work/"):
            identifier = int(route.split("/")[1])
            info = deepcopy(self.works[identifier])
            info.update(
                {
                    "user_name": None,
                    "userRating": None,
                    "review_text": None,
                    "progress": None,
                    "updated_at": None,
                }
            )
            info.update(self.reviews.get(identifier, {}))
            return info
        if route == "review":
            rows = [
                {**self.works[identifier], **review}
                for identifier, review in sorted(self.reviews.items())
            ]
            return self.page(rows, params, "currentPage", "works")
        if route == "playlist/get-playlists":
            return self.page(
                sorted(
                    [
                        {**row, "works_count": len(self.members[row["id"]])}
                        for row in self.playlists.values()
                    ],
                    key=lambda row: row["id"],
                ),
                params,
                "page",
                "playlists",
            )
        identifier = params["id"]
        if identifier not in self.playlists:
            raise APIError("GET request failed (HTTP 404).")
        if route == "playlist/get-playlist-metadata":
            return deepcopy(
                {
                    **self.playlists[identifier],
                    "works_count": len(self.members[identifier]),
                }
            )
        if route == "playlist/get-playlist-works":
            rows = [
                self.works[item] for item in sorted(self.members[identifier])
            ]
            return self.page(rows, params, "page", "works")
        raise AssertionError("Unknown fake endpoint")

    async def put(self, route, data=None, params=None):
        self.event("PUT", route, {"data": data, "params": params})
        identifier = data["work_id"]
        review = self.reviews.setdefault(
            identifier,
            {
                "user_name": self.user,
                "userRating": None,
                "review_text": None,
                "progress": None,
                "updated_at": "2024-01-02",
            },
        )
        for key, target in (
            ("rating", "userRating"),
            ("review_text", "review_text"),
            ("progress", "progress"),
        ):
            if key in data:
                review[target] = data[key]
        return {"message": "updated"}

    async def post(self, route, data=None):
        self.event("POST", route, data)
        if route == "playlist/create-playlist":
            lookup = {
                work["source_id"]: identifier
                for identifier, work in self.works.items()
            }
            identifier = self.playlist(
                data["name"],
                [lookup[source] for source in data["works"]],
                description=data["description"],
                privacy=data["privacy"],
            )
            return deepcopy(self.playlists[str(identifier)])
        identifier = data["id"]
        if route == "playlist/delete-playlist":
            del self.playlists[identifier]
            del self.members[identifier]
            return {"id": identifier}
        if route == "playlist/add-works-to-playlist":
            self.members[identifier] = sorted(
                set(self.members[identifier]) | set(data["works"])
            )
            return {"id": identifier, "rowCount": len(data["works"])}
        raise AssertionError("Unknown fake endpoint")
