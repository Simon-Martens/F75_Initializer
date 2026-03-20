from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HidrawDevice:
    path: str
    vendor_id: int | None
    product_id: int | None
    interface_number: int | None
    name: str | None
    input_report_bytes: int | None
    output_report_bytes: int | None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _walk_for_file(start: Path, filename: str) -> str | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        value = _read_text(candidate / filename)
        if value:
            return value
    return None


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError:
        return None


def _report_sizes_from_descriptor(descriptor: bytes | None) -> tuple[int | None, int | None]:
    if not descriptor:
        return (None, None)

    report_size = 0
    report_count = 0
    input_bits: list[int] = []
    output_bits: list[int] = []
    i = 0

    while i < len(descriptor):
        prefix = descriptor[i]
        i += 1

        if prefix == 0xFE:
            if i + 1 >= len(descriptor):
                break
            data_size = descriptor[i]
            i += 2 + data_size
            continue

        size_code = prefix & 0x03
        data_size = 4 if size_code == 3 else size_code
        item_type = (prefix >> 2) & 0x03
        item_tag = (prefix >> 4) & 0x0F

        data = descriptor[i : i + data_size]
        i += data_size
        value = int.from_bytes(data, "little") if data else 0

        if item_type == 1 and item_tag == 0x07:
            report_size = value
        elif item_type == 1 and item_tag == 0x09:
            report_count = value
        elif item_type == 0 and item_tag == 0x08:
            input_bits.append(report_size * report_count)
        elif item_type == 0 and item_tag == 0x09:
            output_bits.append(report_size * report_count)

    input_bytes = max((bits + 7) // 8 for bits in input_bits) if input_bits else None
    output_bytes = max((bits + 7) // 8 for bits in output_bits) if output_bits else None
    return (input_bytes, output_bytes)


def _parse_hid_id(uevent: str | None) -> tuple[int | None, int | None]:
    if not uevent:
        return (None, None)

    for line in uevent.splitlines():
        if not line.startswith("HID_ID="):
            continue
        _, value = line.split("=", 1)
        parts = value.split(":")
        if len(parts) != 3:
            return (None, None)
        try:
            return (int(parts[1], 16), int(parts[2], 16))
        except ValueError:
            return (None, None)
    return (None, None)


def enumerate_hidraw() -> list[HidrawDevice]:
    devices: list[HidrawDevice] = []
    for sys_node in sorted(Path("/sys/class/hidraw").glob("hidraw*")):
        dev_node = Path("/dev") / sys_node.name
        device_dir = sys_node / "device"
        uevent = _read_text(device_dir / "uevent")
        vendor_id, product_id = _parse_hid_id(uevent)

        interface_raw = _walk_for_file(device_dir, "bInterfaceNumber")
        interface_number = int(interface_raw, 16) if interface_raw else None
        report_descriptor = _read_bytes(device_dir / "report_descriptor")
        if report_descriptor is None:
            resolved = device_dir.resolve()
            report_descriptor = _read_bytes(resolved / "report_descriptor")
        input_report_bytes, output_report_bytes = _report_sizes_from_descriptor(report_descriptor)

        if vendor_id is None:
            vendor_raw = _walk_for_file(device_dir, "idVendor")
            vendor_id = int(vendor_raw, 16) if vendor_raw else None
        if product_id is None:
            product_raw = _walk_for_file(device_dir, "idProduct")
            product_id = int(product_raw, 16) if product_raw else None

        name = None
        if uevent:
            for line in uevent.splitlines():
                if line.startswith("HID_NAME="):
                    _, name = line.split("=", 1)
                    break

        devices.append(
            HidrawDevice(
                path=str(dev_node),
                vendor_id=vendor_id,
                product_id=product_id,
                interface_number=interface_number,
                name=name,
                input_report_bytes=input_report_bytes,
                output_report_bytes=output_report_bytes,
            )
        )
    return devices


def find_matching_device(
    device: str | None = None,
    vendor_id: int | None = None,
    product_id: int | None = None,
    interface_number: int | None = None,
) -> HidrawDevice:
    devices = enumerate_hidraw()

    if device is not None:
        for candidate in devices:
            if candidate.path == device:
                return candidate
        raise FileNotFoundError(f"no hidraw device found for {device}")

    for candidate in devices:
        if vendor_id is not None and candidate.vendor_id != vendor_id:
            continue
        if product_id is not None and candidate.product_id != product_id:
            continue
        if interface_number is not None and candidate.interface_number != interface_number:
            continue
        return candidate

    raise FileNotFoundError(
        "no matching hidraw device found"
        f" (vid={vendor_id!r}, pid={product_id!r}, interface={interface_number!r})"
    )


class HidrawTransport:
    def __init__(self, path: str, timeout_seconds: float = 1.0) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds
        self._fd: int | None = None
        self.report_size: int | None = None

    def __enter__(self) -> "HidrawTransport":
        self._fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def write(self, payload: bytes) -> int:
        if self._fd is None:
            raise RuntimeError("device is not open")
        return os.write(self._fd, payload)

    def read_exact(self, length: int) -> bytes:
        if self._fd is None:
            raise RuntimeError("device is not open")

        import select
        import time

        deadline = time.monotonic() + self.timeout_seconds
        chunks = bytearray()

        while len(chunks) < length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"timed out reading {length} bytes from {self.path}, got {len(chunks)}"
                )
            readable, _, _ = select.select([self._fd], [], [], remaining)
            if not readable:
                continue
            chunk = os.read(self._fd, length - len(chunks))
            if not chunk:
                raise TimeoutError(
                    f"device closed while reading {length} bytes from {self.path}"
                )
            chunks.extend(chunk)

        return bytes(chunks)

    def read_report(self, max_length: int = 64) -> bytes:
        if self._fd is None:
            raise RuntimeError("device is not open")

        import select
        import time

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"timed out waiting for a report from {self.path}")
            readable, _, _ = select.select([self._fd], [], [], remaining)
            if not readable:
                continue
            report = os.read(self._fd, max_length)
            if report:
                return report

    def drain_pending_reports(self, max_reads: int = 32) -> list[bytes]:
        if self._fd is None:
            raise RuntimeError("device is not open")

        import select

        drained: list[bytes] = []
        for _ in range(max_reads):
            readable, _, _ = select.select([self._fd], [], [], 0)
            if not readable:
                break
            report = os.read(self._fd, 64)
            if not report:
                break
            drained.append(report)
        return drained
