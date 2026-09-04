/**
 * Tiny async-resource wrapper for UI views. Holds loading/error/data state and
 * ignores stale responses when a newer request supersedes an in-flight one.
 */
export class AsyncResource<T, M = Record<string, unknown>> {
  value = $state<T | null>(null);
  meta = $state<M | null>(null);
  loading = $state(false);
  error = $state<string | null>(null);
  errorMeta = $state<Record<string, unknown> | null>(null);
  private seq = 0;

  async run(loader: () => Promise<{ data: T; meta: M }>): Promise<void> {
    const mySeq = ++this.seq;
    this.loading = true;
    this.error = null;
    this.errorMeta = null;
    try {
      const response = await loader();
      if (mySeq !== this.seq) return;
      this.value = response.data;
      this.meta = response.meta;
    } catch (err) {
      if (mySeq !== this.seq) return;
      this.error = err instanceof Error ? err.message : String(err);
      this.errorMeta =
        err && typeof err === 'object' && 'meta' in err ? (err as { meta?: Record<string, unknown> }).meta ?? null : null;
    } finally {
      if (mySeq === this.seq) this.loading = false;
    }
  }

  reset(): void {
    this.seq += 1;
    this.value = null;
    this.meta = null;
    this.loading = false;
    this.error = null;
    this.errorMeta = null;
  }
}
