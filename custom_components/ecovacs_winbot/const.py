"""Constants for the Ecovacs Winbot integration."""

from datetime import timedelta

DOMAIN = "ecovacs_winbot"

# While idle and on: backup getInfo (and reconnect if the connection dropped).
IDLE_CHECK_INTERVAL = timedelta(minutes=2)
# While cleaning (connected): backup poll in case a push is missed.
ACTIVE_POLL_INTERVAL = timedelta(seconds=60)
# Seconds without an advertisement before HA considers the robot off.
FALLBACK_AVAILABILITY_SECONDS = 120

EVENT_FINISHED = "finished"
EVENT_RETURNED = "returned"
EVENT_INTERRUPTED = "interrupted"
EVENT_ERROR = "error"
