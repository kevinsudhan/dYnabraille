"""LAN plumbing: local HTTPS certificates (iOS needs HTTPS for the camera) and mDNS."""
from __future__ import annotations

import datetime as dt
import ipaddress
import json
import logging
import socket
from pathlib import Path

from .settings import DATA_DIR

log = logging.getLogger(__name__)
CERT_DIR = DATA_DIR / "certs"


def lan_addresses() -> list[str]:
    """IPv4 addresses other devices on the network can reach us at, best first."""
    found: list[str] = []
    try:  # the interface that holds the default route
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    ordered = []
    for ip in found:
        if ip not in ordered and not ip.startswith(("127.", "169.254.")):
            ordered.append(ip)
    return ordered


# ---------------------------------------------------------------------- certificates

def _names(hostname: str) -> tuple[list[str], list[str]]:
    dns = sorted({"localhost", f"{hostname}.local", socket.gethostname(),
                  f"{socket.gethostname()}.local"})
    ips = sorted({"127.0.0.1", *lan_addresses()})
    return dns, ips


def ensure_certificates(hostname: str) -> tuple[Path, Path, Path]:
    """Create (once) a local CA and (whenever our addresses change) a server cert.

    Returns (ca_cert, server_cert, server_key) paths. Install ca.crt on the iPhone
    once and every later server certificate is trusted automatically.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    ca_cert_path, ca_key_path = CERT_DIR / "ca.pem", CERT_DIR / "ca-key.pem"
    cert_path, key_path = CERT_DIR / "server.pem", CERT_DIR / "server-key.pem"
    names_path = CERT_DIR / "server-names.json"
    now = dt.datetime.now(dt.timezone.utc)

    if ca_cert_path.exists() and ca_key_path.exists():
        ca_cert = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), None)
    else:
        ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"DynaBraille Local CA ({socket.gethostname()})"),
                          x509.NameAttribute(NameOID.ORGANIZATION_NAME, "DynaBraille")])
        ca_cert = (
            x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False,
                                         data_encipherment=False, key_agreement=False,
                                         encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        ca_key_path.write_bytes(ca_key.private_bytes(serialization.Encoding.PEM,
                                                     serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
        ca_cert_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
        cert_path.unlink(missing_ok=True)
        log.info("created local certificate authority %s", ca_cert_path)

    dns, ips = _names(hostname)
    wanted = {"dns": dns, "ips": ips}
    current = json.loads(names_path.read_text()) if names_path.exists() else None
    expiring = False
    if cert_path.exists():
        existing = x509.load_pem_x509_certificate(cert_path.read_bytes())
        expiring = existing.not_valid_after_utc - now < dt.timedelta(days=30)
    if cert_path.exists() and key_path.exists() and current == wanted and not expiring:
        return ca_cert_path, cert_path, key_path

    key = ec.generate_private_key(ec.SECP256R1())
    san = [x509.DNSName(n) for n in dns] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{hostname}.local")]))
        .issuer_name(ca_cert.subject).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        # iOS rejects TLS server certificates valid for more than 825 days.
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=397))
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    names_path.write_text(json.dumps(wanted))
    log.info("issued HTTPS certificate for %s", ", ".join(dns + ips))
    return ca_cert_path, cert_path, key_path


def ca_der(ca_cert_path: Path) -> bytes:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    return x509.load_pem_x509_certificate(ca_cert_path.read_bytes()).public_bytes(serialization.Encoding.DER)


# ---------------------------------------------------------------------- mDNS

class Advertiser:
    """Announces _dynabraille._tcp (for the ESP32) and <hostname>.local (for the iPhone)."""

    def __init__(self, hostname: str, http_port: int, https_port: int):
        self.hostname, self.http_port, self.https_port = hostname, http_port, https_port
        self._zc = None

    async def start(self) -> None:
        from zeroconf import IPVersion
        from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

        # Only the default-route address: virtual adapters (VirtualBox, WSL, VPNs) are
        # unreachable from the ESP32, and it simply takes the first address it hears.
        addresses = lan_addresses()[:1]
        if not addresses:
            log.warning("no LAN address found; mDNS disabled")
            return
        self._info = AsyncServiceInfo(
            "_dynabraille._tcp.local.",
            f"DynaBraille on {socket.gethostname()}._dynabraille._tcp.local.",
            port=self.http_port,
            properties={"https": str(self.https_port), "path": "/ws/device"},
            server=f"{self.hostname}.local.",
            parsed_addresses=addresses,
        )
        self._zc = AsyncZeroconf(ip_version=IPVersion.V4Only)
        try:
            await self._zc.async_register_service(self._info, allow_name_change=True)
            log.info("mDNS: %s.local -> %s", self.hostname, ", ".join(addresses))
        except Exception as exc:
            log.warning("mDNS registration failed: %s", exc)

    async def stop(self) -> None:
        if self._zc:
            try:
                await self._zc.async_unregister_all_services()
            finally:
                await self._zc.async_close()
