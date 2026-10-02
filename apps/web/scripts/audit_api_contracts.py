"""Compare every frontend-declared API response type against what the endpoint actually returns.

Reads `response_signatures.json`, written by `scripts/browser/crawl_all_routes.js`, which records
the real keys of every API response seen while driving each route in a browser — at the top level
and, for single-key envelopes like `{ orders: [...] }`, for the first element as well. Then it
finds the TypeScript type the frontend declares for that same request and diffs the two.

This exists because a declared interface cannot fail a test. `useApi<JournalData>('/ai/journal')`
compiles, lints, and returns 200 at runtime while `JournalData` describes a shape the endpoint has
never returned. Three separate bugs of exactly that kind shipped in this codebase —

    /forward-test  expected ForwardTestItem[]   got { items: [...] }
    /journal       expected JournalData (12)     got { analysis, stats }
    /reports/daily expected { entries, ... }     got { analysis, stats }

— and none was visible to a type checker, a unit test, or a route crawler, because each either
threw only when data was present or rendered a permanently-false branch.

## Two things this tool got wrong first

Both were found by distrusting its own output, and both are worth stating because they are the
failure modes any version of this tool has to avoid.

**Extracting a named type's fields with a regex.** The first version used

    (?:interface|type)\\s+NAME\\s*(?:=|\\{)(?P<body>[^{]*\\{)?(?P<fields>.*?)\\n\\}

`[^{]` matches `}`, so the greedy `[^{]*\\{` ran forward past the end of one interface and consumed
the *next* declaration's header, and the lazy field group then captured the wrong interface
entirely. `Alert` resolved to `JournalNote`'s fields; `JournalResponse` resolved to `EngineOrder`'s.
Every finding was fabricated. Types are now extracted by **brace matching**, which cannot cross a
declaration boundary.

**Comparing an item type against envelope keys.** `/forward-tests` answers `{ items: [...] }` and
the frontend declares `ForwardTestItem` — the item, not the envelope — so every field looked
missing. The crawler now records the contained element's keys, and the audit picks the level the
declaration actually describes.

Where a type cannot be resolved with confidence the tool says so and skips the endpoint rather
than guessing. A contract audit that invents findings is worse than none: it gets ignored.

Reads only. No endpoint is called and nothing is written.

    node scripts/browser/crawl_all_routes.js --out /tmp/contract_audit
    python3 scripts/audit_api_contracts.py --signatures /tmp/contract_audit/response_signatures.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# scripts/audit_api_contracts.py -> scripts -> apps/web
WEB_ROOT = Path(__file__).resolve().parents[1]

_SCAN: list[Path] | None = None


def scan_files() -> list[Path]:
    """Every file a declared API type could live in, plus every file that can declare one.

    Two different sets, because a contract has two ends. The *requesting* files are `lib/api.ts` and
    the page tree, since that is where `request<T>` and `useApi<T>` are written. The *declaring*
    files are wider — anything under `lib/` can export a shared type, and `lib/journal.ts` is
    exactly that case: `/journal` and `/reports/daily` both declare `JournalResponse` against it,
    so a resolver that only looked in `lib/api.ts` called it unresolvable and skipped it.
    """
    global _SCAN
    if _SCAN is None:
        # Deduplicated: listing `lib/api.ts` explicitly *and* globbing `lib/*.ts` would scan it
        # twice and report every type declared there twice.
        files: list[Path] = [*(WEB_ROOT / "lib").glob("*.ts"), *sorted((WEB_ROOT / "app").rglob("*.tsx"))]
        seen: set[Path] = set()
        _SCAN = [f for f in files if not (f in seen or seen.add(f))]
    return _SCAN


CALL_RE = re.compile(r"(?:useApi|request)\s*<")
QUOTED_PATH_RE = re.compile(r"""[\'\"`](?P<path>/[^\'\"`]*)[\'\"`]""")

# Only ever used for the *last* segment of a name, so it cannot swallow a prefix.
#
# The optional marker is part of the pattern, not stripped afterwards. An interface field written
# `analysis?: string` has a `?` between the name and the colon, so without this the field is not
# recognised at all — and since optional fields are exactly the ones an endpoint is most likely to
# omit, dropping them turns every optional field into a fabricated "NOT present" finding. That is
# how `JournalResponse` came back resolving to an empty field set.
IDENT_END_RE = re.compile(r"([A-Za-z_]\w*)\s*\??\s*$")


def normalise(path: str) -> str:
    p = path.split("?", 1)[0]
    for prefix in ("/api/v1", "/api"):
        if p.startswith(prefix):
            p = p[len(prefix):] or "/"
            break
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "/"


def find_declarations(text: str) -> list[tuple[str, str, int]]:
    """`[(declared type, request path, offset)]` for every typed call in `text`.

    Hand-scanned rather than regex-matched, because the type cannot be delimited by a pattern.
    A regex over the type runs into two separate failures:

      - `.*?` with DOTALL happily spans statements, so `request<{ is_active: boolean }>` on one
        line gets matched against a path several lines later whenever the argument is a template
        literal rather than a quoted string. That produced declarations whose "type" contained
        three unrelated statements.
      - a generic type contains `<` and `>` of its own (`Record<string, Foo>`), so the closing
        delimiter is not the first `>`.

    So the angle brackets are depth-matched, and only then is the path read.
    """
    out: list[tuple[str, str, int]] = []
    for m in CALL_RE.finditer(text):
        depth = 0
        i = m.end() - 1  # the `<` itself
        type_start = i + 1
        while i < len(text):
            ch = text[i]
            if ch == "<":
                depth += 1
            elif ch == ">":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        else:
            continue
        if i >= len(text):
            continue
        declared = text[type_start:i].strip()
        if not declared or "=>" in declared or "\n" in declared:
            # Not a type argument in the sense we care about — a malformed call or a generic
            # whose body is a function type. Skipping is correct: those are not response types.
            continue
        tail = text[i + 1 :]
        open_paren = tail.find("(")
        if open_paren < 0 or open_paren > 400:
            continue
        pm = QUOTED_PATH_RE.match(tail[open_paren + 1 :].lstrip())
        if not pm:
            continue
        out.append((declared, pm.group("path"), m.start()))
    return out


def mask_comments(text: str) -> str:
    """Blank out comments, preserving every offset.

    The scanner needs this because a TypeScript file is full of prose: an apostrophe inside a
    `/** ... */` block is indistinguishable from the start of a string literal to a naive
    character walk, and consuming until the *next* quote swallows real code — the closing brace of
    the very type being resolved. That is why `JournalResponse` came back unresolvable while its
    declaration sat in `lib/journal.ts` in plain sight: the prose around it said "the model's
    parsed output" and "provider's", and both ended a string early.

    Same length as the input, so indices from one are valid in the other.
    """
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            out[i] = out[i + 1] = " "
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                if text[i] != "\n":
                    out[i] = " "
                i += 1
            if i < n:
                out[i] = " "
                if i + 1 < n:
                    out[i + 1] = " "
                i += 2
        else:
            i += 1
    return "".join(out)


def matching_brace(text: str, open_at: int) -> int:
    """Index of the `}` matching the `{` at `open_at`, or -1.

    Comments are masked first and string literals are skipped, so neither prose containing an
    apostrophe nor a brace inside a default value can terminate a type early.
    """
    masked = mask_comments(text)
    depth = 0
    i = open_at
    n = len(masked)
    while i < n:
        ch = masked[i]
        if ch in "\"'`":
            quote = ch
            i += 1
            while i < n and masked[i] != quote:
                i += 2 if masked[i] == "\\" else 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def top_level_fields(body: str) -> set[str]:
    """Field names declared at brace depth 0 within `body`.

    Depth is tracked across `{[(`, so an inline nested type contributes its parent name only —
    which is what an envelope type like `{ orders: Order[] }` should report.
    """
    out: set[str] = set()
    depth = 0
    for i, ch in enumerate(body):
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif ch == ":" and depth == 0:
            m = IDENT_END_RE.search(body[:i])
            if m:
                out.add(m.group(1))
    return out


def declared_kind_and_fields(raw: str) -> tuple[str, set[str] | None]:
    """`('inline'|'array'|'named'|'unknown', fields or None)` for a declared response type."""
    t = raw.strip()
    if not t:
        return "unknown", None
    if t.endswith("[]"):
        return "array", None
    if t.startswith("{") or t.startswith("Readonly<{"):
        open_at = t.index("{")
        close = matching_brace(t, open_at)
        if close < 0:
            return "unknown", None
        return "inline", top_level_fields(t[open_at + 1:close])
    if re.fullmatch(r"[A-Za-z_]\w*", t):
        return "named", None
    return "unknown", None


# Deliberately uncompiled: the type name is substituted in, and a compiled pattern has no
# `.format`. Both spellings are checked because the codebase uses each.
TYPE_DECL_RES = {
    "interface": r"(?:export\s+)?interface\s+{name}\b",
    "type": r"(?:export\s+)?type\s+{name}\s*=",
}


def resolve_named_type(name: str) -> tuple[str, set[str] | None]:
    """`('inline'|'array'|'unknown', fields or None)` for a named type.

    Reports `unknown` when the name is declared more than once across the repo. An ambiguous name
    cannot be resolved to *a* body, and picking the first is how the previous version fabricated
    its entire report.
    """
    hits: list[tuple[str, set[str] | None]] = []
    for f in scan_files():
        text = f.read_text()
        for kind, tmpl in TYPE_DECL_RES.items():
            for m in re.compile(tmpl.format(name=re.escape(name))).finditer(text):
                open_at = text.find("{", m.end())
                # A generic parameter list sits between the name and the body: `Foo<T = ...> {`.
                if open_at < 0:
                    hits.append(("unknown", None))
                    continue
                close = matching_brace(text, open_at)
                if close < 0:
                    hits.append(("unknown", None))
                    continue
                body = text[open_at + 1:close].strip()
                if body.startswith("Array<") or body.startswith("Promise<"):
                    hits.append(("array", None))
                elif kind == "type" and body.rstrip().endswith("[]"):
                    hits.append(("array", None))
                else:
                    # "inline", not "fields": the resolved named type is described in the same
                    # vocabulary as a literal one. Returning a third kind name here meant every
                    # successfully-resolved named type failed the `kind != "inline"` check below
                    # and was reported as unresolved, so the audit silently skipped exactly the
                    # declarations it exists to check.
                    hits.append(("inline", top_level_fields(body)))
    if not hits:
        return "unknown", None
    if len(hits) > 1:
        # Same body twice (e.g. re-exported) is fine; different bodies are ambiguous.
        distinct = {(k, tuple(sorted(v or ()))) for k, v in hits}
        if len(distinct) > 1:
            return "unknown", None
    return hits[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--signatures", default="/tmp/contract_audit/response_signatures.json")
    args = ap.parse_args()

    sig_path = Path(args.signatures)
    if not sig_path.exists():
        print(f"no signature file at {sig_path}")
        print("run: node scripts/browser/crawl_all_routes.js --out /tmp/contract_audit")
        return 2

    # `itemKeys` stays None when the endpoint returned no elements at all, which is different from
    # an empty element object. Comparing a declared type against an empty set reports every field
    # as missing, so an endpoint the test user happens to have no data for — `/alerts`,
    # `/forward-tests` — produced a full page of fabricated findings. Absence of data has to be
    # reported as "not auditable", never as a mismatch.
    observed: dict[str, dict] = {}
    for sigs in json.loads(sig_path.read_text()).values():
        for s in sigs:
            key = normalise(s["path"])
            entry = observed.setdefault(key, {"keys": set(), "itemKeys": set(), "itemAvailable": False})
            entry["keys"].update(s.get("keys") or [])
            if s.get("itemKeys"):
                entry["itemKeys"].update(s["itemKeys"])
                entry["itemAvailable"] = True

    declarations: dict[str, list[tuple[Path, int, str]]] = {}
    for f in scan_files():
        text = f.read_text()
        for declared, path, offset in find_declarations(text):
            line = text[:offset].count("\n") + 1
            declarations.setdefault(normalise(path), []).append((f, line, declared))

    audited = findings = 0
    missing_total = 0
    unresolved: list[str] = []
    no_data: list[str] = []
    report: list[str] = []

    for path in sorted(observed):
        real_top = observed[path]["keys"]
        real_item = observed[path]["itemKeys"]
        for f, line, raw in declarations.get(path, []):
            kind, fields = declared_kind_and_fields(raw)
            if kind == "array":
                # A bare-array declaration: the endpoint answers a single-key envelope, so the
                # declaration has to name the envelope key to be usable. That mismatch is itself
                # the finding, and it is the one that crashed `/forward-test`.
                if len(real_top) == 1:
                    only = next(iter(real_top))
                    audited += 1
                    findings += 1
                    missing_total += 1
                    report.append(
                        f"MISMATCH  {path}\n"
                        f"  declared at : {f.relative_to(WEB_ROOT)}:{line}\n"
                        f"  as          : {raw.strip()}\n"
                        f"  actual      : {{ {only}: ... }} — a single-key envelope, not an array\n"
                        f"  impact      : the array methods are undefined, so `.map`/`.filter` throw\n"
                    )
                continue
            if kind == "named":
                kind2, fields = resolve_named_type(raw.strip())
                if kind2 == "unknown" or fields is None:
                    unresolved.append(f"{path}  ({raw.strip()} at {f.relative_to(WEB_ROOT)}:{line})")
                    continue
                kind, fields = kind2, fields
            if kind != "inline" or fields is None:
                unresolved.append(f"{path}  ({raw.strip()} at {f.relative_to(WEB_ROOT)}:{line})")
                continue

            audited += 1
            # Choose the comparison level from the declaration. An envelope type names its own key,
            # so it describes the top level; a type that does not name any observed key is
            # describing the element of the single-key envelope.
            names_top = bool(fields & real_top)
            if not names_top and len(real_top) == 1:
                if not observed[path]["itemAvailable"]:
                    no_data.append(
                        f"{path}  ({raw.strip()} at {f.relative_to(WEB_ROOT)}:{line})"
                        " — endpoint returned no rows, so the element shape is unverifiable"
                    )
                    continue
                target = real_item
            else:
                target = real_top
            missing = {d.rstrip("?") for d in fields if d.rstrip("?") not in target}
            if not missing:
                continue
            findings += 1
            missing_total += len(missing)
            extra = sorted(target - fields)
            level = "envelope" if names_top else "envelope element"
            report.append(
                f"MISMATCH  {path}\n"
                f"  declared at : {f.relative_to(WEB_ROOT)}:{line}\n"
                f"  as          : {raw.strip()}\n"
                f"  compared to : the {level} ({len(target)} keys)\n"
                f"  NOT present : {', '.join(sorted(missing))}\n"
                + (f"  present but undeclared: {', '.join(extra)}\n" if extra else "")
            )

    print(f"endpoints observed        : {len(observed)}")
    print(f"declarations compared     : {audited}")
    print(f"declarations unresolved   : {len(unresolved)}  (named type not resolvable, skipped)")
    print(f"not auditable, no rows    : {len(no_data)}  (endpoint returned an empty list)")
    print(f"mismatching declarations  : {findings}")
    print(f"fields read but not served: {missing_total}\n")

    if report:
        print("\n".join(report))
    if unresolved:
        print("could not resolve, so not audited:")
        for u in unresolved:
            print(f"  {u}")
    if no_data:
        print("returned no rows, so the element shape could not be compared:")
        for u in no_data:
            print(f"  {u}")
    print()

    if not findings:
        print("no mismatches: every resolvable typed field is present in the observed response")
        return 0
    print(f"{findings} declaration(s) read at least one field the endpoint does not return.")
    print("\nEach is a place the page renders `undefined` or `NaN`, or takes a permanently-false")
    print("branch. A `?? 0` in the middle turns that into a confident zero, which is worse than an")
    print("error: it tells the user their profit is nothing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())