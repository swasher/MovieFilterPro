import requests
from bs4 import BeautifulSoup
from datetime import date


target = 'https://kinozal.tv/browse.php?c=1002&v=3&page=73'

scan_to_date = date(2023, 11, 26)

def scraping()

# download the HTML document
# with an HTTP GET request
response = requests.get(target)


if response.ok:
    # scraping logic here...

    # html code as plain text
    #### print(response.text)

    # parse the HTML content of the page
    soup = BeautifulSoup(response.content, "html.parser")

    movies_elements = soup.find_all('tr', 'bg')

    for m in movies_elements:
        s = m.find('a')
        date = m.find_all('td', 's')[-1].text.split(' в ')[0]  #last
        txt = s.text.split(' / ')
        if txt[1] == 'FOUR DIGIT':
            title = txt[0]
            original_title = ''
            year = txt[1]
        else:
            title = txt[0]
            original_title = txt[1]
            year = txt[2]

        # 'Красная жара / Red Heat / 1988 / ПМ / UHD / BDRip (1080p)'
        # 'Наследие / 2023 / РУ, СТ / WEB-DL (1080p)'
        link = s['href']
        print(title, original_title, year, date, link)

else:
    # log the error response
    # in case of 4xx or 5xx
    print(response)