from __future__ import annotations

import os
from typing import Optional
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from src.service import CardPricingService
from src.normalizer import clean_card_number

app = FastAPI(
    title="CardCache Pricing API",
    description="Multi-source market pricing engine aggregating eBay, SportsCardsPro, and Sportlots for collectible sports cards.",
    version="1.0.0"
)

# Allow CORS for Android devices, web views, and local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pricing_service = CardPricingService()


@app.get("/")
def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "CardCache Pricing API",
        "version": "1.0.0"
    }


@app.get("/api/v1/comps")
def get_card_comps(
    response: Response,
    series_name: str = Query(..., description="Card series/set name (e.g., '2006 Topps Chrome')"),
    player_name: str = Query(..., description="Athlete/Subject name (e.g., 'A.J. Hawk')"),
    card_number: str = Query(..., description="Card number (e.g., '222' or 'TTR-48')"),
    year: Optional[str] = Query(None, description="Release year (e.g., '2006')"),
    manufacturer: Optional[str] = Query(None, description="Manufacturer (e.g., 'Topps', 'Upper Deck', 'Panini')"),
    parallel_name: Optional[str] = Query(None, description="Parallel / Variant name (e.g., 'Refractor', 'Red Relic')"),
    source: str = Query("all", description="Source to query: 'all', 'ebay', 'sportscardspro', 'sportlots'"),
    limit: int = Query(50, ge=1, le=100, description="Max comps to return per source"),
    include_history: bool = Query(True, description="Whether to include historical sales data")
):
    """
    Fetches market valuations, condition benchmarks, and comp transactions across eBay, SportsCardsPro, and Sportlots.
    Sets Cache-Control headers so Cloudflare edge can cache identical lookups for 24 hours.
    """
    clean_num = clean_card_number(card_number)
    if not clean_num:
        raise HTTPException(status_code=400, detail="Card number cannot be empty.")

    metadata = {
        "series_name": series_name.strip(),
        "series_year": year.strip() if year else None,
        "manufacturer_name": manufacturer.strip() if manufacturer else None,
        "parallel_name": parallel_name.strip() if parallel_name else None
    }

    sources = [s.strip().lower() for s in source.split(",") if s.strip()]

    result = pricing_service.get_card_comps(
        metadata=metadata,
        player_name=player_name.strip(),
        card_number=clean_num,
        sources=sources,
        limit=limit,
        include_historical=include_history
    )

    # Instruct Cloudflare edge to cache successful results for 24 hours (86400s)
    # Browser / mobile app caches for 1 hour (3600s)
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"

    return result


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, reload=True)
