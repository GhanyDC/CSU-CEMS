"""
Management command to generate pilot test data for CEMS.

Creates:
- 2,000 dummy students across 8 colleges
- 1 election with full position/candidate setup matching the
  campus SSC constitutional structure

Usage:
    python manage.py generate_pilot_data
    python manage.py generate_pilot_data --students 500
    python manage.py generate_pilot_data --clear  (wipe existing test data first)
"""
import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Student
from apps.elections.models import Candidate, Election, Position

COLLEGES = [
    "College of Engineering",
    "College of Arts and Sciences",
    "College of Business Administration",
    "College of Education",
    "College of Nursing",
    "College of Information Technology",
    "College of Law",
    "College of Agriculture",
]

PARTIES = [
    "Alyansa",
    "Katipunan",
    "Bagong Simula",
    "Independente",
]

COURSES_BY_COLLEGE = {
    "College of Engineering": ["BSEE", "BSCE", "BSME", "BSCpE"],
    "College of Arts and Sciences": ["BSPsych", "ABPolSci", "BSBio", "ABComm"],
    "College of Business Administration": ["BSA", "BSBA-MM", "BSBA-FM", "BSBA-HRDM"],
    "College of Education": ["BSED", "BEED", "BPEd"],
    "College of Nursing": ["BSN"],
    "College of Information Technology": ["BSIT", "BSCS"],
    "College of Law": ["JD"],
    "College of Agriculture": ["BSAgri", "BSForestry"],
}

# Typical Filipino first & last names for realistic test data
FIRST_NAMES = [
    "Juan", "Maria", "Jose", "Ana", "Pedro", "Rosa", "Carlos", "Luisa",
    "Ramon", "Carmen", "Miguel", "Sofia", "Rafael", "Isabel", "Antonio",
    "Elena", "Manuel", "Patricia", "Roberto", "Cristina", "Eduardo",
    "Angela", "Fernando", "Teresa", "Daniel", "Beatriz", "Francisco",
    "Gabriela", "Ricardo", "Victoria", "Luis", "Juana", "Andres",
    "Rosario", "Marco", "Lourdes", "Paolo", "Jasmine", "Bryan", "Kaye",
]

LAST_NAMES = [
    "Dela Cruz", "Santos", "Reyes", "Garcia", "Ramos", "Mendoza",
    "Torres", "Flores", "Gonzales", "Bautista", "Villanueva", "Cruz",
    "Hernandez", "Aquino", "Rivera", "Soriano", "Castillo", "Lazaro",
    "Manalo", "Pascual", "Salazar", "Del Rosario", "Navarro", "Espiritu",
    "Lopez", "Romero", "Aguilar", "Domingo", "Miranda", "Santiago",
]

# Executive positions for the election
EXECUTIVE_POSITIONS = [
    ("President", "executive", 1),
    ("Vice President", "executive", 1),
]

SENATE_SEATS = 12


class Command(BaseCommand):
    help = "Generate pilot test data (students, election, positions, candidates)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--students",
            type=int,
            default=2000,
            help="Number of dummy students to generate (default: 2000).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing test data before generating new data.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        num_students = options["students"]
        clear = options["clear"]

        if clear:
            self.stdout.write(self.style.WARNING("Clearing existing data..."))
            Candidate.objects.all().delete()
            Position.objects.all().delete()
            Election.objects.all().delete()
            Student.objects.all().delete()

        # ── Students ──────────────────────────────────────────────
        self.stdout.write(f"Generating {num_students} students...")
        students = []
        used_ids = set(Student.objects.values_list("student_id", flat=True))

        for i in range(num_students):
            # Generate unique student ID: YYYY-NNNNN
            while True:
                sid = f"2024-{random.randint(10000, 99999):05d}"
                if sid not in used_ids:
                    used_ids.add(sid)
                    break

            college = random.choice(COLLEGES)
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)

            students.append(Student(
                student_id=sid,
                full_name=f"{first} {last}",
                date_of_birth=date(
                    random.randint(2000, 2005),
                    random.randint(1, 12),
                    random.randint(1, 28),
                ),
                college=college,
                course=random.choice(COURSES_BY_COLLEGE[college]),
                year=random.randint(1, 4),
            ))

        Student.objects.bulk_create(students, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"  Created {len(students)} students."))

        # ── Election ──────────────────────────────────────────────
        self.stdout.write("Creating election...")
        now = timezone.now()
        election = Election.objects.create(
            name="AY 2025-2026 SSC General Election (Pilot)",
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(days=3),
            status=Election.Status.DRAFT,
        )
        self.stdout.write(self.style.SUCCESS(f"  Election: {election.name}"))

        # ── Positions ─────────────────────────────────────────────
        order = 1

        # Executive
        for title, category, max_sel in EXECUTIVE_POSITIONS:
            pos = Position.objects.create(
                election=election,
                title=title,
                category=category,
                max_selections=max_sel,
                order=order,
            )
            self._create_candidates(pos, count=random.randint(3, 5))
            order += 1

        # Senate (12 seats)
        senate = Position.objects.create(
            election=election,
            title="Senator",
            category="senate",
            max_selections=SENATE_SEATS,
            order=order,
        )
        self._create_candidates(senate, count=random.randint(18, 24))
        order += 1

        # House - College Representatives (one per college)
        for college in COLLEGES:
            pos = Position.objects.create(
                election=election,
                title=f"College Representative – {college.replace('College of ', '')}",
                category="house_college",
                max_selections=1,
                order=order,
            )
            self._create_candidates(pos, count=random.randint(2, 4), college=college)
            order += 1

        # House - Party-List (3 party-list seats)
        party_list = Position.objects.create(
            election=election,
            title="Party-List Representative",
            category="house_party",
            max_selections=3,
            order=order,
        )
        self._create_candidates(party_list, count=random.randint(6, 10))

        total_positions = Position.objects.filter(election=election).count()
        total_candidates = Candidate.objects.filter(position__election=election).count()
        self.stdout.write(self.style.SUCCESS(
            f"  {total_positions} positions, {total_candidates} candidates."
        ))
        self.stdout.write(self.style.SUCCESS("\nPilot data generation complete."))

    def _create_candidates(self, position, count, college=None):
        """Create random candidates for a position."""
        candidates = []
        for _ in range(count):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            candidates.append(Candidate(
                position=position,
                full_name=f"{first} {last}",
                party=random.choice(PARTIES),
                college=college or random.choice(COLLEGES),
            ))
        Candidate.objects.bulk_create(candidates)
