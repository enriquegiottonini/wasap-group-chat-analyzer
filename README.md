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
cp params-example.yml params.yml   # chats y sus zips exportados, zona horaria, modelo de spaCy
cp .env.example .env               # y generar ANON_SALT (ver el archivo)
uv sync
```

`params.yml` y `.env` están ignorados por git.

### Varios chats

Cada chat vive en su propia carpeta, `data/{raw,interim,processed}/<chat>/`, así que se
pueden tener varios grupos a la vez sin borrar nada. En `params.yml`, `chats` registra
cada chat (un slug → la ruta a su zip exportado) y `chat` elige el activo, que es el que
usan los jobs y los notebooks. Para trabajar con otro sin editar el archivo:
`make ... CHAT=<slug>`.

```
make ingest                          # el chat activo, desde el zip registrado en `chats`
make ingest CHAT=los_primos          # otro chat registrado
make ingest ZIP=~/Downloads/"WhatsApp Chat - Los Primos.zip"   # uno nuevo: slug = los_primos
```

## Uso

```
make data            # todo el pipeline del chat activo: ingest → anonymize
make ingest          # copia el zip exportado a data/raw/, lo descomprime y escribe FUENTE.txt
make anonymize       # parsea el chat y lo deja en data/interim/: bronze, messages_anon y members
make process         # genera los conjuntos tidy en data/processed/: messages, tokens y emojis
make leak-check      # falla si un nombre real aparece en interim, processed, notebooks o references
make test            # corre la suite de pruebas
make lint            # ruff check + format --check
make format          # ruff check --fix + format
make nbs             # exporta los notebooks de marimo a .ipynb con salidas
```

`make anonymize` parsea `data/raw/<chat>/_chat.txt` (una fila por mensaje) y deja en
`data/interim/<chat>/`:

- `bronze.parquet`: los mensajes parseados **con nombres reales** y el texto sin tocar,
  para análisis manual en esta máquina (p. ej. con `duckdb`). Nunca sale de `data/`.
- `messages_anon.parquet`: la versión anonimizada, entrada del análisis. Los remitentes
  son ids (hash con la sal de `.env`) y en el texto las menciones, nombres, URLs, correos
  y números largos se sustituyen por marcas (`@[id]`, `[id]`, `[nombre]`, `[url:dominio]`,
  `[correo]`, `[numero]`). Los avisos y las ubicaciones pierden el texto.
- `members.parquet`: el alias de cada miembro, un animal de México ("Ajolote",
  "Jaguar"...) en el orden en que escribió por primera vez. Se asigna aquí, donde se
  conocen los nombres reales, para saltar cualquier alias que comparta una palabra con
  ellos.

`make process` convierte lo anterior en los tres conjuntos tidy de
`data/processed/<chat>/`, con spaCy (`es_core_news_sm`) para las palabras:
`messages.parquet` (una fila por mensaje, con alias, tipo, texto y conteos),
`tokens.parquet` (una fila por token, con lema, categoría gramatical y si es palabra,
vacía o risa) y `emojis.parquet` (una fila por emoji). Cada uno tiene su diccionario de
datos en [`references/`](references/README.md); las tres tablas se unen por `message_id`.

La sección `anonymize` de `params.yml` ajusta el enmascarado: `keep_words` (palabras
que forman parte de un nombre de contacto pero son comunes en el chat, p. ej. la
carrera), `allow_names` (bots como Meta AI), `extra_names` (apodos y nombres de personas
que no son nombres de contacto, como maestros o amigos: se enmascaran como `[nombre]`) y
`min_length`. `make leak-check` busca cada nombre real (y cada `extra_names`) en todo lo
que se puede publicar; `SHOW=1` lista los que encuentre.

### Notebooks

Se editan con marimo (`uv run marimo edit notebooks/<nombre>.py`) y se exportan a
`.ipynb` con sus salidas (`make nbs`) para que GitHub los muestre. Nunca muestran
nombres reales: los remitentes aparecen con un id anónimo (hash con la sal de `.env`).

- `utils`: funciones compartidas por los otros dos (DuckDB del chat activo con la
  función `anon()`, tablas y gráficas), al estilo de los `AdventUtils` de Norvig.
- `01_eda_bronze`: los datos crudos tal como los exporta WhatsApp, su estructura y
  rarezas, y la tabla de qué se conserva y qué se descarta.
- `02_eda_silver`: con los mensajes anonimizados decide el diseño de los datos tidy
  (tipos de mensaje, alias, qué es una palabra, emojis, risas, palabras vacías,
  adjetivos) y, sobre los datos de silver, responde las preguntas del análisis
  (pendiente).

`make ingest` toma el zip del chat activo (o `ZIP=...`) y deja en `data/raw/<chat>/`
una copia (`whatsapp_chat.zip`), su contenido (`_chat.txt`) y un `FUENTE.txt`
con el origen de los datos: grupo, método de exportación, fecha de exportación, periodo
que cubren los mensajes, descripción del formato, enlace a la documentación de WhatsApp
y, por archivo, tamaño, fecha y sha256. Si `data/raw/<chat>/` ya tiene los archivos se respetan
(`on_exists: skip`); con `ON_EXISTS=overwrite` se reemplazan por una exportación nueva.

## Estructura

```
params.yml                 <- configuración local (ignorado por git; ver params-example.yml)
.env                       <- ANON_SALT, la sal secreta para anonimizar (ignorado por git)
data/
├── raw/<chat>/            <- zip exportado, _chat.txt y FUENTE.txt (bronze)
├── interim/<chat>/        <- bronze.parquet (con nombres, local), messages_anon.parquet y members.parquet
└── processed/<chat>/      <- conjuntos tidy (silver): messages, tokens y emojis
references/                <- diccionarios de datos, uno por conjunto (con índice en README.md)
notebooks/                 <- marimo (.py) y su exportación a .ipynb para GitHub
wasap_group_analyzer/
├── config.py              <- carga params.yml y .env, configura el logging
├── constants.py           <- rutas del proyecto
├── logging.py             <- decorador @log_execution (inicio/fin/error + tiempo)
├── parsing.py             <- _chat.txt -> una fila por mensaje (SQL de DuckDB, el mismo del EDA bronze)
├── anonymize.py           <- ids anónimos (blake2b con sal) y enmascarado del texto
├── aliases.py             <- alias de los miembros: animales de México
├── text.py                <- tipo de mensaje, contenido legible, emojis, palabras (spaCy) y stop words
├── provenance.py          <- sha256 y FUENTE.txt: origen, fechas y descripción del chat exportado
├── policies/              <- FilePolicy: skip/overwrite/error ante archivos existentes
└── jobs/
    ├── ingest_job.py      <- zip exportado -> data/raw/<chat>/ (zip, _chat.txt y FUENTE.txt)
    ├── anonymize_job.py   <- raw -> data/interim/<chat>/ (bronze, messages_anon y members)
    ├── process_job.py     <- interim -> data/processed/<chat>/ (messages, tokens y emojis)
    └── leak_check_job.py  <- busca nombres reales en lo que se puede publicar
tests/                     <- pruebas con datos sintéticos (nunca mensajes reales)
logs/                      <- logs de los jobs
```
