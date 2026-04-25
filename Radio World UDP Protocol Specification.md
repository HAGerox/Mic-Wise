# Radio World UDP Protocol Specification

> Derived from packet capture analysis (2026-04-25).  
> Capture scenario: typed "Hello ", enabled flash, disabled flash, cleared screen.

---

## Transport

| Property            | Value                   |
|---------------------|-------------------------|
| Protocol            | UDP (IPv4)              |
| Source Port         | 1090                    |
| Destination Port    | 1090                    |
| Destination Address | 255.255.255.255 (broadcast) |
| Encoding            | ASCII / UTF-8           |

Packets are broadcast on the local network. Any device listening on UDP port 1090 will receive them.

---

## Packet Format

Every packet follows this structure:

```
RWSENDIP{sender_ip}#{command}
```

| Field         | Description                                              |
|---------------|----------------------------------------------------------|
| `RWSENDIP`    | Fixed magic prefix identifying the protocol              |
| `{sender_ip}` | Dotted-decimal IPv4 address of the sending host          |
| `#`           | Fixed separator character                                |
| `{command}`   | Command string (see Commands section below)              |

**Example:**
```
RWSENDIP192.0.2.134#COMM1
```

---

## Reliability — Duplicate Transmission

Because UDP is connectionless and unreliable, each command packet is sent **twice**, approximately **39 ms** apart. Both packets are identical. Receivers should be tolerant of duplicates (idempotent handling is expected).

The only exception observed is the per-keystroke `KEYP` update, which is sent once per keypress (see below). The initial empty `KEYP` on session start is also sent as a duplicate pair.

---

## Commands

### 1. `KEYP` — Set Display Text

Sets (or updates) the text currently shown on the display.

```
KEYP{text}
```

- `{text}` is the full current content of the message, including all characters typed so far.
- The software sends a new `KEYP` packet **after every keystroke**, containing the complete accumulated text (not a delta/diff).
- When the message is confirmed (Enter / Space pressed), a final `KEYP` packet is sent with `0x0a` (Line Feed) appended to the text.
- To display an empty message / reset text without clearing, send `KEYP` with no `{text}`.

**Packet examples (typing "Hello"):**

| Keystroke | Packet payload                        |
|-----------|---------------------------------------|
| *(focus)* | `RWSENDIP192.0.2.134#KEYP`          |
| H         | `RWSENDIP192.0.2.134#KEYPH`         |
| e         | `RWSENDIP192.0.2.134#KEYPHe`        |
| l         | `RWSENDIP192.0.2.134#KEYPHel`       |
| l         | `RWSENDIP192.0.2.134#KEYPHell`      |
| o         | `RWSENDIP192.0.2.134#KEYPHello`     |
| *(confirm)* | `RWSENDIP192.0.2.134#KEYPHello\n` |

> **Integration note:** A client integrating with this system does **not** need to replicate the per-keystroke stream. It may send a single `KEYP{full_text}` packet (optionally followed by a `KEYP{full_text}\n` to confirm) to set the message directly.

---

### 2. `COMM0` — Enable Flash

Enables the flashing/blinking display mode.

```
COMM0
```

Full packet:
```
RWSENDIP192.0.2.134#COMM0
```

Send this command **twice**, ~39 ms apart.

---

### 3. `COMM1` — Disable Flash

Disables the flashing/blinking display mode (returns to normal static display).

```
COMM1
```

Full packet:
```
RWSENDIP192.0.2.134#COMM1
```

Send this command **twice**, ~39 ms apart.

---

### 4. `COMM8` — Clear Screen

Clears the display entirely.

```
COMM8
```

Full packet:
```
RWSENDIP192.0.2.134#COMM8
```

Send this command **twice**, ~39 ms apart.

---

## Observed Packet Sequence

The complete sequence captured, in order:

| # | Payload                                  | Action                        |
|---|------------------------------------------|-------------------------------|
| 1 | `RWSENDIP192.0.2.134#KEYP`             | Session start / empty field   |
| 2 | `RWSENDIP192.0.2.134#KEYP`             | *(duplicate, ~0.6 ms later)*  |
| 3 | `RWSENDIP192.0.2.134#KEYPH`            | Typed 'H'                     |
| 4 | `RWSENDIP192.0.2.134#KEYPHe`           | Typed 'e'                     |
| 5 | `RWSENDIP192.0.2.134#KEYPHel`          | Typed 'l'                     |
| 6 | `RWSENDIP192.0.2.134#KEYPHell`         | Typed 'l'                     |
| 7 | `RWSENDIP192.0.2.134#KEYPHello`        | Typed 'o'                     |
| 8 | `RWSENDIP192.0.2.134#KEYPHello\n`      | Confirmed message (0x0a)      |
| 9 | `RWSENDIP192.0.2.134#COMM0`            | Flash ON                      |
|10 | `RWSENDIP192.0.2.134#COMM0`            | *(duplicate, ~39 ms later)*   |
|11 | `RWSENDIP192.0.2.134#COMM1`            | Flash OFF                     |
|12 | `RWSENDIP192.0.2.134#COMM1`            | *(duplicate, ~39 ms later)*   |
|13 | `RWSENDIP192.0.2.134#COMM8`            | Clear screen                  |
|14 | `RWSENDIP192.0.2.134#COMM8`            | *(duplicate, ~39 ms later)*   |

---

## Integration Guide

### Sending a Message

1. Construct the UDP payload: `RWSENDIP{your_ip}#KEYP{message_text}`
2. Optionally follow with `RWSENDIP{your_ip}#KEYP{message_text}\n` to confirm.
3. Broadcast both to `255.255.255.255:1090` from source port `1090`.

### Flashing a Message

1. Send the message text using `KEYP` (above).
2. Enable flash: send `COMM0` twice, ~40 ms apart.
3. To stop flashing: send `COMM1` twice, ~40 ms apart.

### Clearing the Display After a Set Time

1. Send the message (and optionally enable flash).
2. After your desired display duration, send `COMM8` twice, ~40 ms apart.

### Pseudocode

```python
import socket
import time

BROADCAST_IP = "255.255.255.255"
PORT = 1090

def send_packet(sock, sender_ip, command):
    payload = f"RWSENDIP{sender_ip}#{command}".encode("ascii")
    sock.sendto(payload, (BROADCAST_IP, PORT))

def send_command(sock, sender_ip, command, repeat_delay_ms=39):
    """Send a command twice for reliability."""
    send_packet(sock, sender_ip, command)
    time.sleep(repeat_delay_ms / 1000)
    send_packet(sock, sender_ip, command)

def display_message(sender_ip, message, flash=False, clear_after_seconds=None):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", PORT))

        # Set message text
        send_command(sock, sender_ip, f"KEYP{message}")

        # Optionally enable flash
        if flash:
            send_command(sock, sender_ip, "COMM0")

        # Optionally clear after a delay
        if clear_after_seconds is not None:
            time.sleep(clear_after_seconds)
            if flash:
                send_command(sock, sender_ip, "COMM1")  # disable flash first
            send_command(sock, sender_ip, "COMM8")       # clear screen
```

---

## Notes and Unknowns

- **Other `COMM` values:** Only `COMM0`, `COMM1`, and `COMM8` were observed. Other values (e.g. `COMM2`–`COMM7`, `COMM9`+) may exist and control additional features not covered by this capture.
- **`sender_ip` field:** The IP in the packet header reflects the sender's own address. Receivers may use this to identify the source or for unicast replies.
- **Receiver behaviour:** This capture only shows outbound (sender) traffic. How receivers acknowledge or act on these commands is not captured here.
- **`SpotUdp` packets:** One packet with a `SpotUdp0` prefix and binary payload was observed. This appears to be from a separate unrelated protocol/application and is out of scope.
