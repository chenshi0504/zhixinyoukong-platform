"""初始化测试数据：创建机构和班级"""
from app.database import SessionLocal
from app.models.organization import Organization
from app.models.classroom import Class

db = SessionLocal()

try:
    # 创建机构
    org = db.query(Organization).filter(Organization.name == "大连理工大学").first()
    if not org:
        org = Organization(name="大连理工大学", license_quota=100)
        db.add(org)
        db.flush()
        print(f"[OK] Created org: {org.name} (ID: {org.id})")
    else:
        print(f"[OK] Org exists: {org.name} (ID: {org.id})")

    # 创建班级
    class1 = db.query(Class).filter(Class.name == "计算机1班", Class.org_id == org.id).first()
    if not class1:
        class1 = Class(name="计算机1班", org_id=org.id)
        db.add(class1)
        db.flush()
        print(f"[OK] Created class: {class1.name} (ID: {class1.id})")
    else:
        print(f"[OK] Class exists: {class1.name} (ID: {class1.id})")

    class2 = db.query(Class).filter(Class.name == "计算机2班", Class.org_id == org.id).first()
    if not class2:
        class2 = Class(name="计算机2班", org_id=org.id)
        db.add(class2)
        db.flush()
        print(f"[OK] Created class: {class2.name} (ID: {class2.id})")
    else:
        print(f"[OK] Class exists: {class2.name} (ID: {class2.id})")

    db.commit()
    print("\n[SUCCESS] Test data initialized")
    print(f"   机构ID: {org.id}")
    print(f"   班级ID: {class1.id}, {class2.id}")

except Exception as e:
    db.rollback()
    print(f"[ERROR] {e}")
finally:
    db.close()
