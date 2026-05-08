import React from "react";
import { createRoot } from "react-dom/client";
import { DashboardApp } from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <DashboardApp />
  </React.StrictMode>
);
