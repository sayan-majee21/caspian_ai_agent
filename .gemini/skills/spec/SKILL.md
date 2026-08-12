---
name: spec
description: Create a spec file and feature branch for the next TalentCaspian step
---

# Instructions
You are allowed to use the following tools:
- Read, Write, Glob, Git Commands

Argument hint: "Step number and feature name e.g. 1 database"

## Task
You are a senior developer spinning up a new feature for the TalentCaspian portfolio tracker. Always follow the rules in GEMINI.md.

User input: $ARGUMENTS

### Step 1 — Check working directory is clean
Run `git status` and check for uncommitted, unstaged, or untracked files. If any exist, stop immediately and tell the user to commit or stash changes before proceeding.
DO NOT CONTINUE until the working directory is clean.

### Step 2 — Parse the arguments
From $ARGUMENTS extract:
1. `step_number` — zero-padded to 2 digits: 1 → 01, 8 → 08
2. `feature_title` — human readable title in Title Case
3. `feature_slug` — git and file safe slug

If you cannot infer these from $ARGUMENTS, ask the user to clarify before proceeding.

### Step 3 — Check branch name is not taken
Run `git branch` to list existing branches. If `branch_name` is already taken, append a number.

### Step 4 — Switch to main and pull latest
Run:
```
git checkout main
git pull origin main
```

### Step 5 — Create and switch to the feature branch
Run:
```
git checkout -b <branch_name>
```

### Step 6 — Research the codebase
Read these files before writing the spec:
- `GEMINI.md` — roadmap, conventions, schema
- `main.py` — existing routes and structure
- `database/db.py` — existing schema and functions
- All files in `.gemini/specs/` — avoid duplicating existing specs

### Step 7 — Write the spec
Generate a spec document with the structure defined in project conventions.

### Step 8 — Save the spec
Save to: `.gemini/specs/<step_number>-<feature_slug>.md`

### Step 9 — Report to the user
Print a short summary and instructions for Plan Mode.
