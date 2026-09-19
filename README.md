# wasap_group_analyzer

<a target="_blank" href="https://cookiecutter-data-science.drivendata.org/">
    <img src="https://img.shields.io/badge/CCDS-Project%20template-328F97?logo=cookiecutter" />
</a>

Análisis de un grupo de WhatsApp exportado desde el celular. Un pipeline de jobs toma el
zip exportado, lo anonimiza y genera conjuntos de datos *tidy* en `data/processed/`.
Sobre ellos, notebooks de marimo con DuckDB/SQL y spaCy responden quién escribe más,
cuándo, con qué palabras, emojis y stickers.

Los datos del chat son privados: `data/` nunca se sube a git (solo su estructura de
carpetas) y los notebooks publicados solo muestran nombres anonimizados.

## Instalación

```
cp params-example.yml params.yml   # ruta al zip exportado, zona horaria, modelo de spaCy
cp .env.example .env               # y generar ANON_SALT (ver el archivo)
uv sync
```

`params.yml` y `.env` están ignorados por git.

## Uso

```
make test            # corre la suite de pruebas
make lint            # ruff check + format --check
make format          # ruff check --fix + format
make nbs             # exporta los notebooks de marimo a .ipynb con salidas
```

## Estructura

```
params.yml                 <- configuración local (ignorado por git; ver params-example.yml)
.env                       <- ANON_SALT, la sal secreta para anonimizar (ignorado por git)
data/
├── raw/                   <- zip exportado, _chat.txt y FUENTE.txt (bronze)
├── interim/               <- mensajes parseados y anonimizados (transitorio)
└── processed/             <- conjuntos tidy (platinum)
references/                <- diccionarios de datos, uno por conjunto
notebooks/                 <- marimo (.py) y su exportación a .ipynb para GitHub
wasap_group_analyzer/
├── config.py              <- carga params.yml y .env, configura el logging
├── constants.py           <- rutas del proyecto
├── logging.py             <- decorador @log_execution (inicio/fin/error + tiempo)
├── policies/              <- FilePolicy: skip/overwrite/error ante archivos existentes
└── jobs/                  <- pasos del pipeline
tests/                     <- pruebas con datos sintéticos (nunca mensajes reales)
logs/                      <- logs de los jobs
```
