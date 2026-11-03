Assistant `claude-opus-5-5`, safety check `claude-haiku-5-5`, judge `claude-sonnet-5-5`.

Three trials per set unless noted.

| Set | Result | Lowest trial | Other figures |
|---|---|---|---|
| Retrieval | Not run yet | - | - |
| Policy Q&A (Full run, Nov 5, 2026) | **97%** Program checks | 96% | - |
| Answer quality | Not run yet | - | - |
| Red team | Not run yet | - | - |
| Actions | Not run yet | - | - |
| Fairness (Nov 5, 2026) | **12 of 12** Groups consistent | Groups are judged across all trials. | No identity assumption in any trial<br>Judge equivalence 95% (lowest trial 93%)<br>Groups consistent by attribute: name 100%, parent 100%, religion 100%, age 100%, origin 100%, spouse 100%. |
| Escalation | Not run yet | - | - |
| Case summary | Not run yet | - | - |

### History of full runs

| Date | Model | Q&A | Unanswerable | Red team | Actions | Judge | Cost |
|---|---|---|---|---|---|---|---|
| Nov 5, 2026, 14:00 UTC | `claude-opus-5-5` | 97% | - | - | - | - | $13.50 |

These figures come from recorded eval runs. CI replays the recordings on every change, so it checks the app's handling, not the model.

The sets are small (206 items in the full set), so a single item can move a figure by more than a point.
