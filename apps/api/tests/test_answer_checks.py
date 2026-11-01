"""`says_not_found`, the one check on a finished answer that the app and the evals share.

The sentences are the ones the Q&A grader tests (`test_qa_graders.py`) cover through
`grade_unanswerable`, now asked directly: the turn labels a console row `not_found` by the same
function, so it has tests of its own.
"""

import pytest

from app.ai import answer_checks
from app.ai.answer_checks import normalize, says_not_found
from tests.assistant_eval import load_graders


@pytest.mark.parametrize(
    "sentence",
    [
        "I couldn't find a rule in the handbook about trading days.",
        "I could not find anything in the handbook on that.",
        "I can't find that in the handbook.",
        "I cannot find a policy for this in the employee handbook.",
        "I didn't find anything about it in the handbook.",
        "I did not see that anywhere in the handbook.",
        "Sorry, I couldn" + chr(0x2019) + "t see a rule about that in the Handbook.",
        "I COULDN'T FIND IT IN THE EMPLOYEE HANDBOOK.",
        "I couldn't\nfind   a thing in the handbook.",
        "I don't see anything in the handbook about pet insurance; HR can help.",
        "I do not find a rule in the handbook for that.",
        "I don" + chr(0x2019) + "t see a policy about it in the employee handbook.",
        "I wasn't able to find that in the handbook.",
        "I was not able to find anything about it in the employee handbook.",
        "I'm unable to find a rule in the handbook on that.",
        "Unable to find it in the handbook, sorry.",
        "I'm not able to find that in the handbook.",
        "I couldn't find that in our handbook.",
        "I couldn't find that in this handbook.",
        "I couldn't find that in the company handbook.",
        "I couldn't find that in the Juniper Row handbook.",
        "I couldn't find anything about pet bereavement in the handbook's leave policies.",
        "I couldn't find a pet insurance policy in the handbook; the closest is the benefits"
        " overview [1].",
        "I couldn't find that in the handbook, which says nothing about pet insurance.",
        "When you asked about pets, I couldn't find anything in the handbook.",
        "Whether you're full-time or part-time, I couldn't find a rule in the handbook.",
        "I searched, but couldn't find anything about pet insurance in the handbook.",
        "I also couldn't find anything in the handbook about that.",
        "I wasn't able to locate anything in the handbook on that.",
        "I couldn't find that in Juniper Row's handbook.",
        "I couldn't find anything on section 4.3 in the handbook.",
        "I couldn't find a 3.5 percent rule in the handbook, e.g. for parking.",
        "I couldn't find the pto vs. vacation rule in the handbook.",
        # The smoke run of 2026-10-25 (qa-47): 56 characters between "find" and "in the handbook".
        "I couldn't find anything about parking validation or paying for parking in the handbook.",
        # The full run of 2026-10-29 (qa-51, qa-54): the handbook named before "couldn't find".
        "I searched the handbook twice and couldn't find anything about an employee discount on"
        " Juniper Row merchandise.",
        "I searched the handbook and couldn't find a rule about pets or bringing dogs to work.",
        "I looked through the handbook but didn't find a pet rule.",
    ],
)
def test_close_paraphrases_of_the_not_found_statement_are_found(sentence: str) -> None:
    assert says_not_found(f"{sentence} Ask the HR team.") is True


@pytest.mark.parametrize(
    "sentence",
    [
        "I found it in the handbook.",
        "You can find it in the handbook.",
        "I couldn't say. Look in the handbook.",
        "I couldn't find anything. The handbook may help.",
        "It is in the handbook, so you won't have trouble finding it.",
        "I didn't look in the handbook.",
        "I couldn't find that" + " " + "x" * 120 + " in the handbook.",
        "I couldn't" + " " + "x" * 120 + " find that in the handbook.",
        "I couldn't help with that. You can find it in the handbook.",
        "I couldn't find it. It is in the handbook.",
        "I couldn't tell you! Please see the section in the handbook.",
        "I don't think the handbook covers that.",
        "I do not know what the handbook says.",
        "I wasn't able to help with that. You can find it in the handbook.",
        "I'm unable to help. Please find it in the handbook.",
        "I don't see why not. It is in the handbook.",
        "I don't see that" + " " + "x" * 120 + " in the handbook.",
        "I couldn't find that. Section 4.3 is in the handbook.",
        "I couldn't find that! Look in the handbook.",
        "I couldn't find that? It is in our handbook.",
        "I couldn't find that in the way of the big old handbook.",
        "I couldn't find that in a long list of other things like the handbook.",
        "I don't have the details, but you can find them in the handbook.",
    ],
)
def test_statements_that_are_not_a_not_found_statement_are_not(sentence: str) -> None:
    assert says_not_found(f"{sentence} Ask the HR team.") is False


@pytest.mark.parametrize(
    "sentence",
    [
        "When I looked, I couldn't find that in the handbook, so please ask HR.",
        "Once I searched, I couldn't find it in the handbook.",
    ],
)
def test_a_when_or_once_clause_about_the_assistant_is_still_a_not_found_statement(
    sentence: str,
) -> None:
    assert says_not_found(f"{sentence} Ask HR.") is True


@pytest.mark.parametrize(
    "answer",
    [
        "You get 5 days of bereavement leave [1]. If you can't find the details in the handbook, "
        "ask HR.",
        "When you can't find a rule in the handbook, ask HR.",
        "Unless you can't find it in the handbook, you get 5 days [1]. Ask HR.",
        "You can't find that in the handbook. Ask HR.",
    ],
)
def test_a_not_found_phrase_about_the_reader_is_not_the_assistants_statement(answer: str) -> None:
    assert says_not_found(answer) is False


def test_an_empty_answer_says_nothing() -> None:
    assert says_not_found("") is False


def test_zero_width_characters_do_not_hide_the_statement() -> None:
    assert says_not_found("I couldn't f" + chr(0x200B) + "ind that in the handbook.") is True


def test_normalize_folds_forms_removes_format_characters_and_flattens_dashes() -> None:
    text = "5" + chr(0x2013) + "7" + chr(0x00A0) + "da" + chr(0x200B) + "ys" + chr(0xFF11)

    assert normalize(text) == "5-7 days1"


def test_the_evals_graders_use_this_function_and_hold_no_pattern_of_their_own() -> None:
    graders = load_graders()

    assert graders.says_not_found is answer_checks.says_not_found
    assert graders.normalize is answer_checks.normalize
    assert not hasattr(graders, "_NOT_FOUND")
    assert not hasattr(graders, "_SEARCHED_NOT_FOUND")
