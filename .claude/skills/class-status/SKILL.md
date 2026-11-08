---
id: 6d1f3c2a-8b47-4e0e-9f5a-2c7b1d9e4a10
name: class-status
description: Class status for this lesson. Two modes. `check` runs on a student's machine (sent there as an IT
  message) and answers how far the student got with each task, in the `class_status` shape. `report` runs on the
  teacher's machine and turns the answers of an IT conversation into one clean report page,
  `class-status-report.html`. Use for "check this student's progress", "how is the class doing", "class status
  report".
allowed-tools:
- Read
- Write
- Bash
- Glob
- Grep
---

# class-status

## The lesson's tasks (in order)

| task | done when |
|---|---|
| Build game | a game folder under `games/<name>/` has an `index.html` that loads its own js/css with no missing file |
| Restart button | the game has a working Restart / Play again control that starts a new game |
| Phone layout | the game fits a 390 px wide screen and has touch or tap controls |
| Publish | the game was published: `games/<name>/share-link.json` exists with a link |

## `check` — on a student's machine

You were sent here by the teacher as an IT message. You only READ; never change the student's files, never
start the game builder, never message anyone.

1. Find the student's games: `ls games/*/index.html` from the project folder. No game → every task `not_started`.
2. For the newest game, decide each task from the files, citing the evidence you used:
   - **Build game**: read `index.html`; every local `<script src>` / `<link href>` it names must exist.
   - **Restart button**: a control whose text or id is Restart / Play again / New game, wired to a function that
     resets the game state. Present but throwing or not wired → `stuck`, with the reason in `issue`.
   - **Phone layout**: a `<meta name="viewport">`, sizes based on the screen (`innerWidth`, `vw`, `%`, `min()`), and
     `touchstart`/`pointerdown` handlers. Some but not all → `in_progress`.
   - **Publish**: `share-link.json` with a link → `done`; otherwise `not_started`.
3. If the student's chat is on this machine (the Game Builder session), skim its last turns: a student who asked
   for help and did not get it, or an error they pasted, is `stuck` with that as `issue`.
4. Answer in the `class_status` shape: `tasks` (all four, in order), `needs_help` (true when any task is `stuck`),
   `summary` (two sentences, for the teacher, in English). Write exactly that JSON as your result.

## `report` — on the teacher's machine

Input: an IT conversation (inbox → the IT row → its id, or the one the teacher names).

1. Read it: `flow conversation show <conversation id>`. The first message is the teacher's; every other message is
   one machine's reply. A reply that carries a `returned_value` attachment holds that machine's `class_status`
   value (`flow conversation message <conversation id> <message id>` shows it). A reply without one is a machine
   that did not answer — keep its sentence (IT Sessions off, someone signed in, did not answer).
2. Write `class-status-report.html` (one self-contained page, no libraries, the `html-builder` look):
   - Title "Class status — <lesson>", then when the IT message was sent and how many machines answered.
   - Four counts: answered, all done, stuck, no answer.
   - One row per machine (`••••` + the last 4 of its code): a status pill per task (Done / In progress / Stuck /
     Not started) and a short **Needs** note (the stuck task's `issue`, cut to a few words; the full text in a
     `title` tooltip). Machines with no answer: one muted line with their sentence.
   - Never a wall of text in a cell.
3. Attach it to the same conversation: `flow conversation attach <conversation id> class-status-report.html`, and
   say in one line who needs help.
