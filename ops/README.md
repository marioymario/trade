# ops/ — cron boot + heartbeat + risk guard (quick safety layer)

This implements **risk guardrails without modifying trading code**:
- Kill switch: if file exists => stop `paper` and log HALTED
- Daily caps: if exceeded => stop `paper` and log HALTED

This is the fastest “real-trade safety” win because it works even if the bot code is unchanged.

## Risk knobs (set in target .env — operator state)
These are read by ops scripts:

- `KILL_SWITCH_FILE` (default `/tmp/TRADING_STOP`)
- `MAX_TRADES_PER_DAY` (default `0` disables)
- `MAX_DAILY_LOSS_USD` (default `0` disables)
- `TZ_LOCAL` (default `America/Los_Angeles`)

Notes:
- If `KILL_SWITCH_FILE` is under `/tmp`, it may not persist across reboot.
  If you want persistence, set:
  `KILL_SWITCH_FILE=/home/kk7wus/TRADING_STOP`

## What happens on HALT?
- `ops/cron_heartbeat.sh` stops only the `paper` service (`docker compose stop paper`).
  `trade` stays up for debugging.
- `ops/cron_reboot.sh` will **not start** containers when halted by kill switch or limits.

## Logs (target home dir)
- `~/trade_reboot.log`
- `~/trade_heartbeat.log`

## Manual kill switch (target)
To halt immediately:
- `touch /home/kk7wus/TRADING_STOP`
- `docker compose stop paper`

To resume:
- `rm -f /home/kk7wus/TRADING_STOP`
- `docker compose up -d`
