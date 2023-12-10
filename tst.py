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


if __name__ == '__main__':
    tst3()
