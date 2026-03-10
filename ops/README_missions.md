# ops/README_missions.md — mission-scoped proof scripts

Date: 2026-03-10

Purpose:
This document explains the role of mission-scoped scripts in ops/.

Mission scripts are small, repeatable helpers used to prove or inspect
mission-specific runtime truth.

They are part of the project’s proof discipline.

They are NOT a replacement for:
- canonical docs
- active handoffs
- general ops/control-plane docs

For general ops/control-plane behavior:
- see ops/README.md

For current project truth:
- see docs/CANONICAL_CURRENT_STATE.md

For current mission:
- see HANDOFF.md


--------------------------------------------------
1) WHAT A MISSION SCRIPT IS
--------------------------------------------------

A mission script is a script tied to one specific mission or proof target.

It should answer a narrow question such as:
- did the intended runtime behavior actually appear?
- is the proof condition now true?
- what is the current mission-specific snapshot?

Mission scripts exist to reduce operator error, improve reproducibility,
and make PASS / PENDING / FAIL outcomes explicit.


--------------------------------------------------
2) WHEN TO CREATE ONE
--------------------------------------------------

A command sequence should become a mission script only if it is:

- repeated or likely to repeat
- tied clearly to one mission
- operationally important
- stable enough to trust
- improved by explicit PASS / PENDING / FAIL output

Do not create mission scripts for every one-off command.


--------------------------------------------------
3) WHAT A GOOD MISSION SCRIPT LOOKS LIKE
--------------------------------------------------

A good mission script is:

- small
- readable
- narrow in scope
- mostly read-only
- explicit about inputs
- explicit about what it proves
- explicit about what it does NOT prove
- explicit about PASS / PENDING / FAIL

Preferred behavior:
- print what mission it belongs to
- print what file(s) or data it reads
- print the scope/cutoff if relevant
- end with a clear status


--------------------------------------------------
4) WHAT TO AVOID
--------------------------------------------------

Do not let mission scripts become:

- junk-drawer automation
- multi-mission bundles
- hidden mutation tools
- vague scripts with unclear meaning
- scripts that silently assume too much

Avoid scripts that both:
- change runtime state
- and claim to prove something

Prefer proof scripts to be read-only whenever possible.


--------------------------------------------------
5) CURRENT MISSION SCRIPT(S)
--------------------------------------------------

ops/mission5b1_short_quarantine_check.sh

Mission:
- Mission 5B.1

Purpose:
- prove that SHORT quarantine is live in runtime truth

How it works:
- reads decisions.csv after a supplied cutoff timestamp
- finds post-cutoff SHORT-related rows
- reports PASS / PENDING / FAIL

PASS means:
- explicit SHORT-disabled runtime evidence was found

PENDING means:
- no decisive post-cutoff SHORT-related evidence yet

FAIL means:
- live SHORT entry permission was still observed after cutoff


--------------------------------------------------
6) CURRENT CONVENTIONS
--------------------------------------------------

Naming:
- mission<number><substep>_<purpose>.sh
Examples:
- mission5b1_short_quarantine_check.sh
- mission5b2_long_only_snapshot.sh

Style:
- mission header in comments
- short explanation of what the script proves
- usage example
- clear exit codes where helpful
- read-only by default

Output style:
- PASS
- PENDING
- FAIL


--------------------------------------------------
7) FUTURE DIRECTION
--------------------------------------------------

Possible future additions:
- mission-scoped snapshot scripts
- optional watch mode for selected proof scripts
- optional terminal bell / noise when target condition appears
- small family of reusable proof helpers

Important:
These should be added selectively.
Do not build a large script framework before the need is real.


--------------------------------------------------
8) RULE OF USE
--------------------------------------------------

A mission is not done because it feels done.

A mission is done when file truth and runtime truth both support the conclusion.

Mission scripts help verify runtime truth in a repeatable way.
