# 04 — Receiver scheduling delay

## Purpose

Measure how long the receiver waits when it is runnable but another task
competes for its CPU. This complements the paused-consumer case: here the
receiver remains active, and the experiment observes scheduler wait-time
distributions while adding a bounded CPU load to the receiver's assigned vCPU.

The receiver remains pinned to CPU 4 in all three phases. The publisher stays
at 5 packets per second. Use receiver-b as the delivery control and keep the
same processes running throughout the comparison.

## Establish the baseline

On Ubuntu1, list the current workload PIDs and identify receiver-a:

```sh
pgrep -af marketdata
```

Replace `APP_PID` in each command below with receiver-a's current numeric PID.
Set its allowed CPU to 4:

```sh
taskset -pc 4 APP_PID
taskset -pc APP_PID
```

The second command should show affinity list `4`. Pinning limits where the
process may run; it does not reserve that CPU. Record that `runqlat-bpfcc` is
installed, then collect three 10-second baseline histograms:

```sh
date -Is
runqlat-bpfcc -T -p APP_PID 10 3 | tee /tmp/e04-04-baseline.log
date -Is
```

`runqlat-bpfcc` measures time runnable tasks wait for CPU. Each histogram is a
10-second interval; `count` is the number of scheduler-wait events in each
bucket. It samples scheduler events, not network packets or packet latency.

## Add CPU contention

In a second Ubuntu1 terminal, run a CPU loop on CPU 4 for up to 120 seconds:

```sh
date -Is
timeout 120s taskset -c 4 bash -c 'while true; do :; done'
date -Is
```

While the loop is running, collect the competing phase in another terminal:

```sh
runqlat-bpfcc -T -p APP_PID 10 3 | tee /tmp/e04-04-contention.log
```

The timeout bounds the load. Press Ctrl-C in the load terminal to end it early.
If the command is interrupted after starting a background load in a modified
procedure, confirm it has stopped before continuing.

## Measure recovery

After the load command ends, collect the recovery phase:

```sh
mpstat -P 4 1 3
runqlat-bpfcc -T -p APP_PID 10 3 | tee /tmp/e04-04-recovery.log
```

Check delivery and socket state in receiver-a, then restore its original CPU
affinity (the observed initial range was 0–11):

```sh
docker exec -it clab-marketdata-ceos-receiver-a sh
ss -uanm
nstat -asz UdpInDatagrams UdpInErrors UdpRcvbufErrors
exit
taskset -pc 0-11 APP_PID
taskset -pc APP_PID
```

Use the original affinity if it differs from 0–11. Confirm receiver-a and
receiver-b sequence logs continue to advance.

## Recorded result

The recorded v2 trial ran on 2026-10-16. Receiver-a was pinned to CPU 4; a
120-second CPU loop was also pinned to CPU 4; publisher rate remained 5 pps.
The baseline histograms ended at 03:11:51, 03:12:01 and 03:12:11 UTC. The load
ran from 03:12:27 to 03:14:27 UTC. Contention histograms were 03:13:08,
03:13:18 and 03:13:28 UTC. Recovery histograms were 03:14:54, 03:15:04 and
03:15:14 UTC. All bucket counts are retained in
[observations.json](evidence/observations.json).

| Phase | Scheduler events | Events waiting ≥1024 μs |
| --- | ---: | ---: |
| Baseline | 190 | 8 (4.2%) |
| CPU contention | 150 | 14 (9.3%) |
| Recovery | 169 | 6 (3.6%) |

During the same run, receiver-a's socket queue was empty at the final sample;
`d=78`, `UdpInErrors=78` and `UdpRcvbufErrors=78` remained at the values left
by the previous slow-consumer experiment. No new receive-buffer drops were
observed in this scheduling trial. The v2 run did not include a contemporaneous
`mpstat` sample during the load, so no CPU-utilization percentage is attributed
to this comparison.

## Interpretation and limits

The long-wait share rose during same-CPU contention and fell after the load
ended. Most measured events still fell in short wait-time buckets. This is one
software-VM comparison, useful for practicing scheduler evidence and tail
analysis; it does not establish a production latency result or statistical
significance. A scheduler event is not one packet, and bucket counts do not
reveal exact individual wait times.

The experiment isolates CPU competition for an operator-controlled workload.
It does not identify the cause of a real application stall. For a production
incident, correlate scheduler evidence with NIC, softirq, socket-queue and
application-processing counters over the same time window.
