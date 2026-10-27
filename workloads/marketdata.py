#!/usr/bin/env python3

import argparse
import json
import socket
import struct
import time
from collections import defaultdict

MAGIC = b"LLNI"
VERSION = 1

# magic, version, message_type, feed_id, flags,
# channel_id, sequence, send_timestamp_ns, payload_length
HEADER = struct.Struct("!4sBBBBIQQH")

IP_ADD_SOURCE_MEMBERSHIP = 39

# Linux UAPI values verified on the Ubuntu 1 host. Python 3.12.3's socket
# module does not expose these names in this environment.
LINUX_SO_TIMESTAMPING = 37
LINUX_SCM_TIMESTAMPING = LINUX_SO_TIMESTAMPING
LINUX_SOF_TIMESTAMPING_RX_SOFTWARE = 1 << 3
LINUX_SOF_TIMESTAMPING_SOFTWARE = 1 << 4
SCM_TIMESTAMPING = struct.Struct("@6l")


def encode_packet(feed_id, channel_id, sequence, payload):
    header = HEADER.pack(
        MAGIC,
        VERSION,
        1,
        feed_id,
        0,
        channel_id,
        sequence,
        time.time_ns(),
        len(payload),
    )
    return header + payload


def decode_packet(packet):
    if len(packet) < HEADER.size:
        raise ValueError("packet shorter than header")

    (
        magic,
        version,
        message_type,
        feed_id,
        flags,
        channel_id,
        sequence,
        send_ns,
        payload_length,
    ) = HEADER.unpack_from(packet)

    if magic != MAGIC:
        raise ValueError("invalid magic")

    if version != VERSION:
        raise ValueError(f"unsupported version: {version}")

    payload = packet[HEADER.size:]

    if len(payload) != payload_length:
        raise ValueError("payload length mismatch")

    return {
        "message_type": message_type,
        "feed_id": feed_id,
        "flags": flags,
        "channel_id": channel_id,
        "sequence": sequence,
        "send_ns": send_ns,
        "payload": payload,
    }


def publish(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.source, 0))

    sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_IF,
        socket.inet_aton(args.source),
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, args.ttl)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 0)

    payload = b"x" * args.payload_bytes
    interval_ns = int(1_000_000_000 / args.pps)
    deadline = time.monotonic_ns()

    for offset in range(args.count):
        sequence = args.start_sequence + offset
        packet = encode_packet(
            feed_id=args.feed_id,
            channel_id=args.channel_id,
            sequence=sequence,
            payload=payload,
        )

        sock.sendto(packet, (args.group, args.port))

        deadline += interval_ns
        remaining_ns = deadline - time.monotonic_ns()

        if remaining_ns > 0:
            time.sleep(remaining_ns / 1_000_000_000)

    print(
        json.dumps(
            {
                "event": "publisher_summary",
                "feed_id": args.feed_id,
                "channel_id": args.channel_id,
                "source": args.source,
                "group": args.group,
                "port": args.port,
                "count": args.count,
                "pps": args.pps,
                "first_sequence": args.start_sequence,
                "last_sequence": args.start_sequence + args.count - 1,
            },
            sort_keys=True,
        )
    )


def parse_subscription(value):
    parts = value.split(",")

    if len(parts) != 3:
        raise argparse.ArgumentTypeError(
            "subscription must be FEED_ID,SOURCE,GROUP"
        )

    feed_id, source, group = parts
    return int(feed_id), source, group


def decode_rx_software_timestamp(ancillary):
    """Return the Linux SCM_TIMESTAMPING software RX time in nanoseconds."""
    for level, cmsg_type, data in ancillary:
        if level != socket.SOL_SOCKET or cmsg_type != LINUX_SCM_TIMESTAMPING:
            continue
        if len(data) < SCM_TIMESTAMPING.size:
            continue

        seconds, nanoseconds, *_ = SCM_TIMESTAMPING.unpack_from(data)
        if seconds == 0 and nanoseconds == 0:
            return None
        if not 0 <= nanoseconds < 1_000_000_000:
            return None
        return seconds * 1_000_000_000 + nanoseconds

    return None


def receive(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", args.port))
    sock.settimeout(0.25)

    if args.rx_sw_timestamp:
        timestamp_flags = (
            LINUX_SOF_TIMESTAMPING_RX_SOFTWARE
            | LINUX_SOF_TIMESTAMPING_SOFTWARE
        )
        sock.setsockopt(
            socket.SOL_SOCKET,
            LINUX_SO_TIMESTAMPING,
            timestamp_flags,
        )

    expected_feeds = set()

    for feed_id, source, group in args.subscription:
        expected_feeds.add(feed_id)

        membership = (
            socket.inet_aton(group)
            + socket.inet_aton(args.interface)
            + socket.inet_aton(source)
        )

        sock.setsockopt(
            socket.IPPROTO_IP,
            IP_ADD_SOURCE_MEMBERSHIP,
            membership,
        )

    last_sequence = {}
    counters = defaultdict(int)
    seen_feeds = set()
    stop_at = time.monotonic() + args.duration

    while time.monotonic() < stop_at:
        try:
            if args.rx_sw_timestamp:
                packet, ancillary, _, sender = sock.recvmsg(
                    65535,
                    socket.CMSG_SPACE(SCM_TIMESTAMPING.size),
                )
            else:
                packet, sender = sock.recvfrom(65535)
                ancillary = []
        except socket.timeout:
            continue

        arrival_ns = time.time_ns()
        rx_software_ns = (
            decode_rx_software_timestamp(ancillary)
            if args.rx_sw_timestamp
            else None
        )

        try:
            message = decode_packet(packet)
        except ValueError as error:
            counters["decode_error"] += 1
            print(
                json.dumps(
                    {
                        "event": "decode_error",
                        "error": str(error),
                        "sender": sender[0],
                    },
                    sort_keys=True,
                )
            )
            continue

        feed_id = message["feed_id"]
        channel_id = message["channel_id"]
        sequence = message["sequence"]
        stream = (feed_id, channel_id)
        previous = last_sequence.get(stream)

        seen_feeds.add(feed_id)

        if previous is None:
            classification = "first"
            last_sequence[stream] = sequence
        elif sequence == previous + 1:
            classification = "in_order"
            last_sequence[stream] = sequence
        elif sequence > previous + 1:
            classification = "gap"
            counters["missing_messages"] += sequence - previous - 1
            last_sequence[stream] = sequence
        elif sequence == previous:
            classification = "duplicate"
        else:
            classification = "reordered"

        counters[classification] += 1
        counters["received"] += 1

        record = {
            "event": "packet",
            "classification": classification,
            "feed_id": feed_id,
            "channel_id": channel_id,
            "sequence": sequence,
            "sender": sender[0],
            "send_ns": message["send_ns"],
            "arrival_ns": arrival_ns,
            "host_observed_delta_ns": arrival_ns - message["send_ns"],
        }

        if args.rx_sw_timestamp:
            record["rx_software_ns"] = rx_software_ns
            record["kernel_to_app_ns"] = (
                arrival_ns - rx_software_ns
                if rx_software_ns is not None
                else None
            )
            if rx_software_ns is None:
                counters["rx_timestamp_missing"] += 1

        print(json.dumps(record, sort_keys=True))

    missing_feeds = sorted(expected_feeds - seen_feeds)

    summary = {
        "event": "receiver_summary",
        "interface": args.interface,
        "port": args.port,
        "expected_feeds": sorted(expected_feeds),
        "seen_feeds": sorted(seen_feeds),
        "missing_feeds": missing_feeds,
        "counters": dict(counters),
    }

    print(json.dumps(summary, sort_keys=True))

    if missing_feeds or counters["received"] == 0:
        raise SystemExit(2)


def build_parser():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    publisher = commands.add_parser("publish")
    publisher.add_argument("--source", required=True)
    publisher.add_argument("--group", required=True)
    publisher.add_argument("--port", type=int, default=20001)
    publisher.add_argument("--feed-id", type=int, required=True)
    publisher.add_argument("--channel-id", type=int, default=1)
    publisher.add_argument("--count", type=int, default=1000)
    publisher.add_argument("--pps", type=int, default=500)
    publisher.add_argument("--start-sequence", type=int, default=1)
    publisher.add_argument("--payload-bytes", type=int, default=64)
    publisher.add_argument("--ttl", type=int, default=32)
    publisher.set_defaults(handler=publish)

    receiver = commands.add_parser("receive")
    receiver.add_argument("--interface", required=True)
    receiver.add_argument("--port", type=int, default=20001)
    receiver.add_argument(
        "--subscription",
        action="append",
        type=parse_subscription,
        required=True,
    )
    receiver.add_argument("--duration", type=float, default=8)
    receiver.add_argument(
        "--rx-sw-timestamp",
        action="store_true",
        help="include Linux software receive timestamps in packet records",
    )
    receiver.set_defaults(handler=receive)

    return parser


def main():
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
