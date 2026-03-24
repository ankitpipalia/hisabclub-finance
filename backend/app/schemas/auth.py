from pydantic import BaseModel, EmailStr


class SetupRequest(BaseModel):
    email: str
    display_name: str
    password: str
    first_name: str | None = None
    date_of_birth: str | None = None  # DDMMYYYY


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str

    class Config:
        from_attributes = True
