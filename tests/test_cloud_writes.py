import uuid
from itertools import combinations
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from asmrmanager.common.types import PRIVACY, PROGRESS_VALUES
from asmrmanager.spider.asmrapi import ASMRAPI, APIError


class CloudWriteContractTest(IsolatedAsyncioTestCase):
    def setUp(self):
        self.api = ASMRAPI("test-user", "unused-password", None, 1)
        self.api.put = AsyncMock(return_value={"message": "updated"})
        self.api.post = AsyncMock()

    async def test_every_review_field_subset_is_sent_without_other_fields(
        self,
    ):
        values = {
            "rating": 2,
            "review_text": "Synthetic test comment",
            "progress": "marked",
        }
        for length in (1, 2, 3):
            for keys in combinations(values, length):
                with self.subTest(keys=keys):
                    changes = {key: values[key] for key in keys}
                    original = dict(changes)
                    self.assertEqual(
                        await self.api.update_review(200123, changes),
                        {"message": "updated"},
                    )
                    self.api.put.assert_awaited_with(
                        "review",
                        data={"work_id": 200123, **changes},
                        params={"starOnly": "false"},
                    )
                    self.assertEqual(changes, original)

    async def test_clears_preserve_null_empty_string_and_zero(self):
        for changes in (
            {"rating": None},
            {"rating": 0},
            {"review_text": ""},
            {"progress": None},
        ):
            with self.subTest(changes=changes):
                await self.api.update_review(200123, changes)
                self.api.put.assert_awaited_with(
                    "review",
                    data={"work_id": 200123, **changes},
                    params={"starOnly": "false"},
                )

    async def test_each_supported_progress_is_sent_unchanged(self):
        for progress in PROGRESS_VALUES:
            with self.subTest(progress=progress):
                await self.api.update_review(200123, {"progress": progress})
                self.assertEqual(
                    self.api.put.call_args.kwargs["data"],
                    {"work_id": 200123, "progress": progress},
                )

    async def test_invalid_review_values_never_issue_requests(self):
        for changes in (
            None,
            [],
            {},
            {"notes": "TEST_PRIVATE_VALUE"},
            {"work_id": 123},
            {"rating": True},
            {"rating": -1},
            {"rating": 6},
            {"rating": "2"},
            {"review_text": None},
            {"review_text": 1},
            {"progress": ""},
            {"progress": "all"},
        ):
            with (
                self.subTest(changes=changes),
                self.assertRaises(ValueError) as error,
            ):
                await self.api.update_review(200123, changes)
            self.assertNotIn("TEST_PRIVATE", str(error.exception))
        for work_id in (None, True, 0, -1, "200123"):
            with self.subTest(work_id=work_id), self.assertRaises(ValueError):
                await self.api.update_review(work_id, {"rating": 2})
        self.api.put.assert_not_awaited()

    async def test_update_requires_a_structured_acknowledgement(self):
        for response in (None, [], {}, {"message": None}, {"message": 1}):
            with self.subTest(response=response):
                self.api.put.return_value = response
                with self.assertRaisesRegex(
                    APIError, "outcome may be unknown"
                ):
                    await self.api.update_review(200123, {"rating": 2})

    async def test_update_failure_is_not_replayed_or_turned_into_success(self):
        self.api.put.side_effect = APIError("PUT request failed (HTTP 403).")
        with self.assertRaisesRegex(APIError, "HTTP 403"):
            await self.api.update_review(200123, {"rating": 2})
        self.api.put.assert_awaited_once()

    async def test_creation_consumes_the_returned_id_and_initial_source_strings(
        self,
    ):
        response = {
            "id": str(uuid.uuid4()),
            "user_name": "test-user",
            "privacy": 0,
            "works_count": 1,
        }
        self.api.post.return_value = response
        self.api.get = AsyncMock()
        self.assertEqual(
            await self.api.create_playlist(
                "Synthetic list", "Description", works=["RJ000123"]
            ),
            response,
        )
        self.api.post.assert_awaited_once_with(
            "playlist/create-playlist",
            data={
                "name": "Synthetic list",
                "description": "Description",
                "privacy": 0,
                "locale": "zh-CN",
                "works": ["RJ000123"],
            },
        )
        self.api.get.assert_not_awaited()

    async def test_creation_defaults_remain_private_and_empty(self):
        self.api.post.return_value = {"id": str(uuid.uuid4())}
        await self.api.create_playlist("Synthetic list")
        self.assertEqual(
            self.api.post.call_args.kwargs["data"],
            {
                "name": "Synthetic list",
                "description": "",
                "privacy": PRIVACY.PRIVATE.value,
                "locale": "zh-CN",
                "works": [],
            },
        )

    async def test_invalid_creation_id_reports_unknown_outcome_without_lookup_or_retry(
        self,
    ):
        self.api.get = AsyncMock()
        for response in (
            None,
            [],
            {},
            {"id": None},
            {"id": 123},
            {"id": "TEST_PRIVATE_VALUE"},
        ):
            with self.subTest(response=response):
                self.api.post.reset_mock()
                self.api.post.return_value = response
                with self.assertRaisesRegex(
                    APIError, "Creation may have succeeded"
                ) as error:
                    await self.api.create_playlist("Synthetic list")
                self.api.post.assert_awaited_once()
                self.assertNotIn("TEST_PRIVATE", str(error.exception))
                self.assertTrue(error.exception.__suppress_context__)
        self.api.get.assert_not_awaited()

    async def test_playlist_member_mutations_use_cloud_ids(self):
        playlist_id = uuid.uuid4()
        self.api.post.return_value = {"id": str(playlist_id), "rowCount": 1}
        await self.api.add_works_to_playlist([200123], playlist_id)
        self.api.post.assert_awaited_once_with(
            "playlist/add-works-to-playlist",
            data={"id": str(playlist_id), "works": [200123]},
        )
        self.api.post.reset_mock()
        await self.api.remove_works_from_playlist([200123], playlist_id)
        self.api.post.assert_awaited_once_with(
            "playlist/remove-works-from-playlist",
            data={"id": str(playlist_id), "works": [200123]},
        )
        self.api.post.reset_mock()
        await self.api.delete_playlist(playlist_id)
        self.api.post.assert_awaited_once_with(
            "playlist/delete-playlist", data={"id": str(playlist_id)}
        )
