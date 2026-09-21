import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")

with app.setup:
    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl
    from spacy.lang.es.stop_words import STOP_WORDS

    from utils import (
        barh,
        boxplot,
        chat_dirs,
        columns,
        connect,
        heatmap,
        line,
        note,
        wordcloud,
    )
    from wasap_group_analyzer.config import load_params
    from wasap_group_analyzer.text import (
        CHAT_STOP_WORDS,
        clean_content,
        emoji_name,
        extract_emojis,
        is_edited,
        load_nlp,
        message_type,
        text_for_words,
        tokenize,
    )

    # Tamaño de la muestra de mensajes de texto para explorar con spaCy (la muestra es
    # reproducible: misma semilla, mismos mensajes).
    SAMPLE_SIZE = 20_000


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # EDA silver: de los mensajes anonimizados a datos tidy

    **Parte 1** decide, con datos, cómo convertir `data/interim/<chat>/messages_anon.parquet`
    (una fila por registro: `message_id`, `timestamp`, `sender_id`, `kind` y el `body`
    enmascarado) en los conjuntos tidy de silver (`data/processed/<chat>/`). Cada decisión
    ya está implementada en el paquete (`text.py`, `aliases.py`) y la usa el job de silver;
    aquí se aplica a los datos para justificarla. **Partes 2 y 3** responden preguntas con
    silver.

    **Privacidad.** Solo se lee la versión anonimizada, y nunca se muestra un mensaje
    completo: solo conteos, palabras sueltas y ejemplos inventados.
    """)
    return


@app.cell
def _():
    dirs = chat_dirs()
    con = connect()

    # Funciones del paquete disponibles en SQL.
    con.create_function(
        "message_type", message_type, ["VARCHAR", "VARCHAR"], "VARCHAR", null_handling="special"
    )
    con.create_function("is_edited", is_edited, ["VARCHAR"], "BOOLEAN", null_handling="special")
    con.create_function("emojis", extract_emojis, ["VARCHAR"], "VARCHAR[]", null_handling="special")
    con.create_function("emoji_name", emoji_name, ["VARCHAR"], "VARCHAR")

    # Alias de cada miembro: los asigna el job de anonimización (ver sección 2).
    member_aliases = con.sql("SELECT sender_id, alias FROM members").pl()
    alias_by_id = dict(zip(member_aliases["sender_id"], member_aliases["alias"]))
    con.create_function(
        "clean_content",
        lambda kind, body: clean_content(kind, body, alias_by_id),
        ["VARCHAR", "VARCHAR"],
        "VARCHAR",
        null_handling="special",
    )
    note(f"Chat activo: **{dirs['chat']}**")
    return alias_by_id, con, dirs


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 1. Tipos de mensaje

    `avisos_del_grupo` son los mensajes que WhatsApp firma con el nombre del grupo y no
    con una persona (el aviso de cifrado, la llegada de Meta AI): su `sender_id` queda
    vacío y no reciben alias. `con_cuerpo` son los registros que conservan texto (`text`,
    `attachment` y `poll`).
    """)
    return


@app.cell
def _(con, messages_anon):
    overview = mo.sql(
        f"""
        SELECT
            count(*) AS registros,
            count(DISTINCT sender_id) AS personas,
            count(*) FILTER (sender_id IS NULL) AS avisos_del_grupo,
            count(*) FILTER (body IS NOT NULL) AS con_cuerpo,
            min(timestamp) AS desde,
            max(timestamp) AS hasta
        FROM messages_anon
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `kind` junta todos los adjuntos en `attachment`; para responder "¿quién manda más
    stickers?" hay que separarlos. El marcador que deja WhatsApp (`sticker omitted`,
    `image omitted`...) da el tipo: `text.message_type()` lo convierte en `message_type`,
    igual a `kind` salvo en los adjuntos.
    """)
    return


@app.cell
def _(con, messages_anon):
    types = mo.sql(
        f"""
        SELECT
            message_type(kind, body) AS message_type,
            count(*) AS mensajes,
            round(100 * count(*) / sum(count(*)) OVER (), 2) AS pct,
            count(*) FILTER (kind = 'attachment' AND clean_content(kind, body) IS NOT NULL)
                AS con_pie_de_foto
        FROM messages_anon
        GROUP BY ALL
        ORDER BY mensajes DESC
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Los tipos se quedan así. Los *mensajes de texto* (para palabras por mensaje) son solo
    `text`; los pies de foto y las encuestas también los escribe alguien, así que sus
    palabras cuentan para "las palabras más usadas", pero no como mensajes de texto.

    ## 2. Alias de los miembros

    Cada `sender_id` recibe el nombre de un animal de México (Ajolote, Jaguar, Quetzal,
    Tlacuache...) en el orden en que escribió por primera vez. Los asigna el job de
    anonimización (`interim/<chat>/members.parquet`), el único que conoce los nombres
    reales: salta cualquier animal que comparta una palabra con el nombre de un miembro,
    para que el alias no dé pistas. El orden no depende del hash, y una exportación más
    nueva solo agrega animales al final.

    ## 3. Contenido legible

    El `body` de interim todavía trae ruido: marcas invisibles, el sufijo
    `<This message was edited>`, el marcador del adjunto y los ids de las marcas de
    anonimización. `text.clean_content()` deja el texto que escribió el usuario, con los
    miembros como `@[Alias]` (mención) o `[Alias]` (nombre en el texto); los corchetes
    distinguen a un miembro de, por ejemplo, alguien hablando de Juárez. Para contar
    palabras, `text.text_for_words()` quita además las marcas entre corchetes y las
    etiquetas de las encuestas.

    Con mensajes inventados:
    """)
    return


@app.cell
def _(alias_by_id):
    _lrm = chr(0x200E)
    _someone = next(iter(alias_by_id))
    _examples = [
        ("text", f"nos vemos mañana @[{_someone}] 😂 {_lrm}<This message was edited>"),
        ("attachment", f"mira esto [{_someone}] {_lrm}image omitted"),
        ("attachment", f"{_lrm}sticker omitted"),
        ("text", "checa [url:youtube.com] y me dices, [nombre] ya lo vio"),
        ("poll", "POLL:\n¿Dónde comemos?\nOPTION: Tacos (3 votes)\nOPTION: Pizza (1 vote)"),
    ]
    _rows = []
    for _kind, _body in _examples:
        _content = clean_content(_kind, _body, alias_by_id)
        _rows.append(
            {
                "kind": _kind,
                "body en interim": _body.replace(_lrm, "‹U+200E›"),
                "is_edited": is_edited(_body),
                "content": _content,
                "texto para palabras": " ".join(text_for_words(_content).split()),
            }
        )
    pl.DataFrame(_rows)
    return


@app.cell
def _(con, messages_anon):
    content_marks = mo.sql(
        f"""
        WITH c AS (
            SELECT kind, body, clean_content(kind, body) AS content
            FROM messages_anon
            WHERE body IS NOT NULL
        )
        SELECT
            count(*) FILTER (content IS NOT NULL) AS con_contenido,
            count(*) FILTER (is_edited(body)) AS editados,
            count(*) FILTER (contains(content, '@[')) AS con_mencion,
            count(*) FILTER (
                len(list_filter(
                    regexp_extract_all(content, '(^|[^@])[[]([^]]+)[]]', 2),
                    x -> x NOT IN ('nombre', 'numero', 'correo') AND NOT starts_with(x, 'url:')
                )) > 0
            ) AS con_nombre_de_miembro,
            count(*) FILTER (contains(content, '[nombre]')) AS con_nombre_ambiguo_o_apodo,
            count(*) FILTER (contains(content, '[url:')) AS con_url,
            count(*) FILTER (contains(content, '[numero]')) AS con_numero,
            count(*) FILTER (contains(content, '[correo]')) AS con_correo
        FROM c
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 4. Emojis

    `text.extract_emojis()` usa la librería `emoji`, que reconoce secuencias completas: un
    emoji con tono de piel (👍🏽) o una familia unida con ZWJ cuenta como uno solo. Los
    emoticonos de texto como `:(` o `xD` no son emojis. Cada emoji será una fila de la
    tabla `emojis` de silver, con su nombre en español.
    """)
    return


@app.cell
def _(con, messages_anon):
    emoji_summary = mo.sql(
        f"""
        WITH e AS (
            SELECT message_id, unnest(emojis(clean_content(kind, body))) AS emoji
            FROM messages_anon
            WHERE body IS NOT NULL
        )
        SELECT
            count(DISTINCT message_id) AS mensajes_con_emoji,
            count(*) AS emojis,
            count(DISTINCT emoji) AS emojis_distintos,
            count(*) FILTER (contains(emoji, chr(8205))) AS secuencias_zwj,
            count(*) FILTER (
                regexp_matches(emoji, '[' || chr(127995) || '-' || chr(127999) || ']')
            ) AS con_tono_de_piel
        FROM e
        """,
        engine=con
    )
    return


@app.cell
def _(con, messages_anon):
    top_emojis = mo.sql(
        f"""
        SELECT emoji, emoji_name(emoji) AS nombre, count(*) AS veces
        FROM (
            SELECT unnest(emojis(clean_content(kind, body))) AS emoji
            FROM messages_anon
            WHERE body IS NOT NULL
        )
        GROUP BY emoji
        ORDER BY veces DESC
        LIMIT 10
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 5. Qué cuenta como palabra

    Para palabras, adjetivos y stop words se usa spaCy (`es_core_news_sm`), que separa
    tokens, etiqueta su categoría gramatical (POS) y da su lema. Para explorar basta una
    muestra reproducible de mensajes de texto; el job de silver procesa todos.
    """)
    return


@app.cell
def _(con):
    sample = con.sql(
        f"""
        SELECT message_id, clean_content(kind, body) AS content
        FROM (SELECT * FROM messages_anon WHERE kind = 'text')
        USING SAMPLE reservoir({SAMPLE_SIZE} ROWS) REPEATABLE (42)
        """
    ).pl()
    _words_text = [text_for_words(content) for content in sample["content"]]
    sample = sample.with_columns(
        pl.Series("split_by_spaces", [len(text.split()) for text in _words_text])
    )
    nlp = load_nlp(load_params()["nlp"]["model"])
    _rows = []
    for _message_id, _tokens in zip(sample["message_id"], tokenize(nlp, _words_text)):
        _rows += [{"message_id": _message_id, **_token} for _token in _tokens]
    sample_tokens = pl.DataFrame(_rows).with_columns(
        pl.col("token").is_in(list(STOP_WORDS)).alias("is_spacy_stop")
    )
    con.register("sample", sample)
    con.register("sample_tokens", sample_tokens)
    note(f"Muestra: **{len(sample):,}** mensajes de texto, **{len(sample_tokens):,}** tokens.")
    return nlp, sample, sample_tokens


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Un mensaje inventado, token por token. Una **palabra** es un token alfabético
    (`is_alpha`: solo letras, con o sin acento); números, signos, emojis y emoticonos son
    tokens pero no palabras:
    """)
    return


@app.cell
def _(nlp):
    _example = "jajaja no manches 😂 mañana a las 5pm vamos al cine, está buenísima la peli xD"
    pl.DataFrame(next(tokenize(nlp, [_example]))).drop("token_idx")
    return


@app.cell
def _(con, sample, sample_tokens):
    definitions = mo.sql(
        f"""
        WITH per_message AS (
            SELECT
                s.message_id,
                s.split_by_spaces AS por_espacios,
                count(t.token) FILTER (t.is_alpha) AS palabras
            FROM sample AS s
            LEFT JOIN sample_tokens AS t USING (message_id)
            GROUP BY ALL
        )
        SELECT
            round(avg(por_espacios), 2) AS promedio_separando_por_espacios,
            round(avg(palabras), 2) AS promedio_palabras_spacy,
            median(palabras) AS mediana_palabras_spacy,
            count(*) FILTER (palabras = 0) AS mensajes_sin_palabras
        FROM per_message
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Separar por espacios cuenta de más ("5pm", "😂" y "xD" no son palabras). Los mensajes
    sin palabras son solo emojis, números o signos.

    ## 6. Risas y palabras vacías

    Las risas son las "palabras" más escritas después de las vacías, con muchas variantes.
    `text.LAUGH` reconoce al menos dos sílabas iguales (`jaja`, `jejeje`, `haha`),
    variantes con s (`jsjsjs`), `xd` y `lol`, sin atrapar palabras reales como "he", "ha". Cada token lleva `is_laugh` en silver y cuenta como palabra vacía.
    """)
    return


@app.cell
def _(con, sample_tokens):
    laughs = mo.sql(
        f"""
        SELECT token AS risa, count(*) AS veces
        FROM sample_tokens
        WHERE is_laugh
        GROUP BY token
        ORDER BY veces DESC
        LIMIT 10
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Con solo la lista de spaCy (`STOP_WORDS`, ~500 palabras del español escrito), las
    palabras "con contenido" más frecuentes son en realidad muletillas y abreviaturas del
    chat:
    """)
    return


@app.cell
def _(con, sample_tokens):
    spacy_only = mo.sql(
        f"""
        SELECT token AS palabra, count(*) AS veces
        FROM sample_tokens
        WHERE is_alpha AND NOT is_spacy_stop
        GROUP BY token
        ORDER BY veces DESC
        LIMIT 20
        """,
        engine=con
    )
    return


@app.cell
def _():
    note(
        "Por eso `text.CHAT_STOP_WORDS` agrega abreviaturas de palabras vacías, muletillas "
        "y vocativos del chat, y `text.is_stop_word()` considera vacía también cualquier "
        "palabra de una sola letra y cualquier risa. La jerga con significado (*neta*, "
        "*chamba*, *pedo*) sigue siendo contenido. La lista:\n\n"
        + ", ".join(f"`{word}`" for word in sorted(CHAT_STOP_WORDS))
    )
    return


@app.cell
def _(con, sample_tokens):
    content_words = mo.sql(
        f"""
        SELECT token AS palabra, count(*) AS veces
        FROM sample_tokens
        WHERE is_alpha AND NOT is_stop
        GROUP BY token
        ORDER BY veces DESC
        LIMIT 20
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 7. Adjetivos

    spaCy etiqueta los adjetivos como `ADJ`. Se cuentan por lema, para que *buenas* y
    *bueno* sean el mismo adjetivo. Aquí **no** se filtran las palabras vacías: la lista
    de spaCy incluye justo los adjetivos más comunes (*bueno*, *mejor*, *nuevo*,
    *grande*), y quitarlos dejaría fuera la respuesta. Solo se excluyen las risas y las
    letras sueltas.
    """)
    return


@app.cell
def _(con, sample_tokens):
    adjectives = mo.sql(
        f"""
        SELECT lemma AS adjetivo, count(*) AS veces
        FROM sample_tokens
        WHERE pos = 'ADJ' AND is_alpha AND NOT is_laugh AND length(token) > 1
        GROUP BY lemma
        ORDER BY veces DESC
        LIMIT 20
        """,
        engine=con
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    La mayoría son adjetivos reales, pero el modelo pequeño de spaCy se entrenó con
    noticias, no con chats: con la jerga y los mensajes sin puntuación toma algún
    sustantivo (*amigo*), verbo (*anda*) o abreviatura por adjetivo, y a veces no lematiza
    el femenino. Se acepta esa limitación y se comenta al responder la pregunta, en lugar
    de corregir la lista a mano.

    ## 8. Especificación de silver

    El job de silver (`make process`) escribe tres conjuntos tidy en
    `data/processed/<chat>/`, cada uno con su diccionario de datos en `references/`
    (`make dictionary` junta las descripciones con el perfil que calcula DuckDB).

    **`messages.parquet`**: una fila por mensaje.

    | Columna | Qué es |
    |---|---|
    | `message_id` | orden del registro en el archivo exportado |
    | `timestamp` | fecha y hora local, sin zona |
    | `sender` | alias del remitente (un animal); vacío en avisos del grupo |
    | `message_type` | tipo de mensaje (sección 1) |
    | `content` | texto legible (sección 3); vacío si no hay texto |
    | `is_edited` | si el mensaje fue editado |
    | `n_words` | palabras (tokens alfabéticos) del contenido |
    | `n_emojis` | emojis del contenido |
    | `n_mentions` | menciones a miembros |
    | `has_url` | si trae un enlace |

    **`tokens.parquet`**: una fila por token del contenido (texto, pies de foto y
    encuestas): `message_id`, `token_idx`, `token`, `lemma`, `pos`, `is_alpha`,
    `is_stop`, `is_laugh`.

    **`emojis.parquet`**: una fila por emoji: `message_id`, `emoji_idx`, `emoji`,
    `emoji_name`.

    El remitente, la fecha y el tipo de un token o de un emoji se obtienen uniendo con
    `messages` por `message_id`: cada dato vive en una sola tabla.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---

    # Parte 2: las preguntas

    Todo lo que sigue sale de los tres conjuntos de silver (`make process`), con SQL sobre
    `messages`, `tokens` y `emojis`. "Usuario" es el alias de cada miembro.
    """)
    return


@app.cell
def _(dirs):
    mo.stop(
        not (dirs["processed"] / "messages.parquet").exists(),
        note("Faltan los datos de silver: corre `make process` y vuelve a ejecutar."),
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 9. ¿Quién manda más mensajes?
    """)
    return


@app.cell
def _(con, messages):
    by_sender = mo.sql(
        f"""
        SELECT
            sender AS usuario,
            count(*) AS mensajes,
            round(100 * count(*) / sum(count(*)) OVER (), 1) AS pct
        FROM messages
        WHERE sender IS NOT NULL
        GROUP BY sender
        ORDER BY mensajes DESC
        """,
        engine=con,
        output=False,
    )
    barh(
        by_sender["usuario"][:15],
        by_sender["mensajes"][:15],
        "Mensajes enviados (15 primeros de 42)",
        "mensajes",
    )
    return (by_sender,)


@app.cell
def _(by_sender):
    _top = by_sender.row(0, named=True)
    _half = (by_sender["mensajes"].cum_sum() / by_sender["mensajes"].sum() <= 0.5).sum() + 1
    note(
        f"**{_top['usuario']}** manda más mensajes que nadie: **{_top['mensajes']:,}** "
        f"({_top['pct']}% de todos los mensajes del grupo), seguido de "
        f"{by_sender['usuario'][1]} con {by_sender['mensajes'][1]:,}. La conversación está "
        f"concentrada: entre **{_half}** de las {len(by_sender)} personas escriben la mitad "
        f"de los mensajes."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 10. ¿Cuántas palabras por mensaje de texto escribe cada quien?

    Solo mensajes de texto (`message_type = 'text'`), porque un sticker o una foto sin pie
    no tienen palabras y bajarían el promedio de quien manda muchos.
    """)
    return


@app.cell
def _(con, messages):
    words_per_sender = mo.sql(
        f"""
        SELECT
            sender AS usuario,
            count(*) AS mensajes_de_texto,
            round(avg(n_words), 2) AS palabras_por_mensaje,
            median(n_words) AS mediana,
            max(n_words) AS mensaje_mas_largo
        FROM messages
        WHERE sender IS NOT NULL AND message_type = 'text'
        GROUP BY sender
        HAVING count(*) >= 100
        ORDER BY palabras_por_mensaje DESC
        """,
        engine=con
    )
    return (words_per_sender,)


@app.cell
def _(con, messages, words_per_sender):
    _top = words_per_sender.sort("mensajes_de_texto", descending=True).head(6)["usuario"]
    top_words_per_message = mo.sql(
        f"""
        SELECT sender AS usuario, n_words AS palabras
        FROM messages
        WHERE message_type = 'text' AND sender IN (
            SELECT sender
            FROM messages
            WHERE sender IS NOT NULL AND message_type = 'text'
            GROUP BY sender
            ORDER BY count(*) DESC
            LIMIT 6
        )
        """,
        engine=con,
        output=False,
    )
    boxplot(
        {
            user: top_words_per_message.filter(pl.col("usuario") == user)["palabras"]
            for user in _top
        },
        "Palabras por mensaje de texto (6 con más mensajes)",
        "palabras",
    )
    return


@app.cell
def _(words_per_sender):
    _most = words_per_sender.row(0, named=True)
    _second = words_per_sender.row(1, named=True)
    _least = words_per_sender.row(-1, named=True)
    _skewed = (words_per_sender["mediana"] < words_per_sender["palabras_por_mensaje"]).sum()
    note(
        "La gráfica compara a las seis personas que más mensajes de texto mandan: la caja "
        "cubre la mitad central de sus mensajes, la línea es la mediana y el rombo el "
        "promedio; los mensajes atípicos, muy largos, no se dibujan.\n\n"
        f"En la tabla, el promedio va de **{_most['palabras_por_mensaje']}** palabras por mensaje "
        f"({_most['usuario']}) a **{_least['palabras_por_mensaje']}** ({_least['usuario']}), "
        f"una diferencia de {_most['palabras_por_mensaje'] / _least['palabras_por_mensaje']:.0f} "
        f"veces. {_most['usuario']} es un caso aparte: le sigue {_second['usuario']} con "
        f"{_second['palabras_por_mensaje']}, así que el resto del grupo se mueve en un rango "
        "estrecho de mensajes cortos.\n\n"
        f"En **{_skewed} de {len(words_per_sender)}** usuarios la mediana es menor que el "
        "promedio: casi todos escriben mensajes de unas pocas palabras y, de vez en cuando, "
        "uno largo que jala el promedio hacia arriba. Se excluye a quienes escribieron "
        "menos de 100 mensajes de texto, donde el promedio es puro ruido."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 11. ¿Quién manda más palabras, más emojis y más stickers?
    """)
    return


@app.cell
def _(con, messages):
    totals = mo.sql(
        f"""
        SELECT
            sender AS usuario,
            sum(n_words) AS palabras,
            sum(n_emojis) AS emojis,
            count(*) FILTER (message_type = 'sticker') AS stickers,
            count(*) AS mensajes
        FROM messages
        WHERE sender IS NOT NULL
        GROUP BY sender
        ORDER BY palabras DESC
        LIMIT 10
        """,
        engine=con
    )
    return (totals,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Las mismas diez personas, en el mismo orden (por palabras), en cada medida:
    """)
    return


@app.cell
def _(totals):
    _fig, _axes = plt.subplots(2, 2, figsize=(11, 7.5))
    for _ax, (_column, _title) in zip(
        _axes.flat,
        [
            ("mensajes", "Mensajes"),
            ("palabras", "Palabras"),
            ("emojis", "Emojis"),
            ("stickers", "Stickers"),
        ],
    ):
        barh(totals["usuario"], totals[_column], _title, ax=_ax)
    _fig
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 12. ¿Cuándo se escribe? Día de la semana y hora
    """)
    return


@app.cell
def _(con, messages):
    by_weekday = mo.sql(
        f"""
        SELECT
            ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'][isodow(timestamp)] AS dia,
            isodow(timestamp) AS orden,
            count(*) AS mensajes,
            round(count(*) / count(DISTINCT timestamp::DATE), 0) AS por_dia
        FROM messages
        GROUP BY ALL
        ORDER BY orden
        """,
        engine=con,
        output=False,
    )
    columns(by_weekday["dia"], by_weekday["mensajes"], "Mensajes por día de la semana", "mensajes")
    return (by_weekday,)


@app.cell
def _(con, messages):
    by_hour = mo.sql(
        f"""
        SELECT hour(timestamp) AS hora, count(*) AS mensajes
        FROM messages
        GROUP BY hora
        ORDER BY hora
        """,
        engine=con,
        output=False,
    )
    columns(
        [f"{hour:02d}" for hour in by_hour["hora"]],
        by_hour["mensajes"],
        "Mensajes por hora del día (hora local)",
        "mensajes",
    )
    return (by_hour,)


@app.cell
def _(con, messages):
    weekday_hour = mo.sql(
        f"""
        SELECT isodow(timestamp) AS dia, hour(timestamp) AS hora, count(*) AS mensajes
        FROM messages
        GROUP BY ALL
        ORDER BY dia, hora
        """,
        engine=con,
        output=False,
    )
    _counts = {(row["dia"], row["hora"]): row["mensajes"] for row in weekday_hour.iter_rows(named=True)}
    _days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    heatmap(
        [[_counts.get((day, hour), 0) for hour in range(24)] for day in range(1, 8)],
        _days,
        [f"{hour:02d}" for hour in range(24)],
        "Mensajes por día y hora",
        "mensajes",
    )
    return


@app.cell
def _(by_hour, by_weekday):
    _busiest = by_weekday.sort("mensajes", descending=True).row(0, named=True)
    _quietest = by_weekday.sort("mensajes").row(0, named=True)
    _peak = by_hour.sort("mensajes", descending=True).row(0, named=True)
    _night = by_hour.filter(by_hour["hora"].is_between(4, 7))["mensajes"].sum()
    note(
        f"El día más activo es el **{_busiest['dia']}** "
        f"({_busiest['mensajes']:,} mensajes) y el más callado el **{_quietest['dia']}** "
        f"({_quietest['mensajes']:,}), "
        f"{_busiest['mensajes'] / _quietest['mensajes']:.1f} veces menos. Los cinco días "
        "entre semana se parecen entre sí y el fin de semana cae"
        "o se desconecta.\n\n"
        f"El pico es a las **{_peak['hora']}:00** "
        f"({_peak['mensajes']:,} mensajes), dentro del bloque de media mañana y mediodía, y "
        f"de las 4 a las 7 de la mañana el grupo casi duerme ({_night:,} mensajes en total "
        "entre las cuatro horas). El mapa de calor muestra que ese ritmo diario se repite "
        "igual de lunes a viernes, y que las madrugadas con actividad caen sobre todo en "
        "fin de semana."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 13. ¿Qué palabras se usan más?

    Primero todas las palabras, incluidas las vacías, para ver por qué hay que filtrarlas;
    después solo las que tienen contenido: las 20 más usadas y, para ver más allá, una nube
    con las 80 más usadas.
    """)
    return


@app.cell
def _(con, tokens):
    all_words = mo.sql(
        f"""
        SELECT token AS palabra, count(*) AS veces
        FROM tokens
        WHERE is_alpha
        GROUP BY token
        ORDER BY veces DESC
        LIMIT 10
        """,
        engine=con
    )
    return (all_words,)


@app.cell
def _(all_words):
    barh(all_words["palabra"], all_words["veces"], "Palabras más usadas, con las vacías", "veces")
    return


@app.cell
def _(con, tokens):
    top_content_words = mo.sql(
        f"""
        SELECT token AS palabra, count(*) AS veces
        FROM tokens
        WHERE is_alpha AND NOT is_stop
        GROUP BY token
        ORDER BY veces DESC
        LIMIT 20
        """,
        engine=con,
        output=False,
    )
    barh(
        top_content_words["palabra"],
        top_content_words["veces"],
        "Palabras más usadas en el grupo (sin palabras vacías)",
        "veces",
    )
    return (top_content_words,)


@app.cell
def _(con, tokens):
    cloud_words = mo.sql(
        f"""
        SELECT token AS palabra, count(*) AS veces
        FROM tokens
        WHERE is_alpha AND NOT is_stop
        GROUP BY token
        ORDER BY veces DESC
        LIMIT 80
        """,
        engine=con,
        output=False,
    )
    wordcloud(
        cloud_words["palabra"], cloud_words["veces"], "Las 80 palabras con contenido más usadas"
    )
    return


@app.cell
def _(con, messages, tokens):
    words_by_sender = mo.sql(
        f"""
        WITH por_usuario AS (
            SELECT m.sender, t.token, count(*) AS veces
            FROM tokens AS t
            JOIN messages AS m USING (message_id)
            WHERE t.is_alpha AND NOT t.is_stop AND m.sender IS NOT NULL
            GROUP BY ALL
        ),
        ordenadas AS (
            SELECT *, row_number() OVER (PARTITION BY sender ORDER BY veces DESC, token) AS lugar
            FROM por_usuario
        )
        SELECT
            sender AS usuario,
            string_agg(token || ' (' || veces || ')', ', ' ORDER BY lugar) AS palabras_mas_usadas
        FROM ordenadas
        WHERE lugar <= 5
        GROUP BY sender
        ORDER BY usuario
        """,
        engine=con
    )
    return


@app.cell
def _(con, messages, tokens):
    word_rates = mo.sql(
        f"""
        WITH content AS (
            SELECT m.sender, t.token
            FROM tokens AS t
            JOIN messages AS m USING (message_id)
            WHERE t.is_alpha AND NOT t.is_stop AND m.sender IS NOT NULL
        ),
        top_words AS (
            SELECT token, row_number() OVER (ORDER BY veces DESC, token) AS lugar
            FROM (SELECT token, count(*) AS veces FROM content GROUP BY token)
            QUALIFY lugar <= 12
        ),
        top_users AS (
            SELECT sender, count(*) AS total
            FROM content
            GROUP BY sender
            ORDER BY total DESC
            LIMIT 15
        )
        SELECT
            u.sender AS usuario,
            w.token AS palabra,
            round(1000 * count(*) / u.total, 1) AS por_mil,
            u.total,
            w.lugar
        FROM content AS c
        JOIN top_users AS u USING (sender)
        JOIN top_words AS w USING (token)
        GROUP BY u.sender, w.token, u.total, w.lugar
        """,
        engine=con,
        output=False,
    )
    _users = word_rates.unique("usuario").sort("total", descending=True)["usuario"]
    _words = word_rates.unique("palabra").sort("lugar")["palabra"]
    _rates = {(row["usuario"], row["palabra"]): row["por_mil"] for row in word_rates.iter_rows(named=True)}
    heatmap(
        [[_rates.get((user, word), 0) for word in _words] for user in _users],
        _users,
        _words,
        "Cada palabra en el habla de cada usuario (15 con más palabras)",
        "veces por cada 1,000 palabras con contenido",
    )
    return


@app.cell
def _(top_content_words):
    note(
        "Sin filtrar, las diez palabras más usadas son todas vacías (*de*, *que*, *el*, "
        "*no*...): son las que sostienen cualquier texto en español y no dicen nada del "
        "grupo. Filtrando las vacías (las de spaCy más las muletillas del chat, sección 6) "
        "aparece de qué se habla: las cinco primeras son "
        + ", ".join(
            f"**{row['palabra']}** ({row['veces']:,})"
            for row in top_content_words.head(5).iter_rows(named=True)
        )
        + ". Son sobre todo groserías que en el habla del norte de México funcionan como "
        "muletilla, y palabras de quedar de verse (*casa*, *mañana*, *alguien*): el grupo "
        "se usa para organizar planes más que para conversar de un tema.\n\n"
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 14. ¿Cuáles son los adjetivos más usados?

    Por lema, para juntar *buena*, *buenas* y *bueno*. Aquí no se filtran las palabras
    vacías: la lista de spaCy incluye justo los adjetivos más comunes (sección 7).
    """)
    return


@app.cell
def _(con, tokens):
    top_adjectives = mo.sql(
        f"""
        SELECT lemma AS adjetivo, count(*) AS veces
        FROM tokens
        WHERE pos = 'ADJ' AND is_alpha AND NOT is_laugh AND length(token) > 1
        GROUP BY lemma
        ORDER BY veces DESC
        LIMIT 20
        """,
        engine=con,
        output=False,
    )
    barh(top_adjectives["adjetivo"], top_adjectives["veces"], "Adjetivos más usados (por lema)", "veces")
    return (top_adjectives,)


@app.cell
def _(top_adjectives):
    note(
        f"El adjetivo más usado es **{top_adjectives['adjetivo'][0]}** "
        "Bueno viene del lema de spaCy, que incluye buenos dias, tardes, noches. Los demás vienen tambien de frases memeables como 'que duro', 'mejor nadota', 'solo reales'."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ---

    # Parte 3: el tiempo, las conversaciones y las palabras propias

    Más preguntas sobre los mismos tres conjuntos de silver: cómo cambia el grupo mes a
    mes, cómo se arman las conversaciones y qué palabras distinguen a cada quien.

    ## 15. ¿Cómo ha evolucionado el grupo?

    Mensajes por mes. Los meses a medias (el de la primera y el de la última fecha de la
    exportación) van con el punto vacío: no son comparables con los completos.
    """)
    return


@app.cell
def _(con, messages):
    by_month = mo.sql(
        f"""
        SELECT
            strftime(date_trunc('month', timestamp), '%Y-%m') AS mes,
            count(*) AS mensajes,
            count(DISTINCT sender) AS personas,
            count(DISTINCT timestamp::DATE) AS dias_con_mensajes,
            count(DISTINCT timestamp::DATE) < day(last_day(min(timestamp)::DATE)) AS incompleto
        FROM messages
        GROUP BY mes
        ORDER BY mes
        """,
        engine=con,
        output=False,
    )
    line(
        by_month["mes"],
        by_month["mensajes"],
        "Mensajes por mes",
        "mensajes",
        every=3,
        hollow=[i for i, partial in enumerate(by_month["incompleto"]) if partial],
        label_peak=True,
    )
    return (by_month,)


@app.cell
def _():
    return


@app.cell
def _(by_month):
    _full = by_month.filter(~by_month["incompleto"])
    _peak = _full.sort("mensajes", descending=True).row(0, named=True)
    _low = _full.sort("mensajes").row(0, named=True)
    _first, _last = _full.row(0, named=True), _full.row(-1, named=True)
    note(
        f"La cantidad de mensajes se mantiene relativamente estable. Entre los {len(_full)} meses completos, el más activo es **{_peak['mes']}** "
        f"({_peak['mensajes']:,} mensajes) y el más callado **{_low['mes']}** "
        f"({_low['mensajes']:,}): {_peak['mensajes'] / _low['mensajes']:.1f} veces de "
        f"diferencia."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 16. ¿Quién inicia y quién cierra las conversaciones?

    Una **sesión** es una racha de mensajes sin pausas de más de 30 minutos: cada pausa
    más larga abre una sesión nueva. Se cuentan todos los mensajes de personas (también
    stickers y fotos), en orden de fecha. Quien **inicia** es quien manda el primer
    mensaje de la sesión y quien **cierra**, el último. Para esto solo cuentan las
    sesiones de al menos 2 mensajes: un mensaje que nadie contestó en media hora no es una
    conversación (se reportan aparte).
    """)
    return


@app.cell
def _(con):
    sessions = con.sql(
        """
        WITH ordered AS (
            SELECT
                message_id, timestamp, sender,
                coalesce(timestamp - lag(timestamp) OVER w > INTERVAL 30 MINUTE, true) AS nueva
            FROM messages
            WHERE sender IS NOT NULL
            WINDOW w AS (ORDER BY timestamp, message_id)
        ),
        marked AS (
            SELECT *, sum(nueva::INT) OVER (ORDER BY timestamp, message_id) AS sesion FROM ordered
        )
        SELECT
            sesion,
            min(timestamp) AS desde,
            count(*) AS mensajes,
            count(DISTINCT sender) AS personas,
            arg_min(sender, (timestamp, message_id)) AS inicia,
            arg_max(sender, (timestamp, message_id)) AS cierra,
            date_diff('minute', min(timestamp), max(timestamp)) AS minutos
        FROM marked
        GROUP BY sesion
        """
    ).pl()
    con.register("sessions", sessions)
    note(f"Sesiones: **{len(sessions):,}**")
    return (sessions,)


@app.cell
def _(con, sessions):
    session_summary = mo.sql(
        f"""
        SELECT
            count(*) AS sesiones,
            count(*) FILTER (mensajes = 1) AS de_un_mensaje,
            count(*) FILTER (mensajes >= 2) AS conversaciones,
            median(mensajes) FILTER (mensajes >= 2) AS mediana_mensajes,
            median(minutos) FILTER (mensajes >= 2) AS mediana_minutos,
            max(mensajes) AS la_mas_larga_mensajes,
            max(minutos) AS la_mas_larga_minutos
        FROM sessions
        """,
        engine=con
    )
    return (session_summary,)


@app.cell
def _(con, messages, sessions):
    openers = mo.sql(
        f"""
        WITH abre AS (
            SELECT inicia AS usuario, count(*) AS n FROM sessions WHERE mensajes >= 2 GROUP BY 1
        ),
        cierra AS (
            SELECT cierra AS usuario, count(*) AS n FROM sessions WHERE mensajes >= 2 GROUP BY 1
        ),
        enviados AS (
            SELECT sender AS usuario, count(*) AS n FROM messages WHERE sender IS NOT NULL GROUP BY 1
        )
        SELECT
            e.usuario,
            coalesce(a.n, 0) AS abre,
            coalesce(c.n, 0) AS cierra,
            e.n AS mensajes,
            round(1000.0 * coalesce(a.n, 0) / e.n, 1) AS abre_por_mil_mensajes
        FROM enviados AS e
        LEFT JOIN abre AS a USING (usuario)
        LEFT JOIN cierra AS c USING (usuario)
        ORDER BY abre DESC
        """,
        engine=con
    )
    return (openers,)


@app.cell
def _(openers):
    _top = openers.head(15)
    _fig, _axes = plt.subplots(1, 2, figsize=(11, 5))
    barh(_top["usuario"], _top["abre"], "Conversaciones que inicia", "sesiones", ax=_axes[0])
    barh(_top["usuario"], _top["cierra"], "Conversaciones que cierra", "sesiones", ax=_axes[1])
    _fig
    return


@app.cell
def _(con, sessions):
    session_sizes = mo.sql(
        f"""
        SELECT
            CASE
                WHEN mensajes = 1 THEN '1'
                WHEN mensajes = 2 THEN '2'
                WHEN mensajes <= 5 THEN '3-5'
                WHEN mensajes <= 10 THEN '6-10'
                WHEN mensajes <= 20 THEN '11-20'
                WHEN mensajes <= 50 THEN '21-50'
                WHEN mensajes <= 100 THEN '51-100'
                ELSE '100+'
            END AS mensajes_por_sesion,
            min(mensajes) AS orden,
            count(*) AS sesiones
        FROM sessions
        GROUP BY 1
        ORDER BY orden
        """,
        output=False,
        engine=con
    )
    return (session_sizes,)


@app.cell
def _(con, sessions):
    session_lengths = mo.sql(
        f"""
        SELECT
            CASE
                WHEN minutos < 5 THEN '<5 min'
                WHEN minutos < 15 THEN '5-15 min'
                WHEN minutos < 30 THEN '15-30 min'
                WHEN minutos < 60 THEN '30-60 min'
                WHEN minutos < 120 THEN '1-2 h'
                WHEN minutos < 240 THEN '2-4 h'
                WHEN minutos < 480 THEN '4-8 h'
                ELSE '8 h+'
            END AS duracion,
            min(minutos) AS orden,
            count(*) AS sesiones
        FROM sessions
        WHERE mensajes >= 2
        GROUP BY 1
        ORDER BY orden
        """,
        output=False,
        engine=con
    )
    return (session_lengths,)


@app.cell
def _(session_lengths, session_sizes):
    _fig, _axes = plt.subplots(1, 2, figsize=(11, 3.4))
    columns(
        session_sizes["mensajes_por_sesion"],
        session_sizes["sesiones"],
        "Mensajes por sesión",
        "sesiones",
        ax=_axes[0],
    )
    columns(
        session_lengths["duracion"],
        session_lengths["sesiones"],
        "Duración de las sesiones de 2 o más mensajes",
        "sesiones",
        rotate=30,
        ax=_axes[1],
    )
    _fig
    return


@app.cell
def _(openers, session_summary):
    _s = session_summary.row(0, named=True)
    _opens = openers.sort("abre", descending=True)
    _closes = openers.sort("cierra", descending=True)
    _rate = openers.filter(openers["mensajes"] >= 1000).sort(
        "abre_por_mil_mensajes", descending=True
    )
    note(
        f"Con pausas de 30 minutos, el grupo se reparte en **{_s['sesiones']:,} sesiones**: "
        f"{_s['de_un_mensaje']:,} son de un solo mensaje que nadie contestó en media hora, y "
        f"las otras {_s['conversaciones']:,} son "
        f"conversaciones de {_s['mediana_mensajes']:.0f} mensajes y {_s['mediana_minutos']:.0f} "
        f"minutos en la mediana (la más larga tiene {_s['la_mas_larga_mensajes']:,} mensajes "
        f"a lo largo de {_s['la_mas_larga_minutos'] / 60:.0f} horas). Los rangos de las "
        "gráficas de arriba no tienen el mismo ancho: cada barra cuenta cuántas sesiones "
        "caen en su rango, no es una densidad."
        f"\n\n**{_opens['usuario'][0]}** inicia más conversaciones ({_opens['abre'][0]:,}), "
        f"seguido de {_opens['usuario'][1]} ({_opens['abre'][1]:,}); **{_closes['usuario'][0]}** "
        f"las cierra más ({_closes['cierra'][0]:,}), seguido de {_closes['usuario'][1]} "
        f"({_closes['cierra'][1]:,}). Como quien más escribe tiene más oportunidades de "
        f"abrir y de cerrar, la última columna de la tabla normaliza: por cada mil mensajes "
        f"que manda, quien más inicia (entre quienes mandan al menos mil) es "
        f"**{_rate['usuario'][0]}**, con {_rate['abre_por_mil_mensajes'][0]} sesiones."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 17. ¿Qué palabras distinguen a cada persona?

    Las palabras más usadas de cada quien se parecen (sección 13); lo que lo distingue es
    lo que dice él o ella y casi nadie más. Se mide con **TF-IDF**: cada persona es un
    "documento" hecho de todas sus palabras con contenido; el **TF** es cuánto usa una
    palabra entre las suyas, y el **IDF** (`ln(N / df)`, con `N` personas y `df` las que
    la usan) pesa más las palabras que pocos usan y cero las que usan todos. Así una
    palabra sube cuando esa persona la usa mucho y el resto poco.

    Para no premiar erratas ni chistes de una sola vez, solo entran las personas con al
    menos 2,000 palabras con contenido, las palabras usadas 50 veces o más en el grupo y
    las que esa persona escribió al menos 10 veces.
    """)
    return


@app.cell
def _(con, messages, tokens):
    distinctive = mo.sql(
        f"""
        WITH content AS (
            SELECT m.sender, t.token
            FROM tokens AS t
            JOIN messages AS m USING (message_id)
            WHERE t.is_alpha AND NOT t.is_stop AND m.sender IS NOT NULL
        ),
        users AS (
            SELECT sender, count(*) AS total FROM content GROUP BY sender HAVING count(*) >= 2000
        ),
        per_user AS (
            SELECT sender, token, count(*) AS veces
            FROM content JOIN users USING (sender)
            GROUP BY sender, token
        ),
        words AS (
            SELECT token, count(*) AS personas FROM per_user GROUP BY token HAVING sum(veces) >= 50
        ),
        scored AS (
            SELECT
                p.sender AS usuario,
                p.token AS palabra,
                p.veces,
                w.personas AS personas_que_la_usan,
                u.total,
                p.veces::DOUBLE / u.total * ln((SELECT count(*) FROM users)::DOUBLE / w.personas) AS tfidf
            FROM per_user AS p
            JOIN users AS u USING (sender)
            JOIN words AS w USING (token)
            WHERE p.veces >= 10
        )
        SELECT *, row_number() OVER (PARTITION BY usuario ORDER BY tfidf DESC, palabra) AS lugar
        FROM scored
        QUALIFY lugar <= 8
        ORDER BY usuario, lugar
        """,
        engine=con,
        output=False,
    )
    (
        distinctive.filter(pl.col("lugar") <= 6)
        .group_by("usuario", maintain_order=True)
        .agg(
            pl.format("{} ({})", pl.col("palabra"), pl.col("veces"))
            .str.join(", ")
            .alias("palabras_distintivas")
        )
    )
    return (distinctive,)


@app.cell
def _(distinctive):
    _users = distinctive.unique("usuario").sort("total", descending=True)["usuario"][:9]
    _fig, _axes = plt.subplots(3, 3, figsize=(11, 8))
    for _ax, _user in zip(_axes.flat, _users):
        _words = distinctive.filter(pl.col("usuario") == _user).head(6)
        barh(_words["palabra"], _words["veces"], _user, ax=_ax)
    _fig
    return


@app.cell
def _():
    note(
        "Cada panel es una de las nueve personas con más palabras, con sus seis palabras "
        "más distintivas; la barra es cuántas veces las escribió. Salen **muletillas y "
        "abreviaturas propias** (*qpedo*, *alaverga*, *ylv*, *saka*), **chistes internos** "
        "que solo usan una o pocas personas y **temas personales** (futbol, un videojuego, "
        "trabajo y prácticas). También aparecen palabras en inglés y **nombres propios** "
        "que el enmascarado no reconoció como nombres: TF-IDF es justo la herramienta que "
        "los saca a la luz, así que sirve para revisar `anonymize.extra_names`."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## 18. ¿Cómo cambian las palabras con el tiempo?

    Primero, cómo se mueven mes a mes las 12 palabras con contenido más usadas, como
    veces por cada 1,000 palabras con contenido (así un mes con más mensajes no cuenta
    como más uso; cada gráfica tiene su propia escala). Después, qué palabras se usan más
    y menos en el **último año** que en el año anterior.
    """)
    return


@app.cell
def _(con, messages, tokens):
    monthly_words = mo.sql(
        f"""
        WITH content AS (
            SELECT strftime(date_trunc('month', m.timestamp), '%Y-%m') AS mes, t.token
            FROM tokens AS t
            JOIN messages AS m USING (message_id)
            WHERE t.is_alpha AND NOT t.is_stop AND m.sender IS NOT NULL
        ),
        top_words AS (
            SELECT token, row_number() OVER (ORDER BY count(*) DESC, token) AS lugar
            FROM content
            GROUP BY token
            QUALIFY lugar <= 12
        ),
        months AS (
            SELECT mes, count(*) AS total FROM content GROUP BY mes HAVING count(*) >= 1000
        )
        SELECT
            c.mes,
            w.token AS palabra,
            w.lugar,
            round(1000.0 * count(*) / m.total, 2) AS por_mil
        FROM content AS c
        JOIN months AS m USING (mes)
        JOIN top_words AS w USING (token)
        GROUP BY c.mes, w.token, w.lugar, m.total
        ORDER BY w.lugar, c.mes
        """,
        engine=con,
        output=False,
    )
    _months = sorted(set(monthly_words["mes"]))
    _fig, _axes = plt.subplots(3, 4, figsize=(12, 7))
    _top_words = monthly_words.unique("palabra").sort("lugar")["palabra"]
    for _ax, _word in zip(_axes.flat, _top_words):
        _rows = monthly_words.filter(pl.col("palabra") == _word)
        _rate = dict(zip(_rows["mes"], _rows["por_mil"]))
        line(
            [month[2:] for month in _months],
            [_rate.get(month, 0) for month in _months],
            _word,
            every=6,
            markers=False,
            ax=_ax,
        )
    _fig
    return


@app.cell
def _(con, messages, tokens):
    word_shift = mo.sql(
        f"""
        WITH content AS (
            SELECT m.timestamp > (SELECT max(timestamp) - INTERVAL 1 YEAR FROM messages) AS reciente, t.token
            FROM tokens AS t
            JOIN messages AS m USING (message_id)
            WHERE t.is_alpha AND NOT t.is_stop AND m.sender IS NOT NULL
        ),
        totals AS (
            SELECT count(*) FILTER (reciente) AS reciente, count(*) FILTER (NOT reciente) AS anterior
            FROM content
        ),
        counts AS (
            SELECT
                token AS palabra,
                count(*) FILTER (reciente) AS ultimo_ano,
                count(*) FILTER (NOT reciente) AS año_anterior
            FROM content
            GROUP BY token
            HAVING count(*) >= 150
        )
        SELECT
            palabra,
            ultimo_ano,
            año_anterior,
            round((ultimo_ano / t.reciente) / nullif(año_anterior / t.anterior, 0), 2) AS veces_mas_usada
        FROM counts, totals AS t
        ORDER BY veces_mas_usada DESC NULLS FIRST
        """,
        output=False,
        engine=con
    )
    return (word_shift,)


@app.cell
def _(word_shift):
    _steady = word_shift.filter((pl.col("ultimo_ano") >= 20) & (pl.col("año_anterior") >= 20))
    _rising = _steady.sort("veces_mas_usada", descending=True).head(12)
    _falling = (
        _steady.with_columns(veces_menos=1 / pl.col("veces_mas_usada"))
        .sort("veces_menos", descending=True)
        .head(12)
    )
    _fig, _axes = plt.subplots(1, 2, figsize=(11, 4.2))
    barh(
        _rising["palabra"],
        _rising["veces_mas_usada"],
        "Suben",
        "veces más frecuente que el año anterior",
        fmt="{:.1f}×",
        ax=_axes[0],
    )
    barh(
        _falling["palabra"],
        _falling["veces_menos"],
        "Bajan",
        "veces menos frecuente que el año anterior",
        fmt="{:.1f}×",
        ax=_axes[1],
    )
    _fig
    return


@app.cell
def _(word_shift):
    _new = word_shift.filter((pl.col("año_anterior") <= 2) & (pl.col("ultimo_ano") >= 100))
    note(
        "Las barras comparan la frecuencia de cada palabra (por palabras con contenido) en "
        "los últimos 12 meses contra los 12 anteriores, entre palabras usadas al menos 20 "
        "veces en cada periodo. Palabras **casi nuevas** (100 veces o más en el último año "
        "y a lo sumo 2 antes): "
        + (", ".join(f"*{word}*" for word in _new["palabra"]) or "ninguna")
        + "."
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Conclusiones

    Del análisis del grupo de WhatsApp aprendí que la mayoría de los mensajes provienen de un grupo reducido de miembros, que la actividad se concentra en horario laboral y que predominan los mensajes cortos, de menos de cinco palabras. Como esperaba, el contenido está repleto de groserías y chistes internos. Al mismo tiempo, los temas y las palabras utilizadas son influenciadas por las tendencias de memes.

    Sobre el proyecto aprendí a consolidar un mapa mental de cómo estructurar la ingesta y el procesamiento de datos (notebooks, jobs, data/, metadata/).

    En cuanto al procesamiento, encontré que los textos tienen muchas faltas de ortografía y que una misma palabra puede aparecer con numerosas variantes, sobre todo cuando se combina con términos en inglés. Esto hizo especialmente tediosa la automatización del anonimizado: al final tuve que agregar manualmente una lista de nombres y apodos, y aun así algunos se me escaparon.

    Respecto a los resultados, me pareció muy interesante cómo se pueden capturar las tendencias a lo largo del tiempo. Conociendo el contexto, tiene bastante sentido qué temas empiezan a aparecer y cuáles van perdiendo presencia. Sin embargo, también noté que es difícil que los datos por sí solos expliquen lo que realmente está pasando: los patrones me hacen sentido porque conozco lo que ocurre de fondo, pero para alguien ajeno al grupo no serían tan evidentes.
    """)
    return


if __name__ == "__main__":
    app.run()
