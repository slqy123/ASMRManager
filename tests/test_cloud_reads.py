from copy import deepcopy
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from asmrmanager.common.types import PROGRESS_VALUES
from asmrmanager.spider.asmrapi import ASMRAPI, APIError


def review_page(page=1, page_size=2, total=3):
    return {
        "works": [
            {
                "id": 200123 + index,
                "source_id": f"RJ{123 + index:06d}",
                "user_name": "test-user",
                "userRating": None,
                "review_text": None,
                "progress": "marked",
            }
            for index in range(
                min(page_size, max(0, total - (page - 1) * page_size))
            )
        ],
        "pagination": {
            "currentPage": page,
            "pageSize": page_size,
            "totalCount": total,
        },
    }


class CloudReadContractTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = ASMRAPI("test-user", "unused-password", None, 1)
        self.api.get = AsyncMock()

    async def test_identity_is_read_from_authenticated_nested_user(self):
        user = {
            "loggedIn": True,
            "name": "test-user",
            "group": "user",
            "recommenderUuid": "test-account-id",
            "email": None,
        }
        self.api.get.return_value = {"user": user, "auth": True, "reg": True}
        self.assertEqual(await self.api.get_current_user(), user)
        self.api.get.assert_awaited_once_with("auth/me")

    async def test_invalid_identity_never_returns_an_anonymous_or_cached_account(
        self,
    ):
        for response in (
            None,
            [],
            {},
            {"user": None},
            {
                "user": {
                    "loggedIn": False,
                    "name": "TEST_PRIVATE_NAME",
                    "recommenderUuid": "test-id",
                }
            },
            {
                "user": {
                    "loggedIn": 1,
                    "name": "test-user",
                    "recommenderUuid": "test-id",
                }
            },
            {
                "user": {
                    "loggedIn": True,
                    "name": "",
                    "recommenderUuid": "test-id",
                }
            },
            {
                "user": {
                    "loggedIn": True,
                    "name": "test-user",
                    "recommenderUuid": "",
                }
            },
        ):
            with self.subTest(response=response):
                self.api.get.return_value = response
                with self.assertRaisesRegex(
                    APIError, "Invalid authenticated user"
                ) as error:
                    await self.api.get_current_user()
                self.assertNotIn("TEST_PRIVATE", str(error.exception))

    async def test_review_request_includes_page_size_and_omits_unfiltered_filter(
        self,
    ):
        response = review_page()
        self.api.get.return_value = response
        self.assertEqual(await self.api.get_reviews(page_size=2), response)
        self.api.get.assert_awaited_once_with(
            "review",
            params={"order": "id", "sort": "asc", "page": 1, "pageSize": 2},
        )

    async def test_each_known_progress_filter_is_forwarded(self):
        self.api.get.return_value = review_page(page_size=20, total=1)
        for progress in PROGRESS_VALUES:
            with self.subTest(progress=progress):
                await self.api.get_reviews(progress=progress)
                self.api.get.assert_awaited_with(
                    "review",
                    params={
                        "order": "id",
                        "sort": "asc",
                        "page": 1,
                        "pageSize": 20,
                        "filter": progress,
                    },
                )

    async def test_last_and_beyond_last_review_pages_are_valid(self):
        for page, count in ((2, 1), (3, 0)):
            with self.subTest(page=page):
                self.api.get.return_value = review_page(page=page)
                response = await self.api.get_reviews(page=page, page_size=2)
                self.assertEqual(len(response["works"]), count)

    async def test_empty_account_requires_explicit_zero_total(self):
        self.api.get.return_value = review_page(total=0)
        self.assertEqual(
            (await self.api.get_reviews(page_size=2))["works"], []
        )
        self.api.get.return_value = {
            "works": [],
            "pagination": {"currentPage": 1, "pageSize": 2, "totalCount": 3},
        }
        with self.assertRaisesRegex(APIError, "Incomplete"):
            await self.api.get_reviews(page_size=2)

    async def test_missing_malformed_and_mismatched_pagination_fail_closed(
        self,
    ):
        for response in (
            None,
            [],
            {},
            {"works": []},
            {"works": None},
            {"works": [], "pagination": None},
        ):
            with self.subTest(response=response):
                self.api.get.return_value = response
                with self.assertRaises(APIError):
                    await self.api.get_reviews(page_size=2)
        for key, value in (
            ("currentPage", True),
            ("currentPage", 2),
            ("pageSize", True),
            ("pageSize", 20),
            ("totalCount", True),
            ("totalCount", -1),
            ("totalCount", "3"),
        ):
            with self.subTest(key=key, value=value):
                response = review_page()
                response["pagination"][key] = value
                self.api.get.return_value = response
                with self.assertRaises(APIError):
                    await self.api.get_reviews(page_size=2)

    async def test_invalid_items_and_incomplete_pages_are_not_empty_success(
        self,
    ):
        for items in (
            [],
            [None, {}],
            ["TEST_PRIVATE_VALUE", {}],
            [{}, {}, {}],
        ):
            with self.subTest(items=items):
                response = deepcopy(review_page())
                response["works"] = items
                self.api.get.return_value = response
                with self.assertRaises(APIError) as error:
                    await self.api.get_reviews(page_size=2)
                self.assertNotIn("TEST_PRIVATE", str(error.exception))

    async def test_invalid_parameters_do_not_issue_requests(self):
        for params in (
            {"page": 0},
            {"page": True},
            {"page": "1"},
            {"page_size": 0},
            {"page_size": True},
            {"page_size": "2"},
            {"progress": "all"},
            {"progress": "unknown"},
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                await self.api.get_reviews(**params)
        self.api.get.assert_not_awaited()

    async def test_network_failure_is_not_interpreted_as_no_reviews(self):
        self.api.get.side_effect = APIError("GET request failed (HTTP 401).")
        with self.assertRaisesRegex(APIError, "HTTP 401"):
            await self.api.get_reviews()
