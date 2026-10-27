#!/usr/bin/env python3
"""One-shot i18n extraction for the ARTEMIS showcase UI.

Rewrites Angular templates so every user-visible string flows through the
`t` pipe (English source string as the dictionary key) and emits the full key
list to stdout. Re-runs are idempotent: already-wrapped strings, comments,
<code>/<pre> content, Angular control-flow tokens and pipe arguments with
string literals (| date:'shortTime') are left alone.

Usage: python extract-i18n.py <template.html> [<template.html> ...]
"""

import re
import sys

HAS_LETTERS = re.compile(r"[A-Za-z]{2}")
ENTITIES = re.compile(r"&[a-zA-Z]+;")
ATTRS = ("title", "placeholder", "aria-label")


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def esc_js(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def protect(text: str):
    """Replace comments, <code>/<pre> blocks, Angular control-flow headers and
    block closers with tokens; return (text, store)."""
    store = []

    def keep(m):
        store.append(m.group(0))
        return f"\x00{len(store) - 1}\x00"

    text = re.sub(r"<!--.*?-->", keep, text, flags=re.S)
    text = re.sub(r"<(code|pre)\b.*?</\1>", keep, text, flags=re.S | re.I)
    # Interpolation attributes (attr="{{ expr }}") equal bound attributes;
    # rewriting them keeps the tag whole for the later tag matcher.
    text = re.sub(r"([\w-]+)=\"\{\{([^{}]*)\}\}", r'[\1]="\2', text)
    # @if (...) { / @for (...; track x) { / @else { — the header may contain
    # > < && which must never be mistaken for markup.
    text = re.sub(
        r"@(?:else\s+if|if|else|for|empty|switch|case|default|defer|placeholder|loading|error)\b[^{]*\{",
        keep,
        text,
    )
    # Lone closing braces of control-flow blocks.
    text = re.sub(r"^[ \t]*\}[ \t]*$", keep, text, flags=re.M)
    return text, store


def restore(text: str, store) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: store[int(m.group(1))], text)


DISPLAYISH = re.compile(r"^[A-Z]| |[.!?…,;:)]\Z|\(")


def is_display_literal(body: str) -> bool:
    """True for strings a user reads: sentences, labels, capitalized words.

    Material icon names ('check', 'content_copy'), enum-ish values compared
    against ('Device Locked') and pipe args must stay untouched.
    """
    if not HAS_LETTERS.search(body) or len(body) < 2:
        return False
    if "_" in body:  # snake_case: icon names / identifiers
        return False
    if body != body.upper() and body[0].islower() and " " not in body:
        return False  # lone lowercase word: icon or compare operand
    return bool(DISPLAYISH.search(body))


def transform_moustache(seg: str) -> str:
    """Wrap display string literals inside {{ ... }} with ('...' | t)."""
    # Pipe arguments like | date:'shortTime' must not be translated.
    pipe_arg = re.compile(r"(\|\s*[a-zA-Z]+\s*:\s*)(?:'[^']*'|\"[^\"]*\")")

    def protect_pipe_args(s):
        kept = []

        def keep(m):
            kept.append(m.group(0)[len(m.group(1)):])
            return m.group(1) + f"\x01{len(kept) - 1}\x01"

        return pipe_arg.sub(keep, s), kept

    seg, kept = protect_pipe_args(seg)

    lit = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'|\"([^\"\\]*(?:\\.[^\"\\]*)*)\"")

    def wrap(m):
        body = m.group(1) if m.group(1) is not None else m.group(2)
        quote = "'" if m.group(1) is not None else '"'
        before = seg[: m.start()]
        if re.search(r"[=!]==?\s*$", before):  # comparison operand
            return m.group(0)
        if not is_display_literal(body):
            return m.group(0)
        if re.match(r"\s*\|\s*t\b", seg[m.end():]):
            return m.group(0)  # already piped
        return f"({quote}{body}{quote} | t)"

    seg = lit.sub(wrap, seg)
    return re.sub(r"\x01(\d+)\x01", lambda m: kept[int(m.group(1))], seg)


def transform_tag(tag: str) -> str:
    """Convert static title/placeholder/aria-label attrs to bound + piped, and
    translate display literals inside already-bound ones."""

    def conv_static(m):
        name, value = m.group(1), m.group(2)
        if "{{" in value or not HAS_LETTERS.search(ENTITIES.sub("", value)):
            return m.group(0)
        key = collapse_ws(value)
        return f'[{name}]="\'{esc_js(key)}\' | t"'

    def conv_bound(m):
        name, expr = m.group(1), m.group(2)
        inner = transform_moustache(expr)
        return f'[{name}]="{inner}"'

    tag = re.sub(r"\[(%s)\]=\"([^\"]*)\"" % "|".join(ATTRS), conv_bound, tag)
    return re.sub(r"\b(%s)=\"([^\"]*)\"" % "|".join(ATTRS), conv_static, tag)


TOKEN_RE = re.compile(r"\x00\d+\x00")


def _wrap_runs(piece: str) -> str:
    out = []
    pos = 0
    for m in re.finditer(r"\S(?:[^<>{}\x00]*\S)?", piece):
        run = m.group(0)
        stripped = ENTITIES.sub("", run)
        if run.lstrip().startswith(("@", "}")) or not HAS_LETTERS.search(stripped):
            continue
        key = collapse_ws(run)
        if not is_display_literal(key):
            continue  # icon ligatures / lone lowercase words
        out.append(piece[pos:m.start()])
        out.append("{{ '%s' | t }}" % esc_js(key))
        pos = m.end()
    out.append(piece[pos:])
    return "".join(out)


def transform_text(seg: str) -> str:
    """Wrap static text runs with {{ '...' | t }}, leaving tokens alone."""
    rebuilt = []
    pos = 0
    for m in TOKEN_RE.finditer(seg):
        rebuilt.append(_wrap_runs(seg[pos:m.start()]))
        rebuilt.append(m.group(0))
        pos = m.end()
    rebuilt.append(_wrap_runs(seg[pos:]))
    return "".join(rebuilt)


# Quote-aware tag matcher: attribute values may contain > (e.g. ">= 35").
TAG_RE = re.compile(r"<(?:[^>\"']|\"[^\"]*\"|'[^']*')*>")


def process(src: str) -> str:
    src, store = protect(src)
    parts = re.split(r"(\{\{.*?\}\})", src, flags=re.S)
    for i, part in enumerate(parts):
        if part.startswith("{{"):
            parts[i] = transform_moustache(part)
            continue
        sub = TAG_RE.split(part)
        # TAG_RE.split drops matched tags; walk with finditer to keep them.
        rebuilt = []
        pos = 0
        for m in TAG_RE.finditer(part):
            rebuilt.append(transform_text(part[pos:m.start()]))
            rebuilt.append(transform_tag(m.group(0)))
            pos = m.end()
        rebuilt.append(transform_text(part[pos:]))
        parts[i] = "".join(rebuilt)
    return restore("".join(parts), store)


KEY_RE = re.compile(r"'((?:\\.|[^'\\])*)' \| t")


def collect_keys(text: str):
    for m in KEY_RE.finditer(text):
        yield m.group(1).replace("\\'", "'").replace("\\\\", "\\")


def main():
    keys = set()
    for path in sys.argv[1:]:
        with open(path, encoding="utf-8") as f:
            src = f.read()
        out = process(src)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        keys.update(collect_keys(out))
        print(f"processed {path}")
    for key in sorted(keys):
        print("KEY:", key)


if __name__ == "__main__":
    main()
