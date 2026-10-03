"""Remove comments from Kotlin/Java/Gradle sources (strings are kept: some rules look at string literals).

Line numbers are preserved: every removed character becomes a space, newlines stay.
"""
from __future__ import annotations


def strip_comments(src: str, nested: bool = True) -> str:
    """nested=True for Kotlin (block comments nest); Java and Groovy do not nest, and banners like /*////*/ are common there."""
    out: list[str] = []
    i, n = 0, len(src)

    def blank(s: str) -> str:
        return "".join(c if c == "\n" else " " for c in s)

    while i < n:
        c = src[i]
        two = src[i:i + 2]
        if two == "//":
            j = src.find("\n", i)
            j = n if j == -1 else j
            out.append(blank(src[i:j]))
            i = j
        elif two == "/*":
            depth, j = 1, i + 2
            while j < n and depth:  # Kotlin nests block comments; Java does not, but real Java never relies on that
                if nested and src.startswith("/*", j):
                    depth += 1
                    j += 2
                elif src.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            out.append(blank(src[i:j]))
            i = j
        elif src.startswith('"""', i):
            j = src.find('"""', i + 3)
            j = n if j == -1 else j + 3
            out.append(src[i:j])
            i = j
        elif c == '"' or c == "'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(src[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)
