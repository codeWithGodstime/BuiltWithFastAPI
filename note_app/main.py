# Note app with aauthentication and CRUD operations
# learn to add rate limiting
# authentication with JWT
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from sqlmodel import SQLModel, Session, select
from db import engine, get_session
from contextlib import asynccontextmanager
from models import Note, User
from schemas import NoteCreate, NoteRead, UserCreate, UserRead
from security import AuthHandler, PasswordHasher, get_user

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code here
    SQLModel.metadata.create_all(engine)

    yield
    # Shutdown code here

app = FastAPI(lifespan=lifespan)



@app.post("/register", status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, session: Session = Depends(get_session)):
    db_user = get_user(data.email, session)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = PasswordHasher.hash_password(data.hashed_password)

    user = User(
        email=data.email,
        hashed_password=hashed_password,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )
    
    session.add(user)
    session.commit()
    session.refresh(user)

    access_token = AuthHandler().create_access_token(data={"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer", "data": UserRead.model_validate(user)}

@app.post("/token")
def login(credentials: OAuth2PasswordRequestForm = Depends(), session: Session =Depends(get_session)):
   
    user = get_user(credentials.username, session)

    if not user or not PasswordHasher.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = AuthHandler().create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/notes", response_model=NoteRead)
def create_note(note: NoteCreate, session: Session = Depends(get_session)):
    note = Note(
        title=note.title,
        content=note.content,
        created_at=datetime.utcnow().isoformat(),
        updated_at=datetime.utcnow().isoformat()
    )

    session.add(note)
    session.commit()
    session.refresh(note)   

    return note

@app.get("/notes/{note_id}", response_model=NoteRead)
def read_note(note_id: int, session: Session = Depends(get_session)):

    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note

@app.put("/notes/{note_id}", response_model=NoteRead)
def update_note(note_id: int, note_data: NoteCreate, session: Session = Depends(get_session)):
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
def delete_note(note_id: int, session: Session = Depends(get_session)):

    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
        
    session.delete(note)
    session.commit()
    
    return None