# 03 — Slow consumer: queue growth, overflow and recovery

## Purpose

Observe how a live UDP socket buffers arrivals while the receiver application
is paused, and how a sustained pause leads to socket drops and a sequence gap.
Use the shared [5 pps workload](../../lab/README.md), keep publisher-a and
receiver-b running, and pause only receiver-a.

## Baseline

On Ubuntu1, identify receiver-a's current Python process. Its PID differs from
the container PID used with `nsenter`:

```sh
# Command on Ubuntu1
pgrep -af marketdata

# Recorded process list for this run
# receiver-a 15403; receiver-b 18625; publisher-a 21673
```

Inside receiver-a, inspect the UDP socket and namespace counters:

```sh
# Commands inside receiver-a
ss -uanm
nstat -asz UdpInDatagrams UdpInErrors UdpRcvbufErrors

# Recorded baseline for UDP 20001
# skmem:(r0,rb212992,t0,tb212992,f4096,w0,o112,bl0,d0)
# UdpInDatagrams=32154  UdpInErrors=0  UdpRcvbufErrors=0
```

`r` is allocated receive memory, `rb` its limit and `d` the socket's
cumulative drop count. The memory figure includes kernel packet overhead.

## Short pause

Replace the PID with the current receiver-a process PID on Ubuntu1. Keep this
shell open so it can send `CONT` after the wait:

```sh
# Command on Ubuntu1
bash -c '
kill -STOP 15403
sleep 10
kill -CONT 15403
'

# Recorded socket samples while paused, then after draining
# skmem:(r44160,rb212992,t0,tb212992,f896,w0,o112,bl0,d0)
# skmem:(r70080,rb212992,t0,tb212992,f3648,w0,o112,bl0,d0)
# skmem:(r0,rb212992,t0,tb212992,f4096,w0,o112,bl0,d0)
# UdpInErrors=0  UdpRcvbufErrors=0; no application gap logged
```

The original short pause was entered manually, so its exact duration was not
measured. If the shell is interrupted before `CONT`, run `kill -CONT 15403`
from another Ubuntu1 terminal. A short pause queued messages and then drained.

## Sustained pause

Repeat using `sleep 60`, keeping publisher rate and socket settings unchanged.
Sample `ss -uanm` inside receiver-a during the pause:

```sh
# Command on Ubuntu1; use the receiver-a PID from the current run
bash -c '
kill -STOP 15403
sleep 60
kill -CONT 15403
'

# Successive UDP 20001 socket samples
# r= 71040 rb=212992 d= 0
# r= 95040 rb=212992 d= 0
# r=121920 rb=212992 d= 0
# r=168960 rb=212992 d= 0
# r=213120 rb=212992 d=16
# r=213120 rb=212992 d=72
# Later nstat: UdpInErrors=78; UdpRcvbufErrors=78
```

Memory allocation reached the configured limit and dropped datagrams began to
accumulate. The two UDP counters overlap and must not be added together. The
`d=72` socket sample and `78` namespace counters were taken at different times.

## Recovery and gap attribution

After receiver-a resumes, inspect its application log and socket counters:

```sh
# Commands on Ubuntu1
grep -B 1 '"classification": "gap"' /tmp/e04-03-20261016-receiver-a.log
tail -n 3 /tmp/e04-03-20261016-receiver-a.log
tail -n 3 /tmp/e04-03-20261016-receiver-b.log

# Recorded adjacent receiver-a messages
# sequence=6619  classification=in_order  host_observed_delta_ns=15626900259
# sequence=6698  classification=gap        host_observed_delta_ns=10777637
# Missing sequences: 6620-6697, count=6698-6619-1=78
```

Inside receiver-a, confirm that the queue drains and the counters stop growing:

```sh
# Commands inside receiver-a
ss -uanm
nstat -asz UdpInDatagrams UdpInErrors UdpRcvbufErrors

# Two post-recovery socket samples
# skmem:(r0,rb212992,t0,tb212992,f4096,w0,o112,bl0,d78)
# Recorded namespace counters: UdpInDatagrams 44148 -> 44229
# UdpInErrors 78 -> 78; UdpRcvbufErrors 78 -> 78
```

**The 78-message gap matches the socket drop count and the receive-buffer
error increment.** Sequence 6619 was read in order after a 15.63-second
application timestamp delta, showing that a consumer can read old queued data
before it reaches the missing range. That timestamp includes host waiting and
processing; it is not a pure network or exact socket-residence measurement.
Receiver-a later advanced through 6812–6814, while receiver-b advanced through
6846–6848. Full retained scheduler and socket evidence is in
[observations.json](evidence/observations.json).

This controlled pause demonstrates consumer-side socket overflow. It does not
identify whether a real application's stall comes from computation, locking,
I/O or scheduling; those require correlated evidence.
