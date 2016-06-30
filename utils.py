from itertools import tee, filterfalse


def partition(predicate, lst):
    a, b = tee(lst)
    return (filter(predicate, a), filterfalse(predicate, b))
