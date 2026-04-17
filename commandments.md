# Development Commandments

Working rules for this codebase. These apply to all sessions, all changes, all output.

---

## Working Together

**Ask before assuming.**
No default values, no inferred intent, no "I went ahead and..." — if something is unclear,
ask. One clarifying question beats a wrong implementation.

**Present options when there is a real choice.**
If multiple approaches are viable, lay them out briefly with trade-offs and a recommendation.
Don't present false choices. Don't pad the list.

**Call out issues, don't silently fix them.**
If something adjacent to the current task looks wrong, flag it. Don't refactor it in passing.
Don't ignore it either.

**Don't refactor working code without being asked.**
Improvements are welcome when requested. Unsolicited rewrites of stable code introduce risk
and noise.

**Keep changes focused.**
One concern per task. If a second concern surfaces mid-work, note it and finish the first.

---

## Code Quality

**Explicit over clever.**
Name things clearly. Prefer a longer, obvious name over a short, ambiguous one. Code is read
far more than it is written.

**Fail loudly and specifically.**
Error messages should say what went wrong and where. Generic exceptions and silent failures
make debugging slow. Catch narrowly; re-raise or log with context.

**No dead code, no placeholder comments.**
`# TODO`, `pass`, commented-out blocks — these don't ship. If something is genuinely deferred,
it gets a tracked issue, not an inline comment.

**Don't over-engineer for hypothetical requirements.**
Build for what is needed now. Structure that accommodates obvious growth is fine; abstractions
for imagined future cases are not.

**Favor the standard library and established patterns.**
Reach for a new dependency only when the alternative is meaningfully worse. If a dependency
is proposed, say why it earns its place.

**Log meaningfully.**
Log at the right level. Enough to reconstruct what happened; not so much that signal drowns
in noise. Include context (IDs, state) not just event names.

---

## Testing

**Write unit tests for all new code.**
Tests live alongside the code they cover. If a function is worth writing, it is worth testing.

**Tests are part of the deliverable, not an afterthought.**
New functionality is not complete until tests are written and passing.

**The test suite must pass before any push.**
No exceptions. If a pre-existing test is failing for an unrelated reason, that gets surfaced
and resolved first.

**Test the behavior, not the implementation.**
Tests should survive an internal refactor. Coupling tests tightly to implementation details
means twice the maintenance.

**Name tests plainly.**
`test_picks_highest_frequency_word_when_multiple_eligible` is a good name.
`test_function_1` is not.

---

## Version Control

**Never stage, commit, or push without confirming first.**
Always list what will be committed and ask for a go-ahead.

**Confirm file list before every commit.**
Code and appropriate documentation only. No secrets, no build artifacts, no IDE config,
no personal tooling files.

**Write commits in plain language.**
Concise, direct, lowercase. Describe what changed and why if the why isn't obvious.
Avoid filler: "refactor", "fix", "update" alone mean nothing.

```
# Good
add artist filter to word-of-day selection query
fix transliteration of soft sign in word-final position
pin stanza to 1.8.x — 1.9 drops uk model support

# Avoid
Updated code
Fixed bug
Refactored module for better readability and maintainability
```

**One concern per commit.**
Mixed commits make history hard to read and rollbacks painful.

**Branches for anything non-trivial.**
`main` stays clean and working. Features and experiments get a branch.

---

## Documentation

**Maintain README.md.**
Keep it current when commands, setup steps, env vars, or behavior changes. A stale README
is worse than no README.

**Inline comments for nuance, not narration.**
Don't explain what the code does; explain why it does it that way when the reason isn't
obvious. If a comment is restating the code, delete it.

**Sample data and example requests/responses are documentation.**
Include realistic examples in README sections and docstrings where the shape of data matters.
A concrete example communicates faster than a description.

**Docstrings for public interfaces.**
Public functions and classes get a docstring covering: what it does, non-obvious parameters,
return value, and any important side effects. Keep it tight.

---

## Security and Environment

**Honor env files.**
`.env` and equivalent files are local configuration. Their values do not leave the workspace.
If a value is needed to discuss a problem, ask first.

**Secrets never touch code.**
No credentials, tokens, or keys in source files — not even in comments. Everything
sensitive lives in environment variables.

**`.env.example` stays current.**
When a new env var is introduced, add it to `.env.example` with a comment explaining
what it is and where to get a value.

**Flag security concerns directly.**
If an approach has a meaningful security implication, say so plainly before implementing it.