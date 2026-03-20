from __future__ import annotations

from datetime import datetime
from unittest import TestCase

from aula_hacky.protocol import (
    PACKET_SIZE,
    RTC_SET_ACK,
    SESSION_INIT_IN,
    SESSION_INIT_OUT,
    SESSION_QUERY_IN,
    SESSION_QUERY_OUT,
    build_rtc_set_packet,
    build_transaction_sequence,
    checksum,
    decode_rtc_set_packet,
    iter_candidate_packets,
    validate_packet,
    validate_reply,
)


class ProtocolTests(TestCase):
    def test_observed_packets_have_valid_checksums(self) -> None:
        for packet in (
            SESSION_INIT_OUT,
            SESSION_INIT_IN,
            SESSION_QUERY_OUT,
            SESSION_QUERY_IN,
            RTC_SET_ACK,
            bytes.fromhex("0c100000015a1a03140a07350005000000aa55000000000000000000000000f2"),
        ):
            self.assertEqual(len(packet), PACKET_SIZE)
            validate_packet(packet)

    def test_build_rtc_packet_reproduces_capture(self) -> None:
        when = datetime(2026, 3, 20, 10, 7, 53)
        actual = build_rtc_set_packet(when)
        expected = bytes.fromhex(
            "0c100000015a1a03140a07350005000000aa55000000000000000000000000f2"
        )
        self.assertEqual(actual, expected)

    def test_checksum_byte_matches_sum(self) -> None:
        packet = build_rtc_set_packet(datetime(2026, 3, 20, 10, 7, 53))
        self.assertEqual(packet[-1], checksum(packet[:-1]))

    def test_decode_rtc_packet(self) -> None:
        decoded = decode_rtc_set_packet(
            bytes.fromhex("0c100000015a1a03140a07350005000000aa55000000000000000000000000f2")
        )
        self.assertEqual(
            decoded,
            {
                "year": 2026,
                "month": 3,
                "day": 20,
                "hour": 10,
                "minute": 7,
                "second": 53,
            },
        )

    def test_transaction_sequence_shapes(self) -> None:
        txs = build_transaction_sequence(datetime(2026, 3, 20, 10, 7, 53))
        self.assertEqual([tx.name for tx in txs], ["session-init", "session-query", "rtc-set"])
        validate_reply(SESSION_INIT_IN, txs[0].expected_reply_prefix, txs[0].expected_reply)
        validate_reply(SESSION_QUERY_IN, txs[1].expected_reply_prefix, txs[1].expected_reply)
        validate_reply(RTC_SET_ACK, txs[2].expected_reply_prefix, txs[2].expected_reply)

    def test_iter_candidate_packets_finds_embedded_packet(self) -> None:
        raw = b"\x00\x11" + SESSION_QUERY_IN + b"\x00" * 7
        candidates = iter_candidate_packets(raw)
        self.assertIn(SESSION_QUERY_IN, candidates)
