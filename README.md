# 🌸 AlmaDiet — AI-Powered Pregnancy Diet Recommendation System

A full-stack pregnancy diet recommendation app featuring ML-powered meal planning, trimester-specific South Indian cuisine, and multilingual support.

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **ML-Powered Diet** | Random Forest model (R² = 95.14%) predicts nutrient needs per trimester |
| 🍛 **120+ Meals** | Curated South Indian meals from Kerala, Tamil Nadu, Karnataka & Andhra Pradesh |
| 🌍 **5 Languages** | English, Malayalam, Tamil, Kannada, Telugu |
| 📊 **Health Tracking** | Track weight, hemoglobin, blood pressure, blood sugar monthly |
| 🚨 **Emergency System** | Report & manage pregnancy emergencies (GDM, preeclampsia, etc.) |
| 🏥 **WHO Aligned** | Meals include WHO dietary alignment and cautions |
| 📱 **Cross-Platform** | Flutter app for Android & Windows |

## 🏗️ Architecture

```
almadiet/
├── backend/                   # FastAPI + PostgreSQL
│   ├── main.py               # App entry point with lifespan
│   ├── app/
│   │   ├── config.py         # Environment settings
│   │   ├── database.py       # Async PostgreSQL engine
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── routers/          # API endpoints (5 routers)
│   │   ├── services/         # Business logic
│   │   └── ml/               # Random Forest ML model
│   ├── data/
│   │   └── meals_dataset.json # 120+ curated meals
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                  # Flutter (Riverpod + GoRouter)
│   └── lib/
│       ├── app.dart          # App entry with theme & localization
│       ├── core/             # Theme, router, API client, utils
│       ├── features/         # 9 screens (onboarding → profile)
│       └── providers/        # Riverpod state management
└── docker-compose.yml
```

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+** — Backend
- **PostgreSQL 15+** — Database
- **Flutter 3.20+** — Frontend
- **Git**

### 1. Clone & Setup Backend

```bash
cd almadiet/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### 2. Setup PostgreSQL

```sql
-- Create database
CREATE DATABASE almadiet;

-- Set password (if not set)
ALTER USER postgres PASSWORD 'almadiet2026';
```

Update `.env`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:almadiet2026@localhost:5432/almadiet
JWT_SECRET_KEY=your-secret-key
```

### 3. Start Backend

```bash
cd backend
python -c "import uvicorn; uvicorn.run('main:app', host='0.0.0.0', port=8000)"
```

The server will:
- ✅ Create all database tables
- ✅ Seed 120+ meals from dataset
- ✅ Train ML model (first run)
- ✅ Serve API at http://localhost:8000
- ✅ Swagger UI at http://localhost:8000/docs

### 4. Start Frontend

```bash
cd frontend

# Get packages
flutter pub get

# Run on Windows
flutter run -d windows

# Or run on Android
flutter run -d android
```

### 5. Docker (Alternative)

```bash
# From project root
docker compose up -d

# Backend at http://localhost:8000
# PostgreSQL at localhost:5432
```

## 📡 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login (returns JWT) |
| GET | `/api/auth/me` | Get current user |
| PUT | `/api/auth/me` | Update profile |

### Health Records
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/health/record` | Submit health data |
| GET | `/api/health/records` | List user records |
| GET | `/api/health/analyze/{id}` | Clinical analysis |

### Diet Plans
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/diet/generate` | Generate ML-powered plan |
| GET | `/api/diet/plans` | List diet plans |
| POST | `/api/diet/feedback` | Submit feedback |

### Meals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/meals` | List meals (filter by region, trimester, type) |
| GET | `/api/meals/{id}` | Get meal details |

### Emergency
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/emergency/report` | Report emergency |
| GET | `/api/emergency/list` | List emergencies |
| POST | `/api/emergency/resolve` | Resolve emergency |

## 🧠 ML Model

- **Algorithm**: Random Forest Regressor (multi-output)
- **Accuracy**: R² = 95.14% on test set
- **Features**: Trimester, weight, BMI, hemoglobin, blood pressure, blood sugar, age, gestational diabetes flag
- **Targets**: 7 nutrients — Calories, Protein, Iron, Calcium, Folate, Fiber, Vitamin C
- **Training data**: Generated from WHO pregnancy nutrition guidelines

## 📱 Flutter App Screens

| Screen | Features |
|--------|----------|
| **Onboarding** | 3-slide intro with orbiting emojis, animated gradient background |
| **Login** | Floating logo, staggered field animations, async error handling |
| **Register** | Region/language dropdowns with emojis, responsive layout |
| **Home** | Daily health tips, quick actions, health summary, meal preview |
| **Health Input** | Sectioned form, dietary preference cards, auto-generate toggle |
| **Diet Plan** | Nutrient targets, emoji meal categories, staggered card animations |
| **Meal Detail** | Nutrition grid, ingredients, benefits, WHO alignment, cautions |
| **Emergency** | Type selector with emojis, report/resolve, active/resolved status |
| **Profile** | Image picker (camera/gallery), profile editor, language switcher |

## 🔧 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `JWT_SECRET_KEY` | JWT signing secret | Required |
| `GEMINI_API_KEY` | Google Gemini API key (optional) | - |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `DEBUG` | Enable debug mode | `true` |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `*` |

## 🏥 Supported Meal Regions

- 🌴 **Kerala** — Avial, Puttu, Appam, Fish Curry, Payasam
- 🛕 **Tamil Nadu** — Idli, Dosa, Sambar, Rasam, Pongal
- 🏛️ **Karnataka** — Ragi Mudde, Bisi Bele Bath, Akki Roti
- 🌶️ **Andhra Pradesh** — Pesarattu, Gongura, Pulihora

## 📄 License

This project was created for educational purposes as part of a pregnancy nutrition research initiative.

---

**Built with ❤️ for healthy pregnancies** 🌸
