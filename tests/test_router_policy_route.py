import argparse
import unittest

from router_policy_route import (
    build_tcpmss_delete_commands,
    get_active_ppp_ifs,
    parse_live_ipv4,
    require_ipv4,
)


class RouterPolicyRouteTests(unittest.TestCase):
    def test_require_ipv4_accepts_valid_address(self) -> None:
        self.assertEqual(require_ipv4("192.168.0.60"), "192.168.0.60")

    def test_require_ipv4_rejects_invalid_address(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            require_ipv4("300.168.0.60")

    def test_parse_live_ipv4_extracts_interface_address(self) -> None:
        output = "2: ppp1: <POINTOPOINT>\n    inet 100.64.1.9 peer 10.0.0.1/32 scope global ppp1\n"
        self.assertEqual(parse_live_ipv4(output), "100.64.1.9")

    def test_get_active_ppp_ifs_preserves_first_seen_order(self) -> None:
        route_output = "\n".join(
            [
                "default via 1.1.1.1 dev ppp1",
                "10.0.0.0/24 dev ppp0 proto kernel scope link src 10.0.0.2",
                "192.168.1.0/24 dev ppp1 proto kernel scope link src 192.168.1.2",
                "172.16.0.0/24 dev ppp0 proto kernel scope link src 172.16.0.2",
            ]
        )
        self.assertEqual(get_active_ppp_ifs(route_output), ["ppp1", "ppp0"])

    def test_build_tcpmss_delete_commands_deduplicates_values(self) -> None:
        commands = build_tcpmss_delete_commands("192.168.0.60/32", "ppp1", [1424, 1424, 1412])
        self.assertEqual(
            commands,
            [
                "iptables -D FORWARD -s 192.168.0.60/32 -o ppp1 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1424 2>/dev/null",
                "iptables -D FORWARD -s 192.168.0.60/32 -o ppp1 -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1412 2>/dev/null",
            ],
        )


if __name__ == "__main__":
    unittest.main()
