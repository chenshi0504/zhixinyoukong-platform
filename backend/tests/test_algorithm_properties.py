"""
Property-based tests for student algorithm design feature.
Uses hypothesis for property-based testing.
"""
import time
import pytest
from hypothesis import given, settings as h_settings, assume
from hypothesis import strategies as st
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import User, UserRole, Task
from app.models.algorithm import AlgorithmTemplate, AlgorithmScript, ExecutionStatus
from app.services.algorithm_script import submit_script, get_script_by_id, get_scripts_by_student
from app.services.algorithm_template import (
    create_template, get_template_by_id, get_templates_by_module,
)
from app.services.code_formatter import format_code, parse_code


# ---- Isolated in-memory DB helpers ----

def _make_db():
    """Create a fresh in-memory SQLite DB with all tables. Returns a session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session()


def _seed(db):
    """Insert a student, teacher, and task. Return (student, task)."""
    teacher = User(
        username="t", password_hash="x",
        role=UserRole.TEACHER.value, real_name="T", is_active=True,
    )
    db.add(teacher)
    db.flush()

    student = User(
        username="s", password_hash="x",
        role=UserRole.STUDENT.value, real_name="S", is_active=True,
    )
    db.add(student)
    db.flush()

    task = Task(
        title="PBT Task", description="d",
        teacher_id=teacher.id, status="published",
    )
    db.add(task)
    db.commit()
    return student, task


# ---- Strategies ----

module_id_st = st.from_regex(r"[a-z][a-z0-9_]{0,29}", fullmatch=True)

valid_code_st = st.from_regex(
    r"print\('[a-zA-Z0-9 ]{1,80}'\)\n?", fullmatch=True
)


# **Feature: student-algorithm-design, Property 3: Script Submission Round-Trip**
# **Validates: Requirements 2.1**
@given(module_id=module_id_st, code=valid_code_st)
@h_settings(max_examples=100)
def test_script_submission_round_trip(module_id, code):
    """
    Property 3: Script Submission Round-Trip

    For any valid algorithm script submission (student_id, task_id,
    module_id, code), creating a submission and reading it back should
    return equivalent data for all fields.
    """
    db = _make_db()
    try:
        student, task = _seed(db)

        script = submit_script(
            db=db,
            student_id=student.id,
            task_id=task.id,
            module_id=module_id,
            code=code,
        )
        script_id = script.id

        loaded = get_script_by_id(db, script_id)

        assert loaded is not None
        assert loaded.student_id == student.id
        assert loaded.task_id == task.id
        assert loaded.module_id == module_id
        assert loaded.code == format_code(code)
        assert loaded.execution_status == ExecutionStatus.PENDING
        assert loaded.submitted_at is not None
    finally:
        db.close()


# ---- Strategies for invalid code ----

# Empty string
_empty_st = st.just("")

# Whitespace-only strings (spaces, tabs, newlines)
_whitespace_st = st.text(
    alphabet=st.sampled_from([" ", "\t", "\n", "\r"]),
    min_size=1,
    max_size=50,
)

# Strings exceeding 50KB (50 * 1024 = 51200 bytes)
# Use st.binary to generate large payloads, then decode to string
_oversized_st = st.integers(min_value=51201, max_value=51300).map(
    lambda n: "a" * n
)

invalid_code_st = st.one_of(_empty_st, _whitespace_st, _oversized_st)


# **Feature: student-algorithm-design, Property 4: Invalid Code Rejection**
# **Validates: Requirements 2.2**
@given(code=invalid_code_st)
@h_settings(max_examples=100)
def test_invalid_code_rejection(code):
    """
    Property 4: Invalid Code Rejection

    For any code string that is empty, whitespace-only, or exceeds 50KB
    in size, the submission should be rejected and no record should be
    created.
    """
    db = _make_db()
    try:
        student, task = _seed(db)

        with pytest.raises(HTTPException) as exc_info:
            submit_script(
                db=db,
                student_id=student.id,
                task_id=task.id,
                module_id="test_module",
                code=code,
            )

        assert exc_info.value.status_code == 422

        # Verify no record was persisted
        count = db.query(AlgorithmScript).count()
        assert count == 0
    finally:
        db.close()


# ---- Strategies for template tests ----

template_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1, max_size=50,
).filter(lambda s: s.strip())

template_desc_st = st.one_of(
    st.none(),
    st.text(min_size=0, max_size=200),
)

template_code_st = st.from_regex(
    r"def run\(\):\n    return [0-9]+\n", fullmatch=True
)


# **Feature: student-algorithm-design, Property 1: Template CRUD Round-Trip**
# **Validates: Requirements 1.1**
@given(
    module_id=module_id_st,
    name=template_name_st,
    description=template_desc_st,
    code=template_code_st,
)
@h_settings(max_examples=100)
def test_template_crud_round_trip(module_id, name, description, code):
    """
    Property 1: Template CRUD Round-Trip

    For any valid algorithm template data (module_id, name, description, code),
    creating a template and then reading it back by ID should return equivalent
    data for all fields.
    """
    db = _make_db()
    try:
        teacher = User(
            username="t", password_hash="x",
            role=UserRole.TEACHER.value, real_name="T", is_active=True,
        )
        db.add(teacher)
        db.commit()

        tpl = create_template(
            db,
            module_id=module_id,
            name=name,
            code=code,
            teacher_id=teacher.id,
            description=description,
        )
        tpl_id = tpl.id

        loaded = get_template_by_id(db, tpl_id)

        assert loaded is not None
        assert loaded.module_id == module_id
        assert loaded.name == name
        assert loaded.description == description
        assert loaded.code == code
        assert loaded.teacher_id == teacher.id
        assert loaded.created_at is not None
    finally:
        db.close()


# **Feature: student-algorithm-design, Property 2: Template Module Filtering**
# **Validates: Requirements 1.2**
@given(
    data=st.data(),
    modules=st.lists(
        st.from_regex(r"[a-z]{3,10}", fullmatch=True),
        min_size=2, max_size=5, unique=True,
    ),
)
@h_settings(max_examples=100)
def test_template_module_filtering(data, modules):
    """
    Property 2: Template Module Filtering

    For any set of templates across multiple modules, querying templates by a
    specific module_id should return only templates belonging to that module,
    and should return all of them.
    """
    db = _make_db()
    try:
        teacher = User(
            username="t", password_hash="x",
            role=UserRole.TEACHER.value, real_name="T", is_active=True,
        )
        db.add(teacher)
        db.commit()

        # Create 1-3 templates per module
        counts = {}
        for mod in modules:
            n = data.draw(st.integers(min_value=1, max_value=3))
            counts[mod] = n
            for i in range(n):
                create_template(
                    db,
                    module_id=mod,
                    name=f"tpl_{mod}_{i}",
                    code=f"# {mod} {i}\n",
                    teacher_id=teacher.id,
                )

        # Query each module and verify
        for mod in modules:
            results = get_templates_by_module(db, mod)
            assert len(results) == counts[mod]
            for tpl in results:
                assert tpl.module_id == mod
    finally:
        db.close()


# **Feature: student-algorithm-design, Property 5: Submission Ordering**
# **Validates: Requirements 2.3**
@given(n=st.integers(min_value=2, max_value=10))
@h_settings(max_examples=50)
def test_submission_ordering(n):
    """
    Property 5: Submission Ordering

    For any student with multiple algorithm submissions for the same task,
    querying their submissions should return them ordered by submission time
    (most recent first).
    """
    db = _make_db()
    try:
        student, task = _seed(db)

        # Submit n scripts
        ids = []
        for i in range(n):
            script = submit_script(
                db,
                student_id=student.id,
                task_id=task.id,
                module_id="test_mod",
                code=f"print({i})\n",
            )
            ids.append(script.id)

        results = get_scripts_by_student(db, student.id, task_id=task.id)

        assert len(results) == n
        # Most recent first → IDs should be in descending order
        result_ids = [r.id for r in results]
        assert result_ids == sorted(result_ids, reverse=True)
        # Timestamps should be non-increasing
        for i in range(len(results) - 1):
            assert results[i].submitted_at >= results[i + 1].submitted_at
    finally:
        db.close()


# **Feature: student-algorithm-design, Property 6: Code Pretty-Print Round-Trip**
# **Validates: Requirements 2.4**
@given(
    code=st.from_regex(
        r"([ ]{0,4}[a-z_][a-z0-9_ ]{0,40}\n){1,10}",
        fullmatch=True,
    )
)
@h_settings(max_examples=100)
def test_code_format_round_trip(code):
    """
    Property 6: Code Pretty-Print Round-Trip

    For any valid Python code string, pretty-printing and then parsing back
    should produce a string equivalent to the original code content.
    """
    formatted = format_code(code)
    parsed = parse_code(formatted)

    # parse(format(code)) should equal format(code)
    assert parsed == formatted

    # format is idempotent: format(format(code)) == format(code)
    assert format_code(formatted) == formatted
