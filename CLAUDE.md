# CLAUDE.md

Guidance for AI assistants working in `FidarisAdvisory/ai-training-hub`. Read this end-to-end before editing — the repo has a few non-obvious quirks that are easy to "fix" by accident.

## Repository purpose

A small collection of standalone training/dashboard artifacts:

- An interactive **AI Tools Training Hub** dashboard that walks learners through ChatGPT, Gemini, Claude, Perplexity, and NotebookLM exercises and tracks progress in the browser.
- An unrelated static dashboard for an **F3-The Edge** fitness group (Katy, TX).
- A stub **Privacy Policy** React component intended for some other site/app (not built or rendered from this repo).

There is no application server, no SPA, and no shared component model — each artifact stands alone.

## File map

```
.
├── AI_Training_Dashboard.html   # 1955 lines — main interactive dashboard
├── f3-dashboard.html            #  368 lines — static F3 fitness dashboard
└── src/
    └── components/
        └── pages/
            └── PrivacyPolicyPage.tsx  # 60 lines — orphan TSX, not buildable here
```

That's the entire repo. There is **no** `package.json`, `tsconfig.json`, build config, lint config, test framework, CI config, `.gitignore`, or `README.md`.

## No build tooling — how to run / test

- HTML files: open directly in a browser (`file://...`) or serve with anything static (e.g. `python3 -m http.server`). No bundler, no transpile step.
- TSX file: **cannot be compiled in this repo as-is.** It imports `@/components/Header` and `@/components/Footer` from a path alias that has no `tsconfig` to resolve, and the referenced modules don't exist in `src/`. Treat it as a snippet copied from another project.
- Do **not** suggest `npm install`, `npm run dev`, `npm test`, or any framework CLI — none of them apply. If a task genuinely requires a build pipeline, raise that with the user before scaffolding one.

## `AI_Training_Dashboard.html` internals

Single-file artifact: inline `<style>`, inline `<script>`, Google Fonts loaded via CDN (`Orbitron`, `Rajdhani`, `Space Grotesk`). Cyberpunk/neon visual style driven by CSS custom properties (`--neon-cyan`, `--neon-magenta`, etc.) defined in `:root`.

State (around line 1632):

```js
let progressData = {
  completed: [],         // array of exercise IDs the user has marked done
  achievements: [],      // array of achievement IDs awarded
  sessionCompleted: 0    // counter for the "speed-runner" badge
};
```

Persisted to `sessionStorage` under the key **`aiTrainingProgress`** (load at line 1664, save at line 1672). Note: the comment at line 1660 calls it "memory storage" / mentions `localStorage`, but the actual implementation is `sessionStorage` — state does **not** survive closing the tab. Do not "correct" the comment without confirming intent.

Exercise IDs (line 1639) — there are **12**, not 18:

```
chatgpt-personal, gemini-personal, claude-personal, perplexity-personal, notebooklm-personal,
prompting-1, prompting-2, prompting-3,
meta-templates, meta-1, meta-2, meta-3
```

The static markup at line 767 hard-codes `<div class="stat-value" id="totalCount">18</div>`, but `updateProgressStats()` (line 1684) overwrites it with `exercises.length` = 12 on first render. The "18" in the HTML is dead weight — leave it unless asked, but be aware if you're chasing a count discrepancy.

`toolExercises` mapping (line 1645) groups exercises per tool card so the per-tool progress bars work:

```js
{ chatgpt: ['chatgpt-personal'], gemini: [...], claude: [...], perplexity: [...], notebooklm: [...] }
```

Achievement IDs (declared in `data-achievement` markup ~lines 1572–1607 and awarded in `checkAchievements()` ~line 1746):

```
first-step, tool-explorer, prompt-apprentice, meta-master,
halfway-hero, dedicated-learner, ai-champion, speed-runner
```

Key entry points:

| Function | Line | Purpose |
| --- | --- | --- |
| `init()` | 1654 | Bootstrap on load: `loadProgress` → `updateUI` → `setupNavigation` |
| `loadProgress()` / `saveProgress()` | 1661 / 1671 | sessionStorage round-trip |
| `updateUI()` | 1676 | Recomputes stats, cards, tool bars, achievements |
| `toggleExercise(id)` | 1731 | Mark done/undone, triggers confetti + achievement check |
| `checkAchievements()` | 1746 | Rules engine for the 8 badges |
| `setupNavigation()` | 1844 | Wires `.nav-tab` clicks to section visibility |
| `showToolModal(tool)` / `closeModal()` | 1858 / 1866 | Tool-detail modal |
| `resetProgress()` | 1930 | Wipes state and re-renders |

When editing this file, keep changes scoped — the HTML, CSS, and JS are tightly coupled by string IDs (`exercise-<id>`, `progress-<tool>`, `data-achievement="..."`).

## `f3-dashboard.html`

Pure static HTML/CSS, no JavaScript. All numbers (beatdown counts, leaderboard bar widths, raffle totals) are hard-coded literals — updating the dashboard means editing those values directly. Footer reads "Data as of January 2025"; bump that string if you refresh the data.

## `src/components/pages/PrivacyPolicyPage.tsx`

Termly-style privacy-policy stub. It has cascading runaway indentation (each line is indented further than the last) and stray duplicate closing tags (`</style>style>`, `</div>div>`, `</main>main>`, plus an extra `</div>` after the function's closing brace). This is broken-looking, but **don't reflexively reformat it** — it's a scaffold likely meant to be transplanted into a Next/Vite app elsewhere. If the user explicitly asks to clean it up, fix indentation, remove the stray tags, and replace the placeholder body text inside `dangerouslySetInnerHTML`.

## Known quirks — do not "fix" without being asked

1. **Stray duplicate closing tags** in `f3-dashboard.html` (`</p>p>`, `</div>div>`, duplicated `</body>` / `</html>html>`) and in `PrivacyPolicyPage.tsx`. Browsers and JSX parsers tolerate them; surrounding whitespace looks like it came from a paste/format glitch. `AI_Training_Dashboard.html` does **not** have this issue — don't introduce it when editing.
2. **`sessionStorage` vs `localStorage` comment** in `AI_Training_Dashboard.html` line 1660 — see note above.
3. **`totalCount` shows 18 in markup but renders 12** — see note above.
4. **Orphan `@/components/Header` / `@/components/Footer` imports** in the TSX file — the modules don't exist; don't try to "find and import" them.
5. **Repo has no `.gitignore`** — be careful what you create at the root; everything is trackable by default.

## Conventions

- Single-file artifacts: HTML files keep all CSS in one `<style>` block and all JS in one `<script>` block at the bottom of `<body>`. Don't extract into separate files unless asked.
- Vanilla JS only inside the dashboards — no React, jQuery, or framework imports. Functions are global and event handlers are wired with inline `onclick="..."` plus a couple of `addEventListener` blocks.
- CSS uses `:root` custom properties for the neon palette in `AI_Training_Dashboard.html`; reuse those instead of hard-coding hex values.
- Emoji-heavy UI copy (🚀 🤖 ✨ 🎭 🔍 📓 🏆) is intentional — preserve the style when adding sections.
- Indentation: 4 spaces in `AI_Training_Dashboard.html`. The other two files have inconsistent/runaway indentation — match the local file style if you must edit, don't reformat the whole file.

## Git workflow

- Remote: `FidarisAdvisory/ai-training-hub` (single remote, `origin`).
- AI-authored work goes on a `claude/<slug>` branch. The branch for any in-flight task is supplied by the harness — push only to that branch.
- Commit messages so far are short and imperative (`Add F3-The Edge Dashboard`, `Update PrivacyPolicyPage.tsx`). Match that style.
- Do **not** open pull requests unless the user explicitly asks. Do **not** push to `main`/`master`.

## Verification checklist when editing the main dashboard

1. Open `AI_Training_Dashboard.html` in a browser.
2. Click each nav tab (Overview / Personalization / Prompting / Meta-Prompts / Achievements) — the active section should swap.
3. Click "Mark Complete" on a few exercises — main progress bar, per-tool bar, and counters should update; confetti should fire.
4. Trigger an achievement (e.g. complete the three `prompting-*` exercises for `prompt-apprentice`) and confirm the badge animates.
5. Reload the tab — completed state should persist (sessionStorage). Close and reopen the tab — state should reset (also sessionStorage).
6. Open a tool modal via a tool card and confirm `closeModal()` works (overlay click + close button).
