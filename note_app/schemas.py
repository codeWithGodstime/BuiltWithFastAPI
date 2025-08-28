from sqlmodel import SQLModel, Field
from typing import Optional


class NoteBase(SQLModel):
    title: str
    content: str

class NoteCreate(NoteBase):
    pass

class NoteRead(NoteBase):
    id: int
    created_at: str
    updated_at: str

class UserBase(SQLModel):
    email: str

class UserCreate(UserBase):
    hashed_password: str

class UserRead(UserBase):
    id: int
    created_at: str
    updated_at: str