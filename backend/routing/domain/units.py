"""Unit conversions used at provider boundaries."""

KG_PER_LB = 0.45359237
METERS_PER_MILE = 1609.344


def lb_to_kg(pounds: float) -> int:
    """Whole kilograms, as sent to HERE ``vehicle[grossWeight]``."""
    return round(pounds * KG_PER_LB)


def gross_weight_kg(load_lb: float, empty_truck_lb: float) -> int:
    """Loaded truck weight for routing (empty truck + cargo). Risk rules use the cargo load only."""
    return lb_to_kg(empty_truck_lb + load_lb)


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE
