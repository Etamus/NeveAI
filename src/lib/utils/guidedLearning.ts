// Old drafts and queued requests may contain both flags. Learn takes precedence.
export const normalizeLearningRequestFeatures = (features: Record<string, any>) =>
	features.guided_learning ? { ...features, file_generation: false } : features;
