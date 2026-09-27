import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import 'bootstrap/dist/css/bootstrap.min.css';
import './styles.css';
import { App } from './App';
import { getServices } from './services';

const root = document.getElementById('root');
if (!root) {
  throw new Error('Missing #root element');
}

// Resolve services before first render.
void getServices().then((services) => {
  createRoot(root).render(
    <StrictMode>
      <App services={services} />
    </StrictMode>,
  );
});
