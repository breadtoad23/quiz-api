
import os
import json
import secrets
from typing import Dict, Any, List

import psycopg2
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")


app = FastAPI()

# Для учебного проекта можно оставить *
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXAM_SIZE = 10


def db_connect():
    """
    psycopg2 стабильно работает с Supabase pooler
    """
    return psycopg2.connect(DATABASE_URL)


@app.get("/")
def root():
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/exam")
def get_exam():
    """
    Отдаёт 10 случайных вопросов.
    Без правильных ответов.
    """
    exam_id = secrets.token_hex(8)

    try:
        con = db_connect()
        cur = con.cursor()

        cur.execute(
            "select id, text from questions order by random() limit %s",
            (EXAM_SIZE,)
        )
        qs = cur.fetchall()

        questions: List[Dict[str, Any]] = []

        for qid, qtext in qs:
            cur.execute(
                "select id, text from options where question_id=%s order by random()",
                (qid,)
            )
            opts = [{"id": oid, "text": otext} for (oid, otext) in cur.fetchall()]
            questions.append({
                "id": qid,
                "text": qtext,
                "options": opts
            })

        cur.close()
        con.close()

        return {
            "exam_id": exam_id,
            "questions": questions
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/exam failed: {e}")


class SubmitPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exam_id: str
    answers: Dict[str, int]  # question_id -> option_id


@app.post("/submit")
def submit(payload: SubmitPayload):
    """
    Сервер сам проверяет ответы.
    """
    try:
        if not payload.answers:
            raise HTTPException(status_code=400, detail="No answers provided")

        score = 0

        con = db_connect()
        cur = con.cursor()

        for qid_str, opt_id in payload.answers.items():
            try:
                qid = int(qid_str)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Bad question id: {qid_str}")

            cur.execute(
                "select question_id, is_correct from options where id=%s",
                (opt_id,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail=f"Unknown option_id={opt_id}")

            real_qid, is_correct = row

            if real_qid != qid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Option {opt_id} does not belong to question {qid}"
                )

            if is_correct:
                score += 1

        answers_json = {
            "exam_id": payload.exam_id,
            "answers": payload.answers
        }

        cur.execute(
            "insert into attempts(name, score, answers_json) values (%s, %s, %s)",
            (payload.name.strip(), score, json.dumps(answers_json, ensure_ascii=False))
        )

        con.commit()
        cur.close()
        con.close()

        return {"ok": True, "score": score}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/submit failed: {e}")


@app.get("/results")
def results():
    """
    Последние попытки (для тебя).
    """
    try:
        con = db_connect()
        cur = con.cursor()

        cur.execute(
            """
            select id, name, submitted_at, score, answers_json
            from attempts
            order by id desc
            limit 200
            """
        )
        rows = cur.fetchall()

        cur.close()
        con.close()

        return [
            {
                "id": r[0],
                "name": r[1],
                "submitted_at": str(r[2]),
                "score": r[3],
                "answers_json": r[4]
            }
            for r in rows
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/results failed: {e}")
