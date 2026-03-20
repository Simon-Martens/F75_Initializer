# aula-hacky

Linux-first tooling for the proprietary HID channel observed on the keyboard in
`keyboard5.pcapng`.

This implements the minimal RTC setter described by the capture:

1. Send a fixed 32-byte session-init packet.
2. Read its 32-byte reply.
3. Send a fixed 32-byte probe packet.
4. Read its 32-byte reply.
5. Send a generated 32-byte time packet.
6. Read its 32-byte reply.

The implementation targets Linux `hidraw` directly, so it does not need
third-party Python modules. You will typically need root or an appropriate
udev rule to open the device.

## Files

- `aula_hacky/cli.py`: RTC setter CLI
- `aula_hacky/protocol.py`: packet builders, checksum, validators
- `aula_hacky/hidraw_linux.py`: hidraw enumeration and I/O helpers
- `aula_hacky/decode_capture.py`: tshark-based decoder for packet captures
- `tests/test_protocol.py`: protocol tests from the observed capture

## Usage

Create the environment and run commands with `uv`.
This project is configured for offline-safe `uv run python -m ...` usage, so it
does not need to download packaging backends from PyPI just to run locally.

List matching hidraw devices:

```bash
uv run python -m aula_hacky.cli --list
```

Set the keyboard clock to the current local time:

```bash
sudo uv run python -m aula_hacky.cli --device /dev/hidrawX --time now
```

Set a specific local time:

```bash
sudo uv run python -m aula_hacky.cli --device /dev/hidrawX --time 2026-03-20T10:07:53
```

Dry-run and print the packets without touching the device:

```bash
uv run python -m aula_hacky.cli --time 2026-03-20T10:07:53 --dry-run
```

Decode the observed endpoint-5 packets from a capture:

```bash
uv run python -m aula_hacky.decode_capture /home/simon/keyboard5.pcapng
```

Run the test suite:

```bash
uv run python -m unittest discover -s tests -v
```

## Device Selection

By default the tool looks for a `hidraw` node with:

- vendor ID `05ac`
- product ID `024f`
- interface number `3`

If your keyboard presents a different product ID on Linux, use `--vid`, `--pid`,
or pass `--device` explicitly after finding the matching node with `--list`.

## Notes

- The third command encodes `year_since_2000, month, day, hour, minute, second`
  in raw binary.
- Byte 31 of every 32-byte packet is the checksum:
  `sum(packet[0:31]) & 0xff`.
- The first two commands are currently replayed as captured setup/probe packets.
- The actual config traffic in `keyboard5.pcapng` is on interface `3`
  (`/dev/hidraw7` on the current machine), which exposes a 32-byte input/output
  vendor report. Interface `4` is a different vendor HID interface.
