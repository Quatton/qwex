const FEATURE_PATTERN = /^(.+?)\[([^\]]+)\]$/;

export function parseFeatureKey(key: string): {
  base: string;
  feature: string | null;
} {
  const match = key.match(FEATURE_PATTERN);
  if (match && match[1] && match[2]) {
    return { base: match[1], feature: match[2] };
  }
  return { base: key, feature: null };
}

/**
 * Merge top-level feature keys into a single record for filtering.
 * E.g., { tasks: {...}, "tasks[docker]": {...} } => { tasks: {...all merged...} }
 */
export function mergeFeatureKeys<T>(def: Record<string, T>, baseKey: string): T | undefined {
  const merged: Record<string, unknown> = {};

  // Find all variants of this key
  for (const [key, value] of Object.entries(def)) {
    const { base, feature } = parseFeatureKey(key);
    if (base === baseKey && value && typeof value === "object") {
      // Create feature-suffixed keys for nested items
      for (const [itemKey, itemValue] of Object.entries(value as Record<string, unknown>)) {
        const mergedKey = feature ? `${itemKey}[${feature}]` : itemKey;
        merged[mergedKey] = itemValue;
      }
    }
  }

  return Object.keys(merged).length > 0 ? (merged as T) : undefined;
}

export function filterByFeatures<T>(
  record: Record<string, T> | undefined,
  features: Set<string>,
): Record<string, T> {
  if (!record) return {};

  const result: Record<string, T> = {};
  const featureOverrides = new Map<string, T>();

  for (const [key, value] of Object.entries(record)) {
    const { base, feature } = parseFeatureKey(key);

    if (feature === null) {
      // Plain key - add if not already set
      if (!(base in result)) {
        result[base] = value;
      }
    } else if (features.has(feature)) {
      // Feature key that's enabled - mark for override
      featureOverrides.set(base, value);
    }
    // Feature key that's not enabled - skip
  }

  // Apply feature overrides (they win over plain keys)
  for (const [base, value] of featureOverrides) {
    result[base] = value;
  }

  return result;
}

export function selectUses(
  rawModule: Record<string, unknown>,
  features: Set<string>,
): string | undefined {
  let uses: string | undefined;
  let featureUses: string | undefined;

  for (const [key, value] of Object.entries(rawModule)) {
    if (typeof value !== "string") continue;

    const { base, feature } = parseFeatureKey(key);
    if (base !== "uses") continue;

    if (feature === null) {
      uses = value;
    } else if (features.has(feature)) {
      featureUses = value;
    }
  }

  return featureUses ?? uses;
}
