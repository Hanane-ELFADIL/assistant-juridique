"""Routes historique et favoris."""
from __future__ import annotations
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from src.database import get_db
from src.models.user import User, Conversation, Message, Favorite
from src.auth import get_current_user

router = APIRouter(prefix="/api/user", tags=["History"])


# ── Conversations ──────────────────────────────────────────

@router.get("/conversations")
def list_conversations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    convs = db.query(Conversation).filter(Conversation.user_id == user.id)\
              .order_by(Conversation.updated_at.desc()).limit(50).all()
    return [{"id": c.id, "title": c.title,
             "updated_at": c.updated_at.isoformat() if c.updated_at else None,
             "created_at": c.created_at.isoformat() if c.created_at else None,
             "message_count": len(c.messages)} for c in convs]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(404, "Conversation introuvable")
    return {
        "id": conv.id, "title": conv.title,
        "messages": [_msg_dict(m) for m in conv.messages]
    }


@router.post("/conversations")
def create_conversation(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = Conversation(user_id=user.id, title="Nouvelle conversation")
    db.add(conv); db.commit(); db.refresh(conv)
    return {"id": conv.id, "title": conv.title}


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(404, "Conversation introuvable")
    db.delete(conv); db.commit()
    return {"ok": True}


class SaveMessageIn(BaseModel):
    conversation_id: Optional[int] = None
    question: str
    answer: str
    answer_type: str = "sourced"
    citations: list = []
    sources: list = []


@router.post("/messages")
def save_message(body: SaveMessageIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Créer ou récupérer la conversation
    if body.conversation_id:
        conv = db.query(Conversation).filter(Conversation.id == body.conversation_id, Conversation.user_id == user.id).first()
        if not conv:
            raise HTTPException(404, "Conversation introuvable")
    else:
        title = body.question[:80] + ("…" if len(body.question) > 80 else "")
        conv = Conversation(user_id=user.id, title=title)
        db.add(conv); db.flush()

    # Sauver question + réponse
    db.add(Message(conversation_id=conv.id, role="user", content=body.question))
    db.add(Message(
        conversation_id=conv.id, role="assistant",
        content=body.answer, answer_type=body.answer_type,
        citations_json=json.dumps(body.citations, ensure_ascii=False),
        sources_json=json.dumps(body.sources, ensure_ascii=False),
    ))
    db.commit()
    return {"conversation_id": conv.id, "title": conv.title}


# ── Favoris ────────────────────────────────────────────────

class FavoriteIn(BaseModel):
    question: str
    answer: str
    answer_type: str = "sourced"
    citations: list = []
    note: str = ""


@router.get("/favorites")
def list_favorites(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    favs = db.query(Favorite).filter(Favorite.user_id == user.id)\
              .order_by(Favorite.created_at.desc()).all()
    return [_fav_dict(f) for f in favs]


@router.post("/favorites")
def add_favorite(body: FavoriteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fav = Favorite(
        user_id=user.id, question=body.question,
        answer=body.answer, answer_type=body.answer_type,
        citations_json=json.dumps(body.citations, ensure_ascii=False),
        note=body.note,
    )
    db.add(fav); db.commit(); db.refresh(fav)
    return _fav_dict(fav)


@router.delete("/favorites/{fav_id}")
def remove_favorite(fav_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fav = db.query(Favorite).filter(Favorite.id == fav_id, Favorite.user_id == user.id).first()
    if not fav:
        raise HTTPException(404, "Favori introuvable")
    db.delete(fav); db.commit()
    return {"ok": True}


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id, "role": m.role, "content": m.content,
        "answer_type": m.answer_type,
        "citations": json.loads(m.citations_json) if m.citations_json else [],
        "sources": json.loads(m.sources_json) if m.sources_json else [],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _fav_dict(f: Favorite) -> dict:
    return {
        "id": f.id, "question": f.question, "answer": f.answer,
        "answer_type": f.answer_type, "note": f.note,
        "citations": json.loads(f.citations_json) if f.citations_json else [],
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }
