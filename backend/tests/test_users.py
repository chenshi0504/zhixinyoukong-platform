"""
User management module tests.
"""
import pytest
from io import BytesIO
from fastapi import status


class TestUserCreation:
    """Tests for user creation."""

    def test_create_student(self, client, teacher_token):
        """Test creating a student user."""
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "username": "newstudent",
                "password": "pass123456",
                "role": "student",
                "real_name": "新学生",
                "student_id": "2024099",
                "class_name": "测试班级"
            }
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["username"] == "newstudent"
        assert data["role"] == "student"

    def test_create_duplicate_username(self, client, teacher_token, test_student):
        """Test creating user with existing username fails."""
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={
                "username": "student1",
                "password": "pass123456",
                "role": "student",
                "real_name": "重复用户"
            }
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_student_cannot_create_user(self, client, student_token):
        """Test that students cannot create users."""
        response = client.post(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {student_token}"},
            json={
                "username": "hacker",
                "password": "pass123456",
                "role": "student",
                "real_name": "黑客"
            }
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestUserList:
    """Tests for user listing."""

    def test_teacher_can_list_users(self, client, teacher_token, test_student):
        """Test that teachers can list users."""
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_filter_by_role(self, client, teacher_token, test_student):
        """Test filtering users by role."""
        response = client.get(
            "/api/v1/users?role=student",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        for user in data:
            assert user["role"] == "student"


class TestPasswordReset:
    """Tests for password reset."""

    def test_reset_password(self, client, teacher_token, test_student):
        """Test resetting a student's password."""
        response = client.put(
            f"/api/v1/users/{test_student.id}/reset-password",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={"new_password": "newpass123"}
        )
        assert response.status_code == status.HTTP_200_OK

        # Verify new password works
        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": "student1", "password": "newpass123"}
        )
        assert login_response.status_code == status.HTTP_200_OK

    def test_reset_password_nonexistent_user(self, client, teacher_token):
        """Test resetting password for non-existent user."""
        response = client.put(
            "/api/v1/users/9999/reset-password",
            headers={"Authorization": f"Bearer {teacher_token}"},
            json={"new_password": "newpass123"}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestBatchImport:
    """Tests for batch student import."""

    def test_import_students_from_excel(self, client, teacher_token):
        """Test importing students from an Excel file."""
        import openpyxl
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["username", "real_name", "student_id", "class_name"])
        ws.append(["import_s1", "导入学生1", "2024101", "导入班级"])
        ws.append(["import_s2", "导入学生2", "2024102", "导入班级"])
        
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        
        response = client.post(
            "/api/v1/users/import",
            headers={"Authorization": f"Bearer {teacher_token}"},
            files={"file": ("students.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["created"] == 2
        assert data["skipped"] == 0

    def test_import_invalid_file_type(self, client, teacher_token):
        """Test importing with invalid file type."""
        buffer = BytesIO(b"not an excel file")
        response = client.post(
            "/api/v1/users/import",
            headers={"Authorization": f"Bearer {teacher_token}"},
            files={"file": ("students.csv", buffer, "text/csv")}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
