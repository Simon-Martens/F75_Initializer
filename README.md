# aula-hacky

Tooling for the proprietary HID channel protocol of the AULA F75 MAX keyboard, so we can initialize it with the right date and time from linux; this is neccessary for the screen to stop showing the AULA logo and animation and instead enter "normal" mode.

This implements two RTC setter paths:

- Cable path, preferred when present:
  - 64-byte HID feature reports on interface `3`
  - captured from the wired `0c45:800a` device in `keyboard6.pcapng`
- Dongle path, used as fallback:
  - 32-byte HID interrupt reports on interface `3`
  - captured from the `05ac:024f` dongle in `keyboard5.pcapng`

The implementation targets Linux `hidraw` directly, so it does not need
third-party Python modules. You will typically need root or an appropriate
udev rule to open the device.

## Prerequisites

- Linux with `hidraw` support enabled
- Python 3
- `uv`
- `sudo` access to open the keyboard HID interface

On a normal Linux distribution such as Ubuntu or Arch, this should work as long
as the keyboard exposes its vendor HID interface through `/dev/hidraw*`.

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

Set the keyboard clock to the current local time with autodiscovery:

```bash
sudo uv run python -m aula_hacky.cli --time now
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

By default the tool prefers:

- vendor ID `0c45`
- product ID `800a`
- interface number `3`

If the wired keyboard is not present, it falls back to:

- vendor ID `05ac`
- product ID `024f`
- interface number `3`

You can always override this with `--vid`, `--pid`, or `--device`.

## Notes

- The third command encodes `year_since_2000, month, day, hour, minute, second`
  in raw binary.
- Byte 31 of every 32-byte packet is the checksum:
  `sum(packet[0:31]) & 0xff`.
- The dongle path replays the first two captured setup/probe packets.
- The cable path uses four 64-byte feature reports:
  - `0418...`
  - `0428...`
  - time payload beginning `00015a...`
  - `0402...`
- The actual config traffic in `keyboard5.pcapng` is on interface `3`
  (`/dev/hidraw7` on the current machine), which exposes a 32-byte input/output
  vendor report. Interface `4` is a different vendor HID interface.
- The actual config traffic in `keyboard6.pcapng` is on interface `3`
  (`/dev/hidraw12` on the current machine), which exposes 64-byte feature
  reports over control `SET_REPORT` / `GET_REPORT`.
