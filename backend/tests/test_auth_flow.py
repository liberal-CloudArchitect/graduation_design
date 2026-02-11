import pytest
import httpx
from fastapi import FastAPI
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.api.v1.auth import router as auth_router
from app.core.deps import get_db
from app.core.security import get_password_hash


@pytest.mark.asyncio
async def test_login_me_refresh_me():
    user = SimpleNamespace(
        id=1,
        email="test@example.com",
        username="testuser",
        password_hash=get_password_hash("password123"),
        is_active=True,
    )

    result = MagicMock()
    result.scalar_one_or_none.return_value = user

    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    async def override_get_db():
        yield session

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "password123"},
        )
        assert login_res.status_code == 200
        login_data = login_res.json()
        access = login_data["access_token"]
        refresh = login_data["refresh_token"]
        assert isinstance(access, str) and access.count(".") == 2
        assert isinstance(refresh, str) and refresh.count(".") == 2

        me_res = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
        assert me_res.status_code == 200
        assert me_res.json()["email"] == user.email

        refresh_res = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert refresh_res.status_code == 200
        new_access = refresh_res.json()["access_token"]
        assert isinstance(new_access, str) and new_access.count(".") == 2

        me_res_2 = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"}
        )
        assert me_res_2.status_code == 200
        assert me_res_2.json()["email"] == user.email
