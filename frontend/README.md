# Workforce Scheduler frontend

A responsive React + Vite interface for the Workforce Scheduler. Dashboard and operations screens use explicitly labeled mock data until API integration is enabled.

## Run locally

```bash
cd frontend
npm install
npm run dev
```

The Vite development server prints its local URL. To create and preview a production build, run `npm run build` and `npm run preview`.

Set `VITE_API_URL` to change the API base URL. It defaults to `http://localhost:8000/api`. API helpers are intentionally not called automatically.
