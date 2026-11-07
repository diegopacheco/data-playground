import hashlib
import math
import re

DIMENSIONS = 256
TOKEN = re.compile(r"[a-z0-9]+")


def tokens(text):
    return TOKEN.findall(text.lower())


def bucket(token):
    digest = hashlib.md5(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % DIMENSIONS
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return index, sign


def embed(text):
    vector = [0.0] * DIMENSIONS
    for token in tokens(text):
        index, sign = bucket(token)
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]
