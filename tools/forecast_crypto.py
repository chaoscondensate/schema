#!/usr/bin/env python3
"""Reference cryptographic operations for Forecast Ledger v1.

The implementation intentionally supports the RFC 8785 subset used by this
project: strings, booleans, null, arrays, objects, and I-JSON safe integers.
Floating-point JSON numbers are rejected; forecast decimals are strings and
probabilities are integer basis points.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

MAX_SAFE_INTEGER = 9_007_199_254_740_991
SEAL_SCHEME = "forecast-seal/v1"
ENVELOPE_SCHEMA = "forecast-envelope/v1"


class CanonicalizationError(ValueError):
    """Raised when a value is outside the project's RFC 8785 subset."""


def _reject_surrogates(value: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise CanonicalizationError("lone Unicode surrogates are not valid I-JSON")


def _string(value: str) -> str:
    _reject_surrogates(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _utf16_sort_key(value: str) -> bytes:
    _reject_surrogates(value)
    return value.encode("utf-16-be")


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise CanonicalizationError("integer is outside the I-JSON safe range")
        return str(value)
    if isinstance(value, float):
        raise CanonicalizationError(
            "floating-point values are forbidden; use decimal strings or basis points"
        )
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("JSON object keys must be strings")
        keys = sorted(value, key=_utf16_sort_key)
        return "{" + ",".join(
            f"{_string(key)}:{_serialize(value[key])}" for key in keys
        ) + "}"
    raise CanonicalizationError(f"unsupported JSON value: {type(value).__name__}")


def canonicalize(value: Any) -> bytes:
    """Return canonical UTF-8 bytes for the project's RFC 8785 subset."""

    return _serialize(value).encode("utf-8")


def sha256_ref(data: bytes) -> dict[str, str]:
    return {"algorithm": "sha-256", "value": hashlib.sha256(data).hexdigest()}


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _aad(question_id: str, forecast_id: str, commitment_hex: str) -> bytes:
    return canonicalize(
        {
            "scheme": SEAL_SCHEME,
            "question_id": question_id,
            "forecast_id": forecast_id,
            "commitment_sha256": commitment_hex,
        }
    )


def seal_forecast(
    *,
    question_id: str,
    forecast_id: str,
    bundle: dict[str, Any],
    salt: bytes,
    key: bytes,
    nonce: bytes,
    key_hint: str,
) -> tuple[dict[str, Any], bytes]:
    """Seal a private forecast and return its public commitment plus plaintext."""

    if len(salt) != 32:
        raise ValueError("salt must be exactly 32 bytes")
    if len(key) != 32:
        raise ValueError("key must be exactly 32 bytes")
    if len(nonce) != 12:
        raise ValueError("nonce must be exactly 12 bytes")

    required_bundle_fields = {
        "forecasted_at",
        "recorded_at",
        "value",
        "rationale",
        "key_factors",
        "comment",
    }
    missing = sorted(required_bundle_fields - bundle.keys())
    if missing:
        raise ValueError(f"sealed bundle is missing: {', '.join(missing)}")

    payload = {
        "schema": SEAL_SCHEME,
        "question_id": question_id,
        "forecast_id": forecast_id,
        "bundle": bundle,
        "salt": salt.hex(),
    }
    plaintext = canonicalize(payload)
    commitment = sha256_ref(plaintext)
    aad = _aad(question_id, forecast_id, commitment["value"])
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)

    public_commitment = {
        "scheme": SEAL_SCHEME,
        "commitment_hash": commitment,
        "encryption": {
            "algorithm": "chacha20-poly1305",
            "nonce": _b64(nonce),
            "ciphertext": _b64(ciphertext),
        },
        "key_hint": key_hint,
    }
    return public_commitment, plaintext


def reveal_forecast(
    *, question_id: str, forecast_id: str, commitment: dict[str, Any], key: bytes
) -> dict[str, Any]:
    """Decrypt, authenticate, and verify a sealed forecast payload."""

    if len(key) != 32:
        raise ValueError("key must be exactly 32 bytes")
    commitment_hex = commitment["commitment_hash"]["value"]
    encryption = commitment["encryption"]
    nonce = _unb64(encryption["nonce"])
    ciphertext = _unb64(encryption["ciphertext"])
    aad = _aad(question_id, forecast_id, commitment_hex)
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)

    actual = hashlib.sha256(plaintext).hexdigest()
    if actual != commitment_hex:
        raise ValueError("decrypted payload does not match the commitment hash")

    payload = json.loads(plaintext)
    if payload.get("schema") != SEAL_SCHEME:
        raise ValueError("unexpected sealed payload scheme")
    if payload.get("question_id") != question_id:
        raise ValueError("sealed payload belongs to another question")
    if payload.get("forecast_id") != forecast_id:
        raise ValueError("sealed payload belongs to another forecast")
    if canonicalize(payload) != plaintext:
        raise ValueError("decrypted payload is not canonical RFC 8785 data")
    return payload


def public_forecast_envelope(question_id: str, forecast: dict[str, Any]) -> dict[str, Any]:
    """Build the immutable timestamp target for a public forecast."""

    included = {
        key: forecast[key]
        for key in (
            "id",
            "forecasted_at",
            "recorded_at",
            "visibility",
            "value",
            "rationale",
            "key_factors",
            "comment",
            "public_note",
            "supersedes_forecast_id",
        )
        if key in forecast
    }
    return {
        "schema": ENVELOPE_SCHEMA,
        "question_id": question_id,
        "forecast": included,
    }


def sealed_forecast_envelope(question_id: str, forecast: dict[str, Any]) -> dict[str, Any]:
    """Build the immutable target that binds every security-relevant seal input."""

    commitment = forecast["commitment"]
    included = {
        "id": forecast["id"],
        "forecasted_at": forecast["forecasted_at"],
        "recorded_at": forecast["recorded_at"],
        "visibility": "sealed",
        "commitment": {
            "scheme": commitment["scheme"],
            "commitment_hash": commitment["commitment_hash"],
            "encryption": commitment["encryption"],
        },
    }
    if "public_note" in forecast:
        included["public_note"] = forecast["public_note"]
    if "supersedes_forecast_id" in forecast:
        included["supersedes_forecast_id"] = forecast["supersedes_forecast_id"]
    return {
        "schema": ENVELOPE_SCHEMA,
        "question_id": question_id,
        "forecast": included,
    }


def verify_vector(vector: dict[str, Any]) -> None:
    material = vector["material"]
    commitment, plaintext = seal_forecast(
        question_id=vector["question_id"],
        forecast_id=vector["forecast_id"],
        bundle=vector["bundle"],
        salt=bytes.fromhex(material["salt_hex"]),
        key=bytes.fromhex(material["key_hex"]),
        nonce=bytes.fromhex(material["nonce_hex"]),
        key_hint=vector["expected"]["commitment"]["key_hint"],
    )
    if plaintext.decode("utf-8") != vector["expected"]["canonical_plaintext"]:
        raise AssertionError("canonical plaintext differs from the test vector")
    if commitment != vector["expected"]["commitment"]:
        raise AssertionError("commitment differs from the test vector")

    payload = reveal_forecast(
        question_id=vector["question_id"],
        forecast_id=vector["forecast_id"],
        commitment=commitment,
        key=bytes.fromhex(material["key_hex"]),
    )
    if payload["bundle"] != vector["bundle"]:
        raise AssertionError("revealed bundle differs from the input")


def _demo_vector() -> dict[str, Any]:
    bundle = {
        "forecasted_at": "2026-08-25T10:00:00+01:00",
        "recorded_at": "2026-08-25T10:01:00+01:00",
        "value": {"kind": "binary", "probability_bp": 6500},
        "rationale": "The base rate and two independent indicators point in the same direction.",
        "key_factors": ["base rate", "leading indicator"],
        "comment": "Reveal after the outcome is public.",
    }
    salt = bytes.fromhex("aa" * 10 + "1f" + "aa" * 21)
    key = bytes.fromhex("bb" * 32)
    nonce = bytes.fromhex("cc" * 12)
    commitment, plaintext = seal_forecast(
        question_id="q-example-binary",
        forecast_id="f-example-binary-001",
        bundle=bundle,
        salt=salt,
        key=key,
        nonce=nonce,
        key_hint="secret-manager://forecast-ledger/f-example-binary-001",
    )
    return {
        "schema": "forecast-seal-test-vector/v1",
        "question_id": "q-example-binary",
        "forecast_id": "f-example-binary-001",
        "bundle": bundle,
        "material": {
            "salt_hex": salt.hex(),
            "key_hex": key.hex(),
            "nonce_hex": nonce.hex(),
        },
        "expected": {
            "canonical_plaintext": plaintext.decode("utf-8"),
            "commitment": commitment,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("show-vector", help="Print the built-in deterministic vector")
    verify_parser = subparsers.add_parser("verify-vector", help="Verify a vector file")
    verify_parser.add_argument("path", type=Path)
    args = parser.parse_args()

    if args.command == "show-vector":
        print(json.dumps(_demo_vector(), ensure_ascii=False, indent=2))
        return 0
    vector = json.loads(args.path.read_text(encoding="utf-8"))
    verify_vector(vector)
    print(f"ok: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
