"""
认证接口单元测试：登录、刷新、登出。
"""
import pytest


class TestLogin:
    def test_login_success(self, client, seed_users):
        resp = client.post("/api/cloud/auth/login", json={
            "username": "teacher1",
            "password": "password123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "teacher1"
        assert data["user"]["role"] == "teacher"
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, seed_users):
        resp = client.post("/api/cloud/auth/login", json={
            "username": "teacher1",
            "password": "wrong_password",
        })
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client, seed_users):
        resp = client.post("/api/cloud/auth/login", json={
            "username": "nobody",
            "password": "password123",
        })
        assert resp.status_code == 401


class TestRefresh:
    def _login(self, client):
        resp = client.post("/api/cloud/auth/login", json={
            "username": "teacher1",
            "password": "password123",
        })
        return resp.json()

    def test_refresh_success(self, client, seed_users):
        tokens = self._login(client)
        resp = client.post("/api/cloud/auth/refresh", json={
            "refresh_token": tokens["refresh_token"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_invalid_token(self, client, seed_users):
        resp = client.post("/api/cloud/auth/refresh", json={
            "refresh_token": "invalid-token-value",
        })
        assert resp.status_code == 401


class TestLogout:
    def test_logout_success(self, client, seed_users):
        # 登录
        login_resp = client.post("/api/cloud/auth/login", json={
            "username": "teacher1",
            "password": "password123",
        })
        tokens = login_resp.json()
        access = tokens["access_token"]
        refresh = tokens["refresh_token"]

        # 登出
        resp = client.post(
            "/api/cloud/auth/logout",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert resp.status_code == 204

        # 登出后 refresh token 应失效
        resp2 = client.post("/api/cloud/auth/refresh", json={
            "refresh_token": refresh,
        })
        assert resp2.status_code == 401

    def test_logout_requires_auth(self, client, seed_users):
        resp = client.post("/api/cloud/auth/logout", json={
            "refresh_token": "some-token",
        })
        assert resp.status_code == 401
