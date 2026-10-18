#!/usr/bin/env python3
"""Rebuild the flat APT indexes from every .deb in ./debs."""

import gzip
import hashlib
import io
import tarfile
from datetime import datetime, timezone
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEBS = ROOT / "debs"
DEPICTION = "https://madramdesign.github.io/repo/depiction.json"


def deb_control(path: Path):
    raw = path.read_bytes()
    if not raw.startswith(b"!<arch>\n"):
        raise SystemExit(f"{path.name} is not an ar archive")
    offset = 8
    members = {}
    while offset + 60 <= len(raw):
        header = raw[offset : offset + 60]
        name = header[:16].decode().strip()
        size = int(header[48:58].decode().strip() or "0")
        data = raw[offset + 60 : offset + 60 + size]
        members[name] = data
        offset += 60 + size
        if offset % 2:
            offset += 1
    control = members.get("control.tar.gz") or members.get("control.tar.xz")
    if control is None:
        raise SystemExit(f"{path.name} has no control archive")
    if control.startswith(b"\xfd7zXZ"):
        import lzma

        blob = lzma.decompress(control)
    else:
        blob = gzip.decompress(control)
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tar:
        member = tar.extractfile("./control") or tar.extractfile("control")
        if member is None:
            raise SystemExit(f"{path.name} control archive has no control file")
        return BytesParser().parsebytes(member.read())


def stanza(path: Path) -> str:
    control = deb_control(path)
    payload = path.read_bytes()
    lines = []
    for key in (
        "Package",
        "Name",
        "Version",
        "Architecture",
        "Maintainer",
        "Author",
        "Section",
        "Depends",
        "Description",
    ):
        value = control.get(key)
        if value:
            lines.append(f"{key}: {value}")
    lines.append(f"Filename: ./debs/{path.name}")
    lines.append(f"Size: {len(payload)}")
    lines.append(f"MD5sum: {hashlib.md5(payload).hexdigest()}")
    lines.append(f"SHA1: {hashlib.sha1(payload).hexdigest()}")
    lines.append(f"SHA256: {hashlib.sha256(payload).hexdigest()}")
    lines.append(f"SileoDepiction: {DEPICTION}")
    return "\n".join(lines)


def digest_block(title: str, files: list[tuple[str, bytes]]) -> str:
    rows = [title]
    for name, data in files:
        if title == "MD5Sum:":
            digest = hashlib.md5(data).hexdigest()
        elif title == "SHA1:":
            digest = hashlib.sha1(data).hexdigest()
        else:
            digest = hashlib.sha256(data).hexdigest()
        rows.append(f" {digest} {len(data)} {name}")
    return "\n".join(rows)


def main() -> None:
    debs = sorted(DEBS.glob("*.deb"))
    if not debs:
        raise SystemExit("debs/ is empty")
    packages = "\n\n".join(stanza(path) for path in debs) + "\n"
    encoded = packages.encode()
    gz = gzip.compress(encoded)
    bz = __import__("bz2").compress(encoded)
    (ROOT / "Packages").write_bytes(encoded)
    (ROOT / "Packages.gz").write_bytes(gz)
    (ROOT / "Packages.bz2").write_bytes(bz)
    files = [
        ("Packages", encoded),
        ("Packages.gz", gz),
        ("Packages.bz2", bz),
    ]
    stamp = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    release = "\n".join(
        [
            "Origin: repo",
            "Label: repo",
            "Suite: stable",
            "Version: 1.0",
            "Codename: ios",
            "Architectures: iphoneos-arm64e",
            "Components: main",
            "Description: Sileo package source.",
            f"Date: {stamp}",
            digest_block("MD5Sum:", files),
            digest_block("SHA1:", files),
            digest_block("SHA256:", files),
            "",
        ]
    )
    (ROOT / "Release").write_text(release)
    print(f"indexed {len(debs)} package(s)")


if __name__ == "__main__":
    main()
