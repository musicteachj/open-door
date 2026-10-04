"""The seed company's fixed data: its locations, departments, org chart, and name lists.

The company is fictional, and so is everything about its people. Personal emails use example.com,
phone numbers use 555-0100 to 555-0199, which are reserved for fiction, and street addresses are
made up. seed.py turns this data into rows.
"""

from dataclasses import dataclass

# Every other choice (who gets which name, phone number, and address, and the dates of everyone
# not named below) comes from this seed, so every sandbox gets exactly the same company.
SEED = 20261003

# .example and example.com are reserved for documentation (RFC 2606), so no message sent to these
# addresses can reach anyone.
WORK_EMAIL_DOMAIN = "opendoor.example"
PERSONAL_EMAIL_DOMAIN = "example.com"


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


LOCATIONS = (
    LocationSpec("den", "Denver HQ", "Denver", "CO", "America/Denver", "303", ("80203", "80211")),
    LocationSpec(
        "oak", "Oakland store", "Oakland", "CA", "America/Los_Angeles", "510", ("94606", "94610")
    ),
    LocationSpec(
        "aus", "Austin warehouse", "Austin", "TX", "America/Chicago", "512", ("78702", "78745")
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
    """

    key: str
    title: str
    manager: str | None
    employment_type: str = "salaried"
    seats: int = 1
    person: PersonSpec | None = None


DANA = PersonSpec("Dana", "Whitfield", 1650, 15200, persona_key="dana", is_hr_admin=True)
MARCUS = PersonSpec("Marcus", "Bell", 2400, 16000, persona_key="marcus")
PRIYA = PersonSpec("Priya", "Raman", 1160, 11400, persona_key="priya")
LEO = PersonSpec("Leo", "Nakamura", 700, 9600)
MATEO = PersonSpec("Mateo", "Alvarez", 520, 10300, persona_key="mateo")

HOURLY = "hourly"

# Each department works at one location here. Denver HQ has 40 people, the Oakland store 45, and
# the Austin warehouse 35. Managers come before their reports.
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
        Position("marcus", "Store Manager", "coo", person=MARCUS),
        Position("priya", "Visual Merchandiser", "marcus", person=PRIYA),
        Position("leo", "Sales Associate", "marcus", HOURLY, person=LEO),
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
        Position("aus-nights", "Shift Supervisor, Nights", "aus-manager"),
        Position("aus-night-crew", "Warehouse Associate", "aus-nights", HOURLY, seats=12),
        Position("aus-night-forklift", "Forklift Operator", "aus-nights", HOURLY, seats=2),
    ),
}

# Everyone else's names. Each list has more names than the company has unnamed people, and no
# name appears twice, so no two people in a sandbox share a first name. The lists are blocks of
# words rather than tuples, which ruff would format one name per line.
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

STREET_NAMES = """
Alder Aspen Birch Bluebell Cedar Clover Foxglove Hawthorn
Juniper Larkspur Linden Magnolia Marigold Sycamore Thistle Willow
""".split()  # noqa: SIM905
STREET_TYPES = ("Street", "Avenue", "Lane", "Court", "Drive", "Way", "Place")
