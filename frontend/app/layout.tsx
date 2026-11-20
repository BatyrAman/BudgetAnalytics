import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Suspense } from "react";
import { ThemeProvider } from "next-themes";
import { Toaster } from "sonner";
import "./globals.css";

const inter = Inter({ subsets: ["latin", "cyrillic"], variable: "--font-inter" });
export const metadata: Metadata = {
  title: "BudgetAnalytics — личные финансы и AI-советник",
  description:
    "Демонстрационный интерфейс для учёта финансов, аналитики и персональных советов в Казахстане",
  applicationName: "BudgetAnalytics",
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F4F6F8" },
    { media: "(prefers-color-scheme: dark)", color: "#0D1117" },
  ],
};
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" className={`${inter.variable} bg-background`} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem>
          <Toaster position="bottom-right" richColors />
          {/* App pages read the URL (filters, ?new=1, dev state preview) and load data in
              the browser; one boundary lets them prerender without per-page wrappers. */}
          <Suspense fallback={null}>
            <div className="font-sans">{children}</div>
          </Suspense>
        </ThemeProvider>
      </body>
    </html>
  );
}
