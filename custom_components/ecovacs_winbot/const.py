"""Constants for the Ecovacs Winbot integration."""

from datetime import timedelta
from enum import StrEnum

DOMAIN = "ecovacs_winbot"

# While idle and on: backup getInfo (and reconnect if the connection dropped).
IDLE_CHECK_INTERVAL = timedelta(minutes=2)
# After this long without cleaning, a button press or a command (and not
# charging, when the robot stays on anyway), HA disconnects
# and stops checking, so the robot can switch itself off.
IDLE_RELEASE_AFTER = timedelta(minutes=15)
# While cleaning (connected): backup poll in case a push is missed.
ACTIVE_POLL_INTERVAL = timedelta(seconds=60)
# Seconds without an advertisement before HA considers the robot off.
FALLBACK_AVAILABILITY_SECONDS = 120

# What the robot reports as the cause of a state change (`trigger`). New ones are logged for reporting.
TRIGGERS = ["button", "app", "workComplete"]

EVENT_FINISHED = "finished"
EVENT_RETURNED = "returned"
EVENT_INTERRUPTED = "interrupted"
EVENT_ERROR = "error"
EVENT_STARTED = "started"
EVENT_OUT_OF_WATER = "out_of_water"
EVENT_BUMPED = "bumped"

# Remote control. The remote entity's commands are directions on the window, in the angles
# wheelMove takes (docs/protocol.md). The robot stops by itself about a second after the last
# wheelMove, so a drive is capped rather than left running.
REMOTE_COMMANDS = {"up": 360, "right": 90, "down": 180, "left": 270}
DEFAULT_SPEED = 2  # what the app sends
MAX_DRIVE_SECONDS = 10


class WinbotService(StrEnum):
    """Actions this integration registers."""

    DRIVE = "drive"


class WinbotServiceArgument(StrEnum):
    """Fields of this integration's actions."""

    ANGLE = "angle"
    SPEED = "speed"
    DURATION = "duration"
