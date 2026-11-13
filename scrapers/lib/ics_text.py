"""One rule for escaping and unescaping ICS text values (RFC 5545 §3.3.11).

Every writer and reader imports these: the hand-built scrapers, the combiner
and the JSON export. A copy that drops the bare-CR case emits a line break
inside a property and corrupts the whole feed.
"""

import re

_UNESCAPES = {"\\": "\\", ";": ";", ",": ",", "n": "\n", "N": "\n"}


def escape_ics(text):
    """Escape a text value. CR and CRLF are line breaks, so both become \\n."""
    if not text:
        return ""
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def unescape_ics(text):
    """Reverse escape_ics in one pass, so \\\\n stays a literal backslash + n."""
    if not text:
        return ""
    return re.sub(r"\\([\\;,nN])", lambda m: _UNESCAPES[m.group(1)], text)
