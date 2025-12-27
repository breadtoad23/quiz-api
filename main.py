
import os
import json
from typing import Dict, List, Any

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app = FastAPI()

# Разрешаем твой GitHub Pages (и локальную разработку)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://breadtoad23.github.io",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXAM_SIZE = 10

class ExamResponse(BaseModel):
    exam_id: str
    questions: List[Dict[str, Any]]  # [{id, text, options:[{id,text}]}]

@app.get("/exam", response_model=ExamResponse)
def get_exam():
    """
    Отдаёт вопросы и варианты БЕЗ правильных ответов.
    """
    import secrets
    exam_id = secrets.token_hex(8)

    try:
        with psycopg.connect(DATABASE_URL) as con:
            with con.cursor() as cur:
                # Берём N случайных вопросов
                cur.execute(
                    "select id, text from questions order by random() limit %s",
                    (EXAM_SIZE,)
                )
                qs = cur.fetchall()

                questions_out = []
                for qid, qtext in qs:
                    # Перемешиваем варианты прямо в SQL
                    cur.execute(
                        "select id, text from options where question_id=%s order by random()",
                        (qid,)
                    )
                    opts = [{"id": oid, "text": otext} for (oid, otext) in cur.fetchall()]
                    questions_out.append({"id": qid, "text": qtext, "options": opts})

        return {"exam_id": exam_id, "questions": questions_out}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/exam failed: {e}")


class SubmitPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    exam_id: str = Field(min_length=1, max_length=40)
    answers: Dict[str, int]  # question_id (строкой) -> option_id (числом)

@app.post("/submit")
def submit(payload: SubmitPayload):
    """
    Сервер сам считает score по option_id -> is_correct.
    На клиент правильные ответы не уходят.
    """
    try:
        answers = payload.answers

        # Мини-валидация
        if not answers:
            raise HTTPException(status_code=400, detail="No answers provided")

        score = 0
        with psycopg.connect(DATABASE_URL) as con:
            with con.cursor() as cur:
                # Считаем score
                for qid_str, opt_id in answers.items():
                    cur.execute("select is_correct, question_id from options where id=%s", (opt_id,))
                    row = cur.fetchone()
                    if not row:
                        raise HTTPException(status_code=400, detail=f"Unknown option_id={opt_id}")
                    is_correct, question_id = row

                    # Дополнительно: опция должна принадлежать указанному вопросу
                    try:
                        qid_int = int(qid_str)
                    except:
                        raise HTTPException(status_code=400, detail=f"Bad question_id key: {qid_str}")

                    if question_id != qid_int:
                        raise HTTPException(status_code=400, detail=f"Option {opt_id} does not belong to question {qid_int}")

                    if is_correct:
                        score += 1

                # Сохраняем попытку
                save_obj = {
                    "exam_id": payload.exam_id,
                    "answers": answers
                }
                cur.execute(
                    "insert into attempts(name, score, answers_json) values (%s, %s, %s)",
                    (payload.name.strip(), score, json.dumps(save_obj, ensure_ascii=False))
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
    Для тебя (админ). Потом можно убрать или спрятать.
    """
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
            {"id": r[0], "name": r[1], "submitted_at": str(r[2]), "score": r[3], "answers_json": r[4]}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/results failed: {e}")
