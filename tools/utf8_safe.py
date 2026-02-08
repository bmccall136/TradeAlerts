from pathlib import Path

def safe_write_utf8(path: Path, text: str) -> None:
    """Write UTF-8 WITHOUT BOM. Refuse to write known encoding-damage markers."""
    # Strict UTF-8 encode (will raise if text contains invalid surrogates)
    raw = text.encode("utf-8", errors="strict")

    # Never write a UTF-8 BOM at file start
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path}: refusing to write UTF-8 BOM")

    # Refuse to write Unicode replacement char (often indicates prior decode damage)
    if "\ufffd" in text:
        raise ValueError(f"{path}: refusing to write replacement char \ufffd (encoding damage)")

    path.write_text(text, encoding="utf-8", newline="\n")
