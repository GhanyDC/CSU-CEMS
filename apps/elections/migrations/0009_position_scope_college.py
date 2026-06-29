from django.db import migrations, models


OFFICIAL_COLLEGES = (
    "College of Humanities and Social Sciences",
    "College of Natural Sciences and Mathematics",
    "College of Public Administration",
    "College of Information and Computing Sciences",
    "College of Architecture and Engineering",
    "College of Industrial Technology",
    "College of Human Kinetics",
    "College of Veterinary Medicine",
    "College of Nursing",
)


def normalize_college(name):
    value = (name or "").strip().lower()
    for char in ("-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015"):
        value = value.replace(char, "-")
    while "  " in value:
        value = value.replace("  ", " ")
    if value.startswith("college of "):
        value = value[len("college of "):]
    return value.strip()


def resolve_official_college(name):
    raw = (name or "").strip()
    if not raw:
        return ""
    key = normalize_college(raw)
    for official in OFFICIAL_COLLEGES:
        if key == normalize_college(official):
            return official
    return raw


def extract_college_from_title(title):
    value = (title or "").strip()
    if not value:
        return ""

    prefix = "College Representative"
    rest = ""
    if value.lower().startswith(prefix.lower()):
        rest = value[len(prefix):].strip()
    else:
        for separator in (" - ", "\u2013", "\u2014", "\u00e2\u20ac\u201c", "\u00e2\u20ac\u0093", "\ufffd"):
            if separator in value:
                rest = value.split(separator, 1)[1].strip()
                break

    if not rest:
        for separator in (" - ", "\u2013", "\u2014", "\u00e2\u20ac\u201c", "\u00e2\u20ac\u0093", "\ufffd"):
            if separator in value:
                rest = value.split(separator, 1)[1].strip()
                break

    rest = rest.strip(" -\u2010\u2011\u2012\u2013\u2014\u2015\ufffd")
    return resolve_official_college(rest)


def backfill_position_scope_college(apps, schema_editor):
    Position = apps.get_model("elections", "Position")
    Candidate = apps.get_model("elections", "Candidate")

    positions = Position.objects.filter(
        category="house_college",
        election__election_type="campus",
    )
    for position in positions.iterator():
        if position.scope_college:
            continue

        scope_college = extract_college_from_title(position.title)
        if not scope_college:
            candidate_colleges = {
                resolve_official_college(college)
                for college in Candidate.objects.filter(
                    position=position,
                    is_active=True,
                )
                .exclude(college__isnull=True)
                .exclude(college="")
                .values_list("college", flat=True)
            }
            candidate_colleges = {college for college in candidate_colleges if college}
            if len(candidate_colleges) == 1:
                scope_college = next(iter(candidate_colleges))

        if scope_college:
            position.scope_college = scope_college
            position.save(update_fields=["scope_college"])


class Migration(migrations.Migration):

    dependencies = [
        ("elections", "0008_election_voting_mode_hybridimportbatch_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="position",
            name="scope_college",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "College represented by this position. Required for campus "
                    "House College Representative seats."
                ),
                max_length=255,
            ),
        ),
        migrations.RunPython(backfill_position_scope_college, migrations.RunPython.noop),
    ]
