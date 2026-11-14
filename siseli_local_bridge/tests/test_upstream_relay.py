"""Unit tests for the hybrid UPSTREAM_RELAY path.

No real cloud and no real dongle: these pin the frame routing.
"""

import base64
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from src.siseli_local_bridge import fakecloud


def _publish(topic: str, payload: dict, qos: int = 0) -> bytes:
    topic_bytes = topic.encode()
    body = len(topic_bytes).to_bytes(2, "big") + topic_bytes
    if qos:
        body += b"\x00\x01"
    body += b"\x00" + json.dumps(payload).encode()
    return body


def _reply(token: str, command: str) -> bytes:
    raw = b"(230.0 50.0 00100 00050 001 020 06200 001.0 00001\r"
    return _publish(
        "dtu/1/pub/service/dev_rpc_reply",
        {"c": 5, "t": token, "s": "s", "i": 504, "e": 0,
         "b": {"sa": "", "co": base64.b64encode(raw).decode()}},
    )


class TestUpstreamRelayRouting(unittest.TestCase):
    def test_connect_opens_upstream_and_does_not_send_a_local_connack(self):
        conn = SimpleNamespace(
            dtu_id=None, closed=False, live_token_command={}, local_tokens={},
            reply=mock.Mock(),
        )
        with mock.patch.object(fakecloud, "UPSTREAM_RELAY", True), \
                mock.patch.object(fakecloud, "_log_connect", return_value="1"), \
                mock.patch.object(fakecloud, "_upstream_open", return_value=True) as opened:
            out = fakecloud._handle_frame(0x10, b"connect-body", conn)
        self.assertEqual(out, b"")
        opened.assert_called_once()

    def test_a_local_fast_reply_is_handled_locally(self):
        conn = SimpleNamespace(
            dtu_id="1", closed=False, upstream_socket=object(),
            local_tokens={"tok": 1.0},
            live_token_command={"tok": ("HOP", 1.0, 1)},
            reply=mock.Mock(),
        )
        with mock.patch.object(fakecloud, "UPSTREAM_RELAY", True), \
                mock.patch.object(fakecloud, "_handle_publish", return_value=b"LOCAL-ACK") as local, \
                mock.patch.object(fakecloud, "_upstream_send") as upstream:
            out = fakecloud._handle_frame(0x30, _reply("tok", "HOP"), conn)
        self.assertEqual(out, b"LOCAL-ACK")
        local.assert_called_once()
        upstream.assert_not_called()

    def test_a_cloud_reply_is_forwarded_and_parsed_without_a_local_ack(self):
        conn = SimpleNamespace(
            dtu_id="1", closed=False, upstream_socket=object(),
            local_tokens={}, live_token_command={},
            reply=mock.Mock(),
        )
        with mock.patch.object(fakecloud, "UPSTREAM_RELAY", True), \
                mock.patch.object(fakecloud, "_handle_publish") as local, \
                mock.patch.object(fakecloud, "_upstream_send", return_value=True) as upstream, \
                mock.patch.object(fakecloud, "_parse_forwarded_publish") as parsed:
            out = fakecloud._handle_frame(0x30, _reply("cloud", "HOP"), conn)
        self.assertEqual(out, b"")
        local.assert_not_called()
        upstream.assert_called_once()
        parsed.assert_called_once()

    def test_a_settings_reply_without_a_command_is_still_local(self):
        conn = SimpleNamespace(
            dtu_id="1", closed=False, upstream_socket=object(),
            local_tokens={"tok": 1.0}, live_token_command={},
            reply=mock.Mock(),
        )
        with mock.patch.object(fakecloud, "UPSTREAM_RELAY", True), \
                mock.patch.object(fakecloud, "_handle_publish", return_value=b"LOCAL-ACK"), \
                mock.patch.object(fakecloud, "_upstream_send") as upstream:
            out = fakecloud._handle_frame(0x30, _reply("tok", "PGFC006"), conn)
        self.assertEqual(out, b"LOCAL-ACK")
        upstream.assert_not_called()


class TestUpstreamJournal(unittest.TestCase):
    def test_cloud_request_is_tagged_with_direction_and_topic(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "monitor.jsonl")
            body = _publish(
                "dtu/1/sub/service/dev_rpc",
                {"c": 5, "t": "cloud-token", "s": "s", "i": 501, "b": {}},
            )
            with mock.patch.object(fakecloud, "LIVE_MONITOR", True), \
                    mock.patch.object(fakecloud, "_MONITOR_PATH", path):
                fakecloud._monitor_cloud(0x30, body)
            record = json.loads(open(path, encoding="utf-8").readline())
        self.assertEqual(record["source"], "cloud")
        self.assertEqual(record["direction"], "cloud->dongle")
        self.assertEqual(record["topic"], "dtu/1/sub/service/dev_rpc")
        self.assertEqual(record["i"], 501)
        self.assertEqual(record["token"], "cloud-token")

    def test_dongle_forward_is_tagged_in_the_other_direction(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "monitor.jsonl")
            body = _publish(
                "dtu/1/pub/service/dev_rpc_reply",
                {"c": 5, "t": "cloud-token", "s": "s", "i": 502, "e": 0,
                 "b": {"sa": "", "ct": []}},
            )
            with mock.patch.object(fakecloud, "LIVE_MONITOR", True), \
                    mock.patch.object(fakecloud, "_MONITOR_PATH", path):
                fakecloud._monitor_forwarded(0x30, body)
            record = json.loads(open(path, encoding="utf-8").readline())
        self.assertEqual(record["source"], "dongle")
        self.assertEqual(record["direction"], "dongle->cloud")
        self.assertEqual(record["i"], 502)


class TestUpstreamReader(unittest.TestCase):
    def test_cloud_bytes_are_forwarded_to_the_dongle_unchanged(self):
        import socket
        left, right = socket.socketpair()
        self.addCleanup(left.close)
        self.addCleanup(right.close)

        class Conn:
            closed = False
            local_ip = "127.0.0.1"
            local_port = 1883
            peer_ip = "127.0.0.2"
            peer_port = 12345

            def __init__(self):
                self.seen = []

            def reply(self, data):
                self.seen.append(data)

            def close(self, reason=""):
                self.closed = True

        conn = Conn()
        thread = __import__("threading").Thread(
            target=fakecloud._upstream_reader, args=(conn, left), daemon=True
        )
        thread.start()
        right.sendall(b"CONNACK")
        for _ in range(50):
            if conn.seen:
                break
            __import__("time").sleep(0.01)
        right.close()
        thread.join(2)
        self.assertEqual(conn.seen, [b"CONNACK"])
        self.assertTrue(conn.closed)


if __name__ == "__main__":
    unittest.main()
