#!/usr/bin/env bash
# Keep-warm pinger for the six RapidAPI competitor services on Render free tier.
# Render grants 750 free instance hours per WORKSPACE per month (shared).
# Six always-on services would burn ~4,464h and get ALL services suspended,
# so pings run only inside a daily window: 09:00-12:00 America/New_York.
# Window math: 3h x 6 services x 31 days = 558h worst month, ~190h headroom
# for organic traffic. A spun-down service consumes no hours.
# (Window history: 09:00-16:00 for three services, 09:00-14:00 for four,
# 09:00-13:00 for five, 09:00-12:00 for six, all set 2026-10-28.)
# Usage: keepwarm.sh [--force]   (--force ignores the window, for manual tests)
set -u
LOG="$(dirname "$0")/keepwarm.log"
URLS="https://stablefx-currency-rates.onrender.com/health https://cleanlist-email-verifier.onrender.com/health https://edgar-fundamentals.onrender.com/health https://geobase-cities.onrender.com/health https://cleanextract-articles.onrender.com/health https://swiftrewrite.onrender.com/health"

if [ "${1:-}" != "--force" ]; then
  HOUR=$(TZ=America/New_York date +%H)
  HOUR=$((10#$HOUR))
  if [ "$HOUR" -lt 9 ] || [ "$HOUR" -ge 12 ]; then
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
