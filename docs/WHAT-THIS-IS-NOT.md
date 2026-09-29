# What this is not

Open Door is deliberately narrow. This document lists what it does not do, what its assistant will
never do, and what its evidence does not prove. It exists because a demo that seems to do everything
invites the question of what it actually does well. Most of what follows is a decision, not a gap,
and where something is an open question it says so.

---

## Not an HR system

Open Door is a help desk with a thin, well-built HR core under it. It does not include:

- **Recruiting or applicant tracking.** That overlaps the owner's Smart Resume Builder, and hiring
  decisions are exactly where AI use is most regulated.
- **Payroll, compensation, or timesheets.** There is no salary data at all in v1. Hourly and
  salaried staff differ only in how their time off accrues.
- **Onboarding or benefits enrollment.** These are possible later modules, not v1.
- **Performance reviews.** The EU AI Act treats AI used to evaluate workers as high-risk, and this
  project keeps the assistant out of that space on purpose.
- **Company sign-up, SSO, or SCIM provisioning.** Every visitor gets a generated sandbox company.
  Real identity integration is a stretch goal.
- **A handbook editor.** The handbook is authored in the repository and pinned per sandbox.

---

## What the assistant will never do

- **Decide who can see what.** Permissions are enforced in code and in the database. Asking
  cleverly does not change what a tool returns.
- **Calculate a balance or a duration.** The time-off engine does that. The assistant explains the
  engine's numbers and cites the policy behind them.
- **Change anything on its own.** It proposes. A person confirms, and the server re-checks before
  anything is saved.
- **State a policy without a source.** If the handbook does not cover a question, the assistant says
  so and offers to connect you with HR.
- **Make or recommend an employment decision.** No discipline, no termination, no ratings, no
  opinion on how a case should end.
- **Counsel you on a sensitive matter.** Harassment, discrimination, medical, legal, and safety
  topics go to a human. Crisis situations get fixed, human-written guidance, including the 988
  Suicide & Crisis Lifeline.
- **Remember you between conversations.** Each conversation stands alone.
- **Pretend to be a person.** Every assistant surface says it is an AI.

---

## Not legal advice

The company, its people, and its handbook are fictional. Where the handbook's state addenda quote
a figure from real law (sick-leave entitlements in California and Colorado, for example), the
figure records its source and the date it was read. Laws change, and the handbook is a demo. It is
not guidance for any real employer or employee.

**Do not enter real personal information.** Sandboxes, and every conversation in them, are deleted
after 24 hours. The app warns you if a message looks like it contains a Social Security or card
number.

---

## What the evidence does not prove

- **Offline evals in CI replay recorded responses.** They prove the graders and the plumbing work,
  not that the model answers well today. Live eval runs, with at least three trials and the
  variance reported, are the evidence about the model, and the scoreboard says which is which.
- **A clean red-team score is not a security guarantee.** It means the attacks in the set failed.
  New attacks are added as they are found.
- **Rubric-judged scores depend on the judge.** The judge is validated against hand-labeled answers,
  and that agreement rate is published next to the score.
- **Retrieval results are measured on a small, purpose-built handbook.** About twenty sections is a
  real test of applicability filtering and citation accuracy, not of scale.
