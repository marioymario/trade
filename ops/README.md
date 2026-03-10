# ops/README.md — operator control plane and safety layer

Date: 2026-03-10

Purpose:
This document explains the role of the ops/ layer in MJÖLNIR.

The ops layer is the operational control plane around the trading runtime.
It helps with deploy, restart, reboot behavior, heartbeat checks, kill/halt handling,
and other operator-facing safety actions.

Important:
ops/ is not the entire safety model.

Safety exists in multiple layers:
- code/runtime guardrails
- GuardedBroker / submit-boundary enforcement
- decision/trade observability
- file-based operator controls
- ops heartbeat / reboot / watchdog behavior

ops/ provides an additional operational safety layer around the runtime.


--------------------------------------------------
1) WHAT OPS/ IS FOR
--------------------------------------------------

ops/ exists to support safe, repeatable operation of the system.

Main jobs:
- deploy local repo changes to old-box
- support restart/recreate workflows
- provide operator-facing safety controls
- support reboot/heartbeat behavior
- reduce operational error
- make routine operator actions more reproducible

ops/ should help make the system more boring to run.


--------------------------------------------------
2) CURRENT OPERATOR CONTROL PLANE
--------------------------------------------------

The runtime flag/control directory on old-box is:

/home/kk7wus/trade_flags

Important files:
- STOP
- HALT
- ARM
- status.txt

Meaning:
- STOP = strongest stop condition
- HALT = block entries
- ARM = allow entries when present

These are file-based controls.
They are intended to affect runtime behavior without needing code edits.

General current model:
- flag files are runtime/operator state
- they are not repo truth
- they should not be overwritten by deploy


--------------------------------------------------
3) DEPLOY MODEL
--------------------------------------------------

Canonical deploy command from local:

cd ~/Projects/trade
OLD_BOX_HOST=kk7wus@old-box OLD_BOX_DIR=/home/kk7wus/Projects/trade ./ops/deploy_oldbox.sh

Deploy contract:
- rsync-based
- no delete
- local code truth ships to old-box
- runtime-only state must not ship:
  - .env
  - data/
  - trade_flags/

Deploy is for code truth.
Deploy is not for changing runtime-owned operator state.


--------------------------------------------------
4) RESTART / RECREATE RULES
--------------------------------------------------

Current runtime truth:
- paper bind-mounts ./files into /work/files
- paper bind-mounts ./data into /work/data
- working_dir is /work

Operational rule:
- code change in bind-mounted files -> restart paper
- env / compose runtime change -> recreate paper
- flag-file change -> no restart needed

Canonical commands on old-box:

Restart paper:
docker compose restart paper

Recreate paper:
docker compose up -d --build --force-recreate paper

Important:
Always prefer the smallest correct action.
Do not rebuild/recreate when restart is enough.


--------------------------------------------------
5) HEARTBEAT / REBOOT / RISK-GUARD LAYER
--------------------------------------------------

ops/ contains logic related to the quick operational safety layer around the runtime.

Historical purpose:
- provide fast risk guardrails without requiring strategy-code changes

This includes behavior such as:
- kill-switch handling
- reboot/startup gating
- heartbeat-style checks
- daily cap checks
- stopping paper while leaving other services available for debugging

This layer is still useful, but it now sits alongside stronger in-code/runtime guardrails.

So the right framing today is:
ops risk guard is an additional safety layer, not the only one.


--------------------------------------------------
6) RISK KNOBS / OPERATOR STATE
--------------------------------------------------

These may be read by ops scripts from runtime env / operator state:

- KILL_SWITCH_FILE
- MAX_TRADES_PER_DAY
- MAX_DAILY_LOSS_USD
- TZ_LOCAL

Typical meaning:
- KILL_SWITCH_FILE = file whose presence forces stop/halt behavior
- MAX_TRADES_PER_DAY = optional daily cap
- MAX_DAILY_LOSS_USD = optional daily loss cap
- TZ_LOCAL = local timezone for day-boundary logic

Notes:
- if KILL_SWITCH_FILE is placed under /tmp, it may not survive reboot
- for persistence, use a path under /home/kk7wus or trade_flags


--------------------------------------------------
7) WHAT HAPPENS ON HALT / STOP
--------------------------------------------------

Current operational intent:
- STOP is the strongest stop condition
- paper should not continue opening exposure when stop/halt conditions are active
- trade/debug tooling may remain available even when paper is halted

Historical ops behavior included:
- stopping only the paper service
- leaving trade up for debugging
- preventing reboot scripts from starting runtime when halted by kill switch or limits

That remains a useful operational pattern:
halt runtime execution while preserving debugging access.


--------------------------------------------------
8) LOGS
--------------------------------------------------

Common ops-related logs historically include:

- ~/trade_reboot.log
- ~/trade_heartbeat.log

Current runtime/service logs are also important:

On old-box:
docker compose logs --tail=60 paper
docker compose logs --tail=60 trade
docker compose logs --tail=60 dashboard

Compose/service status:
docker compose ps

Use runtime logs plus decisions/trades truth together.
Logs alone are not enough for strategy-policy proof.


--------------------------------------------------
9) MANUAL OPERATOR ACTIONS
--------------------------------------------------

Typical manual actions on old-box:

Check flags:
ls -l ~/trade_flags

Create a persistent kill/stop file:
touch /home/kk7wus/TRADING_STOP

Remove it:
rm -f /home/kk7wus/TRADING_STOP

Stop paper:
docker compose stop paper

Start/restart paper:
docker compose restart paper

Bring services up:
docker compose up -d

Important:
prefer explicit operator actions over vague assumptions.
Always verify runtime truth after an important intervention.


--------------------------------------------------
10) RELATION TO MISSION SCRIPTS
--------------------------------------------------

ops/ now contains more than one kind of script.

There are two broad categories:

1. operational control scripts
   - deploy
   - reboot / heartbeat / safety helpers
   - runtime control helpers

2. mission-scoped proof scripts
   - scripts tied to one proof target
   - small read-only verification helpers
   - explicit PASS / PENDING / FAIL

Mission-script documentation lives in:
ops/README_missions.md

Keep these categories conceptually separate.


--------------------------------------------------
11) RULES FOR OPS CHANGES
--------------------------------------------------

When working in ops/:

- prefer small changes
- prefer explicit behavior
- do not hide important assumptions
- do not casually mutate runtime state
- verify old-box truth after changes
- avoid mixing deploy logic, strategy logic, and proof logic into one script
- update docs when recurring workflows stabilize

ops/ should improve clarity, not add mystery.


--------------------------------------------------
12) CURRENT OPERATIONAL LESSONS
--------------------------------------------------

Key lessons already learned:

- never assume local runtime state matches old-box state
- inspect compose truth before deciding restart vs recreate
- use decisions.csv as primary runtime proof for strategy-policy questions
- file truth and runtime truth both matter
- repeatable proof commands are worth promoting into mission scripts
- avoid contaminating a clean runtime baseline with unrelated changes

These lessons should guide how ops/ evolves.


--------------------------------------------------
13) BOTTOM LINE
--------------------------------------------------

ops/ is the practical operator layer around MJÖLNIR.

It helps with:
- deploy
- restart discipline
- control-plane behavior
- quick safety controls
- operational boringness

It should stay:
- simple
- explicit
- documented
- reproducible

If something in ops/ becomes important and repeatable, document it.
If something becomes mission-specific, move that explanation to README_missions.md.
