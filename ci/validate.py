#!/usr/bin/env python3
"""Pre-release checks for the integration.

Run by the `validate` job. Catches the mistakes that only surface after a
release is published: malformed JSON, a manifest missing a key Home Assistant
needs, translations that have drifted apart, and a tag whose version does not
match the manifest it ships.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("INTEGRATION_PATH", "custom_components/eastron_modbus"))

# Languages the integration ships. The first one is the reference the others
# are compared against.
LANGUAGES = ("en", "de")


def key_paths(value: object, prefix: str = "") -> set[str]:
    """Every leaf path in a translation file, as dotted keys.

    Compared between languages, so a key added to one file and forgotten in
    the other shows up as a difference rather than as an untranslated string
    in the UI.
    """
    if not isinstance(value, dict):
        return {prefix}
    paths: set[str] = set()
    for key, child in value.items():
        paths |= key_paths(child, f"{prefix}.{key}" if prefix else key)
    return paths


def main() -> int:
    failures: list[str] = []

    for path in sorted(pathlib.Path(".").rglob("*.json")):
        if ".git" in path.parts:
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            failures.append(f"{path}: {exc}")
    if failures:
        print("invalid JSON:", *failures, sep="\n  ")
        return 1

    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    for key in ("domain", "name", "version", "documentation"):
        if not manifest.get(key):
            failures.append(f"manifest.json is missing {key!r}")
    if "codeowners" not in manifest:
        failures.append("manifest.json is missing 'codeowners'")

    # Home Assistant falls back to the raw key when a translation is absent,
    # so a missing entry is visible in the UI but never fails a test.
    reference, *others = LANGUAGES
    ref_path = ROOT / "translations" / f"{reference}.json"
    ref_keys = key_paths(json.loads(ref_path.read_text(encoding="utf-8")))
    for lang in others:
        path = ROOT / "translations" / f"{lang}.json"
        keys = key_paths(json.loads(path.read_text(encoding="utf-8")))
        missing = sorted(ref_keys - keys)
        extra = sorted(keys - ref_keys)
        if missing or extra:
            failures.append(
                f"{path}: keys differ from {reference}.json "
                f"(missing {missing}, extra {extra})"
            )

    # A release must ship the version it claims in its tag.
    tag = os.environ.get("CI_COMMIT_TAG")
    if tag:
        expected = tag.lstrip("v")
        if manifest["version"] != expected:
            failures.append(
                f"tag {tag} expects manifest version {expected!r}, "
                f"found {manifest['version']!r}"
            )

    if failures:
        print("validation failed:", *failures, sep="\n  ")
        return 1

    print(f"manifest {manifest['version']} ok; JSON and translations consistent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
