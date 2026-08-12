---
name: test-feature
description: Writes and runs tests for a specific TalentCaspian feature. Pass the spec name as argument e.g. /test-feature 03-caspian-setup
---

Instructions:
You are allowed to use the following tools:
- Pytest commands

Task:
Run the full testing pipeline for the feature specified in $ARGUMENTS.

If no argument is provided, stop immediately and say:
"Please provide a spec name. Usage: /test-feature <spec-name> e.g. /test-feature 03-caspian-setup"

If `.gemini/specs/$ARGUMENTS.md` does not exist, stop immediately and say:
"Spec file not found at .gemini/specs/$ARGUMENTS.md. Please check the spec name and try again."

---

## Step 1: Write Tests

Invoke the **portfolio-test-writer** subagent with the following context:

- Spec file to base tests on: 
  `.gemini/specs/$ARGUMENTS.md`
- Source files to read for structure:
  - `main.py`
  - `database/` directory
- Output test file to create:
  `tests/test_$ARGUMENTS.py`
- Instruction: Write tests based on what the spec says the feature SHOULD do. Do NOT derive test logic from reading the implementation. Cover happy paths, edge cases, FastAPI exception handlers, input validation errors, and DB side effects.

Wait for portfolio-test-writer to fully complete and confirm the test file has been written before proceeding to Step 2.

---

## Step 2: Run Tests

Once portfolio-test-writer has finished, invoke the **portfolio-test-runner** subagent with the following context:

- Test file to execute:
  `tests/test_$ARGUMENTS.py`
- Spec file for context:
  `.gemini/specs/$ARGUMENTS.md`
- Source files to analyze against when diagnosing failures:
  - `main.py`
  - `database/` directory
- Run command:
  `python -m pytest tests/test_$ARGUMENTS.py -v`
- Instruction: Run ONLY the specified test file. Do NOT run the full test suite. Analyze any failures by cross-referencing the test code, the spec, and the source files. Classify each failure as a bug or a missing feature.

---

## Handoff Rules

- Do NOT start Step 2 until Step 1 is fully complete
- Do NOT attempt to fix any code regardless of what the test results show
- Do NOT run any tests beyond `tests/test_$ARGUMENTS.py`
- If portfolio-test-writer reports it could not write the test file, stop and report the reason — do NOT proceed to Step 2

---

## Final Output

After both subagents complete, produce a combined summary:

### Testing Pipeline Report — $ARGUMENTS

**Step 1 — Tests Written**
- List each test written with a one-line description of which spec requirement it validates

**Step 2 — Test Results**
- Mirror the portfolio-test-runner's structured report

**Verdict**
One of:
- ✅ Ready for code review — all tests pass
- ❌ Needs fixes — list the failing tests and their root causes
