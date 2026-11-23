"""Winbot model names, looked up by the robot's model id.

The robot reports a model id (`MID` in getInfo, and the middle part of its
advertised name `WINBOT_<mid>_<nnnn>`). It's Ecovacs's product class id: a random
code per product and sales region, so the same robot has several. The names below
come from Ecovacs's product catalog, as saved in the ecovacs-deebot.js project
(library/productIotMap.json, 2026-11-22). Only b7oysg has been seen on a real
robot so far. New models need a new line here.
"""

from __future__ import annotations

import re

MODEL_NAMES: dict[str, str] = {
    "uh38qp": "Glassbot W1 Pro",
    "2pj946": "Winbot 920",
    "yu7oqr": "Winbot 920",
    "zr4mqt": "Winbot Lite",
    "05uq5v": "Winbot Mini",
    "6q6ctd": "Winbot Mini",
    "crso4a": "Winbot Mini",
    "ng8bmy": "Winbot Mini",
    "p4ol9u": "Winbot Mini",
    "zbsb7p": "Winbot Mini 2",
    "988he2": "Winbot Neo",
    "ti6dec": "Winbot Neo Mini",
    "19xe25": "Winbot W1 Pro",
    "4xq430": "Winbot W1 Pro",
    "62uooe": "Winbot W1 Pro",
    "gcmyi7": "Winbot W1 Pro",
    "63y3bt": "Winbot W1s",
    "g83vm7": "Winbot W1s",
    "ru2qdd": "Winbot W1s",
    "xjkrto": "Winbot W1s",
    "yephu9": "Winbot W2",
    "81gpyd": "Winbot W2 Omni",
    "ind025": "Winbot W2 Omni",
    "83bpgj": "Winbot W2 Pro",
    "9x9pbo": "Winbot W2 Pro",
    "28ds68": "Winbot W2 Pro Omni",
    "2nps8i": "Winbot W2 Pro Omni",
    "b7oysg": "Winbot W2 Pro Omni",
    "y3z7xf": "Winbot W2 Pro Omni",
    "zqswe5": "Winbot W2 Pro Omni 7-11",
    "780627": "Winbot W2s",
    "v50csw": "Winbot W2s Omni",
    "99iw23": "Winbot W3 Omni",
}

_ADVERTISED_NAME = re.compile(r"^WINBOT_([0-9a-z]+)_")


def model_name(model_id: str | None) -> str | None:
    """Return the model name for a model id, or None if it isn't known."""
    return MODEL_NAMES.get(model_id) if model_id else None


def model_id_from_name(name: str | None) -> str | None:
    """Return the model id in an advertised name like WINBOT_<mid>_<nnnn>."""
    if name and (match := _ADVERTISED_NAME.match(name)):
        return match.group(1)
    return None
