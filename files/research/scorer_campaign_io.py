from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Mapping, Sequence


class CampaignArtifactWriteError(RuntimeError):
    """Raised when a campaign artifact cannot be written safely."""


def canonical_json_text(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def pretty_json_text(value: Any) -> str:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


def _atomic_replace_text(
    *,
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            path,
        )

    except Exception as exc:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise CampaignArtifactWriteError(
            f"Unable to write campaign artifact atomically: {path}"
        ) from exc


def write_json_atomic(
    *,
    path: str | Path,
    value: Any,
) -> None:
    _atomic_replace_text(
        path=Path(path),
        text=pretty_json_text(value),
    )


def write_json_immutable(
    *,
    path: str | Path,
    value: Any,
) -> None:
    destination = Path(path)
    new_canonical = canonical_json_text(value)

    if destination.exists():
        try:
            existing_value = json.loads(
                destination.read_text(
                    encoding="utf-8",
                )
            )
        except Exception as exc:
            raise CampaignArtifactWriteError(
                "Existing immutable JSON artifact is unreadable: "
                f"{destination}"
            ) from exc

        existing_canonical = canonical_json_text(
            existing_value
        )

        if existing_canonical != new_canonical:
            raise CampaignArtifactWriteError(
                "Immutable JSON artifact identity conflict: "
                f"{destination}"
            )

        return

    _atomic_replace_text(
        path=destination,
        text=pretty_json_text(value),
    )


def write_csv_atomic(
    *,
    path: str | Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, Any]],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path: Path | None = None

    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)

            writer = csv.DictWriter(
                handle,
                fieldnames=list(fieldnames),
                extrasaction="raise",
            )
            writer.writeheader()

            for raw_row in rows:
                writer.writerow(
                    {
                        field: raw_row.get(field, "")
                        for field in fieldnames
                    }
                )

            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            destination,
        )

    except Exception as exc:
        if (
            temporary_path is not None
            and temporary_path.exists()
        ):
            temporary_path.unlink()

        raise CampaignArtifactWriteError(
            f"Unable to write campaign CSV atomically: {destination}"
        ) from exc
