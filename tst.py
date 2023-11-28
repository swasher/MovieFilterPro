

def tst():
    x = 0

    while True:
        x += 1
        print(x)
        if x == 15:
            return x

if __name__ == '__main__':
    g = tst()
    print(f'The end! with {g}')