"""Actions that must be confirmed by the user, whatever the script says."""
from __future__ import annotations

import re

SENSITIVE = re.compile(
    r"\b(send\w*|sent|submit\w*|purchas\w*|buy\w*|pay|paid|payment\w*|checkout|check out|place order|order now|"
    r"delet\w*|remov\w*|eras\w*|trash\w*|discard\w*|transfer\w*|wire|publish\w*|post|posted|tweet\w*|"
    r"reply all|unsubscrib\w*|uninstall\w*|empty trash|book now|reserv\w*)\b",
    re.I,
)


def is_sensitive(*texts: str | None) -> bool:
    return any(t and SENSITIVE.search(t) for t in texts)
