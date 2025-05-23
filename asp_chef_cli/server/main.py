from fastapi import Depends
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import clingo, dumbo

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5188",
        "https://asp-chef.alviano.net",
        "https://aspchef.alviano.net",
        "https://asp-chef.netlify.app",
    ],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["*"],
)
app.include_router(dumbo.router, prefix="/dumbo", tags=["dumbo"])
app.include_router(clingo.router, prefix="/clingo", tags=["clingo"])
