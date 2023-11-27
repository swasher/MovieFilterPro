from django.shortcuts import render
from io import StringIO
from django.core.files.storage import FileSystemStorage
from django.core.files.storage import InMemoryStorage
import csv
from django.http import HttpResponse


def movies(request):
    return render(request, template_name='movies.html')


def handle_uploaded_file(f):
    # with open("some/file/name.txt", "wb+") as destination:
    content = f.read()
    for line in content.lines():
        print(line)

def from_line(line: str) -> list[str]:
    return next(csv.reader([line]))

def upload_csv(request):
    if request.method == 'POST':

        if request.FILES['file_movie_list'] and request.FILES['file_votes']:

            uploaded_csv = request.FILES['uploaded_csv']

            content = uploaded_csv.read()
            data = content.decode('utf-16', 'strict')

            csv_input = csv.DictReader(StringIO(data, newline=''), delimiter='\t')
            rows = list(csv_input)
            print("Rows", rows)
            for row in rows:
                print(row['ListTitle'], row['Title'], row['Original Title'], row['Type'], row['Year'])

            return 'erkfhrkfhergkerhkgh'

            # return render(
            #     request,
            #     'upload_csv.html',
            #     # {'uploaded_file_url': uploaded_file_url}
            # )
        else:
            """
            or, you can return html:
            html = "<b>Text</b>"
            return safe(html)
            """
            return HttpResponse(status=400)

    return render(request, 'upload_csv.html')