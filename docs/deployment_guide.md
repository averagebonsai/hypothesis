# Deployment Guide: Render (Backend) & Vercel (Frontend)

This guide walks through deploying the Hypothesis Autonomous Multi-Agent Simulation Studio.

---

## Order of Deployment: Does the Order Matter?

**Yes! Always deploy Render (Backend) first, then Vercel (Frontend).**

### Why?
The Next.js frontend needs the live URL of your Render FastAPI backend (via `NEXT_PUBLIC_API_URL`) at build time. Deploying Render first gives you your live backend URL (e.g., `https://hypothesis-api.onrender.com`), which you can immediately plug into Vercel during project creation without needing a secondary rebuild.

---

## Step 1: Deploy FastAPI Backend on Render

1. **Log in to Render**: Go to [dashboard.render.com](https://dashboard.render.com).
2. **Create New Web Service**:
   - Click **New +** -> **Web Service**.
   - Connect your Git repository (`hypothesis`).
3. **Configure Service Details**:
   - **Name**: `hypothesis-api` (or your preferred name).
   - **Language / Runtime**: Choose **Docker**.
   - **Dockerfile Path**: `./Dockerfile` (or leave as default `./Dockerfile`).
   - **Region**: Choose the region closest to your users (e.g., Oregon, Ohio, Frankfurt, Singapore).
   - **Instance Type**: **Starter** ($7/mo) is recommended because it keeps the instance running continuously without sleeping. (Free tier also works for evaluation, but free instances sleep after 15 mins of inactivity).
4. **Environment Variables**:
   Under the **Environment Variables** section, add:
   - `PORT`: `8000`
   - `API_KEY`: `<Your Gemini / LLM API Key>`
   - `CORS_ORIGINS`: `*` (or your Vercel URL once generated, e.g. `https://hypothesis.vercel.app`)
5. **Health Check Path**:
   - Expand **Advanced Settings** and set **Health Check Path** to:
     ```
     /api/health
     ```
6. **Click "Create Web Service"**:
   - Render will build the Docker image using Python 3.13 and start Uvicorn.
   - Once deployment succeeds, copy your live service URL:
     `https://<your-service-name>.onrender.com`

---

## Step 2: Deploy Next.js Frontend on Vercel

1. **Log in to Vercel**: Go to [vercel.com](https://vercel.com).
2. **Import Project**:
   - Click **Add New...** -> **Project**.
   - Select your Git repository.
3. **Configure Project Settings**:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: Click **Edit** and select **`web`** (important! The Next.js app lives in `web/`).
4. **Environment Variables**:
   Under **Environment Variables**, add:
   - **Name**: `NEXT_PUBLIC_API_URL`
   - **Value**: `https://<your-service-name>.onrender.com` *(paste your Render backend URL from Step 1, without a trailing slash)*
5. **Deploy**:
   - Click **Deploy**.
   - Vercel will install dependencies, compile the pages, and provide your live URL (e.g. `https://hypothesis-web.vercel.app`).

---

## Step 3: (Optional) Lock Down CORS

Once your Vercel URL is live:
1. In your Render Dashboard, go to `hypothesis-api` -> **Environment**.
2. Change `CORS_ORIGINS` to:
   ```
   https://<your-vercel-app>.vercel.app
   ```
3. Save changes. Render will automatically redeploy the backend with strict CORS protection.
