def due(elapsed_s: float, rate: int, sent: int, cap: int) -> int:
    if rate <= 0:
        return cap
    return max(0, min(int(elapsed_s * rate) - sent, cap))
