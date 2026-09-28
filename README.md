# Meow OS

A local-first personal chief of staff. It reads what lands on your plate (class posts, emails, pasted messages), turns it into tasks **it has to back up with a quote from the source**, ranks them with reasons you can read, and fits them into your real week, all on your own Mac. Nothing it proposes happens until you approve it.

Built for one person: a TE Computer Engineering student working toward GPU/CUDA/ML engineering at NVIDIA.

## Status

v0.2 is a rebuild. Everything listed as working has tests behind it.

| Area | State |
|---|---|
| Profile: schedule, courses, weights (TOML, validated) | ✅ works |
| Prioritizer: deterministic, explains every score | ✅ works |
| Planner: timezone-aware, crosses midnight, daily cap, flags deadline risk | ✅ works |
| Proposals and approval inbox, with evidence and source | ✅ works |
| Earned autonomy (L1/L2/L3 per kind of action) | ✅ works |
| Task extraction from pasted text (local model, evidence-checked) | ✅ works (needs Ollama and a model) |
| Audit log of every action | ✅ works |
| Web dashboard + JSON API, token-secured | ✅ works |
| `meow` CLI with a real `doctor` | ✅ works |
| Google sync: Classroom coursework → proposals (no LLM), Gmail + announcements → model, Calendar → busy time | ✅ works (read-only, multi-account) |
| Focus blocks pushed to a "Meow" Google calendar, briefings | ⏳ next |
| Desktop cat, voice, focus mode | ⏳ later slices |

## How it's built, and why

- **Proposals, not actions.** Everything the AI produces is a proposal with the source it came from. You approve, edit, or reject it. Rejections are data.
- **Earned autonomy.** Each kind of action starts at L2 (one click). After 20 of your decisions with at least 95% approved unedited, you can promote it to L1 (automatic). A rejection while automatic demotes it. Each kind also has a ceiling it can never pass (future actions like sending email get L3).
- **The LLM only where it's needed.** Extraction uses a local model with a JSON schema. The output is then checked: a task whose evidence quote isn't actually in the source is dropped, deadlines are read in your timezone, and unknown course codes are discarded. Scoring and planning are plain code you can test.
- **Explainable.** Every score comes with its reasons ("Due in 20h (~2h of work) · Artificial Intelligence is a highest-priority course").
- **Local and locked down.** One SQLite file. The local API needs a per-install token from the macOS Keychain, rejects foreign `Host` headers (DNS rebinding), and refuses cross-site form posts.

```
text / Classroom / Gmail ──► source items (kept for provenance)
                                  │  local LLM + evidence check
                                  ▼
                             proposals ──(you approve)──► tasks ──► prioritizer ──► planner
                                  ▲                                                   │
                                  └────────── focus-block proposals ◄─────────────────┘
                       everything ──► audit log
```

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and, for extraction, [Ollama](https://ollama.com).

```bash
uv sync
uv run meow doctor              # checks config, schedule, database, token, Ollama, model
ollama serve                    # in another terminal, if the Ollama app isn't running
ollama pull qwen3:8b            # the default extraction model; pick yours by testing
uv run meow serve               # dashboard + API on http://127.0.0.1:8765
uv run meow open                # signs your browser in (the link lasts 2 minutes)
```

From the terminal:

```bash
uv run meow task add "CUDA: parallel reduction kernel" --due "fri 23:59" --minutes 180 --career 0.9
uv run meow task list           # ranked, with reasons
uv run meow plan                # the next 7 days of focus time
pbpaste | uv run meow capture   # extract tasks from whatever you copied
uv run meow inbox               # then: meow approve <id-prefix> / meow reject <id-prefix>
```

(`--due` accepts `2026-10-02 23:59`, `2026-10-02`, `today 18:00`, `tomorrow`, `fri` or `friday 17:00`; no time means 23:59.)

## Connecting Google

Meow reads Gmail, Calendar and Classroom **read-only**. Tokens live in the macOS Keychain; account addresses live in your local database, never in this repo.

1. In [Google Cloud Console](https://console.cloud.google.com/), in your project: enable the Gmail, Calendar and Classroom APIs, and create an OAuth client of type **Desktop app**.
2. Under **OAuth consent screen → Audience → Test users**, add every account you'll connect. (In Testing mode only listed users can sign in, and Google expires the sign-in every 7 days; Meow tells you when to log in again.)
3. Then:

```bash
uv run meow google setup ~/Downloads/credentials.json      # installs the client file privately
uv run meow google login you@gmail.com                      # opens Google's consent screen
uv run meow google login you@college.edu --sources classroom   # optional second account
uv run meow sync                                            # or let `meow serve` sync every 30 min
uv run meow google accounts                                 # what synced, and any problems
```

Classroom assignments become proposals directly from their structured due date and course (no model involved); work you've turned in is skipped, and if a teacher changes a deadline before you decide, the proposal is replaced. Emails (Primary tab only, by default) and class announcements go to the local model, which must quote the text for every task it proposes. Calendar events become busy time the planner works around; all-day events, events marked "free" and invitations you declined don't block time.

College Google Workspace accounts are often locked down by the admin; if sign-in says the app is blocked, only the admin can allow it.

## Configuration

Defaults live in [`src/meow/defaults.toml`](src/meow/defaults.toml): the weekly schedule (sleep 04:00–08:00, college 09:15–16:30, deep focus until 04:00, open weekends), the seven courses and their priorities, scoring weights, planner limits, the model, and autonomy rules. Override anything in your own `config.toml`; `meow config` prints where it goes. Data lives in `~/Library/Application Support/MeowOS` (set `MEOW_HOME` to move it).

## Development

```bash
uv run pytest                   # ~160 tests, about a second
uv run ruff check && uv run ruff format --check
uv run mypy                     # strict
MEOW_HOME=.meow-dev MEOW_API_TOKEN=dev-token uv run meow serve   # throwaway dev data
```

Code layout (`src/meow`):

| Path | What |
|---|---|
| `config.py`, `defaults.toml` | Profile model and file locations |
| `domain/` | Pure logic: schedule, prioritizer, planner (no I/O) |
| `db/` | SQLAlchemy models, UTC-safe column types, Alembic migrations |
| `services/` | Use cases: tasks, proposals, autonomy, capture, planning, accounts, sync, audit |
| `integrations/google/` | OAuth + Keychain tokens, thin API adapters, pure normalizers, sync |
| `llm/` | Ollama client and the evidence-checked extractor (+ prompt) |
| `api/` | FastAPI app, auth, JSON routes, server-rendered pages |
| `cli.py`, `doctor.py` | The `meow` command |

The earlier prototype lives in the git history of `main` (its cat widget and AppleScript helpers get ported in later slices).

## Roadmap

1. **Deadline Guardian** (in progress): ~~Google OAuth, Classroom/Gmail/Calendar sync~~ done; next: focus blocks pushed to a separate "Meow" calendar, morning and evening briefings, an extraction eval set built from your own approvals and rejections.
2. **Developer co-pilot**: stale-repo detection from the GitHub API, `meow explain` for failed shell commands, commit-message suggestions (never auto-push).
3. **Presence**: the desktop cat as a client of this API; wake word, then VAD, then local speech-to-text; macOS Focus through Shortcuts.
4. **Chat with tools** over your tasks and plan, every tool tagged L1/L2/L3.
5. **Always on**: launchd agent, weekly self-review.
