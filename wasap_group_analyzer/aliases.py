"""Alias de los miembros: animales de México.

Cada alias es el nombre común de un animal que vive en México ("Ajolote", "Jaguar",
"Quetzal"), y se asignan en el orden en que cada miembro escribió por primera vez en el
chat. Así la asignación no depende del hash y no cambia si una exportación más nueva
agrega miembros al final.

Son nombres de una sola palabra, fáciles de distinguir entre sí en una gráfica y que
rara vez coinciden con el nombre de una persona. Aun así, el job de anonimización salta
cualquier alias que comparta una palabra con el nombre de un miembro real, para que el
alias no dé ninguna pista sobre quién es.
"""

from collections.abc import Iterable
import re

from wasap_group_analyzer.anonymize import fold

ANIMALS = (
    "Ajolote",
    "Jaguar",
    "Coyote",
    "Quetzal",
    "Tlacuache",
    "Armadillo",
    "Colibrí",
    "Tucán",
    "Ocelote",
    "Puma",
    "Xoloitzcuintle",
    "Guacamaya",
    "Mapache",
    "Venado",
    "Tapir",
    "Manatí",
    "Cacomixtle",
    "Zopilote",
    "Chachalaca",
    "Tejón",
    "Berrendo",
    "Lince",
    "Nutria",
    "Iguana",
    "Cocodrilo",
    "Murciélago",
    "Cenzontle",
    "Correcaminos",
    "Zorrillo",
    "Jabalí",
    "Pecarí",
    "Tigrillo",
    "Halcón",
    "Aguililla",
    "Garza",
    "Pelícano",
    "Flamenco",
    "Ballena",
    "Delfín",
    "Vaquita",
    "Tiburón",
    "Mantarraya",
    "Pulpo",
    "Langosta",
    "Abeja",
    "Mariposa",
    "Libélula",
    "Alacrán",
    "Tarántula",
    "Chapulín",
    "Luciérnaga",
    "Salamandra",
    "Tortuga",
    "Búho",
    "Lechuza",
    "Águila",
    "Saraguato",
    "Tepezcuintle",
)

# Alias de alguien que aparece en el texto (una mención) pero nunca escribió en el chat.
UNKNOWN_MEMBER = "persona"


def assign_aliases(sender_ids: Iterable[str], avoid_words: Iterable[str] = ()) -> dict[str, str]:
    """`sender_ids` en orden de su primer mensaje → alias de animal.

    Se salta cualquier alias con una palabra en `avoid_words` (comparadas con `fold`: sin
    mayúsculas ni acentos), p. ej. las palabras de los nombres reales de los miembros. Si
    no alcanzan los animales, los que sobran son "Animal 59", etc.
    """
    avoid = {fold(word) for word in avoid_words}
    available = (
        alias
        for alias in ANIMALS
        if not any(fold(word) in avoid for word in re.findall(r"\w+", alias))
    )
    aliases = {}
    for position, sender in enumerate(dict.fromkeys(sender_ids)):
        aliases[sender] = next(available, None) or f"Animal {position + 1}"
    return aliases
