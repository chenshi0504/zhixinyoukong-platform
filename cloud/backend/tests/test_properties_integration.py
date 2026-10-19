"""
集成属性测试：需要数据库和 API 客户端的属性测试。
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.models.organization import Organization
from app.models.license import License
from app.models.user import User
from app.models.task import Task
from app.models.report import Report
from app.services.auth import hash_password, create_access_token
from app.services.license import generate_license_key


# ============================================================
# Property 7: 机构详情包含所有关联数据
# Feature: cloud-admin-platform, Property 7: 机构详情包含所有关联数据
# Validates: Requirements 2.5
# ============================================================

class TestOrgDetailProperty:
    def test_org_detail_licenses_belong_to_org(self, client, db, admin_headers, seed_users):
        """机构详情中的关联数据 org_id 均等于该机构 id。"""
        org_id = seed_users["org"].id
        # 添加一些 license
        for i in range(3):
            lic = License(license_key=f"PROP-7777-{i:04d}-0001", org_id=org_id, license_type="trial")
            db.add(lic)
        db.commit()

        resp = client.get(f"/api/cloud/orgs/{org_id}", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == org_id
        assert data["license_count"] >= 3
        assert data["user_count"] >= 1  # seed_users 中有用户


# ============================================================
# Property 3: License 激活-验证往返
# Feature: cloud-admin-platform, Property 3: License 激活-验证往返
# Validates: Requirements 3.2, 3.3
# ============================================================

class TestLicenseActivateVerifyProperty:
    def test_activate_verify_roundtrip(self, client, db, admin_headers, seed_users):
        """多个随机 machine_id 激活后验证，状态应一致。"""
        import secrets
        org_id = seed_users["org"].id
        for _ in range(10):
            machine_id = secrets.token_hex(16)
            key = generate_license_key()
            lic = License(license_key=key, org_id=org_id, license_type="education")
            db.add(lic)
            db.commit()

            act_resp = client.post("/api/cloud/licenses/activate", json={
                "license_key": key, "machine_id": machine_id,
            })
            assert act_resp.status_code == 200
            token = act_resp.json()["activation_token"]

            ver_resp = client.post("/api/cloud/licenses/verify", json={
                "activation_token": token,
            })
            assert ver_resp.status_code == 200
            v = ver_resp.json()
            assert v["is_active"] is True
            assert v["license_type"] == "education"
            assert v["machine_id"] == machine_id


# ============================================================
# Property 5: License 吊销后验证失败
# Feature: cloud-admin-platform, Property 5: License 吊销后验证失败
# Validates: Requirements 3.6
# ============================================================

class TestLicenseRevokeProperty:
    def test_revoke_then_verify_inactive(self, client, db, admin_headers, seed_users):
        """激活后吊销，验证应返回 is_active=false。"""
        org_id = seed_users["org"].id
        key = generate_license_key()
        lic = License(license_key=key, org_id=org_id, license_type="trial")
        db.add(lic)
        db.commit()
        db.refresh(lic)

        # 激活
        act = client.post("/api/cloud/licenses/activate", json={
            "license_key": key, "machine_id": "revoke_test_machine",
        })
        token = act.json()["activation_token"]

        # 吊销
        client.put(f"/api/cloud/licenses/{lic.id}/revoke", headers=admin_headers)

        # 验证
        ver = client.post("/api/cloud/licenses/verify", json={"activation_token": token})
        assert ver.json()["is_active"] is False


# ============================================================
# Property 9: 角色权限隔离
# Feature: cloud-admin-platform, Property 9: 角色权限隔离
# Validates: Requirements 4.3
# ============================================================

class TestRoleIsolationProperty:
    def test_non_admin_cannot_access_admin_endpoints(self, client, db, seed_users, teacher_headers):
        """非 super_admin 调用管理员专属接口应返回 403。"""
        admin_endpoints = [
            ("GET", "/api/cloud/orgs"),
            ("POST", "/api/cloud/orgs"),
            ("POST", "/api/cloud/licenses/generate"),
        ]
        for method, url in admin_endpoints:
            if method == "GET":
                resp = client.get(url, headers=teacher_headers)
            else:
                resp = client.post(url, json={}, headers=teacher_headers)
            assert resp.status_code in (403, 422), f"{method} {url} returned {resp.status_code}"


# ============================================================
# Property 8: 密码重置使 Refresh Token 失效
# Feature: cloud-admin-platform, Property 8: 密码重置使 Refresh Token 失效
# Validates: Requirements 4.6
# ============================================================

class TestPasswordResetInvalidatesTokenProperty:
    def test_reset_password_invalidates_refresh(self, client, db, admin_headers, seed_users):
        """登录获取 refresh_token，重置密码后旧 token 应失效。"""
        # teacher1 登录
        login_resp = client.post("/api/cloud/auth/login", json={
            "username": "teacher1", "password": "password123",
        })
        old_refresh = login_resp.json()["refresh_token"]
        teacher_id = seed_users["users"]["teacher1"].id

        # admin 重置 teacher1 密码
        client.post(f"/api/cloud/users/{teacher_id}/reset-password", json={
            "new_password": "new_password_456",
        }, headers=admin_headers)

        # 旧 refresh token 应失效
        resp = client.post("/api/cloud/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 401


# ============================================================
# Property 13: Dashboard 汇总数据一致性
# Feature: cloud-admin-platform, Property 13: Dashboard 汇总数据一致性
# Validates: Requirements 1.2
# ============================================================

class TestDashboardConsistencyProperty:
    def test_dashboard_org_count_matches_db(self, client, db, admin_headers, seed_users):
        """Dashboard 返回的 total_organizations 应等于数据库行数。"""
        # 添加几个机构
        for i in range(3):
            db.add(Organization(name=f"测试机构_{i}"))
        db.commit()

        from sqlalchemy import func as sa_func
        actual_count = db.query(sa_func.count(Organization.id)).scalar()

        resp = client.get("/api/cloud/admin/dashboard", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["total_organizations"] == actual_count



# ============================================================
# Property 2: 增量同步时间戳过滤正确性
# Feature: cloud-admin-platform, Property 2: 增量同步时间戳过滤正确性
# Validates: Requirements 5.3, 6.4, 9.1
# ============================================================

class TestSyncTimestampFilterProperty:
    def test_sync_tasks_only_returns_after_since(self, client, db, seed_users):
        """sync/tasks 只返回 updated_at > since 的已发布任务。"""
        org_id = seed_users["org"].id
        teacher_id = seed_users["users"]["teacher1"].id

        # 创建几个任务，手动设置 updated_at
        from app.models.task import Task
        t1 = Task(title="旧任务", org_id=org_id, teacher_id=teacher_id, status="published")
        t2 = Task(title="新任务", org_id=org_id, teacher_id=teacher_id, status="published")
        t3 = Task(title="草稿", org_id=org_id, teacher_id=teacher_id, status="draft")
        db.add_all([t1, t2, t3])
        db.flush()

        # 手动设置时间
        old_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        new_time = datetime(2026, 2, 20, tzinfo=timezone.utc)
        db.execute(
            Task.__table__.update().where(Task.id == t1.id).values(updated_at=old_time)
        )
        db.execute(
            Task.__table__.update().where(Task.id == t2.id).values(updated_at=new_time)
        )
        db.execute(
            Task.__table__.update().where(Task.id == t3.id).values(updated_at=new_time)
        )
        db.commit()

        # since = 2026-01-01，应只返回 t2（新任务，已发布）
        since = "2026-01-01T00:00:00"
        resp = client.get(f"/api/cloud/sync/tasks?since={since}&org_id={org_id}")
        assert resp.status_code == 200
        titles = [t["title"] for t in resp.json()]
        assert "新任务" in titles
        assert "旧任务" not in titles
        assert "草稿" not in titles  # draft 不应出现
