# Note app with aauthentication and CRUD operations
# learn to add rate limiting
# authentication with JWT
from fastapi import FastAPI, Depends, HTTPException, status
from datetime import datetime
from sqlmodel import SQLModel, create_engine, Session
from contextlib import asynccontextmanager
from models import Note
from schemas import NoteCreate, NoteRead

sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
engine = create_engine(sqlite_url, echo=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code here
    SQLModel.metadata.create_all(engine)

    yield
    # Shutdown code here

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Note App!"}

@app.post("/notes/", response_model=NoteRead)
async def create_note(note: NoteCreate):
    note = Note(
        title=note.title,
        content=note.content,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )

    with Session(engine) as session:
        session.add(note)
        session.commit()
        session.refresh(note)   

    return note

@app.get("/notes/{note_id}", response_model=NoteRead)
async def read_note(note_id: int):
    with Session(engine) as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
    return note

@app.put("/notes/{note_id}", response_model=NoteRead)
async def update_note(note_id: int, note_data: NoteCreate):
    with Session(engine) as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        note.title = note_data.title
        note.content = note_data.content
        note.updated_at = datetime.utcnow().isoformat()
        
        session.add(note)
        session.commit()
        session.refresh(note)
    
    return note

@app.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(note_id: int):
    with Session(engine) as session:
        note = session.get(Note, note_id)
        if not note:
            raise HTTPException(status_code=404, detail="Note not found")
        
        session.delete(note)
        session.commit()
    
    return None