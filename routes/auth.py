from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import uuid

try:
    from backend.database import get_db, User
    from backend.auth import hash_password, verify_password, create_token, firebase_auth, get_current_user
except ImportError:
    from database import get_db, User
    from auth import hash_password, verify_password, create_token, firebase_auth, get_current_user

router = APIRouter()

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class GoogleAuthRequest(BaseModel):
    id_token: str

class AuthResponse(BaseModel):
    token: str
    user: dict

@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=req.email,
        name=req.name or req.email.split("@")[0],
        password_hash=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name}
    }

@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_token(user.id)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name}
    }

@router.post("/google", response_model=AuthResponse)
def google_auth(req: GoogleAuthRequest, db: Session = Depends(get_db)):
    try:
        decoded = firebase_auth.verify_id_token(req.id_token)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {e}")

    uid   = decoded["uid"]
    email = decoded.get("email", "")
    name  = decoded.get("name", email.split("@")[0])

    user = db.query(User).filter(User.firebase_uid == uid).first()
    if not user:
        # Check if email exists (user registered with email before)
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.firebase_uid = uid
        else:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                name=name,
                firebase_uid=uid,
            )
            db.add(user)
    db.commit()
    db.refresh(user)

    token = create_token(user.id)
    return {
        "token": token,
        "user": {"id": user.id, "email": user.email, "name": user.name}
    }

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}