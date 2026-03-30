from pydantic import BaseModel


class SetupRequest(BaseModel):
    email: str
    display_name: str
    password: str
    first_name: str | None = None
    date_of_birth: str | None = None  # DDMMYYYY


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ForgotPasswordResponse(BaseModel):
    message: str
    delivery: str
    preview_url: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ClearUserDataRequest(BaseModel):
    current_password: str
    confirmation: str


class MessageResponse(BaseModel):
    message: str


class ClearUserDataResponse(BaseModel):
    message: str
    deleted_rows: dict[str, int]
    deleted_files: int
    deleted_directories: int
    file_delete_errors: int


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
