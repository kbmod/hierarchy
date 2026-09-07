import { createFileRoute } from "@tanstack/react-router";
import { HierarchyApp } from "@/components/hierarchy-app";

export const Route = createFileRoute("/")({ component: Home });

function Home() {
  return <HierarchyApp />;
}
