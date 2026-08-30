#!/usr/bin/env python3
"""표준 라이브러리만 사용하는 마이그레이션 아카이브 암호화 provider.

포맷은 버전이 지정된 encrypt-then-MAC envelope입니다. 외부 key-file의
내용은 아카이브에 기록하지 않으며, 평문은 스트리밍 처리합니다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path
from typing import BinaryIO, Mapping

MAGIC = b"AISERVICE-MIGRATION-ARCHIVE-V1\n"
ALGORITHM = "HMAC-SHA256-STREAM-V1"
KDF = "PBKDF2-HMAC-SHA256"
PBKDF2_ITERATIONS = 600_000
CHUNK_SIZE = 1024 * 1024
TAG_SIZE = hashlib.sha256().digest_size


def _require_key(key: bytes) -> bytes:
    if not key:
        raise ValueError("암호화 키가 비어 있습니다")
    return key


def load_key_file(
    key_file: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> bytes:
    """외부 key-file을 읽습니다. 키 값은 로그나 예외 메시지에 포함하지 않습니다."""
    values = environ if environ is not None else os.environ
    raw_path = str(key_file or values.get("MIGRATION_PACK_KEY_FILE", "")).strip()
    if not raw_path:
        raise ValueError("MIGRATION_PACK_KEY_FILE 또는 --key-file이 필요합니다")
    path = Path(raw_path)
    try:
        key = path.read_bytes().strip()
    except OSError as exc:
        raise ValueError(f"암호화 키 파일을 읽을 수 없습니다: {path}") from exc
    return _require_key(key)


def _derive_keys(key: bytes, salt: bytes) -> tuple[bytes, bytes]:
    material = hashlib.pbkdf2_hmac(
        "sha256", _require_key(key), salt, PBKDF2_ITERATIONS, dklen=64
    )
    return material[:32], material[32:]


def _xor_stream(stream: BinaryIO, output: BinaryIO, enc_key: bytes, nonce: bytes, size: int) -> hmac.HMAC:
    mac = hmac.new(b"", digestmod=hashlib.sha256)
    counter = 0
    remaining = size
    while remaining:
        chunk = stream.read(min(CHUNK_SIZE, remaining))
        if not chunk:
            raise ValueError("암호화 payload가 예상보다 짧습니다")
        encrypted = bytearray()
        offset = 0
        while offset < len(chunk):
            block = hmac.new(
                enc_key,
                nonce + counter.to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()
            part = chunk[offset : offset + len(block)]
            encrypted.extend(a ^ b for a, b in zip(part, block))
            offset += len(part)
            counter += 1
        cipher_chunk = bytes(encrypted)
        output.write(cipher_chunk)
        mac.update(cipher_chunk)
        remaining -= len(chunk)
    return mac


def encrypt_file(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    key: bytes,
) -> Path:
    """파일을 versioned encrypted envelope으로 스트리밍 암호화합니다."""
    source = Path(source_path)
    output = Path(output_path)
    if not source.is_file():
        raise ValueError(f"암호화 대상이 없습니다: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(16)
    nonce = os.urandom(16)
    enc_key, mac_key = _derive_keys(key, salt)
    header = {
        "version": 1,
        "algorithm": ALGORITHM,
        "kdf": KDF,
        "iterations": PBKDF2_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "plaintext_size": source.stat().st_size,
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    with source.open("rb") as stream, output.open("wb") as encrypted:
        encrypted.write(MAGIC)
        encrypted.write(header_bytes + b"\n")
        mac = _xor_stream(stream, encrypted, enc_key, nonce, header["plaintext_size"])
        tag = hmac.new(mac_key, header_bytes + b"\n" + mac.digest(), hashlib.sha256).digest()
        encrypted.write(tag)
    return output


def _read_envelope_header(stream: BinaryIO) -> tuple[dict[str, object], bytes]:
    if stream.read(len(MAGIC)) != MAGIC:
        raise ValueError("지원하지 않는 암호화 아카이브 형식입니다")
    raw_header = stream.readline()
    if not raw_header.endswith(b"\n"):
        raise ValueError("암호화 아카이브 header가 손상되었습니다")
    try:
        header = json.loads(raw_header[:-1].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("암호화 아카이브 header를 해석할 수 없습니다") from exc
    if not isinstance(header, dict) or header.get("version") != 1:
        raise ValueError("지원하지 않는 암호화 envelope 버전입니다")
    if header.get("algorithm") != ALGORITHM or header.get("kdf") != KDF:
        raise ValueError("지원하지 않는 암호화 알고리즘입니다")
    size = header.get("plaintext_size")
    if not isinstance(size, int) or size < 0:
        raise ValueError("잘못된 plaintext 크기입니다")
    try:
        salt = base64.b64decode(str(header["salt"]), validate=True)
        nonce = base64.b64decode(str(header["nonce"]), validate=True)
    except (KeyError, ValueError) as exc:
        raise ValueError("잘못된 암호화 envelope nonce/salt입니다") from exc
    if len(salt) != 16 or len(nonce) != 16:
        raise ValueError("잘못된 암호화 envelope nonce/salt 크기입니다")
    return header, raw_header


def decrypt_file(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    key: bytes,
) -> Path:
    """인증 검증 후 파일을 원자적으로 복호화합니다."""
    source = Path(source_path)
    output = Path(output_path)
    if not source.is_file():
        raise ValueError(f"복호화 대상이 없습니다: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with source.open("rb") as encrypted:
            header, raw_header = _read_envelope_header(encrypted)
            size = int(header["plaintext_size"])
            salt = base64.b64decode(str(header["salt"]), validate=True)
            nonce = base64.b64decode(str(header["nonce"]), validate=True)
            enc_key, mac_key = _derive_keys(key, salt)
            expected_payload = len(MAGIC) + len(raw_header) + size + TAG_SIZE
            if source.stat().st_size != expected_payload:
                raise ValueError("암호화 아카이브 크기가 header와 일치하지 않습니다")
            temporary_file = tempfile.NamedTemporaryFile(
                mode="wb", delete=False, dir=output.parent, prefix=f".{output.name}."
            )
            temporary = Path(temporary_file.name)
            with temporary_file:
                mac = hmac.new(b"", digestmod=hashlib.sha256)
                remaining = size
                counter = 0
                while remaining:
                    cipher_chunk = encrypted.read(min(CHUNK_SIZE, remaining))
                    if not cipher_chunk:
                        raise ValueError("암호화 payload가 예상보다 짧습니다")
                    mac.update(cipher_chunk)
                    plain = bytearray()
                    offset = 0
                    while offset < len(cipher_chunk):
                        block = hmac.new(
                            enc_key,
                            nonce + counter.to_bytes(8, "big"),
                            hashlib.sha256,
                        ).digest()
                        part = cipher_chunk[offset : offset + len(block)]
                        plain.extend(a ^ b for a, b in zip(part, block))
                        offset += len(part)
                        counter += 1
                    temporary_file.write(plain)
                    remaining -= len(cipher_chunk)
                tag = encrypted.read(TAG_SIZE)
                expected_tag = hmac.new(
                    mac_key, raw_header + mac.digest(), hashlib.sha256
                ).digest()
                if not hmac.compare_digest(tag, expected_tag):
                    raise ValueError("암호화 아카이브 인증 실패")
        os.replace(temporary, output)
        temporary = None
        return output
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
