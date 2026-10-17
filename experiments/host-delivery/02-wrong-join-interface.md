# 02 — Multicast membership on the wrong interface

## Purpose

Trace a receiver's source-specific multicast membership from its socket to the
leaf's IGMP/PIM forwarding state. Change only receiver-a's join interface;
publisher-a and receiver-b remain running as a control.

Start with the [shared lab](../../lab/README.md). Stop receiver-a from its own
workload terminal with Ctrl-C. In the container, confirm its socket and group
membership have cleared, and discover the management address:

```sh
# Commands inside receiver-a
ss -uanp
ip maddr show dev eth1
ip -4 addr show dev eth0

# Observed state after stopping the original receiver
# UDP 20001 socket: absent
# Feed group 232.10.1.1 on eth1: absent
# Management address: 172.31.250.3
```

On Ubuntu1, get the current receiver-a container PID and use it as the target
for `nsenter`. Start a receiver joined on the management address:

```sh
# Commands on Ubuntu1; substitute the current numeric container PID
docker inspect --format '{{.State.Pid}}' clab-marketdata-ceos-receiver-a
nsenter --target RECEIVER_A_CONTAINER_PID --net python3 -u workloads/marketdata.py receive \
  --interface 172.31.250.3 --port 20001 \
  --subscription 1,172.16.1.2,232.10.1.1 --duration 7200 \
  | tee /tmp/e04-wrong-interface.log
```

Inspect the host and leaf state. Stop tcpdump with Ctrl-C after a bounded
observation period:

```sh
# Commands inside receiver-a
ss -uanp
ip maddr show dev eth0
ip maddr show dev eth1
cat /proc/net/igmp
tcpdump -pni eth1 \
  'udp and src host 172.16.1.2 and dst host 232.10.1.1 and dst port 20001'

# Observed host and capture output
# UDP socket: 0.0.0.0:20001 exists
# 232.10.1.1 is joined on eth0 and absent from eth1
# /proc/net/igmp group entry 01010AE8 is under eth0
# tcpdump: 0 packets captured, 0 received by filter, 0 dropped by kernel
```

```text
# Commands in the leaf1 EOS CLI
show ip igmp groups 232.10.1.1 detail
show ip pim upstream joins 232.10.1.1
show ip mroute 232.10.1.1

# Observed forwarding state
# IGMP group: no entry
# PIM upstream Join: no entry
# mroute (172.16.1.2,232.10.1.1): flags PE; incoming interface Null; no OIL
```

Receiver-b advanced from sequence 18970 to 19052 during the observation while
the receiver-a capture saw no matching packets.

## Restore and verify

Stop the wrong-interface receiver. Query the current container PID and restart
receiver-a with the normal market-data interface (`172.16.101.2`). Then repeat
the host and EOS checks:

```sh
# Commands on Ubuntu1
docker inspect --format '{{.State.Pid}}' clab-marketdata-ceos-receiver-a
nsenter --target RECEIVER_A_CONTAINER_PID --net python3 -u workloads/marketdata.py receive \
  --interface 172.16.101.2 --port 20001 \
  --subscription 1,172.16.1.2,232.10.1.1 --duration 7200 \
  | tee /tmp/e04-restored.log

# Observed recovery output
# Host: 232.10.1.1 present on eth1, absent from eth0
# IGMP: Ethernet4, INCLUDE, reporter 172.16.101.2, source 172.16.1.2
# PIM Join: neighbor 10.0.0.0 via Ethernet1, source 172.16.1.2/32 SPT
# mroute: incoming Ethernet1, outgoing Ethernet4
# receiver-a: 20453, 20454, 20455 — in_order
# receiver-b: 20481, 20482, 20483 — in_order
```

Correcting the host membership restored the downstream branch and application
delivery without switch configuration changes. Receiver-a restarted and began
a fresh local sequence baseline.
