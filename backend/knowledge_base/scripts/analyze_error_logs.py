"""
错误日志分析工具
分析系统错误日志，识别问题模式和趋势
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from collections import Counter, defaultdict
import re
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class ErrorLogAnalyzer:
    """错误日志分析器"""

    def __init__(self, log_dir: Optional[Path] = None):
        """
        初始化分析器

        Args:
            log_dir: 日志目录路径
        """
        self.log_dir = log_dir or Path('logs')
        self.error_patterns = self._load_error_patterns()

    def _load_error_patterns(self) -> Dict[str, str]:
        """加载错误模式"""
        return {
            'connection_error': r'(ConnectionError|Connection refused|Connection timeout)',
            'timeout_error': r'(TimeoutError|Request timeout|Read timeout)',
            'api_error': r'(API.*error|API.*failed|API.*exception)',
            'database_error': r'(DatabaseError|SQL.*error|Query.*failed)',
            'file_error': r'(FileNotFoundError|PermissionError|IOError)',
            'memory_error': r'(MemoryError|Out of memory|OOM)',
            'import_error': r'(ImportError|ModuleNotFoundError)',
            'value_error': r'(ValueError|Invalid value)',
            'key_error': r'(KeyError|Missing key)',
            'type_error': r'(TypeError|Type mismatch)',
            'index_error': r'(IndexError|List index out of range)',
            'attribute_error': r'(AttributeError|has no attribute)',
            'assertion_error': r'(AssertionError|Assertion failed)',
            'runtime_error': r'(RuntimeError|Runtime exception)',
        }

    def analyze_log_file(self, log_file: Path) -> Dict[str, Any]:
        """
        分析单个日志文件

        Args:
            log_file: 日志文件路径

        Returns:
            分析结果
        """
        errors = []
        warnings = []

        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    # 检测错误
                    if 'ERROR' in line or 'Exception' in line or 'Traceback' in line:
                        errors.append({
                            'line_num': line_num,
                            'content': line.strip(),
                            'timestamp': self._extract_timestamp(line),
                            'error_type': self._classify_error(line)
                        })

                    # 检测警告
                    elif 'WARNING' in line or 'WARN' in line:
                        warnings.append({
                            'line_num': line_num,
                            'content': line.strip(),
                            'timestamp': self._extract_timestamp(line)
                        })
        except Exception as e:
            print(f"读取日志文件失败 {log_file}: {e}")
            return {}

        return {
            'file': str(log_file),
            'total_errors': len(errors),
            'total_warnings': len(warnings),
            'errors': errors,
            'warnings': warnings,
            'error_types': self._count_error_types(errors)
        }

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """提取时间戳"""
        # 尝试匹配常见的时间戳格式
        patterns = [
            r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',  # 2026-04-22 19:42:57
            r'\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}',  # 2026/04/22 19:42:57
            r'\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # [2026-04-22T19:42:57
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0).strip('[]')

        return None

    def _classify_error(self, line: str) -> str:
        """分类错误类型"""
        for error_type, pattern in self.error_patterns.items():
            if re.search(pattern, line, re.IGNORECASE):
                return error_type

        return 'unknown'

    def _count_error_types(self, errors: List[Dict[str, Any]]) -> Dict[str, int]:
        """统计错误类型"""
        return dict(Counter(error['error_type'] for error in errors))

    def analyze_directory(self, days: int = 7) -> Dict[str, Any]:
        """
        分析目录中的所有日志文件

        Args:
            days: 分析最近N天的日志

        Returns:
            综合分析结果
        """
        if not self.log_dir.exists():
            return {
                'total_files': 0,
                'total_errors': 0,
                'total_warnings': 0,
                'error_types': {},
                'files': []
            }

        cutoff_time = datetime.now() - timedelta(days=days)

        all_errors = []
        all_warnings = []
        all_error_types = Counter()
        analyzed_files = []

        # 分析所有日志文件
        for log_file in self.log_dir.glob('*.log'):
            # 检查文件修改时间
            if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_time:
                continue

            result = self.analyze_log_file(log_file)
            if result:
                analyzed_files.append(result)
                all_errors.extend(result['errors'])
                all_warnings.extend(result['warnings'])
                all_error_types.update(result['error_types'])

        return {
            'analysis_period': f'最近{days}天',
            'total_files': len(analyzed_files),
            'total_errors': len(all_errors),
            'total_warnings': len(all_warnings),
            'error_types': dict(all_error_types),
            'files': analyzed_files,
            'top_errors': self._get_top_errors(all_errors),
            'error_timeline': self._build_error_timeline(all_errors),
            'recommendations': self._generate_recommendations(all_errors, all_error_types)
        }

    def _get_top_errors(self, errors: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        """获取最常见的错误"""
        # 提取错误消息（去除时间戳和行号）
        error_messages = []
        for error in errors:
            content = error['content']
            # 简化错误消息
            simplified = re.sub(r'\d{4}-\d{2}-\d{2}.*?ERROR', 'ERROR', content)
            simplified = re.sub(r'line \d+', 'line X', simplified)
            simplified = re.sub(r'File ".*?"', 'File "..."', simplified)
            error_messages.append(simplified)

        # 统计频率
        counter = Counter(error_messages)

        return [
            {
                'message': msg,
                'count': count,
                'percentage': count / len(errors) * 100 if errors else 0
            }
            for msg, count in counter.most_common(limit)
        ]

    def _build_error_timeline(self, errors: List[Dict[str, Any]]) -> Dict[str, int]:
        """构建错误时间线"""
        timeline = defaultdict(int)

        for error in errors:
            timestamp = error.get('timestamp')
            if timestamp:
                try:
                    # 提取日期部分
                    date = timestamp.split()[0]
                    timeline[date] += 1
                except:
                    pass

        return dict(sorted(timeline.items()))

    def _generate_recommendations(
        self,
        errors: List[Dict[str, Any]],
        error_types: Counter
    ) -> List[str]:
        """生成改进建议"""
        recommendations = []

        if not errors:
            return ["系统运行正常，未发现错误"]

        # 基于错误类型生成建议
        if error_types.get('connection_error', 0) > 5:
            recommendations.append("连接错误频繁，建议检查网络配置和服务可用性")

        if error_types.get('timeout_error', 0) > 5:
            recommendations.append("超时错误较多，建议优化请求性能或增加超时时间")

        if error_types.get('api_error', 0) > 5:
            recommendations.append("API错误频繁，建议检查API密钥和配额")

        if error_types.get('database_error', 0) > 3:
            recommendations.append("数据库错误，建议检查数据库连接和查询语句")

        if error_types.get('memory_error', 0) > 0:
            recommendations.append("内存错误，建议优化内存使用或增加系统资源")

        if error_types.get('file_error', 0) > 3:
            recommendations.append("文件错误，建议检查文件路径和权限")

        # 基于错误频率生成建议
        error_rate = len(errors) / max(1, len(error_types))
        if error_rate > 10:
            recommendations.append("错误率较高，建议进行全面的代码审查")

        if not recommendations:
            recommendations.append("发现少量错误，建议定期监控")

        return recommendations

    def generate_report(self, analysis: Dict[str, Any], output_path: Optional[Path] = None) -> str:
        """
        生成分析报告

        Args:
            analysis: 分析结果
            output_path: 输出路径

        Returns:
            报告内容
        """
        report = []

        report.append("# 错误日志分析报告\n")
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report.append(f"分析周期: {analysis.get('analysis_period', 'N/A')}\n")

        report.append("\n## 概览\n")
        report.append(f"- 分析文件数: {analysis.get('total_files', 0)}")
        report.append(f"- 错误总数: {analysis.get('total_errors', 0)}")
        report.append(f"- 警告总数: {analysis.get('total_warnings', 0)}")

        report.append("\n## 错误类型分布\n")
        if analysis.get('error_types'):
            for error_type, count in sorted(
                analysis['error_types'].items(),
                key=lambda x: x[1],
                reverse=True
            ):
                percentage = count / analysis.get('total_errors', 1) * 100 if analysis.get('total_errors') else 0
                report.append(f"- {error_type}: {count} ({percentage:.1f}%)")
        else:
            report.append("- 无错误")

        report.append("\n## 最常见错误\n")
        if analysis.get('top_errors'):
            for i, error in enumerate(analysis['top_errors'][:5], 1):
                report.append(f"\n### {i}. 出现{error['count']}次 ({error['percentage']:.1f}%)")
                report.append(f"```\n{error['message']}\n```")
        else:
            report.append("- 无错误")

        report.append("\n## 错误时间线\n")
        if analysis.get('error_timeline'):
            for date, count in analysis['error_timeline'].items():
                report.append(f"- {date}: {count}个错误")
        else:
            report.append("- 无数据")

        report.append("\n## 改进建议\n")
        for i, rec in enumerate(analysis.get('recommendations', []), 1):
            report.append(f"{i}. {rec}")

        report_content = '\n'.join(report)

        # 保存报告
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_content)

        return report_content


def main():
    """主函数"""
    print("错误日志分析工具\n")
    print("=" * 60)

    # 创建分析器
    analyzer = ErrorLogAnalyzer()

    # 分析最近7天的日志
    print("\n分析最近7天的日志...")
    analysis = analyzer.analyze_directory(days=7)

    print(f"分析文件数: {analysis['total_files']}")
    print(f"错误总数: {analysis['total_errors']}")
    print(f"警告总数: {analysis['total_warnings']}")

    # 生成报告
    print("\n生成分析报告...")
    report_path = Path('.RAG/error_log_analysis_report.md')
    report = analyzer.generate_report(analysis, report_path)

    print(f"报告已保存: {report_path}")

    # 保存JSON格式
    json_path = report_path.with_suffix('.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"JSON数据已保存: {json_path}")

    print("\n" + "=" * 60)
    print("分析完成!")


if __name__ == '__main__':
    main()
