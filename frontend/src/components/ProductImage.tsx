import { useState } from 'react';
import { useDataMode } from '../lib/dataMode';

const FALLBACK = '/demo-images/fallback.svg';
const GENERIC = '/images/product-placeholder.svg';
const DEMO_ID = /^DEMO-P-\d{3}$/;

/** Local, self-contained demo artwork for synthetic Demo products. */
export function demoImageSrc(mode: string, productId?: string | null): string | null {
  return mode === 'demo' && productId && DEMO_ID.test(productId) ? `/demo-images/${productId}.svg` : null;
}

/** The thumbnail to show in tables and small lists: Demo artwork, else a safe imported URL, else nothing. */
export function thumbnailSrc(mode: string, productId?: string | null, url?: string | null): string | null {
  return demoImageSrc(mode, productId) ?? url ?? null;
}

/**
 * Demo products show fictional, locally served artwork. Imported products show their image only when the API
 * sent a safe URL (https, allowed host); it loads without a referrer and falls back to the local generic image
 * if it fails. Otherwise the local generic image is shown and nothing is presented as a real product photo.
 */
export function ProductImage({ productId, name, url, caption = false }: { kind?: string; productId?: string | null; name?: string | null; url?: string | null; caption?: boolean }) {
  const { mode } = useDataMode();
  const demo = demoImageSrc(mode, productId);
  const [failed, setFailed] = useState(false);
  if (demo) {
    return (
      <figure className="product-image product-image--art">
        <img src={failed ? FALLBACK : demo} alt={failed ? '' : `${name ?? productId} (synthetic demo artwork)`} width={240} height={240} loading="lazy" onError={() => setFailed(true)} />
        <figcaption className={caption ? 'product-image__caption' : 'visually-hidden'}>Synthetic demo artwork, not a product photo</figcaption>
      </figure>
    );
  }
  if (url && !failed) {
    return (
      <figure className="product-image product-image--photo">
        <img src={url} alt={name ?? productId ?? 'Product image'} width={240} height={240} loading="lazy" referrerPolicy="no-referrer" decoding="async" onError={() => setFailed(true)} />
        <figcaption className={caption ? 'product-image__caption' : 'visually-hidden'}>Image from the imported dataset</figcaption>
      </figure>
    );
  }
  return (
    <figure className="product-image">
      <img src={GENERIC} alt="" width={120} height={120} />
      <figcaption className={caption ? 'product-image__caption' : 'visually-hidden'}>{url ? 'The image from the dataset could not be loaded' : 'No product photo in this dataset'}</figcaption>
    </figure>
  );
}
