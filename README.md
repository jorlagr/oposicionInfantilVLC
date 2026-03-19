# Test de Oposición

Aplicación web responsive para practicar preguntas tipo test con corrección inmediata.

## Uso

1. Abrir `index.html` en el navegador.
2. Si prefieres servirlo por HTTP, usa `python3 -m http.server` dentro del proyecto.

## GitHub Pages

El proyecto ya incluye despliegue automático con GitHub Actions en `.github/workflows/deploy-pages.yml`.

Para activarlo en GitHub:

1. Sube el repositorio a GitHub.
2. En `Settings > Pages`, selecciona `Source: GitHub Actions`.
3. Haz push a la rama `main`.
4. GitHub publicará la web en la URL de Pages del repositorio.

Como la app usa rutas relativas, funciona correctamente tanto en local como publicada bajo la subruta del repositorio.

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
