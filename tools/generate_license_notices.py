"""Collect installed backend license texts in an isolated, lockfile-installed runtime.

Run inside the backend container, then commit the generated notices after review.
The installed runtime is the inventory; do not run this in a general tool environment.
"""

import json
from importlib.metadata import distributions
from pathlib import Path


def collect():
    records, notices = [], []
    for item in sorted(distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = item.metadata["Name"]
        if name.lower() in {"pip", "setuptools", "wheel"}:
            continue
        expression = item.metadata.get("License-Expression") or item.metadata.get(
            "License"
        )
        if not expression:
            expression = (
                "; ".join(
                    value
                    for value in item.metadata.get_all("Classifier", [])
                    if value.startswith("License ::")
                )
                or "Review upstream license text"
            )
        texts = []
        for file in sorted(item.files or [], key=str):
            normalized = str(file).lower()
            if ".dist-info/" in normalized and any(
                token in Path(normalized).name
                for token in ("license", "notice", "copying")
            ):
                path = Path(item.locate_file(file))
                if path.is_file():
                    texts.append((str(file), path.read_text(encoding="utf-8")))
        if not texts:
            raise ValueError("Missing installed license text for " + name)
        records.append({"name": name, "version": item.version, "license": expression})
        for path, content in texts:
            notices.append(
                f"{'=' * 72}\n{name} {item.version}\n{path}\n{'=' * 72}\n{content.strip()}\n"
            )
    return {"packages": records, "notices": "\n".join(notices)}


if __name__ == "__main__":
    print(json.dumps(collect()))
