"""Unit tests for the diagnostic LIVE_PROBE mode in fakecloud.py.

The probe is a measurement tool: it sends one read at a time, records whether the
dongle answered it, and writes the per-command outcomes for the user to compare
with the inverter's screen. These tests pin the classification and the state
machine without a real dongle.
"""

import base64
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from src.siseli_local_bridge import fakecloud
from tests import captures


def _co(raw: bytes) -> dict:
    return {"i": 504, "e": 0, "b": {"co": base64.b64encode(raw).decode("ascii")}}


class TestProbeCommands(unittest.TestCase):
    def test_all_expands_to_the_live_poll_set_once(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_COMMANDS", "all"):
            commands = fakecloud._probe_commands()
        for expected in ("HGRID", "HOP", "HPV", "HBAT", "QMOD", "QFLAG", "QPIWS"):
            self.assertIn(expected, commands)
        self.assertEqual(len(commands), len(set(commands)))

    def test_explicit_list_is_trimmed_and_deduplicated(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_COMMANDS", " HOP, HBAT ,HOP, "):
            self.assertEqual(fakecloud._probe_commands(), ["HOP", "HBAT"])

    def test_empty_keeps_it_off(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_COMMANDS", ""):
            self.assertFalse(fakecloud._probe_enabled())


class TestProbeClassify(unittest.TestCase):
    def test_ack_for_an_h_block(self):
        outcome, note = fakecloud._probe_classify("HOP", _co(captures.BLOCK_2L0E_LOADED))
        self.assertEqual(outcome, "ack")
        self.assertEqual(note, "")

    def test_mismatch_when_another_block_arrives(self):
        outcome, note = fakecloud._probe_classify("HOP", _co(captures.BLOCK_WDRR_NO_GRID_FLOW))
        self.assertEqual(outcome, "mismatch")
        self.assertIn("2l0E", note)


    def test_the_hbms2_nine_token_variant_is_accepted(self):
        raw = b"(0000.0 0000.0 0 3317 0003 3313 0002 100.0 0000000000000000\r"
        outcome, note = fakecloud._probe_classify("HBMS2", _co(raw))
        self.assertEqual(outcome, "ack")
        self.assertEqual(note, "")

    def test_nak_text(self):
        outcome, note = fakecloud._probe_classify("HOP", _co(b"(NAKss\r"))
        self.assertEqual(outcome, "nak")
        self.assertIn("NAK", note)

    def test_dongle_refusal_is_nak(self):
        outcome, note = fakecloud._probe_classify("HOP", {"i": 504, "e": 104})
        self.assertEqual(outcome, "nak")
        self.assertIn("e=104", note)

    def test_qflag_ack_without_crc(self):
        outcome, _ = fakecloud._probe_classify("QFLAG", _co(b"(EbuvxyDajkz\r"))
        self.assertEqual(outcome, "ack")

    def test_missing_body_is_mismatch(self):
        outcome, _ = fakecloud._probe_classify("HOP", {"i": 504, "e": 0, "b": {}})
        self.assertEqual(outcome, "mismatch")


class TestProbeStateMachine(unittest.TestCase):
    def setUp(self):
        self.counter = 0
        self.sent_ci = []
        self.conn = SimpleNamespace(dtu_id="test", closed=False)
        self.send_patch = mock.patch.object(fakecloud, "_send_control_ci", side_effect=self._fake_send)
        self.send_patch.start()
        self.addCleanup(self.send_patch.stop)
        for name, value in (
            ("LIVE_PROBE_COMMANDS", "HOP"),
            ("LIVE_PROBE_REPEATS", 2),
            ("LIVE_PROBE_GAP_SEC", 0.0),
            ("LIVE_PROBE_INFLIGHT", 1),
            ("LOCAL_CLOUD_IP", "192.0.2.10"),
        ):
            patcher = mock.patch.object(fakecloud, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        log_patch = mock.patch.object(fakecloud, "log")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    def _fake_send(self, ci_b64, conn=None, claim=True, sent_at=None):
        self.sent_ci.append(ci_b64)
        self.counter += 1
        conn.last_sent_token = f"t{self.counter}"
        return True

    def test_ack_then_nak_finishes(self):
        with mock.patch.object(fakecloud, "_probe_write_json", return_value=None):
            fakecloud._probe_tick(self.conn, 0.0)
            self.assertEqual(self.conn.probe_stats["HOP"]["n"], 1)
            self.assertTrue(fakecloud._probe_handle_reply(self.conn, "t1", _co(captures.BLOCK_2L0E_LOADED)))

            fakecloud._probe_tick(self.conn, 0.0)
            self.assertEqual(self.conn.probe_stats["HOP"]["n"], 2)
            self.assertTrue(fakecloud._probe_handle_reply(self.conn, "t2", _co(b"(NAKss\r")))

            fakecloud._probe_tick(self.conn, 0.0)
        self.assertTrue(self.conn.probe_done)
        self.assertFalse(self.conn.probe_active)
        stats = self.conn.probe_stats["HOP"]
        self.assertEqual((stats["ack"], stats["nak"], stats["missing"], stats["mismatch"]), (1, 1, 0, 0))

    def test_no_answer_becomes_missing(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_REPEATS", 1), mock.patch.object(
            fakecloud, "_probe_write_json", return_value=None
        ):
            fakecloud._probe_tick(self.conn, 0.0)
            fakecloud._probe_tick(self.conn, 4.0)
        self.assertTrue(self.conn.probe_done)
        self.assertEqual(self.conn.probe_stats["HOP"]["missing"], 1)

    def test_wrong_block_becomes_mismatch(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_REPEATS", 1), mock.patch.object(
            fakecloud, "_probe_write_json", return_value=None
        ):
            fakecloud._probe_tick(self.conn, 0.0)
            fakecloud._probe_handle_reply(self.conn, "t1", _co(captures.BLOCK_WDRR_NO_GRID_FLOW))
            fakecloud._probe_tick(self.conn, 0.0)
        self.assertEqual(self.conn.probe_stats["HOP"]["mismatch"], 1)



    def test_out_of_order_replies_match_by_token_not_i(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_INFLIGHT", 2), mock.patch.object(
            fakecloud, "LIVE_PROBE_REPEATS", 2
        ), mock.patch.object(fakecloud, "_probe_write_json", return_value=None):
            fakecloud._probe_tick(self.conn, 0.0)
            self.assertEqual(len(self.conn.probe_outstanding), 2)
            # The dongle answers the second command first: only the echoed "t" can
            # tell them apart, because both dev_rpc requests use i=503.
            self.assertTrue(fakecloud._probe_handle_reply(self.conn, "t2", _co(captures.BLOCK_2L0E_LOADED)))
            self.assertTrue(fakecloud._probe_handle_reply(self.conn, "t1", _co(captures.BLOCK_2L0E_LOADED)))
            fakecloud._probe_tick(self.conn, 0.0)
        self.assertEqual(self.conn.probe_stats["HOP"]["ack"], 2)
        self.assertEqual(self.conn.probe_stats["HOP"]["mismatch"], 0)

    def test_ten_consecutive_missing_answers_abort(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_REPEATS", 20), mock.patch.object(
            fakecloud, "_probe_write_json", return_value=None
        ):
            for index in range(11):
                fakecloud._probe_tick(self.conn, index * 4.0)
        self.assertTrue(self.conn.probe_done)
        self.assertTrue(self.conn.probe_aborted)
        self.assertIn("consecutive missing", self.conn.probe_abort_reason)

    def test_sixty_second_watchdog_aborts_without_replies(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_REPEATS", 1), mock.patch.object(
            fakecloud, "LIVE_PROBE_STALL_SEC", 10.0
        ), mock.patch.object(fakecloud, "_probe_write_json", return_value=None):
            fakecloud._probe_tick(self.conn, 0.0)
            fakecloud._probe_tick(self.conn, 11.0)
        self.assertTrue(self.conn.probe_done)
        self.assertTrue(self.conn.probe_aborted)
        self.assertIn("no answer", self.conn.probe_abort_reason)


    def test_plain_prefix_encodes_the_command_without_crc(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_COMMANDS", "plain:QMOD"), mock.patch.object(
            fakecloud, "LIVE_PROBE_REPEATS", 1
        ), mock.patch.object(fakecloud, "_probe_write_json", return_value=None):
            fakecloud._probe_tick(self.conn, 0.0)
        self.assertEqual(base64.b64decode(self.sent_ci[0]), b"QMOD\r")


    def test_ack_also_stores_raw_and_token(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_REPEATS", 1), mock.patch.object(
            fakecloud, "_probe_write_json", return_value=None
        ):
            fakecloud._probe_tick(self.conn, 0.0)
            fakecloud._probe_handle_reply(self.conn, "t1", _co(captures.BLOCK_2L0E_LOADED))
        self.assertEqual(self.conn.probe_raw["HOP"]["token"], "t1")
        self.assertEqual(self.conn.probe_raw["HOP"]["outcome"], "ack")
        self.assertIn("228.5", self.conn.probe_raw["HOP"]["text"])

    def test_mismatch_stores_the_raw_answer(self):
        with mock.patch.object(fakecloud, "LIVE_PROBE_REPEATS", 1), mock.patch.object(
            fakecloud, "_probe_write_json", return_value=None
        ):
            fakecloud._probe_tick(self.conn, 0.0)
            fakecloud._probe_handle_reply(self.conn, "t1", _co(captures.BLOCK_WDRR_NO_GRID_FLOW))
        self.assertIn("HOP", self.conn.probe_raw)
        self.assertIn(b"232.7", self.conn.probe_raw["HOP"]["text"].encode("latin1"))

    def test_unknown_token_is_not_consumed(self):
        fakecloud._probe_tick(self.conn, 0.0)
        self.assertFalse(fakecloud._probe_handle_reply(self.conn, "other", _co(captures.BLOCK_2L0E_LOADED)))

    def test_json_written_with_expected_shape(self):
        self.conn.probe_started = time.time()
        self.conn.probe_inflight = 1
        self.conn.probe_commands_list = ["HOP"]
        self.conn.probe_stats = {
            "HOP": {"n": 2, "ack": 1, "nak": 0, "missing": 1, "mismatch": 0, "rtts": [400.0, 600.0]}
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            fakecloud, "STATE_CACHE_FILE", os.path.join(directory, "state.json")
        ):
            path = fakecloud._probe_write_json(self.conn)
            self.assertIsNotNone(path)
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        self.assertEqual(payload["commands"]["HOP"]["n"], 2)
        self.assertEqual(payload["commands"]["HOP"]["ack"], 1)
        self.assertEqual(payload["commands"]["HOP"]["missing"], 1)
        self.assertIsNotNone(payload["commands"]["HOP"]["rtt_ms"]["p50"])


if __name__ == "__main__":
    unittest.main()
