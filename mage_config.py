"""Pure helpers for the Mage nodes: API key lookup, widget options from the
SDK's copy of the API reference, and request config assembly. Nothing here
imports ComfyUI or torch, so it is unit tested on its own."""

from __future__ import annotations

import configparser
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from mage_space.types import ARCHITECTURES

CONFIG_FILE = Path(__file__).parent / "config.ini"

KEY_HELP = (
    "No Mage API key. Create one at https://www.mage.space/api?tab=api-keys, then set "
    "the MAGE_API_KEY environment variable before starting ComfyUI, or copy "
    f"config.ini.example to {CONFIG_FILE} and put the key there."
)


def load_api_key(environ: Mapping[str, str] = os.environ, config_file: Path = CONFIG_FILE) -> str | None:
    """The API key from MAGE_API_KEY, else from config.ini's [mage] api_key."""
    key = environ.get("MAGE_API_KEY", "").strip()
    if key:
        return key
    if config_file.is_file():
        parser = configparser.ConfigParser()
        parser.read(config_file)
        return parser.get("mage", "api_key", fallback="").strip() or None
    return None


def properties(architecture: str) -> dict[str, Any]:
    """The request fields an architecture documents, as JSON Schema."""
    return ARCHITECTURES[architecture]["schema"]["properties"]


def option_inputs(architecture: str, fields: Sequence[str]) -> dict[str, tuple]:
    """ComfyUI combo inputs for the listed option fields, in order, with the
    tokens and defaults from the API reference. A field the reference no
    longer lists is left out."""
    inputs: dict[str, tuple] = {}
    schemas = properties(architecture)
    for field in fields:
        schema = schemas.get(field)
        if not schema or "enum" not in schema:
            continue
        tokens = [str(token) for token in schema["enum"]]
        default = str(schema.get("default", tokens[0]))
        inputs[field] = (tokens, {"default": default, "tooltip": schema.get("description", "")})
    return inputs


def parse_extra_config(text: str) -> dict[str, Any]:
    """The generic node's extra fields: a JSON object, or empty."""
    if not text.strip():
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"extra_config is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ValueError('extra_config must be a JSON object, such as {"aspect_ratio": "16:9"}.')
    return value


def check_media(
    architecture: str,
    *,
    references: int = 0,
    first_frame: bool = False,
    last_frame: bool = False,
    video: bool = False,
) -> None:
    """Refuses media the architecture takes no field for, before anything is
    uploaded or spent."""
    schemas = properties(architecture)
    name = ARCHITECTURES[architecture]["name"]
    if references and "image" not in schemas:
        raise ValueError(f"{name} takes no reference images.")
    if references > 1 and "additional_images" not in schemas:
        raise ValueError(f"{name} takes one reference image; got {references}.")
    if first_frame and "first_image" not in schemas:
        raise ValueError(f"{name} takes no first frame image.")
    if last_frame and "last_image" not in schemas:
        raise ValueError(f"{name} takes no last frame image.")
    if video and "videos" not in schemas and "video" not in schemas:
        raise ValueError(f"{name} takes no video input.")


def build_config(
    architecture: str,
    *,
    prompt: str,
    seed: int,
    options: Mapping[str, Any] | None = None,
    references: Sequence[str] = (),
    first_frame: str | None = None,
    last_frame: str | None = None,
    video: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The JSON body of a generate request. Media arguments are uploaded URLs;
    each goes in the field the architecture documents for its role."""
    check_media(
        architecture,
        references=len(references),
        first_frame=first_frame is not None,
        last_frame=last_frame is not None,
        video=video is not None,
    )
    config: dict[str, Any] = {"prompt": prompt, "seed": seed, **(options or {})}
    if references:
        config["image"] = references[0]
    if len(references) > 1:
        config["additional_images"] = list(references[1:])
    if first_frame is not None:
        config["first_image"] = first_frame
    if last_frame is not None:
        config["last_image"] = last_frame
    if video is not None:
        if "videos" in properties(architecture):
            config["videos"] = [video]
        else:
            config["video"] = video
    config.update(extra or {})
    return config
