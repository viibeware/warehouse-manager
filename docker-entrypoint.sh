#!/bin/sh
# Start as root only long enough to make the data volume writable by the
# unprivileged app user, then drop privileges for the actual server process.
#
# Existing installs have /data owned by root, from back when the container ran
# everything as root — so a bare `USER wm` in the Dockerfile would leave those
# deployments unable to write their own database on upgrade. The chown below
# runs once, only when the ownership is actually wrong.
set -e

if [ "$(id -u)" = "0" ]; then
    mkdir -p /data/uploads/temp
    if [ "$(stat -c %u /data)" != "$(id -u wm)" ]; then
        echo "  → Taking ownership of /data for the unprivileged app user (one-time)"
        chown -R wm:wm /data
    fi
    exec gosu wm "$@"
fi

# Already unprivileged (e.g. `docker run --user`): run as-is.
exec "$@"
