const SEED = 9338n;

export function hash(content: Parameters<Bun.Hash["wyhash"]>[0]): bigint {
  return Bun.hash.wyhash(content, SEED);
}
