"""
Authentication module tests.
"""
import pytest
from fastapi import status


class TestLogin:
    """Tests for login functionality."""
    
    def test_login_success(self, client, test_teacher):
        """Test successful login with valid credentials."""
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "teacher1", "password": "teacher123"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_invalid_password(self, client, test_teacher):
        """Test login with wrong password."""
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "teacher1", "password": "wrongpassword"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert data["detail"]["code"] == "AUTH_001"
    
    def test_login_invalid_username(self, client):
        """Test login with non-existent username."""
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "nonexistent", "password": "password123"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_json_success(self, client, test_student):
        """Test successful login with JSON format."""
        response = client.post(
            "/api/v1/auth/login/json",
            json={"username": "student1", "password": "student123"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data


class TestTokenValidation:
    """Tests for token validation."""
    
    def test_get_current_user_valid_token(self, client, teacher_token):
        """Test getting current user with valid token."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["username"] == "teacher1"
        assert data["role"] == "teacher"
    
    def test_get_current_user_invalid_token(self, client):
        """Test getting current user with invalid token."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_get_current_user_no_token(self, client):
        """Test getting current user without token."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRoleBasedAccess:
    """Tests for role-based access control."""
    
    def test_admin_token_contains_role(self, client, admin_token):
        """Test that admin token contains correct role."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["role"] == "admin"
    
    def test_teacher_token_contains_role(self, client, teacher_token):
        """Test that teacher token contains correct role."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["role"] == "teacher"
    
    def test_student_token_contains_role(self, client, student_token):
        """Test that student token contains correct role."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["role"] == "student"


class TestLogout:
    """Tests for logout functionality."""
    
    def test_logout_success(self, client, teacher_token):
        """Test successful logout."""
        response = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {teacher_token}"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
