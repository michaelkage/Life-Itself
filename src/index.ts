import { StrictMode, createElement } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './styles/globals.css';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Life Itself requires a #root element in index.html');
}

createRoot(rootElement).render(
  createElement(StrictMode, null, createElement(App)),
);
