from apps.elections.models import Position, Candidate
from apps.accounts.models import Student
from django.db.models import Q

# All HOUSE_COLLEGE positions with candidates
print('--- All HOUSE_COLLEGE positions with candidates ---')
for p in Position.objects.filter(category='house_college'):
    cands = list(Candidate.objects.filter(position=p, is_active=True))
    print(f'  Position: {p.title} (election_id={p.election_id})')
    for c in cands:
        print(f'    Candidate: {c.full_name} | college="{c.college}"')
    if not cands:
        print(f'    (no candidates)')

print()

# Simulate the ballot view for a CICS student
print('--- Simulating ballot for CICS student ---')
cics_student = Student.objects.filter(college__icontains='information').first()
if cics_student:
    print(f'Student: {cics_student.full_name} | college="{cics_student.college}"')
    
    # Test exact match
    exact = Candidate.objects.filter(
        position__category='house_college',
        college=cics_student.college
    ).count()
    print(f'Exact match candidates: {exact}')
    
    # Test iexact match
    iexact = Candidate.objects.filter(
        position__category='house_college',
        college__iexact=cics_student.college.strip()
    ).count()
    print(f'iexact match candidates: {iexact}')
    
    # Check if the position for CICS has any candidates at all
    for p in Position.objects.filter(category='house_college', title__icontains='information'):
        cands = list(Candidate.objects.filter(position=p, is_active=True))
        print(f'\n  CICS Position: {p.title}')
        print(f'  Candidates count: {len(cands)}')
        for c in cands:
            print(f'    {c.full_name} | college="{c.college}" | is_active={c.is_active}')
else:
    print('No CICS student found')
