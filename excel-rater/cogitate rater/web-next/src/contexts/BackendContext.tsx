"use client";

import { createContext, useContext, useEffect, useState } from "react";

type BackendStatus = "checking" | "online" | "offline";

interface BackendContextType {
  status: BackendStatus;
  url: string;
}

const BackendContext = createContext<BackendContextType | undefined>(undefined);

export function BackendProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<BackendStatus>("checking");
  const [url, setUrl] = useState<string>("");

  useEffect(() => {
    const checkBackend = async () => {
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
        setUrl(apiBase);
        
        // Add timeout to avoid hanging indefinitely
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch(`${apiBase}/api/health`, { 
          cache: "no-store",
          signal: controller.signal
        });
        clearTimeout(timeout);
        
        if (response.ok) {
          setStatus("online");
          console.log("✓ Backend connection successful");
        } else {
          setStatus("offline");
          console.error("✗ Backend returned non-ok status:", response.status);
        }
      } catch (err) {
        setStatus("offline");
        console.error("✗ Backend connection failed:", err);
      }
    };
    checkBackend();
  }, []); // Runs only once on mount

  return (
    <BackendContext.Provider value={{ status, url }}>
      {children}
    </BackendContext.Provider>
  );
}

export function useBackendStatus() {
  const context = useContext(BackendContext);
  if (!context) {
    throw new Error("useBackendStatus must be used within BackendProvider");
  }
  return context;
}
