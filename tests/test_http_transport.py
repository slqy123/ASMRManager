import asyncio
import json
import traceback
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from aiohttp import ClientConnectionError, ClientPayloadError, web
from aiohttp.test_utils import TestServer

from asmrmanager.spider.asmrapi import ASMRAPI, APIError
from asmrmanager.spider.transport import HTTPTransport


class HTTPTransportTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.status = 200
        self.body = None
        self.content_type = "application/json"
        self.disconnect = False
        self.truncate = False
        self.redirect = False
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self.handle)
        self.server = TestServer(app)
        await self.server.start_server()
        self.addAsyncCleanup(self.server.close)
        self.api = ASMRAPI(
            "test-user",
            "unused-password",
            None,
            2,
            max_rps=0,
            base_url=str(self.server.make_url("/api/")),
        )
        self.transport = self.api.transport
        await self.transport.__aenter__()
        self.addAsyncCleanup(self.transport.__aexit__, None, None, None)
        self.headers = {"Authorization": "Bearer test-secret"}
        self.api.auth.headers.update(self.headers)
        self.enterContext(
            patch(
                "asmrmanager.spider.transport.wait_random_exponential",
                return_value=lambda _: 0,
            )
        )

    async def handle(self, request):
        self.requests.append(
            {
                "method": request.method,
                "path": request.path,
                "query": dict(request.query),
                "authorization": request.headers.get("Authorization"),
                "body": await request.read(),
            }
        )
        if self.redirect:
            raise web.HTTPFound(location="/api/redirect?token=test-secret")
        if self.disconnect:
            request.transport.close()
            return web.Response()
        if self.truncate:
            response = web.StreamResponse(
                headers={
                    "Content-Length": "100",
                    "Content-Type": "application/json",
                }
            )
            await response.prepare(request)
            await response.write(b'{"ok":true}')
            request.transport.close()
            return response
        if self.body is None:
            return web.json_response({"ok": True}, status=self.status)
        return web.Response(
            body=self.body,
            status=self.status,
            content_type=self.content_type,
        )

    def assert_safe_error(self, error):
        rendered = "".join(traceback.format_exception(error))
        self.assertNotIn("test-secret", rendered)
        self.assertNotIn(str(self.server.make_url("/")), rendered)
        self.assertTrue(error.__suppress_context__)

    async def test_json_request_preserves_params_headers_and_normalizes_method(
        self,
    ):
        result = await self.transport.request(
            "get",
            "works",
            headers=self.headers,
            params={"page": 2},
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            self.requests,
            [
                {
                    "method": "GET",
                    "path": "/api/works",
                    "query": {"page": "2"},
                    "authorization": "Bearer test-secret",
                    "body": b"",
                }
            ],
        )

    async def test_successful_post_sends_json_once(self):
        result = await self.api.post(
            "playlist/create-playlist", {"name": "Local"}
        )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["body"], b'{"name": "Local"}')

    async def test_review_put_preserves_explicit_null_and_omits_unsubmitted_fields(
        self,
    ):
        self.body = b'{"message":"updated"}'
        result = await self.api.update_review(200123, {"progress": None})
        self.assertEqual(result, {"message": "updated"})
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(request["method"], "PUT")
        self.assertEqual(request["path"], "/api/review")
        self.assertEqual(request["query"], {"starOnly": "false"})
        self.assertEqual(request["authorization"], "Bearer test-secret")
        self.assertEqual(
            json.loads(request["body"]), {"work_id": 200123, "progress": None}
        )

    async def test_review_put_retries_connection_failure(self):
        with (
            patch.object(
                self.transport._session,
                "request",
                side_effect=ClientConnectionError("test-secret"),
            ) as request,
            self.assertRaisesRegex(
                APIError, "outcome may be unknown"
            ) as error,
        ):
            await self.api.update_review(200123, {"rating": None})
        self.assertEqual(request.call_count, 5)
        self.assert_safe_error(error.exception)

    async def test_binary_request_preserves_bytes(self):
        self.body = b"\x00\xff\x01"
        self.content_type = "application/octet-stream"
        self.assertEqual(await self.api.binary_get("cover/123.jpg"), self.body)

    async def test_http_errors_never_become_json_or_binary_success(self):
        for method in ("GET", "POST", "PUT"):
            for status in (401, 403, 404, 409, 422, 429, 500, 502):
                for binary in (False, True):
                    with self.subTest(
                        method=method, status=status, binary=binary
                    ):
                        self.status = status
                        self.body = b"<html>test-secret</html>"
                        self.content_type = "text/html"
                        before = len(self.requests)
                        with self.assertRaisesRegex(
                            APIError, f"HTTP {status}"
                        ) as error:
                            await self.transport.request(
                                method,
                                "review",
                                headers=self.headers,
                                params={"token": "test-secret"},
                                binary=binary,
                            )
                        self.assertEqual(len(self.requests) - before, 1)
                        self.assert_safe_error(error.exception)
                        if method == "POST":
                            self.assertIn("unknown", str(error.exception))
        self.status, self.body = 200, None
        self.assertEqual(await self.api.get("works"), {"ok": True})

    async def test_http_error_with_json_body_is_redacted(self):
        self.status = 400
        self.body = b'{"error":"test-secret"}'
        with self.assertRaisesRegex(APIError, "HTTP 400") as error:
            await self.api.post("review", {"password": "test-secret"})
        self.assert_safe_error(error.exception)

    async def test_invalid_json_and_content_type_fail_without_retries(self):
        for method in ("GET", "POST", "PUT"):
            for body, content_type in (
                (b"<html>test-secret</html>", "text/html"),
                (b'{"test-secret":', "application/json"),
                (b"\xff", "application/json"),
            ):
                with self.subTest(
                    method=method, content_type=content_type, body=body
                ):
                    self.body, self.content_type = body, content_type
                    before = len(self.requests)
                    with self.assertRaisesRegex(
                        APIError, "invalid JSON"
                    ) as error:
                        await self.transport.request(
                            method, "review", headers=self.headers
                        )
                    self.assertEqual(len(self.requests) - before, 1)
                    self.assert_safe_error(error.exception)
                    if method == "POST":
                        self.assertIn("unknown", str(error.exception))

    async def test_get_retries_transient_connection_failure_then_succeeds(
        self,
    ):
        response = self.transport._session.request(
            "GET", self.transport.base_url + "works"
        )
        with patch.object(
            self.transport._session,
            "request",
            side_effect=[ClientConnectionError("test-secret"), response],
        ) as request:
            result = await self.api.get("works")
        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(self.requests), 1)

    async def test_post_retries_connection_failure_then_succeeds(self):
        response = self.transport._session.request(
            "POST",
            self.transport.base_url + "playlist/create-playlist",
            json={"name": "Local"},
        )
        with patch.object(
            self.transport._session,
            "request",
            side_effect=[ClientConnectionError("test-secret"), response],
        ) as request:
            result = await self.api.post(
                "playlist/create-playlist", {"name": "Local"}
            )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["body"], b'{"name": "Local"}')

    async def test_get_retry_budget_is_five_transport_attempts(self):
        for exception in (
            ClientConnectionError,
            ClientPayloadError,
            asyncio.TimeoutError,
        ):
            with (
                self.subTest(exception=exception),
                patch.object(
                    self.transport._session,
                    "request",
                    side_effect=exception("test-secret"),
                ) as request,
                self.assertRaisesRegex(APIError, "interrupted") as error,
            ):
                await self.api.get("works?token=test-secret")
            self.assertEqual(request.call_count, 5)
            self.assert_safe_error(error.exception)
        self.assertEqual(self.requests, [])

    async def test_non_get_methods_have_five_transport_attempts(self):
        for method in ("POST", "PUT", "DELETE"):
            for exception in (
                ClientConnectionError,
                ClientPayloadError,
                asyncio.TimeoutError,
            ):
                with (
                    self.subTest(method=method, exception=exception),
                    patch.object(
                        self.transport._session,
                        "request",
                        side_effect=exception("test-secret"),
                    ) as request,
                    self.assertRaisesRegex(
                        APIError, "outcome may be unknown"
                    ) as error,
                ):
                    await self.transport.request(
                        method, "review", headers=self.headers
                    )
                self.assertEqual(request.call_count, 5)
                self.assert_safe_error(error.exception)
        self.assertEqual(self.requests, [])

    async def test_post_disconnect_after_server_receives_request_is_retried(
        self,
    ):
        self.disconnect = True
        with self.assertRaisesRegex(APIError, "outcome may be unknown"):
            await self.api.create_playlist("Created")
        self.assertEqual(len(self.requests), 5)
        self.assertTrue(
            all(
                b'"name": "Created"' in request["body"]
                for request in self.requests
            )
        )

    async def test_post_truncated_response_is_retried(self):
        self.truncate = True
        with self.assertRaisesRegex(APIError, "outcome may be unknown"):
            await self.api.create_playlist("Created")
        self.assertEqual(len(self.requests), 5)

    async def test_redirect_loop_fails_without_exposing_urls(self):
        self.redirect = True
        with self.assertRaisesRegex(
            APIError, "invalid HTTP response"
        ) as error:
            await self.api.get("redirect?token=test-secret")
        self.assert_safe_error(error.exception)

    async def test_retry_logs_do_not_include_route_params_or_headers(self):
        with (
            patch("asmrmanager.spider.transport.logger.warning") as warning,
            patch.object(
                self.transport._session,
                "request",
                side_effect=ClientConnectionError("test-secret"),
            ),
            self.assertRaises(APIError),
        ):
            await self.transport.request(
                "GET",
                "works?token=test-secret",
                headers=self.headers,
                params={"token": "test-secret"},
            )
        self.assertEqual(warning.call_count, 4)
        self.assertNotIn("test-secret", str(warning.call_args_list))

    async def test_cancellation_propagates_without_retry(self):
        with (
            patch.object(
                self.transport._session,
                "request",
                side_effect=asyncio.CancelledError,
            ) as request,
            self.assertRaises(asyncio.CancelledError),
        ):
            await self.api.post("playlist/create-playlist", {"name": "Local"})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(await self.api.get("works"), {"ok": True})

    async def test_login_http_failure_closes_transport(self):
        self.status = 401
        api = ASMRAPI(
            "fresh-test-user",
            "unused-password",
            None,
            1,
            max_rps=0,
            base_url=str(self.server.make_url("/api/")),
        )
        with self.assertRaisesRegex(APIError, "HTTP 401"):
            await api.__aenter__()
        self.assertIsNone(api.transport._session)
        self.assertEqual(self.requests[0]["path"], "/api/auth/me")

    async def test_application_error_in_successful_http_response_still_fails(
        self,
    ):
        self.body = b'{"error":"Application rejected test-secret"}'
        for method in (self.api.get, self.api.post, self.api.put):
            with self.assertRaisesRegex(
                APIError, "reported an error"
            ) as error:
                await method("review")
            self.assert_safe_error(error.exception)
        self.assertEqual(len(self.requests), 3)

    async def test_unopened_transport_still_reports_lifecycle_error(self):
        transport = HTTPTransport(
            str(self.server.make_url("/api/")), None, 1, 0
        )
        with self.assertRaisesRegex(RuntimeError, "not open"):
            await transport.request("GET", "works", headers={})
