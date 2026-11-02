Assistant `claude-opus-5-5`, safety check `claude-haiku-5-5`, judge `claude-sonnet-5-5`.

Three trials per set unless noted.

| Set | Result | Lowest trial | Other figures |
|---|---|---|---|
| Retrieval (Handbook 2026.11.2) | **100%** Hit rate at 5 | No trials: retrieval is exact. | Every negative passed. |
| Policy Q&A (Full run, Oct 29, 2026) | **97%** Program checks | 96% | Unanswerable 93%, lowest 90% |
| Answer quality (Oct 29, 2026) | **68%** Judge pass rate | 65% | Target 85%<br>18 uncited claims<br>Judge agreement with the hand grades 89.7% (below the 90% bar) |
| Red team (Oct 29, 2026) | **100%** In every trial | 100% | All six groups at 100%: actions, cases, injection, private details, prompt extraction, routing. |
| Actions (Oct 29, 2026) | **99%** Pass rate | 97% | Numbers match the engine 100% |
| Fairness | Not run yet | - | - |
| Escalation (Oct 27, 2026) | **100%** Crisis recall | 100% | Sensitive recall 100%<br>Ordinary questions offered no case 100% |
| Case summary (Oct 30, 2026) | **22 of 22** Passed every check | 22 of 22 | By the judge: 22 of 22 |

### History of full runs

| Date | Model | Q&A | Unanswerable | Red team | Actions | Judge | Cost |
|---|---|---|---|---|---|---|---|
| Oct 19, 2026, 15:22 UTC | `claude-opus-5-5` | 100% | 100% | 100% | - | 74% | $8.02 |
| Oct 25, 2026, 16:04 UTC | `claude-opus-5-5` | 100% | 100% | 97% | 96% | 72% | $10.39 |
| Oct 29, 2026, 14:23 UTC | `claude-opus-5-5` | 97% | 93% | 100% | 99% | 68% | $10.93 |

Actions joined the full set on Oct 25, 2026.

These figures come from recorded eval runs. CI replays the recordings on every change, so it checks the app's handling, not the model.

The sets are small (166 items in the full set), so a single item can move a figure by more than a point.
