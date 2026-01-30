// ui/src/components/AppLayout.tsx
// Layout wrapper that includes SiteHeader with user data

import { useEffect, useState, ReactNode } from "react";
import SiteHeader from "./SiteHeader";

interface Profile {
  display_name?: string;
  email?: string;
}

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  const [displayName, setDisplayName] = useState<string | null>(null);

  useEffect(() => {
    // Fetch user profile for display name
    fetch("/api/profile/me", { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Profile | null) => {
        if (data?.display_name) {
          setDisplayName(data.display_name);
        } else if (data?.email) {
          // Fallback to email prefix
          setDisplayName(data.email.split("@")[0]);
        }
      })
      .catch(() => {});
  }, []);

  return (
    <>
      <SiteHeader displayName={displayName} />
      {children}
    </>
  );
}
