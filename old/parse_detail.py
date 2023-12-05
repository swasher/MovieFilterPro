from bs4 import BeautifulSoup
import requests


def parse_detail():

    html1 = 'sample_detail_pages\Day_of_Reckoning.html'
    html2 = 'sample_detail_pages\Fat_Man_and_Little_Boy.html'
    html3 = 'sample_detail_pages\Kovcheg.html'

    # source = response.content
    with open(html3, 'r') as f:
        source = f.read()

    # source = requests.get('https://kinozal.tv/details.php?id=1559201').content

    soup = BeautifulSoup(source, "html.parser")

    imdb_part = soup.select_one('a:-soup-contains("IMDb")')
    if imdb_part:
        # todo weak assumption for [4]; may be need add some checks
        imdb_id = imdb_part['href'].split('/')[4]
        imdb_rating = imdb_part.find('span').text
    else:
        imdb_id = None
        imdb_rating = None
    print('IMDb id:', imdb_id)
    print('IMDb rating:', imdb_rating)

    kinopoisk_part = soup.select_one('a:-soup-contains("Кинопоиск")')
    if kinopoisk_part:
        # todo weak assumption for [4]; may be need add some checks
        kinopoisk_id = kinopoisk_part['href'].split('/')[4]
        kinopoisk_rating = kinopoisk_part.find('span').text
    else:
        kinopoisk_id = None
        kinopoisk_rating = None
    print('kinopoisk id:', kinopoisk_id)
    print('kinopoisk rating:', kinopoisk_rating)

    print('\nGenres:')  # WORKED
    details_genres = soup.select_one('b:-soup-contains("Жанр:")').find_next_sibling().text
    print(details_genres)

    print('\nCountries:')  # WORKED
    details_countries = soup.select_one('b:-soup-contains("Выпущено:")').find_next_sibling().text
    print(details_countries)

    print('\nDirector:')  # WORKED
    details_director = soup.select_one('b:-soup-contains("Режиссер:")').find_next_sibling().text
    print(details_director)

    print('\nActors:')  # WORKED
    details_actors = soup.select_one('b:-soup-contains("В ролях:")').find_next_sibling().text
    print(details_actors)

    print('\nPlot:')  # WORKED
    details_plot = soup.select_one('b:-soup-contains("О фильме:")').next_sibling.text.strip()
    print(details_plot)

    print('\nTranslate:')  # WORKED
    details_translate_search = (soup.select_one('b:-soup-contains("Перевод:")'))
    if details_translate_search:
        details_translate = details_translate_search.next_sibling.strip()
        print(details_translate)

    print('\nPoster:')  #
    details_poster = soup.find('img', 'p200').attrs['src']
    # or can be constructed via https://kinozal.tv/i/poster/7/6/<ID>.jpg
    print(details_poster)
    print('=====================\n\n')

    # -- для анализа --
    # countries (with studios, but this no matter)
    # genres
    # ratings

    # -- информативная часть --
    # link to poster
    # plot
    return ...


if __name__ == '__main__':
    parse_detail()