import { createRoot } from "react-dom/client";
import { HierarchyApp } from "@/components/hierarchy-app";
import "../src/styles.css";

document.documentElement.setAttribute("data-native", "1");
document.documentElement.style.setProperty("--sat", "36px");

createRoot(document.getElementById("root")!).render(<HierarchyApp />);
