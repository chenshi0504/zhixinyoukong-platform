"""
AI助手工具集测试
"""
import pytest
from sqlalchemy.orm import Session
from app.models import User, UserRole, Task, TaskStatus, ExperimentRecord, ExperimentStatus
from app.routers.ai_assistant_tools import AIAssistantTools
from datetime import datetime, timedelta


class TestAIAssistantTools:
    """AI助手工具集测试"""

    def test_query_experiment_history_success(self, db: Session, test_student: User):
        """测试查询实验历史 - 成功场景"""
        # 创建测试数据
        record = ExperimentRecord(
            student_id=test_student.id,
            module_id="signal_optimization",
            status=ExperimentStatus.COMPLETED,
            started_at=datetime.now() - timedelta(hours=2),
            completed_at=datetime.now() - timedelta(hours=1),
            result_data='{"metrics": {"delay": 45.2, "improvement": 0.25}}'
        )
        db.add(record)
        db.commit()

        # 执行工具
        tools = AIAssistantTools(db, test_student)
        result = tools.query_experiment_history(limit=10)

        # 验证结果
        assert result["success"] is True
        assert result["total"] >= 1
        assert len(result["data"]) >= 1
        assert result["data"][0]["module_id"] == "signal_optimization"
        assert result["data"][0]["status"] == ExperimentStatus.COMPLETED

    def test_query_experiment_history_permission_denied(self, db: Session, test_student: User, test_teacher: User):
        """测试查询实验历史 - 权限拒绝"""
        # 学生尝试查询其他学生的记录
        tools = AIAssistantTools(db, test_student)
        result = tools.query_experiment_history(student_id=test_teacher.id)

        # 验证结果
        assert result["success"] is False
        assert "权限" in result["error"] or "只能查询自己" in result["error"]

    def test_query_experiment_history_with_module_filter(self, db: Session, test_student: User):
        """测试查询实验历史 - 模块过滤"""
        # 创建不同模块的测试数据
        record1 = ExperimentRecord(
            student_id=test_student.id,
            module_id="signal_optimization",
            status=ExperimentStatus.COMPLETED
        )
        record2 = ExperimentRecord(
            student_id=test_student.id,
            module_id="data_collection",
            status=ExperimentStatus.COMPLETED
        )
        db.add_all([record1, record2])
        db.commit()

        # 执行工具 - 只查询信号优化模块
        tools = AIAssistantTools(db, test_student)
        result = tools.query_experiment_history(module_id="signal_optimization")

        # 验证结果
        assert result["success"] is True
        for record in result["data"]:
            assert record["module_id"] == "signal_optimization"

    def test_query_task_info_success(self, db: Session, test_student: User, test_teacher: User):
        """测试查询任务信息 - 成功场景"""
        # 创建测试任务
        task = Task(
            title="测试任务",
            description="这是一个测试任务",
            module_id="signal_optimization",
            teacher_id=test_teacher.id,
            status=TaskStatus.PUBLISHED.value,
            deadline=datetime.now() + timedelta(days=7)
        )
        db.add(task)
        db.commit()

        # 执行工具
        tools = AIAssistantTools(db, test_student)
        result = tools.query_task_info(task_id=task.id)

        # 验证结果
        assert result["success"] is True
        assert result["data"]["id"] == task.id
        assert result["data"]["title"] == "测试任务"
        assert result["data"]["module_id"] == "signal_optimization"
        assert result["data"]["status"] == TaskStatus.PUBLISHED.value

    def test_query_task_info_not_found(self, db: Session, test_student: User):
        """测试查询任务信息 - 任务不存在"""
        tools = AIAssistantTools(db, test_student)
        result = tools.query_task_info(task_id=99999)

        # 验证结果
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_query_task_info_unpublished(self, db: Session, test_student: User, test_teacher: User):
        """测试查询任务信息 - 学生查看未发布任务"""
        # 创建草稿任务
        task = Task(
            title="草稿任务",
            description="未发布的任务",
            module_id="signal_optimization",
            teacher_id=test_teacher.id,
            status=TaskStatus.DRAFT.value
        )
        db.add(task)
        db.commit()

        # 学生尝试查询
        tools = AIAssistantTools(db, test_student)
        result = tools.query_task_info(task_id=task.id)

        # 验证结果
        assert result["success"] is False
        assert "未发布" in result["error"] or "已关闭" in result["error"]

    def test_query_class_statistics_success(self, db: Session, test_student: User):
        """测试查询班级统计 - 成功场景"""
        # 确保测试学生有班级
        if not test_student.class_name:
            test_student.class_name = "测试班级"
            db.commit()

        # 创建实验记录
        record = ExperimentRecord(
            student_id=test_student.id,
            module_id="signal_optimization",
            status=ExperimentStatus.COMPLETED
        )
        db.add(record)
        db.commit()

        # 执行工具
        tools = AIAssistantTools(db, test_student)
        result = tools.query_class_statistics()

        # 验证结果
        assert result["success"] is True
        assert result["data"]["class_name"] == test_student.class_name
        assert result["data"]["total_students"] >= 1
        assert "statistics" in result["data"]

    def test_query_class_statistics_no_class(self, db: Session, test_student: User):
        """测试查询班级统计 - 用户无班级"""
        # 清除班级信息
        test_student.class_name = None
        db.commit()

        # 执行工具
        tools = AIAssistantTools(db, test_student)
        result = tools.query_class_statistics()

        # 验证结果
        assert result["success"] is False
        assert "未分配班级" in result["error"]

    def test_check_algorithm_status_no_service(self, db: Session, test_student: User):
        """测试检查算法状态 - 无独立服务的模块"""
        tools = AIAssistantTools(db, test_student)
        result = tools.check_algorithm_status(module_id="traffic_prediction")

        # 验证结果
        assert result["success"] is True
        assert result["data"]["status"] == "no_service"

    def test_check_algorithm_status_unknown_module(self, db: Session, test_student: User):
        """测试检查算法状态 - 未知模块"""
        tools = AIAssistantTools(db, test_student)
        result = tools.check_algorithm_status(module_id="unknown_module")

        # 验证结果
        assert result["success"] is False
        assert "未知" in result["error"]

    def test_read_experiment_output_not_found(self, db: Session, test_student: User):
        """测试读取实验输出 - 实验不存在"""
        tools = AIAssistantTools(db, test_student)
        result = tools.read_experiment_output(experiment_id=99999)

        # 验证结果
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_read_experiment_output_permission_denied(self, db: Session, test_student: User, test_teacher: User):
        """测试读取实验输出 - 权限拒绝"""
        # 创建其他学生的实验记录
        other_student = User(
            username="other_student",
            password_hash="hash",
            role=UserRole.STUDENT.value
        )
        db.add(other_student)
        db.commit()

        record = ExperimentRecord(
            student_id=other_student.id,
            module_id="signal_optimization",
            status=ExperimentStatus.COMPLETED
        )
        db.add(record)
        db.commit()

        # 当前学生尝试读取
        tools = AIAssistantTools(db, test_student)
        result = tools.read_experiment_output(experiment_id=record.id)

        # 验证结果
        assert result["success"] is False
        assert "无权" in result["error"]

    def test_get_available_tools(self, db: Session, test_student: User):
        """测试获取可用工具列表"""
        tools = AIAssistantTools(db, test_student)
        tool_list = tools.get_available_tools()

        # 验证结果
        assert len(tool_list) == 5
        tool_names = [t["name"] for t in tool_list]
        assert "query_experiment_history" in tool_names
        assert "query_task_info" in tool_names
        assert "query_class_statistics" in tool_names
        assert "check_algorithm_status" in tool_names
        assert "read_experiment_output" in tool_names

        # 验证工具定义格式
        for tool in tool_list:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "properties" in tool["input_schema"]


# Fixtures
@pytest.fixture
def test_student(db: Session) -> User:
    """创建测试学生用户"""
    user = User(
        username="test_student",
        password_hash="hash",
        role=UserRole.STUDENT.value,
        real_name="测试学生",
        class_name="测试班级"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_teacher(db: Session) -> User:
    """创建测试教师用户"""
    user = User(
        username="test_teacher",
        password_hash="hash",
        role=UserRole.TEACHER.value,
        real_name="测试教师"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
