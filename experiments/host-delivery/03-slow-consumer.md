# 03 — Slow consumer: queue growth, overflow and recovery

## Hypothesis

A live UDP socket buffers arrivals while its application is paused. A short
pause can drain without loss; a sustained pause exhausts receive memory and
produces kernel drops followed by an application sequence gap.

Use [shared startup](../../lab/README.md): 5 pps, 94-byte UDP payload, receiver-b
as the control. Keep all three processes continuous within each trial.

## Baseline

On the host, identify the Python receiver-a process by its interface argument:

```sh
pgrep -af marketdata
```

Use its current PID as `APP_PID` below. This is the application PID, distinct
from the container-init PID used by nsenter. In receiver-a:

```sh
docker exec -it clab-marketdata-ceos-receiver-a sh
ss -uanm
nstat -asz UdpInDatagrams UdpInErrors UdpRcvbufErrors
```

Retained baseline excerpt for port 20001:

```text
skmem:(r0,rb212992,t0,tb212992,f4096,w0,o112,bl0,d0)
UdpInDatagrams   32154
UdpInErrors     0
UdpRcvbufErrors 0
```

**r** is receive-memory allocation, **rb** the limit, and **d** the socket's
cumulative drop count. Memory accounting includes packet overhead.

## Short pause

On the host, after replacing APP_PID, run:

```sh
bash -c '
kill -STOP APP_PID
sleep 10
kill -CONT APP_PID
'
```

Keep this shell open. If interrupted, immediately run `kill -CONT APP_PID`
from another host terminal. STOP has no automatic timeout. In another terminal,
repeat `ss -uanm` inside receiver-a during and after the pause.

Observed short-pause excerpts:

```text
skmem:(r44160,rb212992,t0,tb212992,f896,w0,o112,bl0,d0)
skmem:(r70080,rb212992,t0,tb212992,f3648,w0,o112,bl0,d0)
skmem:(r0,rb212992,t0,tb212992,f4096,w0,o112,bl0,d0)
```

The queue drained, errors remained zero and no gap was logged. The original
short pause was entered manually, so its exact duration was not measured;
the block above is the normalized procedure.

## Sustained pause

Repeat with `sleep 60`, leaving the rate and socket settings unchanged. Sample
`ss -uanm` and `nstat` while the receiver is paused.

| Successive samples | r (bytes) | rb (bytes) | d (datagrams) |
| --- | ---: | ---: | ---: |
| 1 | 71040 | 212992 | 0 |
| 2 | 95040 | 212992 | 0 |
| 3 | 121920 | 212992 | 0 |
| 4 | 168960 | 212992 | 0 |
| 5 | **213120** | **212992** | **16** |
| 6 | **213120** | **212992** | **72** |

Later namespace counters:

```text
UdpInErrors     78
UdpRcvbufErrors 78
```

**Memory allocation plateaued near the limit while drops increased.** Packet
admission/accounting can overshoot the byte limit slightly. The two UDP error
counters describe overlapping errors; they are not added together. Socket and
namespace samples were taken at different times.

## Recovery and exact gap

After CONT, on the host:

```sh
grep -B 1 '"classification": "gap"' /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-b.log
```

Retained fields from the adjacent application records (full records in the
[evidence file](evidence/observations.json)):

```text
sequence 6619  in_order  host_observed_delta_ns 15626900259
sequence 6698  gap       host_observed_delta_ns 10777637
```

**Missing sequences: 6620–6697; 6698 − 6619 − 1 = 78.**
This workload has one sequence per datagram. The gap matches the final socket
drop count and receive-buffer error increment.

Two post-recovery samples:

```text
Socket: r0, rb212992, d78   (both samples)
UdpInDatagrams:   44148 → 44229
UdpInErrors:        78 → 78
UdpRcvbufErrors:    78 → 78
```

Receiver-a later advanced through 6812–6814; receiver-b through 6846–6848.
**The queue emptied, successful delivery continued and drops stabilized.**
The in-order record at 6619 had waited sufficiently to produce a **15.63 s**
application timestamp delta; the gap-reporting packet had a roughly **10.78 ms**
delta. Buffered messages were read before the receiver observed the missing
range. Timestamp boundaries are documented in shared startup; these are not
isolated socket-residence measurements.

## Cleanup and interpretation

Ensure `kill -CONT APP_PID` has been issued and use `ps -p APP_PID -o pid,stat,args`
to confirm the receiver is no longer stopped. Confirm advancing logs, an empty
queue and stable drop counters. No network settings changed in this case.

This trial demonstrates consumer suspension causing socket overflow. It does
not identify whether a real application's stall comes from computation, locks,
I/O or scheduling; those require additional evidence.
