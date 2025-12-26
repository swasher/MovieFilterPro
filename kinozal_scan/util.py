def is_float(string):
    if string.replace(".", "").isnumeric():
        return True
    else:
        return False


def not_match_rating(movie_rating: float | None, filter_rating: float | None) -> bool:
    """
    Возвращает True, если рейтинг фильмы ниже заданного.
    Если у фильма нет рейтинга, то фильм проходит проверку (возв. False)
    """
    if movie_rating:
        if movie_rating < filter_rating:
            return True
    return False


def get_object_or_none(klass, *args, **kwargs):
    """
    Use get() to return an object, or returns None if the object
    does not exist instead of throwing an exception.
    klass may be a Model, Manager, or QuerySet object. All other passed
    arguments and keyword arguments are used in the get() query.
    Like with QuerySet.get(), MultipleObjectsReturned is raised if more than
    one object is found.
    """
    queryset = klass._default_manager.all() if hasattr(klass, "_default_manager") else klass
    if not hasattr(queryset, "get"):
        klass__name = (
            klass.__name__ if isinstance(klass, type) else klass.__class__.__name__
        )
        raise ValueError(
            "First argument to get_object_or_none() must be a Model, Manager, "
            "or QuerySet, not '%s'." % klass__name
        )
    try:
        return queryset.get(*args, **kwargs)
    except queryset.model.DoesNotExist:
        return None
