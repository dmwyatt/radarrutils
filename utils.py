import operator
from functools import reduce


def humanbytes_storage(bytes_):
    """
    Return the given bytes as a human friendly KB, MB, GB, or TB string

    >>> tests = [1, 1024, 500000, 1048576, 50000000, 1073741824, 5000000000, 1099511627776, 5000000000000]
    >>> for t in tests: print('{0} == {1}'.format(t, humanbytes_storage(t)))
    1 == 1.0 Byte
    1024 == 1.00 KB
    500000 == 488.28 KB
    1048576 == 1.00 MB
    50000000 == 47.68 MB
    1073741824 == 1.00 GB
    5000000000 == 4.66 GB
    1099511627776 == 1.00 TB
    5000000000000 == 4.55 TB
    """
    bytes_ = float(bytes_)
    kilobytes = float(1024)
    megabytes = float(kilobytes ** 2)  # 1,048,576
    gigabytes = float(kilobytes ** 3)  # 1,073,741,824
    terabytes = float(kilobytes ** 4)  # 1,099,511,627,776

    if bytes_ < kilobytes:
        return "{0} {1}".format(bytes_, "Bytes" if 0 == bytes_ > 1 else "Byte")
    elif kilobytes <= bytes_ < megabytes:
        return "{0:.2f} KB".format(bytes_ / kilobytes)
    elif megabytes <= bytes_ < gigabytes:
        return "{0:.2f} MB".format(bytes_ / megabytes)
    elif gigabytes <= bytes_ < terabytes:
        return "{0:.2f} GB".format(bytes_ / gigabytes)
    elif terabytes <= bytes_:
        return "{0:.2f} TB".format(bytes_ / terabytes)


def humanbytes_transfer(bytes_):
    return f"{humanbytes_storage(bytes_)}/s"


def get_by_path(root, items, default=None):
    """Access a nested object in root by item sequence."""
    try:
        return reduce(operator.getitem, items, root)
    except KeyError:
        return default
