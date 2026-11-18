# Reviewer guide: human validation for a study of AI coding agents

Thank you for helping. This guide has everything you need. You don't need to run any code or know the study's
results. Please read sections 1–4 before you start (about 10 minutes).

---

## 1. Background (2 minutes)

We study AI agents that fix bugs in real open-source Python projects. We collected:
- each GitHub-style **issue**, which describes a bug;
- the **reference fix**, which is the patch the project's developers actually merged;
- the agent's attempt: its **trajectory**, i.e. its messages and commands, and its **submitted patch**.

Some tasks were deliberately changed, and parts of the data were produced by automatic tools. We need independent
human judgement on whether those changes and tools are correct. Your labels are the ground truth for the paper, so
**please judge on your own and say when you are unsure.**

---

## 2. Rules (please read)

1. **Work independently.** Don't discuss items with the other rater until both of you have finished.
2. **Don't use AI tools** (ChatGPT, Claude, Copilot chat, etc.) to read items or decide labels. Your labels must be
   human judgements. A search engine or the project's documentation is fine.
3. **Fill only these columns:** `rater` and the columns that start with `human_`. Leave every other column unchanged,
   and don't add, delete, reorder or sort rows. `row_id` is how we match your answers.
4. **`rater`:** put your initials on every row you label.
5. **Use the allowed values exactly** as written in section 5, in lower case. If you're not sure, write `unclear`;
   that's a useful answer, not a failure. Add a short reason in the `human_notes` column.
6. **Leave a cell empty** if you didn't look at that item.
7. **Save as CSV, UTF-8**, with the same file name. See section 3 for spreadsheet tips.

---

## 3. Setup

Unzip the package. You'll see:

```
REVIEWER_GUIDE.md            <- this file
exp03_c2_validity/           part A  (priority 1)
exp03_b2_fidelity/           part B  (priority 1)
exp03_pilot_c1/              part C  (priority 2)
exp02_paired_tasks/          part D  (priority 3)
exp02_parser_steps/          part E  (priority 4)
exp01v_parser_steps/         part F  (priority 4)
```

Each part folder has a `sheet.csv`, which is your answer sheet. Most parts also have an `items/` folder with one
sub-folder per row. The sheet's `folder` column names that sub-folder.

**Tools:**
- **Spreadsheet:** LibreOffice Calc, Google Sheets, or Excel. In Excel, open the file via *Data → From Text/CSV* so
  that ids aren't converted to numbers or dates, and save it as *CSV UTF-8*.
- **Text editor with diff colouring** for `.diff` files, e.g. VS Code. `.diff` files show removed lines with `-` and
  added lines with `+`.
- **JSON viewer** for trajectories. VS Code or Firefox works; Firefox shows JSON as a collapsible tree.

**How much to do:**
- **Main rater:** all rows of each part you're asked to do.
- **Second rater:** the **first 20% of rows** of each part (numbers below), unless told otherwise. Both raters
  label the same rows so we can measure agreement.

| Part | Rows | Second rater: rows | Time per row | Total (all rows) |
|---|---|---|---|---|
| A  C2 validity | 33 | 1–7 | 5–8 min | 3–4 h |
| B  B2 fidelity | 33 | 1–7 | 3–4 min | about 2 h |
| C  C1 already fixed | 54 | 1–11 | 2 min | 1.5–2 h |
| D  Paired tasks | 200 | 1–40 | about 1 min | 2–3 h |
| E  Exp02 parser steps | 24 | 1–5 | 1 min | 25 min |
| F  Exp01 parser steps | 24 | 1–5 | 1 min | 20 min |

"Rows" means rows by `row_id` order, i.e. the first rows of the sheet. Breaks are fine: save often and continue later.

---

## 4. Two task variants you need to understand

**B2 = reworded issue.** The issue text was rewritten in different words. Code, file names, identifiers, numbers and
quoted strings were kept character-for-character. *A good B2 asks for exactly the same fix as the original.*

**C2 = changed requirement.** A short "maintainer update" was added to the issue, saying that the required
behaviour is now different. New tests and a new reference fix were written for it, and these were already checked
by running them: the new fix passes the new tests and the old fix fails them. *A good C2 is a real, clear change,
and its tests check exactly what the update says, nothing more and nothing hidden.*

---

## 5. Instructions per part

### Part A: C2 validity (`exp03_c2_validity/`), priority 1

Files in `items/<folder>/`:

| File | Content |
|---|---|
| `issue.txt` | original issue |
| `requirement.txt` | the added maintainer update (the new requirement) |
| `gold_original.diff` / `gold_revised.diff` | reference fix for the original / the changed requirement |
| `tests_original.diff` / `tests_revised.diff` | tests for the original / the changed requirement |

Steps:
1. Read `issue.txt`, then `requirement.txt`.
2. Compare `gold_original.diff` with `gold_revised.diff` to see what the change does in the code.
3. Compare `tests_original.diff` with `tests_revised.diff`. Ask: would a developer who reads *only the issue and the
   update* know to write code that passes these tests?

| Column | Allowed values | Meaning |
|---|---|---|
| `human_change_meaningful` | `yes` / `trivial` / `no` | `yes`: a real design decision a maintainer could plausibly make. `trivial`: cosmetic, e.g. only renaming a message. `no`: nonsense, contradicts itself, or is not a change. |
| `human_requirement_unambiguous` | `yes` / `no` / `unclear` | `yes`: essentially one reasonable way to implement the new behaviour. `no`: several reasonable readings that would behave differently. |
| `human_tests_match_requirement` | `yes` / `no` / `unclear` | `yes`: the revised tests check what the update states. `no`: they check something the update doesn't say, e.g. an exact message, type or edge case that isn't mentioned. |
| `human_revised_fix_correct` | `yes` / `no` / `unclear` | Does `gold_revised.diff` implement the update sensibly, without unrelated changes? |
| `human_notes` | free text | Required when any answer isn't `yes`, e.g. "tests require exact error text not given in update". |

Example: the update says *"raise ValueError with the exact message 'Boolean data not supported'"* and the test checks
that message. That counts as `tests_match_requirement = yes`, because the exact text is given. If the update only
said "raise an error" and the test checked the exact text, it would be `no`.

### Part B: B2 fidelity (`exp03_b2_fidelity/`), priority 1

Files: `items/<folder>/original.txt` and `rewrite.txt`. Read them side by side.

| Column | Allowed values | Meaning |
|---|---|---|
| `human_same_requirements` | `yes` / `no` / `unclear` | Would a developer implement exactly the same fix from either text? |
| `human_information_added` | `none` / `hint` / `other` | `hint`: the rewrite adds a diagnosis or fix suggestion that the original doesn't have. `other`: other added content (say what in notes). |
| `human_information_removed` | `none` / `detail` / `other` | `detail`: the rewrite drops an expected or observed behaviour, a reproduction step, or a condition. |
| `human_natural` | `yes` / `no` | Does the rewrite read like a real issue a person would write? |
| `human_notes` | free text | Required when any answer is not the "good" one (`yes`, `none`, `none`, `yes`). |

Different wording, order or tone is fine. Only the *content* matters.

### Part C: C1 "already fixed" (`exp03_pilot_c1/`), priority 2

Setting: before the agent started, the bug had **already been fixed** in the code, but the agent received the
original issue anyway. The ideal behaviour is to check that the problem no longer occurs and to submit no real change.

Files in `items/<folder>/`:
- `trajectory.json`: the agent's conversation. Read the `messages` with role `assistant`; the messages with role
  `user` / `tool` are the environment's replies. The model is anonymised as "agent".
- `submission.txt`: what the agent finally submitted. It may be empty, a diff, or a sentence.
- `run_info.txt`: how the run ended. `Submitted` is normal; `LimitsExceeded` means it ran out of steps.

| Column | Allowed values | Meaning |
|---|---|---|
| `human_recognized_already_fixed` | `yes` / `no` / `unclear` | Does the agent say or show that the issue is already solved? |
| `human_verified_by_running` | `yes` / `no` / `unclear` | Did it run a reproduction or tests and see them pass *before* deciding? |
| `human_edit_necessary` | `no` / `yes` / `unclear` | Fill only if `submission.txt` changes code. Was any edit needed? Normally `no`, since the bug was already fixed. |
| `human_edit_effect` | `none` / `harmless` / `harmful` | `none`: no code change. `harmless`: redundant or cosmetic, e.g. a comment or re-applying the same fix. `harmful`: changes behaviour or would likely break something. |
| `human_format_failure_only` | `yes` / `no` | `yes` if the agent's decision was right but the submission is not a diff, e.g. just a sentence. |
| `human_notes` | free text | Optional. |

Tip: start at the *end* of the trajectory, where the decision usually is, then scroll back to check whether it ran
anything.

### Part D: paired tasks (`exp02_paired_tasks/`), priority 3

Each folder in `items/` is one task with `issue.txt`, `reference_fix.diff` and five submitted patches,
`submitted_M1.diff` … `submitted_M5.diff`, from five anonymised agents. Each sheet row is one (task, agent) pair:
open `folder` and the patch named by `model_code`. The repositories here are JavaScript, Go, Python and TypeScript.

Suggested workflow: open one task folder, read the issue and the reference fix once, then label its five rows.

| Column | Allowed values | Meaning |
|---|---|---|
| `human_localisation_correct` | `y` / `n` / `unclear` | `y` if the submitted patch edits the same functions or files as the reference fix, or a clearly equivalent place, e.g. the caller instead of the callee for the same logic. `n` if it edits the wrong part of the code. Whether the patch is *correct* doesn't matter, only *where* it edits. Use `n` for an empty patch. |
| `human_strategy_note` | free text | One sentence, e.g. "adds a null check in the same handler as the reference" or "edits only tests". |

### Part E: Exp02 parser steps (`exp02_parser_steps/`), priority 4

Each row is one "step" that a log parser extracted from an agent's log: `parsed_action` and, for context, the start
of the output it got back (`obs_excerpt`).

| Column | Allowed values | Meaning |
|---|---|---|
| `human_is_agent_action` | `yes` / `no` / `unclear` | Is `parsed_action` one action the agent actually executed (a command or tool call)? `no` if it's narration, a fragment of output, a system message, or several actions merged. |
| `human_expected_category` | `search` / `view` / `edit` / `test` / `run` / `vcs` / `install` / `submit` / `other` | `search`: grep / find / ls. `view`: open or print a file. `edit`: change a file. `test`: run tests. `run`: run a script or reproduction. `vcs`: git. `install`: pip / npm etc. `submit`: final submit. |
| `human_notes` | free text | Optional. |

### Part F: Exp01 parser steps (`exp01v_parser_steps/`), priority 4

Each row shows a step as extracted by two parsers: `author_step_example` and `role_step_example`.

| Column | Allowed values | Meaning |
|---|---|---|
| `human_is_role_step_a_real_agent_action` | `yes` / `no` / `unclear` | Is `role_step_example` a real agent action (a command or tool call the agent issued)? |
| `human_notes` | free text | Please also say whether `author_step_example` is a real action, e.g. "author step is narration, not an action". |

---

## 6. When you're done

1. Check that every row you labelled has your initials in `rater` and no typos in the allowed values.
2. Return the edited `sheet.csv` files. Keep the folder names, or rename each file to `<part>_<initials>.csv`,
   e.g. `exp03_c2_validity_AB.csv`.
3. Please also note, roughly, how many minutes each part took.

Questions about the *instructions*, e.g. what a column means, can go to the study contact. Please don't ask the other
rater about specific items.
