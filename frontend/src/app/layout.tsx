import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { ThemeProvider } from "@/components/ThemeProvider";
import { GoogleAnalytics } from "@/components/GoogleAnalytics";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://reviewdisparity.com";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "ReviewDisparity - Game Critic vs User Score Tracker",
    template: "%s | ReviewDisparity",
  },
  description:
    "Track the disparity between game journalist review scores and user scores from Steam and Metacritic. See which critics align with players and which diverge.",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "ReviewDisparity",
    title: "ReviewDisparity - Game Critic vs User Score Tracker",
    description:
      "Track the disparity between game journalist review scores and user scores from Steam and Metacritic.",
    url: siteUrl,
  },
  twitter: {
    card: "summary",
    title: "ReviewDisparity - Game Critic vs User Score Tracker",
    description:
      "Track the disparity between game journalist review scores and user scores from Steam and Metacritic.",
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    canonical: siteUrl,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
        style={{ backgroundColor: "var(--background)", color: "var(--foreground)" }}
      >
        <GoogleAnalytics />
        <ThemeProvider>
          <Header />
          <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            {children}
          </main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}
