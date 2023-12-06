import kinol_dooble.asgi
import yaml
from kinozal.models import Country

with open('countries.yaml', 'r') as f:
    yml = yaml.safe_load(f)

# {'iso_2': 'AF', 'name': 'Афганистан'}
    countries = yml['countries']

for c in countries:
    print(countries[c]['iso_2'], countries[c]['name'])

    new_country = Country.objects.create(name=countries[c]['name'])
    new_country.save()
