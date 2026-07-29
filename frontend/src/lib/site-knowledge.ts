import type { SiteStats } from "../types";

export const REVIEW_DATA_SOURCES = [
  {
    name: "OpenCritic",
    url: "https://opencritic.com/",
    role: "Professional critic review records, normalized scores, outlets, and journalist profiles.",
  },
  {
    name: "Steam",
    url: "https://store.steampowered.com/",
    role: "PC player sentiment expressed as the percentage of positive user reviews.",
  },
  {
    name: "Metacritic",
    url: "https://www.metacritic.com/",
    role: "Cross-platform user ratings converted from a 0–10 scale to 0–100.",
  },
] as const;

function baseUrl(siteUrl: string): string {
  return siteUrl.replace(/\/+$/, "");
}

export function siteKnowledgeIds(siteUrl: string) {
  const base = baseUrl(siteUrl);
  return {
    organization: `${base}/#organization`,
    website: `${base}/#website`,
    homepage: `${base}/#webpage`,
    aboutPage: `${base}/about#webpage`,
    dataset: `${base}/about#dataset`,
    faqPage: `${base}/faq#webpage`,
  };
}

function organizationReference(siteUrl: string): Record<string, string> {
  return { "@id": siteKnowledgeIds(siteUrl).organization };
}

function websiteReference(siteUrl: string): Record<string, string> {
  return { "@id": siteKnowledgeIds(siteUrl).website };
}

function datasetReference(siteUrl: string): Record<string, string> {
  return { "@id": siteKnowledgeIds(siteUrl).dataset };
}

export function buildSiteKnowledgeGraph(siteUrl: string): Record<string, unknown> {
  const base = baseUrl(siteUrl);
  const ids = siteKnowledgeIds(base);
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        "@id": ids.organization,
        name: "ReviewDisparity",
        url: `${base}/`,
        logo: {
          "@type": "ImageObject",
          url: `${base}/logo.png`,
          width: 900,
          height: 715,
        },
        description:
          "Independent publisher of data-derived comparisons between professional video game review scores and Steam and Metacritic user scores.",
        knowsAbout: [
          "Video game criticism",
          "Video game user reviews",
          "Review score normalization",
          "Critic and player score disparity",
        ],
        publishingPrinciples: `${base}/about#editorial-principles`,
        correctionsPolicy: `${base}/about#editorial-principles`,
      },
      {
        "@type": "WebSite",
        "@id": ids.website,
        name: "ReviewDisparity",
        alternateName: "Review Disparity",
        url: `${base}/`,
        description:
          "Track critic-versus-player score differences across video games, journalists, and outlets.",
        publisher: organizationReference(base),
        about: datasetReference(base),
        potentialAction: {
          "@type": "SearchAction",
          target: {
            "@type": "EntryPoint",
            urlTemplate: `${base}/search?q={search_term_string}`,
          },
          "query-input": "required name=search_term_string",
        },
      },
    ],
  };
}

export function buildHomePageJsonLd(siteUrl: string): Record<string, unknown> {
  const base = baseUrl(siteUrl);
  const ids = siteKnowledgeIds(base);
  return {
    "@context": "https://schema.org",
    "@type": "WebPage",
    "@id": ids.homepage,
    url: `${base}/`,
    name: "ReviewDisparity — Game Critic vs Player Score Tracker",
    description:
      "Independent, source-linked analysis of the difference between professional video game review scores and Steam and Metacritic user scores.",
    isPartOf: websiteReference(base),
    about: datasetReference(base),
    publisher: organizationReference(base),
  };
}

export function buildDatasetJsonLd(
  siteUrl: string,
  stats?: SiteStats | null,
): Record<string, unknown> {
  const base = baseUrl(siteUrl);
  const ids = siteKnowledgeIds(base);
  return {
    "@type": "Dataset",
    "@id": ids.dataset,
    identifier: ids.dataset,
    name: "ReviewDisparity Video Game Review Alignment Dataset",
    alternateName: "ReviewDisparity critic-versus-player dataset",
    description:
      "A continuously updated collection of normalized professional video game review scores and corresponding Steam and Metacritic user scores, organized by game, journalist, and outlet to measure critic-versus-player disparity.",
    url: `${base}/about#dataset`,
    creator: organizationReference(base),
    publisher: organizationReference(base),
    license: `${base}/terms`,
    isAccessibleForFree: true,
    isBasedOn: REVIEW_DATA_SOURCES.map((source) => source.url),
    measurementTechnique:
      "Source scores are normalized to 0–100. Disparity is critic score minus the corresponding Steam or Metacritic user score; source disparities remain separate and may also be averaged.",
    variableMeasured: [
      {
        "@type": "PropertyValue",
        name: "Normalized critic score",
        description: "Professional review score normalized to a 0–100 scale.",
      },
      {
        "@type": "PropertyValue",
        name: "Steam user score",
        description: "Percentage of positive Steam user reviews on a 0–100 scale.",
      },
      {
        "@type": "PropertyValue",
        name: "Metacritic user score",
        description: "Metacritic user rating converted to a 0–100 scale.",
      },
      {
        "@type": "PropertyValue",
        name: "Review disparity",
        description: "Critic score minus user score, calculated separately by user-score source.",
      },
      {
        "@type": "PropertyValue",
        name: "Review timing",
        description: "Review publication timing relative to a game's release date.",
      },
    ],
    keywords: [
      "video game reviews",
      "critic scores",
      "Steam user reviews",
      "Metacritic user scores",
      "review disparity",
      "game journalists",
    ],
    ...(stats?.last_updated && { dateModified: stats.last_updated }),
  };
}

export function buildAboutKnowledgeGraph(
  siteUrl: string,
  stats?: SiteStats | null,
): Record<string, unknown> {
  const base = baseUrl(siteUrl);
  const ids = siteKnowledgeIds(base);
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "AboutPage",
        "@id": ids.aboutPage,
        name: "How ReviewDisparity Works",
        description:
          "ReviewDisparity methodology, dataset scope, provenance, limitations, and publishing principles.",
        url: `${base}/about`,
        isPartOf: websiteReference(base),
        mainEntity: datasetReference(base),
        about: datasetReference(base),
        publisher: organizationReference(base),
        ...(stats?.last_updated && { dateModified: stats.last_updated }),
      },
      buildDatasetJsonLd(base, stats),
    ],
  };
}

export function buildFaqPageJsonLd(
  siteUrl: string,
  faqs: ReadonlyArray<{ question: string; answer: string }>,
): Record<string, unknown> {
  const base = baseUrl(siteUrl);
  const ids = siteKnowledgeIds(base);
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    "@id": ids.faqPage,
    url: `${base}/faq`,
    name: "ReviewDisparity Frequently Asked Questions",
    isPartOf: websiteReference(base),
    about: datasetReference(base),
    publisher: organizationReference(base),
    mainEntity: faqs.map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };
}
