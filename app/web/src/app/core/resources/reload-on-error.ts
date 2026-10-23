import { effect, ResourceRef } from '@angular/core';

/**
 * Relance `resource` `delayMs` après une erreur. Un flux en échec ne reprend pas seul : sans cela, le
 * rafraîchissement périodique d'un `rxResource` s'arrêterait au premier appel raté.
 * À appeler dans un contexte d'injection.
 */
export function reloadOnError(resource: ResourceRef<unknown>, delayMs: number): void {
  effect((onCleanup) => {
    if (resource.status() !== 'error') {
      return;
    }
    const id = setTimeout(() => resource.reload(), delayMs);
    onCleanup(() => clearTimeout(id));
  });
}
