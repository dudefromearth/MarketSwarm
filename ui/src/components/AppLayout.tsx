// ui/src/components/AppLayout.tsx
// Layout wrapper for app pages

import type { ReactNode } from "react";

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppLayout({ children }: AppLayoutProps) {
  return <>{children}</>;
}
