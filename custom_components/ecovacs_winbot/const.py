"""Constants for the Ecovacs Winbot integration."""

from datetime import timedelta

DOMAIN = "ecovacs_winbot"

# While idle and awake: connect, ask getInfo, disconnect, wait this long.
IDLE_CHECK_INTERVAL = timedelta(minutes=2)
# While cleaning (connected): backup poll in case a push is missed.
ACTIVE_POLL_INTERVAL = timedelta(seconds=60)
# Stay connected this long after the robot goes idle, then let go so the app can connect.
IDLE_DISCONNECT_DELAY = 15.0
# Seconds without an advertisement before HA considers the robot off.
FALLBACK_AVAILABILITY_SECONDS = 120

EVENT_FINISHED = "finished"
EVENT_INTERRUPTED = "interrupted"
