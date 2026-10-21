"""
License 管理接口测试：生成、激活、验证、吊销。
"""
import re


class TestLicenseGenerate:
    def test_generate_license(self, client, admin_headers, seed_users):
        org_id = seed_users["org"].id
        resp = client.post("/api/cloud/licenses/generate", json={
            "org_id": org_id,
            "license_type": "education",
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert re.match(r"^[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}$", data["license_key"])
        assert data["license_type"] == "education"
        assert data["is_active"] is True

    def test_list_licenses(self, client, admin_headers, seed_users):
        org_id = seed_users["org"].id
        client.post("/api/cloud/licenses/generate", json={
            "org_id": org_id, "license_type": "trial",
        }, headers=admin_headers)
        resp = client.get("/api/cloud/licenses", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_non_admin_forbidden(self, client, teacher_headers):
        resp = client.post("/api/cloud/licenses/generate", json={
            "org_id": 1, "license_type": "trial",
        }, headers=teacher_headers)
        assert resp.status_code == 403


class TestLicenseActivateVerify:
    def _generate(self, client, admin_headers, org_id):
        resp = client.post("/api/cloud/licenses/generate", json={
            "org_id": org_id,
            "license_type": "education",
        }, headers=admin_headers)
        return resp.json()

    def test_activate_and_verify(self, client, admin_headers, seed_users):
        lic = self._generate(client, admin_headers, seed_users["org"].id)
        # 激活（无需 JWT）
        resp = client.post("/api/cloud/licenses/activate", json={
            "license_key": lic["license_key"],
            "machine_id": "abc123def456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "activation_token" in data
        assert data["license_type"] == "education"

        # 验证
        resp2 = client.post("/api/cloud/licenses/verify", json={
            "activation_token": data["activation_token"],
        })
        assert resp2.status_code == 200
        v = resp2.json()
        assert v["is_active"] is True
        assert v["license_type"] == "education"

    def test_activate_already_bound(self, client, admin_headers, seed_users):
        lic = self._generate(client, admin_headers, seed_users["org"].id)
        client.post("/api/cloud/licenses/activate", json={
            "license_key": lic["license_key"],
            "machine_id": "machine_A",
        })
        resp = client.post("/api/cloud/licenses/activate", json={
            "license_key": lic["license_key"],
            "machine_id": "machine_B",
        })
        assert resp.status_code == 409

    def test_activate_nonexistent_key(self, client, seed_users):
        resp = client.post("/api/cloud/licenses/activate", json={
            "license_key": "XXXX-XXXX-XXXX-XXXX",
            "machine_id": "machine_A",
        })
        assert resp.status_code == 404


class TestLicenseRevoke:
    def test_revoke_then_verify_fails(self, client, admin_headers, seed_users):
        # 生成
        resp = client.post("/api/cloud/licenses/generate", json={
            "org_id": seed_users["org"].id,
            "license_type": "trial",
        }, headers=admin_headers)
        lic = resp.json()

        # 激活
        act_resp = client.post("/api/cloud/licenses/activate", json={
            "license_key": lic["license_key"],
            "machine_id": "machine_C",
        })
        token = act_resp.json()["activation_token"]

        # 吊销
        resp2 = client.put(f"/api/cloud/licenses/{lic['id']}/revoke", headers=admin_headers)
        assert resp2.status_code == 200
        assert resp2.json()["is_active"] is False

        # 验证应失败
        resp3 = client.post("/api/cloud/licenses/verify", json={
            "activation_token": token,
        })
        assert resp3.json()["is_active"] is False
