def is_float(string):
    if string.replace(".", "").isnumeric():
        return True
    else:
        return False