"""Wake-on-LAN 工具测试：地址解析、魔包与广播发送。"""
from __future__ import annotations

import unittest
from unittest import mock

from wol import magic_packet, normalize_mac, parse_macs, send_magic_packet


class MacParsingTests(unittest.TestCase):
    def test_normalizes_common_formats(self) -> None:
        self.assertEqual(normalize_mac("AA-BB-CC-DD-EE-FF"), "aa:bb:cc:dd:ee:ff")
        self.assertEqual(normalize_mac("aabb.ccdd.eeff"), "aa:bb:cc:dd:ee:ff")
        self.assertIsNone(normalize_mac("00:00:00:00:00:00"))

    def test_parses_lists_and_separated_strings(self) -> None:
        expected = ["aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"]
        self.assertEqual(parse_macs("aa:bb:cc:dd:ee:ff, 11-22-33-44-55-66"), expected)
        self.assertEqual(parse_macs(expected), expected)


class PacketTests(unittest.TestCase):
    def test_magic_packet_has_sync_and_sixteen_repetitions(self) -> None:
        packet = magic_packet("aa:bb:cc:dd:ee:ff")
        self.assertEqual(len(packet), 102)
        self.assertEqual(packet[:6], b"\xff" * 6)
        self.assertEqual(packet[6:], bytes.fromhex("aabbccddeeff") * 16)

    def test_send_uses_udp_broadcast(self) -> None:
        with mock.patch("wol.broadcast_targets", return_value=["255.255.255.255"]), \
             mock.patch("wol.socket.socket") as socket_class:
            socket_obj = socket_class.return_value.__enter__.return_value
            sent = send_magic_packet("aa:bb:cc:dd:ee:ff", port=9)

        self.assertEqual(sent, 1)
        socket_obj.setsockopt.assert_called_once()
        packet, address = socket_obj.sendto.call_args.args
        self.assertEqual(packet, magic_packet("aa:bb:cc:dd:ee:ff"))
        self.assertEqual(address, ("255.255.255.255", 9))


if __name__ == "__main__":
    unittest.main()
