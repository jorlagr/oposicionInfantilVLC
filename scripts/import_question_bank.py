#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PyPDF2 import PdfReader


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def normalize_questions_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    # The source PDF prefixes question numbers with the page number: "2 9."
    text = re.sub(r"(?m)^\s*\d+\s+(\d+\.)", r"\1", text)
    # Some pages also prefix answer options with the page number: "5 c)"
    text = re.sub(r"(?m)^\s*\d+\s+([a-d]\))", r"\1", text)
    lines = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            lines.append("")
            continue
        if line == "TEST MAESTRO INFANTIL":
            continue
        if re.fullmatch(r"\d+", line):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_answers_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    lines = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        if line == "SOLUCIONARIO TEST MAESTRO INFANTIL":
            continue
        lines.append(line)
    return "\n".join(lines)


def compact_paragraph(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?)])", r"\1", text)
    text = re.sub(r"([¿(])\s+", r"\1", text)
    return text


def parse_questions(text: str) -> list[dict]:
    blocks = re.findall(r"(?ms)^\s*(\d+)\.\s+(.*?)(?=^\s*\d+\.\s+|\Z)", text)
    if not blocks:
        raise ValueError("No se han encontrado preguntas en el PDF.")

    questions = []
    for number_text, block in blocks:
        option_matches = list(
            re.finditer(r"(?ms)^\s*([a-d])\)\s+(.*?)(?=^\s*[a-d]\)\s+|\Z)", block)
        )
        if len(option_matches) not in {3, 4}:
            raise ValueError(
                f"La pregunta {number_text} no tiene un número válido de opciones: {len(option_matches)}."
            )

        number = int(number_text)
        question_text = compact_paragraph(block[: option_matches[0].start()])
        options = [
            {
                "id": chr(ord("a") + index),
                "text": compact_paragraph(match.group(2)),
            }
            for index, match in enumerate(option_matches)
        ]
        questions.append(
            {
                "id": f"q{number}",
                "number": number,
                "text": question_text,
                "options": options,
            }
        )

    return questions


def parse_answers(text: str) -> dict[int, str]:
    matches = re.findall(r"(\d+)\.\s*([A-D])", text)
    if not matches:
        raise ValueError("No se han encontrado respuestas en el solucionario del PDF.")
    return {int(number): option.lower() for number, option in matches}


def split_into_exams(
    questions: list[dict],
    answers: dict[int, str],
    exam_id_prefix: str,
    title_prefix: str,
    batch_size: int,
    source_pdf: Path,
) -> list[dict]:
    exams = []
    for index, start in enumerate(range(0, len(questions), batch_size), start=1):
        chunk = questions[start : start + batch_size]
        if not chunk:
            continue

        start_number = chunk[0]["number"]
        end_number = chunk[-1]["number"]
        questions_with_answers = []
        for question in chunk:
            number = question["number"]
            if number not in answers:
                raise ValueError(f"No existe respuesta para la pregunta {number}.")
            payload = dict(question)
            payload["correctOption"] = answers[number]
            questions_with_answers.append(payload)

        exams.append(
            {
                "id": f"{exam_id_prefix}-{index:02d}",
                "title": (
                    f"{title_prefix} · Examen {index:02d} · "
                    f"Preguntas {start_number}-{end_number}"
                ),
                "source": {
                    "questionsPdf": str(source_pdf),
                    "answersPdf": str(source_pdf),
                },
                "questionCount": len(questions_with_answers),
                "questions": questions_with_answers,
            }
        )

    return exams


def load_existing_payload(output_path: Path) -> dict:
    if not output_path.exists():
        return {"exams": []}

    raw = output_path.read_text(encoding="utf-8").strip()
    prefix = "window.TEST_APP_DATA = "
    suffix = ";"
    if not raw.startswith(prefix) or not raw.endswith(suffix):
        raise ValueError("El archivo de salida no tiene el formato esperado.")
    return json.loads(raw[len(prefix) : -len(suffix)])


def merge_payload(existing_payload: dict, new_exams: list[dict], exam_id_prefix: str) -> dict:
    exams = [
        exam
        for exam in existing_payload.get("exams", [])
        if not str(exam.get("id", "")).startswith(f"{exam_id_prefix}-")
    ]
    exams.extend(new_exams)
    exams.sort(key=lambda exam: exam.get("title", ""))
    return {"exams": exams}


def write_output(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = "window.TEST_APP_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    output_path.write_text(output, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa una batería grande de test desde un único PDF con solucionario al final."
    )
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exam-id-prefix", required=True)
    parser.add_argument("--title-prefix", required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--solutions-marker", default="SOLUCIONARIO TEST MAESTRO INFANTIL")
    args = parser.parse_args()

    full_text = extract_pdf_text(args.pdf)
    marker_index = full_text.find(args.solutions_marker)
    if marker_index == -1:
        raise ValueError("No se ha encontrado el marcador del solucionario dentro del PDF.")

    questions_text = normalize_questions_text(full_text[:marker_index])
    answers_text = normalize_answers_text(full_text[marker_index:])
    questions = parse_questions(questions_text)
    answers = parse_answers(answers_text)
    exams = split_into_exams(
        questions=questions,
        answers=answers,
        exam_id_prefix=args.exam_id_prefix,
        title_prefix=args.title_prefix,
        batch_size=args.batch_size,
        source_pdf=args.pdf,
    )

    payload = merge_payload(
        existing_payload=load_existing_payload(args.output),
        new_exams=exams,
        exam_id_prefix=args.exam_id_prefix,
    )
    write_output(payload, args.output)

    print(f"Preguntas importadas: {len(questions)}")
    print(f"Respuestas importadas: {len(answers)}")
    print(f"Exámenes generados: {len(exams)}")
    for exam in exams:
        print(f"- {exam['id']}: {exam['questionCount']} preguntas")


if __name__ == "__main__":
    main()
