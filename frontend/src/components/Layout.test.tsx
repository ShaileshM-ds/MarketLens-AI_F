import { describe, expect, it } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Layout } from './Layout';
import { mockApi, renderAt } from '../test/render';

const routes = [{ path: '/', element: <Layout /> }];

describe('App shell', () => {
  it('switches between light and dark themes', async () => {
    mockApi(() => ({ body: {} }));
    window.localStorage.setItem('ml-theme', 'light');
    renderAt('/', routes);
    await userEvent.click(screen.getByRole('button', { name: 'Switch to dark theme' }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await userEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }));
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('opens and closes the mobile navigation', async () => {
    mockApi(() => ({ body: {} }));
    renderAt('/', routes);
    const nav = screen.getByRole('complementary', { name: 'Main navigation' });
    expect(nav).not.toHaveClass('sidebar--open');
    await userEvent.click(screen.getByRole('button', { name: 'Open navigation' }));
    expect(nav).toHaveClass('sidebar--open');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(nav).not.toHaveClass('sidebar--open');
  });
});
