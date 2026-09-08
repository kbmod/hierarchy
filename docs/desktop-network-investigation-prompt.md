# Desktop network investigation prompt

Paste the following into Codex on the affected desktop:

```text
Investigate severe interactive typing lag from this desktop to my Tailscale VPS at 100.64.0.3.

Context:

- This same VPS was responsive from my phone throughout today, including during the current session.
- This desktop is wired directly to the gateway.
- Another VPS from a different provider is responsive from this same desktop.
- The provider’s browser console for the affected VPS has always been slow, so treat that as baseline rather than new evidence.
- VPS-side checks found the Hierarchy service idle: no connected clients polling port 8765, negligible CPU/RAM, no active routines, and no host resource exhaustion.
- VPS-side diagnostics observed 33–60% loss on the Tailscale path, roughly 299–341 retransmission events, more than 200 out-of-order packets, and repeated switching between a direct UDP path and the IAD DERP relay.
- VPS-side MTU checks did not identify MTU as the primary cause.
- The VPS also receives abnormal DHCP/ARP broadcasts. This is suspicious but has not been proven to cause the desktop-specific lag.

You are running on the affected desktop. Detect the operating system, network interfaces, active VPNs, and available diagnostic tools before testing. Use platform-appropriate commands and explain any unavailable equivalent.

Perform a read-only investigation. Do not restart, disconnect, reconfigure, upgrade, kill, or otherwise change Tailscale, networking, firewall rules, routes, MTU, SSH, the gateway, or other services unless I explicitly authorize it after reviewing your report.

Compare the failing VPS with at least one healthy VPS from this desktop. Use the same protocol, packet size, count, and measurement duration wherever possible. Do not flood the network, run broad port scans, or generate sustained traffic.

Investigate:

- Tailscale version, status, peer details, endpoint, and whether the path is direct or relayed.
- `tailscale ping` and `tailscale netcheck`, including repeated samples over a bounded interval.
- Packet loss, latency, jitter, route stability, and direct/DERP path flapping to 100.64.0.3.
- Equivalent measurements to the healthy VPS.
- TCP/SSH RTT, retransmissions, send/receive queues, congestion behavior, duplicate ACKs, and out-of-order packets.
- Whether ICMP, HTTPS, TCP, and Tailscale traffic are affected equally, or whether the issue is specific to SSH or one transport.
- UDP reachability and whether the direct Tailscale connection is failing while the relay remains stable.
- Safe path-MTU tests using non-fragmenting probes appropriate for this operating system.
- Bounded traceroute/path comparisons, without scanning unrelated hosts.
- Ethernet/Wi-Fi adapter errors, drops, duplex/speed negotiation, CPU, memory, interrupt pressure, and local resource saturation.
- Local VPNs, security software, firewalls, proxies, traffic shapers, power-saving settings, or background processes that could selectively affect this route.
- Recent Tailscale, firewall, and network-manager logs, if available.

If packet capture is useful, capture headers only for a short, clearly bounded interval. Do not capture payloads. Redact or omit authentication tokens, OAuth data, private keys, cookies, passwords, environment variables, full command histories, and other secrets from the report. Do not expose private payloads or upload diagnostics anywhere.

Produce an evidence-backed report containing:

1. The desktop OS, relevant interface, Tailscale version, and exact test time windows.
2. Exact commands or tools used, with sensitive values redacted.
3. Side-by-side results for the failing VPS and healthy VPS.
4. Whether the evidence implicates the desktop, local gateway/NAT, ISP route/peering, Tailscale direct UDP, DERP relay, or VPS provider.
5. Confidence level and the main competing explanations.
6. Safe staged remediation options, explicitly separating reversible desktop-only tests from changes that could interrupt connectivity.
7. The single smallest next diagnostic or remediation step that would best distinguish the leading hypotheses.

Do not make changes yet. Do not conclude that the VPS provider is at fault solely because the phone worked: the phone uses a different peer, NAT mapping, and likely route. Do not conclude that the desktop is at fault solely because another VPS works: compare paths and transports. End with your evidence-backed conclusion and the one smallest next step.
```
