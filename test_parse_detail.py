# page
# https://kinozal.tv/browse.php?c=1002&v=3&page=1
# id
# https://kinozal.tv/details.php?id=564005
from movie_filter_pro import wsgi
from moviefilter.parse import get_details
from moviefilter.classes import KinozalMovie

m = KinozalMovie()
m.id = 564005
m.id = 2009368

get_details(m)

print(m)