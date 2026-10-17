# 01 — Local reverse-path filtering

## Hypothesis

Strict Linux reverse-path validation accepts a packet when the source lookup
selects its ingress interface. Changing that lookup to management eth0 should
interrupt application delivery while packets remain visible on eth1.

Use the [shared startup](../../lab/README.md). Keep all three workload processes
continuous. This changes the endpoint's IP source validation, not PIM RPF.

## Procedure

Enter receiver-a:

```sh
docker exec -it clab-marketdata-ceos-receiver-a sh
ip route
cat /proc/sys/net/ipv4/conf/all/rp_filter
cat /proc/sys/net/ipv4/conf/eth0/rp_filter
cat /proc/sys/net/ipv4/conf/eth1/rp_filter
```

Record all values. The observed baseline had all three at 0. For a different
baseline, resolve the effective policy before proceeding (Linux uses the maximum
of `all` and the interface setting). In this lab:

```sh
sysctl -w net.ipv4.conf.eth1.rp_filter=1
ip route get 172.16.1.2
nstat -asz TcpExtIPReversePathFilter UdpRcvbufErrors
ip route show exact 172.16.1.2/32
```

Observed lookup:

```text
172.16.1.2 via 172.16.101.1 dev eth1 src 172.16.101.2
```

Both receivers continued receiving. Confirm no existing source /32 route;
then use the management gateway shown by `ip route` (172.31.250.1 in this lab):

```sh
ip route add 172.16.1.2/32 via 172.31.250.1 dev eth0
ip route get 172.16.1.2
tcpdump -pni eth1 -c 5 \
  'udp and src host 172.16.1.2 and dst host 232.10.1.1 and dst port 20001'
nstat -asz TcpExtIPReversePathFilter UdpRcvbufErrors
exit
tail -n 3 /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-b.log
```

Repeat log observations to establish progression, rather than comparing the
last sequence at two different sample times.

## Observed results

| Observation | Recorded result |
| --- | --- |
| Source lookup after injection | via management gateway, dev eth0 |
| eth1 capture | 5 packets; UDP payload 94 bytes; capture drops 0 |
| TcpExtIPReversePathFilter | 50 → 523 (**+473** in the sampled interval) |
| UdpRcvbufErrors | 0 → 0 |
| Receiver A | Stopped at sequence **2467** |
| Receiver B | Advanced 3010 → 3073 → 3198 |

**The evidence localizes the interruption to receiver-a's reverse-path policy.**
The counter interval covers part of the fault; its 473 drops are not the full
application gap. Namespace counters can include other traffic.

## Restore and verify

Inside receiver-a, remove only the injected route:

```sh
ip route del 172.16.1.2/32 via 172.31.250.1 dev eth0
ip route get 172.16.1.2
sysctl -w net.ipv4.conf.eth1.rp_filter=0
cat /proc/sys/net/ipv4/conf/eth1/rp_filter
nstat -asz TcpExtIPReversePathFilter UdpRcvbufErrors
```

Restore the saved policy value if it differed from 0. On the host:

```sh
grep -B 1 '"classification": "gap"' /tmp/e04-receiver-a.log
tail -n 3 /tmp/e04-receiver-a.log
```

The unchanged receiver resumed at **3391**, reporting a gap:

```text
Last received: 2467
First received after interruption: 3391
Missing: 2468–3390 = 3391 - 2467 - 1 = 923
```

Subsequent samples advanced in order through 10167; the control receiver's gap
query returned no entries. Route removal and application recovery were observed.
Final policy restoration was operator-confirmed; raw final policy and stable
post-recovery reverse-path counter outputs were not retained.
