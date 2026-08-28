"""Binary BCH(63,45,t=3) codec used by the RadialCode bootstrap header.

The code is a primitive narrow-sense binary BCH code over GF(2^6). The binary
systematic generator polynomial was derived from roots alpha^1 through alpha^6:

    g(x) = x^18 + x^17 + x^16 + x^15 + x^9 + x^7 + x^6
           + x^3 + x^2 + x + 1
"""

from __future__ import annotations

from functools import lru_cache
from itertools import combinations

BCH_N = 63
BCH_K = 45
BCH_PARITY_BITS = BCH_N - BCH_K
BCH_T = 3
BCH_GENERATOR = 0x782CF

# GF(2^6) defined by x^6 + x + 1, with alpha = x.
_GF_PRIMITIVE = 0x43
_GF_SIZE = 64
_GF_ORDER = 63


class BchDecodeError(ValueError):
    """Raised when a header codeword is outside the t=3 decoding radius."""


def _degree(polynomial: int) -> int:
    return polynomial.bit_length() - 1


def _poly_mod(dividend: int, divisor: int) -> int:
    divisor_degree = _degree(divisor)
    while dividend and _degree(dividend) >= divisor_degree:
        dividend ^= divisor << (_degree(dividend) - divisor_degree)
    return dividend


def _gf_mul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        b >>= 1
        a <<= 1
        if a & _GF_SIZE:
            a ^= _GF_PRIMITIVE
    return result & (_GF_SIZE - 1)


@lru_cache(maxsize=None)
def _alpha(power: int) -> int:
    value = 1
    for _ in range(power % _GF_ORDER):
        value = _gf_mul(value, 2)
    return value


def _evaluate_binary_polynomial(polynomial: int, x: int) -> int:
    result = 0
    for degree in range(BCH_N - 1, -1, -1):
        result = _gf_mul(result, x)
        if (polynomial >> degree) & 1:
            result ^= 1
    return result


def syndromes(codeword: int) -> tuple[int, ...]:
    if codeword < 0 or codeword >= (1 << BCH_N):
        raise ValueError("codeword must fit in 63 bits")
    return tuple(_evaluate_binary_polynomial(codeword, _alpha(exponent)) for exponent in range(1, 7))


def encode(data: int) -> int:
    """Encode one 45-bit integer into a systematic 63-bit codeword."""

    if data < 0 or data >= (1 << BCH_K):
        raise ValueError("BCH data must fit in 45 bits")
    shifted = data << BCH_PARITY_BITS
    parity = _poly_mod(shifted, BCH_GENERATOR)
    codeword = shifted | parity
    if any(syndromes(codeword)):
        raise AssertionError("internal BCH encoder failure")
    return codeword


@lru_cache(maxsize=1)
def _error_lookup() -> dict[tuple[int, ...], int]:
    single = [syndromes(1 << bit) for bit in range(BCH_N)]
    lookup: dict[tuple[int, ...], int] = {}

    for bit, signature in enumerate(single):
        lookup[signature] = 1 << bit

    for a, b in combinations(range(BCH_N), 2):
        signature = tuple(x ^ y for x, y in zip(single[a], single[b], strict=True))
        lookup.setdefault(signature, (1 << a) | (1 << b))

    for a, b, c in combinations(range(BCH_N), 3):
        signature = tuple(x ^ y ^ z for x, y, z in zip(single[a], single[b], single[c], strict=True))
        lookup.setdefault(signature, (1 << a) | (1 << b) | (1 << c))

    return lookup


def decode(codeword: int) -> tuple[int, int, int]:
    """Decode a 63-bit codeword.

    Returns ``(data, corrected_codeword, corrected_bit_count)``. The decoder is
    bounded-distance and corrects every error pattern of Hamming weight <= 3.
    """

    if codeword < 0 or codeword >= (1 << BCH_N):
        raise ValueError("codeword must fit in 63 bits")

    signature = syndromes(codeword)
    if not any(signature):
        return codeword >> BCH_PARITY_BITS, codeword, 0

    try:
        error_mask = _error_lookup()[signature]
    except KeyError as exc:
        raise BchDecodeError("BCH codeword is not correctable within t=3") from exc

    corrected = codeword ^ error_mask
    if any(syndromes(corrected)):
        raise BchDecodeError("candidate BCH correction failed syndrome validation")
    return corrected >> BCH_PARITY_BITS, corrected, error_mask.bit_count()


def int_to_bits(value: int, length: int) -> tuple[int, ...]:
    if value < 0 or value >= (1 << length):
        raise ValueError(f"value must fit in {length} bits")
    return tuple((value >> shift) & 1 for shift in range(length - 1, -1, -1))


def bits_to_int(bits: tuple[int, ...] | list[int]) -> int:
    value = 0
    for bit in bits:
        if bit not in (0, 1):
            raise ValueError("bits must contain only 0 and 1")
        value = (value << 1) | bit
    return value
