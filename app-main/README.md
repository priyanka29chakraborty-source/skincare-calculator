# Skincare Worth Calculator

A science-backed skincare product analysis tool that evaluates ingredients, formulation quality, safety, and price value.

---

## Features

### Core Analysis (Main Worth Score 0-100)
- **Component A (45pts)**: Active ingredient strength with evidence and concentration weighting
- **Component B (20pts)**: Formulation quality (preservatives, delivery systems, functional balance)
- **Component C (15pts)**: Claim accuracy vs actual ingredients
- **Component D (10pts)**: Safety profile (irritation risk, allergens, pregnancy safety)
- **Component E (10pts)**: Price rationality vs category/country averages

### Skin Concern Fit (0-100%)
Personalized scoring for 14 concerns:
- Acne & Oily Skin, Pigmentation, Aging & Fine Lines, Barrier Repair, Sensitive Skin
- Hydration, Large Pores, Dullness, Uneven Texture, Dark Circles, Puffiness
- Sun Protection, UV Damage, Tanning (UV filter detection, photostability, spectrum coverage)

### Skin Type Compatibility (0-100%)
Evaluates formula suitability for: Oily, Dry, Combination, Sensitive, Normal skin types.

### Better Alternatives
- Triggers when any concern fit score < 75%
- Same-category products only

### Best Price Comparison
- Multi-source price search (DuckDuckGo + SerpAPI)
- Same-product verification

### Product Data Fetching
5-layer scraping pipeline:
1. Shopify JSON endpoint
2. cloudscraper (Cloudflare bypass)
3. Firecrawl API
4. ScrapeDo API
5. ScraperAPI

### Admin Dashboard
Password-protected panel at `/admin` with usage analytics, API credit tracking, and fetch logs.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React.js, Axios, Font Awesome |
| Backend | FastAPI (Python), Pydantic |
| Data | CSV-based ingredient database, SQLite (logs.db) |
| Scraping | cloudscraper, Firecrawl, ScrapeDo, ScraperAPI |
| Search | DuckDuckGo, SerpAPI (fallback) |

---

## Project Structure

```
app-main/
├── backend/
│   ├── server.py              # FastAPI app, API routes
│   ├── scoring.py             # All scoring logic
│   ├── product_fetcher.py     # 5-layer scraping pipeline
│   ├── admin.py               # Admin dashboard routes
│   ├── admin_db.py            # SQLite logging
│   ├── credits.py             # API credit tracking
│   ├── config.py              # Category averages, country configs
│   ├── data_loader.py         # CSV database loader
│   ├── .env.example           # Template — copy to .env and fill in keys
│   ├── requirements.txt       # Python dependencies
│   ├── database/              # Ingredient databases
│   │   ├── ingredient_master.csv
│   │   ├── uv_sun_tanning_db.csv
│   │   ├── clinical_synergy_registry.csv
│   │   ├── active_upgrade_map.csv
│   │   └── evidence_quality_mapping.csv
│   └── templates/             # Admin HTML templates
│       ├── admin_dashboard.html
│       └── admin_login.html
├── frontend/
│   ├── src/
│   │   ├── App.js             # Main React component
│   │   ├── App.css            # All styles
│   │   └── constants.js       # API URL, lists
│   ├── public/
│   │   └── index.html
│   └── package.json
└── README.md
```

---

## Setup Instructions

### Prerequisites
- Python 3.9+
- Node.js 16+
- npm

### 1. Backend Setup

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Create .env file from example
cp .env.example .env
# Edit .env and fill in your keys

# Run the backend
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create frontend .env
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env

# Start development server
npm start
```

### 3. Access

- **Main Tool**: http://localhost:3000
- **Admin Dashboard**: http://localhost:8001/admin
- **API Health**: http://localhost:8001/api/health

---

## Environment Variables

### Backend (`backend/.env`)

```env
# Required
ADMIN_PASSWORD=your_admin_password_here
SESSION_SECRET=generate_a_random_string_here

# Optional API keys (tool works without them, features degrade gracefully)
FIRECRAWL_API_KEY=
SCRAPDO_API_KEY=
SCRAPERAPI_KEY=
SERPER_API_KEY=
HUGGINGFACE_API_KEY=
EXCHANGE_RATE_API_KEY=
```

### Frontend (`frontend/.env`)

```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

---

## Deployment (Render)

### Backend
1. Create a new **Web Service** on Render
2. Connect your GitHub repo
3. Set **Root Directory**: `backend`
4. Set **Build Command**: `pip install -r requirements.txt`
5. Set **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
6. Add Environment Variables in Render dashboard (same keys as `.env` above)

### Frontend
1. Create a new **Static Site** on Render
2. Set **Root Directory**: `frontend`
3. Set **Build Command**: `npm install && npm run build`
4. Set **Publish Directory**: `build`
5. Add Environment Variable: `REACT_APP_BACKEND_URL=https://your-backend-render-url.com`

---

## API Reference

### POST /api/analyze
```json
{
  "ingredients": "Aqua, Niacinamide, ...",
  "price": 599,
  "size_ml": 30,
  "category": "Serum",
  "skin_concerns": ["Acne & Oily Skin"],
  "skin_type": "oily",
  "country": "India",
  "currency": "INR"
}
```

### POST /api/fetch-product
Auto-fetch product data from URL or barcode.

### POST /api/find-alternatives
Find better alternatives for weak concern scores.

### POST /api/best-price
Find cheapest price across platforms.

### GET /api/health
Health check.

---

## Security

- Rate limiting: 10 requests/minute per IP
- Input sanitization on all fields
- CORS locked to configured domains only
- Admin dashboard password-protected with session tokens

---

## License

Proprietary. All rights reserved.
