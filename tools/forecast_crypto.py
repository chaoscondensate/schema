#!/usr/bin/env python3
"""Reference cryptographic operations for Forecast Ledger seal profiles v1 and v2.

The implementation supports the RFC 8785 subset used by this project: strings,
booleans, null, arrays, objects, and I-JSON safe integers. Floating-point JSON
numbers are rejected; exact values and probabilities are decimal strings in v2.
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
SEAL_SCHEME_V1 = "forecast-seal/v1"
SEAL_SCHEME_V2 = "forecast-seal/v2"
ENVELOPE_SCHEMA_V1 = "forecast-envelope/v1"
ENVELOPE_SCHEMA_V2 = "forecast-envelope/v2"

# Backward-compatible aliases for applications importing the original names.
SEAL_SCHEME = SEAL_SCHEME_V1
ENVELOPE_SCHEMA = ENVELOPE_SCHEMA_V1


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
            "floating-point values are forbidden; use canonical decimal strings"
        )
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("JSON object keys must be strings")
        keys = sorted(value, key=_utf16_sort_key)
        return "{" + ",".join(f"{_string(key)}:{_serialize(value[key])}" for key in keys) + "}"
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


def _aad_v1(question_id: str, forecast_id: str, commitment_hex: str) -> bytes:
    return canonicalize(
        {
            "scheme": SEAL_SCHEME_V1,
            "question_id": question_id,
            "forecast_id": forecast_id,
            "commitment_sha256": commitment_hex,
        }
    )


def _aad_v2(
    question_id: str,
    question_revision_id: str,
    forecast_id: str,
    commitment_hex: str,
) -> bytes:
    return canonicalize(
        {
            "scheme": SEAL_SCHEME_V2,
            "question_id": question_id,
            "question_revision_id": question_revision_id,
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
    scheme: str = SEAL_SCHEME_V1,
    question_revision_id: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Seal a private forecast and return its public commitment plus plaintext."""

    if len(salt) != 32:
        raise ValueError("salt must be exactly 32 bytes")
    if len(key) != 32:
        raise ValueError("key must be exactly 32 bytes")
    if len(nonce) != 12:
        raise ValueError("nonce must be exactly 12 bytes")
    if scheme not in {SEAL_SCHEME_V1, SEAL_SCHEME_V2}:
        raise ValueError(f"unsupported seal scheme: {scheme}")

    value_field = "value" if scheme == SEAL_SCHEME_V1 else "representations"
    required_bundle_fields = {
        "forecasted_at",
        "recorded_at",
        value_field,
        "rationale",
        "key_factors",
        "comment",
    }
    if scheme == SEAL_SCHEME_V2:
        required_bundle_fields.add("question_revision_id")
        if question_revision_id is None:
            question_revision_id = bundle.get("question_revision_id")
        if bundle.get("question_revision_id") != question_revision_id:
            raise ValueError("bundle question_revision_id does not match seal context")
    missing = sorted(required_bundle_fields - bundle.keys())
    if missing:
        raise ValueError(f"sealed bundle is missing: {', '.join(missing)}")

    payload = {
        "schema": scheme,
        "question_id": question_id,
        "forecast_id": forecast_id,
        "bundle": bundle,
        "salt": salt.hex(),
    }
    if scheme == SEAL_SCHEME_V2:
        payload["question_revision_id"] = question_revision_id
    plaintext = canonicalize(payload)
    commitment = sha256_ref(plaintext)
    if scheme == SEAL_SCHEME_V1:
        aad = _aad_v1(question_id, forecast_id, commitment["value"])
    else:
        aad = _aad_v2(
            question_id,
            str(question_revision_id),
            forecast_id,
            commitment["value"],
        )
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, plaintext, aad)

    public_commitment = {
        "scheme": scheme,
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
    *,
    question_id: str,
    forecast_id: str,
    commitment: dict[str, Any],
    key: bytes,
    question_revision_id: str | None = None,
) -> dict[str, Any]:
    """Decrypt, authenticate, and verify a v1 or v2 sealed forecast payload."""

    if len(key) != 32:
        raise ValueError("key must be exactly 32 bytes")
    scheme = commitment["scheme"]
    commitment_hex = commitment["commitment_hash"]["value"]
    encryption = commitment["encryption"]
    nonce = _unb64(encryption["nonce"])
    ciphertext = _unb64(encryption["ciphertext"])
    if scheme == SEAL_SCHEME_V1:
        aad = _aad_v1(question_id, forecast_id, commitment_hex)
    elif scheme == SEAL_SCHEME_V2:
        if question_revision_id is None:
            raise ValueError("question_revision_id is required for forecast-seal/v2")
        aad = _aad_v2(question_id, question_revision_id, forecast_id, commitment_hex)
    else:
        raise ValueError(f"unsupported seal scheme: {scheme}")
    plaintext = ChaCha20Poly1305(key).decrypt(nonce, ciphertext, aad)

    actual = hashlib.sha256(plaintext).hexdigest()
    if actual != commitment_hex:
        raise ValueError("decrypted payload does not match the commitment hash")
    payload = json.loads(plaintext)
    if payload.get("schema") != scheme:
        raise ValueError("unexpected sealed payload scheme")
    if payload.get("question_id") != question_id:
        raise ValueError("sealed payload belongs to another question")
    if payload.get("forecast_id") != forecast_id:
        raise ValueError("sealed payload belongs to another forecast")
    if scheme == SEAL_SCHEME_V2:
        if payload.get("question_revision_id") != question_revision_id:
            raise ValueError("sealed payload belongs to another question revision")
        if payload.get("bundle", {}).get("question_revision_id") != question_revision_id:
            raise ValueError("sealed bundle belongs to another question revision")
    if canonicalize(payload) != plaintext:
        raise ValueError("decrypted payload is not canonical RFC 8785 data")
    return payload


def _included_forecast(forecast: dict[str, Any], *, sealed: bool) -> dict[str, Any]:
    if sealed:
        commitment = forecast["commitment"]
        included = {
            "id": forecast["id"],
            "question_revision_id": forecast.get("question_revision_id"),
            "forecasted_at": forecast["forecasted_at"],
            "recorded_at": forecast["recorded_at"],
            "visibility": "sealed",
            "commitment": {
                "scheme": commitment["scheme"],
                "commitment_hash": commitment["commitment_hash"],
                "encryption": commitment["encryption"],
            },
        }
        if included["question_revision_id"] is None:
            del included["question_revision_id"]
        optional = (
            "public_note",
            "supersedes_forecast_id",
            "provenance",
            "lifecycle_events",
        )
    else:
        included = {
            key: forecast[key]
            for key in (
                "id",
                "question_revision_id",
                "forecasted_at",
                "recorded_at",
                "visibility",
                "representations",
                "value",
                "rationale",
                "key_factors",
                "comment",
                "public_note",
                "supersedes_forecast_id",
                "provenance",
                "lifecycle_events",
            )
            if key in forecast
        }
        optional = ()
    for key in optional:
        if key in forecast:
            included[key] = forecast[key]
    return included


def public_forecast_envelope(
    question_id: str,
    forecast: dict[str, Any],
    question_revision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the immutable timestamp target for a public forecast."""

    if question_revision is None:
        return {
            "schema": ENVELOPE_SCHEMA_V1,
            "question_id": question_id,
            "forecast": _included_forecast(forecast, sealed=False),
        }
    if forecast.get("question_revision_id") != question_revision.get("id"):
        raise ValueError("forecast does not reference the supplied question revision")
    return {
        "schema": ENVELOPE_SCHEMA_V2,
        "question": {"id": question_id, "revision": question_revision},
        "forecast": _included_forecast(forecast, sealed=False),
    }


def sealed_forecast_envelope(
    question_id: str,
    forecast: dict[str, Any],
    question_revision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the immutable target that binds every security-relevant seal input."""

    if question_revision is None:
        return {
            "schema": ENVELOPE_SCHEMA_V1,
            "question_id": question_id,
            "forecast": _included_forecast(forecast, sealed=True),
        }
    if forecast.get("question_revision_id") != question_revision.get("id"):
        raise ValueError("forecast does not reference the supplied question revision")
    return {
        "schema": ENVELOPE_SCHEMA_V2,
        "question": {"id": question_id, "revision": question_revision},
        "forecast": _included_forecast(forecast, sealed=True),
    }


def verify_vector(vector: dict[str, Any]) -> None:
    material = vector["material"]
    vector_schema = vector.get("schema", "forecast-seal-test-vector/v1")
    scheme = SEAL_SCHEME_V2 if vector_schema.endswith("/v2") else SEAL_SCHEME_V1
    revision_id = vector.get("question_revision_id")
    commitment, plaintext = seal_forecast(
        question_id=vector["question_id"],
        question_revision_id=revision_id,
        forecast_id=vector["forecast_id"],
        bundle=vector["bundle"],
        salt=bytes.fromhex(material["salt_hex"]),
        key=bytes.fromhex(material["key_hex"]),
        nonce=bytes.fromhex(material["nonce_hex"]),
        key_hint=vector["expected"]["commitment"]["key_hint"],
        scheme=scheme,
    )
    if plaintext.decode("utf-8") != vector["expected"]["canonical_plaintext"]:
        raise AssertionError("canonical plaintext differs from the test vector")
    if commitment != vector["expected"]["commitment"]:
        raise AssertionError("commitment differs from the test vector")
    payload = reveal_forecast(
        question_id=vector["question_id"],
        question_revision_id=revision_id,
        forecast_id=vector["forecast_id"],
        commitment=commitment,
        key=bytes.fromhex(material["key_hex"]),
    )
    if payload["bundle"] != vector["bundle"]:
        raise AssertionError("revealed bundle differs from the input")


def _demo_vector(version: int) -> dict[str, Any]:
    if version == 1:
        bundle = {
            "forecasted_at": "2026-08-25T10:00:00+01:00",
            "recorded_at": "2026-08-25T10:01:00+01:00",
            "value": {"kind": "binary", "probability_bp": 6500},
            "rationale": (
                "The base rate and two independent indicators point in the same direction."
            ),
            "key_factors": ["base rate", "leading indicator"],
            "comment": "Reveal after the outcome is public.",
        }
        revision_id = None
        scheme = SEAL_SCHEME_V1
    else:
        bundle = {
            "question_revision_id": "qr-example-binary-1",
            "forecasted_at": "2026-08-25T10:00:00+01:00",
            "recorded_at": "2026-08-25T10:01:00+01:00",
            "representations": [{"kind": "probability", "outcome": True, "probability": "0.65"}],
            "rationale": (
                "The base rate and two independent indicators point in the same direction."
            ),
            "key_factors": ["base rate", "leading indicator"],
            "comment": "Reveal after the outcome is public.",
        }
        revision_id = "qr-example-binary-1"
        scheme = SEAL_SCHEME_V2
    salt = bytes.fromhex("aa" * 10 + "1f" + "aa" * 21)
    key = bytes.fromhex("bb" * 32)
    nonce = bytes.fromhex("cc" * 12)
    commitment, plaintext = seal_forecast(
        question_id="q-example-binary",
        question_revision_id=revision_id,
        forecast_id="f-example-binary-001",
        bundle=bundle,
        salt=salt,
        key=key,
        nonce=nonce,
        key_hint="secret-manager://forecast-ledger/f-example-binary-001",
        scheme=scheme,
    )
    vector = {
        "schema": f"forecast-seal-test-vector/v{version}",
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
    if revision_id:
        vector["question_revision_id"] = revision_id
    return vector


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    show_parser = subparsers.add_parser("show-vector", help="Print a deterministic vector")
    show_parser.add_argument("--version", type=int, choices=(1, 2), default=2)
    verify_parser = subparsers.add_parser("verify-vector", help="Verify a vector file")
    verify_parser.add_argument("path", type=Path)
    args = parser.parse_args()

    if args.command == "show-vector":
        print(json.dumps(_demo_vector(args.version), ensure_ascii=False, indent=2))
        return 0
    vector = json.loads(args.path.read_text(encoding="utf-8"))
    verify_vector(vector)
    print(f"ok: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
