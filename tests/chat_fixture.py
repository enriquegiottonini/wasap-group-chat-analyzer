"""Chat sintético con cada caso del formato de iOS que documenta el EDA bronze.

Nunca usar mensajes reales en las pruebas.
"""

from pathlib import Path

LRM, NNBSP, FSI, PDI = "\u200e", "\u202f", "\u2068", "\u2069"

GROUP = "Los Primos 🏠"

RECORDS = [
    # (registro, tipo esperado)
    (f"[01/02/25, 9:05:00{NNBSP}a.m.] Ana López: hola @{FSI}~Beto Ruiz{PDI}, ¿vienes?", "text"),
    (f"{LRM}[01/02/25, 9:06:10{NNBSP}a.m.] ~{NNBSP}Beto Ruiz: {LRM}sticker omitted", "attachment"),
    (f"[01/02/25, 12:30:00{NNBSP}p.m.] Ana López: línea uno\nlínea dos", "text"),
    (
        f"{LRM}[02/02/25, 12:05:00{NNBSP}a.m.] ~{NNBSP}Beto Ruiz: foto de Ana {LRM}image omitted",
        "attachment",
    ),
    (
        f"[02/02/25, 1:00:00{NNBSP}p.m.] {GROUP}: {LRM}Messages and calls are end-to-end encrypted.",
        "group_notice",
    ),
    (f"[02/02/25, 1:01:00{NNBSP}p.m.] Ana López:", "empty"),
    (
        f"[02/02/25, 1:02:00{NNBSP}p.m.] Ana López: {LRM}Location: https://maps.google.com/?q=29.1,-110.9",
        "location",
    ),
    (
        f"[02/02/25, 1:03:00{NNBSP}p.m.] ~{NNBSP}Beto Ruiz: {LRM}This message was deleted.",
        "deleted",
    ),
    (f"[02/02/25, 1:04:00{NNBSP}p.m.] Ana López: {LRM}Ana López added Carla", "system_notice"),
    (
        f"[02/02/25, 1:05:00{NNBSP}p.m.] ~{NNBSP}Beto Ruiz: POLL:\n¿Dónde?\nOPTION: Casa (1 vote)",
        "poll",
    ),
    (
        (
            f"[02/02/25, 1:06:00{NNBSP}p.m.] Ana López: {LRM}You received a view once photo. "
            "For added privacy, you can only open it on your phone."
        ),
        "view_once",
    ),
    (
        (
            f"[02/02/25, 1:07:00{NNBSP}p.m.] Ana López: {LRM}Waiting for this message. "
            "This may take a while."
        ),
        "unavailable",
    ),
    (
        f"[02/02/25, 1:08:00{NNBSP}p.m.] Ana López: corregido, Beto {LRM}<This message was edited>",
        "text",
    ),
]

KINDS = [kind for _, kind in RECORDS]
CHAT = "\r\n".join(record for record, _ in RECORDS) + "\r\n"


def write_chat(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    chat_file = directory / "_chat.txt"
    chat_file.write_text(CHAT, encoding="utf-8", newline="")
    return chat_file
