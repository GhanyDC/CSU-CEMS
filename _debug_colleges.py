from apps.elections.models import Election, Position, Candidate
from apps.accounts.models import Student

# Show all active/published elections
for e in Election.objects.filter(status__in=['active', 'published']):
    print(f'Election: {e.name} | type={e.election_type} | status={e.status}')
    
    # Show HOUSE_COLLEGE positions and their candidates
    for p in Position.objects.filter(election=e, category='house_college'):
        cands = Candidate.objects.filter(position=p, is_active=True)
        print(f'  Position: {p.title}')
        for c in cands:
            print(f'    Candidate: {c.full_name} | college="{c.college}"')

print()
print('--- CICS Students (first 5) ---')
for s in Student.objects.filter(college__icontains='information')[:5]:
    print(f'  Student: {s.full_name} | college="{s.college}"')

print()
print('--- All distinct student colleges ---')
for c in Student.objects.values_list('college', flat=True).distinct().order_by('college'):
    print(f'  "{c}"')

print()
print('--- All distinct candidate colleges ---')
for c in Candidate.objects.values_list('college', flat=True).distinct().order_by('college'):
    print(f'  "{c}"')
