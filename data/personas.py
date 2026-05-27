"""Hand-curated persona seed pool for synthetic data generation.

Two layers:
  • STRESS_PERSONAS — every PRD §7 stress-case row is represented here. These
    are the personas whose variants (via data/variants.py) compound across
    multiple shelter rosters to produce the demo's hero matches and the
    eval-grade gold pairs.
  • FILLER_PERSONAS — additional realistic personas that increase volume and
    serve as distractors / red herrings in the search. No deliberate name
    collisions across shelters.

Distribution rule (applied by generate_synthetic.py):
  • STRESS personas appear in 2–3 shelters (different variant each time)
  • FILLER personas appear in exactly 1 shelter (no collision)

Houston-area shelters (lat, lon) are real evacuation-site neighbourhoods.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Persona:
    person_id: str             # stable id used in gold pairs (e.g. "p_carlos_001")
    canonical_name: str        # the "ground truth" form the persona considers their own
    age: int
    language_spoken: str       # ISO 639-1 ("en", "es", "ar", "vi")
    school_or_employer: str | None = None
    distinguishing_features: str | None = None
    is_stress: bool = False    # affects shelter-distribution policy
    # description used when this persona generates a missing_person_report
    description: str | None = None
    description_language: Literal["en", "es", "ar", "vi"] = "en"


# ── Shelters: 10 real Houston neighbourhoods, geo-pinned ─────────────────
SHELTERS: list[dict[str, object]] = [
    {"shelter_id": "sh_memorial_high",   "name": "Memorial High School",        "lat": 29.7757, "lon": -95.5188},
    {"shelter_id": "sh_george_r_brown",  "name": "George R. Brown Convention Center", "lat": 29.7521, "lon": -95.3577},
    {"shelter_id": "sh_nrg_center",      "name": "NRG Center",                  "lat": 29.6849, "lon": -95.4108},
    {"shelter_id": "sh_lakewood_church", "name": "Lakewood Church",             "lat": 29.7340, "lon": -95.4380},
    {"shelter_id": "sh_alief_taylor",    "name": "Alief Taylor High School",    "lat": 29.6929, "lon": -95.6021},
    {"shelter_id": "sh_chavez_high",     "name": "César Chávez High School",    "lat": 29.6611, "lon": -95.2547},
    {"shelter_id": "sh_jersey_village",  "name": "Jersey Village High School",  "lat": 29.8763, "lon": -95.5638},
    {"shelter_id": "sh_sharpstown",      "name": "Sharpstown High School",      "lat": 29.7110, "lon": -95.5345},
    {"shelter_id": "sh_westside_high",   "name": "Westside High School",        "lat": 29.7384, "lon": -95.6260},
    {"shelter_id": "sh_bellaire_high",   "name": "Bellaire High School",        "lat": 29.7050, "lon": -95.4647},
]


# ── STRESS personas: cover every PRD §7 stress-case row ──────────────────
STRESS_PERSONAS: list[Persona] = [
    # Spanish diminutive + diacritic — the demo hero
    Persona("p_carlos_001", "Carlos Martínez", 15, "es",
            school_or_employer="Memorial High School (sophomore)",
            distinguishing_features="green backpack, glasses, soccer jersey #10",
            is_stress=True,
            description="Mi nieto Carlos tiene 15 años. Estudia en Memorial High School. "
                        "Llevaba una mochila verde y su camiseta de fútbol número 10. "
                        "Hablamos español en casa. No lo encuentro desde el huracán.",
            description_language="es"),

    # Mohammed / Muhammad / محمد — non-Roman script hero case
    Persona("p_mohammed_001", "محمد خان", 42, "ar",
            school_or_employer="Mosque Hamza, Sharpstown",
            distinguishing_features="grey beard, eyeglasses, traditional kurta",
            is_stress=True,
            description="أبحث عن أخي محمد خان، عمره 42 سنة. "
                        "كان يصلي في مسجد حمزة في حي شارب­ستاون قبل العاصفة.",
            description_language="ar"),

    # Vietnamese diacritics + name-order swap
    Persona("p_nguyen_001", "Nguyễn Văn Anh", 8, "vi",
            school_or_employer="Alief Elementary",
            distinguishing_features="red rubber boots, asthma inhaler in pocket",
            is_stress=True,
            description="Cháu trai tôi Nguyễn Văn Anh 8 tuổi, học sinh trường tiểu học Alief. "
                        "Cháu mang ủng cao su màu đỏ và có ống hít hen suyễn trong túi.",
            description_language="vi"),

    # Anglicisation calque
    Persona("p_ramon_001", "Ramón Hernández", 67, "es",
            school_or_employer="retired, former Houston Metro driver",
            distinguishing_features="walks with a cane, diabetic medication",
            is_stress=True,
            description="Busco a mi esposo Ramón Hernández, 67 años. "
                        "Es diabético y necesita su medicina. Camina con bastón.",
            description_language="es"),

    # English nickname graph
    Persona("p_catherine_001", "Catherine Williams", 34, "en",
            school_or_employer="HISD elementary school teacher",
            distinguishing_features="braided hair, school ID lanyard",
            is_stress=True,
            description="Looking for my sister Catherine Williams, age 34. She teaches "
                        "elementary school in HISD. Last seen wearing her school ID lanyard."),

    # Spanish↔English calque (Charles ↔ Carlos)
    Persona("p_charles_001", "Charles Rodríguez", 29, "es",
            school_or_employer="construction crew, Ace Builders",
            distinguishing_features="tattoo of Texas flag on right forearm",
            is_stress=True,
            description="Looking for Charles Rodríguez, 29. Works construction. "
                        "Has a Texas flag tattoo on his right forearm."),

    # Arabic name #2 — Ahmed variants
    Persona("p_ahmed_001", "أحمد عبد الله", 25, "ar",
            school_or_employer="University of Houston graduate student",
            distinguishing_features="wears prayer beads on left wrist",
            is_stress=True,
            description="أبحث عن صديقي أحمد عبد الله، طالب دراسات عليا في جامعة هيوستن.",
            description_language="ar"),

    # Spanish diminutive #2 — Manuel/Manny
    Persona("p_manuel_001", "Manuel Vásquez", 12, "es",
            school_or_employer="Chavez High School (7th grade)",
            distinguishing_features="red baseball cap, missing front tooth",
            is_stress=True,
            description="Mi hijo Manuel Vásquez tiene 12 años. Estudia séptimo grado en "
                        "Chavez High. Lleva una gorra roja de béisbol y le falta un diente."),

    # English nickname #2 — William/Bill
    Persona("p_william_001", "William Foster", 56, "en",
            school_or_employer="HEB grocery, Bellaire branch",
            distinguishing_features="works in produce section, knee brace",
            is_stress=True,
            description="My uncle William Foster, 56, works at the HEB on Bellaire. "
                        "He wears a knee brace and last contacted us before the storm."),

    # Vietnamese #2
    Persona("p_tran_001", "Trần Thị Hồng", 71, "vi",
            school_or_employer="retired seamstress, Alief community",
            distinguishing_features="silver hair in a bun, walks slowly",
            is_stress=True,
            description="Tôi đang tìm bà Trần Thị Hồng, 71 tuổi, sống ở khu vực Alief. "
                        "Bà có mái tóc bạc búi cao và đi lại chậm.",
            description_language="vi"),

    # Maria/Mary cross-language — Maria with several nicknames
    Persona("p_maria_001", "María González", 68, "es",
            school_or_employer="retired, grandmother of Carlos (p_carlos_001)",
            distinguishing_features="silver-rimmed glasses, rosary in hand",
            is_stress=True,
            description="Soy María González, 68 años. Busco a mi nieto Carlos Martínez. "
                        "No habla mucho inglés pero estudia en Memorial High.",
            description_language="es"),

    # José / Yusuf cross-faith calque
    Persona("p_jose_001", "José Ramírez", 19, "es",
            school_or_employer="Lone Star College, IT student",
            distinguishing_features="laptop bag, prescription glasses",
            is_stress=True,
            description="Busco a mi sobrino José Ramírez, 19 años. Estudia informática en "
                        "Lone Star College. Llevaba una bolsa con su computadora.",
            description_language="es"),
]


# ── FILLER personas: volume + distractors. No stress-case collisions ─────
# Order matters: the first 20 fillers enter the eval gold set (see
# generate_synthetic.py). zh/fr personas are placed up front to close PRD §13's
# "≥ 5 languages with at least one matched case" criterion.
FILLER_PERSONAS: list[Persona] = [
    # 5th language: Mandarin Chinese (zh)
    Persona("f_zh_001", "Wang Wei",            34, "zh",
            "Houston Chinese Community Center, volunteer",
            "wears reading glasses, carries a worn leather notebook",
            description="我在寻找我的丈夫王伟,34岁。他在风暴前在休斯敦华人社区中心做志愿者。"
                        "他戴着老花镜,随身带着一本旧的皮革笔记本。请帮帮我们。",
            description_language="zh"),
    Persona("f_zh_002", "Mei Lin Wu",          11, "zh",
            "Bellaire Elementary, 5th grade",
            "Hello Kitty backpack, hair in two braids",
            description="我女儿吴美琳,11岁,就读Bellaire小学五年级。"
                        "她背着Hello Kitty书包,扎着两条辫子。",
            description_language="zh"),

    # 6th language: French (fr)
    Persona("f_fr_001", "Jean-Pierre Dubois",  58, "fr",
            "Methodist Hospital, anaesthesiologist",
            "wedding ring with date engraved 1992, hospital ID",
            description="Je cherche mon père, Jean-Pierre Dubois, 58 ans. "
                        "Il est anesthésiste à l'hôpital Methodist. Il porte une "
                        "alliance gravée 1992 et son badge d'hôpital.",
            description_language="fr"),
    Persona("f_fr_002", "Élise Moreau",        22, "fr",
            "Rice University, French exchange student",
            "Rice University tote bag, photography camera around neck",
            description="Je m'appelle Sophie Moreau. Je cherche ma sœur Élise, "
                        "22 ans, étudiante d'échange à l'université Rice. "
                        "Elle a un sac Rice University et un appareil photo autour du cou.",
            description_language="fr"),

    Persona("f_001", "Emily Johnson",       28, "en", "Texas Children's Hospital RN",
            "nurse scrubs, badge clipped to pocket"),
    Persona("f_002", "Marcus Brown",        45, "en", "FedEx driver",
            "FedEx uniform, dispatch radio"),
    Persona("f_003", "Sofía Reyes",         11, "es", "Sharpstown Elementary, 5th grade",
            "purple unicorn lunchbox"),
    Persona("f_004", "Daniel Kim",          34, "en", "Houston Methodist Hospital, IT",
            "wears noise-cancelling headphones around neck"),
    Persona("f_005", "Priya Patel",         52, "en", "Shell oil & gas, geologist",
            "Indian sari, rudraksha mala"),
    Persona("f_006", "Lucia Romero",        7,  "es", "Bellaire Elementary, 2nd grade",
            "pink hair clips, Frozen-themed backpack"),
    Persona("f_007", "Andrew Davis",        62, "en", "Episcopal Health, hospital chaplain",
            "clerical collar, large wooden cross"),
    Persona("f_008", "Hassan Ali",          38, "en", "Uber driver",
            "blue Toyota Camry, prayer mat in trunk"),
    Persona("f_009", "Linh Pham",           24, "vi", "Vietnamese American Community, volunteer",
            "yellow vest, clipboard with names"),
    Persona("f_010", "Robert Wilson",       71, "en", "retired postal worker",
            "Vietnam Veteran cap, oxygen tank on cart"),
    Persona("f_011", "Aisha Williams",      29, "en", "Houston ISD, social worker",
            "hijab, ID badge, notebook"),
    Persona("f_012", "Isabella Cruz",       16, "es", "Westside High School junior",
            "cheer team duffel bag, ponytail"),
    Persona("f_013", "James Thompson",      41, "en", "HPD officer, off-duty",
            "khaki cargo pants, holstered sidearm"),
    Persona("f_014", "Mei-Lin Chen",        9,  "en", "Jersey Village Elementary, 3rd grade",
            "music recorder in case, glittery shoes"),
    Persona("f_015", "Diego Morales",       33, "es", "Tex-Mex restaurant cook",
            "chef whites, forearm scar from a kitchen burn"),
    Persona("f_016", "Sarah Goldberg",      57, "en", "synagogue secretary, Beth Yeshurun",
            "Magen David necklace, reading glasses on chain"),
    Persona("f_017", "Anthony Garcia",      22, "en", "University of Houston, undergraduate",
            "UH Cougars hoodie, skateboard"),
    Persona("f_018", "Fátima Castro",       64, "es", "retired, lives with daughter in Alief",
            "uses a walker, hearing aid in left ear"),
    Persona("f_019", "Tyler Hayes",         13, "en", "Lanier Middle School",
            "braces, Houston Astros jersey"),
    Persona("f_020", "Olivia Martin",       30, "en", "veterinary technician, Bellaire",
            "scrubs, dog leash always in pocket"),
    Persona("f_021", "Khalid Mahmoud",      48, "ar", "halal grocery store owner",
            "white skullcap, store apron with name embroidered",
            description="نبحث عن خالد محمود، صاحب البقالة الحلال في شارع هيلكروفت.",
            description_language="ar"),
    Persona("f_022", "Tran Minh Quan",      17, "vi", "Lee High School, senior",
            "robotics club jacket, glasses"),
    Persona("f_023", "Patricia Long",       73, "en", "retired librarian",
            "cardigan, library volunteer pin"),
    Persona("f_024", "Carlos Mendoza",      8,  "es", "Hobby Elementary, 3rd grade",
            "blue backpack with Spider-Man, two missing front teeth"),
    Persona("f_025", "Hoa Nguyen",          55, "vi", "nail-salon owner, Sharpstown",
            "manicurist's apron with rhinestones"),
    Persona("f_026", "Jacob Cohen",         19, "en", "Rice University freshman",
            "Rice Owls t-shirt, retainer case"),
    Persona("f_027", "Esperanza Vargas",    36, "es", "house cleaner, lives in Pasadena",
            "right index finger has old scar"),
    Persona("f_028", "Brandon Lee",         27, "en", "MS-IT contractor, Compaq Center area",
            "tech-conference t-shirt, MacBook backpack"),
    Persona("f_029", "Yasmin Hussein",      14, "ar", "Sharpstown Middle School, 8th grade",
            "head scarf, art portfolio under arm"),
    Persona("f_030", "Rodrigo Salazar",     50, "es", "auto-body shop, owner",
            "navy work shirt embroidered 'Rodrigo'"),
]
