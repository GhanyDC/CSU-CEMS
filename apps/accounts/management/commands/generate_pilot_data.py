"""
Management command to generate pilot test data for CEMS.

Creates:
- 2,000 dummy students across 9 colleges
- 3 admin users (EB Head, Operator, Tally Watcher)
- 1 election with full position/candidate setup matching the
  campus SSC constitutional structure
- Verification records + voter roll (EligibleVoter entries) for all students
- Finalized voter roll (ready for DRAFT → ACTIVE transition)

Usage:
    python manage.py generate_pilot_data
    python manage.py generate_pilot_data --students 500
    python manage.py generate_pilot_data --clear  (wipe existing test data first)
"""
import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AdminProfile, AdminRole, Student
from apps.elections.models import Candidate, Election, EligibleVoter, Position, VerificationRecord
from apps.elections.constants import OFFICIAL_COLLEGES

COLLEGES = list(OFFICIAL_COLLEGES)

PARTIES = [
    "Alyansa",
    "Katipunan",
    "Bagong Simula",
    "Independente",
]

COURSES_BY_COLLEGE = {
    "College of Humanities and Social Sciences": ["BSPsych", "ABPolSci", "ABComm", "ABPhilo"],
    "College of Natural Sciences and Mathematics": ["BSBio", "BSChem", "BSMath", "BSPhysics"],
    "College of Public Administration": ["BPA", "BSPA-HRM", "BSPA-FM"],
    "College of Information and Computing Sciences": ["BSIT", "BSCS", "BSIS"],
    "College of Architecture and Engineering": ["BSArch", "BSCE", "BSEE", "BSME"],
    "College of Industrial Technology": ["BSIT-Auto", "BSIT-Elec", "BSIT-Civil"],
    "College of Human Kinetics": ["BPEd", "BSESS"],
    "College of Veterinary Medicine": ["DVM"],
    "College of Nursing": ["BSN"],
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
            EligibleVoter.objects.all().delete()
            VerificationRecord.objects.all().delete()
            Candidate.objects.all().delete()
            Position.objects.all().delete()
            Election.objects.all().delete()
            Student.objects.all().delete()
            # Remove pilot admin users/profiles (only those created by this command)
            for uname in ("eb_head", "operator1", "tally_watcher1"):
                User.objects.filter(username=uname).delete()

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

        # ── Admin Users ───────────────────────────────────────────
        self.stdout.write("Creating admin users...")
        admins_created = self._create_admin_users()
        self.stdout.write(self.style.SUCCESS(f"  {admins_created} admin user(s) created."))

        # ── Voter Roll ────────────────────────────────────────────
        self.stdout.write("Building voter roll (verification -> eligible voters -> finalize)...")
        all_students = list(Student.objects.all())
        self._build_voter_roll(election, all_students)

        self.stdout.write(self.style.SUCCESS("\nPilot data generation complete."))
        self.stdout.write(self.style.SUCCESS("\nAdmin credentials:"))
        self.stdout.write("  EB Head:       eb_head / pilot_admin_pass")
        self.stdout.write("  Operator:      operator1 / pilot_admin_pass")
        self.stdout.write("  Tally Watcher: tally_watcher1 / pilot_admin_pass")

    def _create_candidates(self, position, count, college=None):
        """Create random candidates for a position with unique names."""
        candidates = []
        used_names = set()
        attempts = 0
        while len(candidates) < count and attempts < count * 10:
            attempts += 1
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            full_name = f"{first} {last}"
            if full_name in used_names:
                continue
            used_names.add(full_name)
            candidates.append(Candidate(
                position=position,
                full_name=full_name,
                party=random.choice(PARTIES),
                college=college or random.choice(COLLEGES),
            ))
        Candidate.objects.bulk_create(candidates)

    def _create_admin_users(self):
        """Create pilot admin users (EB Head, Operator, Tally Watcher)."""
        admin_specs = [
            ("eb_head", AdminRole.ELECTORAL_BOARD_HEAD, "EB Head (Pilot)"),
            ("operator1", AdminRole.ELECTORAL_BOARD_OPERATOR, "Operator One (Pilot)"),
            ("tally_watcher1", AdminRole.TALLY_WATCHER, "Tally Watcher One (Pilot)"),
        ]
        created = 0
        for username, role, display_name in admin_specs:
            if User.objects.filter(username=username).exists():
                self.stdout.write(f"    Admin '{username}' already exists — skipping.")
                continue
            user = User.objects.create_user(
                username=username,
                password="pilot_admin_pass",
            )
            AdminProfile.objects.create(
                user=user,
                role=role,
                display_name=display_name,
            )
            created += 1
        return created

    def _build_voter_roll(self, election, students):
        """Create verification records, generate eligible voters, and finalize voter roll."""
        # 1. Create VerificationRecord entries for all students (simulates registrar import)
        existing_vr_sids = set(
            VerificationRecord.objects
            .filter(election=election)
            .values_list("student_id_input", flat=True)
        )
        vr_to_create = []
        for s in students:
            if s.student_id in existing_vr_sids:
                continue
            vr_to_create.append(VerificationRecord(
                election=election,
                student_id_input=s.student_id,
                full_name_input=s.full_name,
                college_input=s.college,
                matched_student=s,
                status=VerificationRecord.MatchStatus.MATCHED,
            ))
        if vr_to_create:
            VerificationRecord.objects.bulk_create(vr_to_create)
        self.stdout.write(self.style.SUCCESS(
            f"  {len(vr_to_create)} verification records created."
        ))

        # 2. Generate EligibleVoter entries from matched records
        existing_ev_sids = set(
            EligibleVoter.objects
            .filter(election=election)
            .values_list("student_id", flat=True)
        )
        ev_to_create = []
        for s in students:
            if s.pk in existing_ev_sids:
                continue
            ev_to_create.append(EligibleVoter(
                election=election,
                student=s,
                college_snapshot=s.college or "",
            ))
        if ev_to_create:
            EligibleVoter.objects.bulk_create(ev_to_create)
        self.stdout.write(self.style.SUCCESS(
            f"  {len(ev_to_create)} eligible voters created."
        ))

        # 3. Finalize voter roll
        if not election.is_voter_roll_finalized:
            election.voter_roll_finalized_at = timezone.now()
            election.voter_roll_finalized_by = "generate_pilot_data"
            election.save(update_fields=[
                "voter_roll_finalized_at",
                "voter_roll_finalized_by",
                "updated_at",
            ])
            self.stdout.write(self.style.SUCCESS("  Voter roll finalized."))
