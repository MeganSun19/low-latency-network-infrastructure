# Linux host-delivery investigations

I used these four scenarios to follow multicast delivery from the receiver's
network interface through Linux and into the application.

| Scenario | What I changed | What I saw |
| --- | --- | --- |
| [01 — Reverse-path filtering](01-rpf-filter.md) | Source `/32` route through the management interface | Packets remained visible on ingress while the receiver stopped advancing; reverse-path filter drops increased |
| [02 — Wrong join interface](02-wrong-join-interface.md) | Receiver joined on the management interface | Membership appeared on the wrong interface; the leaf removed downstream IGMP/PIM interest |
| [03 — Slow consumer](03-slow-consumer.md) | Paused the receiver process | 78 missing sequences aligned with socket drops and receive-buffer errors |
| [04 — Scheduling contention](04-scheduling-delay.md) | Ran a busy loop on the receiver's vCPU | Long scheduler-wait buckets increased during contention and declined after it ended |

Use the [topology and setup notes](../../lab/README.md) for the environment.
The case studies put commands beside selected output from my Ubuntu VM runs;
the Chinese runbook contains the longer learning notes.

The experiments combine packet captures, routes, IGMP/PIM state, socket
queues, kernel counters and application sequence records. They are useful for
understanding Linux host delivery. The VM topology does not model physical
switch ASIC latency/buffering, hardware NIC timestamps/PTP or physical path
diversity.

The scheduling histogram counts and slow-consumer records are available in
[observations.json](evidence/observations.json).
