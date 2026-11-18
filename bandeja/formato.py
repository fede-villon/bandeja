"""Formato de montos al estilo argentino: $12.345,67."""


def pesos(n: float) -> str:
    return f"${n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def cantidad(n: float) -> str:
    return f"{n:g}".replace(".", ",")
