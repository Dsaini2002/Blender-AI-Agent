# Blender AI Agent

**Tell Blender what you want. It plans it, builds it, checks it from every side, and fixes it.**

Blender AI Agent is an add-on that puts an AI assistant inside Blender. You write a request in plain words, such as
*"create a table with two books and a laptop on it, and a lamp"*. The agent writes a plan, builds the scene with real
Blender tools, puts every object in a sensible place, looks at the result from many angles, and fixes what is wrong.

It is not a chat window that pastes random code. It is an engineered system: typed tools, a safe sandbox, undo on
failure, measured checks, picture reviews, and more than 1,600 automated tests.

---

## Contents

- [Highlights](#highlights)
- [How a request works](#how-a-request-works)
- [Quick start](#quick-start)
- [Choosing an AI provider](#choosing-an-ai-provider)
- [The panel](#the-panel)
- [Example prompts](#example-prompts)
- [What it can build](#what-it-can-build)
- [AI usage and quota](#ai-usage-and-quota)
- [When something goes wrong](#when-something-goes-wrong)
- [Settings](#settings)
- [Safety](#safety)
- [For developers](#for-developers)
- [Contributing](#contributing) · [Author](#author) · [License](#license)

---

## Highlights

| | |
|---|---|
| **Plan first** | Before anything is built, the AI writes a checklist: every object, how many, and where it goes. You see it in the panel. |
| **57 typed tools** | Objects, meshes, materials, lights, cameras, curves, buildings, sports fields, stands, text, saving and more. |
| **51 ready-made models** | Furniture, lamps, trees, sports equipment, vehicles and props, placed in one call at real size. |
| **22 procedural materials** | Wood, glass, concrete, grass, brick, water, fire, smoke and more. |
| **Smart placement** | After building, the AI decides the best spot for each object from real measurements. Your positions always win. |
| **Deep check** | The scene is rendered from 9 angles plus a close-up of every checklist item, and reviewed object by object. |
| **Error finder** | A measured list of every problem: overlaps, floating objects, furniture through walls, missing items and more. |
| **One provider, your choice** | Gemini, Claude or OpenAI. The provider you pick does all the work. |
| **Never lost** | Stop at any time, switch provider, and **Continue** from where it stopped. **Revert** undoes a run. |
| **Honest results** | Every run ends as *completed*, *partly done* or *failed*, with the AI requests and tokens it used. |

---

## How a request works

**Plan → Build → Place → Check → Fix → Save**

1. **Plan.** The AI reads your request (English, Hindi or Hinglish) and writes a checklist, for example
   *table ×1, book ×2 on the table, laptop ×1 on the table, lamp ×1*. It also picks the tools the job needs and notes
   whether you want a `.blend` file.
2. **Build.** The AI calls the add-on's tools step by step. Each call is checked before it runs, and only the tools
   from the plan are sent, which keeps every request small. If no tool fits a part, the AI makes it itself (with
   a mesh formula, raw geometry or a reviewed build script).
3. **Place.** The agent measures everything that was built. The AI then decides where each item fits best
   (books *on* the table, a lamp *beside* it). If a move would make the scene worse, it is undone.
4. **Check.** The scene is rendered from the front, back, left, right, top, a low angle, two corner views and a
   zoomed-out view, plus a zoomed-in close-up of every item. The AI reviews these pictures together with the
   checklist and a list of measured problems, and counts every item ("book: 1 of 2 seen").
5. **Fix.** Anything wrong goes back to the AI as a clear fix list. Check and fix repeat until the result is right,
   or until three rounds in a row bring no improvement.
6. **Save.** If you asked for a file, the final scene is saved and the file is checked on disk.

Big requests (a whole room, a campus, a stadium) are first split by a planner into steps for specialists: layout,
modeling, materials and lighting.

Requests that a ready-made skill can build by itself (a campfire, a tent, a house, a cartoon character and other
library models) skip the AI completely: no plan request and no picture review - they are built at once and checked
by measurement only.

---

## Quick start

You need **Blender 5.2**, an internet connection and **one API key**. Nothing else: no Python, no pip, no Git.

### 1. Download the add-on

**[⬇ Download blender_ai_agent.zip](https://github.com/Dsaini2002/Blender-AI-Agent/raw/main/blender_ai_agent.zip)**

Or open the file `blender_ai_agent.zip` at the top of this repository and click the **Download raw file** button
(the arrow at the top right of the file view).

> **Do not unzip it.** Blender installs the zip as it is.
>
> **Do not use the green *Code → Download ZIP* button.** That zip holds the whole project inside an extra folder,
> and Blender cannot install it.

### 2. Install it in Blender

1. Open Blender and go to **Edit → Preferences → Add-ons**.
2. Click the small **drop-down arrow** at the top right and choose **Install from Disk…**
3. Select the downloaded **`blender_ai_agent.zip`** and click **Install from Disk**.
4. Make sure the tick box next to **Blender AI Agent** is on.

### 3. Add your API key (in the panel, only once)

1. Close Preferences. In the 3D viewport press **N** and open the **AI Agent** tab on the right.
2. Pick a provider in the drop-down at the top: **Google Gemini**, **Anthropic Claude** or **OpenAI**
   (see [Choosing an AI provider](#choosing-an-ai-provider)).
3. The panel shows **No API key** and a key box. Click **Get key** - the provider's key page opens in your browser.
4. Create a key, copy it, paste it into the box and press **Submit Key**.

The status changes to **Ready**. You do not need to open Preferences for the key, and you are asked for it **only
once**: it stays saved, also when you install a newer version.

### 4. Make something

Type a request in the **AI Prompt** box and press **Generate with AI**:

```
create a table with two books and a laptop on it, and a lamp, save it as desk_test
```

You will see the plan first, then each step, then the check rounds. **Stop** stops at once; **Revert AI Changes**
undoes the whole run.

### Updating to a new version

1. **Edit → Preferences → Add-ons**, find **Blender AI Agent**, open it and click **Remove**.
2. Download the new `blender_ai_agent.zip` and install it as in step 2.
3. **Restart Blender.** Your API key is still there.

### Install problems

| Problem | Fix |
|---|---|
| Nothing appears after installing | Make sure the add-on's tick box is on, then press **N** in the 3D viewport and look for the **AI Agent** tab. |
| An error while installing, or *Blender AI Agent* is not in the list | You installed the wrong zip. Use `blender_ai_agent.zip` from the link above (not unzipped), not *Code → Download ZIP*. |
| The panel says *Add-on files are out of date* | Remove the add-on, install the new zip again, and restart Blender. |
| Generate is greyed out or says *No API key* | Paste the key for the provider shown at the top and press **Submit Key**. |

---

## Choosing an AI provider

Pick the provider and model in the drop-down at the top of the panel. You can switch at any time.

| Provider | Models | Good to know | Get a key |
|---|---|---|---|
| **Google Gemini** | Gemini 3.6 Flash, Flash (Latest), 3.1 Pro (Preview), 3.5 Flash Lite | Has a free tier with a small **daily** request limit. Flash Lite allows many more requests per day. | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| **Anthropic Claude** | Sonnet 5.5, Opus 5.5, Haiku 5.5 | Paid. Very strong at big, detailed scenes. | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| **OpenAI** | GPT-6 Luna (cheapest), GPT-6 Sol (balanced), GPT-6 Astra (strongest), Astra Pro | Paid. Runs on the Responses API with low reasoning effort to save tokens. Small edits go to Luna automatically. | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

- The provider you pick does **everything**: planning, building, placing and looking at the pictures.
- It never switches to another provider on its own.
- If its quota or rate limit runs out, the run **waits** (a countdown is shown) and then goes on by itself.
  Press **Stop** to cancel the wait.

---

## The panel

| Part | What it does |
|---|---|
| **Status line** | *Ready*, *Working* or *No API key*, with the provider and model drop-downs. Below it: today's AI requests and tokens. |
| **Scene Context** | *Auto* sends the selected objects with your request, so "make it red" knows what *it* is. |
| **AI Prompt** | Type your request. The box grows with the text and scrolls after 12 lines. **Ctrl+V** and **Paste** keep every line. |
| **Generate with AI** | Starts the run. While it works you see the plan, each step, the check rounds and any quota countdown. |
| **Stop** | Stops **at once**, even while the AI is thinking or pictures are rendering. Nothing more is changed after Stop. |
| **Continue with …** | After a stopped or failed run: pick any provider and continue. The plan is reused and only the missing parts are built. |
| **Recent Tasks** | Past runs with time taken, **View Report**, **Check Images**, **Find Errors** and **Retry**. |
| **Revert AI Changes** | Puts the scene back exactly as it was before the last run. |
| **Find Errors** | Writes a full list of scene problems to a text file and opens it. It changes nothing. |
| **Modeling / Material / Lighting** | One-click improvements for the selected objects. |

---

## Example prompts

| You write | What happens | AI requests |
|---|---|---|
| `make a campfire` | A ready-made model is placed at once and checked by measurement. | **None** |
| `make a cute girl with long blonde hair, blue eyes and glasses, laughing` | The character skill builds face, hair, clothes and glasses in one go. | **None** |
| `make a house` | The house skill builds walls, roof, door and windows. | **None** |
| `create a table with two books and a laptop on it, and a lamp` | Plan → build → the AI places the books and laptop on the table → deep check. | Several |
| `make the sofa dark green and move the rug 0.5 m back` | A small edit: only those objects change. | A few |
| `change the roof design to gable` | The building is rebuilt in place with the new roof. | A few |
| `Create a G+5 U-shaped student hostel with 180 rooms, a basketball court and a boundary wall with a gate` | The planner splits it into specialist steps; the hostel itself is built in one tool call. | Many |
| `make a realistic sports car` | The build loop writes a script, renders it, scores it and improves it. | Many |

Tips for good results:

- Name the objects, counts and sizes you care about ("3 chairs", "a 2 m wide desk").
- Say where things go ("on the table", "against the back wall", "at (2, 3, 0)"). Otherwise the AI picks the spot.
- Ask for a file in the same request ("save it as my_room").

---

## What it can build

| Area | Tools and features |
|---|---|
| **Objects** | Create, move, turn, scale, duplicate, rename and delete. Exact placement: `place_on`, `place_next_to`, `snap_to_ground`, `move_by`, `measure`. |
| **Ready-made models** | 51 models: beds, sofas, tables, chairs, wardrobes, bookshelves, lamps, chandeliers, rugs, curtains, plants, trees, benches, street lamps, floodlights, goals, nets, hoops, bicycles, tents and more. |
| **Buildings** | `mesh.building`: hostels, hotels, colleges and offices in one call (rect, L, U or courtyard; any number of floors; rooms with furniture; halls; stairs; lifts; balconies; roofs). |
| **Sites and sports** | Boundary walls with gates, regulation lines for football, cricket, tennis, badminton, volleyball and basketball, and stepped stands with seats and roofs. |
| **Shapes** | Lathe (round objects), SDF (organic shapes), prisms, terrain, curves and flat paths, raw meshes, per-vertex formulas, and 26 edit presets (melted, twisted, cracked …). |
| **Materials** | 22 procedural materials and custom node graphs; recolour existing objects by name. |
| **Characters** | Cartoon characters with 8 expressions, 7 hair styles, clothes, shoes, glasses and hats. |
| **Look** | Lights, world, cameras and render presets (cinematic, product, outdoor, night, clean). |
| **Files** | Collections, saving `.blend` files (checked on disk), importing OBJ/FBX/GLB and 991 searchable free CC0 models. |

---

## AI usage and quota

Every AI request costs tokens or counts against a daily limit, so the add-on shows you what each run used.

- **After each run:** *"AI use: 12 request(s), 210,500 tokens - plan 1, build 8, place 1, check 2.
  Wasted: 26,400 tokens (13%)"*
- **In the panel:** today's total for the selected model, failed requests, and when the quota ran out.
- **In the run report:** an *AI USE* section per phase, with the reason for every wasted request.
- **On disk:** `~/BlenderAIAgent/usage.json` keeps the daily totals for two weeks.

A request counts as **wasted** when the AI only repeated finished work, answered with text instead of acting, a fix
round brought no improvement, or a placement had to be undone.

Ways to use fewer requests:

- Use Gemini 3.5 Flash Lite or GPT-6 Luna for simple scenes.
- Set `"deep": false` or fewer `"closeups"` in `autoverify.json` (see [Settings](#settings)).
- Set `"max_rounds"` lower to allow fewer fix rounds.

The official limits of your account are shown by your provider (for Gemini: Google AI Studio).

---

## When something goes wrong

Everything the add-on writes is in the `BlenderAIAgent` folder in your home folder.

| File | What it tells you |
|---|---|
| `logs/live_trace.txt` | Written live: every plan, AI request, tool call, error and check. If Blender seems stuck, the last lines show what was running. Panel: **Open Live Trace**. |
| `logs/<time>_report.txt` | The readable report of one run: result, versions, AI use, where the time went, every error with its tool and arguments, and a timeline. Panel: **View Report**. |
| `logs/<time>.json` | The same run as data, for bug reports. |
| `checks/<time>_r<round>/` | One folder per check round: the pictures, `review.txt` (score, missing items, problems), `fix_prompt.txt` (what the AI was told to fix) and `errors.txt` (measured problems). Panel: **Check Images**. |
| `errors/<time>_errors.txt` | Written by **Find Errors**: every problem with the objects involved, the measured numbers, why it is wrong and how to fix it. |
| `usage.json` | AI requests and tokens per day. |

When you report a problem, please attach the `_report.txt` of that run, plus `errors.txt` and a screenshot if the
scene looks wrong.

Common messages:

| Message | What to do |
|---|---|
| *No API key* | Paste the key for the selected provider in the key box and press **Submit Key**. |
| *Waiting for … quota: resumes in …* | The provider's limit is used up. Wait, press **Stop**, or pick another provider and press **Continue**. |
| *The API key is not valid any more* | Press **Change** next to the key and paste a new one. |
| *Partly done* | The run hit its step limit. Press **Continue** to finish it. |

---

## Settings

Most people never need these. The check can be tuned in `~/BlenderAIAgent/autoverify.json`:

| Key | Default | Meaning |
|---|---|---|
| `mode` | `full` | `full` = pictures + console + geometry, `console` = no pictures, `off` = no check. |
| `deep` | `true` | Render all 9 angles and close-ups. `false` = a quick check from 2 angles. |
| `closeups` | `10` | Most close-ups per check round. |
| `resolution` | `384` | Size of the check pictures in pixels. |
| `max_rounds` | `15` | Most fix rounds. |
| `stall_rounds` | `3` | Stop after this many rounds without improvement. |
| `pass_score` | `10` | The review score a result needs to pass. |

Environment variables (optional):

| Variable | Meaning |
|---|---|
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Keys from the system instead of the panel. A key saved in the panel wins. |
| `BLENDER_AI_AUTOVERIFY` | `full`, `console` or `off`, overriding `mode`. |
| `BLENDER_AI_LOG_DIR` | Where logs are written (default `~/BlenderAIAgent/logs`). |
| `BLENDER_AI_MODELS_DIR` | Folder with your downloaded CC0 models (see `download_models.py`). |
| `BLENDER_AI_DEBUG` | `1` prints timing details to the System Console. |

---

## Safety

- **Checked tools.** The AI can only call the add-on's typed tools. Every argument is checked before anything runs.
- **Sandboxed scripts.** Build scripts cannot import modules, open files or reach the network, and have limits on
  loops and time. Free Python runs on Blender's main thread with a full checkpoint, so a failure is undone exactly.
- **Undo on failure.** Failed work is rolled back. Objects are tracked by Blender's own ID, so a renamed object is
  restored, never deleted.
- **Your scene first.** Fix rounds are told to change only what the run made, and **Revert AI Changes** brings back
  the scene exactly as it was before the run.
- **Limits.** A run stops (keeping its work) after 300 tool calls, 30 repair retries, 20 minutes or 600 objects.
- **Private keys.** Keys are stored only on your computer, in Blender's preferences and in
  `~/BlenderAIAgent/keys.json` in your user folder. They are never written into `.blend` files, logs or reports.

---

## For developers

### Project layout

```
blender_ai_agent/
├── agent/          plan, checklist, placement, agent loop, prompts, build sandbox, checks
├── bridge/         BlenderBridge - the only layer that changes the Blender scene
├── copilot/        controller, quota waiting, Continue, progress
├── diagnostics/    the error finder (scene audit)
├── providers/      Gemini, Claude and OpenAI clients (plain HTTPS, no SDK)
├── tools/          the 57 typed tools
├── skills/         fast paths: ready props, characters, houses
├── library/        the 51 ready-made models
├── observability/  live trace, run reports, token meter
├── reliability/    rollback, snapshots, friendly errors
├── ui/             the Blender panel
└── tests/          unit and integration tests
```

### Run the tests

The tests do not need Blender: a fake Blender bridge and a mock AI provider stand in.

```powershell
python run_tests.py
```

| Check | Result |
|---|---|
| Automated tests | **1,603 passed**, 0 failed (3 skipped on Windows: low-level console capture) |
| Real-Blender check | **84 of 84 checks passed** on Blender 5.2.1 LTS |

### Real-Blender check

`scripts/real_blender_check.py` runs the add-on inside real Blender 5.2.1 (the `bpy` module from PyPI). It builds a
campus, runs a full Generate flow with scripted AI answers (plan, build, placement, deep check, save), tests Stop
during renders and while the AI is thinking, and Continue with another provider. GitHub runs it on every push.

```bash
python -m venv .bpyenv && .bpyenv/bin/pip install bpy==5.2.1
.bpyenv/bin/python scripts/real_blender_check.py --render
```

### Quality benchmark

`real_benchmark.py` runs 20 fixed prompts through your real AI provider inside Blender and records success, time,
floating objects, overlaps and a picture score for each. Run it before and after a change and compare.

```powershell
blender --background --python real_benchmark.py -- --provider gemini --limit 5
```

### Install from source

```powershell
git clone https://github.com/Dsaini2002/Blender-AI-Agent.git
Copy-Item .\Blender-AI-Agent\blender_ai_agent "$env:APPDATA\Blender Foundation\Blender\5.2\scripts\addons\" -Recurse
```

### Making a release

1. Build `blender_ai_agent.zip` with the `blender_ai_agent` folder at its root (no tests, no `__pycache__`) and put it
   at the root of the repository, replacing the old one - this is the file the download link points to.
2. Push a tag such as `v0.16.4`. The `release` workflow runs the tests, builds the same zip and attaches it to the
   GitHub release.

### Design choices

- **Typed tools, not free code.** Small tools with schemas are easier to check, test, undo and explain.
- **Known work skips the AI.** Ready skills are faster, cheaper and the same every time.
- **The AI decides, the agent measures.** The AI plans and chooses; the code measures, checks and executes.
- **One bridge to Blender.** Only `BlenderBridge` touches the scene, so everything else can be tested without Blender.
- **Pictures and numbers.** A scene can be wrong even when no code failed, so every run is checked both by
  measurement and by looking.

---

## Contributing

Ideas, bug reports and pull requests are welcome.

1. Fork the repository and create a branch.
2. Make your change and add a test for it.
3. Run `python run_tests.py`. It must end with `OK`.
4. Open a pull request that explains *what* changed and *why*.

---

## Author

Made by **Dinesh Saini**, a student at **NIT Trichy**.
GitHub: [@Dsaini2002](https://github.com/Dsaini2002)

---

## License

GPL-3.0-or-later, the same license family as Blender.
