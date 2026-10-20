"""The time-off engine: pure rules for counting leave days, PTO balances, and sick leave.

It imports no framework, reads no clock, and touches no database. The service gathers the inputs
and passes "today" in. Amounts are integer minutes, each with a label from `labels.label`, and
every result names the handbook sections it came from (`rules.RULES`).
"""
