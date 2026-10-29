"""The seed company's fixed data: its locations, departments, org chart, and name lists.

The company is fictional, and so is everything about its people. Personal emails use example.com,
phone numbers use 555-0100 to 555-0199, which are reserved for fiction, and street addresses are
made up. seed.py turns this data into rows.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time

# Every other choice (who gets which name, phone number, and address, and the dates of everyone
# not named below) comes from this seed, so every sandbox gets exactly the same company.
SEED = 20261003
# Time off draws from the stream SEED + 2 (see `build_company` in seed.py), so no location may
# take that stream number. Changing it would reshuffle all seeded history.
TIME_OFF_STREAM = 2

# .example and example.com are reserved for documentation (RFC 2606), so no message sent to these
# addresses can reach anyone.
WORK_EMAIL_DOMAIN = "juniperrow.example"
PERSONAL_EMAIL_DOMAIN = "example.com"


# The ISO weekdays people work: 1 is Monday, 7 is Sunday. Sorted, as they are stored.
MONDAY_TO_FRIDAY = (1, 2, 3, 4, 5)
SUNDAY_TO_THURSDAY = (1, 2, 3, 4, 7)
TUESDAY_TO_SATURDAY = (2, 3, 4, 5, 6)
WEDNESDAY_TO_SUNDAY = (3, 4, 5, 6, 7)
# The stores are open all week, so their staff rotate through these, in this order, one after
# another by seat order (see `_seats` in seed.py). A seat with a `weekdays` of its own skips the
# rotation and doesn't use up a turn.
STORE_ROTATION = (TUESDAY_TO_SATURDAY, SUNDAY_TO_THURSDAY, WEDNESDAY_TO_SUNDAY, MONDAY_TO_FRIDAY)


@dataclass(frozen=True, slots=True)
class LocationSpec:
    code: str
    name: str
    city: str
    state: str
    timezone: str
    # For the fictional phone numbers and addresses of the people who work there.
    area_code: str
    zip_codes: tuple[str, ...]
    # Which random stream draws this location's phone numbers: 0 is the original stream, and each
    # location opened later takes the next number, drawing from SEED + that number (see seed.py).
    # Number 2 is taken by time off (TIME_OFF_STREAM), so the next new location must skip it.
    # A location of its own stream leaves everyone who already existed exactly as they were.
    seed_stream: int = 0
    # The weekdays of everyone here whose seat doesn't set its own: each seat takes the next entry,
    # round and round. Most locations have a single entry, so everyone works the same days.
    rotation: tuple[tuple[int, ...], ...] = (MONDAY_TO_FRIDAY,)


LOCATIONS = (
    LocationSpec("den", "Denver HQ", "Denver", "CO", "America/Denver", "303", ("80203", "80211")),
    LocationSpec(
        "oak",
        "Oakland store",
        "Oakland",
        "CA",
        "America/Los_Angeles",
        "510",
        ("94606", "94610"),
        rotation=STORE_ROTATION,
    ),
    LocationSpec(
        "aus", "Austin warehouse", "Austin", "TX", "America/Chicago", "512", ("78702", "78745")
    ),
    LocationSpec(
        "atl",
        "Atlanta store",
        "Atlanta",
        "GA",
        "America/New_York",
        "404",
        ("30308", "30309"),
        seed_stream=1,
        rotation=STORE_ROTATION,
    ),
)


@dataclass(frozen=True, slots=True)
class PersonSpec:
    """Who fills a seat: a name, and dates counted back from the sandbox's anchor date.

    The people the demo and the evals talk about are written out below, with fixed dates, so an
    answer that depends on tenure never changes. Everyone else is drawn from the seed.
    """

    given_name: str
    family_name: str
    hired_days_ago: int
    born_days_ago: int
    persona_key: str | None = None
    is_hr_admin: bool = False


@dataclass(frozen=True, slots=True)
class Position:
    """A seat in the org chart, or `seats` identical seats under the same manager.

    `key` is stable: the person's ID is made from it, and naming it as another position's
    `manager` makes the reporting line. The people in a position with several seats get the keys
    `key-1`, `key-2`, and so on, so such a position can't be anyone's manager. A position without
    a `person` gets someone drawn from the seed.

    `weekdays` is the ISO weekdays everyone in the position works. Without it, they work their
    location's rotation: Monday to Friday, or at a store whichever of the rotation's turns is next.
    """

    key: str
    title: str
    manager: str | None
    employment_type: str = "salaried"
    seats: int = 1
    person: PersonSpec | None = None
    weekdays: tuple[int, ...] | None = None


DANA = PersonSpec("Dana", "Whitfield", 1650, 15200, persona_key="dana", is_hr_admin=True)
MARCUS = PersonSpec("Marcus", "Bell", 2400, 16000, persona_key="marcus")
PRIYA = PersonSpec("Priya", "Raman", 1160, 11400, persona_key="priya")
LEO = PersonSpec("Leo", "Nakamura", 700, 9600)
MATEO = PersonSpec("Mateo", "Alvarez", 520, 10300, persona_key="mateo")

HOURLY = "hourly"

# The seats the demo's time-off story is about. Leo was out last week, from Wednesday to Friday, so
# "Why was Leo out last week?" has an answer, and Zara Bautista (Marcus's direct report, the
# design's sample) has the one request waiting for him, so "Anything waiting on me?" does too.
LAST_WEEK_PTO_SEAT = "leo"
PENDING_REQUEST_SEAT = "oak-apparel-lead"

# Each department-and-location pair is one group of seats here; Store Operations runs both stores.
# Denver HQ has 40 people, the Oakland store 45, the Austin warehouse 35, and the Atlanta store 25.
# Managers come before their reports. The Atlanta store is last, so it adds people without
# changing anyone before it.
ORG: dict[tuple[str, str], tuple[Position, ...]] = {
    ("Executive", "den"): (
        Position("ceo", "Chief Executive Officer", None),
        Position("coo", "Chief Operating Officer", "ceo"),
        Position("executive-assistant", "Executive Assistant", "ceo"),
    ),
    ("Human Resources", "den"): (Position("dana", "HR Business Partner", "ceo", person=DANA),),
    ("Finance", "den"): (
        Position("cfo", "Chief Financial Officer", "ceo"),
        Position("controller", "Controller", "cfo"),
        Position("accountant", "Accountant", "controller", seats=3),
        Position("payroll", "Payroll Specialist", "controller"),
        Position("payables", "Accounts Payable Specialist", "controller"),
        Position("financial-analyst", "Financial Analyst", "cfo", seats=2),
    ),
    ("Information Technology", "den"): (
        Position("it-director", "Director of IT", "ceo"),
        Position("sysadmin", "Systems Administrator", "it-director", seats=2),
        Position("engineer", "Software Engineer", "it-director", seats=3),
        Position("it-support", "IT Support Specialist", "it-director", seats=2),
        Position("data-analyst", "Data Analyst", "it-director"),
    ),
    ("Merchandising", "den"): (
        Position("merchandising-vp", "VP of Merchandising", "ceo"),
        Position("senior-buyer", "Senior Buyer", "merchandising-vp"),
        Position("buyer", "Buyer", "merchandising-vp", seats=3),
        Position("assistant-buyer", "Assistant Buyer", "senior-buyer", seats=2),
        Position("planner", "Merchandise Planner", "merchandising-vp"),
        Position("allocation", "Allocation Analyst", "merchandising-vp"),
    ),
    ("Marketing", "den"): (
        Position("marketing-director", "Director of Marketing", "ceo"),
        Position("marketing-manager", "Marketing Manager", "marketing-director"),
        Position("designer", "Graphic Designer", "marketing-manager", seats=2),
        Position("copywriter", "Copywriter", "marketing-manager"),
        Position("social", "Social Media Specialist", "marketing-manager"),
        Position("ecommerce", "E-commerce Specialist", "marketing-director", seats=2),
        Position("marketing-coordinator", "Marketing Coordinator", "marketing-manager"),
    ),
    # Marcus runs the store. Priya, Leo, and three department leads report to him directly, and
    # the leads manage everyone else, so he has reports both directly and through the leads.
    # Priya and Leo manage no one.
    ("Store Operations", "oak"): (
        Position("marcus", "Store Manager", "coo", person=MARCUS, weekdays=MONDAY_TO_FRIDAY),
        Position("priya", "Visual Merchandiser", "marcus", person=PRIYA, weekdays=MONDAY_TO_FRIDAY),
        Position(
            "leo", "Sales Associate", "marcus", HOURLY, person=LEO, weekdays=WEDNESDAY_TO_SUNDAY
        ),
        Position("oak-apparel-lead", "Department Lead, Apparel", "marcus"),
        Position("oak-apparel", "Sales Associate", "oak-apparel-lead", HOURLY, seats=13),
        Position("oak-home-lead", "Department Lead, Home", "marcus"),
        Position("oak-home", "Sales Associate", "oak-home-lead", HOURLY, seats=12),
        Position("oak-front-end", "Front End Lead", "marcus"),
        Position("oak-cashier", "Cashier", "oak-front-end", HOURLY, seats=10),
        Position("oak-service", "Customer Service Associate", "oak-front-end", HOURLY, seats=4),
    ),
    ("Distribution", "aus"): (
        Position("aus-manager", "Warehouse Manager", "coo"),
        Position("aus-inventory", "Inventory Control Specialist", "aus-manager", HOURLY, seats=2),
        Position("aus-shipping", "Shipping Coordinator", "aus-manager"),
        Position("aus-days", "Shift Supervisor, Days", "aus-manager"),
        Position("mateo", "Warehouse Associate", "aus-days", HOURLY, person=MATEO),
        Position("aus-day-crew", "Warehouse Associate", "aus-days", HOURLY, seats=12),
        Position("aus-day-forklift", "Forklift Operator", "aus-days", HOURLY, seats=2),
        # The night crew works Sunday to Thursday. A night shift counts on the date it starts.
        Position(
            "aus-nights", "Shift Supervisor, Nights", "aus-manager", weekdays=SUNDAY_TO_THURSDAY
        ),
        Position(
            "aus-night-crew",
            "Warehouse Associate",
            "aus-nights",
            HOURLY,
            seats=12,
            weekdays=SUNDAY_TO_THURSDAY,
        ),
        Position(
            "aus-night-forklift",
            "Forklift Operator",
            "aus-nights",
            HOURLY,
            seats=2,
            weekdays=SUNDAY_TO_THURSDAY,
        ),
    ),
    # Hire dates here reach back before the store opened, so the earliest hires read as transfers
    # from other stores. The store manager reports to the COO, two shift leads report to the
    # assistant manager, and the associates and cashiers report to the shift leads.
    ("Store Operations", "atl"): (
        Position("atl-manager", "Store Manager", "coo", weekdays=MONDAY_TO_FRIDAY),
        Position("atl-assistant-manager", "Assistant Store Manager", "atl-manager"),
        Position("atl-lead-opening", "Shift Lead, Opening", "atl-assistant-manager"),
        Position("atl-opening-sales", "Sales Associate", "atl-lead-opening", HOURLY, seats=6),
        Position("atl-opening-cashier", "Cashier", "atl-lead-opening", HOURLY, seats=4),
        Position("atl-lead-closing", "Shift Lead, Closing", "atl-assistant-manager"),
        Position("atl-closing-sales", "Sales Associate", "atl-lead-closing", HOURLY, seats=6),
        Position("atl-closing-cashier", "Cashier", "atl-lead-closing", HOURLY, seats=4),
        Position("atl-service", "Customer Service Associate", "atl-assistant-manager", HOURLY),
    ),
}

# Everyone else's names. The lists here and the Atlanta ones below have more names than the
# company has unnamed people, and no name appears twice, so no two people in a sandbox share a
# first name. The lists are blocks of words rather than tuples, which ruff would format one name
# per line.
GIVEN_NAMES = """
Aaliyah Aaron Abigail Adrian Aisha Alejandro Alicia Amara Amir Ana
Andre Andrea Angela Anjali Arjun Ava Benjamin Bianca Brandon Brian
Brianna Caleb Camila Carlos Carmen Chloe Christopher Daniel Darius Deepa
Desmond Diego Elena Elijah Emily Emmanuel Eric Erin Esperanza Ethan
Fatima Felix Fernando Gabriel Gloria Grace Hannah Hassan Hector Hiroshi
Imani Isaac Isabel Ivan Jamal James Jasmine Javier Jenna Jordan
Joseph Joy Julia Kai Kayla Keisha Kenji Kevin Khalid Laila
Lauren Layla Lucia Luis Malik Maya Megan Mei Miguel Mina
Nadia Naomi Nathan Nia Nicole Noah Olivia Omar Oscar Rachel
Rafael Rahul Rebecca Ricardo Riya Rosa Ryan Samir Samuel Sara
Sean Sofia Sophie Stephanie Tamika Tariq Teresa Thomas Tiana Tyler
Valentina Victor Vikram Wei Wesley Xavier Yasmin Yuki Zara Zoe
""".split()  # noqa: SIM905

FAMILY_NAMES = """
Abbott Adeyemi Aguilar Ahmed Ali Anderson Baker Banerjee Barnes Bautista
Becker Brooks Bryant Campbell Carter Castillo Chang Chen Choi Coleman
Collins Cruz Delgado Diaz Dixon Edwards Ellis Espinoza Evans Farah
Fischer Flores Foster Garcia Gonzalez Gordon Greene Gupta Gutierrez Hall
Harris Hayes Henderson Hernandez Hoang Hughes Ibrahim Iyer Jackson Jenkins
Jimenez Johnson Kapoor Kaur Kelly Khan Kim Kowalski Lee Lewis
Lopez Mahmoud Martin Martinez Mendoza Mitchell Morales Moreno Murphy Nair
Nelson Nguyen Novak Okafor Okoro Ortiz Owens Park Patel Perez
Peterson Phillips Price Ramirez Ramos Reddy Reyes Richardson Rivera Robinson
Rodriguez Romero Ross Russell Saito Sanchez Santos Shah Silva Singh
Soto Stewart Sullivan Tanaka Taylor Thompson Torres Tran Turner Vargas
Vasquez Walker Washington Watson Williams Wong Wright Yamamoto Young Zhang
""".split()  # noqa: SIM905

# Names added when the Atlanta store opened. They are drawn apart from the lists above, so the
# people who already existed keep their names.
ATLANTA_GIVEN_NAMES = """
Amelia Darnell Eleanor Giovanni Harper Ingrid Jerome Kiara Landon Marisol
Nikhil Odessa Priscilla Quentin Renee Sidney Tobias Uma Vivian Willa
Yusuf Zaire Cassandra Dmitri Gwen
""".split()  # noqa: SIM905

ATLANTA_FAMILY_NAMES = """
Alvarado Beasley Cohen Dawson Estrada Fitzgerald Grant Hamilton Ingram Kimura
Lawson Maddox Navarro Obi Pruitt Quinn Rhodes Sampson Tate Underwood
Velasquez Whitaker Yoon Zimmerman Boateng
""".split()  # noqa: SIM905

STREET_NAMES = """
Alder Aspen Birch Bluebell Cedar Clover Foxglove Hawthorn
Juniper Larkspur Linden Magnolia Marigold Sycamore Thistle Willow
""".split()  # noqa: SIM905
STREET_TYPES = ("Street", "Avenue", "Lane", "Court", "Drive", "Way", "Place")


# --- The seeded cases (Phase 6) ---
#
# Four people who aren't personas have each written to HR. The cases come from these fixed entries,
# with no draws from any random stream, so no other seeded row moves. Dates count in business days
# on Denver HQ's calendar (weekends and HQ holidays), the calendar HR's reply-by date uses.
# The words are the owner's to approve: each is the person's own, first person, short and plain.

# The summary a seeded case carries until the case-summary run has written a real one. It says
# plainly that it is a stand-in, and it is not model output.
SEEDED_SUMMARY_PLACEHOLDER = (
    "Placeholder summary for the demo. A real summary of what the person wrote appears here"
    " once Open Door's AI has written one."
)
# Values that make a placeholder obvious in the timeline and the summary's footer.
SEEDED_SUMMARY_MODEL = "seeded-placeholder"
SEEDED_SUMMARY_PROMPT_VERSION = "seeded-placeholder-1"


@dataclass(frozen=True, slots=True)
class SeededSummary:
    """A real summary of a seeded case's words, with the model and prompt version that wrote it."""

    text: str
    model: str
    prompt_version: str


# Trial 1's summaries of the seeded cases' words, by case key, from a paid case-summary run
# (`make eval-live SET=case-summary YES=1` writes them to `runs/<stamp>-case-summary-seeded.json`;
# `uv run python scripts/apply_seeded_summaries.py <that file>` rewrites this block). A case with no
# entry here keeps the placeholder above. Each entry passes the same checks every live summary
# passes, against its own case's words (a test holds it).
# BEGIN SEEDED SUMMARIES
SEEDED_SUMMARIES: Mapping[str, SeededSummary] = {
    "keisha-zhang": SeededSummary(
        text=(
            "The person says their last two paychecks were each about four hours short. They "
            "say their shift lead had them finish loading a truck after they clocked out, and "
            "they think that is where the hours went. They ask someone to check their time "
            "and tell them if they are owed the pay."
        ),
        model="claude-opus-5-5",
        prompt_version="2026-11.2",
    ),
    "chloe-foster": SeededSummary(
        text=(
            "The person says a regional visitor keeps commenting on their accent in front of "
            "customers. They say he also calls them by a nickname they have asked him not to "
            "use, and he keeps doing it. The person says they do not want to make a scene at "
            "the store, but they want it to stop."
        ),
        model="claude-opus-5-5",
        prompt_version="2026-11.2",
    ),
    "aaliyah-edwards": SeededSummary(
        text=(
            "The person reports that the top step of the ladder in the stockroom is cracked. "
            "They say they told their supervisor and were told to keep using it until a new "
            "one arrives. The person says they are worried someone is going to fall. They ask "
            "someone to look at the ladder before the new one arrives."
        ),
        model="claude-opus-5-5",
        prompt_version="2026-11.2",
    ),
    "lucia-gutierrez": SeededSummary(
        text=(
            "The person says they were diagnosed with migraines last month. They say their "
            "doctor suggested a screen filter for their monitor and a few more short breaks "
            "during the day. The person reports that they asked for both a while ago and have "
            "not heard back. They ask where their request stands."
        ),
        model="claude-opus-5-5",
        prompt_version="2026-11.2",
    ),
}
# END SEEDED SUMMARIES


@dataclass(frozen=True, slots=True)
class CaseStep:
    """One step in a seeded case's timeline, after the `opened` and `summary_written` events that
    every case has. `business_days_later` counts from the day the case was sent."""

    kind: str  # viewed, text_read, or status_changed
    business_days_later: int
    at: time  # local time in Denver
    to_status: str | None = None  # only for a status_changed step


@dataclass(frozen=True, slots=True)
class CaseSpec:
    """One seeded case. The person is named, with their title and location code, so a change to
    the company that moves them is caught instead of silently writing the wrong case."""

    key: str
    given_name: str
    family_name: str
    title: str
    location_code: str
    category: str
    status: str
    screening: str
    business_days_before_anchor: int
    sent_at: time  # local time in Denver
    text: str
    steps: tuple[CaseStep, ...] = ()


# How long after a case is sent the summary is written (and its event is stamped).
SUMMARY_DELAY_MINUTES = 1

CASES: tuple[CaseSpec, ...] = (
    CaseSpec(
        key="keisha-zhang",
        given_name="Keisha",
        family_name="Zhang",
        title="Warehouse Associate",
        location_code="aus",
        category="pay",
        status="new",
        screening="ordinary",
        business_days_before_anchor=1,
        sent_at=time(16, 20),
        text=(
            "My last two paychecks were each about four hours short. My shift lead had me finish"
            " loading a truck after I clocked out, and I think that is where the hours went. I"
            " would like someone to check my time and tell me if I am owed the pay."
        ),
    ),
    CaseSpec(
        key="chloe-foster",
        given_name="Chloe",
        family_name="Foster",
        title="Shift Lead, Opening",
        location_code="atl",
        category="harassment_discrimination",
        status="new",
        screening="sensitive",
        business_days_before_anchor=2,
        sent_at=time(9, 10),
        text=(
            "A regional visitor keeps commenting on my accent in front of customers. He also calls"
            " me by a nickname I have asked him not to use, and he keeps doing it. I don't want to"
            " make a scene at the store, but I want it to stop."
        ),
    ),
    CaseSpec(
        key="aaliyah-edwards",
        given_name="Aaliyah",
        family_name="Edwards",
        title="Cashier",
        location_code="oak",
        category="safety",
        status="in_review",
        screening="ordinary",
        business_days_before_anchor=6,
        sent_at=time(11, 30),
        text=(
            "The top step of the ladder in the stockroom is cracked. I told my supervisor and was"
            " told to keep using it until a new one arrives. I'm worried someone is going to fall,"
            " so can someone look at it before then?"
        ),
        steps=(
            CaseStep("viewed", 1, time(9, 12)),
            CaseStep("text_read", 1, time(9, 15)),
            CaseStep("status_changed", 1, time(9, 20), "in_review"),
        ),
    ),
    CaseSpec(
        key="lucia-gutierrez",
        given_name="Lucia",
        family_name="Gutierrez",
        title="Graphic Designer",
        location_code="den",
        category="medical_accommodation",
        status="closed",
        screening="sensitive",
        business_days_before_anchor=15,
        sent_at=time(13, 45),
        text=(
            "I was diagnosed with migraines last month. My doctor suggested a screen filter for my"
            " monitor and a few more short breaks during the day. I asked for both a while ago and"
            " haven't heard back, so where does my request stand?"
        ),
        steps=(
            CaseStep("viewed", 1, time(10, 0)),
            CaseStep("text_read", 1, time(10, 3)),
            CaseStep("status_changed", 1, time(10, 10), "in_review"),
            CaseStep("status_changed", 8, time(15, 30), "closed"),
        ),
    ),
)
