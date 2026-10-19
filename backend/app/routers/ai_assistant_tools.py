"""
AI助手工具集 - 提供数据库查询和系统状态检查能力
支持Function Calling，让AI助手能够主动查询数据
"""
import os
import json
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from ..models import (
    User, UserRole,
    Task, TaskStatus,
    ExperimentRecord, ExperimentStatus,
    Report, ReportStatus
)
from ..paths import RUNTIME_DATA_DIR, PROJECT_ROOT

logger = logging.getLogger(__name__)


class ToolCallLogger:
    """工具调用日志记录器"""

    @staticmethod
    def log_call(user_id: int, tool_name: str, parameters: Dict[str, Any],
                 result: Dict[str, Any], duration_ms: float):
        """记录工具调用"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "success": result.get("success", False),
            "duration_ms": round(duration_ms, 2)
        }

        if not result.get("success"):
            log_entry["error"] = result.get("error")

        logger.info(f"工具调用: {json.dumps(log_entry, ensure_ascii=False)}")

        # 可选：写入专门的工具调用日志文件
        try:
            log_dir = os.path.join(RUNTIME_DATA_DIR, "backend", "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_file = os.path.join(log_dir, "tool_calls.log")

            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"写入工具调用日志失败: {e}")


class AIAssistantTools:
    """AI助手工具集"""

    # 模块ID到中文名称的映射
    MODULE_NAMES = {
        'data_collection': '数据采集',
        'data_fusion': '数据融合',
        'traffic_reconstruction': '交通流重构',
        'traffic_prediction': '交通流预测',
        'signal_optimization': '信号优化',
        'path_guidance': '路径诱导',
        'speed_control': '车速控制',
        'vehicle_speed_control': '车速控制',
        'three_level_control': '三层级协同控制',
        'cooperative_control': '三层级协同控制',
        'hierarchical_control': '分层控制',
        'carla_simulation': 'CARLA仿真',
    }

    # 算法子服务健康检查地址。
    # 说明：数据融合 / 交通流预测 / 数据采集 现在由主后端进程内的会话隔离路由
    # 直接提供（app/routers/data_fusion_runtime.py、traffic_prediction.py、
    # data_collection_session.py），不再是独立端口的子服务；独立子服务只剩
    # 5001（交通流重构，转发到主后端）与 8001（SUMO 仿真算法测试）。
    # 旧表里的 5000/5002/5003 在本仓库已无任何监听者。
    ALGORITHM_HEALTH_URLS = {
        'traffic_reconstruction': 'http://127.0.0.1:5001/api/health',
        'simulation': 'http://127.0.0.1:8001/health',
    }

    def __init__(self, db: Session, current_user: User):
        """
        初始化工具集

        Args:
            db: 数据库会话
            current_user: 当前登录用户
        """
        self.db = db
        self.current_user = current_user
        self.logger = ToolCallLogger()

    def _execute_with_logging(self, tool_name: str, parameters: Dict[str, Any], func):
        """
        执行工具并记录日志

        Args:
            tool_name: 工具名称
            parameters: 工具参数
            func: 要执行的函数

        Returns:
            工具执行结果
        """
        start_time = time.time()
        try:
            result = func()
            duration_ms = (time.time() - start_time) * 1000
            self.logger.log_call(self.current_user.id, tool_name, parameters, result, duration_ms)
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_result = {"success": False, "error": f"工具执行异常: {str(e)}"}
            self.logger.log_call(self.current_user.id, tool_name, parameters, error_result, duration_ms)
            logger.error(f"工具 {tool_name} 执行失败: {e}", exc_info=True)
            return error_result

    def query_experiment_history(
        self,
        student_id: Optional[int] = None,
        module_id: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        查询学生的实验历史记录

        Args:
            student_id: 学生ID（可选，默认为当前用户）
            module_id: 实验模块ID（可选）
            limit: 返回记录数量限制

        Returns:
            包含实验记录列表的字典
        """
        parameters = {"student_id": student_id, "module_id": module_id, "limit": limit}

        def execute():
            # 权限检查：学生只能查询自己的记录
            target_student_id = student_id if student_id is not None else self.current_user.id

            if target_student_id != self.current_user.id:
                if self.current_user.role == UserRole.STUDENT.value:
                    return {
                        "success": False,
                        "error": "学生只能查询自己的实验记录"
                    }

            # 构建查询
            query = self.db.query(ExperimentRecord).filter(
                ExperimentRecord.student_id == target_student_id
            )

            # 按模块过滤
            if module_id:
                query = query.filter(ExperimentRecord.module_id == module_id)

            # 按时间倒序排列
            query = query.order_by(ExperimentRecord.started_at.desc())

            # 获取总数
            total = query.count()

            # 限制返回数量
            records = query.limit(limit).all()

            # 格式化结果
            data = []
            for record in records:
                # 计算实验时长
                duration_minutes = None
                if record.completed_at and record.started_at:
                    duration = record.completed_at - record.started_at
                    duration_minutes = int(duration.total_seconds() / 60)

                # 解析结果数据
                result_summary = "无结果数据"
                if record.result_data:
                    try:
                        result_json = json.loads(record.result_data)
                        # 尝试提取关键指标
                        if isinstance(result_json, dict):
                            metrics = result_json.get('metrics', {})
                            if metrics:
                                result_summary = ", ".join([
                                    f"{k}: {v}" for k, v in list(metrics.items())[:3]
                                ])
                    except:
                        result_summary = "结果数据解析失败"

                # 获取任务标题
                task_title = None
                if record.task:
                    task_title = record.task.title

                data.append({
                    "id": record.id,
                    "module_id": record.module_id,
                    "module_name": self.MODULE_NAMES.get(record.module_id, record.module_id),
                    "status": record.status,
                    "started_at": record.started_at.strftime("%Y-%m-%d %H:%M:%S") if record.started_at else None,
                    "completed_at": record.completed_at.strftime("%Y-%m-%d %H:%M:%S") if record.completed_at else None,
                    "duration_minutes": duration_minutes,
                    "task_title": task_title,
                    "result_summary": result_summary
                })

            return {
                "success": True,
                "data": data,
                "total": total
            }

        return self._execute_with_logging("query_experiment_history", parameters, execute)

    def query_task_info(self, task_id: int) -> Dict[str, Any]:
        """
        查询实验任务详情

        Args:
            task_id: 任务ID

        Returns:
            包含任务详情的字典
        """
        parameters = {"task_id": task_id}

        def execute():
            # 查询任务
            task = self.db.query(Task).filter(Task.id == task_id).first()

            if not task:
                return {
                    "success": False,
                    "error": "任务不存在"
                }

            # 权限检查：学生只能查看已发布的任务
            if self.current_user.role == UserRole.STUDENT.value:
                if task.status != TaskStatus.PUBLISHED.value:
                    return {
                        "success": False,
                        "error": "任务未发布或已关闭"
                    }

            # 统计提交情况
            submission_count = self.db.query(Report).filter(
                Report.task_id == task_id
            ).count()

            # 查询当前用户的提交状态
            my_submission_status = "未提交"
            if self.current_user.role == UserRole.STUDENT.value:
                my_report = self.db.query(Report).filter(
                    and_(
                        Report.task_id == task_id,
                        Report.student_id == self.current_user.id
                    )
                ).first()

                if my_report:
                    if my_report.status == ReportStatus.GRADED.value:
                        my_submission_status = f"已批改 ({my_report.score}分)"
                    elif my_report.status == ReportStatus.SUBMITTED.value:
                        my_submission_status = "已提交待批改"
                    else:
                        my_submission_status = "草稿"

            # 格式化结果
            data = {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "module_id": task.module_id,
                "module_name": self.MODULE_NAMES.get(task.module_id, task.module_id) if task.module_id else None,
                "teacher_name": task.teacher.real_name or task.teacher.username if task.teacher else None,
                "deadline": task.deadline.strftime("%Y-%m-%d %H:%M:%S") if task.deadline else None,
                "status": task.status,
                "scoring_criteria": task.scoring_criteria,
                "created_at": task.created_at.strftime("%Y-%m-%d %H:%M:%S") if task.created_at else None,
                "submission_count": submission_count,
                "my_submission_status": my_submission_status
            }

            return {
                "success": True,
                "data": data
            }

        return self._execute_with_logging("query_task_info", parameters, execute)

    def query_class_statistics(
        self,
        class_name: Optional[str] = None,
        module_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        查询班级实验统计数据

        Args:
            class_name: 班级名称（可选，默认为当前用户所在班级）
            module_id: 实验模块ID（可选）

        Returns:
            包含班级统计数据的字典
        """
        try:
            # 确定要查询的班级
            if class_name is None:
                class_name = self.current_user.class_name
                if not class_name:
                    return {
                        "success": False,
                        "error": "当前用户未分配班级"
                    }

            # 权限检查：学生只能查询自己的班级
            if self.current_user.role == UserRole.STUDENT.value:
                if class_name != self.current_user.class_name:
                    return {
                        "success": False,
                        "error": "学生只能查询自己班级的统计数据"
                    }

            # 查询班级学生
            students = self.db.query(User).filter(
                and_(
                    User.class_name == class_name,
                    User.role == UserRole.STUDENT.value
                )
            ).all()

            if not students:
                return {
                    "success": False,
                    "error": "班级不存在或没有学生"
                }

            student_ids = [s.id for s in students]

            # 构建实验记录查询
            query = self.db.query(ExperimentRecord).filter(
                ExperimentRecord.student_id.in_(student_ids)
            )

            # 按模块过滤
            if module_id:
                query = query.filter(ExperimentRecord.module_id == module_id)

            # 统计数据
            all_records = query.all()
            completed_records = [r for r in all_records if r.status == ExperimentStatus.COMPLETED]
            in_progress_records = [r for r in all_records if r.status == ExperimentStatus.IN_PROGRESS]

            # 计算完成率
            total_students = len(students)
            students_with_completed = len(set(r.student_id for r in completed_records))
            completion_rate = students_with_completed / total_students if total_students > 0 else 0

            # 计算平均时长
            durations = []
            for record in completed_records:
                if record.completed_at and record.started_at:
                    duration = record.completed_at - record.started_at
                    durations.append(duration.total_seconds() / 60)

            average_duration = sum(durations) / len(durations) if durations else 0

            # 查询报告分数（如果有模块限制，只统计该模块的任务）
            report_query = self.db.query(Report).filter(
                and_(
                    Report.student_id.in_(student_ids),
                    Report.status == ReportStatus.GRADED.value,
                    Report.score.isnot(None)
                )
            )

            if module_id:
                # 通过task关联过滤模块
                report_query = report_query.join(Task).filter(Task.module_id == module_id)

            graded_reports = report_query.all()
            scores = [r.score for r in graded_reports if r.score is not None]
            average_score = sum(scores) / len(scores) if scores else None

            # 获取前3名（仅教师和管理员可见）
            top_performers = []
            if self.current_user.role in [UserRole.TEACHER.value, UserRole.ADMIN.value]:
                if graded_reports:
                    # 按学生分组，取每个学生的最高分
                    student_scores = {}
                    for report in graded_reports:
                        if report.student_id not in student_scores or report.score > student_scores[report.student_id]['score']:
                            student = next((s for s in students if s.id == report.student_id), None)
                            if student:
                                student_scores[report.student_id] = {
                                    'student_name': student.real_name or student.username,
                                    'score': report.score
                                }

                    # 排序并取前3名
                    top_performers = sorted(
                        student_scores.values(),
                        key=lambda x: x['score'],
                        reverse=True
                    )[:3]

            # 格式化结果
            data = {
                "class_name": class_name,
                "total_students": total_students,
                "module_id": module_id,
                "module_name": self.MODULE_NAMES.get(module_id, module_id) if module_id else "全部模块",
                "statistics": {
                    "completed_count": len(completed_records),
                    "in_progress_count": len(in_progress_records),
                    "not_started_count": total_students - students_with_completed,
                    "completion_rate": round(completion_rate, 3),
                    "average_duration_minutes": round(average_duration, 1) if average_duration > 0 else None,
                    "average_score": round(average_score, 1) if average_score is not None else None
                },
                "top_performers": top_performers
            }

            return {
                "success": True,
                "data": data
            }

        except Exception as e:
            logger.error(f"查询班级统计失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"查询失败: {str(e)}"
            }

    def check_algorithm_status(self, module_id: str) -> Dict[str, Any]:
        """
        查看算法服务运行状态

        Args:
            module_id: 算法模块ID

        Returns:
            包含服务状态信息的字典
        """
        try:
            # 检查模块是否存在
            if module_id not in self.MODULE_NAMES:
                return {
                    "success": False,
                    "error": f"未知的算法模块: {module_id}"
                }

            module_name = self.MODULE_NAMES[module_id]
            health_url = self.ALGORITHM_HEALTH_URLS.get(module_id)

            # 如果模块没有独立服务，返回不适用
            if not health_url:
                return {
                    "success": True,
                    "data": {
                        "module_id": module_id,
                        "module_name": module_name,
                        "status": "no_service",
                        "message": "该模块由主后端进程内的会话隔离路由直接提供，不需要独立服务"
                    }
                }

            # 尝试检查服务健康状态
            try:
                import httpx

                with httpx.Client(timeout=2.0) as client:
                    start_time = datetime.now()
                    response = client.get(health_url)
                    response_time = (datetime.now() - start_time).total_seconds() * 1000

                    if response.status_code == 200:
                        return {
                            "success": True,
                            "data": {
                                "module_id": module_id,
                                "module_name": module_name,
                                "status": "running",
                                "port": port,
                                "health_check": {
                                    "status": "healthy",
                                    "response_time_ms": round(response_time, 1),
                                    "last_check": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                },
                                "recent_errors": []
                            }
                        }
                    else:
                        return {
                            "success": True,
                            "data": {
                                "module_id": module_id,
                                "module_name": module_name,
                                "status": "error",
                                "port": port,
                                "error_message": f"服务返回异常状态码: {response.status_code}"
                            }
                        }

            except Exception as e:
                return {
                    "success": True,
                    "data": {
                        "module_id": module_id,
                        "module_name": module_name,
                        "status": "stopped",
                        "port": port,
                        "error_message": f"无法连接到服务: {str(e)}"
                    }
                }

        except Exception as e:
            logger.error(f"检查算法状态失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"检查失败: {str(e)}"
            }

    def read_experiment_output(
        self,
        experiment_id: int,
        file_type: str = "result"
    ) -> Dict[str, Any]:
        """
        读取实验输出结果

        Args:
            experiment_id: 实验记录ID
            file_type: 文件类型 ('log', 'result', 'visualization')

        Returns:
            包含实验输出内容的字典
        """
        try:
            # 查询实验记录
            record = self.db.query(ExperimentRecord).filter(
                ExperimentRecord.id == experiment_id
            ).first()

            if not record:
                return {
                    "success": False,
                    "error": "实验记录不存在"
                }

            # 权限检查：学生只能查看自己的实验
            if self.current_user.role == UserRole.STUDENT.value:
                if record.student_id != self.current_user.id:
                    return {
                        "success": False,
                        "error": "无权查看其他学生的实验结果"
                    }

            # 根据文件类型返回不同内容
            if file_type == "result":
                # 返回结构化结果数据
                content = {}
                if record.result_data:
                    try:
                        content = json.loads(record.result_data)
                    except:
                        content = {"raw": record.result_data}

                # 查找输出文件
                output_files = []
                algo_output_dir = os.path.join(RUNTIME_DATA_DIR, "backend", "algorithms", record.module_id, "output")
                if os.path.exists(algo_output_dir):
                    try:
                        for file in os.listdir(algo_output_dir):
                            if str(experiment_id) in file:
                                output_files.append(file)
                    except:
                        pass

                return {
                    "success": True,
                    "data": {
                        "experiment_id": experiment_id,
                        "file_type": "result",
                        "content": content,
                        "output_files": output_files,
                        "has_errors": False
                    }
                }

            elif file_type == "log":
                # 返回操作日志
                log_content = "无日志记录"
                if record.operation_log:
                    try:
                        log_data = json.loads(record.operation_log)
                        if isinstance(log_data, list):
                            log_content = "\n".join(log_data[-50:])  # 最后50条
                        else:
                            log_content = str(log_data)
                    except:
                        log_content = record.operation_log

                # 尝试读取文件日志
                log_file_path = os.path.join(
                    RUNTIME_DATA_DIR, "backend", "logs",
                    f"{record.module_id}_{experiment_id}.log"
                )

                if os.path.exists(log_file_path):
                    try:
                        with open(log_file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            log_content = "".join(lines[-500:])  # 最后500行
                    except:
                        pass

                return {
                    "success": True,
                    "data": {
                        "experiment_id": experiment_id,
                        "file_type": "log",
                        "content": log_content,
                        "has_errors": "error" in log_content.lower() or "failed" in log_content.lower()
                    }
                }

            elif file_type == "visualization":
                # 返回可视化文件路径
                viz_files = []
                algo_output_dir = os.path.join(RUNTIME_DATA_DIR, "backend", "algorithms", record.module_id, "output")

                if os.path.exists(algo_output_dir):
                    try:
                        for file in os.listdir(algo_output_dir):
                            if str(experiment_id) in file and file.endswith(('.png', '.jpg', '.html', '.pdf')):
                                viz_files.append(os.path.join(algo_output_dir, file))
                    except:
                        pass

                return {
                    "success": True,
                    "data": {
                        "experiment_id": experiment_id,
                        "file_type": "visualization",
                        "files": viz_files,
                        "count": len(viz_files)
                    }
                }

            else:
                return {
                    "success": False,
                    "error": f"不支持的文件类型: {file_type}"
                }

        except Exception as e:
            logger.error(f"读取实验输出失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"读取失败: {str(e)}"
            }

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        获取可用工具列表（用于Function Calling）

        Returns:
            工具定义列表
        """
        return [
            {
                "name": "query_experiment_history",
                "description": "查询学生的实验历史记录，可以按模块过滤。适用于回答'我做过哪些实验'、'我的实验记录'等问题。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "student_id": {
                            "type": "integer",
                            "description": "学生ID（可选，默认为当前用户）"
                        },
                        "module_id": {
                            "type": "string",
                            "description": "实验模块ID（可选），如'signal_optimization'、'data_collection'等"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回记录数量限制，默认10",
                            "default": 10
                        }
                    }
                }
            },
            {
                "name": "query_task_info",
                "description": "查询实验任务的详细信息，包括任务要求、截止时间、评分标准等。适用于回答'任务要求是什么'、'截止时间'等问题。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "integer",
                            "description": "任务ID"
                        }
                    },
                    "required": ["task_id"]
                }
            },
            {
                "name": "query_class_statistics",
                "description": "查询班级的实验统计数据，包括完成率、平均分等。适用于回答'班级完成情况'、'班级平均分'等问题。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "class_name": {
                            "type": "string",
                            "description": "班级名称（可选，默认为当前用户所在班级）"
                        },
                        "module_id": {
                            "type": "string",
                            "description": "实验模块ID（可选）"
                        }
                    }
                }
            },
            {
                "name": "check_algorithm_status",
                "description": "检查算法服务的运行状态。适用于回答'服务是否在运行'、'为什么实验启动失败'等问题。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "module_id": {
                            "type": "string",
                            "description": "算法模块ID，如'data_collection'、'signal_optimization'等"
                        }
                    },
                    "required": ["module_id"]
                }
            },
            {
                "name": "read_experiment_output",
                "description": "读取实验的输出结果、日志或可视化文件。适用于回答'我的实验结果是什么'、'为什么实验失败'等问题。",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "experiment_id": {
                            "type": "integer",
                            "description": "实验记录ID"
                        },
                        "file_type": {
                            "type": "string",
                            "description": "文件类型：'log'(日志)、'result'(结果)、'visualization'(可视化)",
                            "enum": ["log", "result", "visualization"],
                            "default": "result"
                        }
                    },
                    "required": ["experiment_id"]
                }
            }
        ]
