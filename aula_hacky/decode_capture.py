from __future__ import annotations

import argparse
import subprocess

from .protocol import decode_rtc_set_packet


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Decode endpoint-5 HID packets from a tshark capture")
    parser.add_argument("capture", help="path to pcapng file")
    parser.add_argument("--bus", type=int, default=1, help="USB bus id")
    parser.add_argument("--device", type=int, default=4, help="USB device address")
    parser.add_argument("--frame-from", type=int, default=761, help="first frame to inspect")
    parser.add_argument("--frame-to", type=int, default=1200, help="last frame to inspect")
    return parser


def run_tshark(args: argparse.Namespace) -> list[tuple[str, str, str, str]]:
    cmd = [
        "tshark",
        "-r",
        args.capture,
        "-Y",
        (
            f"usb.bus_id=={args.bus} && usb.device_address=={args.device} "
            f"&& frame.number>={args.frame_from} && frame.number<={args.frame_to} "
            "&& usb.transfer_type==0x01 && usb.endpoint_address.number==5"
        ),
        "-T",
        "fields",
        "-e",
        "frame.number",
        "-e",
        "usb.src",
        "-e",
        "usb.dst",
        "-e",
        "usbhid.data",
    ]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    rows: list[tuple[str, str, str, str]] = []
    for line in completed.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def annotate(payload_hex: str) -> str:
    if not payload_hex:
        return ""

    payload = bytes.fromhex(payload_hex)
    if payload.startswith(bytes([0x0C, 0x10, 0x00, 0x00, 0x01, 0x5A])):
        decoded = decode_rtc_set_packet(payload)
        return (
            "rtc-set "
            f"{decoded['year']:04d}-{decoded['month']:02d}-{decoded['day']:02d} "
            f"{decoded['hour']:02d}:{decoded['minute']:02d}:{decoded['second']:02d}"
        )
    if payload.startswith(bytes([0x02, 0x00, 0x00])):
        return "session-init"
    if payload.startswith(bytes([0x20, 0x01, 0x00])):
        return "session-query"
    if payload.startswith(bytes([0x0C, 0x10, 0x00, 0x00])):
        return "rtc-ack"
    return ""


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    for frame, src, dst, payload_hex in run_tshark(args):
        note = annotate(payload_hex)
        if note:
            print(f"{frame}\t{src}\t{dst}\t{payload_hex}\t{note}")
        else:
            print(f"{frame}\t{src}\t{dst}\t{payload_hex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
