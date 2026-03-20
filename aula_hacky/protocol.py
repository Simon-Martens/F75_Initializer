from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

PACKET_SIZE = 32

SESSION_INIT_OUT = bytes.fromhex(
    "0200000000000000000000000000000000000000000000000000000000000002"
)
SESSION_INIT_IN = bytes.fromhex(
    "02000040300000450c0a800801ffff0000000000000000000000000000000054"
)
SESSION_QUERY_OUT = bytes.fromhex(
    "2001000000000000000000000000000000000000000000000000000000000021"
)
SESSION_QUERY_IN = bytes.fromhex(
    "2001006400000000000000000000000000000000000000000000000000000085"
)
RTC_SET_ACK = bytes.fromhex(
    "0c1000000000000000000000000000000000000000000000000000000000001c"
)


@dataclass(frozen=True)
class Transaction:
    name: str
    outgoing: bytes
    expected_reply_prefix: bytes
    expected_reply: bytes | None = None


def checksum(payload: bytes) -> int:
    if len(payload) != PACKET_SIZE - 1:
        raise ValueError(f"checksum expects {PACKET_SIZE - 1} bytes, got {len(payload)}")
    return sum(payload) & 0xFF


def finalize_packet(body: bytes) -> bytes:
    if len(body) != PACKET_SIZE - 1:
        raise ValueError(f"packet body must be {PACKET_SIZE - 1} bytes, got {len(body)}")
    return body + bytes([checksum(body)])


def build_rtc_set_packet(when: datetime) -> bytes:
    year = when.year - 2000
    if not 0 <= year <= 255:
        raise ValueError(f"year {when.year} cannot be encoded as year_since_2000")

    body = bytes(
        [
            0x0C,
            0x10,
            0x00,
            0x00,
            0x01,
            0x5A,
            year,
            when.month,
            when.day,
            when.hour,
            when.minute,
            when.second,
            0x00,
            0x05,
            0x00,
            0x00,
            0x00,
            0xAA,
            0x55,
        ]
        + [0x00] * 12
    )
    return finalize_packet(body)


def decode_rtc_set_packet(packet: bytes) -> dict[str, int]:
    validate_packet(packet)
    if packet[:6] != bytes([0x0C, 0x10, 0x00, 0x00, 0x01, 0x5A]):
        raise ValueError("packet does not look like an RTC set command")

    return {
        "year": 2000 + packet[6],
        "month": packet[7],
        "day": packet[8],
        "hour": packet[9],
        "minute": packet[10],
        "second": packet[11],
    }


def validate_packet(packet: bytes) -> None:
    if len(packet) != PACKET_SIZE:
        raise ValueError(f"packet must be {PACKET_SIZE} bytes, got {len(packet)}")
    if checksum(packet[:-1]) != packet[-1]:
        raise ValueError(
            f"invalid checksum: expected 0x{checksum(packet[:-1]):02x}, got 0x{packet[-1]:02x}"
        )


def validate_reply(reply: bytes, expected_prefix: bytes, exact: bytes | None = None) -> None:
    validate_packet(reply)
    if not reply.startswith(expected_prefix):
        raise ValueError(
            f"reply prefix mismatch: expected {expected_prefix.hex()}, got {reply.hex()}"
        )
    if exact is not None and reply != exact:
        raise ValueError(f"reply mismatch: expected {exact.hex()}, got {reply.hex()}")


def is_valid_reply(reply: bytes, expected_prefix: bytes, exact: bytes | None = None) -> bool:
    try:
        validate_reply(reply, expected_prefix, exact=exact)
    except ValueError:
        return False
    return True


def iter_candidate_packets(raw_report: bytes) -> list[bytes]:
    candidates: list[bytes] = []
    seen: set[bytes] = set()

    def add(candidate: bytes) -> None:
        if candidate in seen:
            return
        seen.add(candidate)
        candidates.append(candidate)

    if len(raw_report) >= PACKET_SIZE:
        add(raw_report[:PACKET_SIZE])
        add(raw_report[-PACKET_SIZE:])

        for offset in range(0, len(raw_report) - PACKET_SIZE + 1):
            window = raw_report[offset : offset + PACKET_SIZE]
            try:
                validate_packet(window)
            except ValueError:
                continue
            add(window)

    return candidates


def build_transaction_sequence(when: datetime) -> list[Transaction]:
    return [
        Transaction(
            name="session-init",
            outgoing=SESSION_INIT_OUT,
            expected_reply_prefix=SESSION_INIT_OUT[:3],
            expected_reply=SESSION_INIT_IN,
        ),
        Transaction(
            name="session-query",
            outgoing=SESSION_QUERY_OUT,
            expected_reply_prefix=SESSION_QUERY_OUT[:3],
            expected_reply=SESSION_QUERY_IN,
        ),
        Transaction(
            name="rtc-set",
            outgoing=build_rtc_set_packet(when),
            expected_reply_prefix=bytes([0x0C, 0x10, 0x00, 0x00]),
            expected_reply=RTC_SET_ACK,
        ),
    ]


def parse_time_argument(value: str, now: datetime | None = None) -> datetime:
    if value == "now":
        return now or datetime.now().astimezone()

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return parsed.astimezone().replace(tzinfo=None)
    return parsed
