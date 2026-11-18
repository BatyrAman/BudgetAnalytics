from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

# Bounds for hashing cost: Argon2 work grows with input length.
PASSWORD_MIN = 8
PASSWORD_MAX = 128
LOGIN_PASSWORD_MAX = 1024  # no minimum: accounts created before the policy must still sign in


def _lower(value: str) -> str:
    return value.lower()


NormalizedEmail = Annotated[EmailStr, AfterValidator(_lower)]
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class RegisterRequest(BaseModel):
    full_name: FullName
    email: NormalizedEmail
    password: NewPassword


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(max_length=LOGIN_PASSWORD_MAX)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(max_length=LOGIN_PASSWORD_MAX)
    new_password: NewPassword


class MessageResponse(BaseModel):
    message: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class RefreshTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
