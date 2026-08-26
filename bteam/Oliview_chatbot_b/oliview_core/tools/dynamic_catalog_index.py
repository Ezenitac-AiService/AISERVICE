"""
Dynamic Catalog Index Module (Feature 039 / Spec 039).
Indexes review-bearing products and brands (COUNT(reviews) >= 1) dynamically from DBMS to eliminate 0-review hallucinations.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any
from functools import lru_cache

from ..logger import get_logger

logger = get_logger("oliview.tools.catalog_index")


@dataclass
class ProductCatalogEntry:
    product_id: int
    product_name: str
    clean_product_name: str
    brand_name: str
    category: str
    total_review_count: int
    avg_rating: float
    series_name: Optional[str] = None
    product_url: Optional[str] = None


@dataclass
class CategoryRecommendationCandidate:
    product_id: int
    product_name: str
    brand_name: str
    category: str
    target_aspect: str
    positive_ratio: float
    composite_score: float
    total_review_count: int
    avg_rating: float
    rank: int


def _clean_korean_name(name: str) -> str:
    """Removes special characters and extra whitespaces for fuzzy normalization."""
    return re.sub(r"[^가-힣a-zA-Z0-9\s]", "", name).strip().lower()


class DynamicCatalogIndex:
    """
    In-memory review-bearing product and brand index.
    Guarantees sub-millisecond query validation and aspect-based category candidate retrieval.
    """

    def __init__(self):
        self.active_brands: Set[str] = set()
        self.products_by_category: Dict[str, List[ProductCatalogEntry]] = {}
        self.product_by_name: Dict[str, ProductCatalogEntry] = {}
        self.product_by_id: Dict[int, ProductCatalogEntry] = {}
        self.is_loaded: bool = False

    def load_from_records(self, records: List[Dict[str, Any]]):
        """Loads and filters records where total_review_count >= 1."""
        self.active_brands.clear()
        self.products_by_category.clear()
        self.product_by_name.clear()
        self.product_by_id.clear()

        for row in records:
            review_count = int(row.get("total_review_count") or row.get("review_count") or 0)
            if review_count < 1:
                # Exclude 0-review ghost products
                continue

            prod_id = int(row.get("product_id") or 0)
            p_name = str(row.get("product_name") or "").strip()
            b_name = str(row.get("brand_name") or "").strip()
            cat = str(row.get("category") or "화장품").strip()
            avg_rate = float(row.get("avg_rating") or row.get("rating") or 5.0)
            clean_name = _clean_korean_name(p_name)

            entry = ProductCatalogEntry(
                product_id=prod_id,
                product_name=p_name,
                clean_product_name=clean_name,
                brand_name=b_name,
                category=cat,
                total_review_count=review_count,
                avg_rating=avg_rate,
                product_url=row.get("product_url"),
            )

            if b_name:
                self.active_brands.add(b_name)

            if cat not in self.products_by_category:
                self.products_by_category[cat] = []
            self.products_by_category[cat].append(entry)

            self.product_by_name[clean_name] = entry
            self.product_by_name[p_name] = entry
            if prod_id:
                self.product_by_id[prod_id] = entry

        self.is_loaded = True
        logger.info(f"DynamicCatalogIndex loaded: {len(self.active_brands)} brands, {len(self.product_by_id)} review-bearing products.")

    def is_brand_active(self, brand_name: str) -> bool:
        """Returns True if the brand has at least 1 collected review in DB."""
        return brand_name in self.active_brands

    def get_products_by_category(self, category_keyword: str) -> List[ProductCatalogEntry]:
        """Returns all review-bearing products matching category keyword."""
        results = []
        for cat, items in self.products_by_category.items():
            if category_keyword.lower() in cat.lower() or cat.lower() in category_keyword.lower():
                results.extend(items)
        return results

    def rank_aspect_candidates(
        self,
        aspect_records: List[Dict[str, Any]],
        target_aspect: str,
        category_keyword: Optional[str] = None,
        min_reviews: int = 5,
        top_k: int = 3,
    ) -> List[CategoryRecommendationCandidate]:
        """
        Ranks products for open recommendation queries based on composite score:
        composite_score = positive_ratio * 0.7 + log(review_count + 1) * 0.3
        Enforces min_reviews threshold to eliminate small sample bias.
        """
        candidates = []
        seen_prod_ids = set()

        for row in aspect_records:
            prod_id = int(row.get("product_id") or 0)
            if prod_id in seen_prod_ids:
                continue

            review_count = int(row.get("total_review_count") or row.get("review_count") or 0)
            if review_count < min_reviews:
                continue

            cat = str(row.get("category") or "")
            if category_keyword and category_keyword not in cat:
                continue

            pos_ratio = float(row.get("positive_ratio") or 0.0)
            avg_rate = float(row.get("avg_rating") or 5.0)
            p_name = str(row.get("product_name") or "")
            b_name = str(row.get("brand_name") or "")

            composite_score = (pos_ratio * 0.7) + (math.log(review_count + 1) * 0.3)

            candidates.append(
                CategoryRecommendationCandidate(
                    product_id=prod_id,
                    product_name=p_name,
                    brand_name=b_name,
                    category=cat,
                    target_aspect=target_aspect,
                    positive_ratio=pos_ratio,
                    composite_score=composite_score,
                    total_review_count=review_count,
                    avg_rating=avg_rate,
                    rank=0,
                )
            )
            seen_prod_ids.add(prod_id)

        # Sort by composite_score desc, then avg_rating desc
        candidates.sort(key=lambda x: (x.composite_score, x.avg_rating), reverse=True)

        for idx, c in enumerate(candidates[:top_k], start=1):
            c.rank = idx

        return candidates[:top_k]


# Global singleton instance
_GLOBAL_CATALOG_INDEX = DynamicCatalogIndex()


def get_dynamic_catalog_index() -> DynamicCatalogIndex:
    return _GLOBAL_CATALOG_INDEX
