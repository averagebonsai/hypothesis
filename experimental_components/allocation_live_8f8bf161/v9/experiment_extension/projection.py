from collections.abc import Sequence


def project_simplex(target: Sequence[float], budget: float) -> list[float]:
    n = len(target)
    order = sorted(target, reverse=True)
    css = 0.0
    lam = 0.0
    for i, v in enumerate(order, start=1):
        css += v
        t = (css - budget) / i
        if i == n or order[i] <= t:
            lam = t
            break
    return [max(float(v) - float(lam), 0.0) for v in target]
