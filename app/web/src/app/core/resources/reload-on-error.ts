import { effect, ResourceRef } from '@angular/core';

/** Retries after an error, otherwise a failed `rxResource` stops refreshing. Call in an injection context. */
export function reloadOnError(resource: ResourceRef<unknown>, delayMs: number): void {
  effect((onCleanup) => {
    if (resource.status() !== 'error') {
      return;
    }
    const id = setTimeout(() => resource.reload(), delayMs);
    onCleanup(() => clearTimeout(id));
  });
}
