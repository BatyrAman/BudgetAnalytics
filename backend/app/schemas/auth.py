from pydantic import BaseModel, EmailStr, Field, field_validator

PASSWORD_MIN = 8
PASSWORD_MAX_BYTES = 72  # ограничение bcrypt


def _check_password(value: str) -> str:
    if len(value) < PASSWORD_MIN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN} characters")
    if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_BYTES} bytes")
    return value


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str

    _password = field_validator("password")(_check_password)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = Field(default=None, description="Access token lifetime, seconds")
    # Только в legacy-режиме REFRESH_TOKEN_IN_BODY=true; иначе refresh
    # передаётся исключительно в httpOnly-cookie.
    refresh_token: str | None = None


# Обратная совместимость имени схемы из v0.1.
RefreshTokenResponse = Token


class RefreshTokenRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=256)
    new_password: str

    _password = field_validator("new_password")(_check_password)


class DeleteAccountRequest(BaseModel):
    password: str = Field(max_length=256)


class MessageResponse(BaseModel):
    message: str
