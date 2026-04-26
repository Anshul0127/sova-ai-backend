from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from backend.database import create_tables
from backend.routes.chat import router as chat_router
from backend.routes.auth import router as auth_router
from backend.routes.history import router as history_router

load_dotenv()
create_tables()

app = FastAPI(title="Sova AI", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router,    prefix="/api")
app.include_router(auth_router,    prefix="/api/auth")
app.include_router(history_router, prefix="/api")

@app.get("/")
def root():
    return {"status": "Sova online"}

@app.get("/health")
def health():
    return {"status": "ok"}