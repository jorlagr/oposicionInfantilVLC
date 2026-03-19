#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PyPDF2 import PdfReader


HEADER_PATTERNS = (
    "TRIBUNAL CALIFICADOR PRUEBAS SELECTIVAS",
    "EDUCADOR/A INFANTIL",
    "AYUNTAMIENTO DE MADRID",
)

TEXT_REPLACEMENTS = {
    "disp uesto": "dispuesto",
    "elabo ración": "elaboración",
    "ec har": "echar",
    "q ue": "que",
    "pa rto": "parto",
    "peo no": "pero no",
    "apartado s": "apartados",
    "nace r": "nacer",
    "hac e": "hace",
    "d e la": "de la",
    "d e la pareja": "de la pareja",
    "Dispone r": "Disponer",
    "Acompaña r": "Acompañar",
    "reformula r": "reformular",
    "garantiza r": "garantizar",
    "Conducir  la": "Conducir la",
    "Organiza r": "Organizar",
    "realiza r": "realizar",
    "plantea r": "plantear",
    "r espuestas": "respuestas",
    "ni expo ner": "ni exponer",
    "Un a bebé": "Una bebé",
}


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def normalize_text(raw_text: str) -> str:
    lines = []
    for line in raw_text.splitlines():
        stripped = " ".join(line.strip().split())
        if not stripped:
            lines.append("")
            continue
        if stripped.startswith("Página "):
            continue
        if stripped in HEADER_PATTERNS:
            continue
        if stripped in {
            "PRUEBAS SELECTIVAS",
            "PARA PROVEER 7 PLAZAS CATEGORÍA",
            "EJERCICIO PRÁCTICO",
            "MODELO A",
            "31 DE ENERO DE 2026",
            "PLANTILLA CORRECTORA",
            "PREGUNTA RESPUESTA",
        }:
            continue
        lines.append(stripped)

    text = "\n".join(lines)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    for source, target in TEXT_REPLACEMENTS.items():
        text = text.replace(source, target)
    return text.strip()


def compact_paragraph(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?)])", r"\1", text)
    text = re.sub(r"([¿(])\s+", r"\1", text)
    return text


def parse_answers(raw_text: str) -> dict[int, str]:
    clean_text = normalize_text(raw_text)
    matches = re.findall(r"(\d+)\s+([ABC])", clean_text)
    if not matches:
        raise ValueError("No se han encontrado respuestas en el PDF de plantilla.")
    return {int(number): letter.lower() for number, letter in matches}


def parse_questions(raw_text: str, answers: dict[int, str]) -> list[dict]:
    clean_text = normalize_text(raw_text)
    blocks = re.findall(r"(?ms)^\s*(\d+)\.\s+(.*?)(?=^\s*\d+\.\s+|\Z)", clean_text)
    if not blocks:
        raise ValueError("No se han encontrado preguntas en el PDF de cuadernillo.")

    questions = []
    for number_text, block in blocks:
        number = int(number_text)
        option_matches = list(re.finditer(r"(?ms)^\s*([abc])\)\s+(.*?)(?=^\s*[abc]\)\s+|\Z)", block))
        if len(option_matches) != 3:
            raise ValueError(f"La pregunta {number} no tiene exactamente tres opciones.")

        question_text = compact_paragraph(block[: option_matches[0].start()])
        options = [
            {
                "id": chr(ord("a") + index),
                "text": compact_paragraph(match.group(2)),
            }
            for index, match in enumerate(option_matches)
        ]

        if number not in answers:
            raise ValueError(f"No existe respuesta para la pregunta {number}.")

        questions.append(
            {
                "id": f"q{number}",
                "number": number,
                "text": question_text,
                "options": options,
                "correctOption": answers[number],
            }
        )

    return questions


def build_exam_payload(
    questions_pdf: Path,
    answers_pdf: Path,
    exam_id: str,
    title: str,
) -> dict:
    answers = parse_answers(extract_pdf_text(answers_pdf))
    questions = parse_questions(extract_pdf_text(questions_pdf), answers)

    return {
        "exams": [
            {
                "id": exam_id,
                "title": title,
                "source": {
                    "questionsPdf": str(questions_pdf),
                    "answersPdf": str(answers_pdf),
                },
                "questionCount": len(questions),
                "questions": questions,
            }
        ]
    }


def load_existing_payload(output_path: Path) -> dict:
    if not output_path.exists():
        return {"exams": []}

    raw = output_path.read_text(encoding="utf-8").strip()
    prefix = "window.TEST_APP_DATA = "
    suffix = ";"
    if not raw.startswith(prefix) or not raw.endswith(suffix):
        raise ValueError("El archivo de salida no tiene el formato esperado.")

    return json.loads(raw[len(prefix) : -len(suffix)])


def merge_payload(existing_payload: dict, new_exam: dict) -> dict:
    exams = [exam for exam in existing_payload.get("exams", []) if exam.get("id") != new_exam["id"]]
    exams.append(new_exam)
    exams.sort(key=lambda exam: exam.get("title", ""))
    return {"exams": exams}


def write_output(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = "window.TEST_APP_DATA = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    output_path.write_text(output, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Importa un examen tipo test desde PDFs.")
    parser.add_argument("--questions-pdf", required=True, type=Path)
    parser.add_argument("--answers-pdf", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--exam-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Añade o actualiza el examen en el catálogo existente.",
    )
    args = parser.parse_args()

    payload = build_exam_payload(
        questions_pdf=args.questions_pdf,
        answers_pdf=args.answers_pdf,
        exam_id=args.exam_id,
        title=args.title,
    )
    if args.merge:
        existing_payload = load_existing_payload(args.output)
        payload = merge_payload(existing_payload, payload["exams"][0])

    write_output(payload, args.output)
    print(f"Examen importado: {args.output}")


if __name__ == "__main__":
    main()
