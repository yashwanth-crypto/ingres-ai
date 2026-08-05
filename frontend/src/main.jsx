import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";
// Must load before our own stylesheet so the overrides in index.css win.
import "leaflet/dist/leaflet.css";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
