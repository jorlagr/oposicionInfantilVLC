# Test de Oposición

Aplicación web responsive para practicar preguntas tipo test con corrección inmediata.

## Uso

1. Abrir [index.html](/Users/jolatorr/Documents/_gitProjects/TestVVG/index.html) en el navegador.
2. Si prefieres servirlo por HTTP, usa `python3 -m http.server` dentro del proyecto.

## Añadir nuevos exámenes

El proyecto incluye un importador desde PDF:

```bash
python3 scripts/import_exam.py \
  --questions-pdf "/ruta/cuadernillo.pdf" \
  --answers-pdf "/ruta/respuestas.pdf" \
  --output "data/exams.js" \
  --exam-id "mi-examen" \
  --title "Mi examen"
```

Para acumular varios exámenes en el mismo catálogo:

```bash
python3 scripts/import_exam.py \
  --questions-pdf "/ruta/cuadernillo.pdf" \
  --answers-pdf "/ruta/respuestas.pdf" \
  --output "data/exams.js" \
  --exam-id "mi-examen" \
  --title "Mi examen" \
  --merge
```
