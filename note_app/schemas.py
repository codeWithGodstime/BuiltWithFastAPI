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