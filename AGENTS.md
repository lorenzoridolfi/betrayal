# AGENTS Rules

## File Safety — NEVER DELETE FILES WITHOUT EXPLICIT USER PERMISSION

* NEVER delete, replace-via-delete, or recreate a file without the user's explicit permission for that file operation.
* If a change can be done by editing an existing file, you MUST edit it in place instead of deleting and recreating it.
* If you believe file deletion is the best or only option, STOP and ask for explicit permission first.
* “I am refactoring”, “it is easier”, or “I plan to recreate it immediately” are NOT valid reasons to delete a file without permission.

## Simplicity — DO NOT COMPLICATE OR INVENT REQUIREMENTS

* Do exactly what was requested, no more.
* Do NOT introduce architecture, abstractions, optionality, fallbacks, or refactors that were not requested.
* Do NOT invent new requirements, edge cases, or design goals unless the user explicitly asked for them.
* Prefer the simplest implementation that satisfies the requested behavior and existing project rules.
* If a simpler direct edit solves the task, you MUST prefer it over a broader redesign.
