import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { setWorkerUrl } from "maplibre-gl";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";

import App from "./App";
import "./index.css";

setWorkerUrl(workerUrl);

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
