# RChat UDP Protocol Specification

This integration is based on inspection of the installed RChat 1.5.0 application and the SCL-RChat Companion module 1.1.0.

## Transport

RChat uses IPv4 UDP broadcast to destination port `1090`. The desktop application binds its socket to port `1090`, listens on all IPv4 addresses, and sends to the selected interface's directed broadcast address. Mic-Wise prefers source port `1090`, but falls back to an ephemeral source port when RChat already owns the port; the RChat Companion module uses the same compatible ephemeral-port approach. Mic-Wise falls back to `255.255.255.255` when no interface is selected or its subnet broadcast cannot be resolved.

Packets are sent once per action. Unlike the older RadioWorld integration, RChat does not require duplicate packets or a delay between identical transmissions.

## Packet envelope

Every user message or command is encoded as UTF-8 using this format:

```text
RWSENDIP{sender_ip}#USER{username}#{command}
```

For example:

```text
RWSENDIP192.0.2.134#USERMic-Wise#KEYPFeedback risk on channel 4
```

The username is required for RChat to attribute and display incoming messages. Mic-Wise strips `#`, carriage returns, and line feeds from configured usernames so they cannot corrupt the delimiter-based envelope.

## Commands used by Mic-Wise

| Command | Meaning |
| --- | --- |
| `KEYP{text}` | Display a normal RChat message. `{text}` may contain UTF-8 characters. |
| `COMM0` | Turn flashing on. |
| `COMM1` | Turn flashing off. |
| `COMM8` | Clear the current message. |

RChat 1.5 also recognizes preset commands including `COMM2` (talk on radio), `COMM3` (act one clearance), `COMM4` (act two clearance), and `COMM7` (cancel clearance). Mic-Wise sends free-form alert text, so those presets are not part of its alert workflow.

## Alert sequence

For a normal alert, Mic-Wise sends:

1. `KEYP{alert_text}`
2. `COMM0` when flashing is enabled
3. after the configured hold time, `COMM1` when needed
4. `COMM8`

Each item is one UDP datagram carrying the complete envelope shown above.
