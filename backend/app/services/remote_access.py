"""Remote access for paired phones (Phase 10.3): TLS certificate and addresses.

Phones connect over HTTPS with one self-signed certificate, pinned by its
SHA-256 fingerprint (sent in the pairing QR), so the same certificate works
for the LAN address, the Tailscale address and the MagicDNS name. It is made
once and kept: a new one would break every paired phone's pin.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.utils.logging import get_logger

logger = get_logger()

_TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")
_TAILSCALE_TIMEOUT_SECONDS = 3
_CERT_YEARS = 10


def cert_paths(data_dir: Path) -> tuple[Path, Path]:
    folder = data_dir / "remote"
    return folder / "cert.pem", folder / "key.pem"


def ensure_certificate(data_dir: Path) -> tuple[Path, Path]:
    """The certificate and key files, created on first use."""
    cert_path, key_path = cert_paths(data_dir)
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Hypatia")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365 * _CERT_YEARS))
        .sign(key, hashes.SHA256())
    )
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    if os.name != "nt":
        key_path.chmod(0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info("remote_certificate_created", fingerprint=fingerprint(cert_path))
    return cert_path, key_path


def fingerprint(cert_path: Path) -> str:
    """SHA-256 of the certificate's DER bytes, as lowercase hex."""
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _usable(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast)


def _interface_addresses() -> list[str]:
    found = []
    # The address the OS would use to reach another network: usually the LAN
    # one. Connecting a UDP socket sends nothing.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed
            found.append(probe.getsockname()[0])
        except OSError:
            pass
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        infos = []
    found += [str(info[4][0]) for info in infos]
    return [a for a in dict.fromkeys(found) if _usable(a)]


def _tailscale_status() -> tuple[list[str], str | None]:
    """Tailscale IPv4 addresses and MagicDNS name from the CLI, if it's installed."""
    cli = shutil.which("tailscale")
    if cli is None:
        return [], None
    try:
        done = subprocess.run(
            [cli, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=_TAILSCALE_TIMEOUT_SECONDS,
            check=True,
        )
        me = json.loads(done.stdout).get("Self") or {}
    except (OSError, subprocess.SubprocessError, ValueError):
        return [], None
    ips = [ip for ip in me.get("TailscaleIPs") or [] if ipaddress.ip_address(ip).version == 4]
    name = (me.get("DNSName") or "").rstrip(".") or None
    return ips, name


def pairing_urls(port: int) -> list[str]:
    """Where a phone can reach this computer, LAN first (fastest), then Tailscale."""
    addresses = _interface_addresses()
    tailscale_ips, magic_dns = _tailscale_status()
    lan = [a for a in addresses if ipaddress.ip_address(a) not in _TAILSCALE_NET]
    tailnet = list(
        dict.fromkeys(
            tailscale_ips + [a for a in addresses if ipaddress.ip_address(a) in _TAILSCALE_NET]
        )
    )
    hosts = lan + tailnet + ([magic_dns] if magic_dns else [])
    return [f"https://{host}:{port}" for host in hosts]
