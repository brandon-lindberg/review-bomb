import { Suspense } from "react";
import type { Metadata } from "next";
import "./globals.css";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { ThemeProvider } from "@/components/ThemeProvider";
import { GoogleAnalytics } from "@/components/GoogleAnalytics";
import { NavigationProgress } from "@/components/NavigationProgress";
import { getSiteUrl } from "@/lib/site-url";

const siteUrl = getSiteUrl();

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "ReviewDisparity - Game Critic vs User Score Tracker",
    template: "%s | ReviewDisparity",
  },
  description:
    "Track the disparity between game journalist review scores and user scores from Steam and Metacritic. See which critics align with players and which diverge.",
  icons: {
    icon: [
      { url: "/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32x32.png", sizes: "32x32", type: "image/png" },
    ],
    apple: [
      { url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },
  manifest: "/site.webmanifest",
  openGraph: {
    type: "website",
    locale: "en_US",
    siteName: "ReviewDisparity",
    title: "ReviewDisparity - Game Critic vs User Score Tracker",
    description:
      "Track the disparity between game journalist review scores and user scores from Steam and Metacritic.",
    url: "/",
    images: [
      {
        url: `${siteUrl}/logo.png`,
        width: 900,
        height: 715,
        alt: "ReviewDisparity Logo",
      },
    ],
  },
  twitter: {
    card: "summary",
    title: "ReviewDisparity - Game Critic vs User Score Tracker",
    description:
      "Track the disparity between game journalist review scores and user scores from Steam and Metacritic.",
    images: [`${siteUrl}/logo.png`],
  },
  robots: {
    index: true,
    follow: true,
  },
  alternates: {
    canonical: "/",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var stored=localStorage.getItem("theme");var t=stored||"dark";var resolved=t==="system"?(window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"):t;var root=document.documentElement;root.classList.remove("light","dark");root.classList.add(resolved);}catch(e){document.documentElement.classList.add("dark");}})();`,
          }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "WebSite",
              name: "ReviewDisparity",
              url: siteUrl,
              description:
                "Track the disparity between game journalist review scores and user scores from Steam and Metacritic.",
              publisher: {
                "@type": "Organization",
                name: "ReviewDisparity",
                logo: {
                  "@type": "ImageObject",
                  url: `${siteUrl}/logo.png`,
                },
              },
            }),
          }}
        />
      </head>
      <body
        className="antialiased"
        style={{ backgroundColor: "var(--background)", color: "var(--foreground)" }}
      >
        <Suspense fallback={null}>
          <NavigationProgress />
        </Suspense>
        <GoogleAnalytics />
        <ThemeProvider>
          <Header />
          <main className="site-shell mx-auto max-w-[88rem] px-4 py-8 sm:px-6 sm:py-10 lg:px-8">
            {children}
          </main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  );
}
