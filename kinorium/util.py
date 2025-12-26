def year_to_int(year: str) -> int:
    try:
        year = int(year)
    except ValueError:
        raise Exception('Year not int')
    return year
