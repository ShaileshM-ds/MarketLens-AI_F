"""Launch categories and collection names (docs/SCOPE.md section 4)."""

from dataclasses import dataclass

PRODUCTS_COLLECTION = "products"


@dataclass(frozen=True)
class Category:
    slug: str
    label: str


LAUNCH_CATEGORIES: tuple[Category, ...] = (
    Category("mens-clothing", "Men's clothing"),
    Category("womens-clothing", "Women's clothing"),
    Category("cameras", "Cameras"),
    Category("smart-home", "Smart home"),
    Category("wearables", "Wearables"),
    Category("mobile-phones", "Mobile phones"),
    Category("home-appliances", "Home appliances"),
    Category("computer-accessories", "Computer accessories"),
)
