# 04 — Receiver scheduling delay

## Purpose

Measure how long receiver-a waits when it is runnable but another task
competes for its CPU. The receiver stays active; this experiment observes
scheduler wait-time distributions while adding a bounded CPU load to its
assigned vCPU. Keep receiver-b and publisher-a running; the publisher remains
at 5 pps in every phase.

`runqlat-bpfcc` counts scheduler wait events, not packets. Each histogram below
covers a 10-second interval; the complete bucket counts are retained in
[observations.json](evidence/observations.json).

## Baseline and contention

On Ubuntu1, get the current Python receiver-a PID. Replace `APP_PID` in each
command below with that literal numeric PID:

```sh
# Command
pgrep -af marketdata

# Process list from this run
# receiver-a=15403; receiver-b=18625; publisher-a=21673
```

Pin receiver-a to CPU 4, confirm its affinity, then collect three baseline
histograms:

```sh
# Commands on Ubuntu1
taskset -pc 4 APP_PID
taskset -pc APP_PID
runqlat-bpfcc -T -p APP_PID 10 3 | tee /tmp/e04-04-baseline.log

# Observed output
# Affinity: 0-11 -> 4
# Three windows ended 03:11:51, 03:12:01, 03:12:11 UTC
# 190 scheduler events; 8 in buckets >=1024 us (4.2%)
```

Pinning limits where the process may run; it does not reserve the CPU. In a
second Ubuntu1 terminal, add an ordinary busy loop to CPU 4 for at most 120
seconds. Collect the contention histograms while the loop is active:

```sh
# Load terminal
date -Is
timeout 120s taskset -c 4 bash -c 'while true; do :; done'
date -Is

# Diagnostics terminal, during the bounded load
runqlat-bpfcc -T -p APP_PID 10 3 | tee /tmp/e04-04-contention.log

# Load window and result
# Load: 2026-10-16T03:12:27+00:00 -> 2026-10-16T03:14:27+00:00
# Histograms ended 03:13:08, 03:13:18, 03:13:28 UTC (inside load window)
# 150 scheduler events; 14 in buckets >=1024 us (9.3%)
```

The timeout bounds the load. Press Ctrl-C in that terminal to stop it early.

## Recovery and cleanup

After the CPU loop ends, collect three more histograms and inspect receiver-a's
socket and UDP counters:

```sh
# Commands on Ubuntu1
mpstat -P 4 1 3
runqlat-bpfcc -T -p APP_PID 10 3 | tee /tmp/e04-04-recovery.log

# Recovery histograms ended 03:14:54, 03:15:04, 03:15:14 UTC
# 169 scheduler events; 6 in buckets >=1024 us (3.6%)

# Commands inside receiver-a
ss -uanm
nstat -asz UdpInDatagrams UdpInErrors UdpRcvbufErrors

# Final sample
# skmem:(r0,rb212992,t0,tb212992,f4096,w0,o112,bl0,d78)
# UdpInDatagrams=62241; UdpInErrors=78; UdpRcvbufErrors=78
# The 78 drop counters were carried over from the previous experiment.
```

Restore receiver-a's original CPU affinity (0–11 in the observed run):

```sh
# Command on Ubuntu1
taskset -pc 0-11 APP_PID
taskset -pc APP_PID

# The operator confirmed the original allowed CPU range was restored to 0-11.
```

## Result and limits

| Phase | Scheduler events | Waiting ≥1024 μs |
| --- | ---: | ---: |
| Baseline | 190 | 8 (4.2%) |
| Same-CPU contention | 150 | 14 (9.3%) |
| Recovery | 169 | 6 (3.6%) |

The long-wait share rose during same-CPU contention and fell after the load
ended. Most measured events remained in short wait-time buckets. Scheduler
events are run-queue samples, not packet samples, and bucket counts do not give
the exact wait time of each event.

The run had no `mpstat` sample during the load, so CPU utilization for that
window was not measured. This is a single VM comparison of scheduler wait
behavior under a controlled CPU load.
