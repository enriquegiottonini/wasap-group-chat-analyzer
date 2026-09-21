import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")

with app.setup:
    from pathlib import Path

    import duckdb
    import marimo as mo
    from matplotlib.colors import LinearSegmentedColormap, to_hex
    from matplotlib.font_manager import FontProperties, findfont
    from matplotlib.lines import Line2D
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator, StrMethodFormatter
    import polars as pl
    from wordcloud import WordCloud

    from wasap_group_analyzer.anonymize import sender_id
    from wasap_group_analyzer.config import active_chat, load_params, load_salt
    from wasap_group_analyzer.constants import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
    from wasap_group_analyzer.metadata.source import read_group_name

    # Colores de las gráficas: una sola serie en azul; texto, ejes y rejilla recesivos.
    COLORS = {
        "series": "#2a78d6",
        "text": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e4e3df",
        "surface": "#fcfcfb",
        "series_light": "#9cc3ef",
    }

    # Las tablas (resultados de mo.sql, en polars) se exportan como HTML estático: se muestran
    # completas, sin recortar textos ni ocultar filas, y sin la fila de tipos de dato.
    pl.Config.set_tbl_rows(60)
    pl.Config.set_fmt_str_lengths(90)
    pl.Config.set_tbl_hide_column_data_types(True)
    pl.Config.set_tbl_hide_dataframe_shape(True)

    plt.rcParams.update(
        {
            "figure.facecolor": COLORS["surface"],
            "axes.facecolor": COLORS["surface"],
            "axes.edgecolor": COLORS["grid"],
            "axes.labelcolor": COLORS["muted"],
            "axes.titlecolor": COLORS["text"],
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["muted"],
            "grid.color": COLORS["grid"],
            "grid.linewidth": 0.8,
            "font.size": 10,
        }
    )


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Utilidades compartidas de los notebooks

    Funciones que usan los dos notebooks de EDA
    (`01_eda_bronze` y `02_eda_silver`), que las importan con `from utils import ...`.
    Lo que también necesitan los jobs (parseo, anonimización) vive en el paquete
    `wasap_group_analyzer`; aquí solo queda lo propio de explorar: conexión a DuckDB,
    rutas del chat activo y gráficas.

    - `chat_dirs()`: carpetas `raw`, `interim` y `processed` del chat activo (`CHAT=` o
      `chat` en `params.yml`).
    - `group_name()`: nombre del grupo según `FUENTE.txt`.
    - `connect()`: DuckDB en memoria con la función `anon(nombre)` y una vista por cada
      `.parquet` del chat en `interim/` y `processed/`.
    - `note()`: markdown con números calculados, como HTML que GitHub sí muestra.
    - `barh()`, `boxplot()`, `columns()`, `line()`, `heatmap()` y `wordcloud()`: gráficas con el mismo estilo.
    """)
    return


@app.function
def chat_dirs(chat: str | None = None) -> dict[str, Path]:
    """Carpetas de datos del chat (por defecto, el activo)."""
    chat = active_chat(load_params(), chat)
    return {
        "chat": chat,
        "raw": RAW_DIR / chat,
        "interim": INTERIM_DIR / chat,
        "processed": PROCESSED_DIR / chat,
    }


@app.function
def group_name(chat: str | None = None) -> str:
    """Nombre del grupo, de la primera línea de FUENTE.txt (lo escribe el job de ingesta)."""
    return read_group_name(chat_dirs(chat)["raw"])


@app.function
def connect(
    chat: str | None = None, views: bool = True, private: bool = False
) -> duckdb.DuckDBPyConnection:
    """DuckDB en memoria para explorar un chat.

    - `anon(nombre)`: id anónimo del nombre (mismo hash con sal que el job de
      anonimización), para mostrar remitentes sin exponer nombres reales.
    - Si `views`, una vista por cada `.parquet` de `interim/` y `processed/`, con el
      nombre del archivo (`messages_anon`, `messages`...). `bronze` (con nombres reales)
      solo si `private`: para análisis manual, nunca en un notebook que se publica.

    El texto crudo (`raw/`) no se carga aquí: leerlo y separarlo en registros es parte de
    lo que explica `01_eda_bronze`.
    """
    dirs = chat_dirs(chat)
    con = duckdb.connect()

    salt = load_salt()
    con.create_function("anon", lambda name: sender_id(name, salt), ["VARCHAR"], "VARCHAR")

    if views:
        for layer in ("interim", "processed"):
            for parquet in sorted(dirs[layer].glob("*.parquet")):
                if parquet.stem == "bronze" and not private:
                    continue
                # Una vista no admite parámetros preparados: la ruta va en el SQL, escapada.
                path = str(parquet).replace("'", "''")
                con.execute(
                    f"CREATE VIEW \"{parquet.stem}\" AS SELECT * FROM read_parquet('{path}')"
                )
    return con


@app.function
def note(markdown: str) -> mo.Html:
    """Markdown calculado (con números del chat) como HTML estático.

    `mo.md` en una celda de código se exporta como `text/markdown`; como HTML lo muestra
    cualquier visor de .ipynb, incluido GitHub.
    """
    return mo.Html(mo.md(markdown).text)


@app.function
def barh(labels, values, title: str, xlabel: str = "", fmt: str = "{:,.0f}", ax=None):
    """Barras horizontales en el orden dado (el primero arriba), con el valor al final."""
    labels, values = list(labels), list(values)
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 0.32 * len(labels) + 1))
    positions = range(len(labels))[::-1]
    ax.barh(positions, values, height=0.72, color=COLORS["series"])
    ax.set_yticks(list(positions), labels)
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.set_axisbelow(True)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    for position, value in zip(positions, values):
        ax.annotate(
            fmt.format(value),
            (value, position),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=COLORS["muted"],
        )
    ax.margins(x=0.12)
    plt.tight_layout()
    return ax


@app.function
def boxplot(groups: dict, title: str, xlabel: str = "", ax=None):
    """Una caja por grupo, en el orden dado (la primera arriba): mediana, cuartiles y promedio.

    La caja cubre la mitad central de los valores, la línea es la mediana y el rombo el
    promedio; los bigotes llegan hasta 1.5 veces el rango de la caja y los valores más
    lejanos no se dibujan, para que unos pocos casos extremos no aplasten al resto.
    """
    labels = list(groups)
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 0.6 * len(labels) + 1.4))
    line_style = {"color": COLORS["muted"], "linewidth": 1.2}
    ax.boxplot(
        [groups[label] for label in labels],
        orientation="horizontal",
        tick_labels=labels,
        widths=0.5,
        showfliers=False,
        showmeans=True,
        patch_artist=True,
        boxprops={"facecolor": COLORS["series_light"], "edgecolor": COLORS["muted"]},
        medianprops={"color": COLORS["text"], "linewidth": 2},
        whiskerprops=line_style,
        capprops=line_style,
        meanprops={
            "marker": "D",
            "markerfacecolor": COLORS["series"],
            "markeredgecolor": COLORS["surface"],
            "markersize": 7,
        },
    )
    ax.invert_yaxis()
    ax.set_xlim(right=ax.get_xlim()[1] * 1.25)  # espacio a la derecha para la leyenda
    ax.xaxis.set_major_locator(MaxNLocator(nbins=8, integer=True))
    ax.tick_params(axis="y", length=0)
    ax.xaxis.grid(True)
    ax.set_axisbelow(True)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.legend(
        [
            Line2D([], [], color=COLORS["text"], linewidth=2),
            Line2D([], [], marker="D", color=COLORS["series"], linestyle="", markersize=7),
        ],
        ["mediana", "promedio"],
        frameon=False,
        loc="lower right",
        labelcolor=COLORS["muted"],
    )
    plt.tight_layout()
    return ax


@app.function
def columns(labels, values, title: str, ylabel: str = "", rotate: int = 0, ax=None):
    """Columnas verticales en el orden dado (p. ej. meses, días u horas)."""
    labels, values = list(labels), list(values)
    if ax is None:
        _, ax = plt.subplots(figsize=(max(6, 0.28 * len(labels) + 2), 3.2))
    ax.bar(range(len(labels)), values, width=0.72, color=COLORS["series"])
    ax.set_xticks(range(len(labels)), labels, rotation=rotate, ha="right" if rotate else "center")
    ax.tick_params(axis="x", length=0)
    ax.yaxis.grid(True)
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.set_axisbelow(True)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    plt.tight_layout()
    return ax


@app.function
def line(
    labels,
    values,
    title: str,
    ylabel: str = "",
    every: int = 1,
    hollow=(),
    markers: bool = True,
    label_peak: bool = False,
    ax=None,
):
    """Línea de una serie en el orden dado (p. ej. meses), con el eje y desde cero.

    - `every`: cada cuántas etiquetas se escribe una en el eje x.
    - `hollow`: posiciones de puntos incompletos (p. ej. un mes a medias), sin relleno.
    - `label_peak`: escribe el valor del punto más alto; es la única etiqueta directa.
    """
    labels, values = list(labels), list(values)
    if ax is None:
        _, ax = plt.subplots(figsize=(max(6, 0.3 * len(labels) + 2), 3.4))
    positions = list(range(len(labels)))
    ax.plot(positions, values, color=COLORS["series"], linewidth=2, zorder=2)
    if markers:
        marker = {"s": 30, "edgecolor": COLORS["series"], "linewidth": 1.5, "zorder": 3}
        solid = [i for i in positions if i not in hollow]
        ax.scatter(solid, [values[i] for i in solid], color=COLORS["series"], **marker)
        if hollow:
            ax.scatter(list(hollow), [values[i] for i in hollow], color=COLORS["surface"], **marker)
    if label_peak:
        peak = max(positions, key=values.__getitem__)
        ax.annotate(
            f"{labels[peak]}: {values[peak]:,.0f}",
            (peak, values[peak]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color=COLORS["muted"],
        )
    ax.set_xticks(positions[::every], labels[::every])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(bottom=0, top=max(values) * 1.15)
    ax.yaxis.grid(True)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,g}"))
    ax.set_axisbelow(True)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    plt.tight_layout()
    return ax


@app.function
def heatmap(matrix, row_labels, col_labels, title: str, legend: str = "", ax=None):
    """Mapa de calor de una sola tonalidad: claro es poco y oscuro es mucho.

    Una escala secuencial (un solo tono, de claro a oscuro) es la que corresponde a una
    magnitud; un arcoíris inventaría diferencias que no están en los datos.
    """
    scale = LinearSegmentedColormap.from_list(
        "azules", ["#f4f8fd", "#9cc3ef", COLORS["series"], "#123f75"]
    )
    if ax is None:
        _, ax = plt.subplots(figsize=(11, 0.42 * len(row_labels) + 1.8))
    image = ax.imshow(matrix, aspect="auto", cmap=scale)
    ax.set_xticks(range(len(col_labels)), col_labels, fontsize=8)
    ax.set_yticks(range(len(row_labels)), row_labels)
    ax.tick_params(length=0)
    ax.grid(False)
    ax.set_title(title)
    bar = ax.figure.colorbar(image, ax=ax, shrink=0.9)
    bar.outline.set_visible(False)
    bar.set_label(legend, color=COLORS["muted"])
    plt.tight_layout()
    return ax


@app.function
def wordcloud(words, counts, title: str, ax=None):
    """Nube de palabras: el tamaño de cada palabra es proporcional a su frecuencia.

    Un solo tono, de claro (poco) a oscuro (mucho), en la misma tipografía que las gráficas;
    la posición es aleatoria pero fija (misma semilla, misma nube). Sirve para ver el
    conjunto y las diferencias grandes; para leer cifras exactas, la tabla.
    """
    frequencies = dict(zip(words, counts))
    low, high = min(frequencies.values()), max(frequencies.values())
    scale = LinearSegmentedColormap.from_list(
        "azules_texto", ["#6fa8e6", COLORS["series"], "#123f75"]
    )

    def color(word, **_):
        return to_hex(scale(((frequencies[word] - low) / max(high - low, 1)) ** 0.5))

    cloud = WordCloud(
        width=1100,
        height=520,
        background_color=COLORS["surface"],
        color_func=color,
        font_path=findfont(FontProperties(family="DejaVu Sans", weight="bold")),
        prefer_horizontal=1.0,
        relative_scaling=1,
        margin=6,
        random_state=42,
    ).generate_from_frequencies(frequencies)
    if ax is None:
        _, ax = plt.subplots(figsize=(11, 5.2))
    ax.imshow(cloud.to_array(), interpolation="bilinear")
    ax.axis("off")
    ax.set_title(title)
    plt.tight_layout()
    return ax


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Prueba rápida

    El chat activo y qué datos encuentra `connect()` para él:
    """)
    return


@app.cell
def _():
    _dirs = chat_dirs()
    _views = [name for (name,) in connect().sql("SHOW TABLES").fetchall()]
    note(
        f"Chat activo: **{_dirs['chat']}** · vistas disponibles: "
        + (", ".join(f"`{name}`" for name in _views) or "ninguna todavía (`make anonymize`)")
    )
    return


if __name__ == "__main__":
    app.run()
