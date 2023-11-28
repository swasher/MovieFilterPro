from django.shortcuts import render
from io import StringIO
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import InMemoryStorage
import csv
from django.http import HttpResponse
from django.template.defaultfilters import safe

from .models import KinoriumMovie

def movies(request):
    return render(request, template_name='movies.html')


def handle_uploaded_file(f):
    # with open("some/file/name.txt", "wb+") as destination:
    content = f.read()
    for line in content.lines():
        print(line)

def from_line(line: str) -> list[str]:
    return next(csv.reader([line]))

def upload_to_dictreader(requst_file):
    content = requst_file.read()
    data = content.decode('utf-16', 'strict')
    dict_reader_obj = csv.DictReader(StringIO(data, newline=''), delimiter='\t')
    return dict_reader_obj


def year_to_int(year: str) -> int:
    try:
        year = int(year)
    except:
        return HttpResponse(safe(f"<b style='color:red'>Year not string in {title}</b>"))
    return year


def upload_csv(request):
    if request.method == 'POST':

        if 'file_votes' in request.FILES and 'file_movie_list' in request.FILES:

            try:
                movie_lists_data = upload_to_dictreader(request.FILES['file_movie_list'])
                print('\nLists')
                for row in movie_lists_data:
                    title = row['Title']
                    original_title = row['Original Title']
                    t = row['Type']
                    year = year_to_int(row['Year'])
                    list_title = row['ListTitle']

                    print(list_title, title, original_title, t, year)

                    match list_title:
                        case 'Буду смотреть':
                            status = KinoriumMovie.WILL_WATCH
                        case 'Не буду смотреть':
                            status = KinoriumMovie.DECLINED
                        case _:
                            status = None

                    if t == 'Фильм' and status:
                        m, created = KinoriumMovie.objects.get_or_create(
                            title=title, original_title=original_title, year=year
                        )
                        m.status = status
                        m.save()
            except:
                return HttpResponse(safe("<b style='color:red'>Error processing Movie List file!</b>"))


            try:
                votes_data = upload_to_dictreader(request.FILES['file_votes'])
                print('\nVOTES')
                for row in votes_data:
                    title = row['Title']
                    original_title = row['Original Title']
                    t = row['Type']
                    year = year_to_int(row['Year'])
                    print(title, original_title, t, year)

                    if t == 'Фильм':
                        m, created = KinoriumMovie.objects.get_or_create(
                            title=title, original_title=original_title, year=year
                        )
                        m.status = KinoriumMovie.WATCHED
                        m.save()

            except Exception as e:
                return HttpResponse(safe(f"<b style='color:red'>Error processing Vote file! Error: {e}</b>"))



            return HttpResponse(safe("<b style='color:green'>Update success!</b>"))

        else:
            html = "<b style='color:red'>Need both files!</b>"
            return HttpResponse(safe(html))

    return render(request, 'upload_csv.html')


def parse_test(request):
    return render(request, 'test.html')
