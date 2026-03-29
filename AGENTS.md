# AGENTS Rules

## File Safety — NEVER DELETE FILES WITHOUT EXPLICIT USER PERMISSION

* NEVER delete, replace-via-delete, or recreate a file without the user's explicit permission for that specific operation.
* If a change can be done by editing an existing file, you MUST edit it in place.
* If deletion or recreation seems necessary, STOP and ask for explicit permission first.
* “Refactor”, “cleanup”, “it is easier”, or “I will recreate it right away” are NOT valid reasons to delete a file without permission.
* Preserve existing filenames, paths, and project structure unless the user explicitly asks to change them.

## Simplicity — DO NOT COMPLICATE OR INVENT REQUIREMENTS

* Do exactly what was requested, no more.
* Do NOT introduce architecture, abstractions, optionality, fallbacks, refactors, or defensive layers that were not explicitly requested.
* Do NOT invent new requirements, edge cases, business rules, or design goals.
* Prefer the simplest implementation that satisfies the request and the current project rules.
* If a direct local edit solves the problem, it MUST be preferred over broader redesign.

## Python Execution — ALWAYS USE `uv`

* Always use `uv` for Python-related commands.
* Prefer:
  * `uv run python ...`
  * `uv run pytest ...`
  * `uv add ...`
  * `uv sync`
* Do NOT call `python`, `pip`, or `pytest` directly unless there is an explicit and justified exception.
* Keep execution consistent with the project's virtual environment and lockfile strategy.

## Fail-Safe — NO SILENT FALLBACKS

* Prefer fail-safe and fail-fast behavior.
* Do NOT introduce fallback behavior unless the user explicitly requested it or there is a clearly exceptional operational reason.
* Silent degradation is forbidden.
* If a required input, dependency, configuration, or resource is missing, raise an explicit error immediately.
* Errors must be clear, specific, and actionable.
* Hidden recovery logic is worse than a visible failure.

## Configuration — NO HARD-CODED CONSTANTS

* Do NOT hard-code configurable values in business logic.
* No magic numbers, magic strings, fixed paths, model names, ports, URLs, thresholds, timeouts, or credentials embedded directly in code.
* Configurable values MUST come from one of these sources, depending on project style:
  * named constants in a dedicated config/constants module
  * environment variables
  * configuration files
  * explicit function parameters
* If a value is intentionally fixed by domain rule, document that clearly and name it explicitly.

## Clarity — WRITE PYTHON THAT IS OBVIOUS

* Prefer readable and explicit code over clever code.
* Use descriptive names for variables, functions, classes, and parameters.
* Keep functions focused and small.
* Avoid unnecessary indirection.
* Avoid premature abstraction.
* Comments should explain intent, not restate obvious code.

## Typing — USE TYPE HINTS CONSISTENTLY

* Use type hints in public functions, methods, and important internal functions.
* Prefer precise types over vague ones.
* Avoid `Any` unless there is a real need.
* Keep function contracts explicit in signatures.

## Errors and Validation — BE STRICT AT THE BOUNDARIES

* Validate inputs at system boundaries.
* Reject invalid data early.
* Never swallow exceptions without a strong reason.
* Do NOT use broad `except Exception` unless the code re-raises with meaningful context or the boundary truly requires it.
* Error handling must preserve debuggability.

## State and Side Effects — KEEP THEM CONTROLLED

* Prefer pure functions when practical.
* Keep side effects explicit and localized.
* Do not hide file writes, network calls, database mutations, or environment-dependent behavior inside innocent-looking helpers.
* Functions that mutate state should make that obvious.

## Paths, Files, and I/O — BE EXPLICIT AND SAFE

* Use `pathlib` instead of ad-hoc string path manipulation.
* Always specify encoding when reading or writing text files.
* Do not overwrite user data carelessly.
* Prefer in-place edits when required by the task.
* If a write operation is risky, make the risk explicit.

## Logging — LOG FOR DIAGNOSIS, NOT FOR DECORATION

* Log meaningful events, decisions, and failures.
* Logs must help diagnose real problems.
* Do NOT log noise just to look robust.
* Never use logs as a substitute for proper error handling.
* Sensitive data must not be logged.

## Dependencies — KEEP THEM MINIMAL

* Do not add dependencies unless they are genuinely necessary.
* Prefer the standard library when it is sufficient.
* Any new dependency must have a clear justification.
* Keep dependency usage aligned with the existing project style.

## Testing — TEST THE BEHAVIOR THAT MATTERS

* Add or update tests when changing behavior, fixing bugs, or adding logic that can regress.
* Test observable behavior, not internal trivia.
* Prefer simple and deterministic tests.
* Avoid brittle tests tied to incidental implementation details.

## Project Consistency — FOLLOW THE LOCAL CODEBASE

* Respect the existing project structure, naming conventions, formatting, and patterns unless the user asked to change them.
* Do not impose a personal framework style on an established codebase.
* Consistency with the current repository is usually more important than theoretical purity.

## Scope Discipline — DO NOT “HELP” BY CHANGING EXTRA THINGS

* Do not make unrelated cleanups.
* Do not rename symbols, move files, reformat broad areas, or rewrite adjacent code unless that is necessary for the requested task.
* Keep diffs tight, local, and reviewable.
* Don't do or add anything I didn't expressly asked for

## Rule of Last Resort

* If something is ambiguous, prefer the safer, simpler, more explicit option.
* If a choice would increase hidden behavior, configuration sprawl, or surprise, do not do it.
* Visible failure is better than invisible wrong behavior.


## Comments and Docstrings — MANDATORY

* Comments and docstrings are mandatory.
* Every public module, class, and function MUST have a docstring.
* Any non-trivial internal function SHOULD have a docstring unless its purpose is completely obvious from its name and signature.
* Comments MUST explain intent, constraints, assumptions, invariants, and non-obvious decisions.
* Do NOT write useless comments that merely restate the code line by line.
* If logic is complex, unusual, domain-specific, or easy to misunderstand, add an explicit comment.
* If a workaround, limitation, or deliberate trade-off exists, document it where it appears.
* Docstrings should be concise, factual, and practical.
* Prefer documenting:
  * what the code does
  * the important inputs and outputs
  * side effects
  * important constraints
  * failure conditions when relevant
* When behavior is intentionally strict, surprising, or fail-fast, the docstring or comment MUST say so.
* A missing explanation in non-obvious code is a defect.