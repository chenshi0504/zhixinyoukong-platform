"""Database initialization and default local seed data."""

import bcrypt
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import AlgorithmTemplate, AlgorithmScript, ExperimentRecord, Report, Task, User, UserRole


DEFAULT_PASSWORD = "123456"
DEFAULT_CLASS_NAME = "交通工程2024级1班"
LEGACY_USERNAMES = (
    "admin01",
    "teacher01",
    "student01",
    "stu0001001",
    "stu0001003",
    "stu0001004",
    "stu0001005",
    "stu0002001",
    "student10001",
    "student10002",
    "student30001",
    "student50001",
    "student140038",
    "student170045",
    "student190049",
    "student250062",
)
LEGACY_TASK_TITLES = ("实验一：多源数据采集与融合", "实验二：交通流预测", "123")


def get_password_hash(password: str) -> str:
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def create_tables():
    Base.metadata.create_all(bind=engine)


def _ensure_user(
    db: Session,
    *,
    username: str,
    role: str,
    real_name: str,
    student_id: str | None = None,
    class_name: str | None = None,
) -> User:
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(username=username)
        db.add(user)
        db.flush()
    user.password_hash = get_password_hash(DEFAULT_PASSWORD)
    user.role = role
    user.real_name = real_name
    user.student_id = student_id
    user.class_name = class_name
    user.is_active = True
    return user


def _cleanup_legacy_demo_data(db: Session) -> None:
    legacy_users = db.query(User).filter(User.username.in_(LEGACY_USERNAMES)).all()
    legacy_user_ids = [user.id for user in legacy_users]
    if legacy_user_ids:
        db.query(AlgorithmScript).filter(AlgorithmScript.student_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.query(ExperimentRecord).filter(ExperimentRecord.student_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.query(Report).filter(Report.graded_by.in_(legacy_user_ids)).update({"graded_by": None}, synchronize_session=False)
        db.query(Report).filter(Report.student_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        legacy_task_ids = [row.id for row in db.query(Task.id).filter(Task.teacher_id.in_(legacy_user_ids)).all()]
        if legacy_task_ids:
            db.query(AlgorithmScript).filter(AlgorithmScript.task_id.in_(legacy_task_ids)).delete(synchronize_session=False)
            db.query(ExperimentRecord).filter(ExperimentRecord.task_id.in_(legacy_task_ids)).delete(synchronize_session=False)
            db.query(Report).filter(Report.task_id.in_(legacy_task_ids)).delete(synchronize_session=False)
            db.query(Task).filter(Task.id.in_(legacy_task_ids)).delete(synchronize_session=False)
        db.query(AlgorithmTemplate).filter(AlgorithmTemplate.teacher_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(legacy_user_ids)).delete(synchronize_session=False)

    demo_tasks = db.query(Task).filter(Task.title.in_(LEGACY_TASK_TITLES)).all()
    demo_task_ids = [task.id for task in demo_tasks]
    if demo_task_ids:
        db.query(AlgorithmScript).filter(AlgorithmScript.task_id.in_(demo_task_ids)).delete(synchronize_session=False)
        db.query(ExperimentRecord).filter(ExperimentRecord.task_id.in_(demo_task_ids)).delete(synchronize_session=False)
        db.query(Report).filter(Report.task_id.in_(demo_task_ids)).delete(synchronize_session=False)
        db.query(Task).filter(Task.id.in_(demo_task_ids)).delete(synchronize_session=False)


def seed_data(db: Session):
    """Create or repair the default local accounts."""
    _cleanup_legacy_demo_data(db)

    admin = _ensure_user(
        db,
        username="admin",
        role=UserRole.ADMIN.value,
        real_name="平台管理员",
    )
    teacher = _ensure_user(
        db,
        username="teacher",
        role=UserRole.TEACHER.value,
        real_name="大连理工大学教师",
        class_name=DEFAULT_CLASS_NAME,
    )
    student = _ensure_user(
        db,
        username="student",
        role=UserRole.STUDENT.value,
        real_name="李明",
        student_id="2024001",
        class_name=DEFAULT_CLASS_NAME,
    )
    db.flush()

    _seed_algorithm_templates(db, teacher.id)
    db.commit()
    print(
        "Default local accounts ready: admin / teacher / student, "
        "password 123456, class 交通工程2024级1班"
    )
    return admin, teacher, student


def _seed_algorithm_templates(db: Session, teacher_id: int):
    templates = [
        (
            "data_collection",
            "多源数据融合模板",
            "演示如何读取多源交通数据并进行简单融合处理。",
            "# 多源数据融合算法模板\n"
            "def fuse_data(sources):\n"
            "    merged = {}\n"
            "    for src in sources:\n"
            "        for key, val in src.items():\n"
            "            merged.setdefault(key, []).append(val)\n"
            "    return {k: sum(v) / len(v) for k, v in merged.items()}\n",
        ),
        (
            "traffic_prediction",
            "交通流预测模板",
            "使用简单移动平均法进行交通流量预测。",
            "# 交通流预测算法模板\n"
            "def moving_average(data, window=3):\n"
            "    return [sum(data[i-window:i]) / window for i in range(window, len(data))]\n",
        ),
        (
            "signal_optimization",
            "信号优化模板",
            "演示简单的固定配时信号优化算法。",
            "# 信号优化算法模板\n"
            "def optimize_signal(flows, cycle=120):\n"
            "    total = sum(flows.values()) or 1\n"
            "    return {direction: round(cycle * flow / total) for direction, flow in flows.items()}\n",
        ),
    ]

    for module_id, name, description, code in templates:
        item = (
            db.query(AlgorithmTemplate)
            .filter(AlgorithmTemplate.teacher_id == teacher_id, AlgorithmTemplate.module_id == module_id, AlgorithmTemplate.name == name)
            .first()
        )
        if item is None:
            db.add(
                AlgorithmTemplate(
                    module_id=module_id,
                    name=name,
                    description=description,
                    code=code,
                    teacher_id=teacher_id,
                )
            )
        else:
            item.description = description
            item.code = code


def init_database():
    print("Creating database tables...")
    create_tables()
    print("Tables created successfully!")

    print("Ensuring default seed data...")
    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    init_database()
