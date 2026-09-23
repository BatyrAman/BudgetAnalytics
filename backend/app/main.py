from contextlib import asynccontextmanager
import sqlalchemy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Создание таблиц при первом запуске
    Base.metadata.create_all(bind=engine)

    print("=" * 60)
    print(f"{settings.APP_NAME} started successfully")
    print(f"Docs: http://127.0.0.1:8000/docs")
    print("=" * 60)

    yield

    print(f"{settings.APP_NAME} stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Budget Analytics API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # позже заменить на адрес Frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# API
app.include_router(
    api_router,
    prefix=settings.API_PREFIX,
)


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to Budget Analytics API",
        "docs": "/docs",
        "redoc": "/redoc",
        "version": settings.VERSION,
    }


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
    }


@app.get("/home", tags=["Home"])
async def home():
    return {"message": "Hello World"}