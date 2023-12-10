def tst():
    x = 0

    while True:
        x += 1
        print(x)
        if x == 15:
            return x

def tst1():
    return False, False


if __name__ == '__main__':
    if tst1():
        print(True)
    else:
        print(False)

    tst()