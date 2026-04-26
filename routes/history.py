from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db, Chat, Message, User
from auth import get_current_user
import uuid, datetime

router = APIRouter()

class MessageIn(BaseModel):
    role: str
    content: str

class SaveChatRequest(BaseModel):
    chat_id: Optional[str] = None
    title: str
    mode: str = "chat"
    messages: List[MessageIn]

@router.get("/chats")
def get_chats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chats = (
        db.query(Chat)
        .filter(Chat.user_id == user.id)
        .order_by(Chat.updated_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": c.id,
            "title": c.title,
            "mode": c.mode,
            "updated_at": c.updated_at.isoformat(),
        }
        for c in chats
    ]

@router.get("/chats/{chat_id}")
def get_chat(
    chat_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {
        "id": chat.id,
        "title": chat.title,
        "mode": chat.mode,
        "messages": [
            {"role": m.role, "content": m.content}
            for m in chat.messages
        ]
    }

@router.post("/chats")
def save_chat(
    req: SaveChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if req.chat_id:
        chat = db.query(Chat).filter(Chat.id == req.chat_id, Chat.user_id == user.id).first()
        if chat:
            # Update existing
            chat.title      = req.title
            chat.updated_at = datetime.datetime.utcnow()
            # Delete old messages and replace
            db.query(Message).filter(Message.chat_id == chat.id).delete()
        else:
            chat = None
    else:
        chat = None

    if not chat:
        chat = Chat(
            id=req.chat_id or str(uuid.uuid4()),
            user_id=user.id,
            title=req.title,
            mode=req.mode,
        )
        db.add(chat)
        db.flush()

    for msg in req.messages:
        db.add(Message(
            id=str(uuid.uuid4()),
            chat_id=chat.id,
            role=msg.role,
            content=msg.content,
        ))

    db.commit()
    return {"id": chat.id, "status": "saved"}

@router.delete("/chats/{chat_id}")
def delete_chat(
    chat_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(chat)
    db.commit()
    return {"status": "deleted"}