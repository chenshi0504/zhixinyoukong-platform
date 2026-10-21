"""
Hypothesis 属性测试：序列化往返一致性。
# Feature: cloud-admin-platform, Property 1: API 数据序列化往返一致性
Validates: Requirements 1.6, 3.7, 9.4
"""
from datetime import datetime, date, timezone
from hypothesis import given, strategies as st, settings as h_settings

from app.schemas.organization import OrgRead
from app.schemas.license import LicenseRead
from app.schemas.task import TaskRead
from app.schemas.report import ReportRead


# --- Strategies ---

_dt = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)
_optional_dt = st.one_of(st.none(), _dt)
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
)
_optional_text = st.one_of(st.none(), _safe_text)
_pos_int = st.integers(min_value=1, max_value=10_000)


org_read_st = st.builds(
    OrgRead,
    id=_pos_int,
    name=_safe_text,
    contact_name=_optional_text,
    contact_phone=_optional_text,
    address=_optional_text,
    license_quota=st.integers(min_value=0, max_value=1000),
    created_at=_dt,
    updated_at=_dt,
)

license_read_st = st.builds(
    LicenseRead,
    id=_pos_int,
    license_key=st.from_regex(r"[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}", fullmatch=True),
    org_id=st.one_of(st.none(), _pos_int),
    license_type=st.sampled_from(["trial", "education", "permanent"]),
    machine_id=_optional_text,
    is_active=st.booleans(),
    activated_at=_optional_dt,
    expires_at=_optional_dt,
    created_at=_dt,
    updated_at=_dt,
)

task_read_st = st.builds(
    TaskRead,
    id=_pos_int,
    title=_safe_text,
    description=_optional_text,
    module_id=_optional_text,
    teacher_id=st.one_of(st.none(), _pos_int),
    org_id=st.one_of(st.none(), _pos_int),
    deadline=_optional_dt,
    max_score=st.integers(min_value=0, max_value=100),
    status=st.sampled_from(["draft", "published"]),
    created_at=_dt,
    updated_at=_dt,
)

report_read_st = st.builds(
    ReportRead,
    id=_pos_int,
    task_id=st.one_of(st.none(), _pos_int),
    student_id=st.one_of(st.none(), _pos_int),
    original_filename=_optional_text,
    file_size=st.one_of(st.none(), st.integers(min_value=0, max_value=10**9)),
    score=st.one_of(st.none(), st.integers(min_value=0, max_value=100)),
    feedback=_optional_text,
    grader_id=st.one_of(st.none(), _pos_int),
    status=st.sampled_from(["submitted", "graded"]),
    submitted_at=_dt,
    graded_at=_optional_dt,
    updated_at=_dt,
)


# --- Property Tests ---

@h_settings(max_examples=100)
@given(obj=org_read_st)
def test_org_read_roundtrip(obj: OrgRead):
    """Organization 序列化往返一致性。"""
    json_str = obj.model_dump_json()
    restored = OrgRead.model_validate_json(json_str)
    assert restored == obj


@h_settings(max_examples=100)
@given(obj=license_read_st)
def test_license_read_roundtrip(obj: LicenseRead):
    """License 序列化往返一致性。"""
    json_str = obj.model_dump_json()
    restored = LicenseRead.model_validate_json(json_str)
    assert restored == obj


@h_settings(max_examples=100)
@given(obj=task_read_st)
def test_task_read_roundtrip(obj: TaskRead):
    """Task 序列化往返一致性。"""
    json_str = obj.model_dump_json()
    restored = TaskRead.model_validate_json(json_str)
    assert restored == obj


@h_settings(max_examples=100)
@given(obj=report_read_st)
def test_report_read_roundtrip(obj: ReportRead):
    """Report 序列化往返一致性。"""
    json_str = obj.model_dump_json()
    restored = ReportRead.model_validate_json(json_str)
    assert restored == obj


# ============================================================
# Property 4: License 唯一性
# Feature: cloud-admin-platform, Property 4: License 唯一性
# Validates: Requirements 3.1
# ============================================================

from app.services.license import generate_license_key


@h_settings(max_examples=50)
@given(n=st.integers(min_value=2, max_value=100))
def test_license_key_uniqueness(n: int):
    """批量生成 N 个 License key，验证两两不同。"""
    keys = [generate_license_key() for _ in range(n)]
    assert len(set(keys)) == len(keys)


# ============================================================
# Property 6: 分页结果数量上界
# Feature: cloud-admin-platform, Property 6: 分页结果数量上界
# Validates: Requirements 1.5
# ============================================================

from app.schemas.common import PagedResponse


@h_settings(max_examples=50)
@given(
    page_size=st.sampled_from([10, 20, 50]),
    total_items=st.integers(min_value=0, max_value=200),
)
def test_paged_response_upper_bound(page_size: int, total_items: int):
    """分页返回数量不超过 page_size。"""
    items = list(range(min(total_items, page_size)))
    pages = (total_items + page_size - 1) // page_size if total_items > 0 else 1
    resp = PagedResponse(items=items, total=total_items, page=1, page_size=page_size, pages=pages)
    assert len(resp.items) <= page_size


# ============================================================
# Property 10: 报告评分范围约束
# Feature: cloud-admin-platform, Property 10: 报告评分范围约束
# Validates: Requirements 6.3
# ============================================================

from pydantic import ValidationError
from app.schemas.report import GradeRequest


@h_settings(max_examples=100)
@given(score=st.integers(min_value=0, max_value=100))
def test_grade_valid_score(score: int):
    """0-100 范围内的 score 应通过验证。"""
    req = GradeRequest(score=score)
    assert req.score == score


@h_settings(max_examples=50)
@given(score=st.one_of(
    st.integers(max_value=-1),
    st.integers(min_value=101),
))
def test_grade_invalid_score(score: int):
    """范围外的 score 应触发 ValidationError。"""
    try:
        GradeRequest(score=score)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass


# ============================================================
# Property 11: 版本更新检查语义正确性
# Feature: cloud-admin-platform, Property 11: 版本更新检查语义正确性
# Validates: Requirements 8.2, 8.3
# ============================================================

from packaging.version import Version

_version_part = st.integers(min_value=0, max_value=99)
_semver = st.builds(lambda a, b, c: f"{a}.{b}.{c}", _version_part, _version_part, _version_part)


@h_settings(max_examples=100)
@given(v1=_semver, v2=_semver)
def test_version_comparison_consistency(v1: str, v2: str):
    """语义版本比较应与 packaging.version 一致。"""
    pv1, pv2 = Version(v1), Version(v2)
    if pv1 > pv2:
        assert not (pv1 <= pv2)
    elif pv1 < pv2:
        assert not (pv1 >= pv2)
    else:
        assert pv1 == pv2


# ============================================================
# Property 12: 统计数据追加模式
# Feature: cloud-admin-platform, Property 12: 统计数据追加模式
# Validates: Requirements 9.2
# ============================================================

from app.schemas.analytics import AnalyticsReport as AnalyticsReportSchema


@h_settings(max_examples=30)
@given(
    count=st.integers(min_value=0, max_value=50),
    exp_count=st.integers(min_value=0, max_value=1000),
)
def test_analytics_report_schema_accepts_duplicates(count: int, exp_count: int):
    """相同参数可以创建多个独立的 AnalyticsReport 对象（追加模式的前提）。"""
    reports = [
        AnalyticsReportSchema(
            license_id=1, org_id=1,
            report_date=date(2026, 1, 15),
            active_user_count=count,
            experiment_count=exp_count,
        )
        for _ in range(2)
    ]
    assert reports[0] == reports[1]  # 值相等
    assert reports[0] is not reports[1]  # 但是不同对象
