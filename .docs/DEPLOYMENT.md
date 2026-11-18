# ResQAI Deployment Guide

This document outlines the deployment configuration for hosting ResQAI with the frontend on Vercel and the backend on Render.

## 1. Backend Deployment (Render)

1. Log in to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** and select **Web Service**.
3. Connect your GitHub repository (`SaiKarun-28/ResQAI`).
4. Configure the service parameters:
   - **Name**: `resqai-backend`
   - **Root Directory**: `Backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt --break-system-packages`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Add required environment variables under **Environment**:
   - `GEMINI_API_KEY` or `GROQ_API_KEY` (depending on which LLM provider you use).
   - `CORS_ORIGINS`: Set to your Vercel frontend URL (e.g., `https://resqai.vercel.app` or `*` for development).
6. Click **Create Web Service**. Note your Render backend URL (e.g., `https://resqai-backend.onrender.com`).

## 2. Frontend Deployment (Vercel)

1. Log in to your [Vercel Dashboard](https://vercel.com).
2. Click **Add New...** -> **Project** and import your GitHub repository (`SaiKarun-28/ResQAI`).
3. Configure project settings:
   - **Root Directory**: Click **Edit** and select `resqai-frontend`.
   - **Framework Preset**: `Vite`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add environment variables under **Environment Variables**:
   - `VITE_API_BASE_URL`: Set to your Render backend URL (e.g., `https://resqai-backend.onrender.com`). *Note: Do not include a trailing slash.*
5. Click **Deploy**.

## 3. Verification

Once deployment completes:
- Access the backend interactive docs at `https://<your-render-url>/docs`.
- Access the frontend dashboard at `https://<your-vercel-domain>`.
