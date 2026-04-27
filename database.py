from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import uuid
import os

# Use PostgreSQL on Railway, SQLite locally
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./sova.db"
)

# Railway gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class User(Base):
    __tablename__ = "users"
    id            = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email         = Column(String, unique=True, index=True, nullable=False)
    name          = Column(String, nullable=True)
    password_hash = Column(String, nullable=True)
    firebase_uid  = Column(String, unique=True, nullable=True)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)
    chats         = relationship("Chat", back_populates="user", cascade="all, delete")

class Chat(Base):
    __tablename__ = "chats"
    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    title      = Column(String, nullable=False)
    mode       = Column(String, default="chat")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    user       = relationship("User", back_populates="chats")
    messages   = relationship("Message", back_populates="chat", cascade="all, delete", order_by="Message.created_at")

class Message(Base):
    __tablename__ = "messages"
    id         = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id    = Column(String, ForeignKey("chats.id"), nullable=False)
    role       = Column(String, nullable=False)
    content    = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    chat       = relationship("Chat", back_populates="messages")

def create_tables():
    Base.metadata.create_all(bind=engine)