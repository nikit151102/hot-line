from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from database.database_app import create_db_if_not_exists, create_tables
from migration import run_auto_migrations
from fastapi.middleware.cors import CORSMiddleware
from routers.hotline import router as hotline_router

create_db_if_not_exists()
create_tables()

# выполняем autogenerate+upgrade
run_auto_migrations()

app = FastAPI(debug=True)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200","http://localhost:51562", "https://xn--80akonecy.xn--p1ai/", "https://xn--80akonecy.xn--p1ai", "https://xn--80aac6chp.xn--80akonecy.xn--p1ai", "https://xn--80aac6chp.xn--80akonecy.xn--p1ai/", "https://xn--90aos.xn--80akonecy.xn--p1ai","https://xn--90aos.xn--80akonecy.xn--p1ai/"],
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)


# Зарегистрируйте роутер в приложении
app.include_router(hotline_router)