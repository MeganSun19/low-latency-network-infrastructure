# Low-Latency Network Infrastructure

My hands-on notes and experiments while learning the network and Linux systems
behind low-latency trading infrastructure.

## What I have worked on

- Built and operated an eight-node Containerlab topology with four cEOS
  routers, two publishers and two receivers, using eBGP and PIM-SSM.
- Used a small Python multicast workload to follow market-data sequences from
  publisher to receiver.
- Investigated Linux receive-path behavior by changing reverse-path filtering,
  multicast socket membership, consumer scheduling and CPU contention.
- Compared packet captures, IGMP/PIM state, routes, socket queues, kernel
  counters and application sequence records to locate where delivery changed.

The [topology and setup notes](lab/README.md) describe the environment I used.
The [host-delivery experiments](experiments/host-delivery/README.md) contain
the commands, selected terminal output and explanations from the four
investigations.

The virtual setup is useful for studying protocol and Linux host behavior. It
does not model physical switch ASIC latency and buffering, hardware NIC
timestamping/PTP, or independent physical paths.

I used an authorized cEOS image; the image itself and generated lab state are
not included. Fault injections are intended for a disposable lab.
