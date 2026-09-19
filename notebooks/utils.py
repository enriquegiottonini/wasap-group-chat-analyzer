import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium")

with app.setup:
    from pathlib import Path

    import duckdb
    import marimo as mo
    import matplotlib.pyplot as plt
    from matplotlib.ticker import StrMethodFormatter
    import polars as pl

    from wasap_group_analyzer.anonymize import sender_id
    from wasap_group_analyzer.config import active_chat, load_params, load_salt
    from wasap_group_analyzer.constants import INTERIM_DIR, PROCESSED_DIR, RAW_DIR
    from wasap_group_analyzer.provenance import read_group_name

    # Colores de las gráficas: una sola serie en azul; texto, ejes y rejilla recesivos.
    COLORS = {
        "series": "#2a78d6",
        "text": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e4e3df",
        "surface": "#fcfcfb",
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
    - `barh()` y `columns()`: gráficas de barras con el mismo estilo.
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
def connect(chat: str | None = None, views: bool = True) -> duckdb.DuckDBPyConnection:
    """DuckDB en memoria para explorar un chat.

    - `anon(nombre)`: id anónimo del nombre (mismo hash con sal que el job de
      anonimización), para mostrar remitentes sin exponer nombres reales.
    - Si `views`, una vista por cada `.parquet` de `interim/` y `processed/`, con el
      nombre del archivo (`bronze`, `messages_anon`...).

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
