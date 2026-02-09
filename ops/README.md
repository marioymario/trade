# ops/ — target runtime automation (cron + health)

Repo-safe scripts. Keep *logic* in repo, keep *operator state* local.

## Allowed target-only differences (operator state)
- `.env` (DATA_TAG/SYMBOL/TIMEFRAME/DRY_RUN/JUPYTER_BIND_ADDR) — NOT committed
- `data/` runtime contents — NOT committed
- crontab installation — NOT committed
- firewall / host settings — not in repo

## Files
- `ops/cron_reboot.sh`: GPU-first compose start with verification + CPU fallback. Logs to `~/trade_reboot.log`.
- `ops/cron_heartbeat.sh`: periodic proof of life. Logs to `~/trade_heartbeat.log`.
- `ops/crontab.example`: template crontab lines for target.
