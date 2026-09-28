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
| Approved focus blocks on a "Meow focus" Google calendar (the only calendar Meow can edit) | ✅ works |
| Morning and evening briefings, with macOS notifications outside quiet hours | ✅ works |
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

Meow reads Gmail, Calendar and Classroom **read-only**. The one thing it writes is a calendar it creates itself, "Meow focus", holding the focus blocks you approved; the `calendar.app.created` permission means it cannot touch any other calendar. Tokens live in the macOS Keychain; account addresses live in your local database, never in this repo.

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

When you approve focus blocks, they appear on the "Meow focus" calendar within a minute (with a 5-minute reminder, so your phone nudges you too). Finish or drop a task and its upcoming blocks come off the calendar on the next sync. If you delete the calendar, Meow recreates it; events you add to it yourself are left alone.

College Google Workspace accounts are often locked down by the admin; if sign-in says the app is blocked, only the admin can allow it.

## Briefings

While `meow serve` runs, Meow writes a **morning briefing** at 08:15 (your day's blocks, focus sessions, what's due in 48 hours, what's at risk, top priorities) and an **evening review** at 22:00 (what you finished, what's left tonight, what's due tomorrow). Each shows on the dashboard and as a macOS notification, never during quiet hours, and once per day. They're built from your data by code, not by a model, so they're instant and never invent a deadline. `meow brief` prints one on demand. Times live under `[briefings]` in the config.

## Measuring the extractor

The model is chosen by measurement, not reputation. `meow eval run` runs the real extractor over labelled messages and reports precision and recall (did it find the real tasks, and only those), deadline and course accuracy, false alarms on messages that ask nothing, and speed.

```bash
uv run meow eval run                                           # the seed benchmark, default model
uv run meow eval run --model qwen3:8b --model qwen3:4b --think off --think on --verbose
uv run meow eval export                                        # your own approvals/rejections → private test set
uv run meow eval run --dataset ~/Library/Application\ Support/MeowOS/evals/mine.jsonl
```

The seed benchmark ([`src/meow/evals/seed_extraction.jsonl`](src/meow/evals/seed_extraction.jsonl)) is 23 invented messages with hand-checked answers: relative and numeric dates, Hinglish, forwarded mail, lecture-time tests, multi-task announcements, and traps (promos, cancellations, a deadline that already passed). Results on an M5 MacBook, 28 Sep 2026:

| Model | Precision | Recall | Deadlines | Courses | Clean negatives | Time / message |
|---|---|---|---|---|---|---|
| **qwen3:8b, thinking off** (default) | 1.00 | 1.00 | **100%** | 100% | 4/4 | 11.4 s |
| qwen3:8b, thinking on | 1.00 | 1.00 | 100% | 100% | 4/4 | 36.0 s |
| qwen3:4b, thinking off | 0.96 | 1.00 | 81% | 95% | 3/4 | 6.2 s |

What the benchmark caught along the way, each now fixed in code and covered by a test: the model counted weekdays wrong ("this Friday" on a Wednesday); it copied a deadline phrase from the prompt's own example into an email that had none; it offered task wording ("form groups of 3") as a deadline; and the date resolver read "last Friday" as next Friday. The rule that came out of it: **a deadline must be backed by time wording that is really in the message, and code (not the model) turns that wording into a date.**

Honest caveat: these 23 cases were also used to find those bugs, so they are a development set, not an independent test. The number that matters is the one from `meow eval export` on your own messages, which never leave your machine.

## Configuration

Defaults live in [`src/meow/defaults.toml`](src/meow/defaults.toml): the weekly schedule (sleep 04:00–08:00, college 09:15–16:30, deep focus until 04:00, open weekends), the seven courses and their priorities, scoring weights, planner limits, the model, and autonomy rules. Override anything in your own `config.toml`; `meow config` prints where it goes. Data lives in `~/Library/Application Support/MeowOS` (set `MEOW_HOME` to move it).

## Development

```bash
uv run pytest                   # ~230 tests, about two seconds
uv run ruff check && uv run ruff format --check
uv run mypy                     # strict
MEOW_HOME=.meow-dev MEOW_API_TOKEN=dev-token uv run meow serve   # throwaway dev data
```

Code layout (`src/meow`):

| Path | What |
|---|---|
| `config.py`, `defaults.toml` | Profile model and file locations |
| `domain/` | Pure logic: schedule, prioritizer, planner, deadline-phrase dates (no I/O) |
| `db/` | SQLAlchemy models, UTC-safe column types, Alembic migrations |
| `services/` | Use cases: tasks, proposals, autonomy, capture, planning, accounts, sync, briefings, background worker, audit |
| `integrations/google/` | OAuth + Keychain tokens, thin API adapters, pure normalizers, sync |
| `llm/` | Ollama client and the evidence-checked extractor (+ prompt) |
| `evals/` | Extraction benchmark: scorer, seed cases, export from your decisions |
| `api/` | FastAPI app, auth, JSON routes, server-rendered pages |
| `notify.py` | macOS notifications (text passed as arguments, never as script) |
| `cli.py`, `doctor.py` | The `meow` command |

The earlier prototype lives in the git history of `main` (its cat widget and AppleScript helpers get ported in later slices).

## Roadmap

1. **Deadline Guardian**: done. Google sync, the Meow focus calendar, briefings, and a measured extractor. Next: re-run the eval on your real messages after a few weeks of use.
2. **Developer co-pilot**: stale-repo detection from the GitHub API, `meow explain` for failed shell commands, commit-message suggestions (never auto-push).
3. **Presence**: the desktop cat as a client of this API; wake word, then VAD, then local speech-to-text; macOS Focus through Shortcuts.
4. **Chat with tools** over your tasks and plan, every tool tagged L1/L2/L3.
5. **Always on**: launchd agent, weekly self-review.
