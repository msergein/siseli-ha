"""Tests for the HTTP bootstrap source selection."""

import unittest
from unittest import mock

from src.siseli_local_bridge import httpstub


def _request(method: str, path: str) -> dict:
    return {"method": method, "path": path, "headers": {"authorization": "x"}, "body": b""}


class TestHttpBootstrapMode(unittest.TestCase):
    def test_local_mode_never_calls_the_cloud(self):
        with mock.patch.object(httpstub, "HTTP_BOOTSTRAP_MODE", "local"), \
                mock.patch.object(httpstub, "_proxy_to_cloud") as proxy:
            out = httpstub._handle_request(_request("POST", "/dtu/checkin"))
        proxy.assert_not_called()
        self.assertTrue(out.startswith(b"HTTP/1.1 200"))

    def test_cloud_mode_returns_the_cloud_response(self):
        with mock.patch.object(httpstub, "HTTP_BOOTSTRAP_MODE", "cloud"), \
                mock.patch.object(httpstub, "_proxy_to_cloud", return_value=b"CLOUD"):
            out = httpstub._handle_request(_request("POST", "/dtu/checkin"))
        self.assertEqual(out, b"CLOUD")

    def test_cloud_mode_has_no_local_fallback(self):
        with mock.patch.object(httpstub, "HTTP_BOOTSTRAP_MODE", "cloud"), \
                mock.patch.object(httpstub, "_proxy_to_cloud", return_value=None):
            out = httpstub._handle_request(_request("POST", "/dtu/checkin"))
        self.assertTrue(out.startswith(b"HTTP/1.1 502"))

    def test_cloud_then_local_falls_back_to_the_local_handler(self):
        local = mock.Mock(return_value=b"LOCAL")
        with mock.patch.object(httpstub, "HTTP_BOOTSTRAP_MODE", "cloud_then_local"), \
                mock.patch.object(httpstub, "_proxy_to_cloud", return_value=None), \
                mock.patch.dict(httpstub._ROUTES, {("POST", "/dtu/checkin"): local}):
            out = httpstub._handle_request(_request("POST", "/dtu/checkin"))
        self.assertEqual(out, b"LOCAL")
        local.assert_called_once()

    def test_the_broker_endpoint_always_stays_local(self):
        with mock.patch.object(httpstub, "HTTP_BOOTSTRAP_MODE", "cloud"), \
                mock.patch.object(httpstub, "_proxy_to_cloud") as proxy:
            out = httpstub._handle_request(_request("GET", "/dtu/servers/mqtt"))
        proxy.assert_not_called()
        self.assertTrue(out.startswith(b"HTTP/1.1 200"))


if __name__ == "__main__":
    unittest.main()
