#!/usr/bin/env bash
# Keep-warm pinger for the four RapidAPI competitor services on Render free tier.
# Render grants 750 free instance hours per WORKSPACE per month (shared).
# Four always-on services would burn ~2,976h and get ALL services suspended,
# so pings run only inside a daily window: 09:00-14:00 America/New_York.
# Window math: 5h x 4 services x 31 days = 620h worst month, ~130h headroom
# for organic traffic. A spun-down service consumes no hours.
# (Window shrank from 09:00-16:00 when the fourth service, geobase-cities,
# was added 2026-10-28.)
# Usage: keepwarm.sh [--force]   (--force ignores the window, for manual tests)
set -u
LOG="$(dirname "$0")/keepwarm.log"
URLS="https://stablefx-currency-rates.onrender.com/health https://cleanlist-email-verifier.onrender.com/health https://edgar-fundamentals.onrender.com/health https://geobase-cities.onrender.com/health"

if [ "${1:-}" != "--force" ]; then
  HOUR=$(TZ=America/New_York date +%H)
  HOUR=$((10#$HOUR))
  if [ "$HOUR" -lt 9 ] || [ "$HOUR" -ge 14 ]; then
    exit 0
  fi
fi

LINE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
for u in $URLS; do
  CODE=$(curl -s -o /dev/null -w '%{http_code}:%{time_total}' -m 90 "$u" || echo "ERR:0")
  LINE="$LINE $u=$CODE"
done
echo "$LINE" >> "$LOG"
# keep the log bounded
tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
