"""Routes d'authentification — inscription, connexion, profil."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
from src.database import get_db
from src.models.user import User
from src.auth import hash_password, verify_password, create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class RegisterIn(BaseModel):
    email: str
    username: str
    password: str
    full_name: str = ""

    @field_validator("password")
    @classmethod
    def check_pw(cls, v):
        if len(v) < 6:
            raise ValueError("Mot de passe trop court (min 6 caractères)")
        return v

    @field_validator("username")
    @classmethod
    def check_username(cls, v):
        if len(v.strip()) < 2:
            raise ValueError("Nom d'utilisateur trop court")
        return v.strip()


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(400, "Email déjà utilisé")
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(400, "Nom d'utilisateur déjà pris")

    import random
    colors = ["#c0392b", "#1a2744", "#d4a843", "#2c7a4b", "#6b4c9a"]
    user = User(
        email=body.email.lower(),
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name or body.username,
        avatar_color=random.choice(colors),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_token({"sub": user.id})
    return {"access_token": token, "user": _user_dict(user)}


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(401, "Email ou mot de passe incorrect")
    if not user.is_active:
        raise HTTPException(403, "Compte désactivé")
    token = create_token({"sub": user.id})
    return {"access_token": token, "user": _user_dict(user)}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_dict(user)


def _user_dict(u: User) -> dict:
    return {
        "id": u.id, "email": u.email,
        "username": u.username, "full_name": u.full_name,
        "avatar_color": u.avatar_color,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
