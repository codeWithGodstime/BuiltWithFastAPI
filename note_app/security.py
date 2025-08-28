from typing import Annotated
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
import jwt
from jwt import PyJWTError, InvalidTokenError
from datetime import datetime, timedelta
from passlib.context import CryptContext
from sqlmodel import Session, select
from models import User

SECRET_KEY = "your_secret_key"
ALGORITHM = "HS256"    
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


class PasswordHasher:
    @staticmethod
    def hash_password(password: str) -> str:
        return password_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return password_context.verify(plain_password, hashed_password)


class AuthHandler:
    def create_access_token(self, data: dict):
        to_encode = data.copy()
        expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    
    def verify_token(self, token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload['sub']
        except PyJWTError:
            return None

auth_handler = AuthHandler()


def get_user(email: str, session: Session):
    statement = select(User).where(User.email == email)
    results = session.exec(statement)
    return results.first()


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: Session = Depends()):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = auth_handler.verify_token(token)
    if token_data is None:
        raise credentials_exception
    
    user = get_user(token_data, session)
    return user