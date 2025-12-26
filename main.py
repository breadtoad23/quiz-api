import os, json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg

DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для учебного проекта ок
    allow_methods=["*"],
    allow_headers=["*"],
)

class SubmitPayload(BaseModel):
    name: str
    score: int
    answers: dict

@app.post("/submit")
def submit(p: SubmitPayload):
    with psycopg.connect(DATABASE_URL) as con:
        with con.cursor() as cur:
            cur.execute(
                "insert into attempts(name, score, answers_json) values (%s, %s, %s)",
                (p.name, p.score, json.dumps(p.answers, ensure_ascii=False))
            )
        con.commit()
    return {"ok": True}

@app.get("/results")
def results():
    with psycopg.connect(DATABASE_URL) as con:
        with con.cursor() as cur:
            cur.execute("select id, name, submitted_at, score, answers_json from attempts order by id desc limit 200")
            rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "submitted_at": str(r[2]), "score": r[3], "answers": r[4]}
        for r in rows
    ]
