# 02 — Multicast membership on the wrong interface

## Hypothesis

Joining the feed on the management interface moves host membership away from
the routed market-data link. Leaf1 then loses receiver interest, removing the
downstream multicast branch. Correcting the join should restore the branch.

Start with [normal reception](../../lab/README.md). Keep the publisher and
receiver-b running throughout.

## Inject and inspect

Stop only receiver-a using Ctrl-C in its own workload terminal. Check that its
old socket and group membership have gone, and discover the management address:

```sh
docker exec -it clab-marketdata-ceos-receiver-a sh
ss -uanp
ip maddr show dev eth1
ip -4 addr show dev eth0
exit
docker inspect --format '{{.State.Pid}}' clab-marketdata-ceos-receiver-a
```

On the host, replace the two uppercase placeholders with the observed values:

```sh
nsenter --target RECEIVER_A_CONTAINER_PID --net python3 -u workloads/marketdata.py receive \
  --interface MANAGEMENT_IP --port 20001 \
  --subscription 1,172.16.1.2,232.10.1.1 --duration 7200 \
  | tee /tmp/e04-wrong-interface.log
```

Inspect receiver-a:

```sh
docker exec -it clab-marketdata-ceos-receiver-a sh
ss -uanp
ip maddr show dev eth0
ip maddr show dev eth1
cat /proc/net/igmp
tcpdump -pni eth1 \
  'udp and src host 172.16.1.2 and dst host 232.10.1.1 and dst port 20001'
```

Stop capture with Ctrl-C after a bounded observation period. In a host terminal:

```sh
docker exec -it clab-marketdata-ceos-leaf1 Cli
enable
show ip igmp groups 232.10.1.1 detail
show ip pim upstream joins 232.10.1.1
show ip mroute 232.10.1.1
```

Allow membership withdrawal/aging; do not assume immediate state removal.

## Observed results

| Layer | Fault observation |
| --- | --- |
| UDP socket | Bound to 0.0.0.0:20001 |
| Host membership | **232.10.1.1 on eth0, absent from eth1** |
| Leaf1 IGMP / upstream Join | No entries for the group |
| Leaf1 mroute | Source entry retained with Null incoming interface and no outgoing list |
| eth1 capture | 0 matching packets during observation |
| Control receiver | Advanced 18970 → 19052 |

**The host's subscription interface explains both the network control state
and the missing delivery.** The recorded capture duration was not retained,
so zero packets is a bounded observation, not a long-term traffic assertion.

## Restore and verify

Stop the wrong-interface receiver. Restart it using the normal receiver-a
command from shared startup (`--interface 172.16.101.2`), writing to a new log
such as `/tmp/e04-restored.log`. Repeat the host and EOS checks above.

Recorded recovery:

```text
Host: 232.10.1.1 present on eth1, absent from eth0
IGMP: Ethernet4; INCLUDE; reporter 172.16.101.2; source 172.16.1.2
PIM Join: neighbor 10.0.0.0 via Ethernet1; 172.16.1.2/32 SPT
mroute: incoming Ethernet1; outgoing Ethernet4
Receiver A: 20453, 20454, 20455 — in_order
Receiver B: 20481, 20482, 20483 — in_order
```

The correction restored membership, forwarding and delivery without switch
configuration changes. The restarted receiver establishes a new sequence
baseline; cross-restart missing counts were not measured.
