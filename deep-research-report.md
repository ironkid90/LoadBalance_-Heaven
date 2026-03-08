# Local Multi‑WAN and Multipath Design for TP‑Link TD‑W9960 and a Windows Host

## Problem framing and what your current evidence already proves

You’re effectively running **two logical WAN sessions (two PPPoE logins) over one physical DSL bearer**. Your own testing already demonstrated the two crucial facts that shape every “brilliant plan” from here:

First, **two PPP sessions can be simultaneously active** and can carry traffic at the same time (you confirmed distinct public IPs per source and concurrent flows). This means the ISP side allows dual PPP sessions and the modem can keep both up concurrently (at least when forced). That’s a big win: it means the problem is not “impossible,” it’s “architecture + bottlenecks + control.”

Second, your best “forced concurrency” numbers (~9.4–9.6 Mbps aggregate across multiple parallel flows) show you are currently **not close to the physical DSL ceiling** implied by 16.2 Mbps sync—and therefore there is still optimization headroom (or a hidden cap) beyond merely “getting both PPP sessions to route.” The rest of this report focuses on **how to redesign locally so you can (a) use both PPP sessions intelligently, (b) add 4G/USB later, (c) reduce latency/bufferbloat, and (d) isolate what is actually limiting throughput**—all without shipping your traffic to far-away bonding servers in the middle of the Internet.

## Reality check on throughput and why “7 + 7” is not automatically a clean 14

### Two PPPoE sessions do not create two copper pairs  
PPPoE is a **session/encapsulation mechanism** that runs over Ethernet frames; it does not magically provision a second physical DSL bearer. PPPoE specifically defines how PPP is carried over Ethernet and how sessions are established. citeturn0search3

So: even with two PPP sessions, you’re still bounded by one DSL physical layer (sync rate), plus overheads, plus any ISP-side shaping policies.

### DSL sync is not payload throughput  
On ADSL-style services, a meaningful portion of the physical sync is consumed by framing/encapsulation overhead. Two sources in your research stream capture the key mechanics clearly:

* **PPPoE adds 8 bytes of overhead** (6-byte PPPoE header + 2-byte PPP protocol id), which reduces the effective MRU/MTU from 1500 to ~1492 unless “baby jumbo” is supported end-to-end. citeturn0search31turn0search7turn0search11  
* Classic DSL aggregation commonly involves **ATM cell framing**, where payload is carried in **48-byte chunks** with per-cell overhead; this is exactly why SQM systems emphasize link-layer adaptation for ATM-based DSL. citeturn10search6turn0search7  

A practical implication: if you sync at ~16.2 Mbps down, it is normal that the best-case IP-layer throughput is lower. However, your observed ~9.6 Mbps aggregate is low enough that it suggests **either congestion, a hidden aggregate shaper, line errors/retransmits, suboptimal MTU/MSS behavior, or CPE/host negotiation issues**—or some combination.

### Single-flow “bonding” requires both ends to cooperate  
The reason a single download (one TCP connection) rarely hits “combined” speed is not a Windows limitation; it is a transport reality. A normal TCP connection is on a single path at a time. **Multipath TCP (MPTCP)** is one standardized way to use multiple paths under one logical connection. citeturn3search0turn3search8  

But MPTCP requires support in the path and/or endpoints; most public servers still do not offer it widely, which is why “true single-flow bonding” normally needs a cooperating aggregation endpoint (a VPS or bonding service).

## Why the previous approaches were constrained

### Windows NIC teaming (LBFO) is the wrong layer and not even a supported lever on client Windows  
You already saw the conceptual mismatch: NIC teaming is a Layer‑2 abstraction, while your problem is **Layer‑3/4 multi‑WAN** (different PPP sessions, different public IPs, different NAT states).

Microsoft’s own documentation draws a hard support boundary: the **NetLbfo (NIC Teaming/LBFO) feature is available only on Windows Server**, and “is not available on Windows 10 or any other client operating systems.” citeturn2search18  
Even where LBFO exists, it also warns that teaming different link speeds is not supported as a clean design assumption. citeturn2search0  

So, even if you hack LBFO onto a client build, you still end up with a tool designed for **one LAN uplink to a switch**, not **two WAN paths that must remain distinct for routing/NAT/PPP statefulness**.

### Speedify is excellent at what it’s built for, but its best features are inherently “server-assisted”  
Speedify’s own “How Speedify Works” description is explicit: its channel bonding “operates similar to a VPN” and uses **both a client-side application and a cloud server component** to distribute and reassemble traffic. citeturn17search4  

Speedify also directly answers your “can I bond without VPN servers” question: **packet-level channel bonding requires packets be split across links and reassembled at a remote server**, so you cannot get full bonding without a server-side component. citeturn17search19  

Speedify’s “Local Load Balancer” mode reinforces the same limit: **without a Speedify server connection, features like single-socket bonding are not available**. citeturn17search16  

Finally, Speedify even warns about one of the exact traps in your topology: bonding Wi‑Fi and Ethernet from the same router/same plan won’t increase performance because they share bandwidth. citeturn17search27  

So Speedify remains useful for experiments (especially with LTE/USB tether), but it can’t be your *fully local, no-remote-aggregation* core solution for “one stream uses both PPP sessions.”

### The TP‑Link host policy routing script was correct—but it’s still only steering, not bonding  
Your router script approach (source-based routing + NAT/MSS) is a valid form of **policy routing**: it decides which WAN a given host uses. That’s useful, but it’s not multipath bonding. It also tends to be fragile on consumer firmware, because “half-states” (rules survive while tables/routes don’t) can happen after reconnects—exactly what you found and repaired.

The conclusion: scripting on the W9960 can remain a tool in your kit, but your “brain” belongs somewhere you can control routing tables, link health checks, queueing, and WAN policies reliably—**locally**.

## The core recommendation: a local “router VM” that terminates the bridged PPPoE session

### What you want is multi‑WAN routing control, not a VPN bond  
Your constraints strongly point to a **local multi‑WAN router** that can:

* terminate multiple WANs (PPPoE + DHCP-routed uplink + later USB tether),
* do policy-based routing and load balancing per flow,
* do health checks and failover,
* do bufferbloat control (SQM/CAKE),
* keep everything local (no “Lebanon → far server → Internet” detour).

OpenWrt with **mwan3** is designed for exactly this category: it supports **multiple WAN interfaces**, does **outbound load balancing/failover** via weights, monitors links with repeated tests, and applies **policy-based routing rules** to steer traffic. citeturn0search0  

### Why “bridge + OpenWrt VM” is the cleanest bridge-based design  
Your best bridge-based design is:

* **W9960 remains DSL modem + minimal router for the household** (at least initially).
* You take the **secondary PPPoE session** and convert it into a **bridged service** (no NAT, no routing) that exists on a **dedicated LAN port**.
* Your **Windows PC hosts an OpenWrt VM** that terminates:
  * WAN1: a “normal” upstream via DHCP behind the W9960’s primary routed PPP (works immediately, minimal disruption),
  * WAN2: PPPoE directly over the bridged port (full control of that PPP session),
  * LAN: an internal Hyper‑V switch that Windows uses as its default gateway.

This gives you a *real* multi‑WAN router under your control, and it makes Speedify’s “Broadband adapters not visible” problem irrelevant, because **Speedify is no longer the multipath engine**—OpenWrt is.

### Evidence the W9960 firmware family supports “service separation to a dedicated LAN port”  
Even if TP‑Link’s UI doesn’t advertise your exact “secondary PPP bridge to LANx” scenario cleanly, the official TD‑W9960 user guide shows a conceptually similar feature: **IPTV can be separated and mapped to a specific LAN port**, including DSL modulation type selection and VLAN/PVC parameters. citeturn11view2  

That matters because your goal is also “bind a WAN-side service to one LAN port.” The UI surface might differ (Internet WAN service vs IPTV), but the hardware/firmware pattern of **port-specific service mapping** exists in this device family.

The same guide also mentions “connection type is not Bridge” as a requirement for some WAN selection features, which implies the product supports Bridge as a WAN connection type in its configuration model. citeturn8view0  

### Hyper‑V is the right local virtualization layer for this job  
The Hyper‑V piece matters because you need multiple, precisely controlled NIC attachments. Microsoft documents the three core virtual switch types and how external switches attach VMs to an external network; it also notes that creating an external switch can disrupt connectivity (important for a careful cutover). citeturn0search2  

Also, since you’re using PowerShell 7 in your workflow, it’s worth noting Microsoft explicitly added `Import-Module -UseWindowsPowerShell` to help load incompatible Windows PowerShell modules in PowerShell 7. citeturn1search10  
(Practically: if Hyper‑V cmdlets don’t show up in pwsh, Windows PowerShell 5.1 is usually the most predictable place to run Hyper‑V management commands.)

## Implementation runbook that matches your constraints and preserves rollback

This section is written to match your design goals: **do everything host-side first**, then do the router bridge cutover as the final controlled step.

### Host-side readiness and dependencies

You need three things ready before you touch the router:

* A working Hyper‑V management environment (Hyper‑V role + cmdlets accessible).
* A bootable OpenWrt x86_64 image in a Hyper‑V disk format (VHDX), with enough disk space for mwan3 + SQM packages.
* A second physical Ethernet path (highly recommended) so WAN1 and WAN2 are physically isolated.

If Hyper‑V cmdlets are missing in PowerShell 7, prefer either:
* Windows PowerShell 5.1 for Hyper‑V tasks, or
* `Import-Module Hyper-V -UseWindowsPowerShell` from PowerShell 7 on Windows. citeturn1search10turn1search26  

### Hyper‑V network topology

You will create:

* **LAN switch (Internal)**: `OpenWrt-LAN`  
  Windows gets a `vEthernet (OpenWrt-LAN)` interface here and uses OpenWrt as its gateway.

* **WAN1 switch (External)**: `OpenWrt-WAN1-RouterLAN`  
  Bound to your normal NIC connected to a normal LAN port on the W9960.

* **WAN2 switch (External)**: `OpenWrt-WAN2-Bridge`  
  Bound to a second NIC connected only to the W9960 bridged DSL service port.

Microsoft’s guidance on external vs internal switches and creating them with Hyper‑V Manager or `New‑VMSwitch` is the canonical reference; note especially the warning that creating an external switch may disrupt connectivity. citeturn0search2  

### OpenWrt VM shape

Your staged design choices are aligned with common best practice for OpenWrt-on-VM routing:

* Gen 2 VM (UEFI), **Secure Boot disabled** (unless you build signed images),
* 2 vCPU,
* 1 GB static memory (avoid dynamic memory surprises in a router role),
* 3 NICs: `lan`, `wan1`, `wan2`.

### Router-side bridge cutover: safest sequence

The safest bridge cutover (minimizing the chance of locking yourself out) is:

Keep PPPoE A routed on the W9960 for management and for household stability. Convert only PPPoE B to a bridged service exposed on one dedicated LAN port.

If you need to leverage built-in per-port separation behavior, the IPTV port mapping workflow in the official guide demonstrates the general pattern: “specify a LAN port for IPTV connection” and configure the WAN-side parameters based on modulation type and VLAN/PVC. citeturn11view2  
In practice, you are adapting the same “port‑bound service” concept to “bridged PPPoE service.”

### WAN2 PPPoE termination details that matter for performance

Once OpenWrt terminates PPPoE, MTU/MSS correctness becomes critical:

* PPPoE’s header overhead constrains MRU/MTU to **1492** in typical Ethernet environments. citeturn0search31turn0search11  
* Incorrect MTU/MSS often manifests as “some sites slow,” “downloads stall,” or strange retransmits/blackholes—especially when PMTUD is impaired. citeturn0search11  

So in the OpenWrt VM, treat MTU/MSS as first-class configuration (and keep MSS clamping available on WAN interfaces if needed).

## Multi‑WAN behavior you should implement first and why it matches your goals

### mwan3 for per-flow load balancing and policy routing

mwan3 is engineered for the exact “use both links, fail over fast, steer specific traffic” use case:

* It supports outbound WAN load balancing (weight-based) and failover across multiple WAN interfaces. citeturn0search0  
* It monitors WAN health using repeated tests and can automatically reroute traffic when a WAN loses connectivity. citeturn0search0  
* It supports rules for policy-based routing (for example: “games always use WAN2,” “bulk downloads use WAN1,” “certain destination IPs go via LTE”). citeturn0search0  

This directly aligns with what you want: “use both PPP sessions concurrently in a smart way” and future expansion to USB LTE/Wi‑Fi without rewriting everything.

### SQM/CAKE to fight bufferbloat and keep latency usable under load

Your environment (DSL, low upstream, Lebanon latency sensitivity) is *exactly* where SQM gives a “feels faster” improvement even when raw Mbps doesn’t double.

OpenWrt’s SQM guidance is blunt: SQM exists to control bufferbloat—latency spikes caused by oversized buffers during load—and it recommends CAKE with a simple script for most cases. citeturn0search1turn0search13  
The deeper SQM details emphasize that DSL/ADSL links often use ATM framing and therefore require correct link-layer adaptation; it specifically notes ATM adds overhead per 48-byte frame, which is why the shaper must be told the right overhead. citeturn10search6turn10search9  

Most importantly for your case, OpenWrt’s own SQM “starter” numbers explicitly call out:  
**“DSL of any other type – choose ATM, set overhead 44 (mpu 96)”** (i.e., not VDSL). citeturn10search1  

This is highly relevant because you are on an ADSL2+-style PVC configuration (0/35) and your throughput-vs-sync mismatch may partly be driven by queueing and overhead misestimation.

CAKE itself is widely described as a rollup of SQM deployment experience meant to manage buffering and improve latency under load. citeturn0search5  

## Optional “next level” variant if you want to chase the maximum possible efficiency

Your initial hybrid design (WAN1 behind W9960 + WAN2 bridged PPPoE) is the best low-risk bridge-first move.

But if your real objective becomes “get as close as possible to the true usable DSL payload limit and reduce complexity,” the next logical step is:

### Full bridge and terminate both PPPoE sessions in OpenWrt (single physical WAN, two PPP sessions)

Why it can be better:

* You avoid “router behind router” artifacts (double NAT, two independent queueing domains).
* OpenWrt can become the one place where you do:
  * both PPPoE terminations,
  * policy routing across PPP sessions,
  * SQM/CAKE shaping based on correct DSL overhead assumptions. citeturn10search1turn10search6  

Why it’s riskier:

* You must preserve a management path to the modem (varies by device/firmware).
* Your household LAN would likely need to hang off OpenWrt, not the W9960.

This is the point where some people reach for MPTCP-based solutions—because they can give single-flow improvements—but those **require a remote endpoint** (a VPS) to terminate and reassemble, which conflicts with your “avoid remote latency” constraint unless the VPS is extremely close and well-peered.

OpenMPTCProuter is explicit about its model: it uses MPTCP to aggregate multiple Internet connections and terminates them over a VPS. citeturn3search1turn3search5  
That can be amazing, but it’s a different tradeoff than your preferred “keep it local” plan.

## Validation and bottleneck isolation checklist designed for your exact symptoms

You already proved the key functional point: both PPP sessions can carry traffic concurrently. Now you need to isolate why you’re seeing ~9.6 Mbps aggregate instead of something closer to what sync + overhead would suggest.

### Test methodology that avoids false negatives

A single speedtest site can lie to you (server caps, TCP behavior, peering). Your best approach is a controlled matrix:

Run multi-flow tests while capturing:
* per-WAN byte counters,
* per-WAN latency (under load),
* DSL error counters and retrains.

Then compare:
* single WAN1 only,
* single WAN2 only,
* multi-WAN balanced (mwan3),
* multi-WAN pinned flows (rules).

### MTU/MSS sanity is non‑negotiable on PPPoE  
Treat PPPoE MTU/MSS as a first-class parameter; PPPoE overhead reduces MTU to 1492 and mismatches can cause fragmentation/loss. citeturn0search31turn0search11  

This matters even more if any NIC is set to jumbo frames or if ICMP “fragmentation needed” is filtered somewhere (PMTUD blackhole behavior).

### SQM is your best lever for “better latency without remote tunnels”  
Your upload is ~0.95 Mbps sync. If uploads or ACKs get stuck behind buffers, downloads can collapse and latency spikes. SQM is specifically designed to prevent those queues from running away, and OpenWrt provides concrete DSL/ATM overhead guidance for correct shaping. citeturn10search1turn10search6turn0search13  

### If you still want a Speedify-based LTE experiment, keep expectations aligned  
Speedify can do impressive bonding, but its full channel bonding is fundamentally cloud-server-assisted. citeturn17search4turn17search19  
Its Local Load Balancer mode is useful, but Speedify itself documents that without server connection you don’t get “single socket bonding.” citeturn17search16  

That’s why the OpenWrt VM becomes your “brilliant” core: it gives you multi-WAN control without “Lebanon → remote bond server → Internet” latency tax, while still letting you optionally use Speedify for a *separate* LTE bonding experiment when you decide the latency tradeoff is acceptable.

## Safety and rollback principles for your bridge cutover

Because bridge cutovers can lock you out, the operational rules are simple:

Keep one known-good routed path active on the W9960 until the VM is proven stable. Microsoft also warns that some Hyper‑V network switch operations can disrupt connectivity, so schedule switch creation carefully. citeturn0search2  

Finally, remember you’re using telnet shell access via configuration injection; treat that as a temporary lab tool. Once your OpenWrt VM becomes the “brain,” you can reduce reliance on fragile router-side hacks and keep the W9960 closer to “modem + minimal services,” which is exactly where consumer DSL CPE tends to be most stable.

