/**
 * Service access. There is a single (browser) implementation; components
 * must use this singleton — never import ./browser/* directly.
 */
import type { Services } from './types';
import { browserServices } from './browser';

let cached: Promise<Services> | null = null;

export function getServices(): Promise<Services> {
  if (!cached) {
    cached = Promise.resolve(browserServices());
  }
  return cached;
}

/** Test-only escape hatch (resets the singleton between tests). */
export function _resetServicesForTests(): void {
  cached = null;
}
