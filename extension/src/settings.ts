export type UserPreferences = {
  validatorPassScore: number | null;
  maxOptimizationAttempts: number;
};

export const DEFAULT_PREFERENCES: UserPreferences = {
  validatorPassScore: null,
  maxOptimizationAttempts: 2,
};

export async function loadPreferences(): Promise<UserPreferences> {
  const saved = await chrome.storage.local.get(DEFAULT_PREFERENCES);
  const score = saved.validatorPassScore;
  const attempts = saved.maxOptimizationAttempts;
  return {
    validatorPassScore: typeof score === "number" && score >= 1 && score <= 10 ? score : null,
    maxOptimizationAttempts: typeof attempts === "number" && attempts >= 1 && attempts <= 5
      ? attempts
      : DEFAULT_PREFERENCES.maxOptimizationAttempts,
  };
}

export async function savePreferences(preferences: UserPreferences): Promise<void> {
  await chrome.storage.local.set(preferences);
}
