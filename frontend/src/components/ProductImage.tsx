import { useState } from 'react';
import { useDataMode } from '../lib/dataMode';
import { DEMO_PHOTOS, type DemoPhoto } from '../lib/demoPhotos';

const FALLBACK = '/demo-images/fallback.svg';
const GENERIC = '/images/product-placeholder.svg';
const DEMO_ID = /^DEMO-P-\d{3}$/;

/** Local, self-contained demo artwork for synthetic Demo products. */
export function demoImageSrc(mode: string, productId?: string | null): string | null {
  return mode === 'demo' && productId && DEMO_ID.test(productId) ? `/demo-images/${productId}.svg` : null;
}

/** A locally stored, openly licensed stock photo of a similar product, when one exists for a Demo product. */
export function demoPhoto(mode: string, productId?: string | null): DemoPhoto | null {
  return mode === 'demo' && productId ? DEMO_PHOTOS[productId] ?? null : null;
}

/** The thumbnail for tables and small lists: Demo photo, else Demo artwork, else a safe imported URL. */
export function thumbnailSrc(mode: string, productId?: string | null, url?: string | null): string | null {
  return demoPhoto(mode, productId)?.src ?? demoImageSrc(mode, productId) ?? url ?? null;
}

function PhotoCredit({ p }: { p: DemoPhoto }) {
  return (
    <>
      Stock photo of a similar product; colour and model may differ. Photo: {p.author},{' '}
      {p.licenseUrl ? <a href={p.licenseUrl} target="_blank" rel="noopener noreferrer">{p.license}</a> : p.license}, via{' '}
      <a href={p.source} target="_blank" rel="noopener noreferrer">Wikimedia Commons</a>.
    </>
  );
}

/**
 * Demo products show a locally stored, credited stock photo of a similar product (falling back to their local
 * SVG artwork), or the artwork when no suitable photo exists. Imported products show their image only when the
 * API sent a safe URL, without a referrer, falling back to the local generic image. Nothing is presented as a
 * photo of the exact product.
 */
export function ProductImage({ productId, name, url, caption = false }: { kind?: string; productId?: string | null; name?: string | null; url?: string | null; caption?: boolean }) {
  const { mode } = useDataMode();
  const photo = demoPhoto(mode, productId);
  const demo = demoImageSrc(mode, productId);
  const [photoFailed, setPhotoFailed] = useState(false);
  const [failed, setFailed] = useState(false);
  if (photo && !photoFailed) {
    return (
      <figure className="product-image product-image--photo product-image--stock">
        <img src={photo.src} alt={`${name ?? productId}: stock photo of a similar product`} width={240} height={240} loading="lazy" decoding="async"
          style={{ objectPosition: photo.focus }} onError={() => setPhotoFailed(true)} />
        <figcaption className={caption ? 'product-image__caption' : 'visually-hidden'}><PhotoCredit p={photo} /></figcaption>
      </figure>
    );
  }
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
