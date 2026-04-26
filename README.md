# Flowstate Backend

The intelligent engine behind **Flowstate**, a personal secretary that converts natural language todo lists into optimized Google Calendar schedules. This service manages the orchestration between the Google AI API (Gemini/Gemma), the Google Calendar API, and user preference state.

## 🌟 Features
- **Natural Language Parsing:** Interprets raw strings into structured calendar events.
- **AI-Driven Scheduling:** Uses Google AI models to intelligently place tasks based on priority and duration.
- **Google Calendar Sync:** Full bi-directional integration for adding, editing, and deleting events.
- **Stateless Auth:** Secure session management via Google OAuth 2.0 and JWT.

## 🚀 Tech Stack
- **Framework:** FastAPI (Python)
- **Database:** MongoDB (Motor Asyncio)
- **AI Integration:** Google AI Models (configured via environment)
- **Authentication:** Google OAuth 2.0 + JWT
- **Frontend Repo:** [flowstate-ai](https://github.com/xckev/flowstate-ai)

---

## Local Setup

### Prerequisites
- Python 3.10+
- MongoDB installed and running locally on default port 27017 (or a MongoDB Atlas URI)
- A Google Cloud Project with the Calendar API and OAuth enabled
- A Google AI API key

### Installation

1. **Clone the repository and enter the directory.**
2. **Create a virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Set up environment variables:**
   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and fill in the required values:
   - `GOOGLE_CLIENT_ID`: Your Google OAuth client ID.
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth client secret.
   - `GOOGLE_AI_API_KEY`: Your Google AI API Key from Google AI Studio.
   - `GOOGLE_MODEL_ID`: The ID of the model to use (e.g., `gemini-2.5-pro` or `gemma-4-31b-it`).
   - `MONGODB_URI`: E.g., `mongodb://localhost:27017`.
   - `MONGODB_DB_NAME`: E.g., `flowstate`.
   - `FRONTEND_ORIGIN`: Important for CORS. Default is `http://localhost:3000` or `http://localhost:5173`.
   - `SECRET_KEY`: A random string used to sign session JWTs.

### Running the Server

Start the development server using:
```bash
python run.py
```
Or via uvicorn directly:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://127.0.0.1:8000`. You can view the interactive API documentation at `http://127.0.0.1:8000/docs`.

---

## Frontend Integration Guide

This backend is designed to be fully stateless via JWTs, meaning you must attach the JWT token as a `Bearer` token to all protected API calls.

### 1. The Authentication Flow
We use standard OAuth 2.0 Authorization Code Flow.

1. **Start Login:** Frontend redirects the user to `GET /auth/login`. This endpoint returns a JSON object with an `authorization_url`. The frontend should `window.location.href = data.authorization_url`.
2. **User Grants Access:** Google handles the login UI.
3. **The Callback:** Google redirects the user back to the frontend's redirect URI with `?code=...&state=...` in the URL.
4. **Exchange Tokens:** The frontend extracts `code` and `state` and sends them to the backend: `GET /auth/callback?code=...&state=...`.
5. **Session Established:** The backend verifies everything, saves the Google tokens to the DB, and returns a JSON object containing your app's `token`, `email`, and `name`. 
6. **Save the Token:** The frontend should save this `token` (e.g., in `localStorage`) and attach it to the `Authorization` header for all subsequent requests:
   ```javascript
   headers: {
     "Authorization": `Bearer ${localStorage.getItem('token')}`
   }
   ```

### 2. Core API Endpoints

*(All endpoints except `/auth/login` and `/auth/callback` require the `Authorization: Bearer <token>` header)*

#### Auth
- `GET /auth/login` - Returns the Google OAuth URL to redirect the user to.
- `GET /auth/callback?code=&state=` - Exchanges the Google code for a backend JWT.
- `GET /auth/status` - Verifies the current JWT is valid and returns user info.
- `POST /auth/logout` - Deletes the user's OAuth tokens from the backend database. (Frontend should also delete the JWT from localStorage).

#### Calendar
- `GET /calendar/events?date=YYYY-MM-DD` - Fetches the user's existing events for the specified date directly from Google Calendar. Useful for rendering the "current state" before the AI modifies anything.

#### Preferences
- `GET /preferences` - Returns the user's saved scheduling preferences (e.g., wake time, sleep time, break frequency). Returns `404` if not set.
- `PUT /preferences` - Saves or updates the user's scheduling preferences. Send a JSON body matching the `UserPreferences` schema.

#### Schedule
- `POST /schedule/process` - The core AI endpoint. Sends the current calendar, the user's natural language todo list, and their preferences to the AI model. The AI figures out the optimal schedule, handling ambiguous times by assuming 1-hour blocks, and can even invite attendees if emails are provided. It directly executes API calls to Google Calendar to add, edit, or delete events. Returns a `ProcessResult` object containing a natural language `message` summarizing what changes were made, what items were held off, and any assumptions made.
