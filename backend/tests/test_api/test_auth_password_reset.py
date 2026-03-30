import uuid
from types import SimpleNamespace

import pytest
from passlib.hash import argon2

from app.api.v1 import auth as auth_api


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _AuthDb:
    def __init__(self, values):
        self.values = list(values)
        self.committed = 0

    async def execute(self, *_args, **_kwargs):
        value = self.values.pop(0) if self.values else None
        return _ScalarResult(value)

    async def commit(self):
        self.committed += 1


@pytest.mark.asyncio
async def test_forgot_password_returns_generic_message_for_missing_user():
    db = _AuthDb([None])
    response = await auth_api.forgot_password(
        auth_api.ForgotPasswordRequest(email="missing@example.com"),
        db,
    )

    assert response.delivery == "email"
    assert "If an account exists" in response.message
    assert response.preview_url is None


@pytest.mark.asyncio
async def test_forgot_password_returns_preview_for_existing_user(monkeypatch):
    user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", display_name="User")
    token_row = SimpleNamespace(delivery="email", destination=None)
    db = _AuthDb([user])

    async def _fake_issue_password_reset_token(_db, _user):
        return "raw-token", token_row

    def _fake_build_password_reset_url(raw_token: str):
        return f"https://hisabclub-dev-web.ankit-tech.store/reset-password?token={raw_token}"

    async def _fake_send_password_reset_instructions(_user, reset_url: str):
        assert reset_url.endswith("raw-token")
        return SimpleNamespace(
            delivery="preview",
            preview_url=reset_url,
        )

    monkeypatch.setattr(auth_api, "issue_password_reset_token", _fake_issue_password_reset_token)
    monkeypatch.setattr(auth_api, "build_password_reset_url", _fake_build_password_reset_url)
    monkeypatch.setattr(auth_api, "send_password_reset_instructions", _fake_send_password_reset_instructions)

    response = await auth_api.forgot_password(
        auth_api.ForgotPasswordRequest(email=user.email),
        db,
    )

    assert response.delivery == "preview"
    assert response.preview_url is not None
    assert token_row.delivery == "preview"
    assert token_row.destination == user.email
    assert db.committed == 1


@pytest.mark.asyncio
async def test_reset_password_updates_hash_and_revokes_other_tokens(monkeypatch):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="reset@example.com",
        display_name="Reset User",
        password_hash=argon2.hash("OldPassword@123"),
    )
    token = SimpleNamespace(user_id=user.id)
    db = _AuthDb([user])
    revoked = {"called": False}

    async def _fake_consume_password_reset_token(_db, raw_token: str):
        assert raw_token == "valid-token"
        return token

    async def _fake_revoke_other_password_reset_tokens(_db, user_id):
        revoked["called"] = True
        assert user_id == user.id

    monkeypatch.setattr(auth_api, "consume_password_reset_token", _fake_consume_password_reset_token)
    monkeypatch.setattr(auth_api, "revoke_other_password_reset_tokens", _fake_revoke_other_password_reset_tokens)

    response = await auth_api.reset_password(
        auth_api.ResetPasswordRequest(token="valid-token", new_password="NewPassword@123"),
        db,
    )

    assert response.message.startswith("Password updated")
    assert argon2.verify("NewPassword@123", user.password_hash)
    assert revoked["called"] is True
    assert db.committed == 1


@pytest.mark.asyncio
async def test_change_password_updates_hash_and_revokes_tokens(monkeypatch):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="change@example.com",
        display_name="Change User",
        password_hash=argon2.hash("CurrentPassword@123"),
    )
    db = _AuthDb([])
    revoked = {"called": False}

    async def _fake_revoke_other_password_reset_tokens(_db, user_id):
        revoked["called"] = True
        assert user_id == user.id

    monkeypatch.setattr(auth_api, "revoke_other_password_reset_tokens", _fake_revoke_other_password_reset_tokens)

    response = await auth_api.change_password(
        auth_api.ChangePasswordRequest(
            current_password="CurrentPassword@123",
            new_password="UpdatedPassword@123",
        ),
        user,
        db,
    )

    assert response.message == "Password changed successfully."
    assert argon2.verify("UpdatedPassword@123", user.password_hash)
    assert revoked["called"] is True
    assert db.committed == 1


@pytest.mark.asyncio
async def test_clear_my_data_requires_confirmation_phrase():
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="wipe@example.com",
        display_name="Wipe User",
        password_hash=argon2.hash("CurrentPassword@123"),
    )
    db = _AuthDb([])

    with pytest.raises(auth_api.HTTPException) as exc:
        await auth_api.clear_my_data(
            auth_api.ClearUserDataRequest(
                current_password="CurrentPassword@123",
                confirmation="DELETE EVERYTHING",
            ),
            user,
            db,
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_clear_my_data_calls_reset_engine_and_commits(monkeypatch):
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="wipe2@example.com",
        display_name="Wipe User 2",
        password_hash=argon2.hash("CurrentPassword@123"),
    )
    db = _AuthDb([])

    async def _fake_clear_user_data_everywhere(_db, *, user_id):
        assert user_id == user.id
        return SimpleNamespace(
            deleted_rows={"canonical_transactions": 12, "statements": 3},
            deleted_files=7,
            deleted_directories=2,
            file_delete_errors=0,
        )

    monkeypatch.setattr(auth_api, "clear_user_data_everywhere", _fake_clear_user_data_everywhere)

    response = await auth_api.clear_my_data(
        auth_api.ClearUserDataRequest(
            current_password="CurrentPassword@123",
            confirmation="CLEAR MY DATA",
        ),
        user,
        db,
    )

    assert response.deleted_rows["canonical_transactions"] == 12
    assert response.deleted_files == 7
    assert db.committed == 1
