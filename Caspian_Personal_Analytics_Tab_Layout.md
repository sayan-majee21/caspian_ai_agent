**CASPIAN**

**Personal Analytics Tab**

Detailed Frontend Layout & UX Specification

| Purpose  Design a student-facing analytics workspace that makes each project’s quality, evolution, recruiter interest, and next actions understandable at a glance—without becoming a dense BI dashboard. |
| :---- |

*Source basis: Caspian Agent Info \+ Frontend Layout for Student Recruiter Portfolio*

# **1\. What this tab is supposed to do**

**\[Source-derived\]** The Student Page has three tabs: Personal Analytics, Search and Feed, and Add New Project. The Personal Analytics tab is explicitly intended to provide detailed analysis of every project, including summary, AI rating, commit/change history, rating changes, and recruiter suggestions.

| Design principle  Do not make the page feel like an admin analytics console. The student should be able to answer five questions quickly: What is my project? How good is it? Why did it get that score? Who is interested? What should I improve next? |
| :---- |

## **Primary outcomes**

* **Understand quality:** Show the overall AI rating and the underlying project metrics.  
* **Understand progress:** Show how the project and its rating have changed over time.  
* **Understand market fit:** Show recruiter interest and the types of recruiters attracted to the project.  
* **Understand feedback:** Surface recruiter suggestions and distinguish open, acknowledged, and acted-on feedback.  
* **Take action:** Turn analytics into a small number of concrete improvement suggestions.

## **What should NOT dominate the page**

* Raw GitHub commit logs.  
* Huge tables of every event.  
* Too many charts competing for attention.  
* A single unexplained AI score.  
* Recruiter data that could expose private details unnecessarily.

# **2\. Recommended page architecture**

The page should use a single vertical scroll with a sticky project selector. The hierarchy is intentionally: identity → score → evidence → trajectory → recruiter signal → actions.

| Priority | Section | Purpose | Visual weight |
| :---- | :---- | :---- | :---- |
| P0 | Project Header | Orient the student and select a project | High |
| P0 | AI Rating \+ Score Breakdown | Show quality and explain the rating | Highest |
| P1 | Project Summary | Explain what the project is | Medium |
| P1 | Project Evolution | Show commits/changes and rating trend | High |
| P1 | Recruiter Interest | Show demand and recruiter-fit patterns | High |
| P1 | Recruiter Suggestions | Turn feedback into visible action items | Medium |
| P2 | AI Suggestions | Recommend next improvements | Medium |
| P2 | Project Metadata | Provide technical context | Low |

## **Desktop wireframe — recommended**

┌─────────────────────────────────────────────────────────────────────────────┐  
│ Student: Krishna Mahajan        Project ▼     All Projects ▼    Search 🔎  │  
├─────────────────────────────────────────────────────────────────────────────┤  
│ PROJECT HEADER                                                               │  
│ Project Name                  AI RATING  87/100        Status: Active       │  
│ One-line description         ↑ \+6 since last review      Updated 2h ago    │  
├─────────────────────────────────────────────────────────────────────────────┤  
│ SCORE BREAKDOWN                                                              │  
│ Overall 87      \[Metric cards: Quality | Activity | Technical | Impact\]     │  
│                 \[compact horizontal contribution bars\]                      │  
├───────────────────────────────┬─────────────────────────────────────────────┤  
│ PROJECT SUMMARY                │ PROJECT EVOLUTION                           │  
│ 3–5 line AI summary            │ Rating trend line \+ commit activity         │  
│ Tags / technologies            │                                             │  
├───────────────────────────────┴─────────────────────────────────────────────┤  
│ RECRUITER INTEREST                                                            │  
│ Interest KPI cards \+ recruiter-type distribution \+ interest timeline         │  
├─────────────────────────────────────────────────────────────────────────────┤  
│ SUGGESTIONS & FEEDBACK                                                        │  
│ Priority cards: What recruiters said → Status → Student action               │  
├─────────────────────────────────────────────────────────────────────────────┤  
│ AI NEXT-STEPS                                                                │  
│ 3 actionable recommendations with expected impact                            │  
└─────────────────────────────────────────────────────────────────────────────┘

| Responsive rule  On mobile/tablet, convert the two-column middle area into a single stack. Keep AI Rating, current trend, and top recruiter signal above the fold. |
| :---- |

# **3\. Section-by-section specification**

## **3.1 Sticky Project Header**

**Goal:** Keep project identity and navigation visible while the student scrolls.

| Element | Design | Behavior |
| :---- | :---- | :---- |
| Student identity | Name \+ small avatar | Static |
| Project selector | Dropdown with project name, score, status | Switching updates entire page |
| Project status | Active / Inactive / Needs Update | Small pill |
| Last analyzed | Relative timestamp | Tooltip with exact time |
| Quick action | “View Repository” button | External GitHub link if available |

## **3.2 AI Rating — hero module**

| Recommended visual  Use one large circular progress/ring score rather than a giant gauge. The ring communicates the score instantly while leaving room for an explanation beside it. |
| :---- |

| Content | Example | Visual | Interaction |
| :---- | :---- | :---- | :---- |
| AI Rating | 87 / 100 | Large score ring | Hover/tap reveals rating definition |
| Change | \+6 vs previous analysis | Small upward indicator | Click opens rating history |
| Confidence | High / Medium / Low | Tiny label | Tooltip explains confidence |
| Classification | High-rated project | Status pill | Non-interactive |

Important: the score must be explainable. The student should never see “87” without being able to understand what contributed to it.

## **3.3 Metrics Score Breakdown**

**\[Source-derived\]** The backend concept includes several project metrics that contribute to a final score and determines which high-rated projects proceed to Agent 2\.

**\[Design recommendation\]** The frontend should expose these as 4–6 normalized dimensions. The exact metric names should be mapped to the final backend schema rather than invented in the UI.

| Metric slot | Recommended UI | What the student learns | Example copy |
| :---- | :---- | :---- | :---- |
| Metric A | Horizontal score bar | How strong this dimension is | Technical Quality · 91 |
| Metric B | Horizontal score bar | How strong this dimension is | Project Activity · 84 |
| Metric C | Horizontal score bar | How strong this dimension is | Documentation · 79 |
| Metric D | Horizontal score bar | How strong this dimension is | Impact / Relevance · 88 |
| Metric E | Optional | Only if backend supports it | Innovation · 83 |
| **Avoid radar-chart overload**  A radar chart looks attractive but becomes hard to compare and explain. Use bars as the primary visualization; optionally place a small radar view behind an “Explore metrics” drawer. |  |  |  |

# **4\. Project Summary module**

**\[Source-derived\]** Agent 1 creates a short write-up on the project and its details. This should become the source for the student-facing project summary.

## **Recommended card**

* Project title.  
* AI-generated 3–5 line summary.  
* Problem → Approach → Result structure where available.  
* Technology tags pulled from the project data.  
* Optional “What makes this project notable?” one-line insight.

| Readability rule  Keep the default summary under roughly 80–100 words. Add “Expand summary” for the full generated description. |
| :---- |

# **5\. Project Evolution: commits \+ rating history**

**\[Source-derived\]** The student’s personal analytics is intended to include commit/change history and rating changes. Agent 1 also analyzes repository changes and reflects them in the database.

## **Recommended visualization: combined timeline**

* **Top line:** AI rating over time as a simple line chart.  
* **Bottom activity strip:** Commit/change frequency represented as small vertical bars.  
* **Event markers:** Highlight major rating changes or meaningful repository updates.  
* **Tooltip:** Date \+ change summary \+ rating before/after.

**Example interpretation:** “Rating increased from 81 → 87 after the latest update. The change was associated with improved documentation and a new feature.”

| Do not show every commit by default  Show a compact 30–90 day activity window and let the student expand to the full history. This keeps the page readable. |
| :---- |

# **6\. Recruiter Interest module**

**\[Source-derived\]** Agent 2 identifies interested recruiters based on recruiter choice filters and creates customized outreach. The recruiter can also make suggestions, which are reflected back into the database.

## **What the student should see**

| Signal | Recommended visualization | Why it matters |
| :---- | :---- | :---- |
| Interested recruiters | Large KPI: count | Shows whether the project is attracting attention |
| Recruiter categories | Compact horizontal bars | Shows which hiring domains are interested |
| Interest trend | Small line/area sparkline | Shows whether interest is growing |
| Top matching interests | Tag chips | Makes recruiter-fit understandable |

## **Recruiter privacy / readability rule**

* Default view should emphasize aggregate interest, not recruiter identities.  
* If recruiter identity is intentionally exposed by the product, show it as a compact list rather than a full recruiter dashboard.  
* Use phrases such as “12 recruiters match this project” instead of exposing a long list immediately.  
* Make recruiter type/category more prominent than individual names.

## **Suggested visual layout**

┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────────┐  
│ 12           │  │ \+18%         │  │ Recruiter fit                         │  
│ Interested   │  │ Interest     │  │ Software  ████████████  62%          │  
│ recruiters   │  │ vs last      │  │ Data      ████████      41%          │  
└──────────────┘  └──────────────┘  │ AI/ML     ██████        31%          │  
                                     └──────────────────────────────────────┘

# **7\. Recruiter Suggestions & Feedback**

**\[Source-derived\]** Recruiter suggestions are stored and can later appear in suggestion history/replies. On the student page, these should be presented as actionable feedback rather than a raw message feed.

## **Suggestion card structure**

| Priority | Suggestion | Source | Status | Action |
| :---- | :---- | :---- | :---- | :---- |
| High | Add deployment documentation | Recruiter feedback | Open | Mark in progress |
| Medium | Explain model evaluation | Recruiter feedback | Acknowledged | View details |
| Low | Improve UI screenshots | Recruiter feedback | Done | View update |

## **Status system**

* **Open:** Feedback received but not yet acknowledged.  
* **Acknowledged:** Student has seen the feedback.  
* **In Progress:** Student is actively addressing it.  
* **Resolved:** Student has made a relevant project update.

| Best UX move  Sort suggestions by expected impact, not only by date. A student should immediately see the 2–3 feedback items most worth acting on. |
| :---- |

# **8\. AI Next-Step Suggestions**

**\[Design recommendation\]** Because Agent 1 evaluates project quality and changes over time, the frontend can convert those signals into concise improvement recommendations. These should be clearly labeled as AI-generated suggestions, not recruiter instructions.

## **Recommended format**

| Increase documentationYour project has strong activity but limited setup/documentation evidence. Add a short installation and usage guide. |
| :---- |

| Show measurable resultsAdd a metric or benchmark to make the project outcome easier for recruiters to evaluate. |
| :---- |

| Strengthen portfolio evidenceAdd screenshots or a short demo link so the project’s functionality is visible without opening the repository. |
| :---- |

## **Recommendation constraints**

* Maximum 3 recommendations in the default view.  
* Each recommendation should explain the reason, not merely issue an instruction.  
* If possible, show an expected effect such as “could improve documentation metric”.  
* Avoid generic advice that cannot be traced to a project signal.

# **9\. Project Metadata — low visual priority**

**\[Source-derived\]** The project data originates from sources including GitHub and Kaggle. The analytics page should provide a compact technical metadata row/card without allowing metadata to overwhelm the analysis.

| Metadata | Example | UI |
| :---- | :---- | :---- |
| Source | GitHub / Kaggle | Icon \+ label |
| Languages | Python, C++, SQL | Tag chips |
| Repository activity | 142 commits | Small KPI |
| Last update | 2 hours ago | Timestamp |
| Project age | 8 months | Small stat |

# **10\. Interaction model**

| Interaction | Result | Animation | Why |
| :---- | :---- | :---- | :---- |
| Switch project | Entire analytics refreshes | Fast fade/skeleton | Avoid page navigation |
| Click AI rating | Open metric explanation drawer | Slide-in | Explainability |
| Click rating trend point | Show analysis/change event | Tooltip/popover | Connect score to events |
| Expand summary | Reveal full summary | Height transition | Preserve scanability |
| Open suggestion | Expand feedback \+ context | Inline accordion | Avoid new page |
| View recruiter signal | Expand aggregate detail | Inline expansion | Keep default view light |

# **11\. Visual design system**

## **Color semantics**

| Use | Suggested color family | Rule |
| :---- | :---- | :---- |
| Primary UI | Deep navy / blue | Navigation, headings, main CTA |
| Positive | Green | Improvement, high score, resolved |
| Attention | Amber | Medium priority, needs attention |
| Negative | Red | Decline or critical issue only |
| Neutral | Slate / light gray | Metadata and secondary content |

## **Typography hierarchy**

* Project name: largest text on the page.  
* AI Rating: visually dominant numeric element.  
* Section headings: consistent and compact.  
* Metric labels: medium weight; values: bold.  
* Supporting explanations: smaller but never tiny.

## **Chart rules**

* Prefer 1–2 meaningful charts per viewport.  
* Always label the metric and time period.  
* Avoid 3D charts and decorative gradients.  
* Use tooltips for detail instead of putting every value on the chart.  
* Keep axes and legends minimal.

# **12\. Information hierarchy: what appears above the fold**

**\[Recommended\]** At 1366×768 desktop resolution, the first viewport should show enough information to make the page useful without scrolling.

1. Project name \+ status \+ last analyzed time.  
2. AI Rating and change from previous rating.  
3. Top 4 metric scores or a compact score breakdown.  
4. One-line project summary.  
5. One recruiter-interest KPI.

| The first viewport test  If a student cannot understand the project’s current quality and whether recruiters care about it within 5–8 seconds, the page is too dense or the hierarchy is wrong. |
| :---- |

# **13\. Suggested final page flow**

**01  Project selector \+ header**  
**↓**  
**02  AI Rating hero \+ rating change**  
**↓**  
**03  Metric score breakdown**  
**↓**  
**04  Project summary \+ technologies**  
**↓**  
**05  Project evolution: rating trend \+ activity**  
**↓**  
**06  Recruiter interest: count \+ categories \+ trend**  
**↓**  
**07  Recruiter suggestions: prioritized action cards**  
**↓**  
**08  AI next steps: max 3 recommendations**  
**↓**  
**09  Technical metadata / full history**

# **14\. Backend-to-frontend data contract to plan for**

**\[Design implication\]** The frontend specification should not invent backend fields. The following is a recommended UI-facing shape that maps directly to the concepts already described in the project documents.

| UI module | Minimum data needed | Fallback if missing |
| :---- | :---- | :---- |
| Header | project\_name, status, last\_analyzed | Hide unavailable field |
| AI rating | overall\_score, score\_change | Show score only |
| Metric breakdown | metrics\[{name, score}\] | Show available metrics |
| Summary | summary | “Summary unavailable” |
| Evolution | rating\_history\[\], activity\_history\[\] | Show available series |
| Recruiter interest | interest\_count, categories\[\] | Show aggregate count only |
| Suggestions | suggestions\[{text, priority, status, source}\] | Empty-state card |
| AI next steps | recommendations\[\] | Do not fabricate recommendations |

# **15\. Empty, loading, and edge states**

| State | UI treatment | Message |
| :---- | :---- | :---- |
| First analysis running | Skeleton cards \+ progress status | “Caspian is analyzing this project…” |
| No recruiter interest | Neutral empty state | “No recruiter matches yet. Improve project signals to increase discoverability.” |
| No recruiter suggestions | Quiet empty card | “No recruiter feedback yet.” |
| No rating history | Single score, no chart | “Rating history will appear after future analyses.” |
| Repository unavailable | Warning banner | “Repository could not be refreshed. Showing last available analysis.” |

# **16\. Final recommended component inventory**

| Component | Count | Priority | Notes |
| :---- | :---- | :---- | :---- |
| Project selector/header | 1 | P0 | Sticky |
| AI rating ring | 1 | P0 | Hero |
| Metric cards/bars | 4–6 | P0 | Backend-driven |
| Summary card | 1 | P1 | Expandable |
| Rating \+ activity chart | 1 | P1 | Combined timeline |
| Recruiter KPI cards | 2–3 | P1 | Aggregate first |
| Recruiter category chart | 1 | P1 | Bars |
| Suggestion cards | 0–N | P1 | Prioritized |
| AI recommendation cards | 3 | P2 | Maximum 3 visible |
| Metadata card | 1 | P2 | Collapsible |

# **17\. One-screen design summary**

| The page should feel like a “project health report”, not a spreadsheet.  The student opens the page, immediately sees the AI rating and why it is high/low, understands how the project has evolved, sees whether recruiters are interested, and receives a short prioritized list of things to improve. |
| :---- |

## **Recommended visual balance**

* ≈ 30%: rating \+ metric evidence  
* ≈ 20%: project summary/context  
* ≈ 20%: evolution/history  
* ≈ 20%: recruiter interest \+ feedback  
* ≈ 10%: AI next steps \+ metadata

## **Source-grounding note**

**\[Source-derived constraints\]** The project documents establish GitHub/Kaggle as input sources; Agent 1 as the project-analysis, update-analysis, rating/classification, and project-summary layer; Agent 2 as the recruiter-matching and customized-outreach layer; and the Student Page Personal Analytics tab as the location for project summary, AI rating, commit/change history, rating changes, and recruiter suggestions.

**\[Design additions in this document\]** The exact visual hierarchy, charts, component behavior, privacy presentation, empty states, responsive behavior, and AI recommendation presentation are UX recommendations intended to make those requirements usable.

**END OF SPECIFICATION**