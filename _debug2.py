from apps.elections.models import Election, Position, Candidate

# All distinct candidate colleges
print('--- All distinct candidate colleges ---')
for c in Candidate.objects.values_list('college', flat=True).distinct().order_by('college'):
    print(f'  "{c}"')

print()

# All HOUSE_COLLEGE positions and their candidates
print('--- All HOUSE_COLLEGE positions with candidates ---')
for p in Position.objects.filter(category='house_college').select_related('election'):
    cands = Candidate.objects.filter(position=p, is_active=True)
    print(f'  Election: {p.election.name} | Position: {p.title}')
    for c in cands:
        print(f'    Candidate: {c.full_name} | college="{c.college}"')
    if not cands.exists():
        print(f'    (no candidates)')
