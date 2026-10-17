# Host-delivery diagnostics

Four executed fault-localization cases connect network observations to Linux
receive policy, multicast membership, socket queues and CPU scheduling.

| Case | Controlled change | Strongest observation |
| --- | --- | --- |
| [01 — Reverse-path filtering](01-rpf-filter.md) | Source /32 route through management interface | Ingress capture continues; reverse-path drops increase |
| [02 — Wrong join interface](02-wrong-join-interface.md) | Receiver joins on management interface | Membership moves; downstream IGMP/PIM interest disappears |
| [03 — Slow consumer](03-slow-consumer.md) | Pause the receiver process | 78 missing sequences match 78 socket/receive-buffer drops |
| [04 — Scheduling contention](04-scheduling-delay.md) | Ordinary busy loop on the receiver's vCPU | Compare baseline, contention and recovery wait distributions |

## Method

Use the [shared environment and startup instructions](../../lab/README.md).
Change receiver-a only; keep receiver-b on the same Feed A as a control.
Observe the host interface, kernel counters, socket state and application
sequence records before injection, during the fault and after restoration.
Run one case at a time; record counter baselines and restore state between cases.

## Evidence provenance

Case results are excerpts and transcriptions from operator-provided terminal
output, recorded on 2026-10-15/16. Full raw sessions are not bundled.
Commands use portable PID/address placeholders and normalized log names;
retained numerical results are from the original runs, not generated examples.
The scheduling histogram counts and slow-consumer records are also retained
as [machine-readable evidence](evidence/observations.json).

Each case is a manually executed software experiment. No independent clean
rerun, physical NIC experiment, production deployment or statistically powered
benchmark is claimed. Restoration observations and missing evidence are stated
per case. The Python syntax check does not deploy the network or validate the
original measurements.
