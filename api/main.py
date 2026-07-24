from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Импорты из ваших файлов
from database.database_app import create_db_if_not_exists, async_engine
from migration import run_auto_migrations
from routers.hotline import router as hotline_router
from crud import init_default_data
from sqlalchemy.ext.asyncio import AsyncSession

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Запуск инициализации базы данных...")
    
    create_db_if_not_exists()
    
    run_auto_migrations()
    
    async with AsyncSession(async_engine) as db:
        await init_default_data(db)
        
    print("Приложение полностью инициализировано и готово к работе!")
    
    yield 
    
    print("Завершение работы приложения...")


app = FastAPI(
    debug=True,
    title="Hotline API",
    description="API для системы горячей линии и анонимных обращений",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200", 
        "https://xn--80akonecy.xn--p1ai/", 
        "https://xn--80akonecy.xn--p1ai", 
        "https://xn--80aac6chp.xn--80akonecy.xn--p1ai", 
        "https://xn--80aac6chp.xn--80akonecy.xn--p1ai/", 
        "https://xn--90aos.xn--80akonecy.xn--p1ai",
        "https://xn--90aos.xn--80akonecy.xn--p1ai/"
    ],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.include_router(hotline_router)
