from enum import StrEnum
from pathlib import Path


class OnExists(StrEnum):
    SKIP = "skip"
    OVERWRITE = "overwrite"
    ERROR = "error"


class FilePolicy:
    def __init__(self, on_exists: OnExists = OnExists.SKIP):
        self.on_exists = on_exists

    def should_write(self, destination: Path) -> bool:
        if not destination.exists():
            return True

        if self.on_exists == OnExists.SKIP:
            return False

        if self.on_exists == OnExists.ERROR:
            raise FileExistsError(f"File already exists: {destination}")

        return True
