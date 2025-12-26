import os, json
from datetime import datetime
from typing import Any, Dict

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in environment variables")

app = FastAPI()

# ✅ ВАЖНО: укажи свой домен GitHub Pages (и localhost для тестов)
# Если хочешь, можно оставить "*" — но тогда allow_credentials должен быть False.
allowed_origins = [
    "https://breadtoad23.github.io",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,   # ✅ лучше явно
    allow_credentials=False,         # ✅ важно для браузера
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)

class SubmitPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    score: int = Field(ge=0, le=9999)
    answers: Dict[str, Any]

@app.get("/health")
def health():
    return {"ok": True, "ts": datetime.utcnow().isoformat()}

@app.post("/submit")
def submit(p: SubmitPayload):
    try:
        with psycopg.connect(DATABASE_URL) as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    insert into attempts(name, score, answers_json)
                    values (%s, %s, %s)
                    """,
                    (p.name.strip(), p.score, json.dumps(p.answers, ensure_ascii=False))
                )
            con.commit()
        return {"ok": True}
    except Exception as e:
        # Чтобы в /docs и в браузере было понятно что случилось
        raise HTTPException(status_code=500, detail=f"DB insert failed: {type(e).__name__}")

@app.get("/results")
def results():
    try:
        with psycopg.connect(DATABASE_URL) as con:
            with con.cursor() as cur:
                cur.execute("""
                    select id, name, submitted_at, score, answers_json
                    from attempts
                    order by id desc
                    limit 200
                """)
                rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "name": r[1],
                "submitted_at": str(r[2]),
                "score": r[3],
                "answers": r[4],
            }
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB read failed: {type(e).__name__}")
