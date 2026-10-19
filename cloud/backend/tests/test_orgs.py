"""
机构管理接口测试。
"""


class TestOrgCRUD:
    def test_create_org(self, client, admin_headers):
        resp = client.post("/api/cloud/orgs", json={
            "name": "北京交通大学",
            "contact_name": "李四",
            "license_quota": 20,
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "北京交通大学"
        assert data["license_quota"] == 20

    def test_list_orgs(self, client, admin_headers):
        resp = client.get("/api/cloud/orgs", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) <= data["page_size"]

    def test_list_orgs_search(self, client, admin_headers):
        resp = client.get("/api/cloud/orgs?search=测试", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_org_detail(self, client, admin_headers, seed_users):
        org_id = seed_users["org"].id
        resp = client.get(f"/api/cloud/orgs/{org_id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == org_id
        assert "user_count" in data

    def test_update_org(self, client, admin_headers, seed_users):
        org_id = seed_users["org"].id
        resp = client.put(f"/api/cloud/orgs/{org_id}", json={
            "name": "更新后的大学",
        }, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后的大学"

    def test_delete_org_success(self, client, admin_headers):
        # 创建一个没有 license 的新机构
        resp = client.post("/api/cloud/orgs", json={"name": "临时机构"}, headers=admin_headers)
        new_id = resp.json()["id"]
        resp = client.delete(f"/api/cloud/orgs/{new_id}", headers=admin_headers)
        assert resp.status_code == 204

    def test_delete_org_with_active_license(self, client, admin_headers, seed_users, db):
        org_id = seed_users["org"].id
        from app.models.license import License
        lic = License(license_key="TEST-0001-0001-0001", org_id=org_id, license_type="trial", is_active=True)
        db.add(lic)
        db.commit()
        resp = client.delete(f"/api/cloud/orgs/{org_id}", headers=admin_headers)
        assert resp.status_code == 409

    def test_non_admin_forbidden(self, client, teacher_headers):
        resp = client.get("/api/cloud/orgs", headers=teacher_headers)
        assert resp.status_code == 403
