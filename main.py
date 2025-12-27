
import os
import json
import secrets
from typing import Dict, Any, List

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set (Render -> Environment -> add DATABASE_URL)")


app = FastAPI()

# Для учебного проекта можно оставить "*"
# Если хочешь строже — поставь свой GitHub Pages домен:
# allow_origins=["https://breadtoad23.github.io"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXAM_SIZE = 10  # сколько вопросов отдаём в тесте


def db_connect():
    return psycopg.connect(
        DATABASE_URL,
        prepare_threshold=0,
        autocommit=True
    )

@app.get("/")
def root():
    return {"ok": True, "service": "quiz-api"}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/exam")
def get_exam():
    """
    Отдаёт 10 случайных вопросов.
    В ответе НЕТ правильных ответов.
    Варианты перемешаны (order by random()).
    """
    exam_id = secrets.token_hex(8)

    try:
        with db_connect() as con:
            with con.cursor() as cur:
                cur.execute(
                    "select id, text from questions order by random() limit %s",
                    (EXAM_SIZE,),
                )
                qs = cur.fetchall()

                questions_out: List[Dict[str, Any]] = []
                for qid, qtext in qs:
                    cur.execute(
                        "select id, text from options where question_id=%s order by random()",
                        (qid,),
                    )
                    opts = [{"id": oid, "text": otext} for (oid, otext) in cur.fetchall()]
                    questions_out.append({"id": qid, "text": qtext, "options": opts})

        return {"exam_id": exam_id, "questions": questions_out}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/exam failed: {e}")


class SubmitPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exam_id: str = Field(min_length=1, max_length=40)
    # question_id (строкой) -> option_id (числом)
    answers: Dict[str, int]


@app.post("/submit")
def submit(payload: SubmitPayload):
    """
    Принимает ответы вида:
    {
      "name": "Маша",
      "exam_id": "....",
      "answers": { "12": 55, "13": 60, ... }
    }

    Сервер:
    - проверяет принадлежность option_id к question_id
    - считает score по options.is_correct
    - сохраняет попытку в attempts
    """
    try:
        if not payload.answers:
            raise HTTPException(status_code=400, detail="No answers provided")

        score = 0

        with db_connect() as con:
            with con.cursor() as cur:
                # Считаем score
                for qid_str, opt_id in payload.answers.items():
                    try:
                        qid = int(qid_str)
                    except ValueError:
                        raise HTTPException(status_code=400, detail=f"Bad question id key: {qid_str}")

                    cur.execute(
                        "select question_id, is_correct from options where id=%s",
                        (opt_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise HTTPException(status_code=400, detail=f"Unknown option_id={opt_id}")

                    real_qid, is_correct = row

                    # option должна принадлежать указанному вопросу
                    if real_qid != qid:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Option {opt_id} does not belong to question {qid}",
                        )

                    if is_correct:
                        score += 1

                # Сохраняем в attempts
                answers_json = {
                    "exam_id": payload.exam_id,
                    "answers": payload.answers,
                }

                cur.execute(
                    "insert into attempts(name, score, answers_json) values (%s, %s, %s)",
                    (payload.name.strip(), score, json.dumps(answers_json, ensure_ascii=False)),
                )
            con.commit()

        return {"ok": True, "score": score}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/submit failed: {e}")


@app.get("/results")
def results():
    """
    Последние 200 попыток — для тебя.
    Если хочешь скрыть от одногруппников — потом уберём/защитим.
    """
    try:
        with db_connect() as con:
            with con.cursor() as cur:
                cur.execute(
                    """
                    select id, name, submitted_at, score, answers_json
                    from attempts
                    order by id desc
                    limit 200
                    """
                )
                rows = cur.fetchall()

        return [
            {
                "id": r[0],
                "name": r[1],
                "submitted_at": str(r[2]),
                "score": r[3],
                "answers_json": r[4],
            }
            for r in rows
        ]

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/results failed: {e}")

