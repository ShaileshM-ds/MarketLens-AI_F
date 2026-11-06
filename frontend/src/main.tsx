import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { createQueryClient } from './lib/queryClient';
import { ThemeProvider } from './lib/theme';
import { DataModeProvider } from './lib/dataMode';
import { CompareProvider } from './lib/compareSelection';
import { App } from './App';
import './styles/tokens.css';
import './styles/global.css';
import './styles/explorer.css';
import './styles/phase4.css';
import './styles/phase5.css';
import './styles/phase6.css';

const queryClient = createQueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <DataModeProvider>
          <CompareProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </CompareProvider>
        </DataModeProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
