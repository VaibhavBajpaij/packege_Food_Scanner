"""NutriTruth (खाद्य) - High-Speed FastAPI Transparency & Deceptive Label API.

Provides:
- Real-time deceptive sugar alias detection (56+ aliases)
- Palm oil and disguised vegetable fat detection
- NOVA-4 ultra-processed food classification
- FSSAI Indian Nutrition Rating (INR 1.0 - 5.0 Stars)
- Serving size illusion and true whole-pack impact calculation
- Local SQLite database matching & healthy alternative swaps
"""

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from food_engine.deception_detector import DeceptiveLabelBuster
from food_engine.product_matching.matcher import ProductMatcher


REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "datasets" / "processed" / "products" / "products.db"

app = FastAPI(
    title="NutriTruth (खाद्य) API",
    description="Open-Source Packaged Food Transparency Engine & Deceptive Label Buster",
    version="1.0.0",
)

# Enable CORS for browser integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

buster = DeceptiveLabelBuster(db_path=str(DB_PATH))
matcher = ProductMatcher(repo_root=str(REPO_ROOT))

# Verified Real Products for Instant Testing
DEMO_PRODUCTS = {
    "bournvita": {
        "product_name": "Cadbury Bournvita",
        "brand": "Cadbury / Mondelez",
        "category": "Health Drink Mix",
        "ingredients_text": "Malt extract (44%), Sugar, Cocoa solids, Milk solids, Liquid glucose, Maltodextrin, Invert sugar syrup, Emulsifiers (INS 322, INS 471), Minerals, Vitamins, Salt, Caramel IV (INS 150d).",
        "nutrients": {
            "energy_kcal": 380.0,
            "sugars_100g": 32.2,
            "saturated_fat_100g": 1.8,
            "sodium_mg": 180.0,
            "fiber_100g": 3.0,
            "proteins_100g": 7.0,
        },
        "serving_size_g": 20.0,
        "pack_weight_g": 500.0,
    },
    "parle-g": {
        "product_name": "Parle-G Gluco Biscuits",
        "brand": "Parle",
        "category": "Biscuits & Cookies",
        "ingredients_text": "Wheat Flour (65%), Sugar, Edible Vegetable Oil (Palmolein), Invert Sugar Syrup, Leavening Agents (INS 503ii, INS 500ii), Salt, Milk Solids, Emulsifier (INS 322), Dough Conditioner (INS 223).",
        "nutrients": {
            "energy_kcal": 454.0,
            "sugars_100g": 26.5,
            "saturated_fat_100g": 6.5,
            "sodium_mg": 280.0,
            "fiber_100g": 1.5,
            "proteins_100g": 6.5,
        },
        "serving_size_g": 25.0,
        "pack_weight_g": 100.0,
    },
    "maggi": {
        "product_name": "Maggi 2-Minute Masala Noodles",
        "brand": "Nestle",
        "category": "Instant Noodles",
        "ingredients_text": "Refined wheat flour (Maida), Palm oil, Salt, Wheat gluten, Mineral (Calcium carbonate), Thickener (INS 508), Acidity regulator (INS 501i, INS 500i). Masala Tastemaker: Hydrolysed groundnut protein, Mixed spices (Onion powder, Coriander, Chili, Turmeric), Noodle powder, Sugar, Edible starch, Palm oil, Flavor enhancer (INS 635), Caramel (INS 150d).",
        "nutrients": {
            "energy_kcal": 427.0,
            "sugars_100g": 2.2,
            "saturated_fat_100g": 6.8,
            "sodium_mg": 1150.0,
            "fiber_100g": 3.6,
            "proteins_100g": 8.0,
        },
        "serving_size_g": 70.0,
        "pack_weight_g": 70.0,
    },
    "oreo": {
        "product_name": "Oreo Original Sandwich Cookies",
        "brand": "Oreo / Mondelez",
        "category": "Cookies & Confectionery",
        "ingredients_text": "Refined Wheat Flour, Sugar, Edible Vegetable Fat (Palm Oil, Fractionated Palm Oil), Invert Sugar Syrup, High Fructose Corn Syrup, Cocoa Solids (2.3%), Leavening Agents (INS 500ii, INS 503ii), Salt, Emulsifier (INS 322).",
        "nutrients": {
            "energy_kcal": 482.0,
            "sugars_100g": 38.5,
            "saturated_fat_100g": 9.8,
            "sodium_mg": 380.0,
            "fiber_100g": 2.0,
            "proteins_100g": 5.2,
        },
        "serving_size_g": 28.0,
        "pack_weight_g": 120.0,
    },
    "lays-chips": {
        "product_name": "Lay's India's Magic Masala",
        "brand": "Lay's / PepsiCo",
        "category": "Potato Chips & Snacks",
        "ingredients_text": "Potato, Edible Vegetable Oil (Palmolein Oil, Rice Bran Oil), Seasoning (Spices and Condiments, Sugar, Iodised Salt, Maltodextrin, Flavor Enhancers (INS 627, INS 631), Emulsifier (INS 414), Anticaking Agent (INS 551)).",
        "nutrients": {
            "energy_kcal": 555.0,
            "sugars_100g": 3.5,
            "saturated_fat_100g": 12.0,
            "sodium_mg": 790.0,
            "fiber_100g": 4.0,
            "proteins_100g": 7.0,
        },
        "serving_size_g": 20.0,
        "pack_weight_g": 90.0,
    },
    "amul-milk": {
        "product_name": "Amul Taaza Homogenised Toned Milk",
        "brand": "Amul (GCMMF)",
        "category": "Fresh Dairy",
        "ingredients_text": "Toned milk, Vitamin A, Vitamin D2.",
        "nutrients": {
            "energy_kcal": 58.2,
            "sugars_100g": 4.7,  # Naturally occurring milk lactose
            "saturated_fat_100g": 1.9,
            "sodium_mg": 50.0,
            "fiber_100g": 0.0,
            "proteins_100g": 3.1,
        },
        "serving_size_g": 200.0,
        "pack_weight_g": 1000.0,
    },
}


class AnalysisRequest(BaseModel):
    barcode: Optional[str] = None
    product_name: Optional[str] = "Packaged Food Item"
    brand: Optional[str] = None
    category: Optional[str] = None
    ingredients_text: Optional[str] = ""
    nutrients: Optional[Dict[str, Any]] = Field(default_factory=dict)
    serving_size_g: Optional[float] = 20.0
    pack_weight_g: Optional[float] = 100.0


@app.get("/api/v1/health")
def health():
    db_connected = DB_PATH.exists()
    row_count = 0
    if db_connected:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM off_products")
            row_count = cur.fetchone()[0]
            conn.close()
        except Exception:
            pass

    return {
        "status": "UP",
        "service": "NutriTruth (खाद्य) Transparency Core",
        "version": "1.0.0",
        "database": {
            "connected": db_connected,
            "verified_products_count": row_count,
            "path": str(DB_PATH),
        },
        "modules": [
            "Deceptive Sugar Alias Buster (56+ Aliases)",
            "Palm Oil / Palmolein Disguise Detector",
            "NOVA 1-4 Industrial Processing Classifier",
            "FSSAI Indian Nutrition Rating (1-5 Stars)",
            "Manufacturer Serving Size Reality Check",
            "Clean Alternative Swaps Engine",
        ],
    }


@app.get("/api/v1/demo/{demo_id}")
def run_demo(demo_id: str):
    key = demo_id.lower().strip()
    if key not in DEMO_PRODUCTS:
        raise HTTPException(status_code=404, detail=f"Demo '{demo_id}' not found. Available: {list(DEMO_PRODUCTS.keys())}")

    item = DEMO_PRODUCTS[key]
    result = buster.analyze_label(
        product_name=item["product_name"],
        ingredients_text=item["ingredients_text"],
        nutrients=item["nutrients"],
        serving_size_g=item["serving_size_g"],
        pack_weight_g=item["pack_weight_g"],
        brand=item["brand"],
        category=item["category"],
    )
    result["raw_input"] = item
    return result


@app.post("/api/v1/analyze")
def analyze_product(req: AnalysisRequest):
    p_name = req.product_name or "Custom Product"
    p_brand = req.brand
    p_category = req.category
    ingr = req.ingredients_text or ""
    nutrients = dict(req.nutrients or {})

    # If barcode provided and no ingredients given, auto-lookup in database or live API
    if req.barcode and not ingr:
        match_res = matcher.match(barcode=req.barcode, allow_online=True)
        if match_res and match_res.get("matched_data"):
            m = match_res["matched_data"]
            p_name = m.get("product_name") or p_name
            p_brand = m.get("brands") or p_brand
            p_category = m.get("categories") or p_category
            ingr = m.get("ingredients_text") or ingr
            if m.get("nutrients"):
                for k, v in m["nutrients"].items():
                    if v is not None and k not in nutrients:
                        nutrients[k] = v

    result = buster.analyze_label(
        product_name=p_name,
        ingredients_text=ingr,
        nutrients=nutrients,
        serving_size_g=req.serving_size_g,
        pack_weight_g=req.pack_weight_g,
        brand=p_brand,
        category=p_category,
    )
    return result


@app.get("/api/v1/swaps")
def get_swaps(category: str = Query("biscuits", description="Food category (e.g. biscuits, cereals, snacks)")):
    swaps = buster._find_healthier_swaps(category=category, current_sugars=25.0, has_palm_oil=True)
    return {
        "category": category,
        "count": len(swaps),
        "recommendations": swaps,
    }


# Beautiful Interactive Web UI
@app.get("/", response_class=HTMLResponse)
def index_page():
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NutriTruth (खाद्य) — Packaged Food Transparency Engine</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
    code, pre { font-family: 'JetBrains Mono', monospace; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased selection:bg-emerald-500/30 selection:text-emerald-300">

  <!-- Header -->
  <header class="border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-30 px-4 sm:px-8 py-3.5 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center text-slate-950 font-black shadow-lg shadow-emerald-500/20">
        <i class="fa-solid fa-leaf"></i>
      </div>
      <div>
        <div class="flex items-center gap-2">
          <span class="font-extrabold text-base sm:text-lg tracking-tight text-white">NutriTruth</span>
          <span class="text-xs px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 font-semibold border border-emerald-500/20">खाद्य Engine</span>
        </div>
        <p class="text-[11px] text-slate-400 hidden sm:block">Open-Source Deceptive Label Buster & FSSAI INR Engine</p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <span class="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2.5 py-1 rounded-full">
        <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
        16,593 Verified Products
      </span>
      <a href="/docs" target="_blank" class="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded-lg border border-slate-700 flex items-center gap-1.5 transition">
        <i class="fa-solid fa-code"></i> OpenAPI Specs
      </a>
    </div>
  </header>

  <!-- Main Content -->
  <main class="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-8 py-6 space-y-6">

    <!-- Hero / Problem Banner -->
    <div class="p-6 rounded-2xl bg-gradient-to-r from-slate-900 via-slate-900/80 to-emerald-950/40 border border-slate-800/80 relative overflow-hidden">
      <div class="max-w-3xl space-y-2">
        <div class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold">
          <i class="fa-solid fa-triangle-exclamation"></i> The Deceptive Food Label Crisis
        </div>
        <h1 class="text-xl sm:text-2xl font-extrabold tracking-tight text-white">
          Expose Hidden Sugars, Disguised Palm Oil & Serving Size Tricks
        </h1>
        <p class="text-xs sm:text-sm text-slate-400 leading-relaxed">
          Brands split sugar across 56+ obscure aliases (like <i>Maltodextrin, Liquid Glucose, Invert Syrup</i>) and disguise palm oil as "Edible Vegetable Oil" to deceive consumers. NutriTruth scans ingredients against FSSAI, WHO, and NOVA standards with zero bias.
        </p>
      </div>

      <!-- Quick Demo Selector -->
      <div class="mt-4 pt-4 border-t border-slate-800/80 flex flex-wrap items-center gap-2">
        <span class="text-xs text-slate-400 font-medium mr-1">Instant Real-World Benchmarks:</span>
        <button onclick="loadDemo('bournvita')" class="demo-btn px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-amber-300 border border-slate-700 hover:border-amber-500/50 transition flex items-center gap-1.5">
          <i class="fa-solid fa-mug-hot"></i> Cadbury Bournvita
        </button>
        <button onclick="loadDemo('parle-g')" class="demo-btn px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-orange-300 border border-slate-700 hover:border-orange-500/50 transition flex items-center gap-1.5">
          <i class="fa-solid fa-cookie"></i> Parle-G Biscuits
        </button>
        <button onclick="loadDemo('maggi')" class="demo-btn px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-yellow-300 border border-slate-700 hover:border-yellow-500/50 transition flex items-center gap-1.5">
          <i class="fa-solid fa-bowl-rice"></i> Maggi Noodles
        </button>
        <button onclick="loadDemo('oreo')" class="demo-btn px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-purple-300 border border-slate-700 hover:border-purple-500/50 transition flex items-center gap-1.5">
          <i class="fa-solid fa-cookie-bite"></i> Oreo Cookies
        </button>
        <button onclick="loadDemo('amul-milk')" class="demo-btn px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-emerald-400 border border-slate-700 hover:border-emerald-500/50 transition flex items-center gap-1.5">
          <i class="fa-solid fa-glass-water"></i> Amul Clean Milk (Control)
        </button>
      </div>
    </div>

    <!-- Interactive Analyzer Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">

      <!-- Left Column: Input Form -->
      <div class="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4">
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-bold text-white flex items-center gap-2">
            <i class="fa-solid fa-barcode text-emerald-400"></i> Label Inspection Console
          </h2>
          <span class="text-[11px] text-slate-500 font-mono">POST /api/v1/analyze</span>
        </div>

        <form id="analyzeForm" onsubmit="handleAnalyze(event)" class="space-y-3">
          <div>
            <label class="block text-xs font-medium text-slate-400 mb-1">Product Name</label>
            <input id="productName" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 transition" placeholder="e.g. Cadbury Bournvita" required>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">Brand</label>
              <input id="productBrand" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 transition" placeholder="e.g. Cadbury">
            </div>
            <div>
              <label class="block text-xs font-medium text-slate-400 mb-1">Category</label>
              <input id="productCategory" type="text" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 transition" placeholder="e.g. Biscuits">
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-slate-400 mb-1">Ingredients Declaration (Paste Raw Label)</label>
            <textarea id="ingredientsText" rows="4" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 font-mono transition leading-relaxed" placeholder="e.g. Malt extract (44%), Sugar, Liquid glucose, Maltodextrin, Invert sugar syrup, Edible vegetable oil (palmolein)..." required></textarea>
          </div>

          <!-- Nutritional Numbers -->
          <div class="p-3 bg-slate-950/60 rounded-xl border border-slate-800 space-y-2">
            <span class="text-[11px] font-bold text-slate-300 block">Declared Nutrition (per 100g)</span>
            <div class="grid grid-cols-3 gap-2">
              <div>
                <label class="block text-[10px] text-slate-500">Sugars (g)</label>
                <input id="sugars" type="number" step="0.1" class="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200" placeholder="32.2">
              </div>
              <div>
                <label class="block text-[10px] text-slate-500">Sat. Fat (g)</label>
                <input id="satFat" type="number" step="0.1" class="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200" placeholder="1.8">
              </div>
              <div>
                <label class="block text-[10px] text-slate-500">Sodium (mg)</label>
                <input id="sodium" type="number" step="1" class="w-full bg-slate-900 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200" placeholder="180">
              </div>
            </div>
          </div>

          <!-- Serving Size Tricks -->
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="block text-[11px] text-slate-400">Serving Size (g)</label>
              <input id="servingSize" type="number" step="1" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-200" value="20">
            </div>
            <div>
              <label class="block text-[11px] text-slate-400">Total Pack Weight (g)</label>
              <input id="packWeight" type="number" step="1" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-200" value="500">
            </div>
          </div>

          <button type="submit" id="submitBtn" class="w-full bg-gradient-to-r from-emerald-600 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-slate-950 font-bold py-2.5 rounded-xl shadow-lg shadow-emerald-500/20 text-xs transition flex items-center justify-center gap-2">
            <i class="fa-solid fa-magnifying-glass"></i> Run Transparency Audit
          </button>
        </form>
      </div>

      <!-- Right Column: Live Analysis Report -->
      <div class="lg:col-span-7 space-y-4">

        <!-- Top Score Cards -->
        <div id="resultsCard" class="space-y-4">
          <!-- Initial Welcome Placeholder -->
          <div id="placeholder" class="p-12 text-center border border-dashed border-slate-800 rounded-2xl bg-slate-900/40">
            <i class="fa-solid fa-wand-magic-sparkles text-3xl text-emerald-400 mb-3 block"></i>
            <h3 class="text-base font-bold text-white mb-1">Click Any Benchmark Product Above</h3>
            <p class="text-xs text-slate-400 max-w-md mx-auto">
              Select <b>Cadbury Bournvita</b>, <b>Parle-G</b>, <b>Maggi</b>, or paste any custom package ingredients to see live deceptive sugar alias detection, palm oil flags, and FSSAI star ratings.
            </p>
          </div>

          <!-- Live Output Container (Hidden by default) -->
          <div id="reportContent" class="hidden space-y-4">

            <!-- Primary Metric Header -->
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <!-- Deception Index -->
              <div id="deceptionBox" class="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
                <span class="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">Deception Score</span>
                <div class="my-2 flex items-baseline gap-2">
                  <span id="deceptionScore" class="text-3xl font-black text-red-400">75</span>
                  <span class="text-xs text-slate-500">/ 100</span>
                </div>
                <span id="deceptionTier" class="text-[11px] text-red-300 font-medium">Severe Misdirection</span>
              </div>

              <!-- FSSAI Star Rating -->
              <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
                <span class="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">FSSAI Rating (INR)</span>
                <div class="my-2 flex items-center gap-1.5 text-amber-400 text-lg" id="starContainer">
                  <!-- Stars populated via JS -->
                </div>
                <span id="fssaiGrade" class="text-[11px] text-slate-300 font-medium">1.5 Stars (HFSS)</span>
              </div>

              <!-- NOVA Group -->
              <div class="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col justify-between">
                <span class="text-[11px] text-slate-400 font-semibold uppercase tracking-wider">Processing Tier</span>
                <div class="my-2">
                  <span id="novaBadge" class="px-2.5 py-1 rounded-lg text-xs font-bold bg-red-950 text-red-300 border border-red-800">
                    NOVA 4
                  </span>
                </div>
                <span id="novaName" class="text-[11px] text-slate-400 font-medium">Ultra-Processed Food</span>
              </div>
            </div>

            <!-- Sugar Aliases Alert Card -->
            <div id="sugarCard" class="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2.5">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold text-amber-300 flex items-center gap-2">
                  <i class="fa-solid fa-cubes-stacked"></i> Hidden Sugar Alias Breakdown
                </span>
                <span id="sugarCountBadge" class="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-bold">
                  4 Aliases Detected
                </span>
              </div>
              <p id="sugarWarning" class="text-xs text-slate-300 leading-relaxed"></p>
              <div id="sugarAliasesList" class="flex flex-wrap gap-1.5 pt-1">
                <!-- Badges injected here -->
              </div>
            </div>

            <!-- Palm Oil Warning Card -->
            <div id="palmOilCard" class="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
              <span class="text-xs font-bold text-orange-400 flex items-center gap-2">
                <i class="fa-solid fa-tree"></i> Palm Oil & Disguised Fat Audit
              </span>
              <p id="palmOilWarning" class="text-xs text-slate-300 leading-relaxed"></p>
            </div>

            <!-- Serving Size Deception Card -->
            <div id="servingCard" class="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2">
              <span class="text-xs font-bold text-sky-400 flex items-center gap-2">
                <i class="fa-solid fa-scale-unbalanced"></i> Serving Size Reality Check
              </span>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-center">
                <div class="p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                  <span class="text-[10px] text-slate-500 block">Declared Serving</span>
                  <span id="servingGrams" class="text-xs font-bold text-slate-200">20g</span>
                </div>
                <div class="p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                  <span class="text-[10px] text-slate-500 block">Total Pack</span>
                  <span id="packGrams" class="text-xs font-bold text-slate-200">500g</span>
                </div>
                <div class="p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                  <span class="text-[10px] text-slate-500 block">Per Serving Sugar</span>
                  <span id="servingSugar" class="text-xs font-bold text-amber-400">6.4g</span>
                </div>
                <div class="p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                  <span class="text-[10px] text-slate-500 block">Full Pack Sugar</span>
                  <span id="packSugar" class="text-xs font-bold text-red-400">161g</span>
                </div>
              </div>
              <p id="servingRealityWarning" class="text-xs text-slate-300 pt-1"></p>
            </div>

            <!-- Healthy Alternative Swaps -->
            <div id="swapsCard" class="p-4 rounded-xl bg-slate-900 border border-slate-800 space-y-2.5">
              <span class="text-xs font-bold text-emerald-400 flex items-center gap-2">
                <i class="fa-solid fa-arrow-right-arrow-left"></i> Healthier Alternative Swaps (0g Palm Oil)
              </span>
              <div id="swapsList" class="space-y-2">
                <!-- Swaps injected here -->
              </div>
            </div>

          </div>
        </div>

      </div>

    </div>

  </main>

  <footer class="border-t border-slate-800 bg-slate-900/40 text-center py-4 text-xs text-slate-500">
    NutriTruth (खाद्य) Engine &bull; Grounded in FSSAI, ICMR-NIN & WHO Guidelines &bull; 100% Free & Open-Source
  </footer>

  <script>
    async function loadDemo(demoId) {
      try {
        const res = await fetch(`/api/v1/demo/${demoId}`);
        const data = await res.json();
        
        // Populate form
        const raw = data.raw_input;
        document.getElementById('productName').value = raw.product_name;
        document.getElementById('productBrand').value = raw.brand || '';
        document.getElementById('productCategory').value = raw.category || '';
        document.getElementById('ingredientsText').value = raw.ingredients_text;
        document.getElementById('sugars').value = raw.nutrients.sugars_100g || '';
        document.getElementById('satFat').value = raw.nutrients.saturated_fat_100g || '';
        document.getElementById('sodium').value = raw.nutrients.sodium_mg || '';
        document.getElementById('servingSize').value = raw.serving_size_g || 20;
        document.getElementById('packWeight').value = raw.pack_weight_g || 100;

        renderReport(data);
      } catch (err) {
        alert('Failed to load demo: ' + err);
      }
    }

    async function handleAnalyze(e) {
      e.preventDefault();
      const payload = {
        product_name: document.getElementById('productName').value,
        brand: document.getElementById('productBrand').value,
        category: document.getElementById('productCategory').value,
        ingredients_text: document.getElementById('ingredientsText').value,
        nutrients: {
          sugars_100g: parseFloat(document.getElementById('sugars').value) || 0,
          saturated_fat_100g: parseFloat(document.getElementById('satFat').value) || 0,
          sodium_mg: parseFloat(document.getElementById('sodium').value) || 0,
        },
        serving_size_g: parseFloat(document.getElementById('servingSize').value) || 20,
        pack_weight_g: parseFloat(document.getElementById('packWeight').value) || 100,
      };

      try {
        const res = await fetch('/api/v1/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        renderReport(data);
      } catch (err) {
        alert('Analysis error: ' + err);
      }
    }

    function renderReport(data) {
      document.getElementById('placeholder').classList.add('hidden');
      document.getElementById('reportContent').classList.remove('hidden');

      // Deception
      document.getElementById('deceptionScore').innerText = data.deception_score;
      document.getElementById('deceptionTier').innerText = data.deception_tier;

      // FSSAI Stars
      const starContainer = document.getElementById('starContainer');
      starContainer.innerHTML = '';
      const fullStars = Math.floor(data.fssai_inr.stars);
      const hasHalf = data.fssai_inr.stars % 1 !== 0;
      for (let i = 0; i < fullStars; i++) {
        starContainer.innerHTML += '<i class=\"fa-solid fa-star\"></i>';
      }
      if (hasHalf) {
        starContainer.innerHTML += '<i class=\"fa-solid fa-star-half-stroke\"></i>';
      }
      document.getElementById('fssaiGrade').innerText = `${data.fssai_inr.stars} Stars (${data.fssai_inr.grade})`;

      // NOVA
      const nova = data.nova_classification;
      document.getElementById('novaBadge').innerText = `NOVA ${nova.nova_group}`;
      document.getElementById('novaName').innerText = nova.nova_name;

      // Sugars
      const sugar = data.sugar_analysis;
      document.getElementById('sugarCountBadge').innerText = `${sugar.detected_count} Aliases Detected`;
      document.getElementById('sugarWarning').innerText = sugar.warning;
      const aliasesList = document.getElementById('sugarAliasesList');
      aliasesList.innerHTML = '';
      sugar.aliases.forEach(a => {
        aliasesList.innerHTML += `<span class=\"px-2 py-1 rounded bg-slate-800 text-amber-300 text-xs font-mono border border-amber-500/30\">
          ${a.alias} <span class=\"text-[10px] text-slate-400\">(GI: ${a.glycemic_index})</span>
        </span>`;
      });

      // Palm Oil
      const palm = data.palm_oil_analysis;
      document.getElementById('palmOilWarning').innerText = palm.warning;

      // Serving
      const serv = data.serving_size_reality;
      document.getElementById('servingGrams').innerText = `${serv.declared_serving_size_g}g`;
      document.getElementById('packGrams').innerText = `${serv.total_pack_weight_g}g`;
      document.getElementById('servingSugar').innerText = `${serv.per_serving_sugar_g}g`;
      document.getElementById('packSugar').innerText = `${serv.full_pack_sugar_g}g (${serv.who_daily_sugar_pct}% WHO Limit)`;
      document.getElementById('servingRealityWarning').innerText = serv.reality_warning;

      // Swaps
      const swapsList = document.getElementById('swapsList');
      swapsList.innerHTML = '';
      if (data.healthy_swaps && data.healthy_swaps.length > 0) {
        data.healthy_swaps.forEach(s => {
          swapsList.innerHTML += `
            <div class=\"p-2.5 rounded-lg bg-slate-950 border border-emerald-900/40 flex items-center justify-between\">
              <div>
                <span class=\"text-xs font-bold text-slate-200 block\">${s.product_name}</span>
                <span class=\"text-[11px] text-slate-400\">Brand: ${s.brand} &bull; ${s.advantage}</span>
              </div>
              <div class=\"text-right\">
                <span class=\"text-xs font-bold text-emerald-400 block\">${s.sugars_100g}g Sugar</span>
                <span class=\"text-[10px] text-slate-500\">0g Palm Oil</span>
              </div>
            </div>
          `;
        });
      } else {
        swapsList.innerHTML = '<span class=\"text-xs text-slate-500\">No lower-sugar alternatives found in immediate category query.</span>';
      }
    }
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
