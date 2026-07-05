import React from "react";
import ReactDOM from "react-dom/client";
import { Toaster } from "react-hot-toast";
import App from "./App";
import "./index.css";
import "./i18n";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <Toaster
      position="top-right"
      toastOptions={{
        style: {
          background: "#ffffff",
          color: "#1f2937",
          border: "1px solid var(--surface-border)",
          boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
        },
      }}
    />
  </React.StrictMode>
);
