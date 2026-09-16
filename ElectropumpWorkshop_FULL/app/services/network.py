"""LAN address discovery — the IP is never hardcoded (requirement 7)."""
from __future__ import annotations

import socket


def primary_lan_ip() -> str:
    """The address this machine would use to reach the network.

    A UDP socket to an off-net address is used because it makes the OS pick a
    route without sending a packet, which works offline and does not depend on
    the hostname being resolvable.
    """
    for probe in ("10.255.255.255", "8.8.8.8", "192.168.1.1"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.4)
        try:
            sock.connect((probe, 1))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            continue
        finally:
            sock.close()
    return "127.0.0.1"


def lan_addresses() -> list[str]:
    """Every non-loopback IPv4 address, primary first."""
    found = []
    primary = primary_lan_ip()
    if primary != "127.0.0.1":
        found.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found or ["127.0.0.1"]


def port_is_free(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("" if host == "0.0.0.0" else host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def port_reachable(ip: str, port: int, timeout: float = 0.6) -> bool:
    """Can the server be reached on its own LAN address? (firewall hint)"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False
    finally:
        sock.close()
