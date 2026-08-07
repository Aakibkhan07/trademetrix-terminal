import type { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: 'https://ai.trademetrix.tech',
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 1,
    },
    {
      url: 'https://ai.trademetrix.tech/pricing',
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.8,
    },
    {
      url: 'https://ai.trademetrix.tech/legal/privacy',
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: 'https://ai.trademetrix.tech/legal/terms',
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: 'https://ai.trademetrix.tech/legal/disclaimer',
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: 'https://ai.trademetrix.tech/legal/risk-disclosure',
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
    {
      url: 'https://ai.trademetrix.tech/legal/refund',
      lastModified: new Date(),
      changeFrequency: 'yearly',
      priority: 0.3,
    },
  ];
}
