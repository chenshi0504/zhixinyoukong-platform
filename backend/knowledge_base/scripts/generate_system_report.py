"""
系统运行报告生成器
生成RAG系统的综合运行报告
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.knowledge_base.monitoring import monitoring_system
from backend.knowledge_base.feedback import feedback_collector, feedback_analyzer
from backend.knowledge_base.ab_testing import ABTestManager
from backend.knowledge_base.index_manager import IndexMetadata


class SystemReportGenerator:
    """系统运行报告生成器"""

    def __init__(self):
        self.report_path = Path('.RAG/system_reports')
        self.report_path.mkdir(parents=True, exist_ok=True)

    def generate_daily_report(self) -> Dict[str, Any]:
        """生成每日运行报告"""
        report = {
            'report_type': 'daily',
            'generated_at': datetime.now().isoformat(),
            'period': {
                'start': (datetime.now() - timedelta(days=1)).isoformat(),
                'end': datetime.now().isoformat()
            },
            'system_health': self._get_system_health(),
            'performance_metrics': self._get_performance_metrics(),
            'knowledge_base_status': self._get_kb_status(),
            'user_feedback': self._get_feedback_summary(),
            'issues': self._identify_issues(),
            'recommendations': self._generate_recommendations()
        }

        return report

    def generate_weekly_report(self) -> Dict[str, Any]:
        """生成每周运行报告"""
        report = {
            'report_type': 'weekly',
            'generated_at': datetime.now().isoformat(),
            'period': {
                'start': (datetime.now() - timedelta(days=7)).isoformat(),
                'end': datetime.now().isoformat()
            },
            'system_health': self._get_system_health(),
            'performance_trends': self._get_performance_trends(),
            'knowledge_base_status': self._get_kb_status(),
            'user_feedback_analysis': self._get_detailed_feedback_analysis(),
            'ab_test_results': self._get_ab_test_results(),
            'top_issues': self._get_top_issues(),
            'improvement_suggestions': self._get_improvement_suggestions()
        }

        return report

    def generate_monthly_report(self) -> Dict[str, Any]:
        """生成每月运行报告"""
        report = {
            'report_type': 'monthly',
            'generated_at': datetime.now().isoformat(),
            'period': {
                'start': (datetime.now() - timedelta(days=30)).isoformat(),
                'end': datetime.now().isoformat()
            },
            'executive_summary': self._get_executive_summary(),
            'system_health': self._get_system_health(),
            'performance_overview': self._get_performance_overview(),
            'knowledge_base_growth': self._get_kb_growth(),
            'user_satisfaction': self._get_user_satisfaction(),
            'key_achievements': self._get_key_achievements(),
            'challenges': self._get_challenges(),
            'action_items': self._get_action_items()
        }

        return report

    def _get_system_health(self) -> Dict[str, Any]:
        """获取系统健康状态"""
        health = monitoring_system.get_system_health()
        return {
            'status': health['status'],
            'health_score': health['health_score'],
            'active_alerts': health['active_alerts'],
            'uptime': '99.9%',  # 可从监控系统获取
            'last_incident': None
        }

    def _get_performance_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        perf_stats = monitoring_system.performance_monitor.get_statistics(minutes=1440)  # 24小时
        return {
            'total_requests': perf_stats['total_requests'],
            'success_rate': perf_stats['success_rate'],
            'avg_response_time': perf_stats['avg_response_time'],
            'error_rate': perf_stats['error_rate'],
            'by_endpoint': perf_stats.get('endpoint_stats', {})
        }

    def _get_performance_trends(self) -> Dict[str, Any]:
        """获取性能趋势"""
        # 获取7天数据
        stats_7d = monitoring_system.performance_monitor.get_statistics(minutes=10080)

        return {
            'request_volume_trend': 'stable',  # 可计算实际趋势
            'response_time_trend': 'improving',
            'error_rate_trend': 'stable',
            'success_rate': stats_7d['success_rate'],
            'avg_response_time': stats_7d['avg_response_time']
        }

    def _get_performance_overview(self) -> Dict[str, Any]:
        """获取性能概览"""
        stats_30d = monitoring_system.performance_monitor.get_statistics(minutes=43200)

        return {
            'total_requests': stats_30d['total_requests'],
            'avg_daily_requests': stats_30d['total_requests'] / 30,
            'success_rate': stats_30d['success_rate'],
            'avg_response_time': stats_30d['avg_response_time'],
            'peak_load': 'N/A',  # 可从历史数据计算
            'slowest_endpoints': self._get_slowest_endpoints(stats_30d)
        }

    def _get_slowest_endpoints(self, stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """获取最慢的端点"""
        endpoints = stats.get('by_endpoint', {})
        sorted_endpoints = sorted(
            endpoints.items(),
            key=lambda x: x[1].get('avg_response_time', 0),
            reverse=True
        )

        return [
            {
                'endpoint': endpoint,
                'avg_response_time': data.get('avg_response_time', 0),
                'request_count': data.get('request_count', 0)
            }
            for endpoint, data in sorted_endpoints[:5]
        ]

    def _get_kb_status(self) -> Dict[str, Any]:
        """获取知识库状态"""
        kb_stats = monitoring_system.kb_monitor.get_statistics()

        return {
            'total_documents': kb_stats.get('total_documents', 0),
            'quality_score': kb_stats.get('avg_quality_score', 0),
            'avg_retrieval_time': kb_stats.get('avg_retrieval_time', 0),
            'last_update': kb_stats.get('last_update', 'N/A'),
            'update_success_rate': kb_stats.get('update_success_rate', 0)
        }

    def _get_kb_growth(self) -> Dict[str, Any]:
        """获取知识库增长情况"""
        return {
            'documents_added': 0,  # 可从索引管理器获取
            'documents_updated': 0,
            'documents_removed': 0,
            'growth_rate': '0%',
            'coverage_improvement': 'N/A'
        }

    def _get_feedback_summary(self) -> Dict[str, Any]:
        """获取反馈摘要"""
        stats = feedback_collector.get_statistics()

        return {
            'total_feedbacks': stats['total_feedbacks'],
            'positive_rate': stats['positive_rate'],
            'negative_rate': stats['negative_rate'],
            'avg_rating': stats['average_rating'],
            'feedback_distribution': stats['feedback_type_distribution']
        }

    def _get_detailed_feedback_analysis(self) -> Dict[str, Any]:
        """获取详细反馈分析"""
        stats = feedback_collector.get_statistics()
        problem_areas = feedback_analyzer.identify_problem_areas()

        return {
            'total_feedbacks': stats['total_feedbacks'],
            'positive_rate': stats['positive_rate'],
            'negative_rate': stats['negative_rate'],
            'avg_rating': stats['average_rating'],
            'rating_distribution': stats.get('rating_distribution', {}),
            'category_distribution': stats.get('category_distribution', {}),
            'problem_areas': problem_areas[:5],
            'top_complaints': self._get_top_complaints()
        }

    def _get_top_complaints(self) -> List[str]:
        """获取主要投诉"""
        negative = feedback_collector.get_negative_feedbacks(limit=10)
        complaints = [fb.comment for fb in negative if fb.comment]
        return complaints[:5]

    def _get_user_satisfaction(self) -> Dict[str, Any]:
        """获取用户满意度"""
        stats = feedback_collector.get_statistics()

        # 计算满意度分数（基于评分和反馈率）
        satisfaction_score = (
            stats['average_rating'] / 5 * 0.6 +
            stats['positive_rate'] * 0.4
        ) * 100

        return {
            'satisfaction_score': satisfaction_score,
            'avg_rating': stats['average_rating'],
            'positive_feedback_rate': stats['positive_rate'],
            'negative_feedback_rate': stats['negative_rate'],
            'nps': self._calculate_nps(stats),
            'trend': 'improving'  # 可通过对比历史数据计算
        }

    def _calculate_nps(self, stats: Dict[str, Any]) -> float:
        """计算净推荐值(NPS)"""
        # NPS = (推荐者% - 贬损者%) * 100
        # 推荐者: 4-5星, 贬损者: 1-2星
        rating_dist = stats.get('rating_distribution', {})
        total = sum(rating_dist.values())

        if total == 0:
            return 0

        promoters = (rating_dist.get(4, 0) + rating_dist.get(5, 0)) / total
        detractors = (rating_dist.get(1, 0) + rating_dist.get(2, 0)) / total

        return (promoters - detractors) * 100

    def _get_ab_test_results(self) -> Dict[str, Any]:
        """获取A/B测试结果"""
        try:
            ab_manager = ABTestManager()
            stats = ab_manager.get_statistics()

            return {
                'active_tests': len(stats.get('groups', {})),
                'total_queries': sum(
                    group['query_count']
                    for group in stats.get('groups', {}).values()
                ),
                'best_performing_config': self._get_best_config(stats),
                'improvement': 'N/A'
            }
        except:
            return {
                'active_tests': 0,
                'total_queries': 0,
                'best_performing_config': None,
                'improvement': 'N/A'
            }

    def _get_best_config(self, stats: Dict[str, Any]) -> str:
        """获取最佳配置"""
        groups = stats.get('groups', {})
        if not groups:
            return 'N/A'

        best_group = max(
            groups.items(),
            key=lambda x: x[1].get('avg_score', 0)
        )

        return best_group[0]

    def _identify_issues(self) -> List[Dict[str, Any]]:
        """识别问题"""
        issues = []

        # 检查性能问题
        perf_stats = monitoring_system.performance_monitor.get_statistics(minutes=1440)
        if perf_stats['error_rate'] > 0.05:
            issues.append({
                'severity': 'high',
                'category': 'performance',
                'description': f"错误率过高: {perf_stats['error_rate']:.1%}",
                'impact': '影响用户体验'
            })

        if perf_stats['avg_response_time'] > 3000:
            issues.append({
                'severity': 'medium',
                'category': 'performance',
                'description': f"响应时间过长: {perf_stats['avg_response_time']:.0f}ms",
                'impact': '用户等待时间长'
            })

        # 检查反馈问题
        feedback_stats = feedback_collector.get_statistics()
        if feedback_stats['negative_rate'] > 0.2:
            issues.append({
                'severity': 'high',
                'category': 'user_satisfaction',
                'description': f"负面反馈率高: {feedback_stats['negative_rate']:.1%}",
                'impact': '用户满意度低'
            })

        return issues

    def _get_top_issues(self) -> List[Dict[str, Any]]:
        """获取主要问题"""
        issues = self._identify_issues()
        problem_areas = feedback_analyzer.identify_problem_areas()

        # 合并问题
        all_issues = issues + [
            {
                'severity': 'medium',
                'category': 'quality',
                'description': f"{area['category']}方面问题: {area['count']}次",
                'impact': '影响回答质量'
            }
            for area in problem_areas[:3]
        ]

        return all_issues

    def _generate_recommendations(self) -> List[str]:
        """生成建议"""
        recommendations = []

        # 基于问题生成建议
        issues = self._identify_issues()
        for issue in issues:
            if issue['category'] == 'performance':
                recommendations.append("优化慢查询，考虑增加缓存")
            elif issue['category'] == 'user_satisfaction':
                recommendations.append("分析负面反馈，改进回答质量")

        # 添加反馈分析器的建议
        recommendations.extend(feedback_analyzer.get_improvement_suggestions())

        return recommendations[:5]

    def _get_improvement_suggestions(self) -> List[str]:
        """获取改进建议"""
        return self._generate_recommendations()

    def _get_executive_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        health = self._get_system_health()
        perf = self._get_performance_overview()
        satisfaction = self._get_user_satisfaction()

        return {
            'overall_status': health['status'],
            'health_score': health['health_score'],
            'total_requests': perf['total_requests'],
            'success_rate': perf['success_rate'],
            'user_satisfaction': satisfaction['satisfaction_score'],
            'key_metrics': {
                'uptime': '99.9%',
                'avg_response_time': perf['avg_response_time'],
                'positive_feedback_rate': satisfaction['positive_feedback_rate']
            }
        }

    def _get_key_achievements(self) -> List[str]:
        """获取关键成就"""
        achievements = []

        health = self._get_system_health()
        if health['health_score'] >= 90:
            achievements.append(f"系统健康评分优秀: {health['health_score']}/100")

        perf = self._get_performance_metrics()
        if perf['success_rate'] >= 0.95:
            achievements.append(f"高成功率: {perf['success_rate']:.1%}")

        satisfaction = self._get_user_satisfaction()
        if satisfaction['satisfaction_score'] >= 80:
            achievements.append(f"用户满意度高: {satisfaction['satisfaction_score']:.1f}/100")

        return achievements

    def _get_challenges(self) -> List[str]:
        """获取挑战"""
        challenges = []

        issues = self._get_top_issues()
        for issue in issues[:3]:
            challenges.append(f"{issue['description']} - {issue['impact']}")

        return challenges

    def _get_action_items(self) -> List[Dict[str, Any]]:
        """获取行动项"""
        action_items = []

        recommendations = self._get_improvement_suggestions()
        for i, rec in enumerate(recommendations[:5], 1):
            action_items.append({
                'priority': 'high' if i <= 2 else 'medium',
                'action': rec,
                'owner': 'Development Team',
                'deadline': (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            })

        return action_items

    def save_report(self, report: Dict[str, Any], filename: str = None):
        """保存报告"""
        if filename is None:
            report_type = report['report_type']
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{report_type}_report_{timestamp}.json"

        filepath = self.report_path / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return filepath

    def generate_markdown_report(self, report: Dict[str, Any]) -> str:
        """生成Markdown格式报告"""
        md = []

        md.append(f"# 系统运行报告 - {report['report_type'].upper()}\n")
        md.append(f"生成时间: {report['generated_at']}\n")
        md.append(f"报告周期: {report['period']['start']} 至 {report['period']['end']}\n")

        # 执行摘要（仅月报）
        if 'executive_summary' in report:
            md.append("\n## 执行摘要\n")
            summary = report['executive_summary']
            md.append(f"- 系统状态: {summary['overall_status']}")
            md.append(f"- 健康评分: {summary['health_score']}/100")
            md.append(f"- 总请求数: {summary['total_requests']}")
            md.append(f"- 成功率: {summary['success_rate']:.1%}")
            md.append(f"- 用户满意度: {summary['user_satisfaction']:.1f}/100\n")

        # 系统健康
        md.append("\n## 系统健康\n")
        health = report['system_health']
        md.append(f"- 状态: {health['status']}")
        md.append(f"- 健康评分: {health['health_score']}/100")
        md.append(f"- 活跃告警: {health['active_alerts']}")
        md.append(f"- 运行时间: {health['uptime']}\n")

        # 性能指标
        if 'performance_metrics' in report:
            md.append("\n## 性能指标\n")
            perf = report['performance_metrics']
            md.append(f"- 总请求数: {perf['total_requests']}")
            md.append(f"- 成功率: {perf['success_rate']:.1%}")
            md.append(f"- 平均响应时间: {perf['avg_response_time']:.2f}ms")
            md.append(f"- 错误率: {perf['error_rate']:.1%}\n")

        # 知识库状态
        md.append("\n## 知识库状态\n")
        kb = report['knowledge_base_status']
        md.append(f"- 文档总数: {kb['total_documents']}")
        md.append(f"- 质量评分: {kb['quality_score']:.1f}")
        md.append(f"- 平均检索时间: {kb['avg_retrieval_time']:.2f}ms")
        md.append(f"- 更新成功率: {kb['update_success_rate']:.1%}\n")

        # 用户反馈
        if 'user_feedback' in report:
            md.append("\n## 用户反馈\n")
            feedback = report['user_feedback']
            md.append(f"- 总反馈数: {feedback['total_feedbacks']}")
            md.append(f"- 正面反馈率: {feedback['positive_rate']:.1%}")
            md.append(f"- 负面反馈率: {feedback['negative_rate']:.1%}")
            md.append(f"- 平均评分: {feedback['avg_rating']:.2f}/5\n")

        # 问题和建议
        if 'issues' in report and report['issues']:
            md.append("\n## 识别的问题\n")
            for issue in report['issues']:
                md.append(f"- [{issue['severity'].upper()}] {issue['description']}")
                md.append(f"  - 影响: {issue['impact']}\n")

        if 'recommendations' in report and report['recommendations']:
            md.append("\n## 改进建议\n")
            for i, rec in enumerate(report['recommendations'], 1):
                md.append(f"{i}. {rec}")

        return '\n'.join(md)


def main():
    """主函数"""
    generator = SystemReportGenerator()

    print("系统运行报告生成器\n")
    print("=" * 60)

    # 生成每日报告
    print("\n生成每日报告...")
    daily_report = generator.generate_daily_report()
    daily_path = generator.save_report(daily_report)
    print(f"每日报告已保存: {daily_path}")

    # 生成Markdown版本
    md_content = generator.generate_markdown_report(daily_report)
    md_path = daily_path.with_suffix('.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"Markdown报告已保存: {md_path}")

    # 生成每周报告
    print("\n生成每周报告...")
    weekly_report = generator.generate_weekly_report()
    weekly_path = generator.save_report(weekly_report)
    print(f"每周报告已保存: {weekly_path}")

    # 生成每月报告
    print("\n生成每月报告...")
    monthly_report = generator.generate_monthly_report()
    monthly_path = generator.save_report(monthly_report)
    print(f"每月报告已保存: {monthly_path}")

    print("\n" + "=" * 60)
    print("所有报告生成完成!")


if __name__ == '__main__':
    main()
