# Phase 3, Stage 6: a Georgia location and addendum

> **Project rule:** never commit, push, or open a PR without the owner's explicit OK for that action
> (see `CLAUDE.md`). Every "Propose the commit" step stops and waits.

**Goal:** Juniper Row opens an Atlanta store. Georgia employees see the handbook as it applies to
them, with Georgia's rules where they differ from the company's, and the retrieval eval proves
search keeps Georgia's rules to Georgia staff and other states' rules away from them.

**Why:** the owner lives in Georgia. Adding a fourth state also tests that the handbook, search,
and applicability rules scale beyond the three states they were built with.

**Parent plan:** [`2026-10-07-phase-3-handbook-and-retrieval.md`](2026-10-07-phase-3-handbook-and-retrieval.md).
Stage 6 follows its stages 1–5 and runs the same way: batches, a stop for the owner's OK after
each, one Sonnet implementer per batch, one combined review, and fixes written test first. Effort
`medium`; the legal research in batch A at `high`.

---

## Decisions (the owner's, 2026-10-13)

- **The company grows to about 145 people,** with about 25 at the new Atlanta store. Everyone who
  exists today keeps their name, manager, and location, so the new people are added after them.
- **No Georgia persona.** The four persona cards are designed screens. Georgia is covered by
  Atlanta employees in the directory and by Georgia askers in the retrieval eval.
- **In Georgia, all voting time is paid:** up to 2 hours on Election Day or an advance-voting day.
- **A company-wide lactation rule** joins section 3.3, generous enough to meet federal law and the
  states' rules, with California's and Colorado's checked so their addenda stay right.
- **The eleven lines of handbook links that put a § before an addendum's ID** (17 links) lose the
  §, in the same new handbook version (decided 2026-10-13, Stage 5).
- **The whole-phase review** (`/code-review high` against `8db9ef5`) runs after this stage.

## What Georgia law adds

Researched on 2026-10-13 from signed Georgia acts on gov.georgia.gov and legis.ga.gov, the Georgia
Department of Labor, and the U.S. Department of Labor. The official code site couldn't be fetched,
so each statute's current text was read from the most recent signed act that changed it. Every
figure gets its source line in the section that states it, checked again in batch A.

| Topic | Georgia | The company section | Addendum |
|---|---|---|---|
| Lactation (O.C.G.A. §34-1-6, revised 2020) | Paid break time of reasonable length, a private place that isn't a restroom, no age limit on the child; hardship exception only under 50 employees | 3.3 says nothing | **GA-3.3**, beside the new company rule |
| Voting (§21-2-404, revised 2023) | Up to 2 hours to vote on Election Day or an advance in-person voting day, on reasonable notice; the employer may set the hours; the old shift-time exception was repealed | 4.5 pays 2 hours only without 3 free hours while polls are open | **GA-4.5** |
| Jury duty and court (§34-1-3) | No discharge or penalty for attending court under a summons, subpoena, or court order; no pay requirement | 4.5 pays jury service, silent on protection | **GA-4.5** |
| Minimum wage and overtime | Federal law governs (the state law yields to the FLSA) | 3.2 follows federal law | none |
| Meal and rest breaks (adults) | None | 3.3 gives more | none |
| Pay frequency (§34-7-2) | At least twice a month | 3.4 pays every two weeks | none |
| Sick leave for family care (Family Care Act, §34-1-10, made permanent 2023) | Up to 5 days of earned sick leave a year for family | 4.3 gives 40 hours with no cap on family use | none (4.3 names Georgia beside Texas) |
| Family and medical leave | No state law for private employers | 5.1 company leave | none |

Left out, with reasons: military leave (the handbook has no section to supplement; backlogged with
a company section under federal USERRA), and anything the research marked unverified.

---

## Batches

### A: The handbook text (content only; the owner reads it before the PR)

- **Research, then write.** Re-read each Georgia source above; read California's and Colorado's
  lactation rules and the federal PUMP Act from their official pages, with dated source lines.
- **Company section 3.3** gains a lactation rule, generous at every location: paid break time,
  a private space that isn't a restroom, for as long as the employee needs it.
- **GA-3.3** (Georgia's specifics, if any remain once the company rule exists) and **GA-4.5**
  (court attendance is job-protected; up to 2 paid hours to vote on Election Day or an advance
  voting day, on reasonable notice). California or Colorado lactation addenda only if their rules
  still go beyond the company rule.
- **Cross-references:** the "State rules" paragraphs in 3.3 and 4.5 link the Georgia addenda; 4.3
  names Georgia beside Texas as a state with no sick leave law of its own; 1.1 and 5.1 describe
  four locations and about 145 people; 4.2 says the Atlanta store closes on the six company
  holidays (not the day after Thanksgiving).
- **The 17 links drop their §:** "[CA-5.1 California family and medical leave]".
- **`handbook.yaml`:** version `2026.10.1`, `GA: Georgia addendum` (in alphabetical order, so the
  API's grouping and the section order agree), and `atl: Atlanta store`.
- A Sonnet fact-checker re-reads every new source line against its page. The owner reads the new
  and changed sections.

### B: The Atlanta store in the seed

- `LOCATIONS` gains `atl` (Atlanta, GA, America/New_York, area code 404, two Atlanta ZIP codes),
  appended last so existing people's names and addresses don't change.
- About 25 people in Store Operations at Atlanta: a store manager reporting to the COO, an
  assistant manager, sales associates, and cashiers; hourly and salaried like Oakland. The name
  pools grow by about 25 names each.
- `holidays.py`: `atl` closes on the six company holidays.
- Tests that count 120 people, three locations, or 41 holidays, and the directory's facet tests,
  move to the new totals. The web app's directory reads its filters from the API, so only the
  browser tests that count 120 change.

### C: The new handbook version through search and the eval

- `STATE_NAMES` gains Georgia in the API's applicability code and the web app's labels.
- `make ingest` loads `2026.10.1`; new sandboxes pin it. `make embed` fills the handbook cache
  (about 1,000 new tokens, free).
- **The eval:** Georgia questions written before running anything, in employees' own words, as
  before: a Georgia hourly associate and a Georgia salaried manager, each Georgia addendum as the
  sole answer, a `location_code: atl` question, and negatives (Georgia staff never get California's
  or Colorado's sick leave; no one else gets Georgia's voting rule). `make embed` for the
  questions, then the run. The 90% gate and every negative must still pass.
- Tests that list exact section sets per persona, the 18 state-type-location combinations (now
  32), the expected state rules for 4.3, and the browser test's addendum order.

### D: The close

- `CHANGELOG.md`, the roadmap row and "Next" note, `docs/DATA-INVENTORY.md` (four locations, the
  new version), and the parent plan's execution notes.
- `make db && make check`, `make eval-retrieval`, my own screenshot comparison of the handbook
  list and a Georgia section as an Atlanta employee and as the personas, then `/code-review medium`
  on the branch, and the proposed commit and PR.
- **Then the whole-phase review:** `/code-review high` on `dev` against `8db9ef5`, limited to the
  application code, migrations, scripts, and config; real findings fixed in a small follow-up PR;
  the roadmap row marked Done, with the "Next" note on planning Phase 4 at effort `high`.

## Backlog

- **Military leave:** a company section under federal USERRA, then any state addenda (Georgia's
  §38-2-279 was not verified).
- **A Georgia persona,** if the owner wants one later, with a design pass on the landing page.

## Changes made during execution

Record here anything that differs from this plan, with the reason, and the test counts and eval
score at the close.

- **Lactation is its own company section, 5.4,** not part of 3.3, because 3.3 and CA-3.3 apply
  only to hourly staff and lactation rights cover salaried staff too (the owner's decision). 3.3
  and CA-3.3 are unchanged apart from the § fix. 5.2 and 5.3 point to 5.4.
- **California keeps an addendum, CA-5.4,** for what its law adds beyond the company rule: an
  hour of premium pay for each denial, the Labor Commissioner complaint right, a one-year window
  for retaliation complaints, and when the policy is handed out. Colorado and Georgia need no
  lactation addendum: the company rule meets or beats both. There is no GA-3.3.
- **Georgia's voting pay is the company's,** and GA-4.5 says so; Georgia law doesn't require it.
  The fact-check confirmed every figure and three wordings were tightened. California's §1031
  space rules were read from CA DIR's lactation page because leginfo blocks automated reading.
- **Atlanta's 25 people come from their own random stream** (`seed_stream = 1`), so the first
  120 people are unchanged; a golden test pins their names, phones, and addresses against the
  pre-Atlanta seed. Atlanta has 4 salaried and 21 hourly staff in Store Operations.
- **The eval's first run scored 98.5%** (66 of 67): "I'm back from leave and still pumping…"
  found 5.2 Parental leave. With the owner's OK, one sentence in 5.4 now says the same breaks and
  space are ready after parental or medical leave. The question is unchanged. **The score after:**
  100% (67 of 67), mean reciprocal rank 0.849, all 20 negatives passing, 87 questions in all.
- **Version 2026.10.1** was re-embedded after that sentence; the local database was reset because
  a loaded version never changes. Nothing had been released.
- **A browser test pinned the handbook's date** ("Oct 7 Handbook updated"); it now matches any
  date, so each new edition doesn't break it.
- **Tests at the close:** 884 API tests, 991 web unit tests, and 174 browser tests.
