import re
from pydantic import BaseModel, Field, field_validator, model_validator, EmailStr

class ResetPasswordSchema(BaseModel):
    password: str = Field(..., min_length=8, max_length=128)
    password_confirm: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("Пароль должен содержать хотя бы одну заглавную букву.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Пароль должен содержать хотя бы одну строчную букву.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Пароль должен содержать хотя бы одну цифру.")
        if not re.search(r"[\W_]", v):
            raise ValueError("Пароль должен содержать хотя бы один спецсимвол.")
        return v

    @model_validator(mode="after")
    def check_password_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Пароли не совпадают.")
        return self

# ВАЖНО: Класс называется UserRegister
class UserRegister(BaseModel):
    first_name: str = Field(..., min_length=2)
    last_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    password_confirm: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        if not re.search(r"[A-Z]", v):
            raise ValueError("Пароль должен содержать хотя бы одну заглавную букву.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Пароль должен содержать хотя бы одну строчную букву.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Пароль должен содержать хотя бы одну цифру.")
        if not re.search(r"[\W_]", v):
            raise ValueError("Пароль должен содержать хотя бы один спецсимвол.")
        return v

    @model_validator(mode="after")
    def check_password_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Пароли не совпадают.")
        return self