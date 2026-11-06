import { useState } from 'react';
import { useDataMode } from '../lib/dataMode';

const FALLBACK = '/demo-images/fallback.svg';
const DEMO_ID = /^DEMO-P-\d{3}$/;

/** Local, self-contained demo artwork for synthetic Demo products. */
export function demoImageSrc(mode: string, productId?: string | null): string | null {
  return mode === 'demo' && productId && DEMO_ID.test(productId) ? `/demo-images/${productId}.svg` : null;
}

/**
 * Demo products show fictional, locally served artwork (labelled as such). Other products use the local generic
 * image: imported placeholder-host URLs are never loaded and nothing is presented as a real product photo.
 */
export function ProductImage({ productId, name, caption = false }: { kind?: string; productId?: string | null; name?: string | null; caption?: boolean }) {
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
  return (
    <figure className="product-image">
      <img src="/images/product-placeholder.svg" alt="" width={120} height={120} />
      <figcaption className={caption ? 'product-image__caption' : 'visually-hidden'}>No product photo in this dataset</figcaption>
    </figure>
  );
}
