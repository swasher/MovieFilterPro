def tst():
    x = 0

    while True:
        x += 1
        print(x)
        if x == 15:
            return x

def tst1():

    def ret_bool():
        return False, False

    if ret_bool():
        print(True)
    else:
        print(False)


def tst3():
    l = ['Apple', 'Banana', 'Berry', 'Cherry']
    for i in l:
        if i in ['Banana', 'Berry']:
            l.remove(i)
    print(l)

import re
import datetime
def tst4():
    a1 = 'Луна / Deo mun (The Moon) / 202 3 / ДБ, СТ / WEB-DL (1080p)'
    print('/' in a1)

    a2 = 'Луна  Deo mun (The Moon) 2023 ДБ, СТ'
    removed_spaces = re.sub(r'\s+', ' ', a2)
    b = [element.strip() for element in removed_spaces.split(' ')]
    print(' '.join(b[:5]))

    match = re.search(r'\d{4}', a1)
    if match:
        year = str(match.group())
    else:
        year = str(datetime.now().year)
    print(year)

if __name__ == '__main__':
    tst4()
