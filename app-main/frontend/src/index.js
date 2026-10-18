import React from "react";
import ReactDOM from "react-dom/client";
import "@/index.css";
import "@/styles/tokens.css";
import "@/styles/base.css";
import "@/styles/components.css";
import "@/styles/landing.css";
import "@/styles/app.css";
import "@/styles/print.css";
import App from "@/App";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
