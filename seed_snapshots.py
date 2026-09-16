from cards.models import ValueSnapshot
from users.models import User
from datetime import date, timedelta

user = User.objects.get(username='Dima')

ValueSnapshot.objects.filter(owner=user).delete()

ValueSnapshot.objects.create(owner=user, date=date.today() - timedelta(days=5), total_value=100)
ValueSnapshot.objects.create(owner=user, date=date.today() - timedelta(days=4), total_value=120)
ValueSnapshot.objects.create(owner=user, date=date.today() - timedelta(days=3), total_value=95)
ValueSnapshot.objects.create(owner=user, date=date.today() - timedelta(days=2), total_value=140)
ValueSnapshot.objects.create(owner=user, date=date.today() - timedelta(days=1), total_value=155)
ValueSnapshot.objects.create(owner=user, date=date.today(), total_value=180)

print(list(ValueSnapshot.objects.filter(owner=user).order_by('date')))