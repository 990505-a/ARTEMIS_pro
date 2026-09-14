# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Write-side service for the active model configuration (artemis.jsonc).

The config file is JSONC with documentation comments, so edits are made by
replacing the small, well-anchored blocks that hold model choices instead of
re-serializing the whole file. Every write is verified by re-parsing the file
with the project's own loaders before it is allowed to stay.
"""

import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = {"google", "openai", "anthropic", "openrouter", "vertexai", "xai"}

_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9._\-/]+(:[A-Za-z0-9._\-/]+)?$")

# Matches `"name": { ...flat or one-level-nested object... },` — the model
# blocks in this file contain at most one nested object (the fallback).
_BLOCK_TEMPLATE = r'"{name}"\s*:\s*\{{[^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*\}},'


class ModelConfigUpdateError(ValueError):
    """Raised when a model-config update cannot be applied safely."""


def _validate(provider: str, model: str) -> None:
    if provider not in ALLOWED_PROVIDERS:
        raise ModelConfigUpdateError(
            f"Unknown provider '{provider}'. Allowed: {', '.join(sorted(ALLOWED_PROVIDERS))}"
        )
    if not model or not _MODEL_NAME_RE.match(model):
        raise ModelConfigUpdateError(
            "Model id may only contain letters, digits, dot, dash, slash, colon."
        )


def _render_block(name: str, provider: str, model: str, indent: str) -> str:
    return (
        f'{indent}"{name}": {{\n'
        f'{indent}  "provider": "{provider}",\n'
        f'{indent}  "model": "{model}",\n'
        f'{indent}  "fallback": {{ "provider": "{provider}", "model": "{model}" }}\n'
        f'{indent}}},'
    )


def _replace_block(text: str, name: str, provider: str, model: str, indent: str) -> str:
    pattern = re.compile(_BLOCK_TEMPLATE.format(name=name))
    replacement = _render_block(name, provider, model, indent)
    if not pattern.search(text):
        raise ModelConfigUpdateError(f'Block "{name}" not found in config file.')
    return pattern.sub(replacement, text, count=1)


def _replace_inline_model(text: str, anchor: str, model: str) -> str:
    """Rewrite `"model": "..."` inside the flat block that follows `anchor`."""
    idx = text.find(f'"{anchor}"')
    if idx < 0:
        raise ModelConfigUpdateError(f'Anchor "{anchor}" not found in config file.')
    local = re.compile(r'("model"\s*:\s*")[^"]*(")')
    match = local.search(text, idx)
    if not match:
        raise ModelConfigUpdateError(f'No model field found after anchor "{anchor}".')
    return text[: match.start(1)] + match.group(1) + model + match.group(2) + text[match.end():]


def update_model_config(
    config_path,
    provider: str,
    model: str,
    fallback_provider: str | None = None,
    fallback_model: str | None = None,
    apply_to_nodes: bool = True,
) -> dict:
    """Patch the active model selection in artemis.jsonc.

    Updates the top-level ``default`` block; when ``apply_to_nodes`` is set it
    also switches the node-level overrides (hopper, object_detector) and the
    background-compression model strings (step_summarizer, chunking) so the
    whole stack runs on the chosen model.
    """
    _validate(provider, model)
    if fallback_provider or fallback_model:
        _validate(fallback_provider or provider, fallback_model or model)

    original = config_path.read_text(encoding="utf-8")
    text = original

    # Top-level default block (2-space indent).
    text = _replace_block(text, "default", provider, model, "  ")

    nodes_updated = ["default"]
    if apply_to_nodes:
        for node in ("object_detector", "hopper"):
            text = _replace_block(text, node, provider, model, "    ")
            nodes_updated.append(node)
        for anchor in ("step_summarizer", "chunking"):
            text = _replace_inline_model(text, anchor, model)
            nodes_updated.append(anchor)

    # Parse-verify before the write is allowed to stay.
    from artemis.utils.file import load_jsonc
    from artemis.config import parse_llm_config

    try:
        import io

        parsed = load_jsonc(io.StringIO(text))
        if not isinstance(parsed, dict) or "default" not in parsed:
            raise ValueError("parsed config lost the 'default' section")
    except Exception as exc:  # noqa: BLE001 - report as a failed update
        raise ModelConfigUpdateError(f"Rewritten config failed to parse: {exc}") from exc

    # Atomic write: temp file in the same directory, then replace.
    fd, tmp_path = tempfile.mkstemp(
        dir=str(config_path.parent), prefix=config_path.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp_path, config_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Belt and braces: run the project's own config loader against the file.
    try:
        parse_llm_config()
    except Exception as exc:  # noqa: BLE001 - restore and report
        config_path.write_text(original, encoding="utf-8", newline="\n")
        raise ModelConfigUpdateError(
            f"Project config loader rejected the new file; original restored. ({exc})"
        ) from exc

    logger.info("Model config updated: %s/%s (nodes: %s)", provider, model, nodes_updated)
    return {
        "provider": provider,
        "model": model,
        "nodes_updated": nodes_updated,
    }
