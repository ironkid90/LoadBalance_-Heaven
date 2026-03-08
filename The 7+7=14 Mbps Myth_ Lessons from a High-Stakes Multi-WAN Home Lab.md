### The 7+7=14 Mbps Myth: Lessons from a High-Stakes Multi-WAN Home Lab

#### 1\. Introduction: The Quest for the Last Megabit

In regions where digital infrastructure is defined by scarcity rather than abundance—specifically in Lebanon—optimizing a home network isn't just a hobby; it’s an engineering necessity. When your gateway to the world is a single copper telephone line that syncs at 16.2 Mbps, but your ISP provides two separate 7 Mbps PPPoE accounts on that same pair, the "mad scientist" urge to merge them becomes irresistible.The goal was simple: aggregate two logical tunnels to create a single, high-performance pipe. But as any network architect will tell you, the distance between theoretical math and real-world throughput is often filled with technical "gotchas." From bypassing restricted consumer firmware via shell injections—specifically using the telnetd \-p 1023 \-l /bin/sh description injection on a TP-Link W9960—to battling physical link bottlenecks, this journey was a masterclass in the "physical vs. logical" reality of networking.

#### 2\. Takeaway 1: Why Your Two ISP Accounts are Competing, Not Combining

The primary fallacy of the "7+7=14" theory is the assumption that multiple logical sessions create multiple physical paths. In this lab, the physical VDSL link reported a sync rate of 16.2 Mbps down and 0.95 Mbps up. While the ISP allowed two concurrent PPPoE sessions (ppp0 and ppp1), both sessions were forced to share that single 16.2 Mbps physical ceiling.In practice, aggregate throughput hit a hard wall at approximately 9.6 Mbps. While DSL overhead is a factor, the real bottleneck was PTM (Packet Transfer Mode) framing and ISP-side constraints. Because both accounts compete for the same physical cycles on the wire, they aren't expanding the pipe; they are just two different logical doors opening into the same narrow hallway."According to the lab's diagnostic logs, PPPoE adds 8 bytes of overhead per packet (6-byte PPPoE header \+ 2-byte PPP protocol ID), which reduces the effective Maximum Transmission Unit (MTU) from the standard 1500 bytes to 1492."

#### 3\. Takeaway 2: The Windows NIC Teaming (LBFO) Trap

Many enthusiasts attempt to use Windows NIC Teaming (Load Balancing and Failover, or LBFO) as a quick fix for aggregation. For a multi-WAN home lab, this is fundamentally the wrong tool.

* **Layer Mismatch:**  LBFO is a  **Layer 2**  technology designed for redundancy between a host and a single switch on the same broadcast network.  
* **Routing Blindness:**  Multi-WAN bonding is a  **Layer 3/4**  challenge. LBFO fails here because it cannot manage  **distinct public IPs and different NAT states**  across separate gateways. It expects a single logical uplink, not two independent ISP paths.  
* **OS Constraints:**  Microsoft explicitly restricts LBFO to Windows Server versions. It is unsupported on Windows 10 and 11, and forcing it usually results in ARP conflicts and broken routing.

#### 4\. Takeaway 3: Speedify’s "Hidden" Latency Tax

Speedify is often touted as a silver bullet, but in high-latency environments, its "Cloud Bonding" comes at a cost. The lab discovered that geography is destiny: for a user in Lebanon, connecting to a server in  **Thessaloniki (Greece)**  was 3x faster than the Istanbul server, despite the latter's proximity.Furthermore, true bonding—where a single file download is split across links—requires a remote server to reassemble the packets, which adds a significant "latency tax.""As noted in the architectural findings, packet-level channel bonding requires packets be split across links and reassembled at a remote server."Without that remote server (Speedify’s "Local Proxy" mode), the system can only distribute multiple concurrent sockets (like a multi-threaded download manager) across links; it cannot bond a single-socket TCP stream.

#### 5\. Takeaway 4: The "God-Tier" Solution—Virtualizing the Edge

The most brilliant path forward was moving the network’s "brain" away from the modem and into a "Bridge \+ OpenWrt VM" architecture. However, an architect’s warning: a single-NIC setup is a recipe for complexity. To isolate bridged PPPoE traffic, the host  **requires a second physical NIC**  (such as a USB 3.0 to Gigabit Ethernet adapter).**The Lab Configuration:**

1. **Modem Demotion:**  Convert the secondary PPPoE session on the W9960 to "Bridge Mode," binding it to a dedicated physical LAN port.  
2. **Hyper-V Brain:**  Host an OpenWrt VM on Windows. Use an  **External Virtual Switch**  in Hyper-V to bind the OpenWrt VM directly to the bridged physical port.  
3. **Direct Pass-through:**  This mechanism allows the VM to "talk" directly to the ISP’s access concentrator, bypassing the Windows TCP/IP stack entirely.This gives the architect full control over PPPoE termination, advanced health checks (mwan3), and smart queuing without relying on a remote VPN.

#### 6\. Takeaway 5: The Invisible Bottleneck—Bufferbloat and 1 Mbps Uploads

In high-latency, low-bandwidth regions, raw download speed matters less than "snappiness." This is governed by Bufferbloat—latency spikes caused by hardware buffers filling up. The solution is Smart Queue Management (SQM) using the  **Cake**  algorithm.To prevent the modem's hardware buffers from engaging, the shaper must account for specific link-layer overhead.

* **The 34-Byte Rule:**  On a VDSL link with PPPoE, the overhead must be set to exactly  **34 bytes**  to account for  **PTM (Packet Transfer Mode)**  framing. This is distinct from the 44-byte setting used for legacy ADSL/ATM links.One critical "gotcha" found in the lab: a Realtek 2.5GbE NIC was found negotiating at only  **100 Mbps**  with a suspicious  **9014-byte Jumbo Frame**  setting. This conflict can cause non-optimal MTU behavior that throttles the very link you are trying to optimize.

#### 7\. Conclusion: The Future of the Local Edge

Mastering a constrained environment like Lebanon’s requires more than just high-end software; it requires absolute control over the network's "brain." Virtualizing the edge with OpenWrt and Hyper-V provides the stability and latency management that off-the-shelf consumer modems simply cannot.For those looking toward the "God-tier" endgame, the future lies in repurposing  **cryptocurrency mining motherboards** . These boards are ideal for high-end networking because of their  **abundance of PCIe slots** . By using PCIe risers, you can add enterprise-grade  **Intel i350-T4 quad-port NICs** , turning a cheap board into a formidable edge router capable of managing multiple ISP paths with surgical precision.As an architect, the question remains: are you content with a single-box solution, or do you demand the absolute control required to master every megabit on the wire? For the true high-performance engineer, the answer is always the latter.  
