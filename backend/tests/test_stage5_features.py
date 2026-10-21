"""
Stage 5 feature tests: global exception handlers, rate limiting, password strength.
"""
import pytest
from fastapi import status


class TestGlobalExceptionHandlers:
    """Verify the standardised error response format."""

    def test_404_returns_structured_error(self, client):
        """Non-existent route should return structured JSON error."""
        resp = client.get("/api/v1/nonexistent-endpoint-xyz")
        assert resp.status_code in (404, 405)
        data = resp.json()
        assert data["success"] is False

    def test_401_structured_detail_preserved(self, client, test_teacher):
        """Router-provided dict detail should be preserved as-is."""
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "teacher1", "password": "wrongpassword"},
        )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        data = resp.json()
        assert data["success"] is False
        assert data["detail"]["code"] == "AUTH_001"

    def test_health_check_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


class TestRateLimiting:
    """Verify per-IP sliding-window rate limiter on login endpoint."""

    def test_normal_login_not_rate_limited(self, client, test_teacher):
        """A single login attempt should not be rate-limited."""
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "teacher1", "password": "teacher123"},
        )
        assert resp.status_code == 200

    def test_excessive_logins_rate_limited(self, client, test_teacher):
        """Exceeding 30 requests in 60s should return 429."""
        # Clear any existing buckets by importing the module-level dict
        from app.main import _rate_buckets
        _rate_buckets.clear()

        for i in range(31):
            resp = client.post(
                "/api/v1/auth/login",
                data={"username": "teacher1", "password": "teacher123"},
            )
            if resp.status_code == 429:
                break

        assert resp.status_code == 429
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "RATE_LIMITED"

        # Clean up so other tests aren't affected
        _rate_buckets.clear()


class TestPasswordStrength:
    """Verify password complexity requirements on user creation."""

    def test_weak_password_digits_only(self, client, teacher_token):
        """Password with only digits should be rejected."""
        resp = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "username": "weakuser1",
                "password": "123456",
                "role": "student",
            },
        )
        assert resp.status_code == 422

    def test_weak_password_letters_only(self, client, teacher_token):
        """Password with only letters should be rejected."""
        resp = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "username": "weakuser2",
                "password": "abcdef",
                "role": "student",
            },
        )
        assert resp.status_code == 422

    def test_strong_password_accepted(self, client, teacher_token):
        """Password with letters + digits should be accepted."""
        resp = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "username": "stronguser1",
                "password": "abc123",
                "role": "student",
            },
        )
        assert resp.status_code in (200, 201)

    def test_password_too_short(self, client, teacher_token):
        """Password shorter than 6 chars should be rejected."""
        resp = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "username": "shortpw",
                "password": "ab1",
                "role": "student",
            },
        )
        assert resp.status_code == 422
