#!/usr/bin/env python3

import argparse
import re
import socket
import sys
import time
from typing import Optional

IAC = 255
DO = 253
DONT = 254
WILL = 251
WONT = 252
SB = 250
SE = 240
PROMPT_RE = re.compile(r"~ # ?$", re.M)
MTU_RE = re.compile(r"\bmtu\s+(\d+)\b")
LIVE_INET_RE = re.compile(r"\binet\s+(\d+\.\d+\.\d+\.\d+)(?:/\d+)?\b")
TCPMSS_RULE_RE = r"-A FORWARD -o {iface} -p tcp .* --set-mss (\d+)"
SOURCE_TCPMSS_RULE_RE = (
    r"-A FORWARD -s {cidr} -o {iface} -p tcp -m tcp --tcp-flags SYN,RST SYN "
    r"-j TCPMSS --set-mss (\d+)"
)
DEFAULT_PPP_RE = re.compile(r"^default via \S+ dev (ppp\d+)\b", re.M)
PPP_IF_RE = re.compile(r"\bdev (ppp\d+)\b")
SOURCE_NAT_IF_RE = r"-A POSTROUTING -s {cidr} -o (ppp\d+) -j MASQUERADE"
TABLE_DEFAULT_IF_RE = re.compile(r"^default dev (ppp\d+)\b", re.M)


class RouterShell:
    def __init__(self, host: str, port: int, timeout: float = 10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(0.5)
        self.buffer = ""

    def close(self) -> None:
        self.sock.close()

    def _pump(self, duration: float = 0.2) -> str:
        end = time.time() + duration
        collected = []
        while time.time() < end:
            try:
                data = self.sock.recv(4096)
            except TimeoutError:
                continue
            if not data:
                break
            out = bytearray()
            i = 0
            while i < len(data):
                b = data[i]
                if b == IAC and i + 1 < len(data):
                    cmd = data[i + 1]
                    if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                        opt = data[i + 2]
                        if cmd in (DO, DONT):
                            self.sock.sendall(bytes([IAC, WONT, opt]))
                        else:
                            self.sock.sendall(bytes([IAC, DONT, opt]))
                        i += 3
                        continue
                    if cmd == SB:
                        i += 2
                        while i < len(data) - 1:
                            if data[i] == IAC and data[i + 1] == SE:
                                i += 2
                                break
                            i += 1
                        continue
                    i += 2
                    continue
                out.append(b)
                i += 1
            if out:
                collected.append(out.decode("utf-8", "ignore"))
        chunk = "".join(collected)
        self.buffer += chunk
        return chunk

    def read_until_prompt(self, timeout: float = 8.0) -> str:
        end = time.time() + timeout
        while time.time() < end:
            self._pump(0.3)
            if PROMPT_RE.search(self.buffer.replace("\r", "")):
                return self.buffer
        return self.buffer

    def run(self, command: str, timeout: float = 8.0) -> str:
        self.buffer = ""
        self.sock.sendall(command.encode("ascii") + b"\n")
        time.sleep(0.1)
        output = self.read_until_prompt(timeout)
        return output.replace("\r", "")


def require_ipv4(text: str) -> str:
    pattern = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
    if not pattern.match(text):
        raise argparse.ArgumentTypeError(f"invalid IPv4 address: {text}")
    octets = [int(x) for x in text.split(".")]
    if any(x < 0 or x > 255 for x in octets):
        raise argparse.ArgumentTypeError(f"invalid IPv4 address: {text}")
    return text


def parse_live_ipv4(ip_addr_output: str) -> Optional[str]:
    match = LIVE_INET_RE.search(ip_addr_output)
    if not match:
        return None
    return match.group(1)


def is_live_ppp_address(ipv4: Optional[str]) -> bool:
    if not ipv4:
        return False
    return not ipv4.startswith("169.254.")


def detect_mss(shell: RouterShell, ppp_if: str) -> int:
    rules = shell.run("iptables -S FORWARD", 8.0)
    rule_re = re.compile(TCPMSS_RULE_RE.format(iface=re.escape(ppp_if)))
    match = rule_re.search(rules)
    if match:
        return int(match.group(1))

    ip_addr = shell.run(f"ip addr show {ppp_if}", 8.0)
    mtu_match = MTU_RE.search(ip_addr)
    if mtu_match:
        return int(mtu_match.group(1)) - 40

    return 1424


def get_route_output(shell: RouterShell) -> str:
    return shell.run("ip route", 8.0)


def get_default_ppp_if(route_output: str) -> Optional[str]:
    match = DEFAULT_PPP_RE.search(route_output)
    if not match:
        return None
    return match.group(1)


def get_active_ppp_ifs(route_output: str) -> list[str]:
    seen: set[str] = set()
    active: list[str] = []
    for ppp_if in PPP_IF_RE.findall(route_output):
        if ppp_if in seen:
            continue
        seen.add(ppp_if)
        active.append(ppp_if)
    return active


def resolve_apply_ppp_if(shell: RouterShell, requested_ppp_if: str) -> tuple[str, Optional[str]]:
    if requested_ppp_if != "auto":
        return requested_ppp_if, None

    route_output = get_route_output(shell)
    default_ppp_if = get_default_ppp_if(route_output)
    active_ppp_ifs = get_active_ppp_ifs(route_output)

    if not default_ppp_if:
        raise RuntimeError("router has no default PPP route right now")

    alternate_ppp_ifs = [ppp_if for ppp_if in active_ppp_ifs if ppp_if != default_ppp_if]
    if not alternate_ppp_ifs:
        raise RuntimeError(
            f"router default is {default_ppp_if}, but no second active PPP interface is available"
        )

    return alternate_ppp_ifs[0], default_ppp_if


def resolve_remove_ppp_ifs(
    shell: RouterShell, requested_ppp_if: str, target_cidr: str, table: int
) -> list[str]:
    if requested_ppp_if != "auto":
        return [requested_ppp_if]

    nat_output = shell.run("iptables -t nat -S POSTROUTING", 8.0)
    nat_re = re.compile(SOURCE_NAT_IF_RE.format(cidr=re.escape(target_cidr)))
    matches = nat_re.findall(nat_output)
    if matches:
        return list(dict.fromkeys(matches))

    table_output = shell.run(f"ip route show table {table}", 8.0)
    match = TABLE_DEFAULT_IF_RE.search(table_output)
    if match:
        return [match.group(1)]

    return ["ppp0", "ppp1"]


def find_source_specific_mss(shell: RouterShell, target_cidr: str, ppp_if: str) -> list[int]:
    rules = shell.run("iptables -S FORWARD", 8.0)
    rule_re = re.compile(
        SOURCE_TCPMSS_RULE_RE.format(cidr=re.escape(target_cidr), iface=re.escape(ppp_if))
    )
    return [int(value) for value in rule_re.findall(rules)]


def build_tcpmss_delete_commands(target_cidr: str, ppp_if: str, mss_values: list[int]) -> list[str]:
    commands: list[str] = []
    seen: set[int] = set()
    for mss in mss_values:
        if mss in seen:
            continue
        seen.add(mss)
        commands.append(
            f"iptables -D FORWARD -s {target_cidr} -o {ppp_if} -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss {mss} 2>/dev/null"
        )
    return commands


def build_apply_commands(
    target_ip: str, table: int, priority: int, ppp_if: str, mss: int, stale_mss_values: list[int]
) -> list[str]:
    target_cidr = f"{target_ip}/32"
    return [
        f"ip rule del from {target_cidr} table {table} priority {priority} 2>/dev/null",
        f"ip route del default table {table} 2>/dev/null",
        f"ip route add default dev {ppp_if} table {table}",
        f"ip rule add from {target_cidr} table {table} priority {priority}",
        f"iptables -t nat -D POSTROUTING -s {target_cidr} -o {ppp_if} -j MASQUERADE 2>/dev/null",
        f"iptables -t nat -I POSTROUTING 1 -s {target_cidr} -o {ppp_if} -j MASQUERADE",
        *build_tcpmss_delete_commands(target_cidr, ppp_if, stale_mss_values + [mss]),
        f"iptables -I FORWARD 1 -s {target_cidr} -o {ppp_if} -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss {mss}",
    ]


def build_remove_commands(
    target_ip: str, table: int, priority: int, ppp_if: str, stale_mss_values: list[int]
) -> list[str]:
    target_cidr = f"{target_ip}/32"
    return [
        f"ip rule del from {target_cidr} table {table} priority {priority} 2>/dev/null",
        f"ip route del default table {table} 2>/dev/null",
        f"iptables -t nat -D POSTROUTING -s {target_cidr} -o {ppp_if} -j MASQUERADE 2>/dev/null",
        *build_tcpmss_delete_commands(target_cidr, ppp_if, stale_mss_values),
    ]


def build_status_commands(table: int, ppp_if: str) -> list[str]:
    ppp_commands = (
        ["ip addr show ppp0", "ip addr show ppp1"]
        if ppp_if == "auto"
        else [f"ip addr show {ppp_if}"]
    )
    return [
        "cat /proc/net/pppoe 2>/dev/null",
        *ppp_commands,
        "ip rule",
        f"ip route show table {table}",
        "ip route",
        "iptables -t nat -S POSTROUTING",
        "iptables -S FORWARD",
        "cat /proc/net/arp",
    ]


def build_ensure_commands(
    target_ip: str, table: int, priority: int, ppp_if: str, mss: int
) -> list[str]:
    target_cidr = f"{target_ip}/32"
    remove_ppp_ifs = ["ppp0", "ppp1"] if ppp_if == "auto" else [ppp_if]
    commands: list[str] = []
    for remove_ppp_if in remove_ppp_ifs:
        commands.extend(build_remove_commands(target_ip, table, priority, remove_ppp_if, [mss]))
    if ppp_if == "auto":
        commands.append(
            f"# ensure mode will auto-select the non-default live PPP interface for {target_cidr}"
        )
        return commands
    commands.extend(build_apply_commands(target_ip, table, priority, ppp_if, mss, []))
    return commands


def print_command_output(command: str, output: str) -> None:
    print(f"===== {command} =====")
    print(output.rstrip())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply, repair, or remove host-specific policy routing on the TP-Link shell."
    )
    parser.add_argument("mode", choices=["status", "apply", "ensure", "remove"])
    parser.add_argument("--router", default="192.168.0.1")
    parser.add_argument("--port", type=int, default=1023)
    parser.add_argument("--target-ip", type=require_ipv4)
    parser.add_argument("--table", type=int, default=100)
    parser.add_argument("--priority", type=int, default=100)
    parser.add_argument("--ppp-if", default="auto")
    parser.add_argument("--mss", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.mode in {"apply", "ensure", "remove"} and not args.target_ip:
        parser.error("--target-ip is required for apply/ensure/remove")

    if args.dry_run:
        if args.mode == "status":
            commands = build_status_commands(args.table, args.ppp_if)
        elif args.mode == "apply":
            commands = build_apply_commands(
                args.target_ip, args.table, args.priority, args.ppp_if, args.mss or 1424, []
            )
        elif args.mode == "ensure":
            commands = build_ensure_commands(
                args.target_ip, args.table, args.priority, args.ppp_if, args.mss or 1424
            )
        else:
            commands = build_remove_commands(
                args.target_ip, args.table, args.priority, args.ppp_if, [args.mss or 1424]
            )
        for command in commands:
            print(command)
        return 0

    try:
        shell = RouterShell(args.router, args.port)
        shell.read_until_prompt(2.0)
        if args.mode == "apply":
            resolved_ppp_if, default_ppp_if = resolve_apply_ppp_if(shell, args.ppp_if)
            if args.ppp_if == "auto":
                print(f"auto-selected {resolved_ppp_if} (router default is {default_ppp_if})")
            ip_addr_output = shell.run(f"ip addr show {resolved_ppp_if}", 8.0)
            ipv4 = parse_live_ipv4(ip_addr_output)
            if not is_live_ppp_address(ipv4):
                print(
                    f"{resolved_ppp_if} is not ready for routing; current IPv4 is {ipv4 or 'missing'}",
                    file=sys.stderr,
                )
                shell.close()
                return 2
            target_cidr = f"{args.target_ip}/32"
            stale_mss_values = find_source_specific_mss(shell, target_cidr, resolved_ppp_if)
            if args.mss is None:
                args.mss = detect_mss(shell, resolved_ppp_if)
            commands = build_apply_commands(
                args.target_ip,
                args.table,
                args.priority,
                resolved_ppp_if,
                args.mss,
                stale_mss_values,
            )
        elif args.mode == "ensure":
            resolved_ppp_if, default_ppp_if = resolve_apply_ppp_if(shell, args.ppp_if)
            if args.ppp_if == "auto":
                print(f"auto-selected {resolved_ppp_if} (router default is {default_ppp_if})")
            ip_addr_output = shell.run(f"ip addr show {resolved_ppp_if}", 8.0)
            ipv4 = parse_live_ipv4(ip_addr_output)
            if not is_live_ppp_address(ipv4):
                print(
                    f"{resolved_ppp_if} is not ready for routing; current IPv4 is {ipv4 or 'missing'}",
                    file=sys.stderr,
                )
                shell.close()
                return 2
            if args.mss is None:
                args.mss = detect_mss(shell, resolved_ppp_if)
            target_cidr = f"{args.target_ip}/32"
            remove_ppp_ifs = resolve_remove_ppp_ifs(shell, args.ppp_if, target_cidr, args.table)
            commands = []
            for remove_ppp_if in remove_ppp_ifs:
                stale_mss_values = find_source_specific_mss(shell, target_cidr, remove_ppp_if)
                if not stale_mss_values:
                    stale_mss_values = [args.mss]
                commands.extend(
                    build_remove_commands(
                        args.target_ip, args.table, args.priority, remove_ppp_if, stale_mss_values
                    )
                )
            commands.extend(
                build_apply_commands(
                    args.target_ip,
                    args.table,
                    args.priority,
                    resolved_ppp_if,
                    args.mss,
                    [],
                )
            )
        elif args.mode == "remove":
            target_cidr = f"{args.target_ip}/32"
            resolved_ppp_ifs = resolve_remove_ppp_ifs(shell, args.ppp_if, target_cidr, args.table)
            commands = []
            for resolved_ppp_if in resolved_ppp_ifs:
                stale_mss_values = find_source_specific_mss(shell, target_cidr, resolved_ppp_if)
                if args.mss is not None:
                    stale_mss_values.append(args.mss)
                if not stale_mss_values:
                    stale_mss_values = [1424]
                commands.extend(
                    build_remove_commands(
                        args.target_ip, args.table, args.priority, resolved_ppp_if, stale_mss_values
                    )
                )
        else:
            commands = build_status_commands(args.table, args.ppp_if)
        for command in commands:
            output = shell.run(command, 10.0)
            print_command_output(command, output)
        shell.close()
    except OSError as exc:
        print(f"router connection failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
