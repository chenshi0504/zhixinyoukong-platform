"""Default cloud seed data for the teaching demo environment."""

import re
from sqlalchemy.orm import Session

from .models.analytics import Analytics
from .models.classroom import Class, student_classes
from .models.license import License
from .models.organization import Organization
from .models.password import PasswordChangeRequest, PasswordHistory
from .models.report import Report
from .models.message import Message, MessageRead
from .models.self_algorithm import SelfAlgorithmSubmission
from .models.sync_log import SyncLog
from .models.task import Task
from .models.user import RefreshToken, User
from .services.auth import hash_password


ORG_NAME = "大连理工大学"
CLASS_NAME = "交通工程2024级1班"
DEFAULT_PASSWORD = "123456"
DEFAULT_USERNAMES = ("admin", "teacher", "student")
LEGACY_USERNAMES = ("admin01", "teacher01", "student01")
LEGACY_ORG_NAMES = ("示例机构", "测试机构")
GENERATED_USERNAME_RE = re.compile(r"^(admin|teacher|student)\d+$")

DEFAULT_TASK_CASES = [
    {
        "title": "多源数据融合自研算法任务",
        "module_id": "data_fusion",
        "description": "\n".join([
            "【实验场景】路侧视频检测与点云特征融合，验证不同感知源对目标置信度的提升效果。",
            "【基础仿真配置/数据】下载 data_fusion_基础数据包.zip，包含 train_features.csv、test_features.csv、baseline_predictions.csv。",
            "【采用算法】平台 baseline 为贝叶斯决策级融合；学生提交自研融合模型或权重策略。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. 仿真过程文件；4. 仿真结果 CSV，字段包含 frame_id、class_name、prediction_fused_prob。",
            "【软件版本】平台 v1.0；Python 3.10+；基础题包 metadata.json。",
            "【下载链接】/api/v1/self-algorithms/packs/data_fusion/download",
        ]),
    },
    {
        "title": "交通流重构自研算法任务",
        "module_id": "traffic_reconstruction",
        "description": "\n".join([
            "【实验场景】区域路网 OD 反推与路段交通流重构，基于观测流量恢复网络交通状态。",
            "【基础仿真配置/数据】下载 traffic_reconstruction_基础数据包.zip，包含 test_observed_counts.csv、input_link.csv、input_node.csv、input_zone.csv。",
            "【采用算法】平台 baseline 为 DTALite/NEXTA ODME 与交通分配；学生提交自研 OD 反推或修正算法。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. DTALite/NEXTA 过程文件；4. 结果 CSV，字段包含 link_id、time_interval、simulated_link_count。",
            "【软件版本】平台 v1.0；Python 3.10+；DTALite/NEXTA 内置版。",
            "【下载链接】/api/v1/self-algorithms/packs/traffic_reconstruction/download",
        ]),
    },
    {
        "title": "交通流预测自研算法任务",
        "module_id": "traffic_prediction",
        "description": "\n".join([
            "【实验场景】短时交通流预测，基于历史流量、速度和时间特征预测测试样本总流量。",
            "【基础仿真配置/数据】下载 traffic_prediction_基础数据包.zip，包含 raw_traffic_flow.csv、train.csv、test_features.csv。",
            "【采用算法】平台 baseline 为 DecisionTreeRegressor(max_depth=10, random_state=42)。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. 训练/预测过程日志；4. 结果 CSV，字段包含 sample_id、prediction_total_flow。",
            "【软件版本】平台 v1.0；Python 3.10+；scikit-learn 环境。",
            "【下载链接】/api/v1/self-algorithms/packs/traffic_prediction/download",
        ]),
    },
    {
        "title": "交通信号优化自研算法任务",
        "module_id": "signal_optimization",
        "description": "\n".join([
            "【实验场景】单点交叉口信号配时优化，在给定相位约束下输出周期与绿灯时间。",
            "【基础仿真配置/数据】下载 signal_optimization_基础数据包.zip，包含 scenario_config.json、baseline_solution.csv。",
            "【采用算法】平台 baseline 为 Webster 配时；学生可提交遗传算法、启发式搜索或自研配时算法。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. SUMO/算法运行过程文件；4. 结果 CSV/JSON，字段包含 cycle、phase_id、green_time。",
            "【软件版本】平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+。",
            "【下载链接】/api/v1/self-algorithms/packs/signal_optimization/download",
        ]),
    },
    {
        "title": "路径诱导自研算法任务",
        "module_id": "path_guidance",
        "description": "\n".join([
            "【实验场景】SiouxFalls 路网 OD 路径诱导，计算候选路径并降低拥堵路段负荷。",
            "【基础仿真配置/数据】下载 path_guidance_基础数据包.zip，包含 network_edges.csv、od_pairs.csv、baseline_paths.csv。",
            "【采用算法】平台 baseline 为最短路/KSP；学生实现动态路径诱导、拥堵惩罚或 CAV 重分配策略。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. SUMO 路径诱导过程文件；4. 结果 CSV，字段包含 origin、destination、path、total_cost。",
            "【软件版本】平台 v1.0；Python 3.10；SUMO 1.15+。",
            "【下载链接】/api/v1/self-algorithms/packs/path_guidance/download",
        ]),
    },
    {
        "title": "车速控制自研算法任务",
        "module_id": "vehicle_speed_control",
        "description": "\n".join([
            "【实验场景】车辆速度控制与跟驰稳定性评估，比较延误、速度波动和通行效率。",
            "【基础仿真配置/数据】下载 vehicle_speed_control_基础数据包.zip，包含 scenario.json、baseline_metrics.csv。",
            "【采用算法】平台 baseline 为 PID/规则控制；学生提交 MPC、强化学习或自研速度控制策略。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. SUMO/CARLA 控制过程记录；4. 结果 CSV，字段包含 algorithm、average_delay、avg_speed、speed_std、avg_accel、throughput。",
            "【软件版本】平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+；可选 CARLA 0.9.13+。",
            "【下载链接】/api/v1/self-algorithms/packs/vehicle_speed_control/download",
        ]),
    },
    {
        "title": "三层级协同优化自研算法任务",
        "module_id": "coordination_control",
        "description": "\n".join([
            "【实验场景】信号优化、路径诱导、车速控制三层级协同，对比无协同、局部协同和全协同。",
            "【基础仿真配置/数据】下载 coordination_control_基础数据包.zip，包含 baseline_none.json、baseline_local.json、baseline_full.json。",
            "【采用算法】平台 baseline 为全协同控制；学生组合信号配时、路径诱导和车速控制策略。",
            "【需要上传】1. 自研代码 .py；2. 方案说明；3. SUMO 协同控制过程文件与决策日志；4. 结果 CSV，字段包含 step、avg_speed、waiting_count。",
            "【软件版本】平台 v1.0；Python 3.10+；SUMO 1.15+/1.19+。",
            "【下载链接】/api/v1/self-algorithms/packs/coordination_control/download",
        ]),
    },
]


def _ensure_default_tasks(db: Session, *, org: Organization, teacher: User, classroom: Class) -> None:
    for item in DEFAULT_TASK_CASES:
        task = (
            db.query(Task)
            .filter(Task.title == item["title"], Task.class_id == classroom.id)
            .first()
        )
        if task is None:
            task = Task(title=item["title"], class_id=classroom.id)
            db.add(task)
        task.description = item["description"]
        task.module_id = item["module_id"]
        task.teacher_id = teacher.id
        task.org_id = org.id
        task.max_score = 100
        task.status = "published"


def _get_or_create_org(db: Session) -> Organization:
    org = db.query(Organization).filter(Organization.name == ORG_NAME).first()
    if org is None:
        org = Organization(
            name=ORG_NAME,
            contact_name="交通工程教学团队",
            address="辽宁省大连市甘井子区凌工路2号",
            license_quota=100,
        )
        db.add(org)
        db.flush()
    else:
        org.contact_name = org.contact_name or "交通工程教学团队"
        org.address = org.address or "辽宁省大连市甘井子区凌工路2号"
        org.license_quota = max(org.license_quota or 0, 100)
    return org


def _ensure_user(
    db: Session,
    *,
    username: str,
    role: str,
    real_name: str,
    org_id: int | None,
) -> User:
    user = db.query(User).filter(User.username == username).first()
    password_hash = hash_password(DEFAULT_PASSWORD)
    if user is None:
        user = User(username=username, password_hash=password_hash)
        db.add(user)
        db.flush()
    else:
        user.password_hash = password_hash
    user.role = role
    user.real_name = real_name
    user.org_id = org_id
    user.is_active = True
    return user


def _cleanup_legacy_demo_data(db: Session) -> None:
    legacy_users = db.query(User).filter(User.username.in_(LEGACY_USERNAMES)).all()
    legacy_user_ids = [user.id for user in legacy_users]
    if legacy_user_ids:
        db.query(RefreshToken).filter(RefreshToken.user_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.query(PasswordChangeRequest).filter(
            PasswordChangeRequest.user_id.in_(legacy_user_ids)
        ).delete(synchronize_session=False)
        db.query(PasswordChangeRequest).filter(
            PasswordChangeRequest.reviewed_by_id.in_(legacy_user_ids)
        ).update({"reviewed_by_id": None}, synchronize_session=False)
        db.query(PasswordHistory).filter(
            PasswordHistory.user_id.in_(legacy_user_ids)
        ).delete(synchronize_session=False)
        db.query(PasswordHistory).filter(
            PasswordHistory.changed_by_id.in_(legacy_user_ids)
        ).update({"changed_by_id": None}, synchronize_session=False)
        db.query(Class).filter(Class.teacher_id.in_(legacy_user_ids)).update(
            {"teacher_id": None}, synchronize_session=False
        )
        db.query(MessageRead).filter(MessageRead.user_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.query(Message).filter(Message.sender_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.execute(student_classes.delete().where(student_classes.c.student_id.in_(legacy_user_ids)))
        db.query(SelfAlgorithmSubmission).filter(SelfAlgorithmSubmission.student_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        db.query(Report).filter(Report.grader_id.in_(legacy_user_ids)).update({"grader_id": None}, synchronize_session=False)
        db.query(Report).filter(Report.student_id.in_(legacy_user_ids)).delete(synchronize_session=False)
        legacy_task_ids = [
            row.id for row in db.query(Task.id).filter(Task.teacher_id.in_(legacy_user_ids)).all()
        ]
        if legacy_task_ids:
            db.query(Report).filter(Report.task_id.in_(legacy_task_ids)).delete(synchronize_session=False)
            db.query(Task).filter(Task.id.in_(legacy_task_ids)).delete(synchronize_session=False)
        db.query(User).filter(User.id.in_(legacy_user_ids)).delete(synchronize_session=False)

    for org in db.query(Organization).filter(Organization.name.in_(LEGACY_ORG_NAMES)).all():
        if not org.users and not getattr(org, "classes", []):
            db.delete(org)


def _looks_like_test_org(name: str | None) -> bool:
    text = (name or "").strip()
    if not text:
        return True
    if text == ORG_NAME:
        return False
    markers = ("示例", "测试", "自研算法", "本地代理", "密码审批", "?")
    return any(marker in text for marker in markers)


def _delete_cloud_demo_data(db: Session, *, org: Organization, classroom: Class) -> None:
    """Remove previous generated test data while keeping the default teaching demo."""
    protected_names = set(DEFAULT_USERNAMES)
    target_org_ids = {
        row.id
        for row in db.query(Organization.id, Organization.name).all()
        if row.id != org.id and _looks_like_test_org(row.name)
    }

    target_user_ids = set()
    for user in db.query(User).all():
        if user.username in protected_names:
            continue
        if user.username in LEGACY_USERNAMES:
            target_user_ids.add(user.id)
        elif GENERATED_USERNAME_RE.match(user.username or ""):
            target_user_ids.add(user.id)
        elif user.org_id in target_org_ids:
            target_user_ids.add(user.id)

    target_class_ids = set()
    for item in db.query(Class).all():
        if item.id == classroom.id:
            continue
        name = item.name or ""
        if (
            item.org_id in target_org_ids
            or item.teacher_id in target_user_ids
            or item.org_id is None
            or any(marker in name for marker in ("示例", "测试", "自研", "本地代理", "密码审批", "?"))
        ):
            target_class_ids.add(item.id)

    target_task_ids = {
        row.id
        for row in db.query(Task.id).filter(
            (Task.teacher_id.in_(target_user_ids))
            | (Task.class_id.in_(target_class_ids))
            | (Task.org_id.in_(target_org_ids))
        )
    }

    target_message_ids = {
        row.id
        for row in db.query(Message.id).filter(
            (Message.sender_id.in_(target_user_ids))
            | (Message.class_id.in_(target_class_ids))
            | (Message.org_id.in_(target_org_ids))
        )
    }

    license_ids = {
        row.id for row in db.query(License.id).filter(License.org_id.in_(target_org_ids))
    }

    if target_message_ids:
        db.query(MessageRead).filter(MessageRead.message_id.in_(target_message_ids)).delete(synchronize_session=False)
    if target_user_ids:
        db.query(MessageRead).filter(MessageRead.user_id.in_(target_user_ids)).delete(synchronize_session=False)

        db.query(RefreshToken).filter(RefreshToken.user_id.in_(target_user_ids)).delete(synchronize_session=False)
        db.query(PasswordChangeRequest).filter(
            PasswordChangeRequest.user_id.in_(target_user_ids)
        ).delete(synchronize_session=False)
        db.query(PasswordChangeRequest).filter(
            PasswordChangeRequest.reviewed_by_id.in_(target_user_ids)
        ).update({"reviewed_by_id": None}, synchronize_session=False)
        db.query(PasswordHistory).filter(PasswordHistory.user_id.in_(target_user_ids)).delete(synchronize_session=False)
        db.query(PasswordHistory).filter(
            PasswordHistory.changed_by_id.in_(target_user_ids)
        ).update({"changed_by_id": None}, synchronize_session=False)
        db.query(Report).filter(Report.grader_id.in_(target_user_ids)).update({"grader_id": None}, synchronize_session=False)

    if target_task_ids:
        db.query(Report).filter(Report.task_id.in_(target_task_ids)).delete(synchronize_session=False)
    if target_user_ids:
        db.query(Report).filter(Report.student_id.in_(target_user_ids)).delete(synchronize_session=False)

    if target_org_ids:
        db.query(SelfAlgorithmSubmission).filter(SelfAlgorithmSubmission.org_id.in_(target_org_ids)).delete(synchronize_session=False)
        db.query(Analytics).filter(Analytics.org_id.in_(target_org_ids)).delete(synchronize_session=False)
    if target_class_ids:
        db.query(SelfAlgorithmSubmission).filter(SelfAlgorithmSubmission.class_id.in_(target_class_ids)).delete(synchronize_session=False)
    if target_user_ids:
        db.query(SelfAlgorithmSubmission).filter(SelfAlgorithmSubmission.student_id.in_(target_user_ids)).delete(synchronize_session=False)

    if target_message_ids:
        db.query(Message).filter(Message.id.in_(target_message_ids)).delete(synchronize_session=False)
    if target_task_ids:
        db.query(Task).filter(Task.id.in_(target_task_ids)).delete(synchronize_session=False)

    if target_class_ids:
        db.execute(student_classes.delete().where(student_classes.c.class_id.in_(target_class_ids)))
    if target_user_ids:
        db.execute(student_classes.delete().where(student_classes.c.student_id.in_(target_user_ids)))
        db.query(Class).filter(Class.teacher_id.in_(target_user_ids)).update({"teacher_id": None}, synchronize_session=False)
    if target_class_ids:
        db.query(Class).filter(Class.id.in_(target_class_ids)).delete(synchronize_session=False)

    if license_ids:
        db.query(SyncLog).filter(SyncLog.license_id.in_(license_ids)).delete(synchronize_session=False)
        db.query(Analytics).filter(Analytics.license_id.in_(license_ids)).delete(synchronize_session=False)
        db.query(License).filter(License.id.in_(license_ids)).delete(synchronize_session=False)

    if target_user_ids:
        db.query(User).filter(User.id.in_(target_user_ids)).delete(synchronize_session=False)
    if target_org_ids:
        db.query(Organization).filter(Organization.id.in_(target_org_ids)).delete(synchronize_session=False)


def seed_default_users(db: Session) -> None:
    _cleanup_legacy_demo_data(db)

    org = _get_or_create_org(db)
    admin = _ensure_user(db, username="admin", role="super_admin", real_name="平台管理员", org_id=None)
    teacher = _ensure_user(
        db,
        username="teacher",
        role="teacher",
        real_name="大连理工大学教师",
        org_id=org.id,
    )
    student = _ensure_user(
        db,
        username="student",
        role="student",
        real_name="李明",
        org_id=org.id,
    )
    db.flush()

    cls = db.query(Class).filter(Class.name == CLASS_NAME, Class.org_id == org.id).first()
    if cls is None:
        cls = Class(
            name=CLASS_NAME,
            org_id=org.id,
            teacher_id=teacher.id,
            description="大连理工大学交通工程课程真实教学班级",
        )
        db.add(cls)
        db.flush()
    else:
        cls.teacher_id = teacher.id
        cls.description = cls.description or "大连理工大学交通工程课程真实教学班级"

    enrolled = db.execute(
        student_classes.select().where(
            student_classes.c.student_id == student.id,
            student_classes.c.class_id == cls.id,
        )
    ).first()
    if enrolled is None:
        db.execute(student_classes.insert().values(student_id=student.id, class_id=cls.id))

    db.flush()
    _delete_cloud_demo_data(db, org=org, classroom=cls)
    admin.org_id = None
    teacher.org_id = org.id
    student.org_id = org.id
    cls.teacher_id = teacher.id
    _ensure_default_tasks(db, org=org, teacher=teacher, classroom=cls)
    for legacy_org in db.query(Organization).filter(Organization.name.in_(LEGACY_ORG_NAMES)).all():
        if not legacy_org.users and not getattr(legacy_org, "classes", []):
            db.delete(legacy_org)

    db.commit()
    print(
        "[seed] 默认账号已就绪: admin / teacher / student，密码均为 123456；"
        "机构：大连理工大学；班级：交通工程2024级1班"
    )
