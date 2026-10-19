"""
Stage 5 tests: RSA license signing and local verification.
"""
import json
import base64
import os
import pytest


# Skip entire module if cryptography not installed
cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization


@pytest.fixture(scope="module")
def rsa_keypair(tmp_path_factory):
    """Generate a temporary RSA key pair for testing."""
    tmp = tmp_path_factory.mktemp("keys")
    priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path = tmp / "license_private.pem"
    pub_path = tmp / "license_public.pem"
    priv_path.write_bytes(
        priv_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        priv_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return str(priv_path), str(pub_path), priv_key


def _sign_with_rsa(payload: dict, priv_key) -> str:
    """Replicate cloud-side RSA signing logic."""
    payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode()
    sig_bytes = priv_key.sign(
        payload_b64.encode(), padding.PKCS1v15(), hashes.SHA256()
    )
    sig_b64 = base64.urlsafe_b64encode(sig_bytes).decode()
    return f"{payload_b64}.{sig_b64}"


class TestRSATokenVerification:
    """Test local-side RSA public key verification of activation tokens."""

    def test_valid_rsa_token_verified(self, rsa_keypair, monkeypatch):
        """A token signed with the matching private key should verify."""
        _priv_path, pub_path, priv_key = rsa_keypair
        # Point the local module to our test public key
        import license.license_check as lc
        monkeypatch.setattr(lc, "_PUBLIC_KEY_FILE", pub_path)

        payload = {
            "license_id": 1,
            "machine_id": "test-machine",
            "license_type": "education",
            "expires_at": "2099-12-31T23:59:59+00:00",
        }
        token = _sign_with_rsa(payload, priv_key)
        result = lc._verify_token_rsa(token)
        assert result is not None
        assert result["license_type"] == "education"
        assert result["machine_id"] == "test-machine"

    def test_tampered_token_rejected(self, rsa_keypair, monkeypatch):
        """A token with modified payload should fail verification."""
        _priv_path, pub_path, priv_key = rsa_keypair
        import license.license_check as lc
        monkeypatch.setattr(lc, "_PUBLIC_KEY_FILE", pub_path)

        payload = {"license_id": 1, "machine_id": "m1", "license_type": "trial"}
        token = _sign_with_rsa(payload, priv_key)

        # Tamper: swap payload
        parts = token.split(".", 1)
        tampered_payload = base64.urlsafe_b64encode(b'{"license_id":999}').decode()
        tampered_token = f"{tampered_payload}.{parts[1]}"

        result = lc._verify_token_rsa(tampered_token)
        assert result is None

    def test_no_public_key_returns_none(self, monkeypatch):
        """When public key file doesn't exist, should return None (fallback)."""
        import license.license_check as lc
        monkeypatch.setattr(lc, "_PUBLIC_KEY_FILE", "/nonexistent/path.pem")
        result = lc._verify_token_rsa("fake.token")
        assert result is None

    def test_decode_payload_still_works(self):
        """_decode_token_payload should decode without signature check."""
        import license.license_check as lc
        payload = {"license_type": "permanent", "machine_id": "xyz"}
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True).encode()
        ).decode()
        token = f"{payload_b64}.fakesignature"
        result = lc._decode_token_payload(token)
        assert result is not None
        assert result["license_type"] == "permanent"
