import { describe, expect, it } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { ProductImage } from './ProductImage';
import { mockApi, renderAt } from '../test/render';

const URL_OK = 'https://images.example-cdn.com/products/tee-black.jpg';

function show(mode: 'demo' | 'imported', el: JSX.Element) {
  window.localStorage.setItem('ml-data-mode', mode);
  mockApi(() => undefined);
  return renderAt('/', [{ path: '/', element: el }]);
}

describe('ProductImage', () => {
  it('shows an imported product image from its safe URL, without a referrer', () => {
    show('imported', <ProductImage productId="IMG-1" name="Black tee" url={URL_OK} caption />);
    const img = screen.getByRole('img', { name: /black tee/i });
    expect(img).toHaveAttribute('src', URL_OK);
    expect(img).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(screen.getByText(/image from the imported dataset/i)).toBeInTheDocument();
  });

  it('falls back to the local generic image when the external image fails', () => {
    const { container } = show('imported', <ProductImage productId="IMG-1" name="Black tee" url={URL_OK} />);
    fireEvent.error(container.querySelector('img')!);
    expect(container.querySelector('img')!.getAttribute('src')).toBe('/images/product-placeholder.svg');
  });

  it('uses the generic image when no safe URL was sent, and Demo artwork for Demo products', () => {
    const a = show('imported', <ProductImage productId="IMG-3" name="No image" url={null} />);
    expect(a.container.querySelector('img')!.getAttribute('src')).toBe('/images/product-placeholder.svg');
    a.unmount();
    const b = show('demo', <ProductImage productId="DEMO-P-001" name="Tee" url={URL_OK} />);
    expect(b.container.querySelector('img')!.getAttribute('src')).toBe('/demo-images/DEMO-P-001.svg');
  });
});
