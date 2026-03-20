from __future__ import annotations

import argparse
from datetime import datetime

from .hidraw_linux import HidrawTransport, enumerate_hidraw, find_matching_device
from .protocol import (
    PACKET_SIZE,
    build_transaction_sequence,
    is_valid_reply,
    iter_candidate_packets,
    parse_time_argument,
)

DEFAULT_VID = 0x05AC
DEFAULT_PID = 0x024F
DEFAULT_INTERFACE = 3


def _format_device_line(device) -> str:
    vid = f"{device.vendor_id:04x}" if device.vendor_id is not None else "????"
    pid = f"{device.product_id:04x}" if device.product_id is not None else "????"
    interface = str(device.interface_number) if device.interface_number is not None else "?"
    name = device.name or "<unknown>"
    in_size = device.input_report_bytes if device.input_report_bytes is not None else "?"
    out_size = device.output_report_bytes if device.output_report_bytes is not None else "?"
    return f"{device.path} vid=0x{vid} pid=0x{pid} iface={interface} in={in_size} out={out_size} {name}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Set the keyboard RTC over the vendor HID channel")
    parser.add_argument("--device", help="explicit hidraw device, for example /dev/hidraw3")
    parser.add_argument("--vid", default=f"{DEFAULT_VID:04x}", help="USB vendor ID in hex")
    parser.add_argument("--pid", default=f"{DEFAULT_PID:04x}", help="USB product ID in hex")
    parser.add_argument(
        "--interface",
        type=int,
        default=DEFAULT_INTERFACE,
        help="USB interface number for the vendor HID endpoint",
    )
    parser.add_argument(
        "--time",
        default="now",
        help="local time as ISO-8601 or the literal 'now'",
    )
    parser.add_argument("--list", action="store_true", help="list hidraw devices and exit")
    parser.add_argument("--dry-run", action="store_true", help="print packets without opening a device")
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="read timeout for each reply in seconds",
    )
    parser.add_argument(
        "--report-size",
        type=int,
        help="override report size used for writes and reads; defaults to the device descriptor size",
    )
    parser.add_argument("--debug", action="store_true", help="print raw reports while waiting for replies")
    return parser


def _parse_hex(value: str) -> int:
    return int(value, 16)


def _wait_for_matching_reply(transport: HidrawTransport, tx, debug: bool) -> bytes:
    skipped: list[bytes] = []
    while True:
        raw_report = transport.read_report(max_length=transport.report_size or 64)
        if debug:
            print(f"{tx.name}: raw={raw_report.hex()}")

        for candidate in iter_candidate_packets(raw_report):
            if is_valid_reply(candidate, tx.expected_reply_prefix, exact=tx.expected_reply):
                for stale in skipped:
                    print(f"{tx.name}: skipped={stale.hex()}")
                return candidate
            skipped.append(candidate)

        if not iter_candidate_packets(raw_report):
            skipped.append(raw_report)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.list:
        for device in enumerate_hidraw():
            print(_format_device_line(device))
        return 0

    when = parse_time_argument(args.time)
    transactions = build_transaction_sequence(when)

    print(f"target-local-time: {when.isoformat(sep=' ')}")
    for tx in transactions:
        print(f"{tx.name}: out={tx.outgoing.hex()}")

    if args.dry_run:
        return 0

    selected = find_matching_device(
        device=args.device,
        vendor_id=None if args.device else _parse_hex(args.vid),
        product_id=None if args.device else _parse_hex(args.pid),
        interface_number=None if args.device else args.interface,
    )
    print(f"using-device: {_format_device_line(selected)}")

    report_size = (
        args.report_size
        or selected.output_report_bytes
        or selected.input_report_bytes
        or PACKET_SIZE
    )

    with HidrawTransport(selected.path, timeout_seconds=args.timeout) as transport:
        transport.report_size = report_size
        drained = transport.drain_pending_reports()
        if args.debug and drained:
            for report in drained:
                print(f"drained: {report.hex()}")
        for tx in transactions:
            outgoing = tx.outgoing.ljust(report_size, b"\x00")
            if len(outgoing) != report_size:
                raise RuntimeError(f"{tx.name}: report size {report_size} is smaller than packet size")
            written = transport.write(outgoing)
            if written != report_size:
                raise RuntimeError(f"{tx.name}: short write, wrote {written} bytes")
            reply = _wait_for_matching_reply(transport, tx, args.debug)
            print(f"{tx.name}: in={reply.hex()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
