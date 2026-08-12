---
name: code-review-feature
description: Runs parallel security and quality code review for a specific TalentCaspian feature. Pass the spec name as argument e.g. /code-review-feature 03-caspian-setup
---

# Instructions
You are allowed to use the following tools:
- Read, Write, Glob, Shell Commands

Argument hint: "Spec name e.g. 03-caspian-setup"

## Task
Perform a multi-dimensional code review on the changes introduced by the specified spec.

### Step 1: Pre-flight checks
- Check if git working directory has unstaged/staged changes.
- Identify the files modified in this feature branch compared to `main`.

### Step 2: Quality Review
Invoke `portfolio-quality-reviewer` to run a static check on the modified files to verify compliance with TalentCaspian PEP 8 standards, async/await usages in FastAPI, and database dependency injections.

### Step 3: Security Review
Invoke `portfolio-security-reviewer` to scan the changed files for SQL injection, CSRF vulnerabilities on API endpoints, and safe handling of Caspian credentials.

### Step 4: Combine & Report
Merge the quality and security review reports into a single, unified Markdown report detailing the findings, and prompt the user to proceed.
